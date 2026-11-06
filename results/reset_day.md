# B12 + B10: the reset day and entry on any day

*Data: TradingView (via local export), FRED. Modeled funds, not live funds. Not investment advice.*

```
Inputs: 8 files; prices from <external>/library, rates from <external>/rates
  SP_SPX_daily.csv: 19333 rows, 1950-01-03 to 2026-11-02, sha256 b146c9af89cc
  SP_SPXTR_daily.csv: 9787 rows, 1988-01-04 to 2026-11-03, sha256 edab5090825e
  AMEX_SPY_daily.csv: 8498 rows, 1993-01-29 to 2026-11-02, sha256 643d6ef08b88
  NASDAQ_NDX_daily.csv: 10519 rows, 1985-01-31 to 2026-10-30, sha256 79d8e8688fa3
  NASDAQ_XNDX_daily.csv: 5019 rows, 2006-11-08 to 2026-10-30, sha256 d7dcc6dffa24
  NASDAQ_QQQ_daily.csv: 6955 rows, 1999-03-10 to 2026-10-30, sha256 f096cd6c6b75
  DFF.csv: 26424 rows, 1954-07-01 to 2026-11-03, sha256 e84a934a5014
  TB3MS.csv: 1112 rows, 1934-01-01 to 2026-08-01, sha256 ebf04b1ae5bc
SPX early-reset trigger: the AMEX:SPY price (daily low) from 1993-01-29, scaled to the SP:SPX price index before that; trigger basis 'etf'; drop 35% from the fund's base; fill mode 'level'.
SPX day counts: financing (reference rate and swap spread) ACT/360; expense ratio ACT/365 (calendar days between rows, so weekends and holidays accrue).
SPX reset dates: last NYSE session of the week / month / quarter from 1970-01-01 (calendar_letf/nyse.py, refuses data that lack it); before that the last row of the period.
NDX early-reset trigger: the NASDAQ:QQQ price (daily low) from 1999-03-10, scaled to the NASDAQ:NDX price index before that; trigger basis 'etf'; drop 35% from the fund's base; fill mode 'level'.
NDX day counts: financing (reference rate and swap spread) ACT/360; expense ratio ACT/365 (calendar days between rows, so weekends and holidays accrue).
NDX reset dates: last NYSE session of the week / month / quarter from 1970-01-01 (calendar_letf/nyse.py, refuses data that lack it); before that the last row of the period.
Encoding: fixed spread 2.6% of NAV: spread 2.60% of NAV a year + 1 x reference rate on the borrowed turn + product fee [ASSUMED]. Study end fixed at 2026-09-30; Monte Carlo seed 20261106.
```

Anchors: std = the prospectus day (last session of the period); mon-thu = the last session on or before that weekday; dN = on or before day N of the month; mKdN = on or before day N of the quarter's K-th month.

## S&P 500
### History (fixed cost, level fill)

| design | anchor | resets | CAGR | early resets | yearly gap vs twin (95%) | minus std, yearly (95%) | t / p / Holm p | 10y median gap | 10y mean [95%] |
|---|---|---|---|---|---|---|---|---|---|
| SPYQ | std | 307 | 11.53% | 1 | [-1.48, +0.29] too narrow | - | - | -0.54 | -0.68 [-1.90, +0.54] |
| SPYQ | m3d5 | 307 | 11.93% | 1 | [-1.16, +0.65] too narrow | [-0.26, +0.94] valid | +1.13 / 0.263 / 1.00 | -0.60 | -0.40 [-1.95, +1.16] |
| SPYQ | m3d10 | 307 | 12.00% | 1 | [-1.07, +0.71] too narrow | [-0.02, +0.85] valid | +1.91 / 0.059 / 1.00 | -0.35 | -0.24 [-1.72, +1.23] |
| SPYQ | m3d15 | 307 | 12.00% | 1 | [-1.08, +0.72] too narrow | [+0.10, +0.73] valid | +2.66 / 0.010 / 0.25 | -0.39 | -0.22 [-1.72, +1.28] |
| SPYQ | m3d20 | 307 | 11.68% | 1 | [-1.33, +0.42] too narrow | [-0.39, +0.66] valid | +0.51 / 0.609 / 1.00 | -0.88 | -0.46 [-1.49, +0.57] |
| SPYQ | m2d15 | 307 | 11.58% | 3 | [-1.83, +0.70] too narrow | [-1.22, +1.28] too narrow | +0.05 / 0.963 / 1.00 | -0.62 | -0.61 [-2.17, +0.95] |
| HYP_SPX_M | std | 921 | 12.57% | 0 | [-0.02, +0.71] too narrow | - | - | +0.29 | +0.38 [-0.59, +1.35] |
| HYP_SPX_M | d5 | 921 | 12.24% | 0 | [-0.37, +0.47] valid | [-0.61, +0.01] valid | -1.92 / 0.059 / 1.00 | +0.22 | +0.06 [-0.81, +0.93] |
| HYP_SPX_M | d10 | 921 | 12.33% | 0 | [-0.17, +0.44] too narrow | [-0.55, +0.14] too narrow | -1.21 / 0.230 / 1.00 | +0.23 | +0.13 [-0.63, +0.88] |
| HYP_SPX_M | d15 | 921 | 12.51% | 0 | [-0.03, +0.64] too narrow | [-0.34, +0.26] valid | -0.26 / 0.794 / 1.00 | +0.63 | +0.35 [-0.56, +1.25] |
| HYP_SPX_M | d20 | 921 | 11.93% | 0 | [-0.76, +0.29] too narrow | [-1.33, +0.17] too narrow | -1.54 / 0.128 / 1.00 | -0.24 | -0.19 [-0.82, +0.44] |
| HYP_SPX_W | std | 4004 | 12.35% | 0 | [-0.10, +0.42] too narrow | - | - | +0.29 | +0.19 [-0.36, +0.74] |
| HYP_SPX_W | mon | 3694 | 11.81% | 0 | [-0.64, -0.02] valid | [-0.90, -0.07] too narrow | -2.32 / 0.023 / 0.58 | -0.57 | -0.40 [-0.96, +0.15] |
| HYP_SPX_W | tue | 4001 | 12.25% | 0 | [-0.28, +0.38] too narrow | [-0.47, +0.26] valid | -0.57 / 0.569 / 1.00 | -0.28 | +0.04 [-0.67, +0.75] |
| HYP_SPX_W | wed | 4005 | 12.47% | 0 | [-0.03, +0.55] too narrow | [-0.06, +0.27] valid | +1.24 / 0.220 / 1.00 | +0.36 | +0.29 [-0.32, +0.89] |
| HYP_SPX_W | thu | 4004 | 12.34% | 0 | [-0.06, +0.37] too narrow | [-0.12, +0.13] too narrow | +0.03 / 0.976 / 1.00 | +0.35 | +0.17 [-0.35, +0.69] |

### 5000 simulated decades (252-day blocks): 10-year gap and the paired difference against std

| design | anchor | gap median | gap mean +/- SE | minus std (mean +/- SE) | z |
|---|---|---|---|---|---|
| SPYQ | std | +0.19 | -0.01 +/- 0.02 | +0.000 +/- 0.000 | - |
| SPYQ | m3d5 | +0.22 | -0.01 +/- 0.02 | +0.003 +/- 0.019 | +0.2 |
| SPYQ | m3d10 | +0.20 | -0.03 +/- 0.02 | -0.018 +/- 0.018 | -1.0 |
| SPYQ | m3d15 | +0.19 | -0.02 +/- 0.02 | -0.011 +/- 0.017 | -0.7 |
| SPYQ | m3d20 | +0.20 | -0.03 +/- 0.02 | -0.023 +/- 0.016 | -1.5 |
| SPYQ | m2d15 | +0.18 | -0.03 +/- 0.02 | -0.023 +/- 0.021 | -1.1 |
| HYP_SPX_M | std | +0.11 | +0.10 +/- 0.01 | +0.000 +/- 0.000 | - |
| HYP_SPX_M | d5 | +0.12 | +0.12 +/- 0.01 | +0.015 +/- 0.009 | +1.7 |
| HYP_SPX_M | d10 | +0.12 | +0.11 +/- 0.01 | +0.012 +/- 0.011 | +1.1 |
| HYP_SPX_M | d15 | +0.12 | +0.11 +/- 0.01 | +0.008 +/- 0.011 | +0.7 |
| HYP_SPX_M | d20 | +0.11 | +0.09 +/- 0.01 | -0.006 +/- 0.011 | -0.6 |
| HYP_SPX_W | std | -0.00 | +0.06 +/- 0.01 | +0.000 +/- 0.000 | - |
| HYP_SPX_W | mon | +0.01 | +0.07 +/- 0.01 | +0.015 +/- 0.006 | +2.6 |
| HYP_SPX_W | tue | +0.00 | +0.06 +/- 0.01 | +0.005 +/- 0.007 | +0.7 |
| HYP_SPX_W | wed | -0.01 | +0.07 +/- 0.01 | +0.007 +/- 0.007 | +1.0 |
| HYP_SPX_W | thu | -0.01 | +0.06 +/- 0.01 | +0.004 +/- 0.006 | +0.6 |

### B10: entry on every trading day (standard day)

| design | years | starts | median gap | wins | mean [95%] | month-end starts median | entry L p5 / median / p95 | gap by entry L: <1.9 / 1.9-2.1 / >2.1 |
|---|---|---|---|---|---|---|---|---|
| SPYQ | 1 | 18998 | +0.16 | 56% | -0.27 [-0.91, +0.36] | +0.15 | 1.84 / 1.98 / 2.19 | +0.35 (n 3031) / +0.17 (n 13474) / -0.36 (n 2493) |
| SPYQ | 10 | 16737 | -0.53 | 44% | -0.68 [-1.89, +0.54] | -0.54 | 1.84 / 1.98 / 2.19 | +0.09 (n 2625) / -0.73 (n 11821) / -0.97 (n 2291) |
| HYP_SPX_M | 1 | 19039 | +0.04 | 52% | +0.32 [-0.05, +0.69] | +0.04 | 1.91 / 1.99 / 2.11 | +0.40 (n 597) / +0.02 (n 17342) / +0.26 (n 1100) |
| HYP_SPX_M | 10 | 16778 | +0.29 | 58% | +0.38 [-0.59, +1.35] | +0.29 | 1.91 / 1.99 / 2.10 | +0.41 (n 512) / +0.28 (n 15322) / +0.39 (n 944) |
| HYP_SPX_W | 1 | 19056 | +0.01 | 52% | +0.13 [-0.08, +0.35] | +0.02 | 1.96 / 2.00 / 2.05 | +0.89 (n 40) / +0.01 (n 18886) / +0.47 (n 130) |
| HYP_SPX_W | 10 | 16795 | +0.28 | 69% | +0.19 [-0.36, +0.74] | +0.28 | 1.96 / 2.00 / 2.04 | +0.36 (n 30) / +0.28 (n 16655) / +0.42 (n 110) |

## Nasdaq-100
### History (fixed cost, level fill)

| design | anchor | resets | CAGR | early resets | yearly gap vs twin (95%) | minus std, yearly (95%) | t / p / Holm p | 10y median gap | 10y mean [95%] |
|---|---|---|---|---|---|---|---|---|---|
| MQQQ | std | 501 | 15.05% | 1 | [-1.53, +2.04] too narrow | - | - | +1.35 | +1.04 [-2.23, +4.31] |
| MQQQ | d5 | 500 | 14.96% | 1 | [-1.86, +2.15] too narrow | [-0.84, +0.63] too narrow | -0.28 / 0.778 / 1.00 | +1.28 | +1.21 [-2.74, +5.17] |
| MQQQ | d10 | 500 | 15.31% | 1 | [-1.17, +2.10] too narrow | [-0.90, +1.33] too narrow | +0.39 / 0.700 / 1.00 | +1.49 | +1.14 [-2.78, +5.05] |
| MQQQ | d15 | 500 | 16.14% | 0 | [+0.22, +2.19] too narrow | [-0.85, +2.75] too narrow | +1.07 / 0.292 / 1.00 | +1.74 | +1.55 [-1.95, +5.06] |
| MQQQ | d20 | 500 | 14.82% | 0 | [-1.11, +1.20] valid | [-1.75, +1.34] valid | -0.27 / 0.787 / 1.00 | +0.19 | +0.39 [-2.21, +3.00] |
| QQQP | std | 167 | 11.73% | 4 | [-6.06, +0.57] too narrow | - | - | -2.09 | -2.44 [-10.85, +5.97] |
| QQQP | m3d5 | 167 | 13.08% | 4 | [-4.55, +1.22] too narrow | [-0.46, +2.63] valid | +1.42 / 0.164 / 1.00 | -2.35 | -1.41 [-10.43, +7.60] |
| QQQP | m3d10 | 167 | 11.87% | 4 | [-6.84, +1.26] too narrow | [-2.54, +2.46] too narrow | -0.03 / 0.974 / 1.00 | -2.43 | -2.71 [-15.22, +9.80] |
| QQQP | m3d15 | 167 | 14.10% | 2 | [-2.91, +1.66] too narrow | [+0.20, +4.04] too narrow | +2.23 / 0.031 / 0.72 | +0.23 | +0.05 [-5.32, +5.42] |
| QQQP | m3d20 | 167 | 13.02% | 3 | [-4.02, +0.82] too narrow | [-0.31, +2.60] too narrow | +1.59 / 0.120 / 1.00 | -1.09 | -1.13 [-5.74, +3.49] |
| QQQP | m2d15 | 167 | 14.37% | 4 | [-2.99, +2.04] too narrow | [+0.03, +4.51] too narrow | +2.05 / 0.047 / 1.00 | -0.81 | +0.01 [-6.14, +6.17] |
| HYP_NDX_W | std | 2174 | 15.83% | 0 | [+0.29, +1.47] too narrow | - | - | +1.13 | +1.17 [-0.24, +2.58] |
| HYP_NDX_W | mon | 1981 | 14.79% | 0 | [-0.80, +0.75] too narrow | [-1.73, -0.10] valid | -2.26 / 0.029 / 0.71 | +0.36 | +0.12 [-1.84, +2.08] |
| HYP_NDX_W | tue | 2172 | 15.07% | 0 | [-0.73, +1.20] valid | [-1.70, +0.40] valid | -1.25 / 0.219 / 1.00 | +0.97 | +0.64 [-1.60, +2.87] |
| HYP_NDX_W | wed | 2174 | 15.78% | 0 | [+0.18, +1.56] too narrow | [-0.61, +0.58] too narrow | -0.05 / 0.960 / 1.00 | +1.36 | +1.19 [-1.22, +3.60] |
| HYP_NDX_W | thu | 2174 | 15.86% | 0 | [+0.38, +1.45] too narrow | [-0.53, +0.59] too narrow | +0.11 / 0.916 / 1.00 | +1.08 | +1.21 [-1.07, +3.50] |

### 5000 simulated decades (252-day blocks): 10-year gap and the paired difference against std

| design | anchor | gap median | gap mean +/- SE | minus std (mean +/- SE) | z |
|---|---|---|---|---|---|
| MQQQ | std | +0.67 | +0.39 +/- 0.02 | +0.000 +/- 0.000 | - |
| MQQQ | d5 | +0.71 | +0.40 +/- 0.02 | +0.016 +/- 0.019 | +0.9 |
| MQQQ | d10 | +0.66 | +0.40 +/- 0.02 | +0.011 +/- 0.024 | +0.5 |
| MQQQ | d15 | +0.68 | +0.41 +/- 0.02 | +0.021 +/- 0.025 | +0.9 |
| MQQQ | d20 | +0.68 | +0.43 +/- 0.02 | +0.043 +/- 0.024 | +1.8 |
| QQQP | std | -0.85 | -1.17 +/- 0.04 | +0.000 +/- 0.000 | - |
| QQQP | m3d5 | -0.76 | -1.12 +/- 0.04 | +0.053 +/- 0.039 | +1.4 |
| QQQP | m3d10 | -0.74 | -1.08 +/- 0.04 | +0.091 +/- 0.037 | +2.5 |
| QQQP | m3d15 | -0.74 | -1.08 +/- 0.04 | +0.088 +/- 0.034 | +2.6 |
| QQQP | m3d20 | -0.79 | -1.12 +/- 0.04 | +0.053 +/- 0.032 | +1.7 |
| QQQP | m2d15 | -0.83 | -1.14 +/- 0.04 | +0.034 +/- 0.041 | +0.8 |
| HYP_NDX_W | std | +0.61 | +0.63 +/- 0.01 | +0.000 +/- 0.000 | - |
| HYP_NDX_W | mon | +0.66 | +0.66 +/- 0.01 | +0.035 +/- 0.012 | +3.0 |
| HYP_NDX_W | tue | +0.62 | +0.64 +/- 0.01 | +0.014 +/- 0.012 | +1.1 |
| HYP_NDX_W | wed | +0.60 | +0.62 +/- 0.01 | -0.010 +/- 0.013 | -0.8 |
| HYP_NDX_W | thu | +0.60 | +0.62 +/- 0.01 | -0.006 +/- 0.010 | -0.6 |

### B10: entry on every trading day (standard day)

| design | years | starts | median gap | wins | mean [95%] | month-end starts median | entry L p5 / median / p95 | gap by entry L: <1.9 / 1.9-2.1 / >2.1 |
|---|---|---|---|---|---|---|---|---|
| MQQQ | 1 | 10246 | +0.76 | 69% | +0.95 [-0.55, +2.46] | +0.73 | 1.87 / 1.99 / 2.18 | +0.98 (n 1035) / +0.74 (n 8080) / +1.04 (n 1131) |
| MQQQ | 10 | 7985 | +1.34 | 91% | +1.01 [-2.34, +4.37] | +1.34 | 1.86 / 1.99 / 2.18 | +1.21 (n 857) / +1.35 (n 6223) / +1.53 (n 905) |
| QQQP | 1 | 10206 | +0.97 | 60% | -0.34 [-2.32, +1.64] | +0.99 | 1.77 / 1.96 / 2.31 | +0.95 (n 2858) / +1.15 (n 5725) / -0.65 (n 1623) |
| QQQP | 10 | 7945 | -2.09 | 30% | -2.45 [-10.89, +6.00] | -2.09 | 1.76 / 1.97 / 2.31 | -2.04 (n 2173) / -2.09 (n 4386) / -2.19 (n 1386) |
| HYP_NDX_W | 1 | 10245 | +0.44 | 71% | +1.04 [+0.14, +1.95] | +0.42 | 1.94 / 2.00 / 2.07 | +1.46 (n 119) / +0.42 (n 9884) / +1.32 (n 242) |
| HYP_NDX_W | 10 | 7984 | +1.13 | 96% | +1.17 [-0.25, +2.58] | +1.13 | 1.94 / 2.00 / 2.07 | +1.32 (n 100) / +1.12 (n 7675) / +1.32 (n 209) |
