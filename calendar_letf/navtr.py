"""Total return of a real fund from its NAV and the distributions its reports print (BACKLOG B19).

Plain-English summary
  * A mutual fund's published daily NAV drops on the day a distribution goes ex: the cash leaves the fund. A price
    series with no distributions added back therefore understates the return, by a lot for leveraged funds that pay
    large capital-gain distributions. This module adds them back.
  * The fund reports print each period's distributions per share, but no ex-dates. So the date is found in the NAV
    itself: on the ex-date the NAV falls by the payout ON TOP OF the move the leverage explains. That move is known
    from the index: L x the index return for a daily-reset fund; for a calendar-reset fund the leverage drifts inside
    the period, to L (1 + R) / (1 + L R) with R the index return since the last reset (FINDINGS F17).
  * The reports print per-share amounts on the share basis of their own day; the NAV history is split-adjusted to
    today. The ratio of the two NAVs at the period start converts one to the other (a split ratio such as 1, 5 or 0.2).
  * Payouts are reinvested at the ex-date NAV, the convention of the reports' own total-return lines, so the result can
    be checked against every period return the reports print (tests and scripts/run_live_monthly.py).
"""
import numpy as np
import pandas as pd


def apply_splits(nav, splits, tol=0.15):
    """Put a NAV series on today's share basis, applying only the splits the data has not already applied.

    splits: [(date, ratio)] from the fund reports, ratio = new shares per old share (5 for a 5-for-1 split, 0.2 for a
    1-for-5 reverse split). A data vendor may adjust some splits and not others (seen in mutual-fund NAV series), so
    each split is tested: if the close on the split date over the close before is within `tol` (in log terms) of
    1 / ratio, the split is still in the data and the earlier rows are divided by the ratio; otherwise it was already
    adjusted. Returns (adjusted series, [(date, ratio, "applied" | "already adjusted")]).
    """
    nav = pd.Series(nav, dtype=float).copy()
    log = []
    for date, ratio in sorted(splits):
        d = pd.Timestamp(date)
        if d not in nav.index or nav.index.get_loc(d) == 0:
            log.append((d, ratio, "outside the data"))
            continue
        i = nav.index.get_loc(d)
        jump = nav.iloc[i] / nav.iloc[i - 1]
        if abs(np.log(jump * ratio)) < tol:
            nav.iloc[:i] = nav.iloc[:i] / ratio
            log.append((d, ratio, "applied"))
        else:
            log.append((d, ratio, "already adjusted"))
    return nav, log


def effective_leverage(index_ret, L, reset_ends):
    """Leverage a calendar-reset fund holds at the start of each day, before that day's move: L just after a reset,
    then L (1 + R) / (1 + L R) with R the index return since the last reset. reset_ends: boolean array, True on the
    rows that close a period (the leverage is back to L on the next row). Pass all True for a daily-reset fund."""
    r = np.asarray(index_ret, dtype=float)
    ends = np.asarray(reset_ends, dtype=bool)
    out = np.empty(len(r))
    R = 0.0
    for t in range(len(r)):
        out[t] = L * (1.0 + R) / (1.0 + L * R) if 1.0 + L * R > 0 else 0.0
        R = (1.0 + R) * (1.0 + r[t]) - 1.0
        if ends[t]:
            R = 0.0
    return out


def residual(nav, index_ret, L, reset_ends):
    """The part of each day's NAV return that the leverage does not explain: nav_ret - lev x index_ret. Near 0 on
    ordinary days (costs and rounding), about -payout / NAV on an ex-date."""
    nav = pd.Series(nav, dtype=float)
    nav_ret = nav.pct_change().fillna(0.0).to_numpy()
    lev = effective_leverage(index_ret, L, reset_ends)
    return pd.Series(nav_ret - lev * np.asarray(index_ret, dtype=float), index=nav.index)


def basis_factor(nav_series_at_start, nav_report_at_start):
    """Today's-basis NAV / the report's NAV on the same day: the factor that moves the report's per-share amounts onto
    the split-adjusted series (1 if no split since; 0.2 after a 5-for-1 split; 5 after a 1-for-5 reverse split)."""
    return float(nav_series_at_start) / float(nav_report_at_start)


def snap_basis(k, ratios, tol=0.15):
    """The basis factor snapped to the nearest value it can truly take: 1 / (a product of some of the fund's split
    ratios), 1 included. A raw factor read from one day's NAV is off when the vendor's close that day is stale (seen:
    RYVYX 2012-12-31 gives 0.1919 for a true 0.2, a 4% stale move). Returns (snapped, "exact" | "snapped"); raises if
    no allowed value lies within `tol` (in log terms, as apply_splits; allowed values are at least a factor 1.5 apart,
    log 0.41, so the nearest one is never ambiguous): then the report and the series disagree by more than a stale
    print."""
    allowed = {1.0}
    for r in ratios:
        allowed |= {a / float(r) for a in allowed}
    best = min(allowed, key=lambda a: abs(np.log(k / a)))
    if abs(np.log(k / best)) > tol:
        raise ValueError(f"basis factor {k:.4f} is not within {tol:.0%} of any split product {sorted(allowed)}")
    return best, ("exact" if abs(np.log(k / best)) < 1e-4 else "snapped")


COMPONENTS = ("dist_net_income", "dist_realized_gains", "dist_return_of_capital")


def _num(x):
    return float(x) if x not in ("", None) else None


def payout_windows(rows):
    """The search windows for each reported payout, from a fund's report rows (dicts with period_start, period_end,
    report_type 'annual' | 'semiannual', nav_begin, nav_end and the COMPONENTS, as in reference/monthly_funds/).

    A semiannual report covers the first half of a fiscal year; the annual report covers the whole year, so the second
    half's payout is the annual amount less the first half's. Each component (income, gains, return of capital) is its
    own payout: they can go ex on different days. A half-year with no annual report yet stands alone. Returns
    [dict(start, end, component, amount, nav_report)]: amount per share on the report's basis, nav_report the report's
    NAV at the window start (for the basis factor)."""
    ann = sorted([r for r in rows if r["report_type"] == "annual"], key=lambda r: r["period_end"])
    semi = {r["period_start"]: r for r in rows if r["report_type"] == "semiannual"}
    used, out = set(), []

    def add(start, end, comp, amount, nav_report):
        out.append(dict(start=start, end=end, component=comp, amount=amount, nav_report=nav_report))

    for a in ann:
        h1 = semi.get(a["period_start"])
        if h1 and h1["period_end"] < a["period_end"]:
            used.add(h1["period_start"])
            start2 = (pd.Timestamp(h1["period_end"]) + pd.Timedelta(days=1)).date().isoformat()
            for c in COMPONENTS:
                v1, va = _num(h1[c]) or 0.0, _num(a[c]) or 0.0
                add(h1["period_start"], h1["period_end"], c, v1, _num(h1["nav_begin"]))
                add(start2, a["period_end"], c, round(va - v1, 6), _num(h1["nav_end"]))
        else:
            for c in COMPONENTS:
                add(a["period_start"], a["period_end"], c, _num(a[c]) or 0.0, _num(a["nav_begin"]))
    for s, h in semi.items():
        if s not in used and not any(a["period_start"] <= s <= a["period_end"] for a in ann):
            for c in COMPONENTS:
                add(h["period_start"], h["period_end"], c, _num(h[c]) or 0.0, _num(h["nav_begin"]))
    return out


def rebuild(nav, resid, windows, split_ratios=(), datable_floor=0.005):
    """Total-return index of a fund from its NAV, its residual (residual()) and its payout windows (payout_windows()).

    Payouts are placed one by one, the LARGEST of a window first: when income and gains go ex on the same day, the
    gains explain most of the day's drop and the income then finds the rest on that day (seen: RMQHX 2023-12-12, gains
    3.64% plus income 0.11% of NAV in one 3.79% drop; placed smallest first, the income went to a noise day). A payout
    under `datable_floor` of NAV is placed the same way but marked undatable: ordinary-day noise reaches 0.0015 of NAV
    (99th percentile in the B19 funds), so its day is not reliable and anchor_bound() widens the check instead.
    A payout no day can explain (no day falls by half of it) is left out and logged with placed=False; a caller must
    treat one inside its check window as a failure.
    Returns (tr, events {date: amount}, log [dict(start, end, component, amount, k, k_status, parts, frac, datable,
    placed)])."""
    nav = pd.Series(nav, dtype=float)
    prev = nav.shift(1)
    work = pd.Series(resid, dtype=float).copy()
    events, log = {}, []
    for w in sorted(windows, key=lambda w: (w["start"], w["end"], -(w["amount"] or 0.0))):
        before = nav.loc[:pd.Timestamp(w["start"]) - pd.Timedelta(days=1)]
        if before.empty or not w["amount"] or w["amount"] <= 1e-9 or not w["nav_report"]:
            continue
        k, k_status = snap_basis(basis_factor(before.iloc[-1], w["nav_report"]), split_ratios)
        parts = locate_ex_dates(work, nav, w["start"], w["end"], w["amount"] * k)
        if not parts:                                      # no day falls by half the payout: logged, never hidden
            log.append(dict(start=w["start"], end=w["end"], component=w["component"], amount=w["amount"], k=k,
                            k_status=k_status, parts=[], frac=0.0, datable=False, placed=False))
            continue
        frac = 0.0
        for d, a in parts:
            events[d] = events.get(d, 0.0) + a
            work.loc[d] += a / float(prev.loc[d])                  # explained now: another payout can use the rest
            frac += a / float(prev.loc[d])
        log.append(dict(start=w["start"], end=w["end"], component=w["component"], amount=w["amount"], k=k,
                        k_status=k_status, parts=[(str(d.date()), float(a)) for d, a in parts], frac=frac,
                        datable=bool(frac >= datable_floor), placed=True))
    return total_return(nav, events), events, log


def anchor_bound(log, start, end):
    """The most the undatable payouts can move a return measured from `start` to `end`: the sum of the payout
    fractions whose search window straddles either date (the payout may lie on either side of it). A return R
    then lies within (1 + R)(1 +- bound) of the rebuilt one."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    total = 0.0
    for x in log:
        if x["datable"]:
            continue
        a, b = pd.Timestamp(x["start"]), pd.Timestamp(x["end"])
        if any(a <= B < b for B in (s, e)):
            total += x["frac"]
    return total


def report_self_consistent(row, tol_pp=0.06):
    """False when a report row with no distribution prints a total return that is not its own NAV change (to
    `tol_pp` points; NAVs print to the cent). Such a row cannot be used to check anything (seen: RMQHX 2015 half-year,
    Nova 1996-97)."""
    dist = _num(row["dist_total"]) or 0.0
    nb, ne, tr = _num(row["nav_begin"]), _num(row["nav_end"]), _num(row["total_return_pct"])
    if dist > 0 or None in (nb, ne, tr):
        return True
    return abs((ne / nb - 1.0) * 100.0 - tr) < tol_pp


def locate_ex_date(resid, nav, start, end, payout):
    """The day in [start, end] whose unexplained drop best matches the payout (payout on the series' basis): the day
    minimizing |resid_t + payout / nav_{t-1}|, among days that fall by at least half the payout. None if no day does."""
    nav = pd.Series(nav, dtype=float)
    prev = nav.shift(1)
    window = resid.loc[start:end]
    frac = payout / prev.loc[window.index]
    cand = window[(window < -0.5 * frac)]
    if cand.empty:
        return None
    return (cand + frac.loc[cand.index]).abs().idxmin()


def locate_ex_dates(resid, nav, start, end, payout, max_dates=3, split_floor=0.01):
    """[(ex_date, amount)] for one reported payout that a fund may have paid on more than one day (seen: a year's
    capital gains paid partly in September, the rest in December). Greedy: the best-matching day (locate_ex_date)
    takes only what its drop implies (-resid x nav_{t-1}), and the rest is searched again on the other days. The day
    takes the whole remaining amount instead when the rest would be under `split_floor` of NAV: a rest that small is
    noise, not a second payout (ordinary-day residuals of the B19 funds are under 0.002 of NAV at the 99th percentile,
    so 0.01 is about 7 times that). A small income payout is therefore never smeared over noise days."""
    nav = pd.Series(nav, dtype=float)
    prev = nav.shift(1)
    work = resid.copy()
    remaining, out = float(payout), []
    for _ in range(int(max_dates)):
        d = locate_ex_date(work, nav, start, end, remaining)
        if d is None:
            break
        implied = -float(work.loc[d]) * float(prev.loc[d])
        if (remaining - implied) / float(prev.loc[d]) < split_floor or len(out) == max_dates - 1:
            out.append((d, remaining))
            remaining = 0.0
            break
        out.append((d, implied))
        remaining -= implied
        work.loc[d] = 0.0                                   # explained; never picked twice
    if remaining > 0.0 and out:
        d0, a0 = out[-1]
        out[-1] = (d0, a0 + remaining)                       # a remainder the search could not place stays with the last day
    return out


def total_return(nav, events):
    """Total-return index (1.0 at the first row) with each payout reinvested at its ex-date NAV.
    events: {ex_date: payout per share on the series' basis}. TR_t = TR_{t-1} x (NAV_t + payout_t) / NAV_{t-1}."""
    nav = pd.Series(nav, dtype=float)
    pay = pd.Series(0.0, index=nav.index)
    for d, amount in events.items():
        if d not in pay.index:
            raise ValueError(f"ex-date {d} is not a row of the NAV series")
        pay.loc[d] += float(amount)
    growth = (nav + pay) / nav.shift(1)
    growth.iloc[0] = 1.0
    return growth.cumprod()


def period_return(tr, start, end):
    """Return of the total-return index from the close BEFORE `start` to the close at `end` (a report period)."""
    before = tr.loc[:pd.Timestamp(start) - pd.Timedelta(days=1)]
    if before.empty:
        raise ValueError(f"no row before the period start {start}")
    return float(tr.loc[:end].iloc[-1] / before.iloc[-1] - 1.0)
