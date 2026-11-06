"""BACKLOG B17: choosing leverage (calendar_letf/leverage.py) and the sub-2x results (results/sub2x.json).

Part A, planted (made-up data; every expected value from an independent route: a hand computation, Python's own
statistics module, a closed form, or a world built from the kernels with known inputs):
  yearly log returns, the yearly interval, the plateau rule and its break cases, the break-even fee search, the
  break-even fee and the Kelly leverage of a daily fund against the kernel (C10, C14), walk-forward causality, and the
  era test's wiring.
Part B reads results/sub2x.json and checks what must hold in any correct run: the grid, the cost anchor against
results/live_monthly.json, costs only hurt, L = 1 pays no spread and breaks even at a zero fee, each optimum is the
argmax of its own curve and sits on its plateau, and the named rows are rows of the curve.
"""
import json
import math
import statistics

import numpy as np
import pandas as pd

from _harness import ROOT, check, raises, worst_of
from calendar_letf import kernel, leverage, provenance, stats

# ---- A1. yearly log returns: full years only, -inf once wiped out ----
ix = pd.bdate_range("2018-12-31", "2022-06-30")
anchors = {"2018-12-31": 100.0, "2019-12-31": 110.0, "2020-12-31": 99.0, "2021-12-31": 99.0 * 1.25, "2022-06-30": 120.0}
lev = pd.Series(np.nan, index=ix)
for d, v in anchors.items():
    lev[pd.Timestamp(d)] = v
lev = lev.interpolate()
y = leverage.yearly_log_returns(lev)
check("yearly_log_returns: years 2019-2021 only (2018 has no earlier year end, 2022 is partial), each log(end / previous end)",
      sorted(y) == [2019, 2020, 2021] and abs(y[2019] - math.log(1.1)) < 1e-12 and abs(y[2020] - math.log(0.9)) < 1e-12
      and abs(y[2021] - math.log(1.25)) < 1e-12, y)
check("year_end_rows: the last NYSE session of each December (2018-12-31, 2019-12-31, 2020-12-31, 2021-12-31)",
      [str(lev.index[i].date()) for i in leverage.year_end_rows(lev.index)] == ["2018-12-31", "2019-12-31", "2020-12-31", "2021-12-31"])
wiped = lev.copy()
wiped[wiped.index >= pd.Timestamp("2020-06-01")] = 0.0
yw = leverage.yearly_log_returns(wiped)
check("yearly_log_returns: a NAV at 0 gives -inf for the year it dies and every later year", yw[2019] == math.log(1.1)
      and yw[2020] == -math.inf and yw[2021] == -math.inf, yw)

# ---- A2. the yearly interval ----
iv = leverage.mean_interval([1.0, 2.0, 3.0])
check("mean_interval: [1, 2, 3] gives mean 2, se 1/sqrt(3), interval 2 +/- 4.302653 / sqrt(3) (t975 at 2 df)",
      iv["k"] == 3 and iv["mean"] == 2.0 and abs(iv["se"] - 1.0 / math.sqrt(3)) < 1e-15
      and abs(iv["hi"] - (2.0 + 4.302653 / math.sqrt(3))) < 1e-6 and abs(iv["lo"] - (2.0 - 4.302653 / math.sqrt(3))) < 1e-6, iv)
check("mean_interval: a wiped-out year (-inf) gives no interval", math.isnan(leverage.mean_interval([0.1, -math.inf, 0.2])["lo"]))

# ---- A3. the plateau rule ----
Y = {1.0: [0.00, 0.00, 0.00], 1.5: [0.20, 0.00, 0.16], 2.0: [0.30, -0.10, 0.25], 2.5: [0.40, -0.30, 0.20],
     3.0: [0.90, -math.inf, 0.50]}
p = leverage.plateau(Y)
want = {}
for L in (1.0, 1.5, 2.0, 2.5):                                          # the rule by hand, with Python's statistics module
    d = [a - b for a, b in zip(Y[L], Y[2.0])]
    se = statistics.stdev(d) / math.sqrt(len(d)) if any(d) else 0.0
    want[L] = statistics.fmean(d) + se >= 0.0
check("plateau: best L = 2.0 (highest mean 0.15); the wiped 3.0 is listed and never on the plateau; membership as the "
      "rule computed by hand (mean + 1 SE of the paired yearly difference >= 0)",
      p["L_best"] == 2.0 and p["wiped"] == [3.0] and set(p["plateau"]) == {L for L, ok in want.items() if ok} and 3.0 not in p["plateau"],
      (p["plateau"], want))
check("plateau: the hand rule here puts 1.5 and 2.5 on and 1.0 off, so the plateau is 1.5-2.5", p["plateau"] == [1.5, 2.0, 2.5]
      and p["lo"] == 1.5 and p["hi"] == 2.5 and p["contiguous"], p["plateau"])
p2 = leverage.plateau(Y, max_L=2.0)
check("plateau: max_L = 2 searches 1.0-2.0 only; growth still rises from 1.5 to 2.0, so rising_at_top", p2["L_best"] == 2.0
      and max(p2["growth"]) == 2.0 and p2["rising_at_top"], p2)
br = leverage.plateau({1.0: [0.05, 0.05], 1.5: [0.07, -0.15], 2.0: [-0.05, -0.07]})
check("plateau BREAK cases: a difference of mean -0.09 with SE 0.11 is on, one of mean -0.11 with SE 0.01 is off",
      br["L_best"] == 1.0 and br["plateau"] == [1.0, 1.5], br["plateau"])
check("plateau: equal growth goes to the lower L", leverage.plateau({1.0: [0.1, 0.2], 1.5: [0.2, 0.1]})["L_best"] == 1.0)
raises("plateau refuses L values with different years", lambda: leverage.plateau({1.0: [0.1, 0.2], 1.5: [0.1]}), "same years")
raises("plateau refuses when every fund is wiped out", lambda: leverage.plateau({1.0: [-math.inf, 0.1]}), "wiped")

# ---- A4. the break-even fee search ----
lin = leverage.break_even_fee(lambda f: 0.10 - 2.0 * f, 0.04)
quad = leverage.break_even_fee(lambda f: 0.10 - f - 5.0 * f * f, 0.0)
check("break_even_fee: linear 0.10 - 2f against 0.04 gives f = 0.03; quadratic 0.10 - f - 5f^2 gives (sqrt(3) - 1) / 10 (to 1e-7)",
      lin["status"] == "found" and abs(lin["fee"] - 0.03) < 1e-9 and abs(quad["fee"] - (math.sqrt(3.0) - 1.0) / 10.0) < 1e-7, (lin, quad))
check("break_even_fee: the Illinois step keeps the search fast (the quadratic in at most 12 evaluations, to 1e-7)",
      quad["iterations"] <= 12, quad["iterations"])
check("break_even_fee: the answer is on the winning side of the target (growth at the fee >= target)",
      0.10 - quad["fee"] - 5.0 * quad["fee"] ** 2 >= 0.0)
check("break_even_fee: a fund behind even at zero fee -> None; one still ahead at the top of the bracket -> hi",
      leverage.break_even_fee(lambda f: -0.01 - f, 0.0)["fee"] is None
      and leverage.break_even_fee(lambda f: 1.0 - f, 0.0, hi=0.2) == dict(fee=0.2, iterations=2, status="above hi"))
check("break_even_fee BREAK: behind by 1e-13 at zero fee (rounding) -> fee 0; behind by 1e-11 -> None (atol 1e-12)",
      leverage.break_even_fee(lambda f: -1e-13 - f, 0.0)["fee"] == 0.0 and leverage.break_even_fee(lambda f: -1e-11 - f, 0.0)["fee"] is None)

# ---- A5. C10: the kernel's break-even fee of a daily fund against the second-order closed form, at three volatilities ----
n = 252 * 30
dates = pd.bdate_range("1990-01-01", periods=n + 1)
acc_fin = np.diff(dates.values.astype("datetime64[D]").astype(np.int64)) / 360.0
acc_fee = acc_fin * 360.0 / 365.0
RATE, SPREAD = 0.03, 0.01
err, err_pop, err_hit = 0.0, 0.0, 0.0
for i, sd in enumerate((0.005, 0.01, 0.015)):
    r = np.random.default_rng(100 + i).normal(0.0008, sd, n)     # drift high enough that 2x at 1.5% a day still breaks even
    u = pd.Series(100.0 * np.concatenate(([1.0], np.cumprod(1.0 + r))), index=dates)
    target = math.log(u.iloc[-1] / u.iloc[0])
    for L in (1.5, 2.0):
        sp = SPREAD * L

        def g(f, L=L, sp=sp, u=u):
            v = kernel.daily_reset_series(u, RATE, L=L, spread_per_nav=sp, fee=f).iloc[-1]
            return math.log(v) if v > 0 else -math.inf
        be = leverage.break_even_fee(g, target)
        if be["fee"] is None:
            err = worst_of(err, 1.0)
            continue
        k = ((L - 1.0) * RATE + sp) * acc_fin
        so = leverage.break_even_fee_second_order(r, k, acc_fee, L)
        err = worst_of(err, abs(be["fee"] - so))
        yrs = acc_fee.sum()
        mu, s2 = r.mean() * n / yrs, r.var() * n / yrs
        pop = (L - 1.0) * (mu - RATE * 365 / 360) - sp * 365 / 360 - (L * L - 1.0) * s2 / 2.0
        err_pop = worst_of(err_pop, abs(be["fee"] - pop))
        err_hit = worst_of(err_hit, abs(g(be["fee"]) - target))
check("C10: the kernel's break-even fee of a daily fund at 1.5x and 2x matches the second-order formula within 0.05 pp a "
      "year at daily volatility 0.5%, 1% and 1.5% (an independent route)", err < 5e-4, err)
check("C10: and the population form (L-1)(mu - r) - spread - (L^2 - 1) sigma^2 / 2 within 0.25 pp", err_pop < 2.5e-3, err_pop)
check("break_even_fee: at the fee found, the kernel's growth equals the index's (within 1e-5 of log wealth)", err_hit < 1e-5, err_hit)

# ---- A6. C14 with costs: the daily kernel's grid optimum against Kelly's closed form ----
r = np.random.default_rng(14).normal(0.0005, 0.01, 20000)
dates2 = pd.bdate_range("1950-01-02", periods=20001)
u2 = pd.Series(100.0 * np.concatenate(([1.0], np.cumprod(1.0 + r))), index=dates2)
a2 = np.diff(dates2.values.astype("datetime64[D]").astype(np.int64)) / 360.0
for sp_turn in (0.0, 0.01):
    grid = np.round(np.arange(1.0, 6.001, 0.01), 2)
    gr = [math.log(kernel.daily_reset_series(u2, RATE, L=L, spread_per_nav=sp_turn * L, fee=0.01).iloc[-1]) for L in grid]
    Lg = float(grid[int(np.argmax(gr))])
    Lk = leverage.kelly_daily(r, np.full(len(r), RATE), a2, sp_turn)
    check(f"C14: with rate 3% and spread {sp_turn:.0%} per turn, the daily kernel's best L on a 0.01 grid is within 0.06 of "
          f"(sum r - sum (rf + s) a) / sum r^2", 1.0 < Lk < 6.0 and abs(Lg - Lk) < 0.06, (Lg, Lk))

# ---- A7. walk-forward: causal, expanding window ----
yrs = np.arange(2000, 2030)
Yw = {1.0: np.full(30, 0.05), 2.0: np.where(yrs < 2015, 0.10, 0.0)}
wf = leverage.walk_forward(Yw, yrs, 2010, 10)
check("walk_forward: 2010 and 2020 choose 2.0 (earlier means 0.10 and 0.075 beat 0.05); hold means 0.05 and 0.0; chain 0.025",
      [r["L"] for r in wf["rows"]] == [2.0, 2.0] and abs(wf["rows"][0]["growth"] - 0.05) < 1e-12 and wf["rows"][1]["growth"] == 0.0
      and abs(wf["chain"]["growth"] - 0.025) < 1e-12 and wf["chain"]["years"] == 20 and wf["chain"]["first_year"] == 2010, wf)
Yc = {1.0: Yw[1.0], 2.0: np.where((yrs >= 2010) & (yrs < 2020), -1.0, Yw[2.0])}
wfc = leverage.walk_forward(Yc, yrs, 2010, 10)
check("walk_forward is causal: a crash in the hold years 2010-2019 does not change the 2010 choice, only the next one",
      wfc["rows"][0]["L"] == 2.0 and wfc["rows"][1]["L"] == 1.0, [r["L"] for r in wfc["rows"]])
check("best_L: a fund with a wiped-out year inside the window is never chosen; when every fund is wiped, None",
      leverage.best_L({1.0: np.full(3, 0.01), 2.0: np.array([0.5, -math.inf, 0.5])}, np.arange(3), np.ones(3, bool), (1.0, 2.0)) == 1.0
      and leverage.best_L({1.0: np.array([0.1, -math.inf]), 2.0: np.array([-math.inf, 0.2])}, np.arange(2), np.ones(2, bool), (1.0, 2.0)) is None)
check("walk_forward: a decision with fewer than 10 earlier years is skipped (2005 has 5), so the first is 2015",
      [r["decision"] for r in leverage.walk_forward(Yw, yrs, 2005, 10)["rows"]] == [2015, 2025])

# ---- A8. the era test's wiring ----
ya = {1.5: np.array([0.1, 0.2, 0.0, 0.3, -0.1, 0.05]), 2.0: np.array([0.2, 0.1, 0.1, 0.0, 0.1, 0.2])}
ye = np.arange(1990, 1996)
z = leverage.era_split_z(ya, ye, 1993, 1.5, 2.0)
dd = ya[1.5] - ya[2.0]
check("era_split_z: equals stats.era_difference_z on the yearly difference sliced by hand at the split (lags 0, 1, 2)",
      all(abs(z[L] - stats.era_difference_z(dd[:3], dd[3:], L)) < 1e-15 for L in (0, 1, 2)), z)

# ================================================================ Part B: the results file
res = json.loads((ROOT / "results" / "sub2x.json").read_text(encoding="utf-8"))
m = res["meta"]
check("results: the grid is 1.00-3.00 in 0.05 steps (41 L) and the named points are 1.2, 1.5, 1.7",
      m["grid"] == [round(1 + 0.05 * i, 2) for i in range(41)] and m["named"] == [1.2, 1.5, 1.7])
lm_path = ROOT / "results" / "live_monthly.json"
lm = json.loads(lm_path.read_text(encoding="utf-8"))
turns = [f["spread_per_turn"] for f in lm["fits"] if f["reset"] == "monthly" and f["label"] == "primary"]
check("results: the B19 cost anchor is the median per-turn residual of the primary monthly fits in the CURRENT "
      "results/live_monthly.json (same file hash), x 2 turns",
      m["b19_anchor"]["sha256"] == provenance.sha256_of(lm_path) and abs(m["b19_anchor"]["per_turn"] - float(np.median(turns))) < 1e-15
      and abs(m["cost_cases"]["b19"]["spread_per_nav_2x"] - 2 * float(np.median(turns))) < 1e-15, m["b19_anchor"]["per_turn"])
check("results: the multiple-testing count is 41 x (3 x 3 + 1) x 4", m["n_variants_per_index"] == 41 * 10 * 4)
for name, W in res["worlds"].items():
    cur = W["curve"]
    check(f"{name}: one curve row per variant (41 L x 10 designs x (4 notional + 2 borrowed cost cases))", len(cur) == 41 * 10 * 6, len(cur))
    G = {(c["basis"], c["cost"], c["reset"], c["trigger"], c["L"]): c for c in cur}
    worst, bad = 0.0, []
    for (basis, cost, reset, trig, L), c in G.items():
        if basis != "notional" or cost != "spread0" or L == 1.0:
            continue
        chain = [G[(basis, k, reset, trig, L)]["growth"] for k in ("spread0", "b19", "base", "double")]
        if None not in chain and not all(a > b for a, b in zip(chain, chain[1:])):
            bad.append((reset, trig, L))
    check(f"{name}: costs only hurt: above 1x, growth falls strictly from no spread to the B19 anchor to the base to double", not bad, bad[:5])
    spread1 = 0.0
    for (b, k, r_, t, L), c in G.items():
        if L == 1.0:
            spread1 = worst_of(spread1, abs(c["growth"] - G[("notional", "spread0", r_, t, 1.0)]["growth"]))
    check(f"{name}: at L = 1 there is no swap, so within each design every cost case and basis gives the same growth (to 1e-12)",
          spread1 < 1e-12, spread1)
    be1 = [b["fee"] for b in W["break_even"] if b["L"] == 1.0]
    check(f"{name}: at L = 1 the fund is the index less its fee, so the break-even fee is 0 (below 1e-6) for every design",
          all(f is not None and f < 1e-6 for f in be1), be1)
    worst, n_opt = 0.0, 0
    for o in W["optimum"]:
        for scope, max_L in (("under2", 2.0), ("to3", 3.0)):
            s = o[scope]
            g = {L: G[(o["basis"], o["cost"], o["reset"], o["trigger"], L)]["growth"] for L in m["grid"] if L <= max_L + 1e-12}
            alive = {L: v for L, v in g.items() if v is not None}
            arg = max(alive, key=lambda L: (alive[L], -L))
            n_opt += int(arg == s["L_best"] and s["plateau_lo"] <= s["L_best"] <= s["plateau_hi"] and s["L_best"] in s["plateau"])
            worst = worst_of(worst, abs(alive[arg] - s["growth_best"]))
    check(f"{name}: every best L is the argmax of its own curve's growth and lies on its plateau ({2 * len(W['optimum'])} optima)",
          n_opt == 2 * len(W["optimum"]) and worst < 1e-15, (n_opt, worst))
    nm_ok = all(abs(r["cagr"] - G[("notional", r["cost"], r["reset"], r["trigger"], r["L"])]["cagr"]) < 1e-15
                and abs(r["cagr_borrowed"] - G[("borrowed", r["cost"], r["reset"], r["trigger"], r["L"])]["cagr"]) < 1e-15 for r in W["named"])
    check(f"{name}: every named row is a row of the curve (both bases)", nm_ok)
    c10r = [b for b in W["break_even"] if b["reset"] == "daily" and b["fee"] is not None and 1.0 < b["L"] <= 2.0]
    check(f"{name}: the C10 summary is the largest |kernel - second-order| break-even fee over the daily rows 1 < L <= 2",
          W["c10"]["n"] == len(c10r) and W["c10"]["max_abs_diff_under2"] == max(abs(b["fee"] - b["second_order"]) for b in c10r))
    nb = [r for r in W["named"] if "break_even_interval" in r]
    check(f"{name}: each named break-even interval is the base fee plus the yearly fund-minus-index interval, and holds its own approximation",
          len(nb) == 4 * 4 * 2 and all(abs(r["break_even_interval"]["lo"] - (m["fee_base"] + r["minus_index_yearly"]["lo"])) < 1e-15
                                     and r["break_even_interval"]["lo"] <= r["break_even_approx"] <= r["break_even_interval"]["hi"] for r in nb))
    # the qualitative claims of FINDINGS F23 (prose pins cover its numbers)
    check(f"{name} (F23): no fund at or under 2x is wiped out, on any basis, cost case or trigger rule",
          all(c["terminated"] is None for c in cur if c["L"] <= 2.0))
    check(f"{name} (F23): on the bad-case and risk objectives the best L is 1.00 in every design and range",
          all(o[s]["L_best_p5"] == 1.0 and o[s]["L_best_ratio"] == 1.0 for o in W["optimum"] for s in ("under2", "to3")))
    b1 = [o[s]["best_minus_1x"] for o in W["optimum"] for s in ("under2", "to3") if "best_minus_1x" in o[s]]
    check(f"{name} (F23): no interval of the best L against 1x excludes zero ({len(b1)} intervals)",
          len(b1) > 0 and all(iv["lo"] <= 0.0 <= iv["hi"] for iv in b1))
    check(f"{name} (F23, README): the 1.2x weekly design at 0.99% grew less than the index at both cost anchors",
          all(r["cagr"] < W["index"]["cagr"] for r in W["weeklypay"]) and len(W["weeklypay"]) == 2)
    check(f"{name} (F23): at the Tradr anchor a 1.2x fund trails the index even with no fee, for every reset (notional basis)",
          all(b["fee"] is None for b in W["break_even"] if b["L"] == 1.2 and b["cost"] == "base" and b["basis"] == "notional"))
    clear = [r["cost"] for r in W["weeklypay"] if r["minus_index_yearly"]["hi"] < 0.0 or r["minus_index_yearly"]["lo"] > 0.0]
    check(f"{name} (F23): of the 1.2x weekly shortfalls, only the Tradr-anchor one on the S&P 500 has an interval that excludes zero",
          clear == (["base"] if name == "SPX" else []), clear)
    check(f"{name}: wipe_first_L is the lowest L of each design's wipeouts", all(
        v == min(x["L"] for x in W["wipeouts_base"] if f"{x['reset']}/{x['trigger']}" == k) for k, v in W["wipe_first_L"].items()))
    zs = [abs(z) for o in W["out_of_sample"] if o["era_z"] for z in o["era_z"].values() if z is not None]
    check(f"{name} (F23): the era test finds no change in the best L (every |z| below 1.96)", all(z < 1.96 for z in zs), max(zs, default=0))
    if name == "NDX":
        pl = [(o["cost"], o["reset"], o["trigger"], o["under2"]["plateau_lo"], o["under2"]["plateau_hi"]) for o in W["optimum"]
              if o["basis"] == "notional" and o["cost"] in ("b19", "base")]
        check("NDX (F23): at both cost anchors the plateau at or under 2x spans 1.00 to 2.00 in every design",
              all(lo == 1.0 and hi == 2.0 for *_, lo, hi in pl), [p for p in pl if (p[3], p[4]) != (1.0, 2.0)])
    if name == "SPX":
        rising = [o["reset"] for o in W["optimum"] if o["basis"] == "notional" and o["cost"] == "b19" and o["trigger"] in ("-", "scaled", "none")
                  and o["under2"]["L_best"] == 2.0 and o["under2"]["rising_at_top"]]
        check("SPX (F23): at the B19 anchor the daily, weekly and monthly curves still rise at 2x (best L 2.00)",
              {"daily", "weekly", "monthly"} <= set(rising), rising)
    c13_ok = all(abs(x["ratio"] - x["gap_log"] / c["gap_2x_log"]) < 1e-12 for c in W["c13"] for x in c["rows"] if x["ratio"] is not None)
    check(f"{name}: C13 ratio = the gap at L / the gap at 2x, and the prediction is L(L-1)/2",
          c13_ok and all(abs(x["predicted"] - x["L"] * (x["L"] - 1) / 2) < 1e-15 for c in W["c13"] for x in c["rows"]))
