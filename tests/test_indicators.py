"""Known-answer tests for indicators.py (step 4). Made-up data only; the TradingView export check is in guppy_ema_local.py."""
import numpy as np
import pandas as pd

from _harness import check, raises  # noqa: I001
from calendar_letf import indicators as ind

# ---- sma / pine_ema by hand ----
x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
check("sma: n=2 on 1..5 -> nan, 1.5, 2.5, 3.5, 4.5", np.allclose(ind.sma(x, 2)[1:], [1.5, 2.5, 3.5, 4.5]) and np.isnan(ind.sma(x, 2)[0]))
# pine_ema n=3: seed = mean(1,2,3) = 2 on row 2; alpha = 0.5; row 3: 0.5*4 + 0.5*2 = 3; row 4: 0.5*5 + 0.5*3 = 4
e = ind.pine_ema(x, 3)
check("pine_ema: n=3 on 1..5 -> nan, nan, 2 (seed = SMA of first 3), 3, 4", np.isnan(e[:2]).all() and np.allclose(e[2:], [2.0, 3.0, 4.0]), e)
check("pine_ema: n longer than the series -> all NaN", np.isnan(ind.pine_ema(x, 9)).all())
raises("pine_ema: refuses NaN input (no silent gaps)", lambda: ind.pine_ema(np.array([1.0, np.nan, 2.0]), 2), "NaN")
check("pine_ema: n=1 is the series itself", np.allclose(ind.pine_ema(x, 1), x))

# ---- ribbon_state ----
up = ind.ribbon_state([np.array([3.0, 3.0]), np.array([2.0, 2.0]), np.array([1.0, 1.0])])
down = ind.ribbon_state([np.array([1.0]), np.array([2.0]), np.array([3.0])])
mixed = ind.ribbon_state([np.array([2.0]), np.array([3.0]), np.array([1.0])])
nan = ind.ribbon_state([np.array([np.nan]), np.array([2.0]), np.array([1.0])])
check("ribbon_state: shorter above longer -> +1, below -> -1, mixed -> 0, any NaN -> 0",
      (up == 1).all() and down[0] == -1 and mixed[0] == 0 and nan[0] == 0)

# ---- guppy on a clean trend ----
days = pd.bdate_range("2020-01-01", periods=400)
rising = np.exp(np.linspace(0, 1, 400)) * 100.0                 # steady uptrend: every shorter EMA above the next longer one
g = ind.guppy(rising)
check("guppy: on a steady uptrend the slow ribbon is stacked up (+1) once all 15 EMAs exist (row 65 on) and 0 before",
      (g["slow_state"][65:] == 1).all() and (g["slow_state"][:65] == 0).all(), (g["slow_state"][:70]))
check("guppy: on a steady uptrend the close is above the 200 EMA from row 199 on, 0 before (EMA not yet defined)",
      (g["above_long"][199:] == 1).all() and (g["above_long"][:199] == 0).all())
falling = rising[::-1].copy()
check("guppy: on a steady downtrend the slow ribbon is stacked down (-1)", (ind.guppy(falling)["slow_state"][65:] == -1).all())
check("guppy: the EMA lengths are Clean Guppy v1's (3..21 step 3; 24..66 step 3; 200)",
      ind.GUPPY_FAST == (3, 6, 9, 12, 15, 18, 21) and ind.GUPPY_SLOW == tuple(range(24, 67, 3)) and ind.GUPPY_LONG == 200)

# ---- no look-ahead: truncating the series never changes earlier values ----
full = ind.pine_ema(rising, 21)
cut = ind.pine_ema(rising[:250], 21)
check("pine_ema: values up to row 249 are identical whether or not later data exist (no look-ahead)",
      np.array_equal(full[:250], cut, equal_nan=True))
gs_full, gs_cut = ind.guppy(rising)["slow_state"], ind.guppy(rising[:300])["slow_state"]
check("guppy: states up to row 299 are identical whether or not later data exist", np.array_equal(gs_full[:300], gs_cut))

# ---- week_end_rows ----
idx = pd.bdate_range("2024-01-01", "2024-01-19")                  # three Mon-Fri weeks
we = ind.week_end_rows(idx)
check("week_end_rows: the last trading day of each week (three Fridays here), final row included",
      [str(idx[i].date()) for i in we] == ["2024-01-05", "2024-01-12", "2024-01-19"])
idx2 = idx.delete(4)                                             # Friday 5 Jan missing: Thursday closes that week
check("week_end_rows: with Friday missing the week ends on Thursday", str(idx2[ind.week_end_rows(idx2)[0]].date()) == "2024-01-04")
