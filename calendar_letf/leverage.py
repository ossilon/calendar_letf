"""Choosing leverage (BACKLOG B17; B1 and B16 reuse it): small functions that turn fund NAVs into the answers of the
sub-2x study. `scripts/run_sub2x.py` runs the kernels and calls these.

Plain-English map
  * The study runs one fund per (leverage L, reset, trigger rule, cost case) over the full history. Each run gives
    one NAV series. These functions read numbers off those series; they never run a kernel themselves, except
    `break_even_fee`, which calls a function the caller hands it.
  * "Growth" is the mean of the calendar-year LOG returns: the full-years CAGR on a log scale. Years are full NYSE
    years (the last session of one December to the last session of the next), so a mean over years has an honest
    standard error: one value per year, with no overlap.
  * The best L is reported as a PLATEAU, never as one point: every L whose growth lies within one standard error of
    the best L's growth. The standard error comes from the yearly differences between that L and the best L (a
    paired test: both funds see the same years).
  * The break-even fee is the largest fee at which a fund at L still grows as fast as the index.
  * The Kelly closed form is the second-order formula for the growth-optimal daily leverage, an independent route
    that the grid search must agree with.

Formulas (second order in the daily return r_t; a_t = accrual of row t; k_t = financing charged on row t):
    daily fund log growth   G(L) ~ sum(L r_t - k_t(L) - f a_t) - L^2 sum(r_t^2) / 2
    Kelly                    L* = (sum r_t - sum (rf_t + s) a_t) / sum r_t^2        (s = spread per turn)
    break-even fee           f* = [(L - 1) sum r_t - sum k_t(L) - (L^2 - 1) sum r_t^2 / 2] / sum a_t
The study never uses these to make a result; the tests check the kernel's grid answers against them.
"""
import math

import numpy as np
import pandas as pd

from . import periods, stats

GRID_STEP = 0.05
GRID = tuple(round(1.0 + GRID_STEP * i, 2) for i in range(41))      # 1.00, 1.05, ..., 3.00: ONE curve, not 41 variants
NAMED = (1.2, 1.5, 1.7)                                              # the named sub-2x points (user, 2026-10-31)
HEADLINE_MAX_L = 2.0                                                 # the headline is "best at or under 2x"
PLATEAU_SE = 1.0                                                     # within this many standard errors of the best


# ---------------------------------------------------------------- yearly growth

def year_end_rows(dates):
    """Row numbers of the last NYSE session of each December in `dates` (periods.period_end_flags, quarterly, in
    December). A year whose December has no session in the data is not a year end."""
    idx = pd.DatetimeIndex(dates)
    q = periods.period_end_flags(idx, "quarterly")
    return np.flatnonzero(q & (idx.month == 12))


def yearly_log_returns(nav):
    """{year: log(NAV at the year's last session / NAV at the previous year's last session)} for every FULL calendar
    year of the Series `nav`: one whose previous year end is also in the data. A NAV at 0 (a fund wiped out) gives
    -inf for the year it ends and every later year. A partial first or last year is left out."""
    v = np.asarray(nav, dtype=np.float64)
    rows = year_end_rows(nav.index)
    out = {}
    for a, b in zip(rows[:-1], rows[1:]):
        v0, v1 = v[a], v[b]
        if v0 <= 0.0 or v1 <= 0.0:
            out[int(nav.index[b].year)] = -math.inf
        else:
            out[int(nav.index[b].year)] = math.log(v1 / v0)
    return out


def mean_interval(x):
    """dict(k, mean, se, lo, hi) of yearly values: mean +/- t975(k - 1) x sd / sqrt(k). NaN fields below k = 2 or when a
    value is not finite (a wiped-out year)."""
    x = np.asarray(x, dtype=np.float64)
    k = len(x)
    if k < 2 or not np.isfinite(x).all():
        nan = float("nan")
        return dict(k=k, mean=float(np.mean(x)) if k and np.isfinite(x).all() else nan, se=nan, lo=nan, hi=nan)
    m, se = float(x.mean()), float(x.std(ddof=1) / math.sqrt(k))
    t = stats.t975(k - 1)
    return dict(k=k, mean=m, se=se, lo=m - t * se, hi=m + t * se)


# ---------------------------------------------------------------- the plateau

def plateau(yearly, Ls=None, max_L=None, n_se=PLATEAU_SE):
    """The best L and the plateau around it.

    yearly  dict L -> array of yearly log returns, the same years for every L (yearly_log_returns, in year order)
    Ls      the L values to search (default: every key); max_L limits them (the headline uses 2.0)
    Returns dict(L_best, growth {L: mean}, diff {L: (mean, se)} against L_best, plateau [L ...], lo, hi, contiguous,
    wiped [L ...], rising_at_top). A fund with a wiped-out year has growth -inf and is never on the plateau.
    The rule: L is on the plateau when mean(y_L - y_best) + n_se x se(y_L - y_best) >= 0. rising_at_top is True when
    growth still rises from the second-highest L searched to the highest (the optimum may lie beyond the grid).
    """
    Ls = sorted(yearly) if Ls is None else sorted(Ls)
    if max_L is not None:
        Ls = [L for L in Ls if L <= max_L + 1e-12]
    if not Ls:
        raise ValueError("plateau: no L to search")
    y = {L: np.asarray(yearly[L], dtype=np.float64) for L in Ls}
    k = {len(v) for v in y.values()}
    if len(k) != 1 or k.pop() < 2:
        raise ValueError("plateau: every L needs the same years, at least 2")
    growth = {L: (float(v.mean()) if np.isfinite(v).all() else -math.inf) for L, v in y.items()}
    wiped = [L for L in Ls if growth[L] == -math.inf]
    alive = [L for L in Ls if L not in wiped]
    if not alive:
        raise ValueError("plateau: every fund was wiped out")
    best = max(alive, key=lambda L: (growth[L], -L))          # ties go to the lower L
    diff, on = {}, []
    for L in alive:
        d = y[L] - y[best]
        se = float(d.std(ddof=1) / math.sqrt(len(d)))
        diff[L] = (float(d.mean()), se)
        if d.mean() + n_se * se >= 0.0:
            on.append(L)
    pos = [Ls.index(L) for L in on]
    contiguous = pos == list(range(min(pos), max(pos) + 1))
    rising = len(Ls) >= 2 and growth[Ls[-1]] > growth[Ls[-2]]
    return dict(L_best=best, growth=growth, diff=diff, plateau=on, lo=min(on), hi=max(on), contiguous=contiguous,
                wiped=wiped, rising_at_top=bool(rising), n_se=n_se)


# ---------------------------------------------------------------- break-even fee

def break_even_fee(growth_at_fee, target, hi=0.20, tol=1e-7, max_iter=80, atol=1e-12):
    """The largest fee f in [0, hi] at which growth_at_fee(f) >= target, for a growth that falls as the fee rises.

    growth_at_fee  a function of the fee (the caller runs the kernel)
    Returns dict(fee, iterations, status): status "found"; "loses at zero fee" (fee None: the fund trails the target
    by more than atol even with no fee); "above hi" (fee = hi: it still wins at the top of the bracket). The search is
    regula falsi with the Illinois change (a bracket that always holds the root), stopped when the bracket is narrower
    than tol. atol absorbs rounding: a 1x fund at zero fee IS the index, but its log wealth can differ in the last
    digits, and that must read as a break-even fee of 0, not as "loses".
    """
    g0 = growth_at_fee(0.0) - target
    if g0 < -atol:
        return dict(fee=None, iterations=1, status="loses at zero fee")
    if g0 < 0.0:
        return dict(fee=0.0, iterations=1, status="found")
    g1 = growth_at_fee(hi) - target
    if g1 >= 0.0:
        return dict(fee=hi, iterations=2, status="above hi")
    a, b, ga, gb, side, it = 0.0, hi, g0, g1, 0, 2
    while b - a > tol and it < max_iter:
        c = (a * gb - b * ga) / (gb - ga)
        if not a < c < b:
            c = 0.5 * (a + b)
        gc = growth_at_fee(c) - target
        it += 1
        if gc >= 0.0:
            a, ga = c, gc
            if side == -1:
                gb *= 0.5
            side = -1
        else:
            b, gb = c, gc
            if side == 1:
                ga *= 0.5
            side = 1
    return dict(fee=a, iterations=it, status="found")


def break_even_fee_second_order(r, k, a, L):
    """The second-order break-even fee of a DAILY fund at L (a closed form, used only by the tests and as a check):

        f* = [(L - 1) sum r - sum k - (L^2 - 1) sum r^2 / 2] / sum a

    r  daily simple returns of the index; k  the fund's financing charge per row as a fraction of NAV
    ((L - 1) x rate x accrual + spread x accrual); a  the fee accrual per row (days / 365). Cross terms between costs
    and returns are dropped, so it is close to the kernel's answer, not equal to it."""
    r, k, a = (np.asarray(x, dtype=np.float64) for x in (r, k, a))
    return float(((L - 1.0) * r.sum() - k.sum() - (L * L - 1.0) * np.sum(r * r) / 2.0) / a.sum())


def kelly_daily(r, rf, a_fin, spread_per_turn=0.0):
    """The second-order growth-optimal (Kelly) leverage of a daily fund, in sample form. Kelly (1956) gives the growth
    criterion; neither he nor Rotando and Thorp (1992) print this closed form, which THEORY.md section 7 derives from the
    second-order growth (R0 read 2026-11-06):

        L* = (sum r - sum (rf + s) x a_fin) / sum r^2

    r  daily simple returns; rf  the annual reference rate known before each row; a_fin  the financing accrual per
    row; s  the swap spread per turn. The same on both balance-sheet bases for L > 1 (the spread grows by s per extra
    turn either way). The fee does not move L*: it does not depend on L."""
    r, rf, a_fin = (np.asarray(x, dtype=np.float64) for x in (r, rf, a_fin))
    return float((r.sum() - np.sum((rf + spread_per_turn) * a_fin)) / np.sum(r * r))


# ---------------------------------------------------------------- out of sample

def best_L(yearly, years, keep, Ls):
    """argmax over Ls of the mean yearly log return over the years where `keep` is True (ties to the lower L); a fund
    with a wiped-out year inside them is never chosen. None when no fund survives."""
    years = np.asarray(years)
    alive = []
    for L in sorted(Ls):
        v = np.asarray(yearly[L], dtype=np.float64)[keep]
        if len(v) and np.isfinite(v).all():
            alive.append((float(v.mean()), -L, L))
    return max(alive)[2] if alive else None


def walk_forward(yearly, years, first_decision, step=10, min_years=10, Ls=None):
    """Choose L again every `step` years on all the years before the decision (an expanding window), hold it for the
    next `step` years, and compare with holding fixed L. Causal: a decision for year D reads only years < D.

    yearly  dict L -> yearly log returns over `years` (in order). Returns dict(rows, chain) where each row is
    (decision year, years held, chosen L, mean growth of the choice in the hold years) and chain is the mean yearly
    growth of the chained choices over every held year, with the years it covers."""
    years = np.asarray(years)
    Ls = sorted(yearly) if Ls is None else sorted(Ls)
    rows, chained = [], []
    D = first_decision
    while D <= years[-1]:
        past = years < D
        hold = (years >= D) & (years < D + step)
        if past.sum() >= min_years and hold.any():
            L = best_L(yearly, years, past, Ls)
            v = np.asarray(yearly[L], dtype=np.float64)[hold] if L is not None else np.array([])
            rows.append(dict(decision=int(D), first_year=int(years[hold][0]), last_year=int(years[hold][-1]),
                             years=int(hold.sum()), L=L, growth=float(v.mean()) if len(v) else float("nan")))
            chained.append(v)
        D += step
    allv = np.concatenate(chained) if chained else np.array([])
    first = rows[0]["first_year"] if rows else None
    return dict(rows=rows, chain=dict(first_year=first, years=int(len(allv)),
                                      growth=float(allv.mean()) if len(allv) else float("nan")))


def fill_losses(nav, period_end, early_dates):
    """The fund's loss from its last reset base at each EARLY reset, for the close and next-close fills (BACKLOG B1: gap
    risk). nav: the NAV Series of a close or next_close run (at an early-reset row the close is the fill, and it becomes
    the new base); period_end: the reset flags of the design; early_dates: nav.attrs["early_resets"].
    Returns [(date, loss)], loss = nav[fill] / nav[last reset before it] - 1. Not for the level fill: there the reset
    happens inside the day at the trigger level, and the close is marked on the new base."""
    v = np.asarray(nav, dtype=np.float64)
    idx = pd.DatetimeIndex(nav.index)
    early = sorted(int(idx.get_loc(pd.Timestamp(d))) for d in early_dates)
    resets = sorted(set(np.flatnonzero(np.asarray(period_end, dtype=bool)).tolist()) | set(early) | {0})
    out = []
    for e in early:
        b = max(r for r in resets if r < e)
        out.append((str(idx[e].date()), float(v[e] / v[b] - 1.0)))
    return out


def era_of(date, eras):
    """The label of the first era (label, first day, last day) that holds `date`, or None."""
    d = pd.Timestamp(date)
    for label, a, b in eras:
        if pd.Timestamp(a) <= d <= pd.Timestamp(b):
            return label
    return None


def era_split_z(yearly, years, split, L_a, L_b, lags=(0, 1, 2)):
    """Does the advantage of L_a over L_b change between the eras before and from `split`? The z statistic of the
    difference in mean yearly log advantage (era 1 minus era 2) with Newey-West standard errors at each Bartlett lag
    (stats.era_difference_z). Returns {lag: z}."""
    years = np.asarray(years)
    d = np.asarray(yearly[L_a], dtype=np.float64) - np.asarray(yearly[L_b], dtype=np.float64)
    return {int(lag): stats.era_difference_z(d[years < split], d[years >= split], lag) for lag in lags}
