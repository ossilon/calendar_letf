"""BACKLOG B19: the long live check on real monthly-reset mutual funds, against real daily-reset funds.

    py scripts\\run_live_monthly.py            (from calendar_letf/, with CALENDAR_LETF_DATA / _RATES set)

The funds (all mutual funds; their daily NAVs come from the user's own price exports, their reports from SEC EDGAR):
    calendar (monthly) reset   DXSLX  S&P 500     2.5x daily to 2009-09-30, 2x monthly, 1.75x monthly from 2022-08-01
                               DXQLX  Nasdaq-100  the same three regimes
                               RMQHX  Nasdaq-100  2x monthly since 2014-11-28
    daily reset                ULPIX  S&P 500 2x;  UOPIX  Nasdaq-100 2x;  RYVYX  Nasdaq-100 2x;  RYNVX  S&P 500 1.5x
Every fact about them is read from reference/mutual_funds/ (SEC accession number on every row): the regimes and their
first days (regimes.csv, from regime_evidence.csv), the share splits (splits.csv), every report period's
distributions, NAVs, total return and expense ratio (highlights.csv), and the prospectus (497K) average annual returns
(anchors.csv).

What it does, in order, for each fund:
  1. NAV: the library's daily close, with every filed split the vendor did not apply put on today's share basis
     (navtr.apply_splits: the vendor applied some splits and not others).
  2. Total return: the reports print each period's payouts but no ex-dates, so each payout's ex-date is found in the
     NAV itself, as the day it falls by the payout on top of the move the leverage explains (navtr.residual,
     navtr.rebuild; the leverage drifts inside a calendar month: FINDINGS F17), and the payout is reinvested there.
  3. HARD TEST, part 1: every report period inside the check window must be reproduced within PERIOD_TOL_PP points,
     except rows the rules mark (REPORT INCONSISTENT: a no-payout row whose return is not its own NAV change; VENDOR
     NAV DIFFERS: the vendor's close at a period end is not the report's NAV, for example a stale copy of the day
     before). Part 2: every 497K return inside the window within its rounding (ANCHOR_PRINT_PP plus the NAV's cent
     at both ends) plus the most the undatable payouts (under DATABLE_FLOOR of NAV) can move it (navtr.anchor_bound),
     except rows marked VENDOR CLOSE STALE by rule (a start or end close that repeats the day before while the index
     moved) and the one figure marked FILING INCONSISTENT in anchors.csv, whose after-tax twin must then be reproduced
     instead. A payout no day explains inside the window also fails. A failure exits 1.
  4. Cost fit per fund and regime: the model (calendar kernel at the fund's L for a monthly fund, early reset off: no
     filed trigger; daily kernel for a daily fund) on the index total return, financing (L - 1) x DFF, the filed net
     expense ratio of each fiscal year, and one fitted number: the spread per NAV a year that makes the model grow
     exactly as the fund did (validate.fit_spread). It is a RESIDUAL: it holds the swap spread and everything else the
     model leaves out. Its interval: t(k-1) x SE over the k calendar years of the window.
  5. REAL vs REAL: the realized total-return gap between a calendar fund and a daily fund on the same index and dates
     (DXSLX vs ULPIX and DXQLX vs UOPIX, 2x, to 2022-07-29; RMQHX vs RYVYX from 2014-11-28), split into the fee
     difference and the rest, next to the model's gap for the same window at equal costs.
Writes results/live_monthly.json and results/live_monthly.md. Prints the provenance banner first.
"""
import csv
import json
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from calendar_letf import coverage, kernel, loader, navtr, periods, provenance, series, validate  # noqa: E402
from calendar_letf.stats import t975  # noqa: E402

OUT = ROOT / "results"
REF = ROOT / "reference" / "mutual_funds"
REFERENCE_FILES = ("regimes.csv", "regime_evidence.csv", "splits.csv", "highlights.csv", "anchors.csv")

FUNDS = ("DXSLX", "DXQLX", "RMQHX", "ULPIX", "UOPIX", "RYVYX", "RYNVX")
CALENDAR_FUNDS = ("DXSLX", "DXQLX", "RMQHX")
SYMBOL = {f: f"NASDAQ:{f}" for f in FUNDS}
# The check window starts at the first day of Direxion's monthly regime. The vendor history before it has many stale
# closes (a close repeated while the index moved; counted per fund in the results); they cancel over two days but
# break a check whose start or end falls on one. A fund whose earliest filed regime starts later is checked from then.
CHECK_FROM = "2009-10-01"
# Last day of the fits and the real-vs-real table: the rate file on hand ends 2026-10-08 (DFF), and a month end keeps
# every calendar fund's window ending at a reset. The total-return rebuild and its checks use the whole NAV history.
FIT_END = "2026-09-30"
PERIOD_TOL_PP = 0.10       # report periods: NAVs print to the cent (up to 0.05 points from both ends) plus the
#                            reinvestment day of a payout (the reports reinvest at the ex-date NAV, as here)
ANCHOR_PRINT_PP = 0.05     # base slack per 497K return: its own print rounding (0.005) plus the reinvestment day of a
#                            payout (one day later, on a 2% day, a 10% payout moves the level 0.2%: about 0.04 points
#                            a year over five years). The NAV's cent rounding and the undatable bound are added per anchor.
DATABLE_FLOOR = 0.005      # a payout under 0.5% of NAV cannot be dated: ordinary-day residuals reach 0.0015 (99th pct)
VENDOR_NAV_TOL = 0.002     # a period-end close more than 0.2% (log) from the report's NAV: the vendor's close is off
STALE_MOVE = 0.003         # a close equal to the day before while the index moved more than 0.3%: a stale close
REVERSAL_MOVE = 0.01       # model-vs-fund daily difference over 1% that the next day undoes (to 25%): a vendor glitch
#                            pair (seen: ULPIX 2020-03-11 and 2020-03-13, 10% and 17%); they cancel in growth but
#                            dominate a daily tracking error, so the fits report it with and without them
PAIRS = (("DXSLX", "ULPIX"), ("DXQLX", "UOPIX"), ("RMQHX", "RYVYX"))
SPREAD_FIT_RANGE = (-0.10, 0.20)
COVERAGE_RUNS = 4000        # per interval and world: Monte Carlo error 0.0034 on a coverage near 0.95
COVERAGE_FLOOR = 0.92       # an interval is VALID when both simulated worlds cover at least this often (3 points under
#                             0.95, about nine Monte Carlo errors); below it the interval is labeled too narrow


def coverage_of(values, key):
    """The simulated coverage of one yearly t interval (coverage.yearly_t_coverage) with its verdict; None when the
    interval itself is None (k < 2) or k < 3. The seed comes from the row's key, so a re-run gives the same draws."""
    v = list(values)
    if len(v) < 3:
        return None
    c = coverage.yearly_t_coverage(v, seed=zlib.crc32(key.encode("utf-8")), runs=COVERAGE_RUNS)
    c["verdict"] = "valid" if min(c["coverage_bootstrap"], c["coverage_ar1"]) >= COVERAGE_FLOOR else "too narrow"
    return c


# ---------------------------------------------------------------- reference tables

def table(name):
    with open(REF / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def regimes_of(fund):
    """[(first_day, last_day or None, L, reset, index)] in date order; last_day = the day before the next regime."""
    rows = sorted([r for r in table("regimes.csv") if r["fund"] == fund], key=lambda r: r["first_day"])
    out = []
    for i, r in enumerate(rows):
        nxt = rows[i + 1]["first_day"] if i + 1 < len(rows) else None
        last = (pd.Timestamp(nxt) - pd.Timedelta(days=1)).date().isoformat() if nxt else None
        out.append((r["first_day"], last, float(r["leverage"]), r["reset"], r["index"]))
    return out


def splits_of(fund):
    return [(pd.Timestamp(r["date"]), float(r["ratio"])) for r in table("splits.csv") if r["fund"] == fund]


def highlights_of(fund):
    return [r for r in table("highlights.csv") if r["fund"] == fund]


def window_start(fund):
    return max(CHECK_FROM, regimes_of(fund)[0][0])


# ---------------------------------------------------------------- the total-return rebuild

def residual(nav, idx_ret, regimes):
    """The NAV return the leverage does not explain, regime by regime. Days before the first filed regime take its
    terms (needed only to place payouts there; no check uses those days)."""
    lev = np.zeros(len(nav))
    for i, (a, b, L, reset, _index) in enumerate(regimes):
        lo = nav.index[0] if i == 0 else pd.Timestamp(a)
        m = (nav.index >= lo) & (nav.index <= (pd.Timestamp(b) if b else nav.index[-1]))
        if not m.any():
            continue
        ends = np.ones(m.sum(), dtype=bool) if reset == "daily" else periods.period_end_flags(nav.index[m], "monthly")
        lev[m] = navtr.effective_leverage(idx_ret[m], L, ends)   # starts at L on the regime's first row (a reset)
    nav_ret = nav.pct_change().fillna(0.0).to_numpy()
    return pd.Series(nav_ret - lev * idx_ret, index=nav.index)


def build(fund, index_tr):
    """dict(nav, tr, events, log, splits, resid, stale_closes) for one fund."""
    regimes = regimes_of(fund)
    nav = loader.close(SYMBOL[fund]).astype(float)
    nav, split_log = navtr.apply_splits(nav, splits_of(fund))
    idx = index_tr[regimes[0][4]].reindex(nav.index).ffill()
    if idx.isna().any():
        raise ValueError(f"{fund}: the index total return has no value on or before {idx[idx.isna()].index[0].date()}")
    idx_ret = idx.pct_change().fillna(0.0).to_numpy()
    resid = residual(nav, idx_ret, regimes)
    windows = navtr.payout_windows(highlights_of(fund))
    tr, events, log = navtr.rebuild(nav, resid, windows, [r for _, r in splits_of(fund)], DATABLE_FLOOR)
    stale = (nav.diff() == 0) & (np.abs(idx_ret) > STALE_MOVE)
    ws = pd.Timestamp(window_start(fund))
    return dict(nav=nav, tr=tr, events=events, log=log, resid=resid,
                splits=[(str(d.date()), r, s) for d, r, s in split_log],
                stale_closes_before_window=int(stale[nav.index < ws].sum()),
                stale_closes_in_window=int(stale[nav.index >= ws].sum()))


# ---------------------------------------------------------------- hard test, part 1: report periods

def vendor_nav_differs(nav, row, ratios):
    """True when the vendor's close at either end of a report period is not the report's NAV (on today's basis)."""
    before = nav.loc[:pd.Timestamp(row["period_start"]) - pd.Timedelta(days=1)]
    at_end = nav.loc[:row["period_end"]]
    if before.empty or not row["nav_begin"] or not row["nav_end"]:
        return False
    k, _ = navtr.snap_basis(navtr.basis_factor(before.iloc[-1], float(row["nav_begin"])), ratios)
    for v, rep in ((before.iloc[-1], row["nav_begin"]), (at_end.iloc[-1], row["nav_end"])):
        if abs(np.log(float(v) / (float(rep) * k))) > VENDOR_NAV_TOL:
            return True
    return False


def check_periods(fund, b):
    ws = window_start(fund)
    ratios = [r for _, r in splits_of(fund)]
    out = []
    for r in highlights_of(fund):
        if not r["total_return_pct"] or not r["nav_begin"]:
            continue
        if pd.Timestamp(r["period_start"]) <= b["nav"].index[0]:
            continue                                           # the series does not reach the close before the start
        got = navtr.period_return(b["tr"], r["period_start"], r["period_end"]) * 100
        pub = float(r["total_return_pct"])
        if not navtr.report_self_consistent(r):
            status = "REPORT INCONSISTENT"
        elif vendor_nav_differs(b["nav"], r, ratios):
            status = "VENDOR NAV DIFFERS"
        else:
            status = "ok"
        in_window = r["period_start"] >= ws
        gated = in_window and status == "ok"
        out.append(dict(fund=fund, start=r["period_start"], end=r["period_end"], kind=r["report_type"], published_pct=pub,
                        rebuilt_pct=round(got, 4), error_pp=round(got - pub, 4), status=status, in_window=in_window,
                        gated=gated, passed=(abs(got - pub) <= PERIOD_TOL_PP) if gated else None, accession=r["accession"]))
    return out


# ---------------------------------------------------------------- hard test, part 2: 497K anchors

def anchor_dates(a):
    """(start, end, years to annualize over or None) of one anchor row."""
    end = pd.Timestamp(a["as_of"])
    if a["period"] in ("1y", "5y", "10y"):
        n = int(a["period"][:-1])
        return end - pd.DateOffset(years=n), end, float(n)
    if a["period"] == "ytd":
        return pd.Timestamp(f"{end.year - 1}-12-31"), end, None
    start = pd.Timestamp(a["start"])                            # since inception
    years = (end - start).days / 365.25
    return start, end, (years if years > 1.0 else None)


def level(tr, d):
    s = tr.loc[:d]
    if s.empty:
        raise ValueError(f"no row on or before {pd.Timestamp(d).date()}")
    return float(s.iloc[-1])


def published_nav(fund, nav, d):
    """The vendor's close on or before d on the share basis printed AT THAT TIME (every filed split after d undone),
    which is the number that was rounded to the cent."""
    v = float(nav.loc[:d].iloc[-1])
    for when, ratio in splits_of(fund):
        if when > pd.Timestamp(d):
            v *= ratio
    return v


def is_stale(b, idx_ret_at, d):
    """True when the close on or before d repeats the close before it while the index moved more than STALE_MOVE."""
    s = b["nav"].loc[:d]
    if len(s) < 2:
        return False
    return bool(s.iloc[-1] == s.iloc[-2] and abs(idx_ret_at(s.index[-1])) > STALE_MOVE)


def check_anchors(fund, b, index_tr):
    """Every 497K return against the rebuilt series. Tolerance = the figure's own rounding (ANCHOR_PRINT_PP) + the
    NAV's rounding to the cent at both ends (on the basis printed then) + the most the undatable payouts can move
    it (navtr.anchor_bound), all carried through the annualizing."""
    ws = pd.Timestamp(window_start(fund))
    idx = index_tr[regimes_of(fund)[0][4]]
    idx_ret = idx.pct_change()
    rows = [a for a in table("anchors.csv") if a["fund"] == fund]
    out = []
    for a in rows:
        start, end, years = anchor_dates(a)
        if start < b["tr"].index[0] or end > b["tr"].index[-1]:
            continue
        C = level(b["tr"], end) / level(b["tr"], start)
        got = ((C ** (1.0 / years) - 1.0) if years else (C - 1.0)) * 100
        u = navtr.anchor_bound(b["log"], start, end)
        cents = 0.005 * (1.0 / published_nav(fund, b["nav"], start) + 1.0 / published_nav(fund, b["nav"], end))
        dC = C * (u + cents)                                    # the most the level ratio can be off
        slope = (C ** (1.0 / years - 1.0) / years) if years else 1.0
        tol = ANCHOR_PRINT_PP + slope * dC * 100
        pub = float(a["return_pct"])
        in_window = start >= ws
        stale = is_stale(b, lambda t: float(idx_ret.get(t, 0.0)), start) or is_stale(b, lambda t: float(idx_ret.get(t, 0.0)), end)
        status = a["status"] if a["status"] != "PRIMARY" else ("VENDOR CLOSE STALE" if stale else "PRIMARY")
        gated = in_window and a["tax"] == "before" and status == "PRIMARY"
        out.append(dict(fund=fund, as_of=a["as_of"], period=a["period"], tax=a["tax"], published_pct=pub,
                        rebuilt_pct=round(got, 4), error_pp=round(got - pub, 4), tolerance_pp=round(tol, 4),
                        undatable_bound=round(u, 6), cent_rounding=round(cents, 6), status=status,
                        in_window=bool(in_window), gated=bool(gated),
                        passed=(abs(got - pub) <= tol) if gated else None, accession=a["accession"]))
    return out


def errata_checks(anchor_rows):
    """Each FILING INCONSISTENT figure must have its after-tax-on-distributions twin reproduced (the erratum's own
    claim: no distribution that year, so before tax = after tax = the rebuilt return)."""
    out = []
    for a in anchor_rows:
        if a["status"] == "FILING INCONSISTENT":
            twin = [x for x in anchor_rows if (x["fund"], x["as_of"], x["period"], x["tax"])
                    == (a["fund"], a["as_of"], a["period"], "after_distributions")]
            ok = bool(twin) and abs(twin[0]["error_pp"]) <= twin[0]["tolerance_pp"]
            out.append(dict(fund=a["fund"], as_of=a["as_of"], period=a["period"], published_pct=a["published_pct"],
                            rebuilt_pct=a["rebuilt_pct"], twin_after_tax_pct=twin[0]["published_pct"] if twin else None,
                            twin_reproduced=ok))
    return out


# ---------------------------------------------------------------- cost fits

def fee_series(fund, index):
    """The filed net expense ratio (annual decimal) on each row: an annual report's ratio over its fiscal year, a
    standalone half-year's over its half; carried back before the first report and forward after the last."""
    rows = highlights_of(fund)
    ann = [r for r in rows if r["report_type"] == "annual" and r["expense_ratio_net_pct"]]
    half = [r for r in rows if r["report_type"] == "semiannual" and r["expense_ratio_net_pct"]
            and not any(a["period_start"] <= r["period_start"] <= a["period_end"] for a in ann)]
    fee = pd.Series(np.nan, index=index)
    for r in sorted(ann + half, key=lambda r: r["period_start"]):
        m = (index >= pd.Timestamp(r["period_start"])) & (index <= pd.Timestamp(r["period_end"]))
        fee[m] = float(r["expense_ratio_net_pct"]) / 100.0
    if fee.isna().all():
        raise ValueError(f"{fund}: no filed expense ratio covers the window")
    return fee.ffill().bfill()


def fit_window(fund, first_day, last_day):
    """(u start row, end row) of a fit: from the close before the regime's first day (a reset) to its last day."""
    end = min(pd.Timestamp(last_day) if last_day else pd.Timestamp(FIT_END), pd.Timestamp(FIT_END))
    return pd.Timestamp(first_day), end


SEASONED_LABEL = ("sensitivity: from the end of the first full fiscal year (chosen AFTER the data showed the launch "
                  "year does not track a 2x monthly fund: RMQHX lost 0.53% in Jan 2015 while the index fell 2.03%)")


def after_launch_year(fund):
    """The day after the fund's first FULL fiscal year (the first annual report that starts after inception)."""
    first = str(loader.close(SYMBOL[fund]).index[0].date())
    ann = sorted([r for r in highlights_of(fund) if r["report_type"] == "annual" and r["period_start"] > first],
                 key=lambda r: r["period_start"])
    return (pd.Timestamp(ann[0]["period_end"]) + pd.Timedelta(days=1)).date().isoformat()


def first_reset(index_rows, fund_rows, first_day):
    """The close a fit starts from: the last close before the regime's first day (the reset that starts it), or the
    fund's own first close when the regime starts at inception (no close before it; the first NAV is the first reset)."""
    s = pd.Timestamp(first_day)
    before = index_rows[(index_rows < s)]
    if len(before) and before[-1] in fund_rows:
        return before[-1]
    first = fund_rows[fund_rows >= s][0]
    if fund_rows[0] != first:
        raise ValueError(f"no close on {before[-1].date()} although the fund has earlier rows")
    return first


def model_nav(u, rate, fee, L, reset, spread):
    if reset == "daily":
        return kernel.daily_reset_series(u, rate, L=L, spread_per_nav=spread, fee=fee)
    return kernel.periodic_reset_series(u, rate, reset="monthly", L=L, spread_per_nav=spread, fee=fee, early_drop=None)


def yearly_log_gaps(a, b, bad_days):
    """{year: log growth of a less log growth of b} for each full calendar year of b's dates. A year ends on its last
    CLEAN close: not in `bad_days` (stale closes and both days of a vendor glitch pair), so a bad year-end close
    cannot move growth from one year into the next (seen: RYVYX 2012-12-31, +4.2 / -3.7 points). For a fit, a = the
    zero-spread model and b = the fund: a spread per NAV takes about that much log growth a year off the model, so
    each year gives one estimate of the fitted spread."""
    clean = b.index[~b.index.isin(bad_days)]
    ends = {}
    for y in sorted(set(b.index.year)):
        rows = clean[clean.year == y]
        if len(rows) and rows[-1] >= pd.Timestamp(f"{y}-12-20"):
            ends[y] = rows[-1]
    out = {}
    for y in sorted(ends):
        if y - 1 in ends:                                       # full calendar years only
            s, e = ends[y - 1], ends[y]
            out[y] = float(np.log(a.loc[e] / a.loc[s]) - np.log(b.loc[e] / b.loc[s]))
    return out


def t_interval(values):
    """(mean, median, [lo, hi], k): the mean of k yearly values with a t(k-1) x SE interval (None when k < 2)."""
    v = np.array(list(values), dtype=float)
    k = len(v)
    if k < 2:
        return (float(v.mean()) if k else None), (float(np.median(v)) if k else None), None, k
    half = t975(k - 1) * float(v.std(ddof=1) / np.sqrt(k))
    return float(v.mean()), float(np.median(v)), [float(v.mean() - half), float(v.mean() + half)], k


def glitch_days(dd):
    """Both days of each vendor glitch pair in a daily log-difference series (REVERSAL_MOVE), and the pair count.
    The next day must undo the move to within 25%; that alone implies the opposite sign (same signs give
    |a + b| >= |a|), so no separate sign test is needed."""
    nxt = dd.shift(-1)
    pair = (dd.abs() > REVERSAL_MOVE) & ((dd + nxt).abs() < 0.25 * dd.abs())
    both = pair | pair.shift(1, fill_value=False)
    return both[both].index, int(pair.sum()), both


def stale_days(nav, idx_ret, rows):
    """Rows whose vendor close repeats the day before while the index moved more than STALE_MOVE."""
    n = nav.reindex(rows)
    return rows[((n.diff() == 0) & (idx_ret.reindex(rows).abs() > STALE_MOVE)).to_numpy()]


def fit_regime(fund, regime, b, u_tr, rate_all, label="primary"):
    first_day, last_day, L, reset, index = regime
    s, e = fit_window(fund, first_day, last_day)
    if e <= s:
        return None
    start_row = first_reset(u_tr[index].index, b["tr"].index, s)
    u = u_tr[index].loc[start_row:e]
    e = u.index[-1]                                            # the last trading day, for the table
    real = b["tr"].loc[start_row:e]                            # the fund's own dates: compare() uses the shared ones
    missing = [str(d.date()) for d in u.index.difference(real.index)]
    extra = [str(d.date()) for d in real.index.difference(u.index)]
    real = real.loc[real.index.intersection(u.index)]         # a fund row on a day the index lacks carries no move
    rate = rate_all.reindex(u.index)
    fee = fee_series(fund, u.index)
    fit = validate.fit_spread(lambda x: model_nav(u, rate, fee, L, reset, x), real, *SPREAD_FIT_RANGE)
    best = model_nav(u, rate, fee, L, reset, fit["spread_per_nav"])
    cmp_ = validate.compare(best, real)
    ix = best.index.intersection(real.index)
    dd = (np.log(best.loc[ix]).diff() - np.log(real.loc[ix]).diff()).dropna()
    g_days, n_pairs, glitch = glitch_days(dd)
    bad_days = g_days.union(stale_days(b["nav"], u.pct_change(), real.index))
    zero = model_nav(u, rate, fee, L, reset, 0.0)
    yearly = yearly_log_gaps(zero, real, bad_days)
    y_mean, y_median, y_interval, k = t_interval(yearly.values())
    m_month = best.resample("ME").last()
    r_month = real.resample("ME").last()
    te_month = float((np.log(m_month).diff() - np.log(r_month).diff()).dropna().std() * np.sqrt(12))
    return dict(fund=fund, label=label, first_day=str(pd.Timestamp(first_day).date()), last_day=str(e.date()), L=L,
                reset=reset, index=index, bad_days=len(bad_days),
                years=round(cmp_["years"], 4), cagr_fund=cmp_["cagr_real"], cagr_model_at_fit=cmp_["cagr_model"],
                fee_mean=float(fee.iloc[1:].mean()), spread_per_nav=fit["spread_per_nav"],
                spread_per_turn=fit["spread_per_nav"] / L, rate_mean=float(rate.iloc[1:].mean()),
                yearly_years=k, yearly_mean=y_mean, yearly_median=y_median, interval=y_interval,
                tracking_error_daily=cmp_["tracking_error_ann"], tracking_error_monthly=te_month,
                vendor_reversal_pairs=n_pairs,
                tracking_error_daily_without_reversals=float(dd[~glitch].std() * np.sqrt(validate.TRADING_DAYS)),
                daily_corr=cmp_["daily_corr"], max_dd_fund=cmp_["max_dd_real"], max_dd_model=cmp_["max_dd_model"],
                fund_rows_missing=missing, fund_rows_not_in_index=extra, yearly={str(y): x for y, x in yearly.items()},
                coverage=coverage_of(yearly.values(), f"fit {fund} {first_day} {label}") if y_interval else None)


# ---------------------------------------------------------------- real vs real

def real_vs_real(cal, daily, built, u_tr, rate_all, from_day=None, label="primary"):
    """The realized gap between a real calendar fund and a real daily fund on the same index over the same dates,
    split into the fee difference and the rest, next to the model's design gap (both kernels at equal costs)."""
    rc, rd = regimes_of(cal), regimes_of(daily)
    pieces = []
    for first_day, last_day, L, reset, index in rc:
        if reset != "monthly":
            continue
        d_reg = [x for x in rd if x[2] == L and x[3] == "daily"]
        if not d_reg:
            continue                                            # no daily fund at this L (the 1.75x regime): skipped
        s = max(pd.Timestamp(first_day), pd.Timestamp(d_reg[0][0]), pd.Timestamp(CHECK_FROM),
                pd.Timestamp(from_day or CHECK_FROM))
        e = min(pd.Timestamp(last_day) if last_day else pd.Timestamp(FIT_END), pd.Timestamp(FIT_END))
        start_row = max(first_reset(u_tr[index].index, built[cal]["tr"].index, s),
                        first_reset(u_tr[index].index, built[daily]["tr"].index, s))
        u = u_tr[index].loc[start_row:e]
        shared = u.index.intersection(built[cal]["tr"].index).intersection(built[daily]["tr"].index)
        if shared[0] != start_row or shared[-1] != u.index[-1]:
            raise ValueError(f"{cal} / {daily}: both funds need a NAV on {start_row.date()} and {u.index[-1].date()}")
        a, d = built[cal]["tr"].loc[shared], built[daily]["tr"].loc[shared]
        c_a, c_d = validate.cagr(a / a.iloc[0]), validate.cagr(d / d.iloc[0])
        fa, fd = fee_series(cal, u.index).iloc[1:].mean(), fee_series(daily, u.index).iloc[1:].mean()
        rate = rate_all.reindex(u.index)
        m_cal = model_nav(u, rate, 0.0, L, "monthly", 0.0)
        m_day = model_nav(u, rate, 0.0, L, "daily", 0.0)
        gap = c_a - c_d
        model_gap = validate.cagr(m_cal) - validate.cagr(m_day)
        # yearly log gaps (real and model on the same clean year ends) for the intervals
        dd = (np.log(a).diff() - np.log(d).diff()).dropna()
        g_days, n_pairs, _ = glitch_days(dd)
        idx_ret = u.pct_change()
        bad = g_days.union(stale_days(built[cal]["nav"], idx_ret, shared)).union(stale_days(built[daily]["nav"], idx_ret, shared))
        real_y = yearly_log_gaps(a, d, bad)
        model_y = yearly_log_gaps(m_cal.loc[shared], m_day.loc[shared], bad)
        rest_y = {y: real_y[y] + float(fa - fd) - model_y[y] for y in real_y}
        g_mean, g_median, g_iv, k = t_interval(real_y.values())
        r_mean, r_median, r_iv, _ = t_interval(rest_y.values())
        pieces.append(dict(label=label, calendar_fund=cal, daily_fund=daily, index=index, L=L, start=str(start_row.date()),
                           end=str(u.index[-1].date()), years=round((u.index[-1] - start_row).days / 365.25, 4),
                           cagr_calendar=c_a, cagr_daily=c_d, gap=gap, fee_calendar=float(fa), fee_daily=float(fd),
                           fee_difference=float(fa - fd), gap_fee_adjusted=float(gap + (fa - fd)), model_gap=model_gap,
                           residual_vs_model=float(gap + (fa - fd) - model_gap), glitch_pairs=n_pairs, bad_days=len(bad),
                           log_gap=float(np.log1p(c_a) - np.log1p(c_d)),
                           yearly_years=k, yearly_gap_mean=g_mean, yearly_gap_median=g_median, yearly_gap_interval=g_iv,
                           yearly_rest_mean=r_mean, yearly_rest_median=r_median, yearly_rest_interval=r_iv,
                           yearly_gap={str(y): v for y, v in real_y.items()},
                           yearly_model_gap={str(y): v for y, v in model_y.items()},
                           coverage_gap=coverage_of(real_y.values(), f"gap {cal} {daily} {start_row.date()} {label}") if g_iv else None,
                           coverage_rest=coverage_of(rest_y.values(), f"rest {cal} {daily} {start_row.date()} {label}") if r_iv else None))
    return pieces


# ---------------------------------------------------------------- output

def build_inputs():
    m = provenance.inputs_manifest([SYMBOL[f] for f in FUNDS] + ["SP:SPX", "NASDAQ:NDX", "NASDAQ:XNDX", "SP:SPXTR"],
                                   ["DFF", "TB3MS"])
    m["reference_dir"] = "reference"
    recs = provenance.manifest([REF / n for n in REFERENCE_FILES] + [series.SHILLER_FILE, series.QQQ_INCOME_FILE])
    for rec, path in zip(recs, [REF / n for n in REFERENCE_FILES] + [series.SHILLER_FILE, series.QQQ_INCOME_FILE]):
        rec["file"] = Path(path).resolve().relative_to((ROOT / "reference").resolve()).as_posix()   # e.g. mutual_funds/regimes.csv
    m["reference_files"] = recs                                # Shiller: pre-1988 S&P 500 yields; QQQ: 1999-2006 Nasdaq-100 yields
    return m


def banner_lines(inputs):
    lines = provenance.banner_lines(inputs)
    lines += [f"Reference tables ({inputs['reference_dir']}/): {len(inputs['reference_files'])} files (mutual_funds/: SEC "
              "filings, accession number on every row; Shiller's monthly S&P 500 yields; QQQ's fiscal-year income yields)"]
    lines += provenance.banner_lines(inputs["reference_files"])[1:]
    lines += [
        "Fund series: daily NAV from the price library (mutual-fund NAVs, distributions NOT included); filed splits the "
        "vendor did not apply are applied; distributions added back on ex-dates found in the NAV (navtr), reinvested "
        "at the ex-date NAV.",
        f"Model: index total return (series.py), financing (L - 1) x DFF lagged one row (TB3MS proxy where DFF is not "
        f"yet published), ACT/{kernel.FIN_DAY_COUNT}; filed net expense ratio per fiscal year, ACT/{kernel.FEE_DAY_COUNT}; "
        "calendar funds reset at the last NYSE session of each month with no early reset (none filed); one fitted "
        "residual spread per NAV.",
        f"Checks from {CHECK_FROM} (or the fund's first filed regime); fits and real-vs-real to {FIT_END}.",
    ]
    return lines


def fmt(x, p=2, sign=True):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "-"
    return f"{x * 100:+.{p}f}" if sign else f"{x * 100:.{p}f}"


def iv_text(mean, iv):
    return f"{fmt(mean)} [{fmt(iv[0])}, {fmt(iv[1])}]" if iv else fmt(mean)


def cov_text(c):
    """'0.94 / 0.93 valid' (bootstrap world / AR(1) world, verdict) or '-'."""
    return f"{c['coverage_bootstrap']:.2f} / {c['coverage_ar1']:.2f} {c['verdict']}" if c else "-"


def markdown(res):
    L = ["# B19: real monthly-reset funds against real daily-reset funds", "",
         "Generated by `scripts/run_live_monthly.py`. Do not edit by hand.", "", "```"] + res["provenance"]["banner"] + ["```", ""]
    h = res["hard_test"]
    L += ["## 1. Total-return rebuild: the hard test", "",
          f"Result: **{h['result']}**. Report periods in the window: {h['periods_passed']} of {h['periods_gated']} within "
          f"{PERIOD_TOL_PP} points. 497K anchors in the window: {h['anchors_passed']} of {h['anchors_gated']} within "
          f"their rounding ({ANCHOR_PRINT_PP} points plus the NAV's cent at both ends) plus the undatable-payout bound. Filing errata: {h['errata']} (after-tax twin "
          f"reproduced: {h['errata_twins_reproduced']}). Largest error: {h['max_period_error_pp']:.2f} points on a report "
          f"period, {h['max_anchor_error_pp']:.2f} on an anchor; {h['anchors_widened_past_0_10']} anchors have a tolerance "
          "above 0.10 points because small payouts of uncertain date straddle their start or end.", "",
          "| fund | splits applied | ex-dates | payouts | undatable | stale closes before / in window | periods gated: passed | anchors gated: passed |",
          "|---|---|---|---|---|---|---|---|"]
    for f in FUNDS:
        x = res["funds"][f]
        L.append(f"| {f} | {sum(s[2] == 'applied' for s in x['splits'])} | {x['ex_dates']} | {x['payouts']} | "
                 f"{x['undatable_payouts']} | {x['stale_closes_before_window']} / {x['stale_closes_in_window']} | "
                 f"{x['periods_gated']}: {x['periods_passed']} | {x['anchors_gated']}: {x['anchors_passed']} |")
    L += ["", "Rows set aside by rule (not counted against the rebuild):", "",
          "| fund | period | published | rebuilt | status |", "|---|---|---|---|---|"]
    for p in res["period_checks"]:
        if p["status"] != "ok" and p["in_window"]:
            L.append(f"| {p['fund']} | {p['start']} to {p['end']} | {p['published_pct']:.2f} | {p['rebuilt_pct']:.2f} | {p['status']} |")
    for e in res["errata"]:
        L.append(f"| {e['fund']} | 497K {e['period']} to {e['as_of']} | {e['published_pct']:.2f} | {e['rebuilt_pct']:.2f} | "
                 f"FILING INCONSISTENT (after-tax twin {e['twin_after_tax_pct']:.2f}) |")
    L += ["", "## 2. Fitted residual cost per fund and regime", "",
          "The spread per NAV a year that makes the model grow exactly as the fund did, on top of (L - 1) x DFF and the "
          "filed expense ratio. A residual, not a filed term.", "",
          "| fund | regime | L | reset | years | fund CAGR % | fee % | fitted spread % of NAV | per turn % | yearly mean [95% interval] | interval coverage | median | TE % daily / without vendor glitches / monthly | glitch pairs |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["fits"]:
        iv = r["interval"]
        tag = "" if r["label"] == "primary" else " (sensitivity*)"
        L.append(f"| {r['fund']}{tag} | {r['first_day']} to {r['last_day']} | {r['L']:g} | {r['reset']} | {r['years']:.1f} | "
                 f"{fmt(r['cagr_fund'])} | {fmt(r['fee_mean'], sign=False)} | {fmt(r['spread_per_nav'])} | "
                 f"{fmt(r['spread_per_turn'])} | {fmt(r['yearly_mean'])} [{fmt(iv[0]) if iv else '-'}, {fmt(iv[1]) if iv else '-'}] | "
                 f"{cov_text(r['coverage'])} | {fmt(r['yearly_median'])} | {fmt(r['tracking_error_daily'], sign=False)} / "
                 f"{fmt(r['tracking_error_daily_without_reversals'], sign=False)} / {fmt(r['tracking_error_monthly'], sign=False)} | "
                 f"{r['vendor_reversal_pairs']} |")
    L += ["", "\\* " + SEASONED_LABEL[0].upper() + SEASONED_LABEL[1:] + ".", "",
          "## 3. Real calendar fund vs real daily fund", "",
          "CAGR columns are compound growth over the whole window; the gap columns are CAGR differences. The bracketed "
          "intervals are on the LOG scale: the mean of the k full calendar years' log-growth gaps with t(k-1) x SE (a "
          "year ends on its last clean close); compare them with the whole-window log gap next to them.", "",
          f"Interval coverage: how often a 95% interval built the same way covers the truth in {COVERAGE_RUNS} simulated "
          "samples at the row's own number of years, in two worlds (the observed yearly values resampled as independent "
          "years / normal years with the measured lag-1 autocorrelation; coverage.yearly_t_coverage). 'valid' when both "
          f"reach {COVERAGE_FLOOR}.", "",
          "| calendar | daily | index | L | window | years | CAGR calendar % | CAGR daily % | gap pp/yr | log gap pp/yr | yearly log gap mean [95%] | coverage | fee difference pp/yr | gap fee-adjusted | model gap (equal costs) | rest | yearly log rest mean [95%] | coverage |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in res["real_vs_real"]:
        tag = "" if p["label"] == "primary" else " (sensitivity*)"
        L.append(f"| {p['calendar_fund']}{tag} | {p['daily_fund']} | {p['index']} | {p['L']:g} | {p['start']} to {p['end']} | "
                 f"{p['years']:.1f} | {fmt(p['cagr_calendar'])} | {fmt(p['cagr_daily'])} | {fmt(p['gap'])} | "
                 f"{fmt(p['log_gap'])} | {iv_text(p['yearly_gap_mean'], p['yearly_gap_interval'])} | {cov_text(p['coverage_gap'])} | "
                 f"{fmt(p['fee_difference'])} | {fmt(p['gap_fee_adjusted'])} | {fmt(p['model_gap'])} | {fmt(p['residual_vs_model'])} | "
                 f"{iv_text(p['yearly_rest_mean'], p['yearly_rest_interval'])} | {cov_text(p['coverage_rest'])} |")
    return "\n".join(L) + "\n"


def main():
    OUT.mkdir(exist_ok=True)
    inputs = build_inputs()
    banner = banner_lines(inputs)
    print("=" * 100 + "\nB19: real monthly-reset funds against real daily-reset funds")
    print("\n".join(banner))
    u_tr = {"SPX": series.underlying("SPX", "total_return"), "NDX": series.underlying("NDX", "total_return")}
    built, period_rows, anchor_rows, fits, funds = {}, [], [], [], {}
    for f in FUNDS:
        b = build(f, u_tr)
        built[f] = b
        p, a = check_periods(f, b), check_anchors(f, b, u_tr)
        period_rows += p
        anchor_rows += a
        funds[f] = dict(splits=b["splits"], ex_dates=len(b["events"]), payouts=len(b["log"]),
                        undatable_payouts=sum(not x["datable"] for x in b["log"] if x["placed"]),
                        unplaced_payouts_before_window=sum(not x["placed"] and x["start"] < window_start(f) for x in b["log"]),
                        unplaced_payouts_in_window=sum(not x["placed"] and x["start"] >= window_start(f) for x in b["log"]),
                        stale_closes_before_window=b["stale_closes_before_window"],
                        stale_closes_in_window=b["stale_closes_in_window"], window_start=window_start(f),
                        periods_gated=sum(x["gated"] for x in p), periods_passed=sum(bool(x["passed"]) for x in p),
                        anchors_gated=sum(x["gated"] for x in a), anchors_passed=sum(bool(x["passed"]) for x in a),
                        payout_log=[dict(x, parts=[[d, a_] for d, a_ in x["parts"]]) for x in b["log"]])
        print(f"{f}: periods {funds[f]['periods_passed']}/{funds[f]['periods_gated']}, anchors "
              f"{funds[f]['anchors_passed']}/{funds[f]['anchors_gated']}, splits {b['splits']}")
    errata = errata_checks(anchor_rows)
    gp = [x for x in period_rows if x["gated"]]
    ga = [x for x in anchor_rows if x["gated"]]
    unplaced = sum(funds[f]["unplaced_payouts_in_window"] for f in FUNDS)
    ok = (all(x["passed"] for x in gp) and all(x["passed"] for x in ga) and all(e["twin_reproduced"] for e in errata)
          and unplaced == 0)
    hard = dict(result="PASS" if ok else "FAIL", unplaced_payouts_in_window=unplaced,
                periods_gated=len(gp), periods_passed=sum(bool(x["passed"]) for x in gp),
                anchors_gated=len(ga), anchors_passed=sum(bool(x["passed"]) for x in ga), errata=len(errata),
                errata_twins_reproduced=all(e["twin_reproduced"] for e in errata),
                max_period_error_pp=max(abs(x["error_pp"]) for x in gp), max_anchor_error_pp=max(abs(x["error_pp"]) for x in ga),
                anchors_widened_past_0_10=sum(x["tolerance_pp"] > 0.10 for x in ga),
                period_tol_pp=PERIOD_TOL_PP, anchor_print_pp=ANCHOR_PRINT_PP, datable_floor=DATABLE_FLOOR,
                vendor_nav_tol=VENDOR_NAV_TOL)
    print(f"HARD TEST: {hard['result']}  periods {hard['periods_passed']}/{hard['periods_gated']}, anchors "
          f"{hard['anchors_passed']}/{hard['anchors_gated']}, errata twins {hard['errata_twins_reproduced']}")

    rate_all = loader.reference_rate(pd.DatetimeIndex(sorted(set(u_tr["SPX"].loc[CHECK_FROM:FIT_END].index)
                                                            | set(u_tr["NDX"].loc[CHECK_FROM:FIT_END].index))))
    for f in FUNDS:
        for reg in regimes_of(f):
            if reg[1] is not None and reg[1] < window_start(f):
                continue                                        # a regime wholly before the check window
            reg = (max(reg[0], window_start(f)),) + reg[1:]
            r = fit_regime(f, reg, built[f], u_tr, rate_all)
            if r:
                fits.append(r)
            if r and pd.Timestamp(r["first_day"]) <= built[f]["nav"].index[0]:
                s2 = after_launch_year(f)                      # the fit starts at inception: launch-year sensitivity
                r2 = fit_regime(f, (s2,) + reg[1:], built[f], u_tr, rate_all, label=SEASONED_LABEL)
                if r2:
                    fits.append(r2)
                    print(f"fit {f} {r2['first_day']} to {r2['last_day']} (sensitivity): spread/NAV {r2['spread_per_nav']:+.4%}")
                print(f"fit {f} {r['first_day']} to {r['last_day']} L {r['L']:g} {r['reset']}: spread/NAV "
                      f"{r['spread_per_nav']:+.4%} (yearly mean {r['yearly_mean']:+.4%}), TE daily {r['tracking_error_daily']:.2%}")
    rvr = []
    for cal, daily in PAIRS:
        rvr += real_vs_real(cal, daily, built, u_tr, rate_all)
        first_nav = str(built[cal]["nav"].index[0].date())
        if any(r[3] == "monthly" and r[0] <= first_nav for r in regimes_of(cal)):   # a monthly regime from inception
            rvr += real_vs_real(cal, daily, built, u_tr, rate_all, from_day=after_launch_year(cal), label=SEASONED_LABEL)
    for p in rvr:
        print(f"real vs real {p['calendar_fund']} - {p['daily_fund']} {p['start']} to {p['end']}: gap {p['gap']:+.2%}/yr, "
              f"fee-adjusted {p['gap_fee_adjusted']:+.2%}, model {p['model_gap']:+.2%}")

    res = dict(meta=dict(title="B19: real monthly-reset funds against real daily-reset funds",
                         run_date=str(pd.Timestamp.today().date()), code=provenance.code_fingerprint(__file__)),
               provenance=dict(inputs=inputs, banner=banner, check_from=CHECK_FROM, fit_end=FIT_END,
                               rate=dict(source=rate_all.attrs.get("source"), last_date=rate_all.attrs.get("rate_last_date"),
                                         stale_rows=rate_all.attrs.get("stale_rows"))),
               hard_test=hard, funds=funds, period_checks=period_rows, anchor_checks=anchor_rows, errata=errata,
               fits=fits, real_vs_real=rvr)
    (OUT / "live_monthly.json").write_text(json.dumps(provenance.json_safe(res), indent=1, allow_nan=False) + "\n",
                                           encoding="utf-8")
    (OUT / "live_monthly.md").write_text(markdown(res), encoding="utf-8")
    print("wrote results/live_monthly.json and results/live_monthly.md")
    if not ok:
        bad = [x for x in gp + ga if not x["passed"]]
        print("HARD TEST FAILED on:\n  " + "\n  ".join(str(x) for x in bad[:20]))
        sys.exit(1)


if __name__ == "__main__":
    main()
