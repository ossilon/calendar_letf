# B14: volatility drag and enhanced compounding, calendar against daily

*Data: TradingView (via local export), FRED. Modeled funds at zero cost (the mechanism alone). Not investment advice.*

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
Zero cost. 2x: the passive study's designs (35% trigger); 3x: B1's designs (trigger 0.70 / 3). Study end 2026-09-30.
```

Zero cost throughout: the mechanism alone. Gap = log fund minus log daily twin (a year's figure is the gap over the window, not per year). Ratio = SS_period / SS_daily (below 1: the days reverse inside the periods). Trend score = (log index return)^2 / SS_daily over the WHOLE window: a mechanism, not a timing rule.

## S&P 500

| design | L | years | windows | ratio median | ratio < 1 | gap median | calendar > L x index | daily > L x index | formula slope | R2 (y = x) | median error | gap: chop / middle / trend |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SPYQ | 2 | 1 | 907 | 1.115 | 41% | -0.0016 | 57% | 52% | 1.145 | 0.305 | 0.0030 | +0.0020 / +0.0009 / -0.0065 |
| SPYQ | 2 | 3 | 883 | 1.226 | 34% | -0.0079 | 59% | 66% | 1.002 | 0.217 | 0.0069 | -0.0063 / -0.0041 / -0.0109 |
| SPYQ | 2 | 5 | 859 | 1.174 | 33% | -0.0118 | 66% | 71% | 0.951 | 0.130 | 0.0142 | -0.0546 / +0.0007 / -0.0218 |
| SPYQ | 2 | 10 | 799 | 1.175 | 34% | -0.0652 | 70% | 75% | 0.890 | -0.073 | 0.0249 | -0.1949 / +0.0002 / -0.0403 |
| HYP_SPX_M | 2 | 1 | 907 | 1.041 | 46% | -0.0004 | 54% | 52% | 0.910 | 0.972 | 0.0010 | +0.0019 / +0.0013 / -0.0029 |
| HYP_SPX_M | 2 | 3 | 883 | 1.057 | 43% | -0.0006 | 66% | 66% | 0.925 | 0.981 | 0.0020 | +0.0188 / +0.0013 / -0.0036 |
| HYP_SPX_M | 2 | 5 | 859 | 1.053 | 45% | +0.0007 | 70% | 71% | 0.935 | 0.985 | 0.0038 | +0.0474 / +0.0144 / -0.0091 |
| HYP_SPX_M | 2 | 10 | 799 | 0.992 | 52% | +0.0125 | 82% | 75% | 0.945 | 0.989 | 0.0074 | +0.0943 / +0.0277 / -0.0264 |
| HYP_SPX_W | 2 | 1 | 907 | 1.018 | 47% | -0.0001 | 51% | 52% | 1.020 | 0.927 | 0.0003 | +0.0002 / +0.0004 / -0.0006 |
| HYP_SPX_W | 2 | 3 | 883 | 0.966 | 55% | +0.0017 | 67% | 66% | 0.994 | 0.937 | 0.0007 | +0.0063 / +0.0033 / +0.0003 |
| HYP_SPX_W | 2 | 5 | 859 | 0.941 | 62% | +0.0053 | 70% | 71% | 0.983 | 0.943 | 0.0011 | +0.0175 / +0.0082 / +0.0026 |
| HYP_SPX_W | 2 | 10 | 799 | 0.913 | 68% | +0.0208 | 74% | 75% | 0.960 | 0.949 | 0.0036 | +0.0354 / +0.0278 / +0.0061 |
| HYP_SPX_W_3x_scaled | 3 | 1 | 907 | 1.018 | 47% | -0.0009 | 51% | 51% | 0.028 | -1.173 | 0.0012 | -0.0008 / +0.0002 / -0.0017 |
| HYP_SPX_W_3x_scaled | 3 | 3 | 883 | 0.966 | 55% | -0.0016 | 61% | 62% | 0.113 | -1.323 | 0.0025 | -0.0320 / +0.0061 / +0.0011 |
| HYP_SPX_W_3x_scaled | 3 | 5 | 859 | 0.941 | 62% | -0.0006 | 63% | 66% | 0.205 | -1.153 | 0.0039 | -0.0507 / +0.0074 / +0.0059 |
| HYP_SPX_W_3x_scaled | 3 | 10 | 799 | 0.940 | 68% | -0.0116 | 69% | 70% | 0.355 | -0.798 | 0.0150 | -0.0109 / -0.0340 / -0.0155 |
| HYP_SPX_M_3x_scaled | 3 | 1 | 907 | 1.076 | 44% | -0.0019 | 54% | 51% | 0.476 | -0.077 | 0.0038 | +0.0007 / +0.0030 / -0.0078 |
| HYP_SPX_M_3x_scaled | 3 | 3 | 883 | 1.089 | 35% | -0.0106 | 60% | 62% | 0.536 | 0.143 | 0.0095 | -0.0125 / -0.0055 / -0.0112 |
| HYP_SPX_M_3x_scaled | 3 | 5 | 859 | 1.115 | 32% | -0.0347 | 60% | 66% | 0.576 | 0.323 | 0.0169 | -0.0246 / -0.0433 / -0.0281 |
| HYP_SPX_M_3x_scaled | 3 | 10 | 799 | 1.192 | 41% | -0.0598 | 71% | 70% | 0.612 | 0.527 | 0.0351 | +0.2298 / -0.0580 / -0.0781 |
| SPYQ_3x_scaled | 3 | 1 | 907 | 1.143 | 39% | -0.0052 | 56% | 51% | 1.074 | 0.337 | 0.0107 | +0.0015 / +0.0046 / -0.0161 |
| SPYQ_3x_scaled | 3 | 3 | 883 | 1.253 | 29% | -0.0334 | 53% | 62% | 1.014 | 0.187 | 0.0384 | -0.1679 / -0.0225 / -0.0268 |
| SPYQ_3x_scaled | 3 | 5 | 859 | 1.261 | 23% | -0.0855 | 55% | 66% | 1.012 | 0.048 | 0.0918 | -0.3242 / -0.0427 / -0.0609 |
| SPYQ_3x_scaled | 3 | 10 | 799 | 1.326 | 23% | -0.2331 | 57% | 70% | 1.060 | -0.168 | 0.2135 | -0.3839 / -0.1351 / -0.1188 |

## Nasdaq-100

| design | L | years | windows | ratio median | ratio < 1 | gap median | calendar > L x index | daily > L x index | formula slope | R2 (y = x) | median error | gap: chop / middle / trend |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MQQQ | 2 | 1 | 487 | 0.860 | 63% | +0.0060 | 52% | 46% | 1.035 | 0.534 | 0.0028 | +0.0090 / +0.0050 / +0.0018 |
| MQQQ | 2 | 3 | 463 | 0.814 | 81% | +0.0239 | 62% | 59% | 0.970 | 0.610 | 0.0086 | +0.0277 / +0.0218 / +0.0211 |
| MQQQ | 2 | 5 | 439 | 0.794 | 83% | +0.0547 | 63% | 64% | 0.920 | 0.670 | 0.0145 | +0.0908 / +0.0495 / +0.0404 |
| MQQQ | 2 | 10 | 379 | 0.770 | 84% | +0.1301 | 68% | 65% | 0.782 | 0.600 | 0.0362 | +0.1252 / +0.1377 / +0.1169 |
| QQQP | 2 | 1 | 487 | 0.987 | 51% | +0.0034 | 48% | 46% | 0.804 | 0.078 | 0.0089 | +0.0104 / +0.0057 / -0.0049 |
| QQQP | 2 | 3 | 463 | 1.019 | 48% | +0.0082 | 57% | 59% | 1.234 | 0.136 | 0.0236 | -0.2038 / +0.0169 / +0.0195 |
| QQQP | 2 | 5 | 439 | 1.023 | 46% | +0.0024 | 58% | 64% | 1.429 | 0.180 | 0.0514 | -0.2268 / +0.0146 / +0.0359 |
| QQQP | 2 | 10 | 379 | 1.043 | 45% | -0.1839 | 51% | 65% | 1.390 | -0.319 | 0.2322 | -0.5194 / -0.1804 / +0.0330 |
| HYP_NDX_W | 2 | 1 | 487 | 0.891 | 71% | +0.0038 | 51% | 46% | 0.853 | 0.768 | 0.0009 | +0.0029 / +0.0059 / +0.0019 |
| HYP_NDX_W | 2 | 3 | 463 | 0.869 | 87% | +0.0154 | 62% | 59% | 0.760 | 0.666 | 0.0019 | +0.0361 / +0.0092 / +0.0115 |
| HYP_NDX_W | 2 | 5 | 439 | 0.815 | 94% | +0.0517 | 65% | 64% | 0.755 | 0.628 | 0.0043 | +0.0739 / +0.0314 / +0.0335 |
| HYP_NDX_W | 2 | 10 | 379 | 0.820 | 98% | +0.0877 | 68% | 65% | 0.768 | 0.527 | 0.0085 | +0.1771 / +0.0814 / +0.0693 |
| HYP_NDX_W_3x_scaled | 3 | 1 | 487 | 0.891 | 71% | +0.0096 | 48% | 45% | 0.766 | 0.479 | 0.0035 | +0.0077 / +0.0172 / +0.0051 |
| HYP_NDX_W_3x_scaled | 3 | 3 | 463 | 0.869 | 87% | +0.0377 | 58% | 55% | 0.594 | 0.042 | 0.0071 | +0.0915 / +0.0261 / +0.0295 |
| HYP_NDX_W_3x_scaled | 3 | 5 | 439 | 0.815 | 94% | +0.1311 | 61% | 57% | 0.581 | -0.358 | 0.0157 | +0.1975 / +0.0787 / +0.0715 |
| HYP_NDX_W_3x_scaled | 3 | 10 | 379 | 0.820 | 98% | +0.2556 | 62% | 55% | 0.600 | -1.320 | 0.0372 | +0.4038 / +0.2300 / +0.2030 |
| MQQQ_3x_scaled | 3 | 1 | 487 | 0.884 | 61% | +0.0116 | 50% | 45% | -0.016 | -0.292 | 0.0122 | +0.0201 / +0.0111 / +0.0049 |
| MQQQ_3x_scaled | 3 | 3 | 463 | 0.852 | 76% | +0.0445 | 49% | 55% | -0.376 | -0.528 | 0.0425 | -0.1407 / +0.0475 / +0.0556 |
| MQQQ_3x_scaled | 3 | 5 | 439 | 0.839 | 80% | -0.1385 | 56% | 57% | -0.518 | -0.846 | 0.1205 | -0.4938 / -0.0616 / +0.1143 |
| MQQQ_3x_scaled | 3 | 10 | 379 | 0.836 | 82% | -0.3623 | 48% | 55% | -1.277 | -3.580 | 0.6866 | -0.7831 / -0.3840 / -0.0521 |
| QQQP_3x_scaled | 3 | 1 | 487 | 0.944 | 53% | +0.0142 | 51% | 45% | 0.320 | -0.521 | 0.0310 | +0.0322 / +0.0207 / -0.0086 |
| QQQP_3x_scaled | 3 | 3 | 463 | 0.993 | 51% | +0.0359 | 57% | 55% | 0.348 | -0.334 | 0.0879 | -0.0672 / +0.0580 / +0.0663 |
| QQQP_3x_scaled | 3 | 5 | 439 | 1.013 | 49% | +0.0405 | 52% | 57% | 0.525 | -0.037 | 0.1485 | -0.1452 / -0.0510 / +0.1272 |
| QQQP_3x_scaled | 3 | 10 | 379 | 1.011 | 48% | +0.0026 | 61% | 55% | 0.335 | -0.679 | 0.1983 | -0.5091 / +0.1337 / +0.0639 |

## Planted paths (2x, zero cost, no trigger; ten years)

| path | index | daily | weekly | monthly | quarterly |
|---|---|---|---|---|---|
| trend +0.05% a day | 252.4% | 1141.3% | 1138.2% | 1125.3% | 1093.9% |
| chop +-1% every other day | 0.0% | -22.1% | -4.6% | -0.6% | -0.2% |
| AR(1) days, phi -0.2 | 83.6% | 159.8% | 183.9% | 192.4% | 193.4% |
| AR(1) days, phi +0.2 | -6.0% | -31.1% | -39.1% | -42.4% | -41.6% |

## Worked example: the index ends +50% after one year (2000 paths, zero cost, no trigger)

| annual vol | L | reset | median return | p5 / p95 | wiped | L x index |
|---|---|---|---|---|---|---|
| 10% | 2 | daily | 122.6% | 122.3% / 122.9% | 0.0% | 100% |
| 10% | 2 | weekly | 122.2% | 121.4% / 122.8% | 0.0% | 100% |
| 10% | 2 | monthly | 120.3% | 118.7% / 121.2% | 0.0% | 100% |
| 10% | 2 | quarterly | 115.8% | 113.5% / 116.6% | 0.0% | 100% |
| 10% | 3 | daily | 227.0% | 225.5% / 228.4% | 0.0% | 150% |
| 10% | 3 | weekly | 225.0% | 221.9% / 227.9% | 0.0% | 150% |
| 10% | 3 | monthly | 217.5% | 210.9% / 221.4% | 0.0% | 150% |
| 10% | 3 | quarterly | 200.2% | 192.1% / 203.1% | 0.0% | 150% |
| 20% | 2 | daily | 116.1% | 114.8% / 117.3% | 0.0% | 100% |
| 20% | 2 | weekly | 116.0% | 112.9% / 118.3% | 0.0% | 100% |
| 20% | 2 | monthly | 115.2% | 109.1% / 118.9% | 0.0% | 100% |
| 20% | 2 | quarterly | 112.9% | 104.5% / 116.2% | 0.0% | 100% |
| 20% | 3 | daily | 199.3% | 193.8% / 204.1% | 0.0% | 150% |
| 20% | 3 | weekly | 198.8% | 186.6% / 208.7% | 0.0% | 150% |
| 20% | 3 | monthly | 197.0% | 173.1% / 211.8% | 0.0% | 150% |
| 20% | 3 | quarterly | 190.0% | 160.3% / 201.8% | 0.0% | 150% |
| 40% | 2 | daily | 91.8% | 87.2% / 96.3% | 0.0% | 100% |
| 40% | 2 | weekly | 92.9% | 82.0% / 101.8% | 0.0% | 100% |
| 40% | 2 | monthly | 96.2% | 73.0% / 110.4% | 0.0% | 100% |
| 40% | 2 | quarterly | 102.0% | 66.5% / 114.5% | 0.0% | 100% |
| 40% | 3 | daily | 109.1% | 94.2% / 123.9% | 0.0% | 150% |
| 40% | 3 | weekly | 112.4% | 77.2% / 144.1% | 0.0% | 150% |
| 40% | 3 | monthly | 125.5% | 45.1% / 178.5% | 0.1% | 150% |
| 40% | 3 | quarterly | 151.2% | 18.0% / 195.7% | 2.3% | 150% |
