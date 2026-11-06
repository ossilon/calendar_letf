"""BACKLOG B11: the Monte Carlo machinery (calendar_letf/montecarlo.py) and its results (results/montecarlo.json).

Part A, planted (made-up data; each expected value from an independent route: a hand computation, the original level
series, kernel.run on the same path, a closed form): block starts and picks, the path builder, the batch kernel against
kernel.run, the AR(1) law, the variance ratio, the bridge, the summary statistics and the coverage of their intervals.
Part B reads results/montecarlo.json and checks what must hold in any correct run.
"""
import json
import math

import numpy as np
import pandas as pd

from _harness import ROOT, check, raises, worst_of
from calendar_letf import coverage, kernel, metrics, montecarlo as mc, periods, products, study

# ---- A1. block starts and picks ----
check("block_starts: a history of 10 days and blocks of 4 gives starts 0..6",
      list(mc.block_starts(10, 4)) == [0, 1, 2, 3, 4, 5, 6])
allowed = np.array([1, 1, 1, 0, 1, 1, 1, 1, 0, 1], dtype=bool)
check("block_starts with allowed days: only blocks wholly inside allowed days (blocks of 3: starts 0, 4, 5)",
      list(mc.block_starts(10, 3, allowed)) == [0, 4, 5], list(mc.block_starts(10, 3, allowed)))
raises("block_starts refuses a block longer than the history", lambda: mc.block_starts(5, 6), "does not fit")
starts = mc.block_starts(1000, 21)
pk = mc.block_pick(np.random.default_rng(3), starts, 21, 100, 7)
inside = all(np.all(np.diff(pk[p, k:k + 21]) == 1) for p in range(7) for k in range(0, 100 - 21, 21))
check("block_pick: shape (paths, days); inside each block the history days run consecutively; every block starts at an allowed start",
      pk.shape == (7, 100) and inside and np.isin(pk[:, ::21], starts).all())
check("block_pick: the same seed gives the same picks; another seed does not",
      np.array_equal(pk, mc.block_pick(np.random.default_rng(3), starts, 21, 100, 7))
      and not np.array_equal(pk, mc.block_pick(np.random.default_rng(4), starts, 21, 100, 7)))

# ---- A2. history and path building: copying the history in order gives the history back ----
ix = pd.bdate_range("2015-12-31", periods=600)
rng = np.random.default_rng(11)
u = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, 600))), index=ix)
trig = u * 0.98
low = trig * (1.0 - rng.uniform(0.0, 0.02, 600))
rate = pd.Series(rng.uniform(0.0, 0.05, 600), index=ix)
h = mc.history(u, trig, low, rate)
check("history: one entry per day with a move; the rate and the low ratio come from the SAME day as the move",
      len(h["lr_u"]) == 599 and h["rate"][0] == rate.iloc[1] and abs(h["low_ratio"][5] - low.iloc[6] / trig.iloc[6]) < 1e-15
      and (h["low_ratio"] <= 1.0).all())
U, T, TL, R = mc.build_paths(h, np.arange(599)[None, :])
check("build_paths: a path that copies every history day in order IS the history (levels over the first, to 1e-12)",
      np.max(np.abs(U[0] - (u / u.iloc[0]).values)) < 1e-12 and np.max(np.abs(T[0] - (trig / trig.iloc[0]).values)) < 1e-12
      and np.max(np.abs(TL[0, 1:] - (low / trig.iloc[0]).values[1:])) < 1e-12 and np.array_equal(R[0, 1:], rate.values[1:]))
Us, Ts, *_ = mc.build_paths(h, np.arange(599)[None, :], shift=0.001)
check("build_paths: a shift of 0.001 a day lowers the final log level of the underlying AND of the trigger by exactly 599 x 0.001",
      abs(math.log(U[0, -1]) - math.log(Us[0, -1]) - 0.599) < 1e-12 and abs(math.log(T[0, -1]) - math.log(Ts[0, -1]) - 0.599) < 1e-12)

# ---- A3. the batch kernel against kernel.run, path by path ----
cal = ix
af, ae = periods.accrual_fraction(cal, 360), periods.accrual_fraction(cal, 365)
picks = mc.block_pick(np.random.default_rng(5), mc.block_starts(599, 63), 63, 599, 6)
U, T, TL, R = mc.build_paths(h, picks)
base = products.PRODUCTS["HYP_SPX_M"]
specs = [(products.PRODUCTS["SPYQ"], study.ENCODINGS["rate"]), (base, study.ENCODINGS["fixed"]),
         (products.at_leverage(base, 1.5, "none"), study.encoding_at(study.ENCODINGS["fixed"], 1.5)),
         (products.twin_of(base), study.ENCODINGS["fixed"]), (products.PRODUCTS["HYP_SPX_W"], study.ZERO_COSTS)]
kw = dict(period_end=np.array([periods.period_end_flags(cal, s.reset) if s.reset != "daily" else np.zeros(len(cal), bool) for s, _ in specs]),
          L=np.array([s.L for s, _ in specs]), spread=np.array([study.kernel_kwargs(s, e)["spread_per_nav"] for s, e in specs]),
          fee=np.array([e.fee if e.fee is not None else s.fee for s, e in specs]), drop=np.array([s.early_drop or 0.0 for s, _ in specs]),
          rate_mult=np.array([e.rate_turns for _, e in specs]), daily=np.array([s.reset == "daily" for s, _ in specs]))
U[3, 300:] *= 0.4                                                       # one path crashes, so the triggers fire
T[3, 300:] *= 0.4
TL[3, 300:] *= 0.4
ck = np.arange(len(cal), dtype=np.int64)
navc, mdd, early, term = mc.simulate_batch(U, T, TL, R, af, ae, checkpoints=ck, **kw)
err, ok_meta = 0.0, True
for p in range(6):
    for k, (s, e) in enumerate(specs):
        d = s.reset == "daily"
        nav = kernel.run(s, pd.Series(U[p], index=cal), study.scaled_rate(pd.Series(R[p], index=cal), e),
                         trigger=None if d else pd.Series(T[p], index=cal), trigger_low=None if d else pd.Series(TL[p], index=cal),
                         **study.kernel_kwargs(s, e))
        err = worst_of(err, float(np.max(np.abs(nav.values - navc[p, k]))))
        ok_meta &= abs(mdd[p, k] - metrics.max_drawdown(nav)) < 1e-12 and early[p, k] == len(nav.attrs["early_resets"])
        ok_meta &= (term[p, k] < 0) == (nav.attrs["terminated"] is None)
check("simulate_batch: every NAV equals kernel.run on the same path (calendar with trigger and lows, 1.5x, daily twin, "
      "rate turns 1.3, zero cost) to 1e-12 (the second implementation)", err < 1e-12, err)
check("simulate_batch: the drawdown equals metrics.max_drawdown, the early-reset count and the wipeout match kernel.run's attrs",
      ok_meta and early[3].sum() > 0, early[3])

# ---- A4. the AR(1) law and its variance ratio ----
x = mc.ar1_log_returns(np.random.default_rng(1), 200, 2000, 0.0005, 0.01, -0.1)
xc = x - x.mean()
rho = float(np.sum(xc[:, 1:] * xc[:, :-1]) / np.sum(xc * xc))
check("ar1_log_returns: mean 0.0005, SD 0.01 and lag-1 autocorrelation -0.10, each within its Monte Carlo error (400,000 draws)",
      abs(x.mean() - 0.0005) < 1e-4 and abs(x.std() - 0.01) < 1e-4 and abs(rho + 0.1) < 0.006, (x.mean(), x.std(), rho))
x6 = mc.ar1_log_returns(np.random.default_rng(6), 100, 2000, 0.0, 0.01, 0.6)
check("ar1_log_returns: at phi 0.6 the SD is still 0.01 (the innovations are scaled by sqrt(1 - phi^2)), within 2%",
      abs(x6.std() / 0.01 - 1.0) < 0.02, x6.std())
raises("ar1_log_returns refuses |phi| >= 1", lambda: mc.ar1_log_returns(np.random.default_rng(1), 2, 5, 0.0, 0.01, 1.0), "phi")
vr_closed = lambda phi, T: 1 + 2 * phi / (1 - phi) - 2 * phi * (1 - phi ** T) / (T * (1 - phi) ** 2)   # noqa: E731
check("ar1_variance_ratio: 1 at phi 0, 1 + phi at T = 2, and the closed form 1 + 2phi/(1-phi) - 2phi(1-phi^T)/(T(1-phi)^2) at T = 21, 63",
      mc.ar1_variance_ratio(0.0, 21) == 1.0 and abs(mc.ar1_variance_ratio(0.3, 2) - 1.3) < 1e-15
      and all(abs(mc.ar1_variance_ratio(f, T) - vr_closed(f, T)) < 1e-12 for f in (-0.1, 0.05) for T in (21, 63)))

# ---- A5. the bridge ----
rows, logs = np.array([0, 20, 41, 60]), np.array([0.0, -0.3, -0.1, 0.2])
b = mc.bridge_log_levels(np.random.default_rng(2), 4000, rows, logs, 0.02)
inc = np.diff(b[:, 0:21], axis=1)
check("bridge_log_levels: every path passes exactly through every anchor",
      np.allclose(b[:, rows], logs[None, :], atol=1e-12, rtol=0))
check("bridge_log_levels: inside a 20-day segment the daily steps have mean (anchor change) / 20 and variance sd^2 (1 - 1/20)",
      abs(inc.mean() - (-0.3 / 20)) < 2e-4 and abs(inc.var() / (0.02 ** 2 * (1 - 1 / 20)) - 1.0) < 0.02, (inc.mean(), inc.var()))
raises("bridge_log_levels refuses anchors that do not start at row 0", lambda: mc.bridge_log_levels(np.random.default_rng(2), 2, [1, 5], [0, 1], 0.01), "start at 0")

# ---- A6. statistics of a sample and the coverage of their intervals ----
d = mc.describe([1.0, 2.0, 3.0, -4.0])
check("describe: [1, 2, 3, -4] gives n 4, mean 0.5, SE sd / 2, share above zero 0.75, median 1.5",
      d["n"] == 4 and d["mean"] == 0.5 and abs(d["mean_se"] - np.std([1, 2, 3, -4], ddof=1) / 2) < 1e-15 and d["share_pos"] == 0.75
      and d["median"] == 1.5)
check("describe: NaN values are dropped and counted", mc.describe([1.0, np.nan, 2.0, 3.0])["n_missing"] == 1)
navs = np.array([[1.0, 1.21, 2.0], [2.0, 0.0, 0.0]])
g = mc.cagr_between(navs, 0, 1, 2.0)
check("cagr_between: 1 -> 1.21 over 2 years is 10%; a fund at 0 is -100%; a start at 0 has no CAGR",
      abs(g[0] - 0.1) < 1e-12 and g[1] == -1.0 and np.isnan(mc.cagr_between(np.array([[0.0, 1.0]]), 0, 1, 1.0)[0]))
cov_m, cov_q, true_med = 0, 0, math.exp(-0.01)
rng = np.random.default_rng(8)
for _ in range(400):
    s = rng.lognormal(-0.01, 0.6, 5000) - 1.0                 # skewed, like a ten-year gap or wealth
    dd = mc.describe(s)
    cov_m += dd["mean_lo"] <= math.exp(-0.01 + 0.18) - 1.0 <= dd["mean_hi"]
    cov_q += dd["median_lo"] <= true_med - 1.0 <= dd["median_hi"]
check("describe: on skewed samples of 5,000 (the study's size) the mean +/- 1.96 SE covers the true mean and the median "
      "interval covers the true median in 0.92-0.99 of 400 runs", 0.92 <= cov_m / 400 <= 0.99 and 0.92 <= cov_q / 400 <= 0.99,
      (cov_m / 400, cov_q / 400))

# ---- A7. the calendar of the paths ----
dates = pd.bdate_range("2014-01-02", "2026-09-30")
pc_ = mc.path_calendar(dates, "2026-09-30")
check("path_calendar: from the last session on or before 2016-09-30 to 2026-09-30; month_end_rows gives row 0 plus 120 month ends",
      pc_[0] == pd.Timestamp("2016-09-30") and pc_[-1] == pd.Timestamp("2026-09-30") and len(mc.month_end_rows(pc_)) == 121)
raises("path_calendar refuses an end with no session", lambda: mc.path_calendar(dates, "2026-10-03"), "no session")

# ================================================================ Part B: the results file
res = json.loads((ROOT / "results" / "montecarlo.json").read_text(encoding="utf-8"))
m = res["meta"]
check("results: four block lengths (21, 63, 126, 252), horizons 1, 3, 5, 10 years, 5,000 paths",
      m["blocks"] == [21, 63, 126, 252] and m["horizons_years"] == [1, 3, 5, 10] and m["n_paths"] == 5000)
sub = json.loads((ROOT / "results" / "sub2x.json").read_text(encoding="utf-8"))
from calendar_letf import provenance  # noqa: E402
check("results: the B17 history optimum it quotes comes from the CURRENT results/sub2x.json (same hash)",
      m["sub2x_source"]["sha256"] == provenance.sha256_of(ROOT / "results" / "sub2x.json"))
for name, W in res["worlds"].items():
    bs = W["bootstrap"]
    check(f"{name}: one row per block, cost case, fund and horizon (4 x 2 x 3 x 4 = 96)", len(bs) == 96, len(bs))
    ok = all(r["gap"]["n"] + r["gap"]["n_missing"] == m["n_paths"] and r["gap"]["mean_lo"] < r["gap"]["mean"] < r["gap"]["mean_hi"]
             and r["gap"]["median_lo"] <= r["gap"]["median"] <= r["gap"]["median_hi"]
             and r["gap"]["p5"] <= r["gap"]["p25"] <= r["gap"]["median"] <= r["gap"]["p75"] <= r["gap"]["p95"] for r in bs)
    check(f"{name}: every gap summary counts every path, holds its mean and median inside their intervals, and orders its percentiles", ok)
    F = W["fan"]
    fan_ok = all(F[s][f"p{a}"][c] <= F[s][f"p{b}"][c] + 1e-12 for s in ("cal", "twin", "index") for a, b in ((5, 25), (25, 50), (50, 75), (75, 95))
                 for c in range(len(F["months"]))) and all(F[s]["p50"][0] == 1.0 for s in ("cal", "twin", "index"))
    check(f"{name}: the fan's percentiles are ordered at every month and start at 1", fan_ok and len(F["months"]) == 121)
    c5_ok = all(sum(c["n"] for c in r["cells"]) == m["n_paths"] for r in W["c5"])
    check(f"{name}: C5 puts every path in exactly one of the nine volatility x trend cells", c5_ok and len(W["c5"]) == 12)
    hist = {(o["cost"], o["reset"], s): o[s]["L_best"] for o in sub["worlds"][name]["optimum"]
            if o["basis"] == "notional" and o["trigger"] in ("-", "scaled") for s in ("under2", "to3")}
    ls_ok = all(r["L_p10"] <= r["L_median"] <= r["L_p90"] and r["share_at_1"] + r["share_at_top"] <= 1.0 + 1e-12
                and r["hist_L_best"] == hist[(r["cost"], r["reset"], r["scope"])] for r in W["lstar"])
    check(f"{name}: each best-L distribution is ordered and quotes B17's history optimum for the same design", ls_ok and len(W["lstar"]) == 32)
    mono = all(all(a["log_gap_per_year"]["mean"] > b["log_gap_per_year"]["mean"] for a, b in zip(rows_, rows_[1:]))
               for rows_ in ([r for r in W["mechanism"] if r["reset"] == rs] for rs in ("weekly", "monthly", "quarterly")))
    check(f"{name}: on AR(1) paths the reset gap falls as the lag-1 autocorrelation rises, for every reset (the mechanism of F7)", mono)
    rd = W["real_decade"]
    check(f"{name}: the real decade starts at 1 and its rank among the paths is a share", rd["cal"][0] == 1.0 and 0.0 <= rd["share_of_paths_below"] <= 1.0)
# the qualitative claims of FINDINGS F24 (prose pins cover its numbers)
allrows = [(n, r) for n, W in res["worlds"].items() for r in W["bootstrap"] + W["stress_flat"]["rows"]
           + W.get("stress_rate_shock", {}).get("rows", []) + [x for d in W.get("stress_1929", []) for x in d["rows"]] if "wiped_cal" in r]
check(f"F24: no fund or twin loses all its value on any path of any run ({len(allrows)} ten-year rows)",
      len(allrows) > 0 and all(r["wiped_cal"] == 0.0 and r["wiped_twin"] == 0.0 for _, r in allrows))
q05 = [next(r for r in W["mechanism"] if r["reset"] == "quarterly" and r["phi"] == -0.05) for W in res["worlds"].values()]
check("F24: at an autocorrelation of -0.05 the second-order formula gets the quarterly sign wrong on both indexes",
      all(r["log_gap_per_year"]["mean"] > 0 > r["predicted_per_year"] for r in q05))
C5 = {(n, c["product"], c["horizon_years"]): c for n, W in res["worlds"].items() for c in W["c5"]}
weekly = {"SPX": "HYP_SPX_W", "NDX": "HYP_NDX_W"}
check("F24 (C5): the weekly gaps grow with volatility at every horizon on both indexes (z above 1.96)",
      all(C5[(n, weekly[n], h)]["high_minus_low_vol_z"] > 1.96 for n in weekly for h in (1, 3, 5, 10)))
check("F24 (C5): at 10 years the quarterly gaps shrink with volatility on both indexes (z below -1.96)",
      C5[("SPX", "SPYQ", 10)]["high_minus_low_vol_z"] < -1.96 and C5[("NDX", "QQQP", 10)]["high_minus_low_vol_z"] < -1.96)
check("F24 (C5): the S&P 500 monthly gap grows with volatility at every horizon; the Nasdaq-100 monthly gap at 1 and 3 years only",
      all(C5[("SPX", "HYP_SPX_M", h)]["high_minus_low_vol_z"] > 1.96 for h in (1, 3, 5, 10))
      and all(C5[("NDX", "MQQQ", h)]["high_minus_low_vol_z"] > 1.96 for h in (1, 3))
      and all(C5[("NDX", "MQQQ", h)]["high_minus_low_vol_z"] <= 1.96 for h in (5, 10)))
calm = {(n, p): next(x for x in C5[(n, p, 10)]["cells"] if x["vol_tercile"] == 0 and x["trend_tercile"] == 2)["median"]
        for (n, p, h) in C5 if h == 10}
check("F24 (C5): at 10 years, in the calm strong-uptrend cell, only the S&P 500 weekly design trails its twin",
      [k for k, v in calm.items() if v < 0] == [("SPX", "HYP_SPX_W")], calm)
ls = [r for W in res["worlds"].values() for r in W["lstar"] if r["block"] == 252 and r["cost"] == "b19" and r["scope"] == "under2"]
check("F24 (B17 on paths): at or under 2x the 10th-90th percentile of the best L spans 1.00-2.00 in every design, and the median "
      "is 2.00 in every design but the Nasdaq-100 quarterly one",
      all(r["L_p10"] == 1.0 and r["L_p90"] == 2.0 for r in ls)
      and [r["reset"] for W in res["worlds"].values() for r in W["lstar"] if r in ls and r["L_median"] != 2.0] == ["quarterly"]
      and next(r for r in res["worlds"]["NDX"]["lstar"] if r in ls and r["reset"] == "quarterly")["L_median"] < 2.0)
check("SPX: the stress cases are the flat decade, the rate shock and the 1929-39 bridge at both bracketing rates",
      {"stress_flat", "stress_rate_shock", "stress_1929"} <= set(res["worlds"]["SPX"]) and len(res["worlds"]["SPX"]["stress_1929"]) == 2
      and "stress_rate_shock" not in res["worlds"]["NDX"])
