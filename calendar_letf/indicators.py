"""Indicators used by the strategy plugins: simple and exponential moving averages that match TradingView, the Guppy
ribbon "stack" states, and week-end closes.

Plain-English notes
  * A moving average smooths a price series. The SIMPLE average (SMA) of the last n closes weights them equally.
    The EXPONENTIAL average (EMA) weights recent closes more: each day it moves a fraction alpha = 2/(n+1) of the way
    from yesterday's EMA toward today's close.
  * TradingView's `ta.ema` starts the EMA with the plain average of the first n closes (so the first n-1 rows are
    empty) and then applies the alpha rule. `pine_ema` does exactly that: it matches all 23 EMA columns of a
    TradingView export of QQQ daily and weekly with Clean Guppy v1 applied to 3e-12 (ASSUMPTIONS section 4;
    `tests/guppy_ema_local.py` re-checks it whenever those local files are present).
  * The Guppy Multiple Moving Average (Daryl Guppy; ChrisMoody's "CM Super Guppy"; the user's "Clean Guppy v1" Pine
    script in reference/) draws two ribbons of EMAs. A ribbon is "stacked up" when every shorter EMA sits above the
    next longer one (a clean uptrend), "stacked down" when every shorter EMA sits below the next longer one, and
    "gray" otherwise. `ribbon_state` returns +1 / -1 / 0 for that.
Everything here uses only data up to and including the row it is computed for (no look-ahead): an EMA on row t
needs closes 0..t, nothing later.
"""
import numpy as np
from numba import njit

GUPPY_FAST = (3, 6, 9, 12, 15, 18, 21)                                       # trader group, Clean Guppy v1 defaults
GUPPY_SLOW = (24, 27, 30, 33, 36, 39, 42, 45, 48, 51, 54, 57, 60, 63, 66)   # investor group
GUPPY_LONG = 200                                                             # the long-term EMA


def sma(x, n):
    """Simple moving average of the last n values; NaN on the first n-1 rows."""
    x = np.asarray(x, dtype=np.float64)
    if n < 1 or n > len(x):
        raise ValueError(f"sma: n must be between 1 and the series length, got {n}")
    out = np.full(len(x), np.nan)
    c = np.cumsum(np.insert(x, 0, 0.0))
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


@njit(cache=True)
def _ema_loop(x, n):
    out = np.full(x.shape[0], np.nan)
    if n > x.shape[0]:
        return out
    a = 2.0 / (n + 1.0)
    s = 0.0
    for i in range(n):
        s += x[i]
    s = s / n                                   # TradingView seeds with the SMA of the first n values
    out[n - 1] = s
    for t in range(n, x.shape[0]):
        s = a * x[t] + (1.0 - a) * s
        out[t] = s
    return out


def pine_ema(x, n):
    """Exponential moving average exactly as TradingView's ta.ema: alpha = 2/(n+1), seeded with the SMA of the first
    n values; NaN on the first n-1 rows."""
    x = np.asarray(x, dtype=np.float64)
    if n < 1:
        raise ValueError(f"pine_ema: n must be >= 1, got {n}")
    if not np.isfinite(x).all():
        raise ValueError("pine_ema: the input must have no NaN (compute on the raw close series)")
    return _ema_loop(x, int(n))


def ribbon_state(emas):
    """+1 where every shorter EMA is above the next longer one (stacked up), -1 where every shorter EMA is below the
    next longer one (stacked down), 0 otherwise or where any EMA is still NaN.

    `emas`: list of arrays ordered from the SHORTEST length to the longest (the Pine script's array order)."""
    arr = np.vstack([np.asarray(e, dtype=np.float64) for e in emas])     # rows = EMAs short..long, cols = time
    valid = np.isfinite(arr).all(axis=0)
    up = (arr[:-1] > arr[1:]).all(axis=0) & valid
    down = (arr[:-1] < arr[1:]).all(axis=0) & valid
    return np.where(up, 1, np.where(down, -1, 0)).astype(np.int8)


def guppy(close, fast=GUPPY_FAST, slow=GUPPY_SLOW, long=GUPPY_LONG):
    """Clean Guppy v1 states on a close series: dict(fast_state, slow_state, above_long) as int8 arrays, plus the
    EMAs themselves. slow_state is what the fixed trading rule uses (PROMPT.md: buy when it becomes +1, sell when
    it becomes -1, hold through 0); above_long is 1 where close > the 200 EMA (variant B's filter)."""
    close = np.asarray(close, dtype=np.float64)
    fast_emas = [pine_ema(close, n) for n in fast]
    slow_emas = [pine_ema(close, n) for n in slow]
    long_ema = pine_ema(close, long)
    above = np.where(np.isfinite(long_ema) & (close > long_ema), 1, 0).astype(np.int8)
    return dict(fast_state=ribbon_state(fast_emas), slow_state=ribbon_state(slow_emas), above_long=above,
                fast_emas=fast_emas, slow_emas=slow_emas, long_ema=long_ema)


def week_end_rows(dates):
    """Row numbers of the last trading day of each calendar week (Monday-to-Sunday weeks), as in periods.period_ids."""
    from . import periods
    # calendar=None on purpose: a weekly SIGNAL is computed on the data's own last bar of the week (TradingView's
    # weekly bar closes on the week's last session in the file), not on the fund's reset calendar.
    flags = periods.period_end_flags(dates, "weekly", calendar=None).copy()
    flags[-1] = True                            # the final row closes the last (possibly partial) week for signals
    return np.flatnonzero(flags)
