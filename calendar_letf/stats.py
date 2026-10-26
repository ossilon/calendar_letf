"""Uncertainty statistics for the study layer (R2 step 3): intervals for the headline gaps and a test of the
autocorrelation story.  Pure NumPy; no data files.

Plain-English map
  * A headline such as "the 10-year median gap is +0.29 pp" is one number from ONE history.  An interval says how far
    that number could move if the same market process had produced a different history.
  * Windows that start a month apart share 119 of their 120 months, so they are not independent observations.  The
    bootstrap here resamples whole BLOCKS of consecutive windows, so the dependence inside a block is kept.
  * A "variance ratio" VR(q) compares the variance of q-day returns with q times the variance of 1-day returns.
    VR = 1 for a random walk, VR < 1 when daily moves tend to reverse, VR > 1 when they tend to continue.  The test
    statistic z says how many standard errors VR is from 1.

What is here
  t975(df)                    two-sided 95 percent Student-t quantile.  A built-in table (df 1 to 60, from the exact
                              values) and the Cornish-Fisher series above 60; it matches scipy.stats.t.ppf(0.975, df)
                              to 1e-5 for every df, and scipy is NOT needed (the tests compare the two when scipy is
                              installed).  Using one built-in function keeps every number the same on every machine.
  block_bootstrap_mean        circular block bootstrap of a mean; interval = mean +/- t(k-1) x bootstrap SE
  block_bootstrap_median      the same for the median of the window gaps (bootstrap SE of a median: reasonable, not exact)
  phase_pooled_mean           interval for windows that do not overlap (one set per start phase), pooled over phases
  variance_ratio              Lo-MacKinlay (1988) unbiased VR(q) with the heteroskedasticity-robust z
  ar1                         lag-1 autocorrelation with its standard error and a robust z
  predicted_reset_gap         Bessembinder's second-order prediction of calendar-minus-daily per reset period
"""
import math

import numpy as np

# ---------------------------------------------------------------- Student t quantile (two-sided 95 percent)

_T975 = (12.706205, 4.302653, 3.182446, 2.776445, 2.570582, 2.446912,
         2.364624, 2.306004, 2.262157, 2.228139, 2.200985, 2.178813,
         2.160369, 2.144787, 2.131450, 2.119905, 2.109816, 2.100922,
         2.093024, 2.085963, 2.079614, 2.073873, 2.068658, 2.063899,
         2.059539, 2.055529, 2.051831, 2.048407, 2.045230, 2.042272,
         2.039513, 2.036933, 2.034515, 2.032245, 2.030108, 2.028094,
         2.026192, 2.024394, 2.022691, 2.021075, 2.019541, 2.018082,
         2.016692, 2.015368, 2.014103, 2.012896, 2.011741, 2.010635,
         2.009575, 2.008559, 2.007584, 2.006647, 2.005746, 2.004879,
         2.004045, 2.003241, 2.002465, 2.001717, 2.000995, 2.000298)
_Z975 = 1.959963984540054


def t975(df):
    """The 97.5th percentile of Student's t with `df` degrees of freedom (df >= 1): the multiplier for a two-sided
    95 percent interval.  Table for df <= 60; above 60 the Cornish-Fisher series in 1/df, four terms (error below 1e-6)."""
    df = float(df)
    if not df >= 1.0:
        raise ValueError(f"t975: df must be at least 1, got {df}")
    if df <= 60.0 and df == int(df):
        return _T975[int(df) - 1]
    if df <= 60.0:                                        # non-integer df: interpolate the table linearly
        lo = int(math.floor(df))
        return _T975[lo - 1] + (df - lo) * (_T975[lo] - _T975[lo - 1])
    z = _Z975
    return (z + (z ** 3 + z) / (4.0 * df) + (5.0 * z ** 5 + 16.0 * z ** 3 + 3.0 * z) / (96.0 * df ** 2)
            + (3.0 * z ** 7 + 19.0 * z ** 5 + 17.0 * z ** 3 - 15.0 * z) / (384.0 * df ** 3))


def covers_zero(lo, hi):
    """True when the interval [lo, hi] contains 0 (or is undefined): the headline is 'noisy'."""
    if lo is None or hi is None or not (np.isfinite(lo) and np.isfinite(hi)):
        return True
    return bool(lo <= 0.0 <= hi)


# ---------------------------------------------------------------- block bootstrap

def _block_bootstrap_draws(x, block, n_boot, seed, stat):
    """The `n_boot` circular-block-bootstrap values of `stat` (np.mean or np.median) for a clean 1-D array x with
    len(x) >= 2 and 1 <= block <= len(x).  Each resample joins ceil(n / block) blocks of `block` consecutive values
    (start drawn uniformly, the end wraps to the start) and keeps the first n values.  The draws depend only on
    (n, block, n_boot, seed), so the mean and the median bootstrap use the same resamples."""
    n = len(x)
    rng = np.random.default_rng(seed)
    nb = -(-n // block)                                     # blocks per resample (ceiling)
    offs = np.arange(block)
    out = np.empty(int(n_boot))
    step = 500
    for a in range(0, int(n_boot), step):
        b = min(a + step, int(n_boot))
        starts = rng.integers(0, n, size=(b - a, nb))
        idx = ((starts[:, :, None] + offs[None, None, :]) % n).reshape(b - a, nb * block)[:, :n]
        out[a:b] = stat(x[idx], axis=1)
    return out


def block_bootstrap_mean(x, block=21, n_boot=2000, seed=0):
    """Circular block bootstrap of the mean of a 1-D array, with a Student-t interval.

    Steps
      1. Cut the series into blocks of `block` consecutive values (circular: the end wraps to the start), draw
         ceil(n / block) blocks with replacement, join them, keep the first n values and take their mean.
      2. Repeat `n_boot` times; the standard deviation (ddof = 1) of those means is the bootstrap SE.
      3. Interval = mean +/- t(k-1, 0.975) x SE with k = n // block, the number of independent-sized blocks the
         series holds.  The t multiplier (not 1.96, and not a percentile of the bootstrap means) is the 2x Ledger
         rule (engine review F1): with only k blocks the SE itself is uncertain, and a percentile interval ignores
         that and covers less than 95 percent (about 0.85 at k = 6 in the 2x Ledger simulation).
    Returns dict(mean, median, se, lo, hi, k, n, block, n_boot, pct_lo, pct_hi).  `median` is the median of x itself.
    `pct_lo` / `pct_hi` are the 2.5 / 97.5 percentiles of the bootstrap means: kept only so tests can show that this
    naive interval under-covers; do not publish them.  NaN values are dropped first.  With k < 2 the t interval is
    undefined and lo = hi = NaN.  A constant series has se 0 and lo = hi = the mean.
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    x = x[np.isfinite(x)]
    n = len(x)
    block = int(block)
    if block < 1:
        raise ValueError("block must be at least 1")
    if n == 0:
        return dict(mean=float("nan"), median=float("nan"), se=float("nan"), lo=float("nan"), hi=float("nan"), k=0, n=0,
                    block=block, n_boot=int(n_boot), pct_lo=float("nan"), pct_hi=float("nan"))
    mean = float(x.mean())
    k = n // block
    out = dict(mean=mean, median=float(np.median(x)), k=int(k), n=int(n), block=block, n_boot=int(n_boot))
    if n < 2 or block > n:
        out.update(se=float("nan"), lo=float("nan"), hi=float("nan"), pct_lo=float("nan"), pct_hi=float("nan"))
        return out
    means = _block_bootstrap_draws(x, block, n_boot, seed, np.mean)
    se = float(means.std(ddof=1))
    if k >= 2:
        half = t975(k - 1) * se
        lo, hi = mean - half, mean + half
    else:
        lo = hi = float("nan")
    out.update(se=se, lo=float(lo), hi=float(hi), pct_lo=float(np.percentile(means, 2.5)), pct_hi=float(np.percentile(means, 97.5)))
    return out


def block_bootstrap_median(x, block=21, n_boot=2000, seed=0):
    """Circular block bootstrap of the MEDIAN of a 1-D array, with the same Student-t interval as the mean version.

    Steps are those of `block_bootstrap_mean` (same resamples for the same seed), with the median of each resample in
    place of its mean:  interval = median(x) +/- t(k-1, 0.975) x bootstrap SE of the median, k = n // block.
    Caveats, stated plainly:
      * The interval is for the median of the window gaps (the median over all month-end starts in this one history),
        not for a population median of an assumed distribution.
      * The bootstrap SE of a median is a reasonable device, not an exact one: the sample median is a non-smooth
        statistic, its bootstrap distribution is discrete and can be lumpy, and on skewed data the sampling
        distribution is not symmetric, so a symmetric interval is an approximation.  The coverage tests in
        tests/test_stats.py show about 95 percent on normal and on skewed data at n = 252, block = 21; they do not
        prove the same for every series.
    Returns dict(median, mean, se, lo, hi, k, n, block, n_boot).  NaN values are dropped first.  With k < 2 the t
    interval is undefined and lo = hi = NaN.  A constant series has se 0 and lo = hi = the median.
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    x = x[np.isfinite(x)]
    n = len(x)
    block = int(block)
    if block < 1:
        raise ValueError("block must be at least 1")
    nan = float("nan")
    if n == 0:
        return dict(median=nan, mean=nan, se=nan, lo=nan, hi=nan, k=0, n=0, block=block, n_boot=int(n_boot))
    med = float(np.median(x))
    k = n // block
    out = dict(median=med, mean=float(x.mean()), k=int(k), n=int(n), block=block, n_boot=int(n_boot))
    if n < 2 or block > n:
        out.update(se=nan, lo=nan, hi=nan)
        return out
    meds = _block_bootstrap_draws(x, block, n_boot, seed, np.median)
    se = float(meds.std(ddof=1))
    if k >= 2:
        half = t975(k - 1) * se
        lo, hi = med - half, med + half
    else:
        lo = hi = nan
    out.update(se=se, lo=float(lo), hi=float(hi))
    return out


def phase_pooled_mean(g, step):
    """Interval from NON-overlapping windows, pooled over start phases.

    g holds one value per start, in time order, with starts one month apart; `step` is the horizon in months.  Taking
    every step-th value gives one set of windows that do not overlap; there are `step` such sets (phases).  For a
    phase with k_p windows, mean m_p and sample variance s_p^2:  SE_p^2 = s_p^2 / k_p.
    Pooled:  mean = average of the phase means;  SE^2 = average of SE_p^2;  df = (smallest k_p) - 1;
             interval = mean +/- t(df, 0.975) x SE.
    The phases are NOT independent of each other (a phase is the next one shifted by a month), so their errors are
    not averaged away: SE is the typical single-phase SE, not that divided by sqrt(step).  The smallest k_p is the
    conservative choice for the degrees of freedom.  Phases with fewer than 2 windows are skipped.
    Returns dict(mean, se, lo, hi, df, k_min, k_max, phases, share_phases_excl_zero); the last is the share of
    phases whose OWN t interval excludes zero.
    """
    g = np.asarray(g, dtype=np.float64)
    means, ses2, ks, excl = [], [], [], []
    for ph in range(int(step)):
        x = g[ph::int(step)]
        x = x[np.isfinite(x)]
        if len(x) < 2:
            continue
        k = len(x)
        m, s2 = float(x.mean()), float(x.var(ddof=1))
        means.append(m)
        ses2.append(s2 / k)
        ks.append(k)
        half = t975(k - 1) * math.sqrt(s2 / k)
        excl.append(not (m - half <= 0.0 <= m + half))
    if not ks:
        nan = float("nan")
        return dict(mean=nan, se=nan, lo=nan, hi=nan, df=0, k_min=0, k_max=0, phases=0, share_phases_excl_zero=nan)
    mean = float(np.mean(means))
    se = math.sqrt(float(np.mean(ses2)))
    df = min(ks) - 1
    half = t975(df) * se
    return dict(mean=mean, se=se, lo=mean - half, hi=mean + half, df=int(df), k_min=int(min(ks)), k_max=int(max(ks)),
                phases=len(ks), share_phases_excl_zero=float(np.mean(excl)))


# ---------------------------------------------------------------- long-run variance (Newey-West) and an era-difference test

def newey_west_variance(x, lags):
    """Long-run variance of a series (Newey and West 1987, Bartlett weights), the variance that the mean of an
    autocorrelated series needs in place of the plain one:

        V = gamma_0 + 2 x sum_{j=1}^{L} (1 - j / (L + 1)) x gamma_j,   gamma_j = (1/n) sum_{t>j} (x_t - m)(x_{t-j} - m)

    SE of the mean = sqrt(V / n). L = 0 gives the plain variance with 1/n. The Bartlett weights keep V >= 0. NaN
    values are dropped; fewer than 2 values give NaN.
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    x = x[np.isfinite(x)]
    n = len(x)
    L = int(lags)
    if L < 0:
        raise ValueError(f"newey_west_variance: lags must be >= 0, got {lags}")
    if n < 2:
        return float("nan")
    d = x - x.mean()
    v = float(np.dot(d, d)) / n
    for j in range(1, min(L, n - 1) + 1):
        v += 2.0 * (1.0 - j / (L + 1.0)) * float(np.dot(d[j:], d[:-j])) / n
    return v


def era_difference_z(x1, x2, lags):
    """z statistic for the difference of two series' means (era 1 minus era 2) with Newey-West standard errors:
    (m1 - m2) / sqrt(V1 / n1 + V2 / n2). The two eras are taken as independent of each other. NaN when either side
    has fewer than 2 values or a zero variance."""
    a = np.asarray(x1, dtype=np.float64).ravel()
    b = np.asarray(x2, dtype=np.float64).ravel()
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    denom = newey_west_variance(a, lags) / len(a) + newey_west_variance(b, lags) / len(b)
    if not denom > 0.0:
        return float("nan")
    return float((a.mean() - b.mean()) / math.sqrt(denom))


# ---------------------------------------------------------------- variance ratio and autocorrelation

def variance_ratio(r, q):
    """Lo and MacKinlay (1988, Review of Financial Studies 1, 41-66) variance ratio VR(q) of a return series.

    r: the T one-period returns (log or simple; the caller chooses), q >= 2 the aggregation horizon.
        mu      = mean(r)
        sa2     = sum((r - mu)^2) / (T - 1)                                   one-period variance (unbiased)
        sc2     = sum_t (q-period sum - q mu)^2 / m,   m = q (T - q + 1)(1 - q/T)   overlapping q-period variance (unbiased)
        VR(q)   = sc2 / sa2
    The q-period sums overlap (every start, not every q-th), which is the estimator of their eq. (2.7) and makes the
    estimate unbiased.  Two z statistics, both asymptotically N(0, 1) under the random-walk null:
        z_homoskedastic = (VR - 1) / sqrt(2 (2q - 1)(q - 1) / (3 q T))                       their z(q), needs iid returns
        z_robust        = (VR - 1) / sqrt(theta),  theta = sum_{j=1}^{q-1} [2 (q - j) / q]^2 delta_j,
                          delta_j = sum_{t=j+1}^{T} (r_t - mu)^2 (r_{t-j} - mu)^2 / [sum_t (r_t - mu)^2]^2
                          their z*(q) (theorem 2): valid when the variance changes over time (it does for markets).
    Use z_robust.  Returns dict(vr, z_robust, z_homoskedastic, n = T, q).  NaN when T <= q or the series is constant.
    """
    r = np.asarray(r, dtype=np.float64).ravel()
    r = r[np.isfinite(r)]
    T = len(r)
    q = int(q)
    if q < 2:
        raise ValueError("variance_ratio needs q >= 2")
    nan = float("nan")
    if T <= q + 1:
        return dict(vr=nan, z_robust=nan, z_homoskedastic=nan, n=int(T), q=q)
    mu = r.mean()
    d = r - mu
    ss = float(np.sum(d * d))
    if ss <= 0.0:
        return dict(vr=nan, z_robust=nan, z_homoskedastic=nan, n=int(T), q=q)
    sa2 = ss / (T - 1)
    cs = np.concatenate(([0.0], np.cumsum(r)))
    sums = cs[q:] - cs[:-q] - q * mu                         # T - q + 1 overlapping q-period deviations
    m = q * (T - q + 1) * (1.0 - q / T)
    vr = float(np.sum(sums * sums) / m / sa2)
    d2 = d * d
    theta = 0.0
    for j in range(1, q):
        delta = float(np.sum(d2[j:] * d2[:-j])) / (ss * ss)
        theta += (2.0 * (q - j) / q) ** 2 * delta
    z_rob = (vr - 1.0) / math.sqrt(theta) if theta > 0 else nan
    phi = 2.0 * (2 * q - 1) * (q - 1) / (3.0 * q * T)
    return dict(vr=vr, z_robust=float(z_rob), z_homoskedastic=float((vr - 1.0) / math.sqrt(phi)), n=int(T), q=q)


def ar1(r):
    """Lag-1 autocorrelation of a return series, with two ways to judge it.

        rho  = sum_{t>=2} (r_t - mu)(r_{t-1} - mu) / sum_t (r_t - mu)^2
        se   = 1 / sqrt(n)                    the standard error under independent, equal-variance returns
        z    = rho / se
        z_robust = the heteroskedasticity-robust z of VR(2): since VR(2) - 1 is about rho, (VR(2) - 1) / sqrt(delta_1)
                   tests rho = 0 when the variance changes over time (Lo and MacKinlay 1988)
    Returns dict(rho, se, z, z_robust, n).
    """
    r = np.asarray(r, dtype=np.float64).ravel()
    r = r[np.isfinite(r)]
    n = len(r)
    nan = float("nan")
    if n < 4:
        return dict(rho=nan, se=nan, z=nan, z_robust=nan, n=int(n))
    d = r - r.mean()
    ss = float(np.sum(d * d))
    if ss <= 0.0:
        return dict(rho=nan, se=nan, z=nan, z_robust=nan, n=int(n))
    rho = float(np.sum(d[1:] * d[:-1]) / ss)
    se = 1.0 / math.sqrt(n)
    return dict(rho=rho, se=se, z=rho / se, z_robust=variance_ratio(r, 2)["z_robust"], n=int(n))


# ---------------------------------------------------------------- Bessembinder's prediction

def predicted_reset_gap(mu, sigma, vr, T, beta=2.0):
    """Expected (calendar-reset minus daily-reset) return per reset period of T trading days, to second order.

    Bessembinder (2026, SSRN 7376118, eq. 7-13) writes the expected buy-and-hold (calendar) minus rebalanced (daily)
    return of a beta-times fund over T days as
        E[BH - RB] = (beta - beta^2) [ C(T,2) mu^2 + T sigma^2 / 2 (VR_T - 1) ]  + third-order terms,
    mu and sigma the mean and standard deviation of the one-day simple return, VR_T the variance ratio at horizon T.
    For beta = 2 the factor is -2, so the calendar fund is ahead exactly when the bracket is negative, i.e. when
        VR_T < 1 - (T - 1) mu^2 / sigma^2.        (the `crossover_vr` returned here)
    The bracket alone, with the sign flipped, is the prediction the study compares with the realized sign.
    This is an expansion, not an identity: it drops the (beta - beta^3) terms, which are about 2 percent of the
    second-order term for iid returns at mu = 0.1 percent a day, T = 21 (tests/test_stats.py) and larger when the
    variance ratio is far from 1.  Costs, the early-reset trigger and the financing difference between the two
    structures are NOT in it.
    Returns dict(gap_per_period, bracket, crossover_vr, sign) with sign = +1 (calendar ahead), -1 (daily ahead), 0.
    """
    T = float(T)
    bracket = T * (T - 1.0) / 2.0 * mu * mu + T * sigma * sigma / 2.0 * (vr - 1.0)
    gap = (beta - beta * beta) * bracket
    cross = 1.0 - (T - 1.0) * mu * mu / (sigma * sigma) if sigma > 0 else float("nan")
    sign = 0 if gap == 0 or not np.isfinite(gap) else (1 if gap > 0 else -1)
    return dict(gap_per_period=float(gap), bracket=float(bracket), crossover_vr=float(cross), sign=int(sign))
