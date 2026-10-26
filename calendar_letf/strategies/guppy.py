"""Clean Guppy: a Python port of the author's unpublished Pine Script indicator "Clean Guppy v1" (the Guppy Multiple
Moving Average after Daryl Guppy; EMA lengths and stack-color logic after ChrisMoody's "CM Super Guppy") turned into
a trading rule. The port's EMAs and ribbon states were verified against TradingView's own output on every daily and
weekly bar of a QQQ export. The rule was FIXED before any testing (PROMPT.md STRATEGIES):

    slow ribbon = the 15 EMAs of lengths 24, 27, ..., 66 (the Pine "investor group"), computed on the close series
    state  +1  every EMA is above the next longer one   ("stacked up", green)
           -1  every EMA is below the next longer one   ("stacked down", red)
            0  neither                                  (gray: the trend is in transition)
    rule   buy (exposure 1.0) when the state becomes +1, sell (0.0) when it becomes -1 from ANY prior state, and hold
           the previous exposure while the state is 0 (gray). The rule starts flat (0.0).
    variant B (filter_200=True) additionally holds only while the close is above its 200 EMA (on the same series).

`guppy` runs on daily closes; `guppy_weekly` runs on the week-end closes (lengths then count weeks) and carries each
weekly signal forward over the days of the next week. The EMA lengths are NOT tuned. The EMAs are TradingView's
ta.ema (indicators.pine_ema, verified against a TradingView export to 3e-12).

Direct red <-> green jumps: the Pine alert only fires on gray->green and gray->red, so a bar where the state goes
straight from -1 to +1 (or +1 to -1) would trade here but raise no alert live. `diagnostics` counts them.
"""
import numpy as np
from numba import njit

from .. import indicators as ind
from .base import Strategy, carry_forward, register, week_end_closes


@njit(cache=True)
def hold_through_gray(state):
    """Turn a +1 / 0 / -1 state sequence into exposure: 1 when the state is +1, 0 when it is -1, otherwise unchanged;
    starts at 0. [0,0,1,0,0,-1,0,1] -> [0,0,1,1,1,0,0,1]."""
    n = state.shape[0]
    out = np.empty(n)
    expo = 0.0
    for t in range(n):
        if state[t] == 1:
            expo = 1.0
        elif state[t] == -1:
            expo = 0.0
        out[t] = expo
    return out


def count_direct_jumps(state):
    """(up, down): bars where the state goes straight from -1 to +1 (up) or from +1 to -1 (down) with no gray bar between."""
    s = np.asarray(state, dtype=np.int64)
    if len(s) < 2:
        return 0, 0
    return int(((s[:-1] == -1) & (s[1:] == 1)).sum()), int(((s[:-1] == 1) & (s[1:] == -1)).sum())


class _Guppy(Strategy):
    WEEKLY = False
    DEFAULTS = {"filter_200": False}
    VARIANTS = ({"filter_200": False}, {"filter_200": True})

    @property
    def name(self):
        return self.key + ("_f200" if self.params["filter_200"] else "")

    @property
    def warmup(self):
        """Nominal leading NaN rows: the slowest EMA needed (66, or 200 with the filter) minus 1, in days or weeks."""
        need = ind.GUPPY_LONG if self.params["filter_200"] else max(ind.GUPPY_SLOW)
        return (need - 1) * (5 if self.WEEKLY else 1)

    def _series(self, ctx):
        """(row numbers the bars sit on, the bar closes): every day, or the week-end rows."""
        if self.WEEKLY:
            return week_end_closes(ctx)
        return np.arange(len(ctx)), ctx.close

    def _bar_exposure(self, close):
        """Exposure per bar (NaN before the first valid bar) and the guppy dict for those bars."""
        g = ind.guppy(close)
        expo = hold_through_gray(g["slow_state"])
        first_valid = (ind.GUPPY_LONG if self.params["filter_200"] else max(ind.GUPPY_SLOW)) - 1
        if self.params["filter_200"]:
            expo = expo * g["above_long"]
        expo[:first_valid] = np.nan
        return expo, g

    def exposure(self, ctx):
        rows, close = self._series(ctx)
        expo, _ = self._bar_exposure(close)
        if not self.WEEKLY:
            return expo
        return carry_forward(expo, rows, len(ctx))

    def diagnostics(self, ctx):
        """Counts on the slow-ribbon state of the bars the rule trades on (days or weeks): bars valid, share of bars
        green / red / gray, direct red<->green jumps (up, down) and the number of buy and sell events of the rule."""
        rows, close = self._series(ctx)
        expo, g = self._bar_exposure(close)
        s = g["slow_state"][max(ind.GUPPY_SLOW) - 1:]               # the slow ribbon's own valid bars (not cut by the 200 filter)
        up, down = count_direct_jumps(s)
        e = expo[np.isfinite(expo)]
        buys = int(((e[1:] == 1.0) & (e[:-1] == 0.0)).sum()) + int(len(e) > 0 and e[0] == 1.0)
        sells = int(((e[1:] == 0.0) & (e[:-1] == 1.0)).sum())
        return dict(bars=int(len(s)), green_share=float((s == 1).mean()) if len(s) else float("nan"),
                    red_share=float((s == -1).mean()) if len(s) else float("nan"),
                    gray_share=float((s == 0).mean()) if len(s) else float("nan"),
                    jumps_red_to_green=up, jumps_green_to_red=down, jumps_total=up + down, buy_events=buys, sell_events=sells)


@register("guppy")
class GuppyDaily(_Guppy):
    """Clean Guppy v1 slow ribbon on daily closes."""
    WEEKLY = False


@register("guppy_weekly")
class GuppyWeekly(_Guppy):
    """Clean Guppy v1 slow ribbon on weekly (last-trading-day-of-week) closes."""
    WEEKLY = True
