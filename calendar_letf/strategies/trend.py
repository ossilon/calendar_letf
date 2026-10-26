"""Trend rules: hold the product while the underlying's close is above its n-period average, otherwise hold cash.

    trend_50d   50-day average of daily closes
    trend_200d  200-day average of daily closes
    trend_200w  200-WEEK average of weekly closes (the last trading day of each week); the signal only changes on
                week-end rows and is carried forward on the other days

Each takes kind="sma" (simple average, the default: the standard in published studies) or kind="ema" (exponential
average exactly as TradingView's ta.ema, via indicators.pine_ema). Both are run. The lengths (50, 200, 200 weeks) are
the textbook ones and are NOT tuned.

Plain-English: exposure is 1.0 on a day when close > average, 0.0 when close <= average, and NaN (no signal yet)
until the average exists. The signal on row t uses closes 0..t only; the backtest acts on it one day later.
"""
import numpy as np

from .. import indicators as ind
from .base import Strategy, carry_forward, register, week_end_closes


def moving_average(x, n, kind):
    """SMA or Pine EMA of x with length n; all NaN (not an error) if the series is shorter than n."""
    x = np.asarray(x, dtype=np.float64)
    if kind == "sma":
        return ind.sma(x, n) if n <= len(x) else np.full(len(x), np.nan)
    if kind == "ema":
        return ind.pine_ema(x, n)
    raise ValueError(f"kind must be 'sma' or 'ema', got {kind!r}")


def above_average(close, n, kind):
    """1.0 where close > its n-average, 0.0 where not, NaN while the average does not exist yet."""
    avg = moving_average(close, n, kind)
    return np.where(np.isfinite(avg), (close > avg).astype(np.float64), np.nan)


class _Trend(Strategy):
    N = 200                     # average length, in days or weeks
    WEEKLY = False
    DEFAULTS = {"kind": "sma"}
    VARIANTS = ({"kind": "sma"}, {"kind": "ema"})

    def __init__(self, **params):
        super().__init__(**params)
        if self.params["kind"] not in ("sma", "ema"):
            raise ValueError(f"{self.key}: kind must be 'sma' or 'ema', got {self.params['kind']!r}")

    @property
    def name(self):
        return f"{self.key}_{self.params['kind']}"

    @property
    def warmup(self):
        """Nominal leading NaN rows: N-1 days, or about 5 days per week for the weekly rule (the engine uses the real
        first valid row, which depends on where the weeks fall)."""
        return (self.N - 1) * (5 if self.WEEKLY else 1)

    def exposure(self, ctx):
        if not self.WEEKLY:
            return above_average(ctx.close, self.N, self.params["kind"])
        rows, weekly_close = week_end_closes(ctx)
        return carry_forward(above_average(weekly_close, self.N, self.params["kind"]), rows, len(ctx))


@register("trend_50d")
class Trend50d(_Trend):
    """Hold while close > 50-day average."""
    N = 50


@register("trend_200d")
class Trend200d(_Trend):
    """Hold while close > 200-day average."""
    N = 200


@register("trend_200w")
class Trend200w(_Trend):
    """Hold while the latest week-end close > 200-week average of week-end closes (signal changes on week-ends only)."""
    N = 200
    WEEKLY = True
