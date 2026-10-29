"""Planted-answer tests for calendar_letf/coverage.py, the coverage simulation behind ASSUMPTIONS section 7.

Made-up data only; no files needed. The simulation's published numbers are checked in tests/test_stats.py (three cases
recomputed and compared with results/coverage_sim.json); here the building blocks are proved: the synthetic gap series
has the study's overlap structure, the regime component has the stated variance and persistence, the autocorrelation
estimator and the reader of the real gap series give hand-computed answers, and `simulate` reports what it says.
"""
import math
import tempfile
from pathlib import Path

import numpy as np

from _harness import check, raises
from calendar_letf import coverage, stats

# ---- gap_series: the overlap structure ----
check("gap_series: with zero shock sd every gap equals the true constant",
      np.allclose(coverage.gap_series(np.random.default_rng(7), 10, 3, sd=0.0), coverage.TRUE_GAP))
e1 = np.random.default_rng(11).normal(0.0, 0.02, 5)
check("gap_series: h = 1 gives the true gap plus the shock itself",
      np.allclose(coverage.gap_series(np.random.default_rng(11), 5, 1), coverage.TRUE_GAP + e1))
e2 = np.random.default_rng(3101).normal(0.0, 0.02, 801 + 120 - 1)
cs2 = np.concatenate(([0.0], np.cumsum(e2)))
plain = 0.004 + (cs2[120:120 + 801] - cs2[:801]) / 120
check("gap_series: iid shocks reproduce 'normal shocks, cumulative sum, window means' bit for bit at the same seed (the step-10 test's construction)",
      np.array_equal(coverage.gap_series(np.random.default_rng(3101), 801, 120), plain))
e3 = np.random.default_rng(5).normal(0.0, 0.02, 20 + 4 - 1)
g3 = coverage.gap_series(np.random.default_rng(5), 20, 4)
check("gap_series: moving one start on swaps one shock for another: g[s+1] - g[s] = (e[s+4] - e[s]) / 4",
      np.allclose(np.diff(g3), (e3[4:4 + 19] - e3[:19]) / 4))
check("gap_series: the first gap is the true gap plus the mean of the first h shocks", abs(g3[0] - (0.004 + e3[:4].mean())) < 1e-15)
raises("gap_series refuses n = 0", lambda: coverage.gap_series(np.random.default_rng(0), 0, 3), "at least 1")
raises("gap_series refuses a regime share above 1", lambda: coverage.gap_series(np.random.default_rng(0), 10, 3, regime=(0.9, 1.5)), "share")

# ---- regime component: unit variance, autocorrelation phi ----
r9 = coverage.regime_component(np.random.default_rng(1), 200_000, 0.9)
check("regime_component: variance about 1 and lag-1 autocorrelation about phi = 0.9 over 200,000 steps",
      abs(float(r9.var()) - 1.0) < 0.03 and abs(coverage.autocorr(r9, 1) - 0.9) < 0.01, (float(r9.var()), coverage.autocorr(r9, 1)))
check("regime_component: lag-10 autocorrelation about phi^10 = 0.349", abs(coverage.autocorr(r9, 10) - 0.9 ** 10) < 0.02, coverage.autocorr(r9, 10))
check("regime_component: phi = 0 is white noise (lag-1 autocorrelation about 0)",
      abs(coverage.autocorr(coverage.regime_component(np.random.default_rng(2), 100_000, 0.0), 1)) < 0.01)
raises("regime_component refuses phi = 1 (not stationary)", lambda: coverage.regime_component(np.random.default_rng(0), 10, 1.0), "phi")
g_all = coverage.gap_series(np.random.default_rng(4), 50_000, 1, regime=(0.0, 1.0))
check("gap_series regime: share 1 with phi 0 keeps the shock variance at sd^2 (the share re-weights, it does not add variance)",
      abs(float(g_all.var()) / coverage.SHOCK_SD ** 2 - 1.0) < 0.03, float(g_all.var()) / coverage.SHOCK_SD ** 2)
g_iid = coverage.gap_series(np.random.default_rng(9), 20_000, 12)
g_reg = coverage.gap_series(np.random.default_rng(9), 20_000, 12, regime=(0.99, 0.05))
check("gap_series regime: the lag-h autocorrelation of 12-month gaps is about 0 under iid shocks and clearly positive with a 5% persistent share (phi 0.99)",
      abs(coverage.autocorr(g_iid, 12)) < 0.05 and coverage.autocorr(g_reg, 12) > 0.2, (coverage.autocorr(g_iid, 12), coverage.autocorr(g_reg, 12)))

# ---- autocorr: hand-computed ----
# x = 1, 2, 3, 4: mean 2.5, deviations -1.5, -0.5, 0.5, 1.5, sum of squares 5.  lag 1: (-0.5)(-1.5) + (0.5)(-0.5) + (1.5)(0.5) = 1.25 -> 0.25.
# lag 2: (0.5)(-1.5) + (1.5)(-0.5) = -1.5 -> -0.3.  lag 3 leaves one pair: not estimated (NaN).
check("autocorr: x = 1..4 gives 0.25 at lag 1 and -0.30 at lag 2 (hand-computed)",
      abs(coverage.autocorr([1, 2, 3, 4], 1) - 0.25) < 1e-15 and abs(coverage.autocorr([1, 2, 3, 4], 2) + 0.3) < 1e-15)
check("autocorr: a lag that leaves fewer than 2 pairs, lag 0, or a constant series gives NaN",
      math.isnan(coverage.autocorr([1, 2, 3, 4], 3)) and math.isnan(coverage.autocorr([1, 2, 3, 4], 0)) and math.isnan(coverage.autocorr([2, 2, 2, 2], 1)))

# ---- measured_persistence: a square wave with period 24 read from a CSV in the raw layout ----
# g_s = +1 for s mod 24 < 12, else -1, n = 48, h = 12 (horizon 1 year): mean 0, sum of squares 48.
# lag 12: every pair has opposite sign: -36 / 48 = -0.75.  lag 24: 24 equal pairs: +0.5.  lag 36: 12 opposite pairs: -0.25.
# se if independent = 1 / sqrt(48 / 12) = 0.5.  The rows are written out of order to prove the reader sorts by start date.
with tempfile.TemporaryDirectory() as tmp:
    rows = []
    for s in range(48):
        y, m = 2000 + s // 12, s % 12 + 1
        rows.append(f"{y}-{m:02d}-28,1,SQ,{1.0 if s % 24 < 12 else -1.0},0,0,0,0,0,0")
    for s in range(30):                                    # a second product with 30 starts and horizon 2 (h = 24): only lag h fits
        y, m = 2000 + s // 12, s % 12 + 1
        rows.append(f"{y}-{m:02d}-28,2,ZZ,{float(s % 2)},0,0,0,0,0,0")
    shuffled = rows[::-1]
    path = Path(tmp) / "multi_start_T_fixed.csv"
    path.write_text("start,horizon_years,product,gap,cal_cagr,twin_cagr,cal_maxdd,twin_maxdd,cal_terminal,twin_terminal\n" + "\n".join(shuffled) + "\n", encoding="utf-8")
    recs = coverage.measured_persistence(path)
    sq = next(r for r in recs if r["product"] == "SQ")
    check("measured_persistence: the square wave reads -0.75 / +0.50 / -0.25 at lags h, 2h, 3h, n = 48, se if independent 0.5",
          abs(sq["acf_lag_1h"] + 0.75) < 1e-12 and abs(sq["acf_lag_2h"] - 0.5) < 1e-12 and abs(sq["acf_lag_3h"] + 0.25) < 1e-12
          and sq["n"] == 48 and sq["h"] == 12 and abs(sq["se_if_independent"] - 0.5) < 1e-15, sq)
    zz = next(r for r in recs if r["product"] == "ZZ")
    check("measured_persistence: a second product is grouped on its own (h = 24 from horizon 2; lags beyond the data give NaN)",
          zz["h"] == 24 and zz["n"] == 30 and math.isfinite(zz["acf_lag_1h"]) and math.isnan(zz["acf_lag_2h"]), zz)

# ---- quantile_interval: the Monte Carlo error of a simulated 95th percentile ----
# n = 400, q = 0.95: n q = 380, sd = sqrt(19) = 4.359, z sd = 8.54, so ranks floor(371.46) = 371 and ceil(388.54) = 389.
check("quantile_interval: x = 1..400 (shuffled) gives the order statistics at ranks 371 and 389 (hand-computed)",
      coverage.quantile_interval(np.random.default_rng(0).permutation(np.arange(1.0, 401.0))) == (371.0, 389.0))
# Independent route 1: the exact binomial probability that the true quantile falls between those order statistics.
log_pmf = lambda n, b, q: math.lgamma(n + 1) - math.lgamma(b + 1) - math.lgamma(n - b + 1) + b * math.log(q) + (n - b) * math.log(1 - q)
exact400 = sum(math.exp(log_pmf(400, b, 0.95)) for b in range(371, 389))
check("quantile_interval: exact binomial coverage at n = 400 is P(371 <= B <= 388) = 0.962, at or above the nominal 0.95",
      0.95 <= exact400 < 0.97, exact400)
# Independent route 2: simulate. Uniform(0, 1) draws have a 95th percentile of exactly 0.95.
u = np.random.default_rng(21).random((4000, 400))
hits = sum(lo <= 0.95 <= hi for lo, hi in (coverage.quantile_interval(row) for row in u))
check("quantile_interval: 4,000 samples of 400 uniforms cover the true 0.95 quantile at the exact binomial rate (within 3 Monte Carlo SE)",
      abs(hits / 4000 - exact400) < 3 * math.sqrt(exact400 * (1 - exact400) / 4000), (hits / 4000, exact400))
check("quantile_interval: with 20 draws the 95th percentile has no upper bound (rank 21 > 20 gives +inf), and the 5th no lower bound",
      coverage.quantile_interval(np.arange(20.0))[1] == math.inf and coverage.quantile_interval(np.arange(20.0), q=0.05)[0] == -math.inf)
# Boundaries of the two guards: n = 100, q = 0.95 gives r = floor(95 - 4.27) = floor(90.73) = 90 (rounding outward, not
# to 90.73's nearest 91) and s = ceil(95 + 4.27) = 100 = n exactly; n = 120, q = 0.05 gives r = floor(6 - 4.68) = 1 exactly.
check("quantile_interval: ranks round outward and a rank equal to n or to 1 is still a draw (n = 100: (90, 100); n = 120, q = 0.05: lower end = smallest draw)",
      coverage.quantile_interval(np.arange(1.0, 101.0)) == (90.0, 100.0) and coverage.quantile_interval(np.arange(1.0, 121.0), q=0.05)[0] == 1.0)
raises("quantile_interval refuses an empty sample", lambda: coverage.quantile_interval([]), "empty")

# ---- simulate: shape and the quantities it promises ----
s1 = coverage.simulate(60, 12, seed=1, runs=20, n_boot=200)
check("simulate: the needed multiplier lies inside its own Monte Carlo interval (20 runs: no upper bound)",
      s1["t_needed_pooled_lo"] <= s1["t_needed_pooled"] <= s1["t_needed_pooled_hi"] and s1["t_needed_pooled_hi"] == math.inf, s1)
check("simulate: k = n // block (5), df = smallest phase - 1 (4), t used = t(4) = 2.776, no regime",
      s1["k"] == 5 and s1["df"] == 4 and abs(s1["t_used_pooled"] - stats.t975(4)) < 1e-12 and s1["regime"] is None and s1["runs"] == 20 and s1["n_boot"] == 200, s1)
check("simulate: coverages are shares in [0, 1], SE ratios and the needed multiplier are positive and finite",
      all(0.0 <= s1[k] <= 1.0 for k in ("coverage_bb_mean", "coverage_bb_median", "coverage_pooled"))
      and all(math.isfinite(s1[k]) and s1[k] > 0 for k in ("se_ratio_bb", "se_ratio_pooled", "t_needed_pooled")), s1)
s2 = coverage.simulate(60, 12, seed=1, runs=20, n_boot=200, regime=(0.9, 0.1))
check("simulate: a regime case records phi, share and the half-life ln(0.5) / ln(phi) = 6.58 months",
      s2["regime"]["phi"] == 0.9 and s2["regime"]["share"] == 0.1 and abs(s2["regime"]["half_life_months"] - math.log(0.5) / math.log(0.9)) < 1e-12, s2["regime"])
check("simulate: the same seed gives the same numbers (deterministic)", coverage.simulate(60, 12, seed=1, runs=20, n_boot=200) == s1)
s_phi0 = coverage.simulate(60, 12, seed=1, runs=5, n_boot=50, regime=(0.0, 0.5))
check("simulate: a regime with phi = 0 (white noise, which regime_component accepts) runs and reports a half-life of 0, not a math error",
      s_phi0["regime"]["half_life_months"] == 0.0 and 0.0 <= s_phi0["coverage_pooled"] <= 1.0, s_phi0["regime"])

# ---- acf_null and mc_p_value: the Monte Carlo test behind the persistence claim ----
null = coverage.acf_null(120, 12, seed=3, runs=500)
check("acf_null: 500 sorted, finite draws of the lag-h autocorrelation under iid shocks",
      len(null) == 500 and np.all(np.diff(null) >= 0) and np.all(np.isfinite(null)), (len(null), null[:3]))
check("acf_null: under iid shocks the lag-h autocorrelation of overlapping-window means is negative on average (few windows share one mean) "
      "and its SD is well below the rule of thumb 1 / sqrt(n / h) = 0.316", null.mean() < 0.0 and 0.05 < null.std(ddof=1) < 0.316, (null.mean(), null.std(ddof=1)))
check("acf_null: deterministic for a seed; a regime shifts the distribution up",
      np.array_equal(coverage.acf_null(120, 12, seed=3, runs=500), null) and coverage.acf_null(120, 12, seed=3, runs=500, regime=(0.98, 0.05)).mean() > null.mean())
check("mc_p_value: the share of null draws at or above the observed value: 3 of [1, 2, 3, 4] -> 0.5; 5 -> 0.0; 0 -> 1.0; NaN -> NaN",
      coverage.mc_p_value([1.0, 2.0, 3.0, 4.0], 3.0) == 0.5 and coverage.mc_p_value([1.0, 2.0, 3.0, 4.0], 5.0) == 0.0
      and coverage.mc_p_value([1.0, 2.0, 3.0, 4.0], 0.0) == 1.0 and math.isnan(coverage.mc_p_value([1.0, 2.0], float("nan"))) and math.isnan(coverage.mc_p_value([], 1.0)))
