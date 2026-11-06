"""BACKLOG B14: the compounding decomposition (scripts/run_compounding.py) and results/compounding.json.

Part A, planted: the sum-of-squares helper by hand, the line fit by hand, and the known-answer paths against closed forms
(a steady trend compounds daily to (1 + 2 mu)^n; a pure chop costs the daily fund a fixed amount per pair of days).
Part B checks the results file and the qualitative claims of FINDINGS F28.
"""
import importlib.util
import json

import numpy as np
import pandas as pd

from _harness import ROOT, check

spec_ = importlib.util.spec_from_file_location("run_compounding", ROOT / "scripts" / "run_compounding.py")
RC = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(RC)

# ---- A1. the sums of squares, by hand ----
u = np.array([100.0, 110.0, 99.0, 108.9, 108.9])          # +10%, -10%, +10%, 0%
cuts = np.array([False, False, True, False, False])       # one reset at row 2
ssd, ssp = RC.ss_windows(u, np.array([0]), np.array([4]), cuts)
check("ss_windows: SS_daily = 0.1^2 + 0.1^2 + 0.1^2 + 0 = 0.03; SS_period over (0..2) and (2..4) = (-0.01)^2 + 0.1^2 = 0.0101",
      abs(ssd[0] - 0.03) < 1e-12 and abs(ssp[0] - (0.0001 + 0.01)) < 1e-12, (ssd, ssp))
f = RC.fit_line(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0]))
check("fit_line: y = x gives slope 1, R^2 1 and zero error", abs(f["slope"] - 1) < 1e-15 and abs(f["r2_identity"] - 1) < 1e-15 and f["median_abs_error"] == 0)
check("fit_line: y = 2x gives slope 2 (through the origin) and a median error equal to the median x",
      abs(RC.fit_line(np.array([1.0, 2.0, 3.0]), np.array([2.0, 4.0, 6.0]))["slope"] - 2) < 1e-15
      and RC.fit_line(np.array([1.0, 2.0, 3.0]), np.array([2.0, 4.0, 6.0]))["median_abs_error"] == 2.0)

# ---- A2. known-answer paths against closed forms ----
n = 400
t = np.arange(n + 1)
trend = 100.0 * 1.0005 ** t
check("planted trend: the daily 2x fund compounds to (1 + 2 x 0.0005)^n exactly (to 1e-9)",
      abs(RC.run_on(trend, "daily", 2.0) - 1.001 ** n) < 1e-9)
chop = 100.0 * np.cumprod(np.concatenate(([1.0], np.where(t[1:] % 2 == 1, 1.01, 1 / 1.01))))
pair = (1 + 2 * 0.01) * (1 + 2 * (1 / 1.01 - 1))
check("planted chop: the index ends where it began; the daily 2x fund loses (1.02 x (1 - 2 x 0.0099..))^(n/2) - 1",
      abs(chop[-1] - 100.0) < 1e-9 and abs(RC.run_on(chop, "daily", 2.0) - pair ** (n / 2)) < 1e-9)
check("planted chop: every calendar design loses far less than the daily fund (its periods hold the up and down days together)",
      all(RC.run_on(chop, r, 2.0) > RC.run_on(chop, "daily", 2.0) + 0.01 for r in ("weekly", "monthly", "quarterly")))

# ================================================================ Part B: the results file
res = json.loads((ROOT / "results" / "compounding.json").read_text(encoding="utf-8"))
for name, W in res["worlds"].items():
    rows = W["windows"]
    check(f"{name}: 6 designs (2x and 3x) x 4 horizons", len(rows) == 24)
    check(f"{name}: every trend tercile split covers every window", all(sum(b["n"] for b in r["by_trend"]) == r["n"] for r in rows))
P = {r["path"]: r for r in res["planted"]}
# the qualitative claims of FINDINGS F28
check("F28: in a steady trend the daily fund makes the most and the quarterly the least; in a pure chop the order turns around",
      P["trend +0.05% a day"]["daily"] > P["trend +0.05% a day"]["quarterly"] and P["chop +-1% every other day"]["daily"]
      < P["chop +-1% every other day"]["quarterly"])
check("F28: with reversing days (phi -0.2) every calendar design beats the daily fund; with following days (phi +0.2) none does",
      all(P["AR(1) days, phi -0.2"][r] > P["AR(1) days, phi -0.2"]["daily"] for r in ("weekly", "monthly", "quarterly"))
      and all(P["AR(1) days, phi +0.2"][r] < P["AR(1) days, phi +0.2"]["daily"] for r in ("weekly", "monthly", "quarterly")))
R = {(n, r["product"], r["horizon_years"]): r for n, W in res["worlds"].items() for r in W["windows"]}
check("F28: the second-order formula explains the S&P 500 weekly and monthly 2x gaps (R^2 against y = x at least 0.92 at every horizon)",
      all(R[("SPX", p, h)]["formula"]["r2_identity"] >= 0.92 for p in ("HYP_SPX_W", "HYP_SPX_M") for h in (1, 3, 5, 10)))
check("F28: at 10 years the S&P 500 monthly and the Nasdaq-100 weekly design gain most in the choppiest third of windows and least in "
      "the trending third; QQQP turns that around",
      all((lambda b: b[0]["gap_median"] > b[2]["gap_median"])(R[k]["by_trend"]) for k in (("SPX", "HYP_SPX_M", 10), ("NDX", "HYP_NDX_W", 10)))
      and R[("NDX", "QQQP", 10)]["by_trend"][0]["gap_median"] < R[("NDX", "QQQP", 10)]["by_trend"][2]["gap_median"])
E = {(r["vol"], r["L"], r["reset"]): r for r in res["worked_example"]}
check("F28: in the +50% year the daily 2x fund beats the quarterly at 10% volatility, and the quarterly beats the daily at 40%",
      E[(0.10, 2.0, "daily")]["median"] > E[(0.10, 2.0, "quarterly")]["median"] and E[(0.40, 2.0, "quarterly")]["median"] > E[(0.40, 2.0, "daily")]["median"])
