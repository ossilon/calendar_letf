# B1: 3x calendar resets against 3x daily twins

*Data: TradingView (via local export), FRED. Every 3x calendar fund is HYPOTHETICAL; the real UPRO and TQQQ are price-only overlays. Not investment advice.*

```
Inputs: 10 files; prices from <external>/library, rates from <external>/rates
  SP_SPX_daily.csv: 19333 rows, 1950-01-03 to 2026-11-02, sha256 b146c9af89cc
  SP_SPXTR_daily.csv: 9787 rows, 1988-01-04 to 2026-11-03, sha256 edab5090825e
  AMEX_SPY_daily.csv: 8498 rows, 1993-01-29 to 2026-11-02, sha256 643d6ef08b88
  NASDAQ_NDX_daily.csv: 10519 rows, 1985-01-31 to 2026-10-30, sha256 79d8e8688fa3
  NASDAQ_XNDX_daily.csv: 5019 rows, 2006-11-08 to 2026-10-30, sha256 d7dcc6dffa24
  NASDAQ_QQQ_daily.csv: 6955 rows, 1999-03-10 to 2026-10-30, sha256 f096cd6c6b75
  AMEX_UPRO_daily.csv: 4345 rows, 2009-06-25 to 2026-10-02, sha256 17d862355823
  NASDAQ_TQQQ_daily.csv: 4206 rows, 2010-02-11 to 2026-10-30, sha256 ae88fcb39ab3
  DFF.csv: 26424 rows, 1954-07-01 to 2026-11-03, sha256 e84a934a5014
  TB3MS.csv: 1112 rows, 1934-01-01 to 2026-08-01, sha256 ebf04b1ae5bc
SPX early-reset trigger: the AMEX:SPY price (daily low) from 1993-01-29, scaled to the SP:SPX price index before that; trigger basis 'etf'; drop 35% from the fund's base; fill mode 'level'.
SPX day counts: financing (reference rate and swap spread) ACT/360; expense ratio ACT/365 (calendar days between rows, so weekends and holidays accrue).
SPX reset dates: last NYSE session of the week / month / quarter from 1970-01-01 (calendar_letf/nyse.py, refuses data that lack it); before that the last row of the period.
NDX early-reset trigger: the NASDAQ:QQQ price (daily low) from 1999-03-10, scaled to the NASDAQ:NDX price index before that; trigger basis 'etf'; drop 35% from the fund's base; fill mode 'level'.
NDX day counts: financing (reference rate and swap spread) ACT/360; expense ratio ACT/365 (calendar days between rows, so weekends and holidays accrue).
NDX reset dates: last NYSE session of the week / month / quarter from 1970-01-01 (calendar_letf/nyse.py, refuses data that lack it); before that the last row of the period.
B1 trigger rules replace the 35% drop above: none none, scaled 23.33%, d20 20.00%, d25 25.00%, d30 30.00%, fixed35 35.00%.
Study end fixed at 2026-09-30; Monte Carlo seed 20261106.
```

Every 3x calendar fund here is HYPOTHETICAL. Trigger rules: none = no intra-period reset: an in-period index fall of 1/3 wipes the fund out; scaled = early reset at a 23.33% index fall: the 70% fund loss that 35% gives at 2x; d20 = sensitivity: early reset at a 20% index fall; d25 = sensitivity: early reset at a 25% index fall; d30 = sensitivity: early reset at a 30% index fall; fixed35 = the live 2x funds' 35% trigger kept at 3x: a 1/3 fall wipes the fund out first, so it can never fire.

## S&P 500

Cost cases (spread per NAV a year): zero 0.00%; nport 2.23%; double 4.46% (base: nport); the rate on 2 borrowed turns; fee 1.00%.

### Full history per trigger rule (base cost, level fill)

| trigger | design | CAGR | max DD | twin CAGR | wiped out | early resets | eras | yearly gap vs twin (95%) |
|---|---|---|---|---|---|---|---|---|
| none | HYP_SPX_W_3x_none | 14.70% | -98.1% | 14.20% | - | 0 | - | [-0.41, +1.30] too narrow |
| none | HYP_SPX_M_3x_none | 15.19% | -97.4% | 14.20% | - | 0 | - | [-0.20, +1.92] too narrow |
| none | SPYQ_3x_none | -100.00% | -100.0% | 14.20% | 2008-11-20 (2008-09) | 0 | - | n/a |
| scaled | HYP_SPX_W_3x_scaled | 13.83% | -98.5% | 14.20% | - | 2 | 1987 Aug-Dec, 2008-09 | [-0.99, +0.31] valid |
| scaled | HYP_SPX_M_3x_scaled | 14.15% | -98.0% | 14.20% | - | 3 | 1987 Aug-Dec, 2008-09, 2020 Feb-Dec | [-0.88, +0.73] too narrow |
| scaled | SPYQ_3x_scaled | 10.97% | -99.2% | 14.20% | - | 8 | 1973-74, 1987 Aug-Dec, 2000-02, 2008-09, 2020 Feb-Dec, other | [-5.51, -0.37] valid |
| d20 | HYP_SPX_W_3x_d20 | 14.34% | -98.2% | 14.20% | - | 2 | 1987 Aug-Dec, 2008-09 | [-0.38, +0.62] too narrow |
| d20 | HYP_SPX_M_3x_d20 | 14.01% | -98.7% | 14.20% | - | 5 | 1987 Aug-Dec, 2000-02, 2008-09, 2020 Feb-Dec | [-1.22, +0.83] valid |
| d20 | SPYQ_3x_d20 | 12.90% | -98.7% | 14.20% | - | 9 | 1973-74, 1987 Aug-Dec, 2000-02, 2008-09, 2020 Feb-Dec, other | [-2.94, +0.56] valid |
| d25 | HYP_SPX_W_3x_d25 | 14.70% | -98.1% | 14.20% | - | 0 | - | [-0.41, +1.30] too narrow |
| d25 | HYP_SPX_M_3x_d25 | 13.60% | -98.3% | 14.20% | - | 3 | 1987 Aug-Dec, 2008-09, 2020 Feb-Dec | [-1.74, +0.61] valid |
| d25 | SPYQ_3x_d25 | 10.66% | -99.1% | 14.20% | - | 6 | 1973-74, 1987 Aug-Dec, 2008-09, 2020 Feb-Dec, other | [-5.97, -0.50] valid |
| d30 | HYP_SPX_W_3x_d30 | 14.70% | -98.1% | 14.20% | - | 0 | - | [-0.41, +1.30] too narrow |
| d30 | HYP_SPX_M_3x_d30 | 13.72% | -97.4% | 14.20% | - | 1 | 1987 Aug-Dec | [-3.28, +2.36] too narrow |
| d30 | SPYQ_3x_d30 | 7.87% | -99.7% | 14.20% | - | 3 | 1987 Aug-Dec, 2008-09, 2020 Feb-Dec | [-11.15, -0.55] too narrow |
| fixed35 | HYP_SPX_W_3x_fixed35 | 14.70% | -98.1% | 14.20% | - | 0 | - | [-0.41, +1.30] too narrow |
| fixed35 | HYP_SPX_M_3x_fixed35 | 15.19% | -97.4% | 14.20% | - | 0 | - | [-0.20, +1.92] too narrow |
| fixed35 | SPYQ_3x_fixed35 | -100.00% | -100.0% | 14.20% | 2008-11-20 (2008-09) | 0 | - | n/a |

### Multi-start gap against the 3x daily twin (base cost; phase-pooled 95% interval)

| trigger | design | years | starts | median gap | p10 / p90 | calendar wins | mean [95%] | noisy |
|---|---|---|---|---|---|---|---|---|
| none | HYP_SPX_W_3x_none | 1 | 907 | +0.04 | -1.55 / +2.38 | 51% | +0.32 [-0.28, +0.91] | yes |
| none | HYP_SPX_W_3x_none | 3 | 883 | +0.29 | -1.35 / +2.53 | 58% | +0.53 [-0.45, +1.50] | yes |
| none | HYP_SPX_W_3x_none | 5 | 859 | +0.46 | -1.36 / +2.52 | 65% | +0.57 [-0.58, +1.71] | yes |
| none | HYP_SPX_W_3x_none | 10 | 799 | +0.81 | -1.85 / +2.61 | 68% | +0.57 [-1.13, +2.27] | yes |
| none | HYP_SPX_M_3x_none | 1 | 907 | +0.02 | -3.22 / +5.02 | 50% | +0.67 [-0.34, +1.67] | yes |
| none | HYP_SPX_M_3x_none | 3 | 883 | +0.15 | -2.46 / +4.94 | 53% | +0.80 [-0.45, +2.05] | yes |
| none | HYP_SPX_M_3x_none | 5 | 859 | +0.40 | -2.12 / +4.97 | 57% | +0.89 [-0.73, +2.51] | yes |
| none | HYP_SPX_M_3x_none | 10 | 799 | +0.53 | -2.04 / +5.54 | 57% | +0.94 [-1.89, +3.77] | yes |
| none | SPYQ_3x_none | 1 | 704 | -0.18 | -10.03 / +3.86 | 48% | -1.95 [-4.61, +0.72] | yes |
| none | SPYQ_3x_none | 3 | 704 | -1.27 | -13.67 / +2.40 | 33% | -5.35 [-12.45, +1.76] | yes |
| none | SPYQ_3x_none | 5 | 704 | -1.26 | -15.23 / +1.45 | 22% | -9.25 [-24.49, +5.99] | yes |
| none | SPYQ_3x_none | 10 | 704 | -3.79 | -99.80 / +0.53 | 18% | -18.78 [-63.10, +25.53] | yes |
| scaled | HYP_SPX_W_3x_scaled | 1 | 907 | -0.03 | -1.79 / +2.08 | 49% | +0.02 [-0.47, +0.51] | yes |
| scaled | HYP_SPX_W_3x_scaled | 3 | 883 | -0.00 | -1.71 / +1.54 | 50% | -0.19 [-0.85, +0.47] | yes |
| scaled | HYP_SPX_W_3x_scaled | 5 | 859 | +0.03 | -2.51 / +1.25 | 51% | -0.26 [-1.05, +0.53] | yes |
| scaled | HYP_SPX_W_3x_scaled | 10 | 799 | -0.14 | -1.93 / +0.97 | 43% | -0.40 [-1.57, +0.77] | yes |
| scaled | HYP_SPX_M_3x_scaled | 1 | 907 | -0.20 | -3.61 / +4.24 | 47% | +0.10 [-0.81, +1.00] | yes |
| scaled | HYP_SPX_M_3x_scaled | 3 | 883 | -0.24 | -2.87 / +2.83 | 45% | -0.11 [-1.16, +0.93] | yes |
| scaled | HYP_SPX_M_3x_scaled | 5 | 859 | -0.67 | -2.53 / +2.78 | 42% | -0.14 [-1.36, +1.09] | yes |
| scaled | HYP_SPX_M_3x_scaled | 10 | 799 | -0.56 | -2.04 / +2.65 | 36% | -0.03 [-1.92, +1.87] | yes |
| scaled | SPYQ_3x_scaled | 1 | 907 | +0.05 | -9.82 / +4.40 | 50% | -1.75 [-3.68, +0.18] | yes |
| scaled | SPYQ_3x_scaled | 3 | 883 | -1.05 | -11.91 / +3.06 | 39% | -2.43 [-4.73, -0.13] | no |
| scaled | SPYQ_3x_scaled | 5 | 859 | -1.48 | -9.44 / +2.05 | 31% | -2.82 [-5.33, -0.30] | no |
| scaled | SPYQ_3x_scaled | 10 | 799 | -2.56 | -8.64 / +0.39 | 18% | -3.18 [-6.60, +0.24] | yes |

### Fills: the close and next-close fills against the level fill (gap risk)

| trigger | design | fill | early resets | worst fill loss | on | level fill loss | wiped | CAGR |
|---|---|---|---|---|---|---|---|---|
| scaled | HYP_SPX_W_3x_scaled | close | 1 | -48.8% | 1987-10-20 | -70.0% | - | 14.59% |
| scaled | HYP_SPX_W_3x_scaled | next_close | 1 | -25.9% | 1987-10-21 | -70.0% | - | 14.75% |
| scaled | HYP_SPX_M_3x_scaled | close | 3 | -91.0% | 1987-10-19 | -70.0% | - | 12.65% |
| scaled | HYP_SPX_M_3x_scaled | next_close | 3 | -79.9% | 1987-10-20 | -70.0% | - | 14.61% |
| scaled | SPYQ_3x_scaled | close | 8 | -91.0% | 1987-10-19 | -70.0% | - | 9.83% |
| scaled | SPYQ_3x_scaled | next_close | 9 | -79.9% | 1987-10-20 | -70.0% | - | 11.91% |
| d20 | HYP_SPX_W_3x_d20 | close | 1 | -61.5% | 1987-10-19 | -60.0% | - | 14.37% |
| d20 | HYP_SPX_W_3x_d20 | next_close | 1 | -48.8% | 1987-10-20 | -60.0% | - | 14.59% |
| d20 | HYP_SPX_M_3x_d20 | close | 5 | -91.0% | 1987-10-19 | -60.0% | - | 12.43% |
| d20 | HYP_SPX_M_3x_d20 | next_close | 5 | -79.9% | 1987-10-20 | -60.0% | - | 13.68% |
| d20 | SPYQ_3x_d20 | close | 9 | -91.0% | 1987-10-19 | -60.0% | - | 10.98% |
| d20 | SPYQ_3x_d20 | next_close | 9 | -79.9% | 1987-10-20 | -60.0% | - | 12.67% |
| d25 | HYP_SPX_W_3x_d25 | close | 0 | n/a | - | -75.0% | - | 14.70% |
| d25 | HYP_SPX_W_3x_d25 | next_close | 0 | n/a | - | -75.0% | - | 14.70% |
| d25 | HYP_SPX_M_3x_d25 | close | 3 | -91.0% | 1987-10-19 | -75.0% | - | 12.65% |
| d25 | HYP_SPX_M_3x_d25 | next_close | 3 | -79.9% | 1987-10-20 | -75.0% | - | 14.61% |
| d25 | SPYQ_3x_d25 | close | 6 | -91.0% | 1987-10-19 | -75.0% | - | 10.02% |
| d25 | SPYQ_3x_d25 | next_close | 7 | -79.9% | 1987-10-20 | -75.0% | - | 11.45% |
| d30 | HYP_SPX_W_3x_d30 | close | 0 | n/a | - | -90.0% | - | 14.70% |
| d30 | HYP_SPX_W_3x_d30 | next_close | 0 | n/a | - | -90.0% | - | 14.70% |
| d30 | HYP_SPX_M_3x_d30 | close | 1 | -91.0% | 1987-10-19 | -90.0% | - | 13.67% |
| d30 | HYP_SPX_M_3x_d30 | next_close | 1 | -79.9% | 1987-10-20 | -90.0% | - | 14.67% |
| d30 | SPYQ_3x_d30 | close | 3 | -92.6% | 2020-03-23 | -90.0% | - | 7.65% |
| d30 | SPYQ_3x_d30 | next_close | 1 | -79.9% | 1987-10-20 | -90.0% | 2008-11-20 | -100.00% |

### Costs (trigger scaled, 10-year multi-start)

| cost | design | CAGR | twin CAGR | median gap | mean [95%] |
|---|---|---|---|---|---|
| zero | HYP_SPX_W_3x_scaled | 16.44% | 16.82% | -0.14 | -0.41 [-1.60, +0.78] |
| zero | HYP_SPX_M_3x_scaled | 16.76% | 16.82% | -0.58 | -0.04 [-1.97, +1.90] |
| zero | SPYQ_3x_scaled | 13.52% | 16.82% | -2.57 | -3.24 [-6.65, +0.17] |
| nport | HYP_SPX_W_3x_scaled | 13.83% | 14.20% | -0.14 | -0.40 [-1.57, +0.77] |
| nport | HYP_SPX_M_3x_scaled | 14.15% | 14.20% | -0.56 | -0.03 [-1.92, +1.87] |
| nport | SPYQ_3x_scaled | 10.97% | 14.20% | -2.56 | -3.18 [-6.60, +0.24] |
| double | HYP_SPX_W_3x_scaled | 11.28% | 11.64% | -0.14 | -0.39 [-1.53, +0.75] |
| double | HYP_SPX_M_3x_scaled | 11.60% | 11.64% | -0.53 | -0.02 [-1.88, +1.84] |
| double | SPYQ_3x_scaled | 8.47% | 11.64% | -2.62 | -3.13 [-6.57, +0.31] |

### C13: the 3x gap against the 2x gap at zero cost, no trigger (prediction: 3)

| reset | 10y median 2x | 10y median 3x | ratio | full-history log gap 2x | 3x | ratio | 3x wiped |
|---|---|---|---|---|---|---|---|
| weekly | +0.27 | +0.87 | 3.17 | +0.1080 | +0.3246 | 3.01 | - |
| monthly | +0.16 | +0.46 | 2.84 | +0.2261 | +0.6473 | 2.86 | - |
| quarterly | -0.16 | -4.16 | n/a (wiped) | -0.2050 | n/a | n/a | 2008-11-20 |

### $10,000 through the key periods (base cost)

| period | index | 3x daily twin | HYP_SPX_W_3x_none | HYP_SPX_M_3x_none | SPYQ_3x_none | HYP_SPX_W_3x_scaled | HYP_SPX_M_3x_scaled | SPYQ_3x_scaled | AMEX:UPRO |
|---|---|---|---|---|---|---|---|---|---|
| 1973-74 | $6,254 | $1,242 | $1,091 | $1,138 | $585 | $1,091 | $1,138 | $789 | - |
| 1987 Aug-Dec | $7,856 | $2,994 | $3,837 | $3,060 | $2,852 | $2,601 | $2,812 | $2,954 | - |
| 2000-02 | $6,239 | $1,063 | $1,091 | $1,190 | $983 | $1,091 | $1,190 | $687 | - |
| 2008-09 | $7,968 | $2,159 | $2,420 | $2,993 | $0 WIPED | $1,985 | $2,257 | $1,528 | - |
| 2020 Feb-Dec | $11,845 | $11,026 | $11,408 | $13,156 | $0 | $11,408 | $9,456 | $9,396 | $11,080 |
| 2022 | $8,189 | $4,309 | $4,382 | $4,328 | $0 | $4,382 | $4,328 | $4,320 | $4,296 |

### Real AMEX:UPRO (price only) from its first bar, 2009-06-25 to 2026-09-30

| series | CAGR |
|---|---|
| real AMEX:UPRO (price only) | 32.08% |
| model at its filed terms | 31.26% |
| 3x daily twin (1.00% fee) | 31.12% |
| HYP_SPX_W_3x_scaled | 32.10% |
| HYP_SPX_M_3x_scaled | 32.00% |
| SPYQ_3x_scaled | 30.92% |
| index (total return) | 15.16% |

### 5000 simulated decades (252-day blocks, base cost)

| trigger | reset | wiped | early reset | gap median (10y) | median wealth | p5 wealth | twin median |
|---|---|---|---|---|---|---|---|
| none | weekly | 0.0% | 0.0% | -0.10 | 3.89 | 0.199 | 3.87 |
| none | monthly | 0.2% | 0.0% | +0.03 | 3.72 | 0.152 | 3.87 |
| none | quarterly | 10.8% | 0.0% | +0.06 | 3.61 | 0.000 | 3.87 |
| scaled | weekly | 0.0% | 14.2% | -0.25 | 3.85 | 0.192 | 3.87 |
| scaled | monthly | 0.0% | 31.3% | -0.18 | 3.80 | 0.169 | 3.87 |
| scaled | quarterly | 0.0% | 52.1% | -0.68 | 3.56 | 0.129 | 3.87 |
| d20 | weekly | 0.0% | 16.8% | -0.11 | 3.90 | 0.199 | 3.87 |
| d20 | monthly | 0.0% | 39.3% | +0.02 | 3.88 | 0.179 | 3.87 |
| d20 | quarterly | 0.0% | 66.4% | -0.66 | 3.64 | 0.149 | 3.87 |
| d25 | weekly | 0.0% | 9.4% | -0.20 | 3.84 | 0.194 | 3.87 |
| d25 | monthly | 0.0% | 29.4% | -0.41 | 3.68 | 0.157 | 3.87 |
| d25 | quarterly | 0.0% | 44.9% | -0.82 | 3.49 | 0.121 | 3.87 |
| d30 | weekly | 0.0% | 2.4% | -0.11 | 3.85 | 0.191 | 3.87 |
| d30 | monthly | 0.0% | 18.0% | -0.25 | 3.46 | 0.101 | 3.87 |
| d30 | quarterly | 0.0% | 28.9% | -0.80 | 3.17 | 0.074 | 3.87 |
| fixed35 | weekly | 0.0% | 0.0% | -0.10 | 3.89 | 0.199 | 3.87 |
| fixed35 | monthly | 0.2% | 0.0% | +0.03 | 3.72 | 0.151 | 3.87 |
| fixed35 | quarterly | 11.2% | 0.0% | +0.06 | 3.60 | 0.000 | 3.87 |

Twin wiped on 0.0% of the paths. The 35% rule fired before a wipeout in no design: confirmed. It watches the day's low, so it ends a fund whose low passes 1/3 even when the close recovers; with no trigger the kernel judges a wipeout at the close. Extra wipe rate of that intraday test: weekly +0.0%, monthly +0.0%, quarterly +0.4%; on the history the two rules give the same funds: True.

## Nasdaq-100

Cost cases (spread per NAV a year): zero 0.00%; nport 2.71%; double 5.42% (base: nport); the rate on 2 borrowed turns; fee 1.00%.

### Full history per trigger rule (base cost, level fill)

| trigger | design | CAGR | max DD | twin CAGR | wiped out | early resets | eras | yearly gap vs twin (95%) |
|---|---|---|---|---|---|---|---|---|
| none | HYP_NDX_W_3x_none | 13.27% | -100.0% | 11.21% | - | 0 | - | [-0.45, +4.24] valid |
| none | MQQQ_3x_none | -100.00% | -100.0% | 11.21% | 1987-10-26 (1987 Aug-Dec) | 0 | - | n/a |
| none | QQQP_3x_none | -100.00% | -100.0% | 11.21% | 1987-10-26 (1987 Aug-Dec) | 0 | - | n/a |
| scaled | HYP_NDX_W_3x_scaled | 13.47% | -100.0% | 11.21% | - | 1 | 2000-02 | [-0.03, +4.17] valid |
| scaled | MQQQ_3x_scaled | 7.25% | -100.0% | 11.21% | - | 9 | 1987 Aug-Dec, 2000-02, 2008-09, other | [-9.92, +2.54] too narrow |
| scaled | QQQP_3x_scaled | 8.68% | -100.0% | 11.21% | - | 9 | 1987 Aug-Dec, 2000-02, 2008-09, 2022, other | [-6.37, +2.21] too narrow |
| d20 | HYP_NDX_W_3x_d20 | 13.85% | -100.0% | 11.21% | - | 3 | 1987 Aug-Dec, 2000-02 | [+0.82, +4.03] too narrow |
| d20 | MQQQ_3x_d20 | 9.11% | -100.0% | 11.21% | - | 12 | 1987 Aug-Dec, 2000-02, 2008-09, other | [-6.32, +2.53] valid |
| d20 | QQQP_3x_d20 | 7.86% | -100.0% | 11.21% | - | 18 | 1987 Aug-Dec, 2000-02, 2008-09, 2020 Feb-Dec, 2022, other | [-7.16, +1.42] valid |
| d25 | HYP_NDX_W_3x_d25 | 13.09% | -100.0% | 11.21% | - | 1 | 2000-02 | [-0.88, +4.32] valid |
| d25 | MQQQ_3x_d25 | 8.92% | -100.0% | 11.21% | - | 6 | 1987 Aug-Dec, 2000-02, 2008-09 | [-7.40, +3.25] too narrow |
| d25 | QQQP_3x_d25 | 5.83% | -100.0% | 11.21% | - | 9 | 1987 Aug-Dec, 2000-02, 2008-09, 2022, other | [-10.90, +1.21] too narrow |
| d30 | HYP_NDX_W_3x_d30 | 13.27% | -100.0% | 11.21% | - | 0 | - | [-0.45, +4.24] valid |
| d30 | MQQQ_3x_d30 | 9.87% | -100.0% | 11.21% | - | 1 | 1987 Aug-Dec | [-7.83, +5.49] too narrow |
| d30 | QQQP_3x_d30 | -7.32% | -100.0% | 11.21% | - | 7 | 1987 Aug-Dec, 2000-02, 2008-09 | [-36.52, -0.81] too narrow |
| fixed35 | HYP_NDX_W_3x_fixed35 | 13.27% | -100.0% | 11.21% | - | 0 | - | [-0.45, +4.24] valid |
| fixed35 | MQQQ_3x_fixed35 | -100.00% | -100.0% | 11.21% | 1987-10-26 (1987 Aug-Dec) | 0 | - | n/a |
| fixed35 | QQQP_3x_fixed35 | -100.00% | -100.0% | 11.21% | 1987-10-26 (1987 Aug-Dec) | 0 | - | n/a |

### Multi-start gap against the 3x daily twin (base cost; phase-pooled 95% interval)

| trigger | design | years | starts | median gap | p10 / p90 | calendar wins | mean [95%] | noisy |
|---|---|---|---|---|---|---|---|---|
| none | HYP_NDX_W_3x_none | 1 | 487 | +1.24 | -2.13 / +11.39 | 69% | +3.32 [-0.64, +7.28] | yes |
| none | HYP_NDX_W_3x_none | 3 | 463 | +1.63 | -1.66 / +8.83 | 78% | +2.74 [-0.41, +5.90] | yes |
| none | HYP_NDX_W_3x_none | 5 | 439 | +2.41 | +0.05 / +6.07 | 90% | +2.70 [-0.44, +5.85] | yes |
| none | HYP_NDX_W_3x_none | 10 | 379 | +2.69 | +0.83 / +3.78 | 95% | +2.56 [-0.84, +5.96] | yes |
| none | MQQQ_3x_none | 1 | 31 | -14.44 | -48.85 / -4.26 | 0% | -26.99 [-252.10, +198.12] | yes |
| none | MQQQ_3x_none | 3 | 31 | -93.99 | -108.55 / -78.35 | 0% | n/a [n/a, n/a] | yes |
| none | MQQQ_3x_none | 5 | 31 | -99.88 | -108.68 / -91.83 | 0% | n/a [n/a, n/a] | yes |
| none | MQQQ_3x_none | 10 | 31 | -118.99 | -124.98 / -115.50 | 0% | n/a [n/a, n/a] | yes |
| none | QQQP_3x_none | 1 | 31 | -29.04 | -48.85 / -15.84 | 0% | -33.84 [-214.83, +147.16] | yes |
| none | QQQP_3x_none | 3 | 31 | -93.99 | -108.55 / -78.35 | 0% | n/a [n/a, n/a] | yes |
| none | QQQP_3x_none | 5 | 31 | -99.88 | -108.68 / -91.83 | 0% | n/a [n/a, n/a] | yes |
| none | QQQP_3x_none | 10 | 31 | -118.99 | -124.98 / -115.50 | 0% | n/a [n/a, n/a] | yes |
| scaled | HYP_NDX_W_3x_scaled | 1 | 487 | +1.24 | -2.11 / +11.39 | 69% | +3.46 [-0.30, +7.23] | yes |
| scaled | HYP_NDX_W_3x_scaled | 3 | 463 | +1.68 | -1.57 / +8.83 | 79% | +2.88 [-0.18, +5.93] | yes |
| scaled | HYP_NDX_W_3x_scaled | 5 | 439 | +2.52 | +0.27 / +6.07 | 92% | +2.85 [-0.25, +5.95] | yes |
| scaled | HYP_NDX_W_3x_scaled | 10 | 379 | +2.80 | +0.95 / +3.97 | 95% | +2.77 [-0.50, +6.03] | yes |
| scaled | MQQQ_3x_scaled | 1 | 487 | +1.49 | -11.98 / +14.94 | 62% | +1.58 [-3.78, +6.94] | yes |
| scaled | MQQQ_3x_scaled | 3 | 463 | +1.90 | -16.96 / +9.86 | 57% | -1.08 [-7.24, +5.08] | yes |
| scaled | MQQQ_3x_scaled | 5 | 439 | -3.06 | -10.91 / +8.10 | 41% | -2.04 [-9.46, +5.37] | yes |
| scaled | MQQQ_3x_scaled | 10 | 379 | -4.19 | -8.88 / +0.50 | 14% | -3.96 [-14.67, +6.76] | yes |
| scaled | QQQP_3x_scaled | 1 | 487 | +2.87 | -13.01 / +17.58 | 59% | +2.71 [-2.85, +8.26] | yes |
| scaled | QQQP_3x_scaled | 3 | 463 | +2.24 | -9.72 / +10.56 | 59% | +1.04 [-4.12, +6.21] | yes |
| scaled | QQQP_3x_scaled | 5 | 439 | +1.06 | -8.24 / +8.92 | 59% | +0.27 [-6.29, +6.83] | yes |
| scaled | QQQP_3x_scaled | 10 | 379 | +0.59 | -5.29 / +2.94 | 53% | -0.71 [-10.69, +9.26] | yes |

### Fills: the close and next-close fills against the level fill (gap risk)

| trigger | design | fill | early resets | worst fill loss | on | level fill loss | wiped | CAGR |
|---|---|---|---|---|---|---|---|---|
| scaled | HYP_NDX_W_3x_scaled | close | 0 | n/a | - | -70.0% | - | 13.27% |
| scaled | HYP_NDX_W_3x_scaled | next_close | 0 | n/a | - | -70.0% | - | 13.27% |
| scaled | MQQQ_3x_scaled | close | 9 | -81.9% | 2000-04-14 | -70.0% | - | 10.04% |
| scaled | MQQQ_3x_scaled | next_close | 8 | -90.9% | 1987-10-20 | -70.0% | - | 10.28% |
| scaled | QQQP_3x_scaled | close | 9 | -87.7% | 2001-03-12 | -70.0% | - | 6.38% |
| scaled | QQQP_3x_scaled | next_close | 10 | -90.9% | 1987-10-20 | -70.0% | - | 6.05% |
| d20 | HYP_NDX_W_3x_d20 | close | 1 | -64.6% | 1987-10-20 | -60.0% | - | 13.18% |
| d20 | HYP_NDX_W_3x_d20 | next_close | 1 | -40.4% | 1987-10-21 | -60.0% | - | 13.73% |
| d20 | MQQQ_3x_d20 | close | 11 | -81.9% | 2000-04-14 | -60.0% | - | 9.40% |
| d20 | MQQQ_3x_d20 | next_close | 11 | -90.9% | 1987-10-20 | -60.0% | - | 8.83% |
| d20 | QQQP_3x_d20 | close | 19 | -81.9% | 2000-04-14 | -60.0% | - | 7.63% |
| d20 | QQQP_3x_d20 | next_close | 19 | -90.9% | 1987-10-20 | -60.0% | - | 8.44% |
| d25 | HYP_NDX_W_3x_d25 | close | 0 | n/a | - | -75.0% | - | 13.27% |
| d25 | HYP_NDX_W_3x_d25 | next_close | 0 | n/a | - | -75.0% | - | 13.27% |
| d25 | MQQQ_3x_d25 | close | 4 | -90.9% | 1987-10-20 | -75.0% | - | 7.09% |
| d25 | MQQQ_3x_d25 | next_close | 4 | -74.1% | 2008-10-24 | -75.0% | - | 11.05% |
| d25 | QQQP_3x_d25 | close | 9 | -90.9% | 1987-10-20 | -75.0% | - | 3.72% |
| d25 | QQQP_3x_d25 | next_close | 9 | -78.8% | 2001-09-06 | -75.0% | - | 9.11% |
| d30 | HYP_NDX_W_3x_d30 | close | 0 | n/a | - | -90.0% | - | 13.27% |
| d30 | HYP_NDX_W_3x_d30 | next_close | 0 | n/a | - | -90.0% | - | 13.27% |
| d30 | MQQQ_3x_d30 | close | 1 | -90.9% | 1987-10-20 | -90.0% | - | 9.91% |
| d30 | MQQQ_3x_d30 | next_close | 1 | -69.3% | 1987-10-21 | -90.0% | - | 12.35% |
| d30 | QQQP_3x_d30 | close | 7 | -97.0% | 2001-09-17 | -90.0% | - | -7.79% |
| d30 | QQQP_3x_d30 | next_close | 4 | -96.0% | 2000-05-23 | -90.0% | 2001-09-18 | -100.00% |

### Costs (trigger scaled, 10-year multi-start)

| cost | design | CAGR | twin CAGR | median gap | mean [95%] |
|---|---|---|---|---|---|
| zero | HYP_NDX_W_3x_scaled | 16.64% | 14.31% | +2.88 | +2.85 [-0.51, +6.20] |
| zero | MQQQ_3x_scaled | 10.30% | 14.31% | -4.28 | -4.02 [-14.85, +6.80] |
| zero | QQQP_3x_scaled | 11.76% | 14.31% | +0.50 | -0.75 [-10.44, +8.93] |
| nport | HYP_NDX_W_3x_scaled | 13.47% | 11.21% | +2.80 | +2.77 [-0.50, +6.03] |
| nport | MQQQ_3x_scaled | 7.25% | 11.21% | -4.19 | -3.96 [-14.67, +6.76] |
| nport | QQQP_3x_scaled | 8.68% | 11.21% | +0.59 | -0.71 [-10.69, +9.26] |
| double | HYP_NDX_W_3x_scaled | 10.38% | 8.18% | +2.71 | +2.69 [-0.49, +5.87] |
| double | MQQQ_3x_scaled | 4.27% | 8.18% | -4.10 | -3.90 [-14.49, +6.70] |
| double | QQQP_3x_scaled | 5.66% | 8.18% | +0.70 | -0.69 [-10.95, +9.56] |

### C13: the 3x gap against the 2x gap at zero cost, no trigger (prediction: 3)

| reset | 10y median 2x | 10y median 3x | ratio | full-history log gap 2x | 3x | ratio | 3x wiped |
|---|---|---|---|---|---|---|---|
| weekly | +1.18 | +2.91 | 2.47 | +0.3529 | +0.7772 | 2.20 | - |
| monthly | +1.55 | -139.24 | n/a (wiped) | +0.2955 | n/a | n/a | 1987-10-26 |
| quarterly | -0.01 | -139.24 | n/a (wiped) | -0.6084 | n/a | n/a | 1987-10-26 |

### $10,000 through the key periods (base cost)

| period | index | 3x daily twin | HYP_NDX_W_3x_none | MQQQ_3x_none | QQQP_3x_none | HYP_NDX_W_3x_scaled | MQQQ_3x_scaled | QQQP_3x_scaled | NASDAQ:TQQQ |
|---|---|---|---|---|---|---|---|---|---|
| 1987 Aug-Dec | $7,968 | $3,320 | $3,078 | $0 WIPED | $0 WIPED | $3,078 | $2,786 | $3,028 | - |
| 2000-02 | $2,660 | $12 | $11 | $0 | $0 | $12 | $4 | $4 | - |
| 2008-09 | $9,054 | $3,083 | $3,717 | $0 | $0 | $3,717 | $1,725 | $2,888 | - |
| 2020 Feb-Dec | $14,453 | $19,176 | $21,644 | $0 | $0 | $21,644 | $23,905 | $22,364 | $19,415 |
| 2022 | $6,762 | $2,089 | $2,233 | $0 | $0 | $2,233 | $2,137 | $1,817 | $2,080 |

### Real NASDAQ:TQQQ (price only) from its first bar, 2010-02-11 to 2026-09-30

| series | CAGR |
|---|---|
| real NASDAQ:TQQQ (price only) | 42.48% |
| model at its filed terms | 41.07% |
| 3x daily twin (1.00% fee) | 40.81% |
| HYP_NDX_W_3x_scaled | 43.49% |
| MQQQ_3x_scaled | 42.11% |
| QQQP_3x_scaled | 42.77% |
| index (total return) | 19.82% |

### 5000 simulated decades (252-day blocks, base cost)

| trigger | reset | wiped | early reset | gap median (10y) | median wealth | p5 wealth | twin median |
|---|---|---|---|---|---|---|---|
| none | weekly | 0.0% | 0.0% | +1.39 | 4.01 | 0.020 | 3.65 |
| none | monthly | 15.2% | 0.0% | +0.27 | 2.37 | 0.000 | 3.65 |
| none | quarterly | 55.3% | 0.0% | -67.55 | 0.00 | 0.000 | 3.65 |
| scaled | weekly | 0.0% | 24.1% | +1.14 | 4.05 | 0.019 | 3.65 |
| scaled | monthly | 0.0% | 75.2% | -0.63 | 3.44 | 0.010 | 3.65 |
| scaled | quarterly | 0.0% | 87.7% | -2.97 | 2.80 | 0.005 | 3.65 |
| d20 | weekly | 0.0% | 50.4% | +0.69 | 3.88 | 0.018 | 3.65 |
| d20 | monthly | 0.0% | 87.1% | -0.83 | 3.46 | 0.010 | 3.65 |
| d20 | quarterly | 0.0% | 95.1% | -2.31 | 3.07 | 0.009 | 3.65 |
| d25 | weekly | 0.0% | 16.6% | +1.27 | 4.07 | 0.019 | 3.65 |
| d25 | monthly | 0.0% | 64.9% | -0.31 | 3.54 | 0.009 | 3.65 |
| d25 | quarterly | 0.0% | 82.4% | -3.80 | 2.68 | 0.004 | 3.65 |
| d30 | weekly | 0.0% | 0.0% | +1.39 | 4.01 | 0.020 | 3.65 |
| d30 | monthly | 0.0% | 36.5% | -0.96 | 2.96 | 0.005 | 3.65 |
| d30 | quarterly | 0.4% | 68.3% | -10.91 | 1.30 | 0.000 | 3.65 |
| fixed35 | weekly | 0.0% | 0.0% | +1.39 | 4.01 | 0.020 | 3.65 |
| fixed35 | monthly | 15.2% | 0.0% | +0.27 | 2.37 | 0.000 | 3.65 |
| fixed35 | quarterly | 56.2% | 0.0% | -69.48 | 0.00 | 0.000 | 3.65 |

Twin wiped on 0.0% of the paths. The 35% rule fired before a wipeout in no design: confirmed. It watches the day's low, so it ends a fund whose low passes 1/3 even when the close recovers; with no trigger the kernel judges a wipeout at the close. Extra wipe rate of that intraday test: weekly +0.0%, monthly +0.0%, quarterly +0.9%; on the history the two rules give the same funds: True.
