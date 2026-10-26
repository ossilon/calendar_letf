"""Simulated coverage of the interval conventions on the overlap structure of the project's own gap series.

Plain-English summary
  * The passive study measures a reset gap (calendar CAGR minus twin CAGR) at every month-end start over a horizon of
    h months. Starts one month apart share h - 1 of their h months, so the per-start gaps are heavily dependent and a
    naive standard error is far too small. This module builds synthetic gap series with exactly that structure (the
    gap at start s = a constant + the mean of the h monthly shocks s .. s + h - 1), applies the project's three
    interval conventions many times, and counts how often each interval contains the constant: the COVERAGE. A
    "95 percent" interval should cover about 0.95 of the time; less means it is too short, more means it is wide.
  * Shock models. "iid": every month's shock is independent, which is the model the headline interval assumes
    (windows that do not overlap are independent). "regime": the monthly shock also carries a slow AR(1) component
    (a persistence phi and a share of the shock variance, chosen by the caller), so windows that do not overlap depend
    on each other, the way decade regimes make them (FINDINGS F7). Every run also records the autocorrelation of the
    simulated gap series at lags h and 2h, so a regime case can be matched to the autocorrelation measured in the real
    gap series (`measured_persistence`).
  * Conventions tested, all from calendar_letf/stats.py: block-bootstrap mean and median intervals (block = h,
    t(k-1) x SE) and the phase-pooled interval from non-overlapping windows (the headline since R2 step 10).
  * For each run the module also records the pooled statistic |mean - truth| / SE. Its 95th percentile over runs is
    the multiplier that WOULD give 95 percent coverage; next to the t multiplier actually used it says how
    conservative the interval is (with 3 windows per phase t(2) = 4.30, far above what the sampling distribution needs).

Not in this module: the real gap series (results/raw/*.csv; `measured_persistence` only reads them), the studies'
results, plotting. scripts/run_coverage_sim.py runs the configurations and writes results/coverage_sim.json.
"""
import csv
import math
from collections import defaultdict

import numpy as np

from . import stats

TRUE_GAP = 0.004            # the constant every synthetic series carries (0.4 pp a year); its value is immaterial
SHOCK_SD = 0.02             # standard deviation of a monthly shock; immaterial too, coverage is scale-free


def regime_component(rng, length, phi):
    """A stationary AR(1) path of unit variance: r_t = phi r_{t-1} + sqrt(1 - phi^2) z_t, with r_0 a standard normal
    draw (the stationary law), so every r_t has variance 1 and the autocorrelation at lag j is phi^j."""
    if not 0.0 <= phi < 1.0:
        raise ValueError(f"regime_component: phi must be in [0, 1), got {phi}")
    z = rng.normal(0.0, 1.0, int(length))
    r = np.empty(int(length))
    r[0] = z[0]
    s = math.sqrt(1.0 - phi * phi)
    for t in range(1, int(length)):
        r[t] = phi * r[t - 1] + s * z[t]
    return r


def gap_series(rng, n, h, regime=None, true_gap=TRUE_GAP, sd=SHOCK_SD):
    """n per-start gaps with the overlap structure of rolling h-month windows.

    e_t (t = 1 .. n + h - 1) are the monthly shocks; the gap at start s is true_gap + mean(e_s .. e_{s+h-1}), so two
    starts one month apart share h - 1 shocks. regime = None: e_t iid normal(0, sd). regime = (phi, share):
    e_t = sqrt(1 - share) x (iid shock) + sd x sqrt(share) x r_t with r the unit-variance AR(1) of `regime_component`;
    the shock variance is still sd^2 and the share `share` of it is persistent.
    The iid draw is made first and alone, so with regime = None the series equals the plain construction
    "normal shocks, cumulative sum, window means" for the same generator state (tests rely on this).
    """
    n, h = int(n), int(h)
    if n < 1 or h < 1:
        raise ValueError(f"gap_series: n and h must be at least 1, got n = {n}, h = {h}")
    length = n + h - 1
    e = rng.normal(0.0, sd, length)
    if regime is not None:
        phi, share = regime
        if not 0.0 <= share <= 1.0:
            raise ValueError(f"gap_series: the regime share must be in [0, 1], got {share}")
        e = math.sqrt(1.0 - share) * e + sd * math.sqrt(share) * regime_component(rng, length, phi)
    cs = np.concatenate(([0.0], np.cumsum(e)))
    return true_gap + (cs[h:h + n] - cs[:n]) / h


def autocorr(x, lag):
    """Sample autocorrelation of x at `lag`: sum of products of deviations from the one overall mean, over the sum of
    squared deviations (the usual estimator). NaN when fewer than 2 pairs remain, when lag < 1, or when x is constant."""
    x = np.asarray(x, dtype=np.float64).ravel()
    n, lag = len(x), int(lag)
    if lag < 1 or n - lag < 2:
        return float("nan")
    d = x - x.mean()
    den = float(np.dot(d, d))
    if den == 0.0:
        return float("nan")
    return float(np.dot(d[lag:], d[:-lag]) / den)


def simulate(n, h, seed, runs=400, n_boot=1000, regime=None, block=None):
    """Coverage of the three conventions on `runs` synthetic series of n starts and h-month windows.

    block defaults to h (the study's rule). The series come from numpy's default_rng(seed), one after another; run i
    uses bootstrap seed i, exactly as tests/test_stats.py does, so the suite can recompute an entry and compare.
    Returns a dict of plain numbers:
      coverage_bb_mean, coverage_bb_median, coverage_pooled   share of runs whose interval contains TRUE_GAP
      se_ratio_bb        mean bootstrap SE / standard deviation over runs of the series mean (1 = an unbiased SE)
      se_ratio_pooled    mean pooled SE / standard deviation over runs of the pooled mean
      t_needed_pooled    95th percentile over runs of |pooled mean - TRUE_GAP| / pooled SE: the multiplier that would
                         give 0.95 coverage; t_used_pooled is the t(df, 0.975) the convention uses
      acf_gap_h, acf_gap_2h   mean over runs of the gap series' autocorrelation at lags h and 2h (the dependence
                         between windows that do not overlap; about 0 under iid shocks)
      plus n, h, block, k (= n // block), df, runs, n_boot, seed and regime (phi, share, half_life_months) or None.
    """
    n, h = int(n), int(h)
    block = int(h if block is None else block)
    rng = np.random.default_rng(seed)
    c_mean = c_med = c_pool = 0
    se_bb, se_pool, mean_all, mean_pool, t_pool, acf_h, acf_2h = [], [], [], [], [], [], []
    df_used = 0
    for i in range(int(runs)):
        g = gap_series(rng, n, h, regime)
        a = stats.block_bootstrap_mean(g, block, n_boot=n_boot, seed=i)
        m = stats.block_bootstrap_median(g, block, n_boot=n_boot, seed=i)
        p = stats.phase_pooled_mean(g, h)
        c_mean += (a["lo"] <= TRUE_GAP <= a["hi"])
        c_med += (m["lo"] <= TRUE_GAP <= m["hi"])
        c_pool += (p["lo"] <= TRUE_GAP <= p["hi"])
        se_bb.append(a["se"])
        se_pool.append(p["se"])
        mean_all.append(float(g.mean()))
        mean_pool.append(p["mean"])
        t_pool.append(abs(p["mean"] - TRUE_GAP) / p["se"] if p["se"] > 0.0 else float("inf"))
        acf_h.append(autocorr(g, h))
        acf_2h.append(autocorr(g, 2 * h))
        df_used = p["df"]
    runs = int(runs)
    return dict(n=n, h=h, block=block, k=int(n // block), df=int(df_used), runs=runs, n_boot=int(n_boot), seed=int(seed),
                regime=None if regime is None else dict(phi=float(regime[0]), share=float(regime[1]),
                                                        half_life_months=(0.0 if regime[0] <= 0.0 else float("inf") if regime[0] >= 1.0 else math.log(0.5) / math.log(regime[0]))),
                coverage_bb_mean=c_mean / runs, coverage_bb_median=c_med / runs, coverage_pooled=c_pool / runs,
                se_ratio_bb=float(np.mean(se_bb) / np.std(mean_all, ddof=1)),
                se_ratio_pooled=float(np.mean(se_pool) / np.std(mean_pool, ddof=1)),
                t_needed_pooled=float(np.quantile(t_pool, 0.95)),
                t_used_pooled=float(stats.t975(df_used)) if df_used >= 1 else float("nan"),
                acf_gap_h=float(np.nanmean(acf_h)), acf_gap_2h=float(np.nanmean(acf_2h)))


def acf_null(n, h, seed, runs=4000, regime=None):
    """The sampling distribution of the gap series' lag-h autocorrelation under the shock model: `runs` synthetic
    series of n starts and h-month windows, one autocorrelation each (sorted, as a numpy array). Under iid shocks this
    is the null distribution for the persistence test: a measured lag-h autocorrelation is compared with it (the
    one-sided Monte Carlo p-value is the share of draws at or above the measured value). Cheap: no bootstrap, so
    thousands of runs take seconds."""
    rng = np.random.default_rng(seed)
    vals = np.array([autocorr(gap_series(rng, n, h, regime), h) for _ in range(int(runs))])
    return np.sort(vals[np.isfinite(vals)])


def mc_p_value(null_sorted, observed):
    """One-sided Monte Carlo p-value: the share of null draws at or above `observed` (0 means none of them)."""
    null_sorted = np.asarray(null_sorted)
    if len(null_sorted) == 0 or not np.isfinite(observed):
        return float("nan")
    return float((null_sorted >= observed).mean())


def measured_persistence(csv_path, lags=(1, 2, 3)):
    """Autocorrelation of the REAL per-start gap series at multiples of the horizon, per product and horizon.

    csv_path: results/raw/multi_start_<world>_<encoding>.csv (columns start, horizon_years, product, gap, ...; one
    row per start). For each (product, horizon_years), with h = 12 x horizon_years, the record holds acf at lags h,
    2h, 3h (the dependence between windows that do not overlap, which the headline interval takes as zero), the
    number of starts n, and se_if_independent = 1 / sqrt(n / h): the rough standard error of an autocorrelation when
    the n / h non-overlapping windows are independent. Reads with the csv module only (no pandas).
    """
    series = defaultdict(list)
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            series[(row["product"], int(float(row["horizon_years"])))].append((row["start"], float(row["gap"])))
    out = []
    for (product, hy), rows in sorted(series.items()):
        rows.sort()
        g = np.array([v for _, v in rows])
        h = 12 * hy
        rec = dict(product=product, horizon_years=hy, h=h, n=len(g), se_if_independent=1.0 / math.sqrt(len(g) / h))
        for m in lags:
            rec[f"acf_lag_{m}h"] = autocorr(g, m * h)
        out.append(rec)
    return out
