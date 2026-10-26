"""Performance and risk statistics for a LEVEL series (a NAV or an index: 1.0 means "worth the same as at the start").

Plain-English notes
  * "level" is any positive series that grows when you make money: a fund's NAV, an index, wealth. Most functions
    accept a pandas Series (dates in the index) or a plain numpy array.
  * A "drawdown" is how far the level is below its highest earlier value, as a fraction: 0 at a new high, -0.5 when
    it has halved from the peak. "Max drawdown" is the worst one.
  * CAGR (compound annual growth rate) = (end / start) ** (1 / years) - 1. With a pandas Series the years come from
    the dates (days / 365.25, the same rule as validate.cagr). With a plain array you must say `years=` (or use
    `periods_per_year`, trading rows per year, default 252).
  * A fund that has hit zero is finished: CAGR -1 (-100%) and drawdown -1.
  * `window_stats` scores MANY (start, end) windows of ONE level series at once. It exists because the study asks
    the same question for tens of thousands of start dates; the per-window maximum drawdown is a small loop that
    numba compiles to machine code (`@njit`: "compile this function; no Python objects inside").

Nothing here is a result; the study script records results with their provenance.
"""
import numpy as np
import pandas as pd
from numba import njit

TRADING_DAYS = 252
DAYS_PER_YEAR = 365.25


def _arr(level):
    """The level as a float64 numpy array (a copy, so callers can never change the input)."""
    return np.array(level, dtype=np.float64)


def _daily_returns(level):
    """Simple daily returns level[t]/level[t-1] - 1 (NaN where the previous level is not positive)."""
    v = _arr(level)
    prev = v[:-1]
    out = np.full(len(v) - 1, np.nan)
    ok = prev > 0
    out[ok] = v[1:][ok] / prev[ok] - 1.0
    return out


def _years_between(level):
    """Years from first to last row: dates / 365.25 for a Series with a DatetimeIndex, else None."""
    if isinstance(level, pd.Series) and isinstance(level.index, pd.DatetimeIndex) and len(level) > 1:
        return (level.index[-1] - level.index[0]).days / DAYS_PER_YEAR
    return None


# ---------------------------------------------------------------- single-series statistics

def cagr(level, years=None, periods_per_year=TRADING_DAYS):
    """Compound annual growth rate from the first to the last row.

    years: elapsed years. If None: from the dates of a Series (days / 365.25), else (rows - 1) / periods_per_year.
    A start level <= 0 gives NaN; an end level <= 0 gives -1.0 (the fund is finished).
    """
    v = _arr(level)
    if len(v) < 2:
        return float("nan")
    if years is None:
        years = _years_between(level)
        if years is None:
            years = (len(v) - 1) / periods_per_year
    if years <= 0 or v[0] <= 0:
        return float("nan")
    if v[-1] <= 0:
        return -1.0
    return float((v[-1] / v[0]) ** (1.0 / years) - 1.0)


def drawdown_series(level):
    """level / running peak - 1, as a numpy array (0 at a new high)."""
    v = _arr(level)
    peak = np.maximum.accumulate(v)
    return v / peak - 1.0


def max_drawdown(level):
    """Worst peak-to-trough fall as a negative fraction (-0.5 = fell by half). Same rule as validate.max_drawdown."""
    return float(drawdown_series(level).min())


def ann_vol(level, periods_per_year=TRADING_DAYS):
    """Annualized volatility: standard deviation (n-1) of simple daily returns x sqrt(periods_per_year)."""
    r = _daily_returns(level)
    r = r[np.isfinite(r)]
    if len(r) < 2:
        return float("nan")
    return float(r.std(ddof=1) * np.sqrt(periods_per_year))


def calmar(level, years=None):
    """CAGR divided by the size of the max drawdown (a positive number when the fund grew). NaN if no drawdown."""
    mdd = max_drawdown(level)
    if mdd == 0:
        return float("nan")
    return float(cagr(level, years=years) / abs(mdd))


def sortino(level, rf=0.0, periods_per_year=TRADING_DAYS):
    """Sortino ratio on daily returns: annualized mean excess return / annualized downside deviation.

    excess = daily return - rf / periods_per_year (rf is an annual rate as a decimal, 0 unless given).
    Downside deviation = sqrt(mean(min(excess, 0) ** 2)) over ALL days (days above the target count as 0).
    """
    r = _daily_returns(level)
    r = r[np.isfinite(r)]
    if len(r) < 2:
        return float("nan")
    ex = r - rf / periods_per_year
    dd = np.sqrt(np.mean(np.minimum(ex, 0.0) ** 2))
    if dd == 0:
        return float("nan")
    return float(ex.mean() * periods_per_year / (dd * np.sqrt(periods_per_year)))


def ulcer_index(level):
    """Ulcer index: sqrt(mean(drawdown ** 2)) over all rows, with the drawdown as a fraction (0.05 = 5% below peak).

    It punishes depth AND duration of time spent below the peak; a level that only rises scores 0. (Many authors
    quote it in percent points; here it is a fraction, the same unit as max_drawdown.)
    """
    return float(np.sqrt(np.mean(drawdown_series(level) ** 2)))


def time_under_water(level):
    """Fraction of rows where the level is below its running peak (a new high is not under water)."""
    v = _arr(level)
    return float(np.mean(v < np.maximum.accumulate(v)))


def recovery_days(level, count_open=True):
    """Longest peak-to-recovery spell, in ROWS: from a peak's row to the row where the level first gets back to it.

    [1, 0.5, 1] -> 2. If the series ends still below a peak, that unfinished spell counts up to the last row when
    count_open is True (it is at least that long), and is ignored when False.
    """
    v = _arr(level)
    peak, peak_row, below, longest = v[0], 0, False, 0
    for i in range(1, len(v)):
        if v[i] >= peak:                            # back at (or above) the old peak: a new high
            if below:
                longest = max(longest, i - peak_row)    # the spell that just ended
            peak, peak_row, below = v[i], i, False
        else:
            below = True                            # a row below the peak: a spell is under way
    if below and count_open:
        longest = max(longest, len(v) - 1 - peak_row)
    return int(longest)                             # a rising series (no row below a peak) has no spell: 0


def lag1_autocorr(level):
    """Correlation between each daily LOG return and the next one (1-day autocorrelation).

    Negative = moves tend to reverse the next day (daily-reset leverage does better); positive = trends continue
    (daily-reset leverage does worse). Rows with a non-positive level are dropped.
    """
    v = _arr(level)
    v = v[v > 0]
    if len(v) < 4:
        return float("nan")
    r = np.diff(np.log(v))
    a, b = r[:-1], r[1:]
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


# ---------------------------------------------------------------- many windows of one series

def rolling_cagr(level, years, periods_per_year=TRADING_DAYS):
    """CAGR of the trailing `years`-year window ending on each row; NaN until a full window exists.

    Series with a DatetimeIndex: the window starts on the last row dated on or before (end date - years x 365.25
    days), and the CAGR uses the actual elapsed days. Plain array: the window is round(years x periods_per_year) rows.
    Returns a Series (same index) or an array (same length).
    """
    v = _arr(level)
    n = len(v)
    out = np.full(n, np.nan)
    if isinstance(level, pd.Series) and isinstance(level.index, pd.DatetimeIndex):
        days = level.index.values.astype("datetime64[D]").astype(np.int64)
        target = days - int(round(years * DAYS_PER_YEAR))
        starts = np.searchsorted(days, target, side="right") - 1
        ok = starts >= 0
        el = (days - days[np.clip(starts, 0, None)]) / DAYS_PER_YEAR
        good = ok & (v[np.clip(starts, 0, None)] > 0) & (el > 0)
        s0 = v[np.clip(starts, 0, None)]
        with np.errstate(divide="ignore", invalid="ignore"):
            g = np.where(v > 0, (v / s0) ** (1.0 / el) - 1.0, -1.0)
        out[good] = g[good]
        return pd.Series(out, index=level.index, name=getattr(level, "name", None))
    w = int(round(years * periods_per_year))
    if w >= 1 and n > w:
        s0 = v[:-w]
        with np.errstate(divide="ignore", invalid="ignore"):
            g = np.where(v[w:] > 0, (v[w:] / s0) ** (1.0 / years) - 1.0, -1.0)
        out[w:] = np.where(s0 > 0, g, np.nan)
    return out


@njit(cache=True)
def _window_max_drawdown(v, starts, ends):
    """Max drawdown of v[s..e] (inclusive) for each (s, e) pair. NaN if the start level is not positive."""
    m = starts.shape[0]
    out = np.empty(m)
    for k in range(m):
        s, e = starts[k], ends[k]
        peak = v[s]
        if peak <= 0.0:
            out[k] = np.nan
            continue
        worst = 0.0
        for j in range(s, e + 1):
            x = v[j]
            if x > peak:
                peak = x
            dd = x / peak - 1.0
            if dd < worst:
                worst = dd
        out[k] = worst
    return out


def window_stats(level, starts, ends, years=None):
    """CAGR, terminal wealth and max drawdown for many windows [starts[k], ends[k]] of one level series.

    starts, ends: integer ROW positions (ends inclusive, ends >= starts). Returns a dict of float arrays:
        cagr      (end/start)^(1/years) - 1 (-1 if the end level is <= 0; NaN if the start level is not positive)
        terminal  level[end] / level[start]  (wealth of 1 invested at the start; 0 if the fund is finished)
        max_dd    worst peak-to-trough fall inside the window, starting from the start level
        years     elapsed years used for the CAGR
    years: optional array (one per window). Default: the dates of a Series (days / 365.25), else rows / 252.
    Fund NAVs are computed once over the full history and sliced here, never re-simulated per start (DESIGN section 8).
    """
    v = _arr(level)
    s = np.asarray(starts, dtype=np.int64)
    e = np.asarray(ends, dtype=np.int64)
    if s.shape != e.shape:
        raise ValueError("starts and ends must have the same length")
    if len(s) and (s.min() < 0 or e.max() >= len(v) or (e < s).any()):
        raise ValueError("window rows must satisfy 0 <= start <= end < len(level)")
    if years is None:
        if isinstance(level, pd.Series) and isinstance(level.index, pd.DatetimeIndex):
            days = level.index.values.astype("datetime64[D]").astype(np.int64)
            years = (days[e] - days[s]) / DAYS_PER_YEAR
        else:
            years = (e - s) / TRADING_DAYS
    years = np.asarray(years, dtype=np.float64)
    v0, v1 = v[s], v[e]
    with np.errstate(divide="ignore", invalid="ignore"):
        terminal = np.where(v0 > 0, np.maximum(v1, 0.0) / v0, np.nan)
        growth = np.where(terminal > 0, terminal ** (1.0 / years) - 1.0, -1.0)
    growth = np.where(np.isfinite(terminal) & (years > 0), growth, np.nan)
    return dict(cagr=growth, terminal=terminal, max_dd=_window_max_drawdown(v, s, e), years=years)
