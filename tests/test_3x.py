"""BACKLOG B1: 3x calendar resets. products.at_leverage_filed, leverage.fill_losses, leverage.era_of, the kernel's
wipeout and trigger order at 3x, and the results file results/three_x.json.

Part A, planted (made-up data; each expected value from an independent route: the one-period closed form 1 + 3R,
hand-computed levels, the filed terms in products.MODELS_3X). Part B checks what must hold in any correct run.
"""
import json
import math

import numpy as np
import pandas as pd

from _harness import ROOT, check, raises
from calendar_letf import kernel, leverage, products, study

UPRO = products.MODELS_3X["UPRO_MODEL"]
BASE = products.PRODUCTS["HYP_SPX_M"]

# ---- A1. the 3x design with filed swap terms ----
p3 = products.at_leverage_filed(BASE, 3.0, UPRO, 0.7 / 3, "planted", "T3")
tw = products.twin_of(p3)
check("at_leverage_filed: L 3, the swaps basis, UPRO's filed spread per turn and swap turns, the base design's fee and reset",
      p3.L == 3.0 and p3.costs.spread_basis == "swaps" and p3.costs.spread == UPRO.costs.spread and p3.costs.turns == UPRO.costs.turns
      and p3.fee == BASE.fee and p3.reset == "monthly" and p3.kind == "MODELED" and "HYPOTHETICAL" in p3.note)
check("at_leverage_filed: the daily twin carries the same L, spread, turns and fee", tw.L == 3.0 and tw.costs.turns == p3.costs.turns
      and tw.costs.spread == p3.costs.spread and tw.fee == p3.fee and tw.reset == "daily")
raises("at_leverage_filed refuses a daily base", lambda: products.at_leverage_filed(products.PRODUCTS["TWIN_SPX_D"], 3.0, UPRO, None, "x", "x"), "daily")
raises("at_leverage_filed refuses a model that is not a real fund at filed terms",
       lambda: products.at_leverage_filed(BASE, 3.0, BASE, None, "x", "x"), "not a model")
raises("at_leverage_filed refuses a model on another index", lambda: products.at_leverage_filed(BASE, 3.0, products.MODELS_3X["TQQQ_MODEL"], None, "x", "x"),
       "is on NDX")


# ---- A2. wipeout and trigger order at 3x (zero costs, the trigger watches the index itself) ----
def run(levels, drop, mode="level", start="2024-01-29"):
    ix = pd.bdate_range(start, periods=len(levels))
    u = pd.Series(levels, index=ix, dtype=float)
    return kernel.periodic_reset_series(u, 0.0, reset="monthly", L=3.0, spread_per_nav=0.0, fee=0.0, early_drop=drop, early_mode=mode)


flat_then = lambda lv: [3.0, 3.0, 3.0, 3.0, 3.0] + lv          # noqa: E731  (2024-01-31 is the reset; the fall comes in February)
dead = run(flat_then([2.0, 2.0, 2.5]), None)
alive = run(flat_then([2.0 + 3e-9, 2.0 + 3e-9, 2.5]), None)
check("kernel at 3x, no trigger: an in-period fall of exactly 1/3 (3 -> 2) wipes the fund out for good; a fall 1e-9 short does not",
      dead.attrs["terminated"] is not None and dead.iloc[-1] == 0.0 and alive.attrs["terminated"] is None and alive.iloc[-1] > 0.0,
      (dead.attrs["terminated"], alive.iloc[-1]))
slide = flat_then([2.85, 2.7, 2.55, 2.4, 2.25, 2.1, 1.95, 1.8])       # a steady fall to -40% inside February
d35 = run(slide, 0.35)
d13 = run(slide, 1.0 / 3.0)
d30 = run(slide, 0.30)
check("kernel at 3x: a trigger at 35% or at exactly 1/3 never resets before the wipeout (the fund dies, no early reset)",
      d35.attrs["terminated"] is not None and d35.attrs["early_resets"] == [] and d13.attrs["terminated"] is not None
      and d13.attrs["early_resets"] == [], (d35.attrs, d13.attrs["early_resets"]))
check("kernel at 3x: a 30% trigger fires first and the fund survives the same fall", d30.attrs["early_resets"] != []
      and d30.attrs["terminated"] is None and d30.iloc[-1] > 0.0, d30.attrs)

# ---- A3. the fill losses (gap risk), against 1 + 3R ----
ix = pd.bdate_range("2024-01-29", periods=8)
pe = np.array([d == pd.Timestamp("2024-01-31") for d in ix])
close = run([3.0, 3.0, 3.0, 2.25, 2.25, 2.25, 2.25, 2.25], 0.7 / 3, "close")          # -25% on 2024-02-01: fires 23.3%
fl = leverage.fill_losses(close, pe, close.attrs["early_resets"])
check("fill_losses, close fill: a -25% day fills at the close, a fund loss of 3 x 25% = 75% (the trigger level would give 70%)",
      len(fl) == 1 and fl[0][0] == "2024-02-01" and abs(fl[0][1] + 0.75) < 1e-12, fl)
nxt = run([3.0, 3.0, 3.0, 2.25, 2.1, 2.1, 2.1, 2.1], 0.7 / 3, "next_close")          # the next day falls to -30%
fn = leverage.fill_losses(nxt, pe, nxt.attrs["early_resets"])
check("fill_losses, next-close fill: the fill waits a day while the index reaches -30%: a fund loss of 3 x 30% = 90%",
      len(fn) == 1 and fn[0][0] == "2024-02-02" and abs(fn[0][1] + 0.90) < 1e-12, fn)
check("fill_losses: the base of an early reset is the last reset before it (a second fall after an early reset counts from the new base)",
      [round(x, 12) for _, x in leverage.fill_losses(pd.Series([1.0, 1.0, 0.5, 0.25], index=ix[:4]), np.array([0, 1, 0, 0], bool),
                                                      ["2024-01-31", "2024-02-01"])] == [-0.5, -0.5])
check("era_of: a date inside a key period gets its label; one outside gets None",
      leverage.era_of("2008-10-10", study.KEY_PERIODS) == "2008-09" and leverage.era_of("1995-06-01", study.KEY_PERIODS) is None)
check("era_of BREAK: the first and last day of a period belong to it (2008-01-01 and 2009-12-31); the day after does not",
      leverage.era_of("2008-01-01", study.KEY_PERIODS) == "2008-09" and leverage.era_of("2009-12-31", study.KEY_PERIODS) == "2008-09"
      and leverage.era_of("2010-01-01", study.KEY_PERIODS) is None)

# ================================================================ Part B: the results file
res = json.loads((ROOT / "results" / "three_x.json").read_text(encoding="utf-8"))
m = res["meta"]
check("results: six trigger rules, base 'scaled' at 0.70 / 3", list(m["triggers"]) == ["none", "scaled", "d20", "d25", "d30", "fixed35"]
      and abs(m["triggers"]["scaled"] - 0.7 / 3) < 1e-15 and m["L"] == 3.0)
for name, W in res["worlds"].items():
    D = W["designs"]
    check(f"{name}: one design row per trigger rule and reset (18), one multi-start row per rule, reset and horizon (72)",
          len(D) == 18 and len(W["multi_start"]) == 72)
    check(f"{name}: the 35% rule never resets early at 3x, and on the history it gives the same funds as no trigger",
          W["fixed35_never_fires"] and W["history_none_equals_fixed35"])
    check(f"{name}: with the scaled trigger no design is wiped out, on the history (level fill) or on any simulated decade",
          all(d["terminated"] is None for d in D if d["trigger"] == "scaled")
          and all(r["wiped"] == 0.0 for r in W["montecarlo"] if r["trigger"] == "scaled"))
    check(f"{name}: each designed level-fill loss is -3 x the drop", all(abs(d["designed_level_fill_loss"] + 3 * d["drop"]) < 1e-15
                                                                       for d in D if d["drop"] is not None))
    cs = {(r["cost"], r["product"]): r["cagr"] for r in W["cost_sensitivity"]}
    check(f"{name}: costs only hurt: CAGR falls from no spread to the filed spread to twice it, for every design",
          all(cs[("zero", p)] > cs[("nport", p)] > cs[("double", p)] for (_, p) in cs))
    c13ok = all((c["ratio_10y_median"] is None) == (c["wiped_3x"] is not None) for c in W["c13"]) and all(
        abs(c["ratio_10y_median"] - c["gap10_median_3x"] / c["gap10_median_2x"]) < 1e-12 for c in W["c13"] if c["ratio_10y_median"] is not None)
    check(f"{name}: C13 ratio = 3x gap / 2x gap, and no ratio for a wiped 3x fund", c13ok)
    check(f"{name}: the intraday wipeout test only adds wipeouts (extra rate >= 0)", all(v >= 0 for v in W["intraday_wipe_extra"].values()))
    o = W["overlay"]
    check(f"{name}: the real-fund window runs from the real fund's first bar to the study end", o["last"] == m["study_end"] and o["first"] >= "2009-06-25")
# the qualitative claims of FINDINGS F25 (prose pins cover its numbers)
ms10 = [r for W in res["worlds"].values() for r in W["multi_start"] if r["trigger"] == "scaled" and r["horizon_years"] == 10]
check("F25: with the 23.33% trigger every one of the six 10-year phase-pooled intervals covers zero", len(ms10) == 6 and all(r["noisy"] for r in ms10))
died = [(n, d["reset"]) for n, W in res["worlds"].items() for d in W["designs"] if d["trigger"] == "none" and d["terminated"]]
check("F25: with no trigger exactly three of the six designs die in history", len(died) == 3, died)
f30 = {(n, f["reset"]): f["terminated"] for n, W in res["worlds"].items() for f in W["fills"] if f["trigger"] == "d30" and f["mode"] == "next_close"}
check("F25: with a 30% trigger and the next-close fill, the quarterly designs die (S&P 500 2008-11-20, Nasdaq-100 2001-09-18) "
      "and no other design does", f30[("SPX", "quarterly")] == "2008-11-20" and f30[("NDX", "quarterly")] == "2001-09-18"
      and all(v is None for k, v in f30.items() if k[1] != "quarterly"), f30)
term = {(n, d["trigger"], d["reset"]): d["terminated"] for n, W in res["worlds"].items() for d in W["designs"]}
check("C9: with no trigger the 3x quarterly S&P 500 design is wiped out on 2008-11-20; the 3x monthly and quarterly Nasdaq-100 "
      "designs on 1987-10-26; no weekly design and no S&P 500 monthly design is wiped out",
      term[("SPX", "none", "quarterly")] == "2008-11-20" and term[("NDX", "none", "monthly")] == "1987-10-26"
      and term[("NDX", "none", "quarterly")] == "1987-10-26" and term[("SPX", "none", "weekly")] is None
      and term[("NDX", "none", "weekly")] is None and term[("SPX", "none", "monthly")] is None)
