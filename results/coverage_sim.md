# Simulated coverage of the interval conventions

Coverage = share of 400 synthetic histories whose 95% interval contains the true constant. Synthetic gap at start s = constant + mean of the h monthly shocks from s (the study's overlap). Block-bootstrap intervals: block = h, t(k-1) x SE. Phase-pooled: non-overlapping windows per start phase, pooled, t(min k_p - 1) x SE (the headline). 't needed' = 95th percentile of |pooled mean - truth| / SE over runs; 't used' = the t multiplier the convention applies.

400 runs per case, 1000 bootstrap resamples per run; seeds in the JSON. Code fingerprint aa82c7998c20.

## 1. Published configurations, independent monthly shocks

| world | horizon | starts n | h = block | k | df | coverage: bb mean | bb median | phase-pooled | bootstrap SE / true SD | pooled SE / true SD | t needed (pooled) | t used | acf of gaps at lag h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NDX | 1y | 487 | 12 | 40 | 39 | 0.860 | 0.877 | 0.945 | 0.78 | 0.98 | 2.06 | 2.02 | -0.04 |
| NDX | 3y | 463 | 36 | 12 | 11 | 0.855 | 0.865 | 0.953 | 0.70 | 0.94 | 2.15 | 2.20 | -0.10 |
| NDX | 5y | 439 | 60 | 7 | 6 | 0.895 | 0.905 | 0.978 | 0.71 | 1.02 | 2.05 | 2.45 | -0.15 |
| NDX | 10y | 379 | 120 | 3 | 2 | 0.915 | 0.932 | 0.998 | 0.52 | 0.97 | 2.21 | 4.30 | -0.30 |
| SPX | 1y | 907 | 12 | 75 | 74 | 0.897 | 0.900 | 0.968 | 0.81 | 1.00 | 1.88 | 1.99 | -0.01 |
| SPX | 3y | 883 | 36 | 24 | 23 | 0.907 | 0.892 | 0.970 | 0.86 | 1.10 | 1.83 | 2.07 | -0.05 |
| SPX | 5y | 859 | 60 | 14 | 13 | 0.882 | 0.882 | 0.953 | 0.75 | 0.99 | 2.10 | 2.16 | -0.08 |
| SPX | 10y | 799 | 120 | 6 | 5 | 0.885 | 0.912 | 0.983 | 0.67 | 0.98 | 2.12 | 2.57 | -0.19 |

Range over the eight cases: block-bootstrap mean 0.855-0.915, median 0.865-0.932, phase-pooled 0.945-0.998; bootstrap SE ratio 0.52-0.86.

## 2. Why the block bootstrap is short: block = window length, not only few blocks

| case | starts n | h = block | k | coverage: bb mean | bb median | phase-pooled | bootstrap SE / true SD |
|---|---|---|---|---|---|---|---|
| large k | 2412 | 12 | 201 | 0.892 | 0.902 | 0.953 | 0.83 |

A block bootstrap sees only the dependence inside one block. For a gap that is the mean of h shocks, blocks of length h lose about a third of the variance of the series mean at ANY block count (the Bartlett-type truncation at one window), and the few-block cases lose more on top.

## 3. Regime stress: a slow AR(1) component in the monthly shocks

't needed' is the 95th percentile of 400 runs, so it carries Monte Carlo error; the bracket is its distribution-free 95% interval (order statistics, `coverage.quantile_interval`). A t ratio inside the bracket cannot be called clear or noisy under that case.

| world | horizon | phi | share | half-life (months) | acf of gaps at lag h | at lag 2h | coverage: bb mean | phase-pooled | t needed (pooled) [95% MC] | t used |
|---|---|---|---|---|---|---|---|---|---|---|
| NDX | 1y | 0.98 | 0.02 | 34 | 0.09 | 0.06 | 0.685 | 0.785 | 3.01 [2.78, 3.43] | 2.02 |
| NDX | 1y | 0.98 | 0.05 | 34 | 0.21 | 0.14 | 0.610 | 0.682 | 4.07 [3.86, 4.39] | 2.02 |
| NDX | 1y | 0.995 | 0.02 | 138 | 0.07 | 0.05 | 0.507 | 0.590 | 4.86 [4.39, 5.72] | 2.02 |
| NDX | 1y | 0.995 | 0.05 | 138 | 0.15 | 0.13 | 0.390 | 0.460 | 6.28 [5.57, 7.35] | 2.02 |
| NDX | 3y | 0.98 | 0.02 | 34 | 0.06 | -0.02 | 0.770 | 0.870 | 2.88 [2.60, 3.48] | 2.20 |
| NDX | 3y | 0.98 | 0.05 | 34 | 0.16 | -0.03 | 0.698 | 0.843 | 3.24 [3.07, 3.63] | 2.20 |
| NDX | 3y | 0.995 | 0.02 | 138 | 0.06 | -0.01 | 0.595 | 0.698 | 4.26 [3.80, 5.23] | 2.20 |
| NDX | 3y | 0.995 | 0.05 | 138 | 0.19 | 0.05 | 0.552 | 0.632 | 4.88 [4.65, 5.43] | 2.20 |
| NDX | 5y | 0.98 | 0.02 | 34 | -0.04 | -0.11 | 0.782 | 0.902 | 2.84 [2.63, 3.08] | 2.45 |
| NDX | 5y | 0.98 | 0.05 | 34 | -0.00 | -0.13 | 0.795 | 0.882 | 3.21 [2.86, 4.34] | 2.45 |
| NDX | 5y | 0.995 | 0.02 | 138 | -0.03 | -0.08 | 0.608 | 0.757 | 4.26 [3.56, 4.76] | 2.45 |
| NDX | 5y | 0.995 | 0.05 | 138 | 0.08 | -0.08 | 0.530 | 0.677 | 5.51 [4.95, 7.22] | 2.45 |
| NDX | 10y | 0.98 | 0.02 | 34 | -0.27 | -0.14 | 0.850 | 0.978 | 3.09 [2.76, 3.70] | 4.30 |
| NDX | 10y | 0.98 | 0.05 | 34 | -0.27 | -0.14 | 0.860 | 0.978 | 3.20 [2.86, 3.98] | 4.30 |
| NDX | 10y | 0.995 | 0.02 | 138 | -0.25 | -0.15 | 0.755 | 0.932 | 4.78 [4.15, 5.92] | 4.30 |
| NDX | 10y | 0.995 | 0.05 | 138 | -0.21 | -0.18 | 0.667 | 0.860 | 5.87 [5.32, 7.04] | 4.30 |
| SPX | 1y | 0.98 | 0.02 | 34 | 0.11 | 0.09 | 0.703 | 0.787 | 3.12 [2.76, 3.58] | 1.99 |
| SPX | 1y | 0.98 | 0.05 | 34 | 0.25 | 0.18 | 0.615 | 0.672 | 3.68 [3.47, 3.83] | 1.99 |
| SPX | 1y | 0.995 | 0.02 | 138 | 0.10 | 0.09 | 0.460 | 0.560 | 5.11 [4.61, 5.57] | 1.99 |
| SPX | 1y | 0.995 | 0.05 | 138 | 0.24 | 0.20 | 0.365 | 0.445 | 6.77 [6.29, 7.60] | 1.99 |
| SPX | 3y | 0.98 | 0.02 | 34 | 0.14 | 0.02 | 0.730 | 0.810 | 2.91 [2.65, 3.15] | 2.07 |
| SPX | 3y | 0.98 | 0.05 | 34 | 0.27 | 0.09 | 0.733 | 0.790 | 3.30 [2.93, 3.64] | 2.07 |
| SPX | 3y | 0.995 | 0.02 | 138 | 0.19 | 0.11 | 0.557 | 0.647 | 4.37 [4.15, 4.86] | 2.07 |
| SPX | 3y | 0.995 | 0.05 | 138 | 0.34 | 0.20 | 0.443 | 0.497 | 6.13 [5.60, 6.54] | 2.07 |
| SPX | 5y | 0.98 | 0.02 | 34 | 0.07 | -0.06 | 0.777 | 0.875 | 2.79 [2.55, 3.23] | 2.16 |
| SPX | 5y | 0.98 | 0.05 | 34 | 0.16 | -0.05 | 0.785 | 0.863 | 2.94 [2.66, 3.48] | 2.16 |
| SPX | 5y | 0.995 | 0.02 | 138 | 0.17 | 0.04 | 0.610 | 0.715 | 4.10 [3.76, 4.73] | 2.16 |
| SPX | 5y | 0.995 | 0.05 | 138 | 0.30 | 0.10 | 0.500 | 0.583 | 5.46 [4.83, 6.39] | 2.16 |
| SPX | 10y | 0.98 | 0.02 | 34 | -0.11 | -0.13 | 0.843 | 0.950 | 2.55 [2.26, 2.96] | 2.57 |
| SPX | 10y | 0.98 | 0.05 | 34 | -0.05 | -0.15 | 0.863 | 0.935 | 2.84 [2.46, 3.18] | 2.57 |
| SPX | 10y | 0.995 | 0.02 | 138 | 0.01 | -0.15 | 0.705 | 0.833 | 4.19 [3.80, 4.46] | 2.57 |
| SPX | 10y | 0.995 | 0.05 | 138 | 0.11 | -0.14 | 0.680 | 0.765 | 4.90 [4.22, 5.52] | 2.57 |

## 4. Persistence measured in the real gap series (results/raw), and the nearest simulated case


SPX: autocorrelation of the per-start gap at lags h, 2h, 3h (h = horizon in months); se if independent = 1 / sqrt(n / h) (a conservative rule of thumb, 1.2-3.3 times the true sampling SD); 'iid expected' = the same statistic in the iid simulation (negative: few windows share one mean); 'excess' = (measured - iid expected) / se; the Monte Carlo columns use 4,000 iid series per configuration: null SD, excess in null SDs, and the one-sided p (share of null draws at or above the measured value).

| product | horizon | starts n | acf lag h | lag 2h | lag 3h | se if independent | iid expected | excess (se) | null SD | excess (MC SD) | p (MC) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HYP_SPX_M | 1y | 907 | 0.13 | 0.21 | 0.18 | 0.12 | -0.01 | 1.2 | 0.093 | 1.6 | 0.0597 |
| HYP_SPX_M | 3y | 883 | 0.48 | 0.44 | 0.44 | 0.20 | -0.05 | 2.6 | 0.156 | 3.4 | 0.0003 |
| HYP_SPX_M | 5y | 859 | 0.58 | 0.51 | 0.26 | 0.26 | -0.08 | 2.5 | 0.187 | 3.6 | 0.0003 |
| HYP_SPX_M | 10y | 799 | 0.54 | 0.07 | -0.30 | 0.39 | -0.19 | 1.9 | 0.222 | 3.2 | 0.0000 |
| HYP_SPX_W | 1y | 907 | 0.07 | 0.06 | 0.03 | 0.12 | -0.01 | 0.7 | 0.093 | 0.9 | 0.1850 |
| HYP_SPX_W | 3y | 883 | 0.14 | 0.18 | 0.12 | 0.20 | -0.05 | 0.9 | 0.156 | 1.3 | 0.1042 |
| HYP_SPX_W | 5y | 859 | 0.23 | 0.10 | -0.08 | 0.26 | -0.08 | 1.2 | 0.187 | 1.7 | 0.0517 |
| HYP_SPX_W | 10y | 799 | 0.13 | -0.01 | -0.24 | 0.39 | -0.19 | 0.8 | 0.222 | 1.4 | 0.0907 |
| SPYQ | 1y | 907 | 0.01 | -0.04 | -0.04 | 0.12 | -0.01 | 0.2 | 0.093 | 0.3 | 0.3870 |
| SPYQ | 3y | 883 | -0.07 | 0.02 | -0.03 | 0.20 | -0.05 | -0.1 | 0.156 | -0.1 | 0.5232 |
| SPYQ | 5y | 859 | -0.06 | -0.09 | -0.12 | 0.26 | -0.08 | 0.1 | 0.187 | 0.1 | 0.4387 |
| SPYQ | 10y | 799 | -0.26 | -0.24 | 0.03 | 0.39 | -0.19 | -0.2 | 0.222 | -0.3 | 0.6055 |

NDX: autocorrelation of the per-start gap at lags h, 2h, 3h (h = horizon in months); se if independent = 1 / sqrt(n / h) (a conservative rule of thumb, 1.2-3.3 times the true sampling SD); 'iid expected' = the same statistic in the iid simulation (negative: few windows share one mean); 'excess' = (measured - iid expected) / se; the Monte Carlo columns use 4,000 iid series per configuration: null SD, excess in null SDs, and the one-sided p (share of null draws at or above the measured value).

| product | horizon | starts n | acf lag h | lag 2h | lag 3h | se if independent | iid expected | excess (se) | null SD | excess (MC SD) | p (MC) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HYP_NDX_W | 1y | 487 | -0.05 | 0.07 | -0.10 | 0.16 | -0.04 | -0.0 | 0.123 | -0.1 | 0.5473 |
| HYP_NDX_W | 3y | 463 | -0.07 | 0.00 | -0.33 | 0.28 | -0.10 | 0.1 | 0.199 | 0.1 | 0.4310 |
| HYP_NDX_W | 5y | 439 | -0.19 | -0.14 | -0.21 | 0.37 | -0.15 | -0.1 | 0.222 | -0.1 | 0.5285 |
| HYP_NDX_W | 10y | 379 | -0.33 | 0.01 | -0.01 | 0.56 | -0.30 | -0.1 | 0.171 | -0.2 | 0.5727 |
| MQQQ | 1y | 487 | 0.11 | 0.05 | 0.08 | 0.16 | -0.04 | 1.0 | 0.123 | 1.1 | 0.1247 |
| MQQQ | 3y | 463 | 0.17 | -0.06 | -0.03 | 0.28 | -0.10 | 1.0 | 0.199 | 1.3 | 0.1032 |
| MQQQ | 5y | 439 | -0.07 | 0.02 | 0.03 | 0.37 | -0.15 | 0.2 | 0.222 | 0.4 | 0.3402 |
| MQQQ | 10y | 379 | 0.06 | -0.12 | -0.13 | 0.56 | -0.30 | 0.6 | 0.171 | 2.1 | 0.0077 |
| QQQP | 1y | 487 | 0.14 | -0.02 | 0.10 | 0.16 | -0.04 | 1.2 | 0.123 | 1.4 | 0.0835 |
| QQQP | 3y | 463 | -0.01 | -0.20 | -0.04 | 0.28 | -0.10 | 0.3 | 0.199 | 0.4 | 0.3230 |
| QQQP | 5y | 439 | -0.33 | 0.07 | -0.11 | 0.37 | -0.15 | -0.5 | 0.222 | -0.8 | 0.7595 |
| QQQP | 10y | 379 | -0.24 | -0.14 | -0.05 | 0.56 | -0.30 | 0.1 | 0.171 | 0.3 | 0.3940 |

Nearest simulated case by lag-h autocorrelation (the iid case counts as 'no persistence'). READ WITH CARE: one lag-h number is a poor summary of a slow regime (the phi 0.995 cases show a small lag-h autocorrelation but a large dependence spread over many lags), so this matching is rough; the register quotes the RANGE of coverage over the regime cases, not a matched value.

| world | product | horizon | measured acf lag h | nearest case | its acf lag h | its phase-pooled coverage | its bb-mean coverage | t needed | t used |
|---|---|---|---|---|---|---|---|---|---|
| SPX | HYP_SPX_M | 1y | 0.13 | phi 0.98, share 0.02 | 0.11 | 0.787 | 0.703 | 3.12 | 1.99 |
| SPX | HYP_SPX_M | 3y | 0.48 | phi 0.995, share 0.05 | 0.34 | 0.497 | 0.443 | 6.13 | 2.07 |
| SPX | HYP_SPX_M | 5y | 0.58 | phi 0.995, share 0.05 | 0.30 | 0.583 | 0.500 | 5.46 | 2.16 |
| SPX | HYP_SPX_M | 10y | 0.54 | phi 0.995, share 0.05 | 0.11 | 0.765 | 0.680 | 4.90 | 2.57 |
| SPX | HYP_SPX_W | 1y | 0.07 | phi 0.995, share 0.02 | 0.10 | 0.560 | 0.460 | 5.11 | 1.99 |
| SPX | HYP_SPX_W | 3y | 0.14 | phi 0.98, share 0.02 | 0.14 | 0.810 | 0.730 | 2.91 | 2.07 |
| SPX | HYP_SPX_W | 5y | 0.23 | phi 0.995, share 0.02 | 0.17 | 0.715 | 0.610 | 4.10 | 2.16 |
| SPX | HYP_SPX_W | 10y | 0.13 | phi 0.995, share 0.05 | 0.11 | 0.765 | 0.680 | 4.90 | 2.57 |
| SPX | SPYQ | 1y | 0.01 | iid | -0.01 | 0.968 | 0.897 | 1.88 | 1.99 |
| SPX | SPYQ | 3y | -0.07 | iid | -0.05 | 0.970 | 0.907 | 1.83 | 2.07 |
| SPX | SPYQ | 5y | -0.06 | iid | -0.08 | 0.953 | 0.882 | 2.10 | 2.16 |
| SPX | SPYQ | 10y | -0.26 | iid | -0.19 | 0.983 | 0.885 | 2.12 | 2.57 |
| NDX | HYP_NDX_W | 1y | -0.05 | iid | -0.04 | 0.945 | 0.860 | 2.06 | 2.02 |
| NDX | HYP_NDX_W | 3y | -0.07 | iid | -0.10 | 0.953 | 0.855 | 2.15 | 2.20 |
| NDX | HYP_NDX_W | 5y | -0.19 | iid | -0.15 | 0.978 | 0.895 | 2.05 | 2.45 |
| NDX | HYP_NDX_W | 10y | -0.33 | iid | -0.30 | 0.998 | 0.915 | 2.21 | 4.30 |
| NDX | MQQQ | 1y | 0.11 | phi 0.98, share 0.02 | 0.09 | 0.785 | 0.685 | 3.01 | 2.02 |
| NDX | MQQQ | 3y | 0.17 | phi 0.98, share 0.05 | 0.16 | 0.843 | 0.698 | 3.24 | 2.20 |
| NDX | MQQQ | 5y | -0.07 | phi 0.98, share 0.02 | -0.04 | 0.902 | 0.782 | 2.84 | 2.45 |
| NDX | MQQQ | 10y | 0.06 | phi 0.995, share 0.05 | -0.21 | 0.860 | 0.667 | 5.87 | 4.30 |
| NDX | QQQP | 1y | 0.14 | phi 0.995, share 0.05 | 0.15 | 0.460 | 0.390 | 6.28 | 2.02 |
| NDX | QQQP | 3y | -0.01 | phi 0.995, share 0.02 | 0.06 | 0.698 | 0.595 | 4.26 | 2.20 |
| NDX | QQQP | 5y | -0.33 | iid | -0.15 | 0.978 | 0.895 | 2.05 | 2.45 |
| NDX | QQQP | 10y | -0.24 | phi 0.995, share 0.02 | -0.25 | 0.932 | 0.755 | 4.78 | 4.30 |

## 5. Monte Carlo error of the published bootstrap bounds

Each bound of the block-bootstrap mean and median intervals (block = horizon, 10,000 draws; seed 0 is the published value) recomputed with seeds 0, 1, 2, 3; the spread is the largest minus the smallest value of that bound, in pp a year. Fixed encoding.

| world | product | horizon | mean lo | mean hi | median lo | median hi | largest |
|---|---|---|---|---|---|---|---|
| NDX | HYP_NDX_W | 1y | 0.014 | 0.014 | 0.005 | 0.005 | 0.014 |
| NDX | HYP_NDX_W | 3y | 0.007 | 0.007 | 0.011 | 0.011 | 0.011 |
| NDX | HYP_NDX_W | 5y | 0.006 | 0.006 | 0.005 | 0.005 | 0.006 |
| NDX | HYP_NDX_W | 10y | 0.011 | 0.011 | 0.015 | 0.015 | 0.015 |
| NDX | MQQQ | 1y | 0.011 | 0.011 | 0.006 | 0.006 | 0.011 |
| NDX | MQQQ | 3y | 0.026 | 0.026 | 0.015 | 0.015 | 0.026 |
| NDX | MQQQ | 5y | 0.012 | 0.012 | 0.017 | 0.017 | 0.017 |
| NDX | MQQQ | 10y | 0.005 | 0.005 | 0.009 | 0.009 | 0.009 |
| NDX | QQQP | 1y | 0.026 | 0.026 | 0.005 | 0.005 | 0.026 |
| NDX | QQQP | 3y | 0.043 | 0.043 | 0.168 | 0.168 | 0.168 |
| NDX | QQQP | 5y | 0.038 | 0.038 | 0.063 | 0.063 | 0.063 |
| NDX | QQQP | 10y | 0.017 | 0.017 | 0.110 | 0.110 | 0.110 |
| SPX | HYP_SPX_M | 1y | 0.004 | 0.004 | 0.002 | 0.002 | 0.004 |
| SPX | HYP_SPX_M | 3y | 0.008 | 0.008 | 0.003 | 0.003 | 0.008 |
| SPX | HYP_SPX_M | 5y | 0.012 | 0.012 | 0.014 | 0.014 | 0.014 |
| SPX | HYP_SPX_M | 10y | 0.005 | 0.005 | 0.015 | 0.015 | 0.015 |
| SPX | HYP_SPX_W | 1y | 0.001 | 0.001 | 0.002 | 0.002 | 0.002 |
| SPX | HYP_SPX_W | 3y | 0.008 | 0.008 | 0.003 | 0.003 | 0.008 |
| SPX | HYP_SPX_W | 5y | 0.004 | 0.004 | 0.004 | 0.004 | 0.004 |
| SPX | HYP_SPX_W | 10y | 0.006 | 0.006 | 0.009 | 0.009 | 0.009 |
| SPX | SPYQ | 1y | 0.007 | 0.007 | 0.003 | 0.003 | 0.007 |
| SPX | SPYQ | 3y | 0.008 | 0.008 | 0.004 | 0.004 | 0.008 |
| SPX | SPYQ | 5y | 0.011 | 0.011 | 0.011 | 0.011 | 0.011 |
| SPX | SPYQ | 10y | 0.006 | 0.006 | 0.009 | 0.009 | 0.009 |

Largest movement: 0.168 pp (NDX QQQP 3y); largest at ten years 0.110 pp; largest for any mean bound 0.043 pp.


Wall time 157.3 s.
