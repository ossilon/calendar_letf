"""Validate the model against the real funds (step 2): build the funds' total-return series, compare a model NAV
with a real one, fit the one cost nobody publishes, and check what multiple of the ETF each fund really delivered.

Plain-English notes
  * The price library holds the funds' CLOSING PRICES, split-adjusted but with distributions left out. A fund that
    pays out 1.5% of its value (MQQQ, December 2025) looks 1.5% worse than it was. `fund_total_return` adds each
    payout back on its ex-date, which is the day the price drops by the payout.
  * The funds track SPY and QQQ, whose library prices also leave dividends out. `etf_total_return` puts the
    index's dividend accrual back on top of the ETF's own price path (ETF price x the published total-return /
    price index ratio) and then takes the ETF's expense ratio off. Why the fee must be taken off separately: SPY
    and QQQ pay their fees out of the dividends they collect, not out of the share price, so their PRICE tracks
    the index price almost exactly (audit S2: within 0.1%/yr) and the fee only shows up as a smaller dividend.
    Without the deduction the series is the index's total return, not the ETF's (audit S2 finding 1).
  * `compare` reports the usual fit statistics; `fit_spread` finds the spread per NAV that makes the model's growth
    rate equal the fund's over the overlap. A fitted spread is a RESIDUAL: it absorbs every cost the model left
    out, so it is reported, never promoted to a verified input.
  * `period_multiple` is the direct test of the product's promise: over each full calendar period, the fund's
    return divided by the ETF's. For a 2x fund it should be about 2 before costs.
  * R2 step 2 adds the pieces the live fit needs to follow the filings: `fee_timeline` (the expense ratio as a step
    series: a fee cap that ends on a date), `Structure` and `structural_rate` (the fund's balance sheet, swaps plus
    cash, written as the kernel's two cost inputs), `fit_cash_yield` (the one number in that balance sheet nobody
    files: what fraction of the reference rate the cash earns), `window_return` and `worst_in_period_fall`.
Nothing here is a result until a script records it with its provenance.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import periods as cal

TRADING_DAYS = 252


# ---------------------------------------------------------------- fee timeline and balance-sheet structure (R2 step 2)

def fee_timeline(index, initial, changes=None):
    """The expense ratio as a step Series on `index` (what kernel.run accepts as `fee=`).

    initial:  annual fee (decimal) in force from the first row.
    changes:  {date: fee}: from each date on, the new fee. Row t carries the fee for the step from row t-1 to row t,
              so rows dated AFTER a change date take the new fee; the row dated on the change date still accrues
              the old one (its step ended that day). A change dated beyond the index has no effect; a change
              before the first row replaces `initial`.
    attrs["steps"] lists [first row at each fee, fee] for banners.
    """
    idx = pd.DatetimeIndex(index)
    out = pd.Series(float(initial), index=idx, name="fee")
    for date, fee in sorted((changes or {}).items()):
        out.loc[idx > pd.Timestamp(date)] = float(fee)
    if (out < 0).any() or (out > 0.5).any():
        raise ValueError("fees must be annual decimals between 0 and 0.5 (0.013 = 1.30%)")
    change_rows = np.flatnonzero(np.r_[True, out.values[1:] != out.values[:-1]])
    out.attrs["steps"] = [[str(idx[i].date()), float(out.iloc[i])] for i in change_rows]
    return out


@dataclass(frozen=True)
class Structure:
    """A calendar fund's balance sheet between resets, as fractions of NAV (ASSUMPTIONS section 6).

    swap_turns   s: swap notional / NAV. The fund pays (reference rate + spread) on all of it.
    cash_nav     k: cash / NAV. The fund earns cash_yield x reference rate on it (what is not in the ETF itself).
    cash_yield   c: the fraction of the reference rate the cash earns (1.0 = the full rate; fitted, never filed).
    Net financing per year, per NAV: (s - k c) x rate + s x spread. The kernel charges (L-1) x rate + spread_per_nav
    with L-1 = 1, so rate_turns = s - k c multiplies the rate series and spread_turns = s multiplies the spread.
    A direct ETF holding d = 2 - s costs nothing (it earns its own total return, which the swaps also receive).
    """
    swap_turns: float
    cash_nav: float
    cash_yield: float
    label: str = ""

    def __post_init__(self):
        for name in ("swap_turns", "cash_nav"):
            v = getattr(self, name)
            if not (np.isfinite(v) and 0.0 <= v <= 3.0):
                raise ValueError(f"Structure.{name} must be a fraction of NAV between 0 and 3, got {v}")
        if not (np.isfinite(self.cash_yield) and -2.0 <= self.cash_yield <= 3.0):
            raise ValueError(f"Structure.cash_yield must be a finite multiple of the rate, got {self.cash_yield}")

    @property
    def rate_turns(self):
        return self.swap_turns - self.cash_nav * self.cash_yield

    @property
    def spread_turns(self):
        return self.swap_turns

    def describe(self, spread):
        return (f"{self.label + ': ' if self.label else ''}swaps {self.swap_turns:g} x NAV at rate + {spread:.2%}, cash "
                f"{self.cash_nav:g} x NAV earning {self.cash_yield:.3f} x rate -> rate turns {self.rate_turns:.3f}, "
                f"spread {self.spread_turns * spread:.2%} of NAV a year")


def structural_rate(rate, spread, structures):
    """The whole financing cost of a balance-sheet timeline folded into ONE rate series for the kernel.

    rate:        the lagged reference rate on the run's index (loader.rate_known_before).
    spread:      swap spread per turn over that rate (decimal), the same in every window.
    structures:  list of (last_date, Structure): rows dated on or before last_date use that Structure; the last
                 entry's date may be None (to the end). Dates must be ascending and must cover every row.
    Row t gets rate[t] x rate_turns + spread_turns x spread. Run the kernel with spread_per_nav=0.0 so nothing is
    charged twice: (L-1) x this series x accrual_fin is then exactly (s - k c) x rate + s x spread on ACT/360,
    which is what a constant spread_per_nav would also have been charged on. The kernel's spread input is a scalar;
    this is how a spread that changes with the swap turns on a date is expressed without touching the kernel.
    attrs["windows"] records each window's dates and its Structure.describe(spread).
    """
    if not isinstance(rate, pd.Series) or not isinstance(rate.index, pd.DatetimeIndex):
        raise ValueError("rate must be a Series on a DatetimeIndex (the lagged reference rate)")
    if not (0.0 <= float(spread) < 0.05):
        raise ValueError(f"spread must be a decimal per turn (0.0092 = 92 bp), got {spread}")
    out = pd.Series(np.nan, index=rate.index, name="structural_rate")
    windows, prev = [], None
    for i, (last, st) in enumerate(structures):
        if not isinstance(st, Structure):
            raise ValueError("each entry must be (last_date, Structure)")
        if last is None and i != len(structures) - 1:
            raise ValueError("only the last window may be open-ended (last_date None)")
        hi = rate.index[-1] if last is None else pd.Timestamp(last)
        if prev is not None and hi <= prev:
            raise ValueError("window end dates must be ascending")
        mask = (rate.index <= hi) & (out.isna().values)
        if mask.any():
            out.loc[mask] = rate.loc[mask] * st.rate_turns + st.spread_turns * float(spread)
            windows.append(dict(first=str(rate.index[mask][0].date()), last=str(rate.index[mask][-1].date()),
                                swap_turns=st.swap_turns, cash_nav=st.cash_nav, cash_yield=st.cash_yield,
                                rate_turns=st.rate_turns, spread_per_nav=st.spread_turns * float(spread),
                                text=st.describe(spread)))
        prev = hi
    if out.isna().any():
        raise ValueError(f"no Structure covers {out[out.isna()].index[0].date()} (extend the last window with None)")
    out.attrs["windows"] = windows
    out.attrs["spread"] = float(spread)
    return out


def fit_cash_yield(build, real, lo=-1.0, hi=3.0, tol=1e-7, max_iter=80):
    """The cash yield c (fraction of the reference rate the fund's cash earns) at which build(c) grows at `real`'s
    rate over their overlap. A HIGHER c means a CHEAPER fund, the opposite direction to fit_root's x, so the search
    runs on -c. Returns dict(cash_yield=c, cagr_gap_at_fit, iterations). c is a fitted residual like the others:
    it absorbs every cost the structure leaves out, so it is reported with its window, never promoted to a fact.
    """
    r = fit_root(lambda x: build(-x), real, -hi, -lo, tol, max_iter, name="neg_cash_yield")
    return {"cash_yield": -r["neg_cash_yield"], "cagr_gap_at_fit": r["cagr_gap_at_fit"], "iterations": r["iterations"]}


def fixed_turns_structure(swap_turns, rate_turns, label=""):
    """A Structure that charges `swap_turns` x spread and `rate_turns` x rate, whatever the balance sheet behind it.
    It holds the cash at 1.0 x NAV and sets the cash yield to swap_turns - rate_turns, so Structure.rate_turns equals
    the value asked for. Used to step from one cost structure to another one input at a time (gap_decomposition)."""
    return Structure(swap_turns, 1.0, float(swap_turns) - float(rate_turns), label)


def gap_decomposition(real, steps):
    """Split the CAGR gap between a first model and the fitted model into one piece per changed input.

    real:   the fund's total-return level (Series).
    steps:  ordered list of (label, model NAV Series). steps[0] is the starting model (for example the v1 filed
            structure); each later entry changes ONE input of the entry before it (fee, then spread turns, then rate
            turns); the last entry is the fitted model.
    The gap of a model is its CAGR minus the fund's CAGR over their overlap (compare). A costlier model has a lower
    CAGR, so each step closes gap[i-1] - gap[i] >= 0 of the gap. The pieces add up to start gap - end gap exactly
    (the sum telescopes), and to the start gap when the last model is the fitted one (its gap is zero up to the
    fit tolerance). Returns dict(labels, gaps (one per model), closed (one per step after the first), start_gap,
    end_gap, total_closed)."""
    if len(steps) < 2:
        raise ValueError("gap_decomposition needs a starting model and at least one step")
    gaps = [compare(nav, real)["cagr_gap"] for _, nav in steps]
    closed = [gaps[i - 1] - gaps[i] for i in range(1, len(gaps))]
    return dict(labels=[lab for lab, _ in steps], gaps=gaps, closed=closed, start_gap=gaps[0], end_gap=gaps[-1],
                total_closed=gaps[0] - gaps[-1])


def window_return(level, start, end):
    """level[end] / level[start] - 1, with both dates required to be rows of `level` (an anchor is a close-to-close
    figure, so a missing row is an error, never a nearest match)."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    for d in (s, e):
        if d not in level.index:
            raise ValueError(f"{d.date()} is not a row of the series (needed for a window return)")
    if e <= s:
        raise ValueError("end must be after start")
    return float(level.loc[e] / level.loc[s] - 1.0)


def worst_in_period_fall(close, reset, low=None):
    """The deepest fall of a trigger series inside any one calendar period: min over periods of (level / level at the
    period's last reset close - 1), on the close and, if given, on the day's low. A -35% here would have fired the
    fund's early reset. Returns dict(close=..., close_date=..., low=..., low_date=...)."""
    ix = close.index
    ends = np.flatnonzero(cal.period_end_flags(ix, reset))
    starts = np.r_[0, ends]                                   # row 0 counts as a reset (kernel convention)
    c = close.to_numpy(float)
    lo_arr = c if low is None else np.minimum(low.reindex(ix).to_numpy(float), c)
    worst_c, worst_l, dc, dl = 0.0, 0.0, None, None
    for a, b in zip(starts, np.r_[starts[1:], len(ix) - 1]):   # rows a+1 .. b belong to the period that reset at a
        if b <= a:
            continue
        seg_c = c[a + 1:b + 1] / c[a] - 1.0
        seg_l = lo_arr[a + 1:b + 1] / c[a] - 1.0
        if seg_c.min() < worst_c:
            worst_c, dc = float(seg_c.min()), str(ix[a + 1 + int(seg_c.argmin())].date())
        if seg_l.min() < worst_l:
            worst_l, dl = float(seg_l.min()), str(ix[a + 1 + int(seg_l.argmin())].date())
    return dict(close=worst_c, close_date=dc, low=(worst_l if low is not None else None),
                low_date=(dl if low is not None else None))


def fund_total_return(price, distributions=None):
    """Fund level with distributions reinvested on their ex-dates, = 1.0 on the first row.

    price:          Series of split-adjusted closes (DatetimeIndex).
    distributions:  Series of amount per share (same adjustment as the price) indexed by EX-DATE, or None.
    r_t = (P_t + D_t) / P_{t-1} - 1, so a payout D on its ex-date is treated as received at that day's close.
    Every ex-date must be a trading day in `price`; anything else raises (a payout cannot be silently dropped).
    """
    p = price.astype(float)
    if not p.index.is_monotonic_increasing or not p.index.is_unique:
        raise ValueError("price index must be strictly increasing")
    if (p.values <= 0).any() or not np.isfinite(p.values).all():
        raise ValueError("prices must be finite and positive")
    d = pd.Series(0.0, index=p.index)
    if distributions is not None and len(distributions):
        dist = distributions.astype(float)
        missing = dist.index.difference(p.index)
        if len(missing):
            raise ValueError(f"distribution ex-dates not in the price series: {[str(x.date()) for x in missing]}")
        if (dist.values < 0).any():
            raise ValueError("distributions must be >= 0")
        d.loc[dist.index] = dist.values
    r = (p + d) / p.shift(1) - 1.0
    r.iloc[0] = 0.0
    out = (1.0 + r).cumprod().rename(f"{price.name}_TR" if price.name else "fund_TR")
    out.attrs.update(basis="fund price + distributions reinvested on ex-date",
                     distributions={str(k.date()): float(v) for k, v in d[d > 0].items()},
                     distribution_total_pct_of_price=float((d / p.shift(1)).fillna(0).sum() * 100))
    return out


def etf_total_return(etf_price, index_price, index_tr, etf_fee=0.0):
    """ETF level with the INDEX's dividends added to the ETF's own price path, less the ETF's fee; 1.0 on row 0.

    level_t = etf_price_t x (index_tr_t / index_price_t) / (index_tr_0 / index_price_0) x prod(1 - fee x days/365)
    on the ETF's dates. `etf_fee` is the ETF's annual expense ratio (decimal); it is deducted by calendar-day
    accrual because the ETF pays it out of its dividend income, so the price alone never shows it (module notes).
    Where the published total-return index lacks a day the ETF has (holiday quirks, or trailing rows after the
    last TR export), the ratio is carried forward, so that day's dividend accrual is zero. Those days are listed
    in attrs["ratio_carried_days"] and must stay few.
    """
    e = etf_price.astype(float)
    if not (0.0 <= float(etf_fee) < 0.05):
        raise ValueError(f"etf_fee must be a decimal annual expense ratio (0.0009 = 0.09%), got {etf_fee}")
    ratio = (index_tr.astype(float) / index_price.astype(float)).dropna()
    r = ratio.reindex(ratio.index.union(e.index)).ffill().reindex(e.index)
    if r.isna().any():
        raise ValueError(f"no total-return / price ratio on or before {r[r.isna()].index[0].date()}")
    carried = [str(d.date()) for d in e.index.difference(ratio.index)]
    days = pd.Series(e.index, index=e.index).diff().dt.days.fillna(0.0) / 365.0
    fee_factor = (1.0 - float(etf_fee) * days).cumprod()
    out = (e * r / r.iloc[0] * fee_factor).rename(f"{etf_price.name}_TR" if etf_price.name else "etf_TR")
    out = out / out.iloc[0]
    out.attrs.update(basis="ETF price x (index total return / index price) less the ETF fee by calendar-day accrual",
                     etf_fee=float(etf_fee), ratio_carried_days=carried,
                     implied_dividend_yield_pct=float(np.log(r.iloc[-1] / r.iloc[0])
                                                      / ((e.index[-1] - e.index[0]).days / 365.25) * 100))
    return out


def cagr(level):
    years = (level.index[-1] - level.index[0]).days / 365.25
    if years <= 0 or level.iloc[0] <= 0:
        return float("nan")
    return float((level.iloc[-1] / level.iloc[0]) ** (1 / years) - 1) if level.iloc[-1] > 0 else -1.0


def max_drawdown(level):
    return float((level / level.cummax() - 1).min())


def compare(model, real, min_overlap=60):
    """Fit statistics of a model NAV against a real one over their common dates (both rebased to 1.0 there).

    Returns a dict: overlap, cagr_model, cagr_real, cagr_gap (model - real, in decimal per year),
    cumulative_tracking_difference (end-of-window wealth difference), tracking_error_ann (std of the difference
    in daily log returns x sqrt(252)), daily_corr, max_dd_model, max_dd_real, worst_day_diff.
    Real-fund PRICES (not NAVs) carry bid-ask noise, which inflates tracking error for thin funds; say so in tables.
    """
    ix = model.index.intersection(real.index)
    if len(ix) < min_overlap:
        raise ValueError(f"only {len(ix)} overlapping dates; need at least {min_overlap}")
    a = model.loc[ix] / model.loc[ix].iloc[0]
    b = real.loc[ix] / real.loc[ix].iloc[0]
    la, lb = np.log(a).diff().dropna(), np.log(b).diff().dropna()
    diff = la - lb
    return dict(start=str(ix[0].date()), end=str(ix[-1].date()), overlap_rows=int(len(ix)),
                years=float((ix[-1] - ix[0]).days / 365.25),
                cagr_model=cagr(a), cagr_real=cagr(b), cagr_gap=cagr(a) - cagr(b),
                cumulative_tracking_difference=float(a.iloc[-1] - b.iloc[-1]),
                tracking_error_ann=float(diff.std() * np.sqrt(TRADING_DAYS)),
                daily_corr=float(la.corr(lb)),
                max_dd_model=max_drawdown(a), max_dd_real=max_drawdown(b),
                worst_day_diff=float(diff.min()), best_day_diff=float(diff.max()))


def fit_root(build, real, lo, hi, tol=1e-7, max_iter=80, name="x"):
    """The value x in [lo, hi] at which build(x) grows at the same rate as `real` over their overlap.

    build:  a function x -> model NAV Series (any superset of real's dates), where a larger x means a COSTLIER
            fund (the gap model CAGR - real CAGR must fall as x rises). Bisection then finds the zero.
    Returns dict(<name>=x, cagr_gap_at_fit, iterations). Raises if the gap has the same sign at both ends of
    [lo, hi] (then no value in that range explains the fund).
    """
    def gap(x):
        return compare(build(x), real)["cagr_gap"]
    g_lo, g_hi = gap(lo), gap(hi)
    if not (g_lo > 0 > g_hi):
        raise ValueError(f"no root in [{lo}, {hi}]: gap {g_lo:+.4%} at {lo}, {g_hi:+.4%} at {hi}")
    for i in range(max_iter):
        mid = 0.5 * (lo + hi)
        g = gap(mid)
        if abs(g) < tol or (hi - lo) < 1e-9:
            return {name: float(mid), "cagr_gap_at_fit": float(g), "iterations": i + 1}
        if g > 0:
            lo = mid
        else:
            hi = mid
    return {name: float(mid), "cagr_gap_at_fit": float(g), "iterations": max_iter}


def fit_spread(build, real, lo=-0.05, hi=0.15, tol=1e-7, max_iter=80):
    """The spread-per-NAV at which build(spread_per_nav) grows at the same rate as `real` (see fit_root).

    A fitted spread is a RESIDUAL: it absorbs every cost the model left out (collateral yield, day count, fee
    accrual, bid-ask drift), so it is reported next to the filed number, never promoted to a verified input.
    """
    return fit_root(build, real, lo, hi, tol, max_iter, name="spread_per_nav")


def fit_rate_turns(build, real, lo=0.5, hi=3.0, tol=1e-7, max_iter=80):
    """The number of NAV turns paying the reference rate at which build(turns) matches `real`'s growth.

    The other way to encode the residual (audit S2 finding 2): keep the filed spread fixed and let the rate be
    charged on more than the (L-1) = 1 turn the kernel assumes. A fixed spread and a rate-proportional charge
    agree in a single rate regime but differ when rates move, so both encodings must be carried into history.
    """
    return fit_root(build, real, lo, hi, tol, max_iter, name="rate_turns")


DEFAULT_MIN_ABS_ETF_RETURN = {"weekly": 0.005, "monthly": 0.01, "quarterly": 0.03}


def period_regression(pm):
    """Fit fund_return = intercept + slope x etf_return over the full periods in `pm` (from period_multiple).

    This is the right test of "2x per period": the slope is the delivered multiple and the intercept is the
    cost per period, which a plain ratio muddles (a constant cost divided by a small ETF move prints a wild
    multiple). Returns dict(n, slope, intercept, r2, intercept_pct_per_period).
    """
    x, y = pm["etf_return"].to_numpy(float), pm["fund_return"].to_numpy(float)
    if len(x) < 3:
        return dict(n=int(len(x)), slope=float("nan"), intercept=float("nan"), r2=float("nan"),
                    intercept_pct_per_period=float("nan"))
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (intercept + slope * x)
    r2 = 1.0 - float(np.sum(resid ** 2) / np.sum((y - y.mean()) ** 2))
    return dict(n=int(len(x)), slope=float(slope), intercept=float(intercept), r2=r2,
                intercept_pct_per_period=float(intercept * 100))


def period_multiple(fund_level, etf_level, reset, min_abs_etf_return=None):
    """Per full calendar period: the fund's return, the ETF's, their ratio (the realized multiple) and the
    difference fund - 2 x ETF (in return units). First and last periods are dropped unless complete.

    A period runs from one period-end close to the next (`periods.period_ids`). The ratio is NaN when the ETF
    moved less than `min_abs_etf_return` (default by reset: 0.5% weekly, 1% monthly, 3% quarterly), because a
    near-constant cost divided by a small move prints a meaningless multiple. Prefer `period_regression` for the
    headline; the ratio column is for reading individual periods.
    """
    if min_abs_etf_return is None:
        min_abs_etf_return = DEFAULT_MIN_ABS_ETF_RETURN[reset]
    ix = fund_level.index.intersection(etf_level.index)
    f, e = fund_level.loc[ix], etf_level.loc[ix]
    ends = np.flatnonzero(cal.period_end_flags(ix, reset))         # NYSE period ends (raises if one is missing)
    rows = []
    for a, b in zip(ends[:-1], ends[1:]):
        rf, re_ = f.iloc[b] / f.iloc[a] - 1.0, e.iloc[b] / e.iloc[a] - 1.0
        rows.append(dict(period_start=ix[a].date(), period_end=ix[b].date(), fund_return=float(rf),
                         etf_return=float(re_),
                         multiple=(float(rf / re_) if abs(re_) >= min_abs_etf_return else float("nan")),
                         fund_minus_2x_etf=float(rf - 2.0 * re_)))
    return pd.DataFrame(rows)


def calendar_year_return(level, year):
    """Return over calendar `year`: last close of the previous year to last close of `year`. NaN if not covered."""
    prev = level.loc[:f"{year - 1}-12-31"]
    cur = level.loc[:f"{year}-12-31"]
    if prev.empty or cur.empty or cur.index[-1].year != year:
        return float("nan")
    return float(cur.iloc[-1] / prev.iloc[-1] - 1.0)


_PAY_LEG = None


def _pay_leg_bp(pay, where):
    """The spread in bp from a pay leg 'OBFR01 + <n>bps (Spread)'. Refuses a leg on any other reference rate (the model
    charges OBFR, so a SOFR or fed-funds leg must not be read as a spread over OBFR) and a leg that states no spread."""
    import re
    global _PAY_LEG
    if _PAY_LEG is None:
        _PAY_LEG = re.compile(r"^\s*OBFR01\s*\+\s*(\d+(?:\.\d+)?)\s*bps\b")
    m = _PAY_LEG.search(str(pay or ""))
    if m is None:
        raise ValueError(f"{where}: cannot read a spread over OBFR01 from the pay leg {pay!r}")
    return float(m.group(1))


def filed_spread_range(nport):
    """(smallest, largest) swap spread over every swap of every snapshot of every fund in the N-PORT extract, as annual
    decimals. A counterparty mix lies between them IF every swap in it carries one of the filed terms; for a period the
    extract does not cover, that premise needs its own source (for window 1: the N-CSR to 2025-03-31, ASSUMPTIONS section
    6). Reads the same 'OBFR01 + <n>bps' pay legs as filed_spread and refuses one it cannot read."""
    vals = []
    for fund, rec in nport.items():
        if fund.startswith("_"):
            continue
        for snap in rec.get("snapshots", []):
            for sw in snap.get("swaps", []):
                vals.append(_pay_leg_bp(sw.get("pay"), f"filed_spread_range: {fund} {snap.get('period')}") / 1e4)
    if not vals:
        raise ValueError("filed_spread_range: the extract holds no swaps")
    return min(vals), max(vals)


def cash_yield_at_spreads(build_at, real, spreads):
    """The fitted cash yield c at each of several swap spreads: {spread: c}, with build_at(spread) returning the
    build(c) function that fit_cash_yield takes. A higher spread is a costlier fund, so its fitted c is higher (the cash
    must earn more to match the same fund); at the spread the base fit used, c equals the base c. Used to bound window 1's
    c by the smallest and largest filed spread when that window's counterparty mix is not read (R2 step 12g)."""
    return {float(s): fit_cash_yield(build_at(s), real)["cash_yield"] for s in spreads}


def filed_spread(nport, fund, period):
    """The fund's notional-weighted swap spread (annual decimal) at one N-PORT period, read from the filing extract
    (reference/nport_tradr_2026.json, or any dict of the same shape): each swap's 'pay' leg reads
    'OBFR01 + <n>bps (Spread)', and the spreads are weighted by notional.

    Raises when the fund or the period is absent, when a snapshot has no swaps, or when a pay leg does not state its
    spread, so a typed number can never stand in for a filed one (R2 step 12e: a typed 0.97% for MQQQ had passed as
    VERIFIED while the extract gives 0.993%).
    """
    try:
        snaps = nport[fund]["snapshots"]
    except (KeyError, TypeError) as err:
        raise ValueError(f"filed_spread: no snapshots for {fund!r} in the N-PORT extract") from err
    snap = next((s for s in snaps if s.get("period") == period), None)
    if snap is None or not snap.get("swaps"):
        raise ValueError(f"filed_spread: {fund} has no swaps at {period} in the N-PORT extract")
    num = den = 0.0
    for sw in snap["swaps"]:
        num += float(sw["notional"]) * _pay_leg_bp(sw.get("pay"), f"filed_spread: {fund} {period}")
        den += float(sw["notional"])
    if den <= 0.0:
        raise ValueError(f"filed_spread: {fund} {period}: zero swap notional")
    return num / den / 1e4
