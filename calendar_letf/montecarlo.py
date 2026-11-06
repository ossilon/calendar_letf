"""Monte Carlo paths for the calendar-reset funds (BACKLOG B11). `scripts/run_montecarlo.py` runs the study.

Plain-English map
  * A PATH is ten years of made-up history on a REAL trading calendar (the NYSE sessions of the ten years to the study
    end), so weekly, monthly and quarterly resets fall on real period ends and every day accrues its real calendar
    days. Each day of the path copies one day of the real history: the index's total-return move, its price move (what
    the early-reset trigger watches), that day's low against its close, and the reference rate known before it.
  * BLOCK BOOTSTRAP: the days are copied in blocks of consecutive history days (21, 63, 126 or 252), so a path keeps
    how real days follow each other inside a block. The calendar-versus-daily gap lives in that order (FINDINGS F7), so
    the answer can depend on the block length, and the study reports all four.
  * PARAMETRIC paths: daily log returns from an AR(1) law with a chosen drift, volatility and lag-1 autocorrelation.
    They show the mechanism with nothing else in the way.
  * BRIDGE paths: a path pinned to given month-end levels (the 1929-39 S&P 500 from Shiller's monthly prices), with
    random daily moves between the pins. The project has no daily data before 1950, so these paths are PARAMETRIC and
    every result from them says so.
  * `simulate_batch` runs every fund on every path with the project's own numba kernels (kernel.periodic_reset_nav,
    kernel.daily_reset_nav) in parallel over paths, and keeps the NAV at chosen rows, the worst drawdown, the count of
    early resets and the row of a wipeout. tests/test_montecarlo.py checks it against kernel.run, path by path.
A Monte Carlo distribution is a spread of outcomes under the resampling model. It is NOT a confidence interval for
the true gap; the Monte Carlo error of each statistic is reported next to it.
"""
import math

import numpy as np
import pandas as pd
from numba import njit, prange

from . import coverage, periods
from .kernel import daily_reset_nav, periodic_reset_nav

BLOCKS = (21, 63, 126, 252)
PATH_YEARS = 10


# ---------------------------------------------------------------- the kernels on many paths

@njit(parallel=True, cache=True)
def simulate_batch(U, T, TL, R, acc_fin, acc_fee, period_end, L, spread, fee, drop, rate_mult, daily, checkpoints):
    """Every product k on every path p.

    U, T, TL, R   (paths x rows) underlying level, trigger close, trigger low and reference rate (lagged) of each path
    acc_fin/fee   (rows) accrual fractions of the shared calendar
    period_end    (products x rows) reset flags of each product (ignored for a daily product)
    L, spread, fee, drop, rate_mult, daily   (products) the product's terms; drop 0 = no early reset; the rate the
                  product pays is R x rate_mult (a cost encoding's rate turns)
    checkpoints   rows at which to keep the NAV
    Returns navc (paths x products x checkpoints), mdd (paths x products, worst peak-to-trough fall), early (count of
    early resets), term (row of a wipeout, -1 if none).
    """
    P, n = U.shape
    K = L.shape[0]
    C = checkpoints.shape[0]
    navc = np.zeros((P, K, C))
    mdd = np.zeros((P, K))
    early = np.zeros((P, K), dtype=np.int64)
    term = np.full((P, K), -1, dtype=np.int64)
    for p in prange(P):
        for k in range(K):
            fee_arr = np.full(n, fee[k])
            r = R[p] * rate_mult[k]
            if daily[k]:
                nav, ti = daily_reset_nav(U[p], r, acc_fin, acc_fee, L[k], spread[k], fee_arr)
                ne = 0
            else:
                nav, flags, ti = periodic_reset_nav(U[p], T[p], TL[p], r, acc_fin, acc_fee, period_end[k], L[k], spread[k],
                                                    fee_arr, drop[k], 0)
                ne = 0
                for t in range(n):
                    ne += flags[t]
            peak = nav[0]
            worst = 0.0
            for t in range(n):
                v = nav[t]
                if v > peak:
                    peak = v
                dd = v / peak - 1.0
                if dd < worst:
                    worst = dd
            mdd[p, k] = worst
            early[p, k] = ne
            term[p, k] = ti
            for c in range(C):
                navc[p, k, c] = nav[checkpoints[c]]
    return navc, mdd, early, term


# ---------------------------------------------------------------- the calendar of every path

def path_calendar(dates, end, years=PATH_YEARS):
    """The real sessions from the last session on or before (end - years) to `end`: the shared calendar of every path.
    Row 0 is the start (no return), so a path has len - 1 daily moves."""
    dates = pd.DatetimeIndex(dates)
    end = pd.Timestamp(end)
    start = dates[dates <= end - pd.DateOffset(years=years)][-1]
    cal = dates[(dates >= start) & (dates <= end)]
    if cal[-1] != end:
        raise ValueError(f"path_calendar: no session on {end.date()}")
    return cal


def month_end_rows(cal):
    """Row 0 and the row of every NYSE month end after it (the checkpoints of the fan chart and the horizons)."""
    rows = np.flatnonzero(periods.period_end_flags(cal, "monthly"))
    return np.concatenate(([0], rows[rows > 0])).astype(np.int64)


# ---------------------------------------------------------------- the history the blocks copy

def history(u, trigger, trigger_low, rate):
    """Daily arrays of the real history, one entry per history day that has a move (day 1 onward):
    lr_u (log move of the underlying), lr_t (log move of the trigger close), low_ratio (that day's trigger low over its
    close, at most 1) and rate (the reference rate known before that day). All four come from the SAME day."""
    u, trig, rate = (np.asarray(x, dtype=np.float64) for x in (u, trigger, rate))
    low = trig if trigger_low is None else np.asarray(trigger_low, dtype=np.float64)
    if not (len(u) == len(trig) == len(low) == len(rate)):
        raise ValueError("history: u, trigger, trigger_low and rate must have one value per day")
    return dict(lr_u=np.diff(np.log(u)), lr_t=np.diff(np.log(trig)), low_ratio=np.minimum(low, trig)[1:] / trig[1:],
                rate=rate[1:].copy())


def block_starts(n_hist, block, allowed=None):
    """Every start s whose block s .. s + block - 1 lies inside the history (and, with `allowed`, a boolean per history
    day, only on allowed days: the era-restricted bootstrap)."""
    if block < 1 or block > n_hist:
        raise ValueError(f"block_starts: block {block} does not fit a history of {n_hist} days")
    s = np.arange(n_hist - block + 1)
    if allowed is None:
        return s
    ok = np.asarray(allowed, dtype=bool)
    run = np.convolve(ok.astype(np.int64), np.ones(block, dtype=np.int64), mode="valid")   # allowed days per window
    return s[run == block]


def block_pick(rng, starts, block, n_days, paths, random_phase=False):
    """(paths x n_days) history-day indices: blocks of `block` consecutive days, each block's start drawn uniformly from
    `starts`, joined and cut to n_days.

    random_phase=False (the B11 default): every path's seams fall on the same rows (1, block + 1, ...). With 252-day
    blocks on a ten-year calendar that starts at a quarter end, the seams sit near the standard period ends, so a standard
    period rarely straddles one. random_phase=True drops a uniform 0 .. block - 1 days from the front of each path, so a
    seam can fall on any row (BACKLOG B12: a reset moved to another day must not straddle seams more often than the
    standard day does)."""
    nb = -(-n_days // block) + (1 if random_phase else 0)
    st = rng.choice(starts, size=(paths, nb), replace=True)
    pick = (st[:, :, None] + np.arange(block)[None, None, :]).reshape(paths, nb * block)
    if not random_phase:
        return pick[:, :n_days]
    off = rng.integers(0, block, size=paths)
    return pick[np.arange(paths)[:, None], off[:, None] + np.arange(n_days)[None, :]]


def build_paths(h, pick, shift=0.0):
    """Levels of the paths whose days copy history days `pick` (paths x n_days). Row 0 is 1.0 (the start); `shift` is
    taken off every daily log move of both the underlying and the trigger (the flat-decade stress). Returns U, T, TL, R
    as (paths x (n_days + 1)) arrays."""
    P, n = pick.shape
    U = np.ones((P, n + 1))
    T = np.ones((P, n + 1))
    U[:, 1:] = np.exp(np.cumsum(h["lr_u"][pick] - shift, axis=1))
    T[:, 1:] = np.exp(np.cumsum(h["lr_t"][pick] - shift, axis=1))
    TL = T.copy()
    TL[:, 1:] *= h["low_ratio"][pick]
    R = np.empty((P, n + 1))
    R[:, 1:] = h["rate"][pick]
    R[:, 0] = R[:, 1]
    return U, T, TL, R


# ---------------------------------------------------------------- parametric and bridge paths

def ar1_log_returns(rng, paths, n, mean, sd, phi):
    """(paths x n) daily log returns with mean `mean`, standard deviation `sd` and lag-1 autocorrelation `phi`
    (a stationary AR(1), started from its stationary law)."""
    if not -1.0 < phi < 1.0:
        raise ValueError(f"ar1_log_returns: phi must be in (-1, 1), got {phi}")
    z = rng.standard_normal((paths, n))
    x = np.empty((paths, n))
    x[:, 0] = z[:, 0]
    s = math.sqrt(1.0 - phi * phi)
    for t in range(1, n):
        x[:, t] = phi * x[:, t - 1] + s * z[:, t]
    return mean + sd * x


def bridge_log_levels(rng, paths, anchor_rows, anchor_logs, sd):
    """(paths x (last anchor row + 1)) log levels that pass exactly through anchor_logs at anchor_rows, with a
    Brownian bridge of daily standard deviation `sd` between consecutive anchors. anchor_rows must start at 0 and rise."""
    rows = np.asarray(anchor_rows, dtype=np.int64)
    logs = np.asarray(anchor_logs, dtype=np.float64)
    if rows[0] != 0 or (np.diff(rows) <= 0).any() or len(rows) != len(logs):
        raise ValueError("bridge_log_levels: anchor rows must start at 0 and rise, one log level per row")
    out = np.empty((paths, rows[-1] + 1))
    out[:, 0] = logs[0]
    for a, b, la, lb in zip(rows[:-1], rows[1:], logs[:-1], logs[1:]):
        m = b - a
        w = np.cumsum(rng.normal(0.0, sd, (paths, m)), axis=1)
        frac = np.arange(1, m + 1) / m
        out[:, a + 1:b + 1] = la + frac * (lb - la) + w - frac * w[:, -1:]
    return out


def paths_from_log_returns(lr_u, lr_t, rate):
    """U, T, TL, R from daily log returns (paths x n) of the underlying and the trigger and a rate per day (n) or a
    constant: row 0 is 1.0, the trigger low equals the close (no intraday information)."""
    P, n = lr_u.shape
    U = np.ones((P, n + 1))
    T = np.ones((P, n + 1))
    U[:, 1:] = np.exp(np.cumsum(lr_u, axis=1))
    T[:, 1:] = np.exp(np.cumsum(lr_t, axis=1))
    R = np.empty((P, n + 1))
    R[:, :] = rate if np.ndim(rate) == 0 else np.concatenate(([rate[0]], rate))[None, :]
    return U, T, T.copy(), R


# ---------------------------------------------------------------- statistics of a Monte Carlo sample

def describe(x, quantiles=(5, 25, 50, 75, 95)):
    """Summary of one statistic over paths: n, mean with its Monte Carlo SE and normal 95% interval, the median with its
    distribution-free 95% interval (coverage.quantile_interval), the chosen percentiles and the share above zero with
    its SE. NaN values (a statistic a path does not have) are dropped and counted."""
    x = np.asarray(x, dtype=np.float64).ravel()
    ok = np.isfinite(x)
    v = x[ok]
    n = len(v)
    if n < 2:
        return dict(n=n, n_missing=int((~ok).sum()))
    se = float(v.std(ddof=1) / math.sqrt(n))
    m = float(v.mean())
    p = float((v > 0).mean())
    lo, hi = coverage.quantile_interval(v, 0.5)
    out = dict(n=n, n_missing=int((~ok).sum()), mean=m, mean_se=se, mean_lo=m - 1.959963984540054 * se,
               mean_hi=m + 1.959963984540054 * se, median=float(np.median(v)), median_lo=lo, median_hi=hi,
               share_pos=p, share_pos_se=math.sqrt(p * (1.0 - p) / n))
    for q in quantiles:
        out[f"p{q}"] = float(np.percentile(v, q))
    return out


def cagr_between(navc, c0, c1, years):
    """CAGR of every path between checkpoint columns c0 and c1 (navc: paths x checkpoints); -1 once a fund is at 0."""
    a, b = navc[:, c0], navc[:, c1]
    with np.errstate(divide="ignore", invalid="ignore"):
        g = np.where(b > 0, (b / a) ** (1.0 / years) - 1.0, -1.0)
    return np.where(a > 0, g, np.nan)


def ar1_variance_ratio(phi, T):
    """VR(T) of an AR(1) with lag-1 autocorrelation phi: 1 + 2 sum_{j=1}^{T-1} (1 - j / T) phi^j."""
    return 1.0 + 2.0 * sum((1.0 - j / T) * phi ** j for j in range(1, int(T)))
