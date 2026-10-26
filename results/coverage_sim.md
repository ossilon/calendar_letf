# Simulated coverage of the interval conventions

Coverage = share of 400 synthetic histories whose 95% interval contains the true constant. Synthetic gap at start s = constant + mean of the h monthly shocks from s (the study's overlap). Block-bootstrap intervals: block = h, t(k-1) x SE. Phase-pooled: non-overlapping windows per start phase, pooled, t(min k_p - 1) x SE (the headline). 't needed' = 95th percentile of |pooled mean - truth| / SE over runs; 't used' = the t multiplier the convention applies.

400 runs per case, 1000 bootstrap resamples per run; seeds in the JSON. Code fingerprint 5a341e6cdf5a.

## 1. Published configurations, independent monthly shocks

| world | horizon | starts n | h = block | k | df | coverage: bb mean | bb median | phase-pooled | bootstrap SE / true SD | pooled SE / true SD | t needed (pooled) | t used | acf of gaps at lag h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NDX | 1y | 489 | 12 | 40 | 39 | 0.863 | 0.870 | 0.940 | 0.77 | 0.96 | 2.07 | 2.02 | -0.04 |
| NDX | 3y | 465 | 36 | 12 | 11 | 0.865 | 0.885 | 0.958 | 0.73 | 0.97 | 2.13 | 2.20 | -0.10 |
| NDX | 5y | 441 | 60 | 7 | 6 | 0.858 | 0.907 | 0.978 | 0.68 | 0.98 | 2.25 | 2.45 | -0.15 |
| NDX | 10y | 381 | 120 | 3 | 2 | 0.922 | 0.943 | 0.998 | 0.57 | 1.05 | 2.34 | 4.30 | -0.29 |
| SPX | 1y | 909 | 12 | 75 | 74 | 0.885 | 0.877 | 0.955 | 0.79 | 0.98 | 1.93 | 1.99 | -0.02 |
| SPX | 3y | 885 | 36 | 24 | 23 | 0.912 | 0.902 | 0.968 | 0.84 | 1.07 | 1.87 | 2.07 | -0.05 |
| SPX | 5y | 861 | 60 | 14 | 13 | 0.875 | 0.890 | 0.965 | 0.74 | 0.99 | 2.10 | 2.16 | -0.09 |
| SPX | 10y | 801 | 120 | 6 | 5 | 0.875 | 0.892 | 0.980 | 0.68 | 1.00 | 2.23 | 2.57 | -0.18 |

Range over the eight cases: block-bootstrap mean 0.858-0.922, median 0.870-0.943, phase-pooled 0.940-0.998; bootstrap SE ratio 0.57-0.84.

## 2. Why the block bootstrap is short: block = window length, not only few blocks

| case | starts n | h = block | k | coverage: bb mean | bb median | phase-pooled | bootstrap SE / true SD |
|---|---|---|---|---|---|---|---|
| large k | 2412 | 12 | 201 | 0.892 | 0.902 | 0.953 | 0.83 |

A block bootstrap sees only the dependence inside one block. For a gap that is the mean of h shocks, blocks of length h lose about a third of the variance of the series mean at ANY block count (the Bartlett-type truncation at one window), and the few-block cases lose more on top.

## 3. Regime stress: a slow AR(1) component in the monthly shocks

| world | horizon | phi | share | half-life (months) | acf of gaps at lag h | at lag 2h | coverage: bb mean | phase-pooled | t needed (pooled) | t used |
|---|---|---|---|---|---|---|---|---|---|---|
| NDX | 1y | 0.98 | 0.02 | 34 | 0.08 | 0.05 | 0.720 | 0.810 | 3.07 | 2.02 |
| NDX | 1y | 0.98 | 0.05 | 34 | 0.20 | 0.13 | 0.608 | 0.698 | 4.25 | 2.02 |
| NDX | 1y | 0.995 | 0.02 | 138 | 0.05 | 0.05 | 0.485 | 0.575 | 4.75 | 2.02 |
| NDX | 1y | 0.995 | 0.05 | 138 | 0.16 | 0.12 | 0.393 | 0.463 | 6.29 | 2.02 |
| NDX | 3y | 0.98 | 0.02 | 34 | 0.05 | -0.04 | 0.755 | 0.848 | 2.92 | 2.20 |
| NDX | 3y | 0.98 | 0.05 | 34 | 0.17 | -0.02 | 0.740 | 0.815 | 3.35 | 2.20 |
| NDX | 3y | 0.995 | 0.02 | 138 | 0.04 | 0.00 | 0.580 | 0.677 | 4.11 | 2.20 |
| NDX | 3y | 0.995 | 0.05 | 138 | 0.20 | 0.05 | 0.510 | 0.595 | 5.51 | 2.20 |
| NDX | 5y | 0.98 | 0.02 | 34 | -0.05 | -0.13 | 0.777 | 0.915 | 2.95 | 2.45 |
| NDX | 5y | 0.98 | 0.05 | 34 | 0.01 | -0.14 | 0.780 | 0.877 | 3.27 | 2.45 |
| NDX | 5y | 0.995 | 0.02 | 138 | -0.02 | -0.10 | 0.583 | 0.743 | 4.28 | 2.45 |
| NDX | 5y | 0.995 | 0.05 | 138 | 0.08 | -0.09 | 0.482 | 0.605 | 5.74 | 2.45 |
| NDX | 10y | 0.98 | 0.02 | 34 | -0.28 | -0.13 | 0.887 | 0.993 | 2.76 | 4.30 |
| NDX | 10y | 0.98 | 0.05 | 34 | -0.27 | -0.14 | 0.840 | 0.978 | 3.41 | 4.30 |
| NDX | 10y | 0.995 | 0.02 | 138 | -0.23 | -0.16 | 0.748 | 0.932 | 4.75 | 4.30 |
| NDX | 10y | 0.995 | 0.05 | 138 | -0.20 | -0.19 | 0.680 | 0.882 | 5.73 | 4.30 |
| SPX | 1y | 0.98 | 0.02 | 34 | 0.12 | 0.09 | 0.695 | 0.777 | 3.05 | 1.99 |
| SPX | 1y | 0.98 | 0.05 | 34 | 0.25 | 0.18 | 0.657 | 0.728 | 3.53 | 1.99 |
| SPX | 1y | 0.995 | 0.02 | 138 | 0.09 | 0.08 | 0.475 | 0.552 | 4.69 | 1.99 |
| SPX | 1y | 0.995 | 0.05 | 138 | 0.24 | 0.21 | 0.393 | 0.422 | 6.68 | 1.99 |
| SPX | 3y | 0.98 | 0.02 | 34 | 0.15 | 0.02 | 0.767 | 0.838 | 2.97 | 2.07 |
| SPX | 3y | 0.98 | 0.05 | 34 | 0.27 | 0.08 | 0.728 | 0.810 | 3.13 | 2.07 |
| SPX | 3y | 0.995 | 0.02 | 138 | 0.16 | 0.09 | 0.517 | 0.610 | 4.77 | 2.07 |
| SPX | 3y | 0.995 | 0.05 | 138 | 0.34 | 0.20 | 0.515 | 0.565 | 5.49 | 2.07 |
| SPX | 5y | 0.98 | 0.02 | 34 | 0.09 | -0.06 | 0.818 | 0.910 | 2.48 | 2.16 |
| SPX | 5y | 0.98 | 0.05 | 34 | 0.15 | -0.05 | 0.787 | 0.873 | 2.87 | 2.16 |
| SPX | 5y | 0.995 | 0.02 | 138 | 0.16 | 0.05 | 0.570 | 0.688 | 4.70 | 2.16 |
| SPX | 5y | 0.995 | 0.05 | 138 | 0.31 | 0.10 | 0.542 | 0.598 | 5.64 | 2.16 |
| SPX | 10y | 0.98 | 0.02 | 34 | -0.10 | -0.14 | 0.858 | 0.958 | 2.37 | 2.57 |
| SPX | 10y | 0.98 | 0.05 | 34 | -0.06 | -0.15 | 0.850 | 0.930 | 2.70 | 2.57 |
| SPX | 10y | 0.995 | 0.02 | 138 | 0.05 | -0.16 | 0.698 | 0.812 | 3.94 | 2.57 |
| SPX | 10y | 0.995 | 0.05 | 138 | 0.08 | -0.15 | 0.615 | 0.723 | 4.85 | 2.57 |

## 4. Persistence measured in the real gap series (results/raw), and the nearest simulated case


SPX: autocorrelation of the per-start gap at lags h, 2h, 3h (h = horizon in months); se if independent = 1 / sqrt(n / h) (a conservative rule of thumb, 1.2-3.3 times the true sampling SD); 'iid expected' = the same statistic in the iid simulation (negative: few windows share one mean); 'excess' = (measured - iid expected) / se; the Monte Carlo columns use 4,000 iid series per configuration: null SD, excess in null SDs, and the one-sided p (share of null draws at or above the measured value).

| product | horizon | starts n | acf lag h | lag 2h | lag 3h | se if independent | iid expected | excess (se) | null SD | excess (MC SD) | p (MC) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HYP_SPX_M | 1y | 909 | 0.13 | 0.21 | 0.18 | 0.11 | -0.02 | 1.2 | 0.093 | 1.6 | 0.0587 |
| HYP_SPX_M | 3y | 885 | 0.48 | 0.44 | 0.44 | 0.20 | -0.05 | 2.6 | 0.156 | 3.4 | 0.0005 |
| HYP_SPX_M | 5y | 861 | 0.58 | 0.51 | 0.26 | 0.26 | -0.09 | 2.5 | 0.189 | 3.5 | 0.0000 |
| HYP_SPX_M | 10y | 801 | 0.54 | 0.07 | -0.30 | 0.39 | -0.18 | 1.9 | 0.223 | 3.2 | 0.0000 |
| HYP_SPX_W | 1y | 909 | 0.07 | 0.06 | 0.03 | 0.11 | -0.02 | 0.7 | 0.093 | 0.9 | 0.1870 |
| HYP_SPX_W | 3y | 885 | 0.14 | 0.18 | 0.12 | 0.20 | -0.05 | 0.9 | 0.156 | 1.3 | 0.1047 |
| HYP_SPX_W | 5y | 861 | 0.23 | 0.10 | -0.07 | 0.26 | -0.09 | 1.2 | 0.189 | 1.7 | 0.0485 |
| HYP_SPX_W | 10y | 801 | 0.13 | -0.01 | -0.24 | 0.39 | -0.18 | 0.8 | 0.223 | 1.4 | 0.0953 |
| SPYQ | 1y | 909 | 0.01 | -0.04 | -0.04 | 0.11 | -0.02 | 0.2 | 0.093 | 0.3 | 0.3855 |
| SPYQ | 3y | 885 | -0.07 | 0.02 | -0.03 | 0.20 | -0.05 | -0.1 | 0.156 | -0.1 | 0.5190 |
| SPYQ | 5y | 861 | -0.06 | -0.09 | -0.12 | 0.26 | -0.09 | 0.1 | 0.189 | 0.1 | 0.4450 |
| SPYQ | 10y | 801 | -0.26 | -0.24 | 0.03 | 0.39 | -0.18 | -0.2 | 0.223 | -0.3 | 0.6032 |

NDX: autocorrelation of the per-start gap at lags h, 2h, 3h (h = horizon in months); se if independent = 1 / sqrt(n / h) (a conservative rule of thumb, 1.2-3.3 times the true sampling SD); 'iid expected' = the same statistic in the iid simulation (negative: few windows share one mean); 'excess' = (measured - iid expected) / se; the Monte Carlo columns use 4,000 iid series per configuration: null SD, excess in null SDs, and the one-sided p (share of null draws at or above the measured value).

| product | horizon | starts n | acf lag h | lag 2h | lag 3h | se if independent | iid expected | excess (se) | null SD | excess (MC SD) | p (MC) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HYP_NDX_W | 1y | 489 | -0.04 | 0.07 | -0.10 | 0.16 | -0.04 | -0.0 | 0.123 | -0.1 | 0.5357 |
| HYP_NDX_W | 3y | 465 | -0.06 | 0.00 | -0.33 | 0.28 | -0.10 | 0.1 | 0.198 | 0.2 | 0.4173 |
| HYP_NDX_W | 5y | 441 | -0.18 | -0.17 | -0.20 | 0.37 | -0.15 | -0.1 | 0.223 | -0.1 | 0.5148 |
| HYP_NDX_W | 10y | 381 | -0.35 | 0.02 | -0.01 | 0.56 | -0.29 | -0.1 | 0.173 | -0.3 | 0.6025 |
| MQQQ | 1y | 489 | 0.11 | 0.06 | 0.08 | 0.16 | -0.04 | 1.0 | 0.123 | 1.2 | 0.1338 |
| MQQQ | 3y | 465 | 0.18 | -0.05 | -0.03 | 0.28 | -0.10 | 1.0 | 0.198 | 1.4 | 0.0980 |
| MQQQ | 5y | 441 | -0.06 | 0.01 | 0.03 | 0.37 | -0.15 | 0.2 | 0.223 | 0.4 | 0.3300 |
| MQQQ | 10y | 381 | 0.06 | -0.12 | -0.13 | 0.56 | -0.29 | 0.6 | 0.173 | 2.0 | 0.0103 |
| QQQP | 1y | 489 | 0.14 | -0.02 | 0.10 | 0.16 | -0.04 | 1.2 | 0.123 | 1.4 | 0.0872 |
| QQQP | 3y | 465 | 0.00 | -0.20 | -0.05 | 0.28 | -0.10 | 0.3 | 0.198 | 0.5 | 0.3160 |
| QQQP | 5y | 441 | -0.33 | 0.06 | -0.10 | 0.37 | -0.15 | -0.5 | 0.223 | -0.8 | 0.7588 |
| QQQP | 10y | 381 | -0.23 | -0.14 | -0.06 | 0.56 | -0.29 | 0.1 | 0.173 | 0.3 | 0.3920 |

Nearest simulated case by lag-h autocorrelation (the iid case counts as 'no persistence'). READ WITH CARE: one lag-h number is a poor summary of a slow regime (the phi 0.995 cases show a small lag-h autocorrelation but a large dependence spread over many lags), so this matching is rough; the register quotes the RANGE of coverage over the regime cases, not a matched value.

| world | product | horizon | measured acf lag h | nearest case | its acf lag h | its phase-pooled coverage | its bb-mean coverage | t needed | t used |
|---|---|---|---|---|---|---|---|---|---|
| SPX | HYP_SPX_M | 1y | 0.13 | phi 0.98, share 0.02 | 0.12 | 0.777 | 0.695 | 3.05 | 1.99 |
| SPX | HYP_SPX_M | 3y | 0.48 | phi 0.995, share 0.05 | 0.34 | 0.565 | 0.515 | 5.49 | 2.07 |
| SPX | HYP_SPX_M | 5y | 0.58 | phi 0.995, share 0.05 | 0.31 | 0.598 | 0.542 | 5.64 | 2.16 |
| SPX | HYP_SPX_M | 10y | 0.54 | phi 0.995, share 0.05 | 0.08 | 0.723 | 0.615 | 4.85 | 2.57 |
| SPX | HYP_SPX_W | 1y | 0.07 | phi 0.995, share 0.02 | 0.09 | 0.552 | 0.475 | 4.69 | 1.99 |
| SPX | HYP_SPX_W | 3y | 0.14 | phi 0.98, share 0.02 | 0.15 | 0.838 | 0.767 | 2.97 | 2.07 |
| SPX | HYP_SPX_W | 5y | 0.23 | phi 0.995, share 0.02 | 0.16 | 0.688 | 0.570 | 4.70 | 2.16 |
| SPX | HYP_SPX_W | 10y | 0.13 | phi 0.995, share 0.05 | 0.08 | 0.723 | 0.615 | 4.85 | 2.57 |
| SPX | SPYQ | 1y | 0.01 | iid | -0.02 | 0.955 | 0.885 | 1.93 | 1.99 |
| SPX | SPYQ | 3y | -0.07 | iid | -0.05 | 0.968 | 0.912 | 1.87 | 2.07 |
| SPX | SPYQ | 5y | -0.06 | iid | -0.09 | 0.965 | 0.875 | 2.10 | 2.16 |
| SPX | SPYQ | 10y | -0.26 | iid | -0.18 | 0.980 | 0.875 | 2.23 | 2.57 |
| NDX | HYP_NDX_W | 1y | -0.04 | iid | -0.04 | 0.940 | 0.863 | 2.07 | 2.02 |
| NDX | HYP_NDX_W | 3y | -0.06 | iid | -0.10 | 0.958 | 0.865 | 2.13 | 2.20 |
| NDX | HYP_NDX_W | 5y | -0.18 | iid | -0.15 | 0.978 | 0.858 | 2.25 | 2.45 |
| NDX | HYP_NDX_W | 10y | -0.35 | iid | -0.29 | 0.998 | 0.922 | 2.34 | 4.30 |
| NDX | MQQQ | 1y | 0.11 | phi 0.98, share 0.02 | 0.08 | 0.810 | 0.720 | 3.07 | 2.02 |
| NDX | MQQQ | 3y | 0.18 | phi 0.98, share 0.05 | 0.17 | 0.815 | 0.740 | 3.35 | 2.20 |
| NDX | MQQQ | 5y | -0.06 | phi 0.98, share 0.02 | -0.05 | 0.915 | 0.777 | 2.95 | 2.45 |
| NDX | MQQQ | 10y | 0.06 | phi 0.995, share 0.05 | -0.20 | 0.882 | 0.680 | 5.73 | 4.30 |
| NDX | QQQP | 1y | 0.14 | phi 0.995, share 0.05 | 0.16 | 0.463 | 0.393 | 6.29 | 2.02 |
| NDX | QQQP | 3y | 0.00 | phi 0.995, share 0.02 | 0.04 | 0.677 | 0.580 | 4.11 | 2.20 |
| NDX | QQQP | 5y | -0.33 | iid | -0.15 | 0.978 | 0.858 | 2.25 | 2.45 |
| NDX | QQQP | 10y | -0.23 | phi 0.995, share 0.02 | -0.23 | 0.932 | 0.748 | 4.75 | 4.30 |

## 5. Monte Carlo error of the published bootstrap bounds

Each bound of the block-bootstrap mean and median intervals (block = horizon, 10,000 draws; seed 0 is the published value) recomputed with seeds 0, 1, 2, 3; the spread is the largest minus the smallest value of that bound, in pp a year. Fixed encoding.

| world | product | horizon | mean lo | mean hi | median lo | median hi | largest |
|---|---|---|---|---|---|---|---|
| NDX | HYP_NDX_W | 1y | 0.014 | 0.014 | 0.005 | 0.005 | 0.014 |
| NDX | HYP_NDX_W | 3y | 0.008 | 0.008 | 0.011 | 0.011 | 0.011 |
| NDX | HYP_NDX_W | 5y | 0.006 | 0.006 | 0.006 | 0.006 | 0.006 |
| NDX | HYP_NDX_W | 10y | 0.011 | 0.011 | 0.014 | 0.014 | 0.014 |
| NDX | MQQQ | 1y | 0.006 | 0.006 | 0.007 | 0.007 | 0.007 |
| NDX | MQQQ | 3y | 0.025 | 0.025 | 0.014 | 0.014 | 0.025 |
| NDX | MQQQ | 5y | 0.012 | 0.012 | 0.015 | 0.015 | 0.015 |
| NDX | MQQQ | 10y | 0.005 | 0.005 | 0.010 | 0.010 | 0.010 |
| NDX | QQQP | 1y | 0.026 | 0.026 | 0.003 | 0.003 | 0.026 |
| NDX | QQQP | 3y | 0.043 | 0.043 | 0.158 | 0.158 | 0.158 |
| NDX | QQQP | 5y | 0.042 | 0.042 | 0.069 | 0.069 | 0.069 |
| NDX | QQQP | 10y | 0.015 | 0.015 | 0.093 | 0.093 | 0.093 |
| SPX | HYP_SPX_M | 1y | 0.004 | 0.004 | 0.002 | 0.002 | 0.004 |
| SPX | HYP_SPX_M | 3y | 0.008 | 0.008 | 0.003 | 0.003 | 0.008 |
| SPX | HYP_SPX_M | 5y | 0.012 | 0.012 | 0.013 | 0.013 | 0.013 |
| SPX | HYP_SPX_M | 10y | 0.005 | 0.005 | 0.015 | 0.015 | 0.015 |
| SPX | HYP_SPX_W | 1y | 0.001 | 0.001 | 0.002 | 0.002 | 0.002 |
| SPX | HYP_SPX_W | 3y | 0.008 | 0.008 | 0.003 | 0.003 | 0.008 |
| SPX | HYP_SPX_W | 5y | 0.004 | 0.004 | 0.005 | 0.005 | 0.005 |
| SPX | HYP_SPX_W | 10y | 0.006 | 0.006 | 0.009 | 0.009 | 0.009 |
| SPX | SPYQ | 1y | 0.007 | 0.007 | 0.003 | 0.003 | 0.007 |
| SPX | SPYQ | 3y | 0.008 | 0.008 | 0.003 | 0.003 | 0.008 |
| SPX | SPYQ | 5y | 0.011 | 0.011 | 0.010 | 0.010 | 0.011 |
| SPX | SPYQ | 10y | 0.006 | 0.006 | 0.010 | 0.010 | 0.010 |

Largest movement: 0.158 pp (NDX QQQP 3y); largest at ten years 0.093 pp; largest for any mean bound 0.043 pp.


Wall time 102.4 s.
