"""Known-answer and simulation tests for stats.py (R2 step 3): the block bootstrap, the variance ratio, the
autocorrelation test and Bessembinder's prediction.  Made-up data only; no files needed.  Expected numbers are worked
out by hand in the comments; simulation tests use fixed seeds, so they are exact repeats, and their bounds come from
the sampling error of the number of runs.
"""
import json
import math

import numpy as np

from _harness import ROOT, check, raises  # noqa: I001
from calendar_letf import coverage, stats

# ---- the t quantile ----
check("t975: df 1 = 12.7062, df 10 = 2.2281, df 60 = 2.0003 (table values)",
      abs(stats.t975(1) - 12.706205) < 1e-9 and abs(stats.t975(10) - 2.228139) < 1e-9 and abs(stats.t975(60) - 2.000298) < 1e-9)
# scipy-free anchor: the textbook two-sided 97.5% quantiles to 3 decimals. They do not depend on this code or on scipy.
T975_ANCHORS = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
                12: 2.179, 15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 50: 2.009, 60: 2.000,
                10 ** 9: 1.960}    # 10**9 = normal limit


def anchors_agree(f, tol=5e-4):
    return all(abs(f(df) - want) <= tol for df, want in T975_ANCHORS.items())


check("t975 equals the textbook 97.5% quantiles for 18 df (1 to 60; 12.706 ... 2.000) and the normal limit (1.960) to 5e-4, no scipy",
      anchors_agree(stats.t975), {df: stats.t975(df) for df in T975_ANCHORS})
# The check bites: a table with one wrong entry must fail it. Here df 5 carries the df 4 value (2.776 instead of 2.571, off by 0.205):
check("t975 anchor test fails on a table with a wrong entry (df 5 holding the df 4 value 2.776)",
      not anchors_agree(lambda df: 2.776445 if df == 5 else stats.t975(df)))
try:
    from scipy.stats import t as _t
    worst = max(abs(stats.t975(d) - float(_t.ppf(0.975, d))) for d in list(range(1, 400)) + [500, 1000, 5000])
    check("t975 equals scipy.stats.t.ppf(0.975, df) to 1e-5 for every df from 1 to 399 and at 500 / 1000 / 5000 (scipy used only here)",
          worst < 1e-5, worst)
except ImportError:
    print("     info: scipy not installed; t975 compared with its own table only")
check("t975: the multiplier falls toward the normal 1.96 as df grows", stats.t975(5) > stats.t975(30) > stats.t975(200) > 1.9599)
raises("t975: df below 1 is refused", lambda: stats.t975(0.5), "at least 1")

# ---- block bootstrap: shape of the output and edge cases ----
x = np.arange(100, dtype=float)
bb = stats.block_bootstrap_mean(x, block=10, n_boot=500, seed=1)
check("bootstrap: mean, median, n and k = n // block are those of the data (mean 49.5, median 49.5, n 100, k 10)",
      bb["mean"] == 49.5 and bb["median"] == 49.5 and bb["n"] == 100 and bb["k"] == 10, bb)
check("bootstrap: the interval is mean +/- t(k-1) x se exactly (t(9) = 2.2622)",
      abs((bb["hi"] - bb["lo"]) / 2 - stats.t975(9) * bb["se"]) < 1e-12 and abs((bb["hi"] + bb["lo"]) / 2 - bb["mean"]) < 1e-12)
check("bootstrap: the same seed gives the same answer; another seed gives a different se",
      stats.block_bootstrap_mean(x, 10, 500, 1)["se"] == bb["se"] and stats.block_bootstrap_mean(x, 10, 500, 2)["se"] != bb["se"])
const = stats.block_bootstrap_mean(np.full(252, 0.37), block=21)
check("bootstrap: a constant array has se 0 (to rounding, below 1e-15) and lo = hi = the constant to 1e-15",
      const["se"] < 1e-15 and abs(const["lo"] - 0.37) < 1e-15 and abs(const["hi"] - 0.37) < 1e-15, const)
nanx = stats.block_bootstrap_mean(np.r_[x, np.nan, np.nan], block=10, n_boot=200, seed=1)
check("bootstrap: NaN values are dropped (n stays 100)", nanx["n"] == 100 and nanx["mean"] == 49.5)
few = stats.block_bootstrap_mean(np.arange(15, dtype=float), block=10, n_boot=200)
check("bootstrap: fewer than 2 blocks (k = 1) gives no t interval (NaN), not a made-up one", few["k"] == 1 and math.isnan(few["lo"]) and not math.isnan(few["se"]))
check("bootstrap: an empty array gives NaN and n = 0", stats.block_bootstrap_mean(np.array([]))["n"] == 0)
check("covers_zero: [-1, 2] covers; [0.1, 2] does not; NaN counts as covering (an interval that does not exist proves nothing)",
      stats.covers_zero(-1, 2) and not stats.covers_zero(0.1, 2) and stats.covers_zero(float("nan"), 1.0))

# ---- block bootstrap: coverage on simulated data ----
RUNS, N, BLOCK = 400, 252, 21
rng = np.random.default_rng(2026)
cover_t = cover_pct = 0
for i in range(RUNS):
    y = rng.normal(0.0, 1.0, N)
    r = stats.block_bootstrap_mean(y, BLOCK, n_boot=1000, seed=i)
    cover_t += (r["lo"] <= 0.0 <= r["hi"])
    cover_pct += (r["pct_lo"] <= 0.0 <= r["pct_hi"])
cov_t, cov_pct = cover_t / RUNS, cover_pct / RUNS
print(f"     info: iid normal, n = {N}, block {BLOCK}, {RUNS} runs: coverage of the true mean 0: t(k-1) x SE {cov_t:.3f}; percentile {cov_pct:.3f}")
check("bootstrap coverage on iid normal data (400 runs, n 252, block 21): the t(k-1) interval covers between 0.93 and 0.98",
      0.93 <= cov_t <= 0.98, cov_t)
check("bootstrap coverage on iid normal data: the naive percentile interval covers less than the t interval", cov_pct < cov_t, (cov_pct, cov_t))

rng = np.random.default_rng(77)
cover_t = cover_pct = 0
for i in range(RUNS):
    e = rng.normal(0.0, 1.0, N + 100)
    y = np.empty(N + 100)
    y[0] = e[0]
    for j in range(1, N + 100):                              # AR(1), phi = 0.5, true mean 0
        y[j] = 0.5 * y[j - 1] + e[j]
    r = stats.block_bootstrap_mean(y[100:], BLOCK, n_boot=1000, seed=i)
    cover_t += (r["lo"] <= 0.0 <= r["hi"])
    cover_pct += (r["pct_lo"] <= 0.0 <= r["pct_hi"])
cov_t2, cov_pct2 = cover_t / RUNS, cover_pct / RUNS
print(f"     info: AR(1) phi 0.5, n = {N}, block {BLOCK}, {RUNS} runs: coverage: t(k-1) x SE {cov_t2:.3f}; percentile {cov_pct2:.3f}")
check("bootstrap coverage on an AR(1) series (phi 0.5): the naive percentile interval covers less than the t interval", cov_pct2 < cov_t2, (cov_pct2, cov_t2))
check("bootstrap coverage on an AR(1) series: the t interval covers at least 0.90 (blocks of 21 keep most of the dependence)", cov_t2 >= 0.90, cov_t2)

# ---- block bootstrap of the MEDIAN: shape, edge cases, coverage ----
bm = stats.block_bootstrap_median(x, block=10, n_boot=500, seed=1)
check("median bootstrap: median, mean, n and k = n // block are those of the data (median 49.5, mean 49.5, n 100, k 10)",
      bm["median"] == 49.5 and bm["mean"] == 49.5 and bm["n"] == 100 and bm["k"] == 10, bm)
check("median bootstrap: the interval is median +/- t(k-1) x se exactly (t(9) = 2.2622)",
      abs((bm["hi"] - bm["lo"]) / 2 - stats.t975(9) * bm["se"]) < 1e-12 and abs((bm["hi"] + bm["lo"]) / 2 - bm["median"]) < 1e-12 and bm["se"] > 0)
check("median bootstrap: the same seed gives the same answer; another seed gives a different se",
      stats.block_bootstrap_median(x, 10, 500, 1)["se"] == bm["se"] and stats.block_bootstrap_median(x, 10, 500, 2)["se"] != bm["se"])
constm = stats.block_bootstrap_median(np.full(252, 0.37), block=21)
check("median bootstrap: a constant array has se 0 and lo = hi = the constant to 1e-15",
      constm["se"] < 1e-15 and abs(constm["lo"] - 0.37) < 1e-15 and abs(constm["hi"] - 0.37) < 1e-15, constm)
check("median bootstrap: NaN values are dropped (n stays 100)", stats.block_bootstrap_median(np.r_[x, np.nan, np.nan], 10, 200, 1)["n"] == 100)
fewm = stats.block_bootstrap_median(np.arange(15, dtype=float), block=10, n_boot=200)
check("median bootstrap: fewer than 2 blocks gives no t interval (NaN), not a made-up one", fewm["k"] == 1 and math.isnan(fewm["lo"]) and not math.isnan(fewm["se"]))
check("median bootstrap: an empty array gives NaN and n = 0", stats.block_bootstrap_median(np.array([]))["n"] == 0)
# Second implementation: the same resamples written with a plain loop (circular blocks, first n values, np.median of each).
rs = np.random.default_rng(5)
xs = rs.normal(size=60)
loop_rng = np.random.default_rng(3)
loop_starts = loop_rng.integers(0, 60, size=(40, 3))              # n = 60, block 20: 3 blocks per resample
loop_meds = [np.median(np.concatenate([xs[(s + np.arange(20)) % 60] for s in row])[:60]) for row in loop_starts]
check("median bootstrap: the standard error equals a plain-loop reimplementation on the same resamples (n 60, block 20, 40 resamples)",
      abs(stats.block_bootstrap_median(xs, block=20, n_boot=40, seed=3)["se"] - float(np.std(loop_meds, ddof=1))) < 1e-12)

rng = np.random.default_rng(404)
cover_n = cover_s = 0
for i in range(RUNS):
    y = rng.normal(0.0, 1.0, N)                                    # true median 0
    rn = stats.block_bootstrap_median(y, BLOCK, n_boot=1000, seed=i)
    cover_n += (rn["lo"] <= 0.0 <= rn["hi"])
    z = np.exp(rng.normal(0.0, 1.0, N)) - 1.0                      # lognormal shifted by 1: skewed, true median 0
    rsk = stats.block_bootstrap_median(z, BLOCK, n_boot=1000, seed=i)
    cover_s += (rsk["lo"] <= 0.0 <= rsk["hi"])
cov_mn, cov_ms = cover_n / RUNS, cover_s / RUNS
print(f"     info: median interval coverage, n = {N}, block {BLOCK}, {RUNS} runs: iid normal {cov_mn:.3f}; skewed (lognormal - 1) {cov_ms:.3f}")
check("median bootstrap coverage on iid normal data (400 runs, n 252, block 21): the interval covers between 0.92 and 0.98", 0.92 <= cov_mn <= 0.98, cov_mn)
check("median bootstrap coverage on skewed data (lognormal - 1, true median 0): the interval covers between 0.92 and 0.98", 0.92 <= cov_ms <= 0.98, cov_ms)

# ---- phase-pooled interval from non-overlapping windows ----
# g = 0..11 with step 6: the 6 phases are {p, p + 6}, p = 0..5.  Phase means 3..8 (average 5.5); each phase has k = 2 and
# sample variance (6^2)/2 = 18, so SE_p^2 = 9 and the pooled SE = 3; df = 2 - 1 = 1, t = 12.7062; half-width 38.1186.
pp_ = stats.phase_pooled_mean(np.arange(12, dtype=float), 6)
check("phase-pooled mean: g = 0..11, step 6: mean 5.5, se 3, df 1, interval 5.5 +/- 12.7062 x 3",
      abs(pp_["mean"] - 5.5) < 1e-12 and abs(pp_["se"] - 3.0) < 1e-12 and pp_["df"] == 1 and abs(pp_["hi"] - (5.5 + 12.706205 * 3)) < 1e-9
      and pp_["phases"] == 6 and pp_["k_min"] == 2, pp_)
check("phase-pooled mean: no phase interval (+/- 12.7 x 3 around 3..8) excludes zero, so the share is 0", pp_["share_phases_excl_zero"] == 0.0)
cc = stats.phase_pooled_mean(np.full(40, 2.0), 10)
check("phase-pooled mean: a constant gap of 2 has se 0 and every phase excludes zero", cc["se"] < 1e-15 and abs(cc["lo"] - 2.0) < 1e-15 and abs(cc["hi"] - 2.0) < 1e-15 and cc["share_phases_excl_zero"] == 1.0, cc)
check("phase-pooled mean: step larger than the data gives no phases (NaN, not a crash)", stats.phase_pooled_mean(np.arange(5.0), 12)["phases"] == 0)
# Unequal phases, the path the real data takes (6 and 7 windows on the S&P, 3 and 4 on the Nasdaq-100).  g = 0..12 with step 6:
# phase 0 = {0, 6, 12} (k = 3, mean 6, sample variance 36, SE_p^2 = 12); phases 1..5 = {p, p + 6} (k = 2, means 4..8, variance 18,
# SE_p^2 = 9).  Pooled mean = (6 + 4 + 5 + 6 + 7 + 8) / 6 = 6; SE^2 = (12 + 5 x 9) / 6 = 9.5; df = 2 - 1 = 1; k_min 2, k_max 3.
pu_ = stats.phase_pooled_mean(np.arange(13, dtype=float), 6)
check("phase-pooled mean, unequal phases: g = 0..12, step 6: mean 6, se sqrt(9.5) = 3.0822, df 1, k 2-3, 6 phases",
      abs(pu_["mean"] - 6.0) < 1e-12 and abs(pu_["se"] - math.sqrt(9.5)) < 1e-12 and pu_["df"] == 1 and pu_["k_min"] == 2 and pu_["k_max"] == 3
      and pu_["phases"] == 6 and abs(pu_["lo"] - (6.0 - 12.706205 * math.sqrt(9.5))) < 1e-8, pu_)


def _pooled_plain(g, step):
    """Second, independent implementation of the phase-pooled interval: plain Python loops, no numpy statistics.
    Phase p holds g[p], g[p + step], ...; phases with fewer than 2 finite values are skipped; mean = average of the phase
    means; SE^2 = average over phases of s_p^2 / k_p (s_p^2 with k_p - 1 in the denominator); df = smallest k_p - 1."""
    phases = []
    for p in range(int(step)):
        vals = [float(v) for v in g[p::int(step)] if v == v]
        if len(vals) >= 2:
            phases.append(vals)
    means = [sum(v) / len(v) for v in phases]
    ses2 = [sum((x - m) ** 2 for x in v) / (len(v) - 1) / len(v) for v, m in zip(phases, means)]
    mean = sum(means) / len(means)
    se = math.sqrt(sum(ses2) / len(ses2))
    df = min(len(v) for v in phases) - 1
    half = stats.t975(df) * se
    return dict(mean=mean, se=se, lo=mean - half, hi=mean + half, df=df, k_min=min(len(v) for v in phases), k_max=max(len(v) for v in phases), phases=len(phases))


rng_pp = np.random.default_rng(2024)
pp_cases = ((801, 120), (381, 120), (465, 36), (909, 12), (25, 12), (13, 6))        # k_p 6/7, 3/4, 12/13, 75/76, 2/3, 2/3
pp_agree = True
for n_, h_ in pp_cases:
    g_ = rng_pp.normal(0.001, 0.02, n_)
    a_, b_ = stats.phase_pooled_mean(g_, h_), _pooled_plain(g_, h_)
    pp_agree &= all(abs(a_[k] - b_[k]) <= 1e-12 * max(1.0, abs(b_[k])) for k in ("mean", "se", "lo", "hi")) and all(a_[k] == b_[k] for k in ("df", "k_min", "k_max", "phases"))
check("phase-pooled mean: equals a plain-loop second implementation to 1e-12 on random data at six (n, step) pairs with unequal phases, incl. the four published shapes", pp_agree)
g_nan = np.arange(13, dtype=float)
g_nan[6] = np.nan
check("phase-pooled mean: a NaN gap is dropped from its phase (phase 0 keeps {0, 12}, k 2), both implementations agree",
      stats.phase_pooled_mean(g_nan, 6)["k_max"] == 2 and abs(stats.phase_pooled_mean(g_nan, 6)["se"] - _pooled_plain(g_nan, 6)["se"]) < 1e-12)

# ---- phase-pooled interval: coverage on gap series with the overlap structure of rolling 120-month windows ----
# The true 10-year gap is the constant GAP_TRUE.  Monthly shocks e_t are iid; the gap at start s is GAP_TRUE plus the MEAN of the
# 120 shocks s .. s + 119, so neighboring starts share 119 of 120 shocks (the structure of rolling 120-month windows).
# 801 starts need 801 + 119 shocks.  Coverage = the share of runs whose interval contains GAP_TRUE.
GAP_TRUE, STARTS, STEP = 0.004, 801, 120
rng = np.random.default_rng(1201)
cover_pp = 0
for i in range(RUNS):
    e = rng.normal(0.0, 0.02, STARTS + STEP - 1)
    cs = np.concatenate(([0.0], np.cumsum(e)))
    g_sim = GAP_TRUE + (cs[STEP:STEP + STARTS] - cs[:STARTS]) / STEP         # mean of the 120 shocks starting at s
    r = stats.phase_pooled_mean(g_sim, STEP)
    cover_pp += (r["lo"] <= GAP_TRUE <= r["hi"])
cov_pp = cover_pp / RUNS
print(f"     info: phase-pooled interval, {STARTS} starts, 120-month windows sharing 119 of 120 shocks, {RUNS} runs: coverage of the true gap {cov_pp:.3f}")
check("phase-pooled coverage on simulated overlapping 120-month windows (400 runs, 801 starts): the interval covers the true constant between 0.88 and 0.99",
      0.88 <= cov_pp <= 0.99, cov_pp)

# ---- the headline configurations: block-bootstrap coverage is BIASED LOW, phase-pooled coverage is not (R2 step 10) ----
# Same series as above (gap at start s = GAP_TRUE + mean of h consecutive iid monthly shocks), now built by calendar_letf/coverage.py
# (`gap_series`; its iid draw reproduces the construction above bit for bit, tests/test_coverage.py), at the three configurations
# first tested in step 10: n = 801 / 381 starts with a 10-year horizon (block 120, k = 6 / 3: the S&P 500 and the Nasdaq-100 rows)
# and n = 909 starts with a 1-year horizon (block 12).  The test DOCUMENTS the bias; it does not hide it: the block-bootstrap
# t(k-1) x SE intervals for the mean and the median cover 0.82 to 0.95, not 0.95.  The cause is block = window length: a block
# bootstrap sees only the dependence inside one block, and for a mean of h shocks blocks of length h lose about a third of the
# variance of the series mean at ANY block count (results/coverage_sim.json, the 201-block case); 3 to 6 blocks lose more on top.
# The phase-pooled interval uses only windows that do not overlap.
# scripts/run_coverage_sim.py runs every published configuration and a regime stress into results/coverage_sim.json; the three
# entries recomputed here (same seeds, same resamples) must equal that file exactly, so the file cannot drift from the code.
# With 400 runs the sampling error of a coverage near 0.95 is 0.011; the 1-year phase-pooled bound is therefore 0.92.
HEADLINE_CONFIGS = ((801, 120, 3101, 0.95), (381, 120, 3102, 0.95), (909, 12, 3103, 0.92))   # n, h (= block), seed, pooled lower bound
SIM_PATH = ROOT / "results" / "coverage_sim.json"
sim = json.loads(SIM_PATH.read_text(encoding="utf-8")) if SIM_PATH.exists() else None
if sim is None:
    print("     skip: results/coverage_sim.json is absent (py scripts\\run_coverage_sim.py writes it); the recomputed entries are checked against their bounds only")
SIM_KEYS = ("coverage_bb_mean", "coverage_bb_median", "coverage_pooled", "se_ratio_bb", "se_ratio_pooled", "t_needed_pooled")
for n_, h_, seed_, pp_lo_bound in HEADLINE_CONFIGS:
    r_ = coverage.simulate(n_, h_, seed_, runs=RUNS, n_boot=1000)
    print(f"     info: headline configuration n = {n_}, block {h_}, k = {r_['k']}, {RUNS} runs: coverage of the true gap: block-bootstrap mean "
          f"{r_['coverage_bb_mean']:.3f}, block-bootstrap median {r_['coverage_bb_median']:.3f}, phase-pooled {r_['coverage_pooled']:.3f}; "
          f"bootstrap SE / true SD of the mean {r_['se_ratio_bb']:.2f}; pooled t needed {r_['t_needed_pooled']:.2f} against t used {r_['t_used_pooled']:.2f}")
    check(f"headline coverage, n = {n_}, block {h_} (400 runs): the block-bootstrap mean and median intervals cover between 0.82 and 0.95 (biased low; documented)",
          0.82 <= r_["coverage_bb_mean"] <= 0.95 and 0.82 <= r_["coverage_bb_median"] <= 0.95, (r_["coverage_bb_mean"], r_["coverage_bb_median"]))
    check(f"headline coverage, n = {n_}, block {h_} (400 runs): the phase-pooled interval covers between {pp_lo_bound:.2f} and 1.00",
          pp_lo_bound <= r_["coverage_pooled"] <= 1.0, r_["coverage_pooled"])
    check(f"headline coverage, n = {n_}, block {h_}: the bootstrap SE is below 0.9 of the true SD of the mean (the cause of the low coverage)",
          0.3 < r_["se_ratio_bb"] < 0.9, r_["se_ratio_bb"])
    if sim is not None:
        entry = next((e for e in sim["iid"] if e["n"] == n_ and e["h"] == h_), None)
        check(f"coverage_sim.json holds the n = {n_}, h = {h_} entry with seed {seed_}, {RUNS} runs and 1,000 resamples",
              entry is not None and entry["seed"] == seed_ and entry["runs"] == RUNS and entry["n_boot"] == 1000,
              None if entry is None else {k: entry[k] for k in ("seed", "runs", "n_boot")})
        if entry is not None:
            check(f"coverage_sim.json n = {n_}, h = {h_}: the shipped coverages, SE ratios and needed multiplier equal the recomputation exactly",
                  all(abs(entry[k] - r_[k]) < 1e-12 for k in SIM_KEYS), {k: (entry[k], r_[k]) for k in SIM_KEYS if abs(entry[k] - r_[k]) >= 1e-12})
if sim is not None:
    iid_ = sim["iid"]
    have_ = sorted((e["world"], e["horizon_years"]) for e in iid_)
    check("coverage_sim: all eight published configurations are present (S&P 500 and Nasdaq-100 at 1, 3, 5 and 10 years)",
          have_ == sorted((w, y) for w in ("NDX", "SPX") for y in (1, 3, 5, 10)), have_)
    check("coverage_sim: under independent months the phase-pooled interval covers at least 0.92 at every published configuration",
          all(e["coverage_pooled"] >= 0.92 for e in iid_), {(e["world"], e["horizon_years"]): e["coverage_pooled"] for e in iid_})
    check("coverage_sim: the block-bootstrap mean and median intervals cover below 0.95 at every published configuration (the documented bias)",
          all(e["coverage_bb_mean"] < 0.95 and e["coverage_bb_median"] < 0.95 for e in iid_),
          {(e["world"], e["horizon_years"]): (e["coverage_bb_mean"], e["coverage_bb_median"]) for e in iid_})
    mech_ = sim["mechanism"]
    check("coverage_sim: with about 200 blocks of 12 the bootstrap SE is still 0.75-0.90 of the truth: block = window length is a cause on its own",
          mech_["k"] >= 150 and 0.75 <= mech_["se_ratio_bb"] <= 0.90, (mech_["k"], mech_["se_ratio_bb"]))
    check("coverage_sim: at ten years the pooled interval is conservative under independent months (the multiplier the sampling distribution needs is below the t used)",
          all(e["t_needed_pooled"] < e["t_used_pooled"] for e in iid_ if e["horizon_years"] == 10),
          {e["world"]: (e["t_needed_pooled"], e["t_used_pooled"]) for e in iid_ if e["horizon_years"] == 10})
    reg_ = sim["regime"]
    check("coverage_sim: the regime stress reaches the persistence measured in the real gap series (a case with lag-h autocorrelation above 0.3)",
          any(e["acf_gap_h"] is not None and e["acf_gap_h"] > 0.3 for e in reg_), max(e["acf_gap_h"] or 0.0 for e in reg_))
    check("coverage_sim: every regime case reports a coverage in [0, 1] and a finite needed multiplier (the limit of the headline interval is measured, not assumed)",
          all(0.0 <= e["coverage_pooled"] <= 1.0 and e["t_needed_pooled"] is not None and math.isfinite(e["t_needed_pooled"]) for e in reg_))
    check("coverage_sim: the code fingerprint in the file names its script", sim["meta"]["code"]["script"] == "run_coverage_sim.py")

# ---- Newey-West long-run variance and the era-difference z (R2 step 12e) ----
# x = 1, 2, 3, 4: mean 2.5, deviations -1.5, -0.5, 0.5, 1.5.  gamma_0 = (2.25 + 0.25 + 0.25 + 2.25) / 4 = 1.25.
# gamma_1 = ((-0.5)(-1.5) + (0.5)(-0.5) + (1.5)(0.5)) / 4 = 1.25 / 4 = 0.3125.  gamma_2 = ((0.5)(-1.5) + (1.5)(-0.5)) / 4 = -0.375.
# L = 1: V = 1.25 + 2 x (1 - 1/2) x 0.3125 = 1.5625.  L = 2: V = 1.25 + 2 x (2/3) x 0.3125 + 2 x (1/3) x (-0.375) = 1.4167.
check("newey_west_variance: L = 0 is the plain variance with 1/n (1.25 for 1..4); L = 1 gives 1.5625; L = 2 gives 1.41667 (hand-computed)",
      abs(stats.newey_west_variance([1, 2, 3, 4], 0) - 1.25) < 1e-15 and abs(stats.newey_west_variance([1, 2, 3, 4], 1) - 1.5625) < 1e-15
      and abs(stats.newey_west_variance([1, 2, 3, 4], 2) - (1.25 + 2 * (2 / 3) * 0.3125 - 2 * (1 / 3) * 0.375)) < 1e-12)


def _nw_plain(x, L):
    """Second implementation: explicit double loop over the autocovariances."""
    x = [float(v) for v in x]
    n, m = len(x), sum(x) / len(x)
    g = [sum((x[t] - m) * (x[t - j] - m) for t in range(j, n)) / n for j in range(0, min(L, n - 1) + 1)]
    return g[0] + 2.0 * sum((1.0 - j / (L + 1.0)) * g[j] for j in range(1, len(g)))


_rx = np.random.default_rng(12).normal(0.0, 1.0, 300)
check("newey_west_variance: equals a plain double-loop implementation to 1e-12 on random data at lags 0, 5, 21, 63 and 400 (lags beyond n - 1 are cut)",
      all(abs(stats.newey_west_variance(_rx, L) - _nw_plain(_rx, L)) < 1e-12 for L in (0, 5, 21, 63, 400)))
check("newey_west_variance: non-negative on 50 random series at lag 21 (Bartlett weights), NaN below 2 values",
      all(stats.newey_west_variance(np.random.default_rng(s).normal(size=120), 21) >= 0.0 for s in range(50))
      and math.isnan(stats.newey_west_variance([1.0], 3)))
# era_difference_z, hand-computed: x1 = 1..4 (mean 2.5, V at L = 1 = 1.5625, above); x2 = 0, 0, 1, 1 (mean 0.5; deviations
# -0.5, -0.5, 0.5, 0.5; gamma_0 = 0.25, gamma_1 = (0.25 - 0.25 + 0.25) / 4 = 0.0625; V = 0.25 + 2 x 0.5 x 0.0625 = 0.3125).
# z = (2.5 - 0.5) / sqrt(1.5625 / 4 + 0.3125 / 4) = 2 / sqrt(0.46875) = 2.921187. A denominator with sqrt(2) too much or too
# little, pooled n, or the plain variance (L = 0: 2 / sqrt(1.25/4 + 0.25/4) = 3.265986) all miss it.
check("era_difference_z: hand case x1 = 1..4, x2 = 0, 0, 1, 1 at lag 1 gives z = 2 / sqrt(0.46875) = 2.921187 exactly; at lag 0 it gives 3.265986",
      abs(stats.era_difference_z([1, 2, 3, 4], [0, 0, 1, 1], 1) - 2.0 / math.sqrt(0.46875)) < 1e-12
      and abs(stats.era_difference_z([1, 2, 3, 4], [0, 0, 1, 1], 0) - 2.0 / math.sqrt(1.25 / 4 + 0.25 / 4)) < 1e-12,
      (stats.era_difference_z([1, 2, 3, 4], [0, 0, 1, 1], 1), stats.era_difference_z([1, 2, 3, 4], [0, 0, 1, 1], 0)))


def _z_plain(a, b, L):
    """Second implementation of the era-difference z, built on the double-loop long-run variance above."""
    a, b = [float(v) for v in a], [float(v) for v in b]
    return (sum(a) / len(a) - sum(b) / len(b)) / math.sqrt(_nw_plain(a, L) / len(a) + _nw_plain(b, L) / len(b))


_ea, _eb = np.random.default_rng(31).normal(0.0, 1.0, 700), np.random.default_rng(32).normal(0.2, 1.5, 500)
check("era_difference_z: equals a plain-loop second implementation to 1e-12 on random eras of unequal size at lags 0, 5, 21 and 63",
      all(abs(stats.era_difference_z(_ea, _eb, L) - _z_plain(_ea, _eb, L)) < 1e-12 for L in (0, 5, 21, 63)))
raises("newey_west_variance refuses a negative lag", lambda: stats.newey_west_variance([1, 2, 3], -1), "lags")
# a planted MA(1): x_t = e_t + 0.5 e_{t-1}, sigma 1: gamma_0 = 1.25, gamma_1 = 0.5, long-run variance 2.25; the Bartlett estimate at
# L = 50 aims at 1.25 + 2 x (50/51) x 0.5 = 2.2304 (the kernel shrinks gamma_1 by 1/51)
_e = np.random.default_rng(3).normal(size=400_001)
_ma = _e[1:] + 0.5 * _e[:-1]
check("newey_west_variance: planted MA(1) with long-run variance 2.25 reads 2.23 (+/- 0.05) at lag 50 on 400,000 points, while the plain variance reads 1.25",
      abs(stats.newey_west_variance(_ma, 50) - 2.2304) < 0.05 and abs(stats.newey_west_variance(_ma, 0) - 1.25) < 0.02,
      (stats.newey_west_variance(_ma, 50), stats.newey_west_variance(_ma, 0)))
_za = np.random.default_rng(5).normal(0.0, 1.0, 10_000)
_zb = np.random.default_rng(6).normal(0.1, 1.0, 10_000)
check("era_difference_z: means 0 and 0.1 with sd 1 and n 10,000 each give z about -7 (below -5); two draws from one law give |z| below 3",
      stats.era_difference_z(_za, _zb, 21) < -5.0 and abs(stats.era_difference_z(_za, np.random.default_rng(7).normal(0.0, 1.0, 10_000), 21)) < 3.0,
      stats.era_difference_z(_za, _zb, 21))
check("era_difference_z: NaN with fewer than 2 values on a side or zero variance", math.isnan(stats.era_difference_z([1.0], [1.0, 2.0], 1)) and math.isnan(stats.era_difference_z([2.0, 2.0], [2.0, 2.0], 1)))

# ---- variance ratio: a hand-computed case ----
# r = [0.01, -0.02, 0.03, 0.00, -0.01, 0.02], T = 6, q = 2.  mu = 0.005; deviations d = [.005, -.025, .025, -.005, -.015, .015].
# sum d^2 = 1750e-6, so sa2 = 1750e-6 / 5 = 350e-6.  Overlapping 2-sums of d: -.02, 0, .02, -.02, 0 -> squares sum 1200e-6;
# m = q (T - q + 1)(1 - q/T) = 2 x 5 x 2/3 = 20/3;  sc2 = 1200e-6 x 3/20 = 180e-6;  VR = 180/350 = 18/35 = 0.514286.
# delta_1 = sum_{t=2}^{6} d_t^2 d_{t-1}^2 / (sum d^2)^2 = (15625 + 390625 + 15625 + 5625 + 50625)e-12 / (1750e-6)^2
#         = 478125 / 3062500 = 0.1561224;  theta = (2 x 1 / 2)^2 x delta_1 = 0.1561224;  z* = (18/35 - 1) / sqrt(theta) = -1.22928.
rr = np.array([0.01, -0.02, 0.03, 0.00, -0.01, 0.02])
v = stats.variance_ratio(rr, 2)
check("variance ratio, 6 returns, q = 2: VR = 18/35 (hand computation)", abs(v["vr"] - 18.0 / 35.0) < 1e-12, v["vr"])
check("variance ratio, 6 returns, q = 2: robust z = (18/35 - 1) / sqrt(478125/3062500) = -1.22928 (hand computation)",
      abs(v["z_robust"] - (18.0 / 35.0 - 1.0) / math.sqrt(478125.0 / 3062500.0)) < 1e-12 and abs(v["z_robust"] + 1.22928) < 1e-4, v)
# homoskedastic z: phi = 2 (2q-1)(q-1) / (3 q T) = 2 x 3 x 1 / 36 = 1/6;  z = (18/35 - 1) / sqrt(1/6) = -1.18977
check("variance ratio, 6 returns, q = 2: homoskedastic z = (18/35 - 1) x sqrt(6) = -1.18977", abs(v["z_homoskedastic"] + 1.18977) < 1e-4, v["z_homoskedastic"])
check("variance ratio: n and q are reported", v["n"] == 6 and v["q"] == 2)
raises("variance ratio: q = 1 is refused", lambda: stats.variance_ratio(rr, 1), "q >= 2")
check("variance ratio: too few returns (T <= q + 1) gives NaN, not a crash", math.isnan(stats.variance_ratio(rr[:3], 2)["vr"]))
check("variance ratio: a constant series gives NaN", math.isnan(stats.variance_ratio(np.full(50, 0.01), 5)["vr"]))


def vr_slow(r, q):
    """Reference implementation: the formulas written with plain loops (not the cumulative-sum shortcut)."""
    T = len(r)
    mu = sum(r) / T
    sa2 = sum((x - mu) ** 2 for x in r) / (T - 1)
    m = q * (T - q + 1) * (1 - q / T)
    sc2 = sum((sum(r[t:t + q]) - q * mu) ** 2 for t in range(T - q + 1)) / m
    ss = sum((x - mu) ** 2 for x in r)
    theta = 0.0
    for j in range(1, q):
        delta = sum((r[t] - mu) ** 2 * (r[t - j] - mu) ** 2 for t in range(j, T)) / ss ** 2
        theta += (2 * (q - j) / q) ** 2 * delta
    return sc2 / sa2, (sc2 / sa2 - 1) / math.sqrt(theta)


rg = np.random.default_rng(3).normal(0.0005, 0.01, 300)
for q in (2, 5, 21):
    a, b = stats.variance_ratio(rg, q), vr_slow(list(rg), q)
    check(f"variance ratio q = {q}: the vectorized code equals the plain-loop reference on 300 random returns (vr and robust z to 1e-10)",
          abs(a["vr"] - b[0]) < 1e-10 and abs(a["z_robust"] - b[1]) < 1e-10, (a, b))

# ---- variance ratio: size under the random walk, power under positive autocorrelation ----
rng = np.random.default_rng(11)
paths, steps = 1000, 2500
rej5 = rej21 = 0
for i in range(paths):
    z = rng.normal(0.0004, 0.01, steps)
    rej5 += abs(stats.variance_ratio(z, 5)["z_robust"]) > 1.96
    rej21 += abs(stats.variance_ratio(z, 21)["z_robust"]) > 1.96
print(f"     info: random walk, {paths} paths x {steps} steps: share with |z_robust| > 1.96: q = 5 {rej5 / paths:.3f}; q = 21 {rej21 / paths:.3f}")
check("variance ratio z (robust) on 1,000 random-walk paths of 2,500 steps, q = 5: |z| > 1.96 in 3-7% of paths", 0.03 <= rej5 / paths <= 0.07, rej5 / paths)
check("variance ratio z (robust) on 1,000 random-walk paths of 2,500 steps, q = 21: |z| > 1.96 in 3-7% of paths", 0.03 <= rej21 / paths <= 0.07, rej21 / paths)

rng = np.random.default_rng(12)
e = rng.normal(0.0, 0.01, 2501)
ma = e[1:] + 0.5 * e[:-1]                                    # MA(1), coefficient +0.5: rho_1 = 0.5 / 1.25 = 0.4, VR(2) = 1 + 0.4 = 1.4
vma = stats.variance_ratio(ma, 2)
check("variance ratio on an MA(1) path with coefficient +0.5: VR(2) near 1.4 (1.3 to 1.5) and z_robust above 8", 1.3 < vma["vr"] < 1.5 and vma["z_robust"] > 8, vma)
check("variance ratio on the same path: VR(21) above 1 (continuation) and z_robust above 3 (theory: 1 + 2 x 0.4 x 20/21 = 1.76)",
      stats.variance_ratio(ma, 21)["vr"] > 1.3 and stats.variance_ratio(ma, 21)["z_robust"] > 3)
neg = e[1:] - 0.5 * e[:-1]
vneg = stats.variance_ratio(neg, 2)
check("variance ratio on an MA(1) path with coefficient -0.5: VR(2) near 0.6 (reversal) and z_robust below -8", 0.5 < vneg["vr"] < 0.7 and vneg["z_robust"] < -8, vneg)

# ---- ar1 ----
a = stats.ar1(np.array([1.0, -1.0, 1.0, -1.0]))
check("ar1: [1, -1, 1, -1] has rho = (-1 -1 -1) / 4 = -0.75 and se = 1/sqrt(4) = 0.5 (hand computation)", abs(a["rho"] + 0.75) < 1e-15 and abs(a["se"] - 0.5) < 1e-15 and abs(a["z"] + 1.5) < 1e-12, a)
rng = np.random.default_rng(5)
n_ar = 6000
ee = rng.normal(0.0, 0.01, n_ar)
yy = np.empty(n_ar)
yy[0] = ee[0]
for j in range(1, n_ar):
    yy[j] = 0.3 * yy[j - 1] + ee[j]
a = stats.ar1(yy)
check("ar1: an AR(1) path with phi 0.3 and 6,000 points gives rho within 0.04 of 0.3, se = 1/sqrt(n), and both z above 10",
      abs(a["rho"] - 0.3) < 0.04 and abs(a["se"] - 1 / math.sqrt(n_ar)) < 1e-15 and a["z"] > 10 and a["z_robust"] > 10, a)
a0 = stats.ar1(rng.normal(0, 0.01, 4000))
check("ar1: iid noise gives |rho| below 4 se", abs(a0["rho"]) < 4 * a0["se"], a0)
from calendar_letf import metrics  # noqa: E402
lvl = np.exp(np.cumsum(rng.normal(0.0003, 0.01, 2001)))
check("ar1 agrees with metrics.lag1_autocorr on 2,000 log returns to within 3/n (the two differ only in how the mean is removed)",
      abs(stats.ar1(np.diff(np.log(lvl)))["rho"] - metrics.lag1_autocorr(lvl)) < 3.0 / 2000)

# ---- Bessembinder's prediction ----
# VR = 1, mu = 0.0004, sigma = 0.01, T = 21:  bracket = C(21,2) mu^2 = 210 x 1.6e-7 = 3.36e-5;  gap = (2 - 4) x 3.36e-5 = -6.72e-5 per month,
# i.e. -0.0067% a month = -0.08 pp a year: the daily fund is ahead by the drift term alone (R1 memo section 3.2).
pg = stats.predicted_reset_gap(0.0004, 0.01, 1.0, 21)
check("predicted gap: VR = 1, mu 0.04%/day, sigma 1%/day, T = 21: -6.72e-5 per month (hand computation), about -0.08 pp a year, sign -1",
      abs(pg["gap_per_period"] + 6.72e-5) < 1e-12 and abs(pg["gap_per_period"] * 12 * 100 + 0.08064) < 1e-9 and pg["sign"] == -1, pg)
check("predicted gap: the crossover VR = 1 - (T-1) mu^2/sigma^2 = 1 - 20 x 1.6e-7 / 1e-4 = 0.968 (R1: 0.968-0.978 monthly)", abs(pg["crossover_vr"] - 0.968) < 1e-12, pg)
at = stats.predicted_reset_gap(0.0004, 0.01, pg["crossover_vr"], 21)
check("predicted gap: exactly zero at the crossover VR", abs(at["gap_per_period"]) < 1e-15, at)
below = stats.predicted_reset_gap(0.0004, 0.01, 0.90, 21)
check("predicted gap: VR = 0.90 puts the calendar fund ahead (sign +1; gap = -2 x (3.36e-5 + 21 x 1e-4 / 2 x (0.90 - 1)) = +2.4e-4)",
      below["sign"] == 1 and abs(below["gap_per_period"] - (-2.0) * (3.36e-5 + 21 * 1e-4 / 2 * (0.90 - 1.0))) < 1e-15, below)

# The expansion against the exact expectation for iid returns: E[e_k] = C(T,k) mu^k exactly, so with beta = 2
# E[calendar - daily] = sum_{k>=2} (beta - beta^k) C(T,k) mu^k.  The expansion keeps k = 2 only; the rest is third order.
mu_, T_ = 0.001, 21
exact = sum((2.0 - 2.0 ** k) * math.comb(T_, k) * mu_ ** k for k in range(2, T_ + 1))
approx = stats.predicted_reset_gap(mu_, 0.0, 1.0, T_)["gap_per_period"]
check("predicted gap (iid, sigma term zero): the second-order value is within 3% of the exact expectation sum (beta - beta^k) C(T,k) mu^k",
      abs(approx / exact - 1.0) < 0.03, (approx, exact))

# Planted MA(1) paths: simulate calendar (buy and hold the 2x position for T days) minus daily (rebalance every day) per period, no costs.
def simulated_gap(theta, mu, sig, T=21, periods=40000, seed=0):
    rng = np.random.default_rng(seed)
    n = T * periods
    e = rng.normal(0.0, sig, n + 1)
    r = mu + e[1:] + theta * e[:-1]
    cal = 1.0 + 2.0 * (np.prod(1.0 + r.reshape(periods, T), axis=1) - 1.0)
    day = np.prod(1.0 + 2.0 * r.reshape(periods, T), axis=1)
    return float(np.mean(cal - day)), r


for theta, label in ((-0.5, "reversals (MA coefficient -0.5)"), (0.5, "continuations (MA coefficient +0.5)")):
    sim, path = simulated_gap(theta, 0.0004, 0.01)
    m_, s_ = float(path.mean()), float(path.std(ddof=1))
    vr_ = stats.variance_ratio(path, 21)["vr"]
    pr = stats.predicted_reset_gap(m_, s_, vr_, 21)
    print(f"     info: {label}: simulated calendar minus daily {sim:+.3e} per month; expansion {pr['gap_per_period']:+.3e} (VR(21) {vr_:.3f})")
    check(f"planted path with {label}: the simulated gap has the sign of the prediction (sign {pr['sign']:+d})", np.sign(sim) == pr["sign"], (sim, pr))
    check(f"planted path with {label}: the expansion is within 15% of the simulated gap", abs(pr["gap_per_period"] / sim - 1.0) < 0.15, (sim, pr))


# =====================================================================================================================
# The study layer on made-up data (R1 section 4.2 P6): intervals, the decade prediction, the trigger splice.
# =====================================================================================================================
import pandas as pd  # noqa: E402

from calendar_letf import nyse, products, study  # noqa: E402

# ---- gap_interval ----
gi = study.gap_interval(np.full(300, 0.004), 12)
check("gap_interval: a constant positive gap has se 0, an interval of one point above zero, and is not noisy",
      gi["gap_se"] < 1e-15 and gi["gap_lo"] > 0 and not gi["noisy"] and gi["gap_block_months"] == 12 and gi["gap_k"] == 25, gi)
gn = study.gap_interval(np.random.default_rng(4).normal(0.0, 0.01, 300), 12)
check("gap_interval: pure noise around zero is flagged noisy (interval covers zero), headline and block-bootstrap", gn["noisy"] and gn["noisy_indep"] and gn["noisy_bb_mean"], gn)
gp = study.gap_interval(np.random.default_rng(4).normal(0.02, 0.005, 300), 12)
check("gap_interval: a gap of +2 pp with sd 0.5 pp is clear (interval above zero), headline and block-bootstrap",
      (not gp["noisy"]) and (not gp["noisy_indep"]) and (not gp["noisy_bb_mean"]) and gp["gap_lo"] > 0, gp)
check("gap_interval: the median interval of a constant gap has se 0 and is not noisy; pure noise is noisy; +2 pp is clear",
      gi["median_se"] < 1e-15 and gi["median_lo"] > 0 and not gi["noisy_bb_median"] and gn["noisy_bb_median"] and (not gp["noisy_bb_median"]) and gp["median_lo"] > 0, (gi, gn, gp))
bmg = stats.block_bootstrap_median(np.random.default_rng(4).normal(0.02, 0.005, 300), block=12, n_boot=study.N_BOOT)
check("gap_interval: the median columns equal stats.block_bootstrap_median on the same gaps (block = months, N_BOOT resamples)",
      abs(gp["median_se"] - bmg["se"]) < 1e-15 and abs(gp["median_lo"] - bmg["lo"]) < 1e-15 and abs(gp["median_hi"] - bmg["hi"]) < 1e-15
      and gp["bb_median_se"] == gp["median_se"] and gp["bb_median_lo"] == gp["median_lo"] and gp["bb_median_hi"] == gp["median_hi"])
ind_g = stats.phase_pooled_mean(np.random.default_rng(4).normal(0.02, 0.005, 300), 12)
check("gap_interval: the headline flag `noisy` is the PHASE-POOLED flag (same as noisy_indep), the bb_* columns are the block-bootstrap ones, and the draw count is N_BOOT = 10,000",
      gp["noisy"] == gp["noisy_indep"] == stats.covers_zero(ind_g["lo"], ind_g["hi"]) and gp["indep_df"] == ind_g["df"]
      and abs(gp["indep_lo"] - ind_g["lo"]) < 1e-15 and gp["bb_lo"] == gp["gap_lo"] and gp["bb_hi"] == gp["gap_hi"] and gp["bb_k"] == gp["gap_k"]
      and gp["bb_n_boot"] == study.N_BOOT == 10000, gp)
# The two flags can differ, and `noisy` must follow the phase-pooled interval: a series built so that the block bootstrap
# (SE biased low) excludes zero while the pooled interval, which uses only independent windows, covers it.
gd = None
for sd_ in range(2000):
    cs_ = np.concatenate(([0.0], np.cumsum(np.random.default_rng(sd_).normal(0.0, 0.02, 801 + 119))))
    cand = study.gap_interval(0.0 + (cs_[120:120 + 801] - cs_[:801]) / 120, 120, n_boot=300)
    if cand["noisy_bb_mean"] != cand["noisy"]:
        gd = cand
        break
check("gap_interval: on simulated overlapping windows with a true gap of 0 there are series where the flags differ, and `noisy` is then the pooled one",
      gd is not None and gd["noisy"] == stats.covers_zero(gd["indep_lo"], gd["indep_hi"]) and gd["noisy_bb_mean"] == stats.covers_zero(gd["bb_lo"], gd["bb_hi"]), gd)

# ---- match_episodes ----
m1 = study.match_episodes(["2001-09-20", "2008-11-20"], ["2001-09-19", "2008-11-21", "2010-05-06"])
check("match_episodes: dates within 4 days are one episode (listed as shifted); unmatched dates are one-sided",
      m1["episodes_shifted"] == ["2001-09-20 -> 2001-09-19", "2008-11-20 -> 2008-11-21"] and m1["episodes_index_only"] == [] and m1["episodes_etf_only"] == ["2010-05-06"], m1)
m2 = study.match_episodes(["2008-11-20"], [])
check("match_episodes: an index episode with no ETF episode is index-only", m2["episodes_index_only"] == ["2008-11-20"] and m2["episodes_etf_only"] == [])
m3 = study.match_episodes(["2000-01-04", "2000-01-05"], ["2000-01-05"])
check("match_episodes: each ETF date is used once (two index dates, one ETF date: one pairs, one is index-only)",
      len(m3["episodes_index_only"]) == 1 and m3["episodes_etf_only"] == [], m3)

# ---- the ETF trigger splice ----
dts = pd.bdate_range("2001-01-02", periods=10)
idx_c = pd.Series(np.linspace(1000.0, 1090.0, 10), index=dts, name="IDX")
idx_l = idx_c * 0.99                                               # index low: 1% under the close
etf_dates = dts[3:]                                                # the ETF's first bar is dts[3]; it has no bar on dts[6]
etf_c = pd.Series(np.linspace(40.0, 49.0, 10)[3:] * 1.0, index=etf_dates)
etf_c = etf_c.drop(dts[6])
etf = pd.DataFrame({"close": etf_c, "low": etf_c * 0.985})         # ETF low 1.5% under its close
etf.loc[dts[8], "low"] = etf.loc[dts[8], "close"] * 0.60           # a bad print: 40% under the close (index gap is 1%)
etf.loc[dts[4], "low"] = etf.loc[dts[4], "close"] * 0.93           # a real dislocation: 7% under the close, inside the 10% tolerance
tr, lo, info = study.splice_etf_trigger(idx_c, idx_l, etf, "TEST:ETF")
k_ = idx_c.iloc[3] / etf.iloc[0]["close"]
check("ETF splice: before the first ETF bar the trigger is the index price and the low is the index low",
      np.allclose(tr.iloc[:3], idx_c.iloc[:3]) and np.allclose(lo.iloc[:3], idx_l.iloc[:3]))
check("ETF splice: continuous at the first bar (trigger = index close there), scale = index close / ETF close", abs(tr.iloc[3] - idx_c.iloc[3]) < 1e-12 and abs(info["scale"] - k_) < 1e-12)
check("ETF splice: after the first bar the trigger is the ETF close x scale", np.allclose(tr.iloc[[4, 5, 7, 8, 9]], (etf["close"] * k_).loc[dts[[4, 5, 7, 8, 9]]]))
check("ETF splice: the day the ETF has no bar is carried by the index move at the last known ratio (and listed)",
      info["rows_carried_from_index"] == [str(dts[6].date())] and abs(tr.loc[dts[6]] / tr.loc[dts[5]] - idx_c.loc[dts[6]] / idx_c.loc[dts[5]]) < 1e-12)
check("ETF splice: a real ETF low (7% under the close) is kept x scale", abs(lo.loc[dts[4]] - etf.loc[dts[4], "low"] * k_) < 1e-9)
check("ETF splice: a bad low print (40% under the close, index gap 1%) is replaced by the index's own gap and listed",
      abs(lo.loc[dts[8]] - tr.loc[dts[8]] * (idx_l.loc[dts[8]] / idx_c.loc[dts[8]])) < 1e-9 and [d["date"] for d in info["bad_low_days"]] == [str(dts[8].date())], info["bad_low_days"])
tr2, lo2, info2 = study.splice_etf_trigger(idx_c, None, etf, "TEST:ETF")
check("ETF splice: with no index low (close-only trigger) the low is None and the close series is unchanged", lo2 is None and np.allclose(tr2, tr))
raises("ETF splice: an ETF whose first bar is not an index trading day is refused",
       lambda: study.splice_etf_trigger(idx_c, None, etf.rename(index={etf.index[0]: pd.Timestamp("2001-01-06")}), "T:E"), "not a trading day")
raises("trigger_series: basis other than index / etf is refused", lambda: study.trigger_series("SPX", "futures"), "'index' or 'etf'")


# ---- a made-up world ----
def made_up_world(theta, seed, mu=0.0004, sig=0.01, start="1990-01-02", end="2009-12-31"):
    """An index with planted serial correlation: r_t = mu + e_t + theta e_{t-1}, on real NYSE sessions. theta < 0 = reversals."""
    days = pd.DatetimeIndex(nyse.sessions(pd.Timestamp(start).date(), pd.Timestamp(end).date()))
    rng = np.random.default_rng(seed)
    e = rng.normal(0.0, sig, len(days) + 1)
    r = mu + e[1:] + theta * e[:-1]
    u = pd.Series(100.0 * np.cumprod(1.0 + r), index=days, name="MADEUP")
    specs = [products.PRODUCTS[p] for p in study.PRODUCT_NAMES["SPX"]]
    w = study.World("SPX", u, u, pd.Series(0.03, index=days), specs, {s.name: products.twin_of(s) for s in specs})
    return w


ENC_ = study.ENCODINGS["fixed"]
w_rev = made_up_world(-0.6, 21)
w_con = made_up_world(+0.6, 22)
for label_, w_, want in (("reversals (MA coefficient -0.6)", w_rev, +1), ("continuations (MA coefficient +0.6)", w_con, -1)):
    dec = study.decade_table(w_, ENC_)
    check(f"planted {label_}: two decades (1990s, 2000s) in the decade table", [d["decade"] for d in dec] == ["1990s", "2000s"], [d["decade"] for d in dec])
    ar_ = [d["returns"]["ar1_rho"] for d in dec]
    exp_rho = -0.6 / 1.36 if want > 0 else 0.6 / 1.36
    check(f"planted {label_}: lag-1 autocorrelation near {exp_rho:+.2f} in each decade (within 3 se) and its z has the right sign and passes 1.96",
          all(abs(a - exp_rho) < 3 * d["returns"]["ar1_se"] for a, d in zip(ar_, dec)) and all(np.sign(d["returns"]["ar1_z"]) == -want and abs(d["returns"]["ar1_z_robust"]) > 1.96 for d in dec), ar_)
    vr21 = [d["returns"]["vr"]["21"] for d in dec]
    check(f"planted {label_}: VR(21) is {'below' if want > 0 else 'above'} 1 and significant (robust z beyond 1.96) in both decades",
          all(((v["vr"] < 1) if want > 0 else (v["vr"] > 1)) and v["significant"] for v in vr21), vr21)
    for pn in ("HYP_SPX_M", "HYP_SPX_W"):
        pr_ = [d["products"][pn] for d in dec]
        check(f"planted {label_}: {pn} predicted sign {want:+d} and realized sign {want:+d} in both decades (the prediction works on a planted answer)",
              all(x["predicted_sign"] == want and x["realized_sign"] == want and x["sign_agrees"] for x in pr_), pr_)
    ps = study.prediction_summary(dec, "HYP_SPX_M")
    check(f"planted {label_}: prediction_summary counts 2 of 2 agreeing decades for the monthly product", ps["n_agree"] == 2 and ps["n_decades"] == 2, ps)

# ---- multi_start intervals on the made-up world ----
rows, raw = study.multi_start(w_rev, ENC_, horizons_years=(1, 3))
row3 = next(r for r in rows if r["product"] == "HYP_SPX_M" and r["horizon_years"] == 3)
g3 = raw[(raw["product"] == "HYP_SPX_M") & (raw["horizon_years"] == 3)]["gap"].to_numpy()
check("multi_start: gap_mean is the mean of the per-start gaps; the block is 36 months and k = n // 36",
      abs(row3["gap_mean"] - np.nanmean(g3)) < 1e-15 and row3["gap_block_months"] == 36 and row3["gap_k"] == len(g3) // 36 and row3["gap_n_windows"] == len(g3), row3)
check("multi_start: the block-bootstrap interval is mean +/- t(k-1) x se, `noisy_bb_mean` follows from it, and the bb_* columns repeat it",
      abs((row3["gap_hi"] - row3["gap_lo"]) / 2 - stats.t975(row3["gap_k"] - 1) * row3["gap_se"]) < 1e-12
      and row3["noisy_bb_mean"] == stats.covers_zero(row3["gap_lo"], row3["gap_hi"]) and row3["bb_lo"] == row3["gap_lo"] and row3["bb_se"] == row3["gap_se"])
check("multi_start: on planted reversals the monthly fund's 3-year gap is clearly positive (not noisy, headline and block-bootstrap) and the daily-twin comparison keeps its median and win share",
      row3["gap_mean"] > 0.01 and not row3["noisy"] and not row3["noisy_bb_mean"] and row3["calendar_wins"] > 0.9 and row3["gap_median"] > 0.01, row3)
ind3 = stats.phase_pooled_mean(g3, 36)
check("multi_start: the non-overlapping-window columns equal stats.phase_pooled_mean on the same gaps, and the headline flag `noisy` is its flag",
      abs(row3["indep_mean"] - ind3["mean"]) < 1e-15 and row3["indep_df"] == ind3["df"] and row3["noisy"] == stats.covers_zero(ind3["lo"], ind3["hi"]))
rows1 = [r for r in rows if r["horizon_years"] == 1]
check("multi_start: every horizon (1 and 3 years) carries the phase-pooled interval with step = the horizon in months (1-year phases: 12; 3-year phases: 36)",
      all(r["indep_phases"] == 12 for r in rows1) and all(r["indep_phases"] == 36 for r in rows if r["horizon_years"] == 3)
      and all(np.isfinite(r["indep_lo"]) and r["indep_df"] >= 1 for r in rows), [(r["product"], r["horizon_years"], r["indep_phases"], r["indep_df"]) for r in rows])

# ---- World.variant: new trigger, new drop, empty caches ----
nav0 = w_rev.nav("SPYQ", ENC_)
wv = w_rev.variant(early_drop=0.20)
check("World.variant: caches are empty and the drop replaces the calendar products' drop (twins keep none)",
      wv.navs == {} and all(s.early_drop == 0.20 for s in wv.specs) and all(t.early_drop is None for t in wv.twins.values()) and w_rev.specs[0].early_drop == 0.35)
nav20 = wv.nav("SPYQ", ENC_)
check("World.variant: the 20% trigger fires on the planted path where the 35% one does not (the 35% world's cache is untouched)",
      len(nav20.attrs["early_resets"]) >= len(nav0.attrs["early_resets"]) and w_rev.nav("SPYQ", ENC_) is nav0)
