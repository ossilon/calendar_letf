"""Volatility threshold: hold the product while recent volatility is low, otherwise hold cash.

Plain-English: "realized volatility" is how much the underlying has been jumping around lately. Take the daily log
returns of the underlying close, ln(close[t] / close[t-1]), over the last `window` days (default 21, about a month),
take their standard deviation (n-1 divisor) and multiply by sqrt(252) to express it per year. Hold (1.0) when that
is below `threshold` (default 25% a year), else cash (0.0). The window ends on row t, so it uses closes 0..t only.
The parameters are the PROMPT.md defaults and are not tuned.
"""
import numpy as np

from .base import Strategy, register

TRADING_DAYS = 252


def realized_vol(close, window):
    """Annualized trailing volatility of daily log returns; NaN on rows 0..window-1 (the first window needs `window` returns)."""
    close = np.asarray(close, dtype=np.float64)
    out = np.full(len(close), np.nan)
    r = np.diff(np.log(close))                                   # r[k] is the return into row k+1
    if len(r) >= window:
        sd = np.lib.stride_tricks.sliding_window_view(r, window).std(axis=1, ddof=1)   # sd[k] covers r[k..k+window-1]
        out[window:] = sd * np.sqrt(TRADING_DAYS)                # that window ends at row k+window
    return out


@register("vol_threshold")
class VolThreshold(Strategy):
    DEFAULTS = {"threshold": 0.25, "window": 21}
    VARIANTS = ({},)

    @property
    def warmup(self):
        return self.params["window"]

    def exposure(self, ctx):
        vol = realized_vol(ctx.close, self.params["window"])
        return np.where(np.isfinite(vol), (vol < self.params["threshold"]).astype(np.float64), np.nan)
