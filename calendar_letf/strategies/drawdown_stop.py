"""Drawdown stop: go to cash after a big fall in the product's own NAV, come back when it makes a new peak.

Plain-English: keep the highest NAV seen so far (the "running peak"). If the NAV is more than `drop` (default 30%)
below that peak, exposure is 0 (cash). Once out, stay out until the NAV makes a NEW peak (a close strictly above the
old one), then exposure is 1 again. The signal on row t uses NAVs 0..t only.

PATH-DEPENDENT. The running peak starts at the first row the rule is given, so the answer depends on where the
investor starts. A multi-start result for this rule therefore cannot be read off one wealth path (as it can for the
trend rules): the study runs the rule once per start date, giving the rule only the history from that start.
This one signal uses the product NAV (the fund's own drawdown), not the underlying index.
"""
import numpy as np
from numba import njit

from .base import Strategy, register


@njit(cache=True)
def stop_exposure(nav, drop):
    """1.0 / 0.0 exposure path of the drawdown stop on a NAV array (see the module docstring)."""
    n = nav.shape[0]
    out = np.empty(n)
    peak = nav[0]
    holding = True
    for t in range(n):
        new_peak = nav[t] > peak
        if new_peak:
            peak = nav[t]
        if holding:
            if nav[t] < (1.0 - drop) * peak:
                holding = False                  # fell more than `drop` below the peak: sell
        elif new_peak:
            holding = True                       # a new peak: buy back
        out[t] = 1.0 if holding else 0.0
    return out


@register("drawdown_stop")
class DrawdownStop(Strategy):
    DEFAULTS = {"drop": 0.30}
    VARIANTS = ({},)
    path_dependent = True

    def __init__(self, **params):
        super().__init__(**params)
        if not 0.0 < self.params["drop"] < 1.0:
            raise ValueError("drawdown_stop: drop must be between 0 and 1 (0.30 = 30%)")

    def exposure(self, ctx):
        nav = np.ascontiguousarray(ctx.product_nav, dtype=np.float64)
        if len(nav) == 0:
            return np.zeros(0)
        return stop_exposure(nav, float(self.params["drop"]))
