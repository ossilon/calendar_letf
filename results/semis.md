# B16: calendar-reset funds on semiconductors

*Data: TradingView (via local export), FRED, SEC N-PORT. Every fund is HYPOTHETICAL; the index is PRICE ONLY; SOXL is a price-only overlay on another index since 2021. Not investment advice.*

```
Inputs: 6 files; prices from <external>/library, rates from <external>/rates
  NASDAQ_SOX_daily.csv: 8159 rows, 1994-05-04 to 2026-10-02, sha256 0f8d336a1666
  AMEX_SOXL_daily.csv: 4167 rows, 2010-03-11 to 2026-10-02, sha256 1a134c80a653
  NASDAQ_SOXX_daily.csv: 6367 rows, 2001-07-13 to 2026-11-05, sha256 661618bb2798
  AMEX_USD_daily.csv: 4967 rows, 2007-02-01 to 2026-11-05, sha256 434a39d64efa
  DFF.csv: 26424 rows, 1954-07-01 to 2026-11-03, sha256 e84a934a5014
  OBFR.csv: 2683 rows, 2016-03-01 to 2026-11-03, sha256 bbef2a371e62
SOX early-reset trigger: the NASDAQ:SOX price index, daily low; trigger basis 'index'; drop 35% from the fund's base; fill mode 'level'.
SOX day counts: financing (reference rate and swap spread) ACT/360; expense ratio ACT/365 (calendar days between rows, so weekends and holidays accrue).
SOX reset dates: last NYSE session of the week / month / quarter from 1970-01-01 (calendar_letf/nyse.py, refuses data that lack it); before that the last row of the period.
B16 trigger rules replace the 35% drop above: none, scaled (0.70 / L), fixed 35%.
Index basis: PHLX Semiconductor Sector Index (NASDAQ:SOX), price only: dividends left out. Study end fixed at 2026-09-30; Monte Carlo seed 20261106.
```

Index: PHLX Semiconductor Sector Index (NASDAQ:SOX), price only: dividends left out. Fee 1.30% (SOXM / SOXW, filed); spread 0.9391% per turn over fed funds (USD, N-PORT) on L turns; trigger rules none / scaled (0.70 / L) / fixed 35%. Every fund is HYPOTHETICAL.

## SOXM / SOXW one-month check (RUN: on SOXX's own total return (price plus payouts at their ex-dates))

| fund | reset | window | anchor NAV return | 2 x SOXX TR | model, Tradr spread low | gap pp | model, Tradr spread high | gap pp | model, USD spread | gap pp | SOXX index (SECONDARY) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SOXM | monthly | 2024-08-30 to 2024-09-30 | -0.72% | 0.01% | -0.71% | +0.01 | -0.75% | -0.03 | -0.74% | -0.02 | NYSE Semiconductor Index |
| SOXW | weekly | 2024-08-30 to 2024-09-30 | -3.36% | 0.01% | -3.37% | -0.01 | -3.41% | -0.05 | -3.40% | -0.04 | NYSE Semiconductor Index |

Cash yield c = 0.908 x OBFR (from results/validate_live.json); payouts in the window: 2024-09-25. SOXX payouts 2022-2025: 0.65%-1.09% of the mean price a year (SECONDARY).

## Per leverage, trigger rule and reset (full history, base cost, level fill)

| L | trigger | design | CAGR | max DD | twin CAGR | wiped | early resets | eras | yearly gap vs twin (95%) |
|---|---|---|---|---|---|---|---|---|---|
| 1.2 | none | HYP_SOX_W_L1.20_none | 13.64% | -94.8% | 13.40% | - | 0 | - | [+0.05, +0.33] valid |
| 1.2 | none | HYP_SOX_M_L1.20_none | 13.70% | -94.8% | 13.40% | - | 0 | - | [+0.10, +0.46] valid |
| 1.2 | none | HYP_SOX_Q_L1.20_none | 13.47% | -95.0% | 13.40% | - | 0 | - | [-0.23, +0.42] valid |
| 1.2 | scaled | HYP_SOX_W_L1.20_scaled | 13.64% | -94.8% | 13.40% | - | 0 | - | [+0.05, +0.33] valid |
| 1.2 | scaled | HYP_SOX_M_L1.20_scaled | 13.70% | -94.8% | 13.40% | - | 0 | - | [+0.10, +0.46] valid |
| 1.2 | scaled | HYP_SOX_Q_L1.20_scaled | 13.47% | -95.0% | 13.40% | - | 0 | - | [-0.23, +0.42] valid |
| 1.2 | fixed35 | HYP_SOX_W_L1.20_fixed35 | 13.64% | -94.8% | 13.40% | - | 0 | - | [+0.05, +0.33] valid |
| 1.2 | fixed35 | HYP_SOX_M_L1.20_fixed35 | 13.69% | -94.8% | 13.40% | - | 1 | 2000-02 | [+0.08, +0.45] valid |
| 1.2 | fixed35 | HYP_SOX_Q_L1.20_fixed35 | 13.48% | -94.8% | 13.40% | - | 6 | 2000-02, 2008-09, other | [-0.22, +0.43] valid |
| 1.5 | none | HYP_SOX_W_L1.50_none | 13.62% | -98.4% | 12.92% | - | 0 | - | [+0.12, +1.00] valid |
| 1.5 | none | HYP_SOX_M_L1.50_none | 13.75% | -98.5% | 12.92% | - | 0 | - | [+0.20, +1.37] valid |
| 1.5 | none | HYP_SOX_Q_L1.50_none | 12.88% | -98.8% | 12.92% | - | 0 | - | [-1.09, +1.18] valid |
| 1.5 | scaled | HYP_SOX_W_L1.50_scaled | 13.62% | -98.4% | 12.92% | - | 0 | - | [+0.12, +1.00] valid |
| 1.5 | scaled | HYP_SOX_M_L1.50_scaled | 13.75% | -98.5% | 12.92% | - | 0 | - | [+0.20, +1.37] valid |
| 1.5 | scaled | HYP_SOX_Q_L1.50_scaled | 12.88% | -98.8% | 12.92% | - | 0 | - | [-1.09, +1.18] too narrow |
| 1.5 | fixed35 | HYP_SOX_W_L1.50_fixed35 | 13.62% | -98.4% | 12.92% | - | 0 | - | [+0.12, +1.00] valid |
| 1.5 | fixed35 | HYP_SOX_M_L1.50_fixed35 | 13.71% | -98.5% | 12.92% | - | 1 | 2000-02 | [+0.13, +1.36] valid |
| 1.5 | fixed35 | HYP_SOX_Q_L1.50_fixed35 | 12.91% | -98.5% | 12.92% | - | 6 | 2000-02, 2008-09, other | [-1.03, +1.18] valid |
| 1.7 | none | HYP_SOX_W_L1.70_none | 12.86% | -99.3% | 11.80% | - | 0 | - | [+0.14, +1.57] valid |
| 1.7 | none | HYP_SOX_M_L1.70_none | 12.99% | -99.4% | 11.80% | - | 0 | - | [+0.15, +2.12] valid |
| 1.7 | none | HYP_SOX_Q_L1.70_none | 11.36% | -99.6% | 11.80% | - | 0 | - | [-2.40, +1.80] too narrow |
| 1.7 | scaled | HYP_SOX_W_L1.70_scaled | 12.86% | -99.3% | 11.80% | - | 0 | - | [+0.14, +1.57] valid |
| 1.7 | scaled | HYP_SOX_M_L1.70_scaled | 12.99% | -99.4% | 11.80% | - | 0 | - | [+0.15, +2.12] valid |
| 1.7 | scaled | HYP_SOX_Q_L1.70_scaled | 10.57% | -99.6% | 11.80% | - | 2 | 2000-02, 2008-09 | [-3.72, +1.64] too narrow |
| 1.7 | fixed35 | HYP_SOX_W_L1.70_fixed35 | 12.86% | -99.3% | 11.80% | - | 0 | - | [+0.14, +1.57] valid |
| 1.7 | fixed35 | HYP_SOX_M_L1.70_fixed35 | 12.92% | -99.4% | 11.80% | - | 1 | 2000-02 | [+0.02, +2.12] valid |
| 1.7 | fixed35 | HYP_SOX_Q_L1.70_fixed35 | 11.45% | -99.5% | 11.80% | - | 6 | 2000-02, 2008-09, other | [-2.17, +1.75] valid |
| 2 | none | HYP_SOX_W_L2.00_none | 10.57% | -99.9% | 8.94% | - | 0 | - | [+0.06, +2.59] valid |
| 2 | none | HYP_SOX_M_L2.00_none | 10.53% | -99.9% | 8.94% | - | 0 | - | [-0.35, +3.46] valid |
| 2 | none | HYP_SOX_Q_L2.00_none | 6.81% | -100.0% | 8.94% | - | 0 | - | [-6.75, +2.90] too narrow |
| 2 | scaled | HYP_SOX_W_L2.00_scaled | 10.57% | -99.9% | 8.94% | - | 0 | - | [+0.06, +2.59] valid |
| 2 | scaled | HYP_SOX_M_L2.00_scaled | 10.37% | -99.9% | 8.94% | - | 1 | 2000-02 | [-0.68, +3.49] valid |
| 2 | scaled | HYP_SOX_Q_L2.00_scaled | 7.18% | -99.9% | 8.94% | - | 6 | 2000-02, 2008-09, other | [-5.72, +2.61] valid |
| 2 | fixed35 | HYP_SOX_W_L2.00_fixed35 | 10.57% | -99.9% | 8.94% | - | 0 | - | [+0.06, +2.59] valid |
| 2 | fixed35 | HYP_SOX_M_L2.00_fixed35 | 10.37% | -99.9% | 8.94% | - | 1 | 2000-02 | [-0.68, +3.49] valid |
| 2 | fixed35 | HYP_SOX_Q_L2.00_fixed35 | 7.18% | -99.9% | 8.94% | - | 6 | 2000-02, 2008-09, other | [-5.72, +2.61] valid |
| 3 | none | HYP_SOX_W_L3.00_none | -6.89% | -100.0% | -9.18% | - | 0 | - | [-3.68, +7.51] too narrow |
| 3 | none | HYP_SOX_M_L3.00_none | -100.00% | -100.0% | -9.18% | 2001-09-26 (2000-02) | 0 | - | n/a |
| 3 | none | HYP_SOX_Q_L3.00_none | -100.00% | -100.0% | -9.18% | 1997-12-12 (other) | 0 | - | n/a |
| 3 | scaled | HYP_SOX_W_L3.00_scaled | -6.05% | -100.0% | -9.18% | - | 3 | 2000-02 | [-1.76, +7.45] valid |
| 3 | scaled | HYP_SOX_M_L3.00_scaled | -12.48% | -100.0% | -9.18% | - | 15 | 2000-02, 2008-09, 2020 Feb-Dec, other | [-14.23, +7.78] too narrow |
| 3 | scaled | HYP_SOX_Q_L3.00_scaled | -9.69% | -100.0% | -9.18% | - | 16 | 2000-02, 2008-09, 2020 Feb-Dec, 2022, other | [-7.29, +8.74] valid |
| 3 | fixed35 | HYP_SOX_W_L3.00_fixed35 | -6.89% | -100.0% | -9.18% | - | 0 | - | [-3.68, +7.51] too narrow |
| 3 | fixed35 | HYP_SOX_M_L3.00_fixed35 | -100.00% | -100.0% | -9.18% | 2001-09-21 (2000-02) | 0 | - | n/a |
| 3 | fixed35 | HYP_SOX_Q_L3.00_fixed35 | -100.00% | -100.0% | -9.18% | 1997-12-12 (other) | 0 | - | n/a |

## Multi-start gap against the daily twin (phase-pooled 95% interval)

| L | trigger | design | years | starts | median gap | calendar wins | mean [95%] | noisy |
|---|---|---|---|---|---|---|---|---|
| 1.2 | none | HYP_SOX_W_L1.20_none | 10 | 268 | +0.17 | 100% | +0.18 [-0.48, +0.85] | yes |
| 1.2 | none | HYP_SOX_M_L1.20_none | 10 | 268 | +0.25 | 100% | +0.28 [-1.27, +1.82] | yes |
| 1.2 | none | HYP_SOX_Q_L1.20_none | 10 | 268 | +0.28 | 66% | +0.15 [-3.30, +3.60] | yes |
| 1.2 | scaled | HYP_SOX_W_L1.20_scaled | 1 | 376 | +0.13 | 75% | +0.23 [+0.03, +0.43] | no |
| 1.2 | scaled | HYP_SOX_W_L1.20_scaled | 3 | 352 | +0.18 | 92% | +0.21 [+0.06, +0.37] | no |
| 1.2 | scaled | HYP_SOX_W_L1.20_scaled | 5 | 328 | +0.18 | 99% | +0.21 [+0.02, +0.41] | no |
| 1.2 | scaled | HYP_SOX_W_L1.20_scaled | 10 | 268 | +0.17 | 100% | +0.18 [-0.48, +0.85] | yes |
| 1.2 | scaled | HYP_SOX_M_L1.20_scaled | 1 | 376 | +0.21 | 75% | +0.34 [+0.06, +0.62] | no |
| 1.2 | scaled | HYP_SOX_M_L1.20_scaled | 3 | 352 | +0.24 | 89% | +0.30 [+0.04, +0.56] | no |
| 1.2 | scaled | HYP_SOX_M_L1.20_scaled | 5 | 328 | +0.24 | 94% | +0.30 [-0.02, +0.61] | yes |
| 1.2 | scaled | HYP_SOX_M_L1.20_scaled | 10 | 268 | +0.25 | 100% | +0.28 [-1.27, +1.82] | yes |
| 1.2 | scaled | HYP_SOX_Q_L1.20_scaled | 1 | 376 | +0.34 | 72% | +0.18 [-0.23, +0.59] | yes |
| 1.2 | scaled | HYP_SOX_Q_L1.20_scaled | 3 | 352 | +0.30 | 73% | +0.15 [-0.28, +0.58] | yes |
| 1.2 | scaled | HYP_SOX_Q_L1.20_scaled | 5 | 328 | +0.29 | 72% | +0.13 [-0.48, +0.74] | yes |
| 1.2 | scaled | HYP_SOX_Q_L1.20_scaled | 10 | 268 | +0.28 | 66% | +0.15 [-3.30, +3.60] | yes |
| 1.2 | fixed35 | HYP_SOX_W_L1.20_fixed35 | 10 | 268 | +0.17 | 100% | +0.18 [-0.48, +0.85] | yes |
| 1.2 | fixed35 | HYP_SOX_M_L1.20_fixed35 | 10 | 268 | +0.25 | 98% | +0.27 [-1.38, +1.91] | yes |
| 1.2 | fixed35 | HYP_SOX_Q_L1.20_fixed35 | 10 | 268 | +0.20 | 69% | +0.17 [-2.62, +2.96] | yes |
| 1.5 | none | HYP_SOX_W_L1.50_none | 10 | 268 | +0.50 | 100% | +0.55 [-1.56, +2.66] | yes |
| 1.5 | none | HYP_SOX_M_L1.50_none | 10 | 268 | +0.74 | 95% | +0.80 [-4.69, +6.28] | yes |
| 1.5 | none | HYP_SOX_Q_L1.50_none | 10 | 268 | +0.77 | 64% | +0.27 [-11.84, +12.38] | yes |
| 1.5 | scaled | HYP_SOX_W_L1.50_scaled | 1 | 376 | +0.39 | 74% | +0.72 [-0.02, +1.46] | yes |
| 1.5 | scaled | HYP_SOX_W_L1.50_scaled | 3 | 352 | +0.55 | 89% | +0.64 [+0.12, +1.16] | no |
| 1.5 | scaled | HYP_SOX_W_L1.50_scaled | 5 | 328 | +0.53 | 99% | +0.63 [-0.01, +1.28] | yes |
| 1.5 | scaled | HYP_SOX_W_L1.50_scaled | 10 | 268 | +0.50 | 100% | +0.55 [-1.56, +2.66] | yes |
| 1.5 | scaled | HYP_SOX_M_L1.50_scaled | 1 | 376 | +0.63 | 73% | +1.04 [+0.06, +2.02] | no |
| 1.5 | scaled | HYP_SOX_M_L1.50_scaled | 3 | 352 | +0.68 | 87% | +0.87 [+0.01, +1.73] | no |
| 1.5 | scaled | HYP_SOX_M_L1.50_scaled | 5 | 328 | +0.71 | 86% | +0.85 [-0.22, +1.93] | yes |
| 1.5 | scaled | HYP_SOX_M_L1.50_scaled | 10 | 268 | +0.74 | 95% | +0.80 [-4.69, +6.28] | yes |
| 1.5 | scaled | HYP_SOX_Q_L1.50_scaled | 1 | 376 | +0.92 | 69% | +0.42 [-0.98, +1.82] | yes |
| 1.5 | scaled | HYP_SOX_Q_L1.50_scaled | 3 | 352 | +0.82 | 72% | +0.30 [-1.12, +1.73] | yes |
| 1.5 | scaled | HYP_SOX_Q_L1.50_scaled | 5 | 328 | +0.81 | 71% | +0.21 [-1.89, +2.31] | yes |
| 1.5 | scaled | HYP_SOX_Q_L1.50_scaled | 10 | 268 | +0.77 | 64% | +0.27 [-11.84, +12.38] | yes |
| 1.5 | fixed35 | HYP_SOX_W_L1.50_fixed35 | 10 | 268 | +0.50 | 100% | +0.55 [-1.56, +2.66] | yes |
| 1.5 | fixed35 | HYP_SOX_M_L1.50_fixed35 | 10 | 268 | +0.74 | 87% | +0.76 [-5.11, +6.63] | yes |
| 1.5 | fixed35 | HYP_SOX_Q_L1.50_fixed35 | 10 | 268 | +0.47 | 65% | +0.33 [-9.39, +10.04] | yes |
| 1.7 | none | HYP_SOX_W_L1.70_none | 10 | 268 | +0.71 | 100% | +0.83 [-2.68, +4.34] | yes |
| 1.7 | none | HYP_SOX_M_L1.70_none | 10 | 268 | +1.14 | 81% | +1.18 [-8.69, +11.04] | yes |
| 1.7 | none | HYP_SOX_Q_L1.70_none | 10 | 268 | +1.09 | 64% | +0.16 [-22.18, +22.50] | yes |
| 1.7 | scaled | HYP_SOX_W_L1.70_scaled | 1 | 376 | +0.61 | 74% | +1.15 [-0.17, +2.46] | yes |
| 1.7 | scaled | HYP_SOX_W_L1.70_scaled | 3 | 352 | +0.87 | 87% | +0.98 [+0.13, +1.83] | no |
| 1.7 | scaled | HYP_SOX_W_L1.70_scaled | 5 | 328 | +0.79 | 98% | +0.96 [-0.10, +2.02] | yes |
| 1.7 | scaled | HYP_SOX_W_L1.70_scaled | 10 | 268 | +0.71 | 100% | +0.83 [-2.68, +4.34] | yes |
| 1.7 | scaled | HYP_SOX_M_L1.70_scaled | 1 | 376 | +0.97 | 72% | +1.69 [+0.01, +3.38] | no |
| 1.7 | scaled | HYP_SOX_M_L1.70_scaled | 3 | 352 | +1.05 | 83% | +1.31 [-0.14, +2.75] | yes |
| 1.7 | scaled | HYP_SOX_M_L1.70_scaled | 5 | 328 | +1.10 | 81% | +1.26 [-0.60, +3.13] | yes |
| 1.7 | scaled | HYP_SOX_M_L1.70_scaled | 10 | 268 | +1.14 | 81% | +1.18 [-8.69, +11.04] | yes |
| 1.7 | scaled | HYP_SOX_Q_L1.70_scaled | 1 | 376 | +1.40 | 66% | +0.28 [-2.16, +2.72] | yes |
| 1.7 | scaled | HYP_SOX_Q_L1.70_scaled | 3 | 352 | +1.12 | 63% | -0.27 [-2.99, +2.45] | yes |
| 1.7 | scaled | HYP_SOX_Q_L1.70_scaled | 5 | 328 | +0.86 | 53% | -0.61 [-4.67, +3.44] | yes |
| 1.7 | scaled | HYP_SOX_Q_L1.70_scaled | 10 | 268 | -0.88 | 36% | -0.76 [-26.75, +25.22] | yes |
| 1.7 | fixed35 | HYP_SOX_W_L1.70_fixed35 | 10 | 268 | +0.71 | 100% | +0.83 [-2.68, +4.34] | yes |
| 1.7 | fixed35 | HYP_SOX_M_L1.70_fixed35 | 10 | 268 | +1.14 | 77% | +1.12 [-9.45, +11.69] | yes |
| 1.7 | fixed35 | HYP_SOX_Q_L1.70_fixed35 | 10 | 268 | +0.54 | 64% | +0.27 [-17.58, +18.12] | yes |
| 2 | none | HYP_SOX_W_L2.00_none | 10 | 268 | +0.98 | 100% | +1.29 [-5.32, +7.90] | yes |
| 2 | none | HYP_SOX_M_L2.00_none | 10 | 268 | +1.78 | 71% | +1.72 [-18.28, +21.72] | yes |
| 2 | none | HYP_SOX_Q_L2.00_none | 10 | 268 | +1.45 | 63% | -0.64 [-49.14, +47.86] | yes |
| 2 | scaled | HYP_SOX_W_L2.00_scaled | 1 | 376 | +0.95 | 73% | +1.96 [-0.68, +4.59] | yes |
| 2 | scaled | HYP_SOX_W_L2.00_scaled | 3 | 352 | +1.16 | 84% | +1.53 [+0.03, +3.03] | no |
| 2 | scaled | HYP_SOX_W_L2.00_scaled | 5 | 328 | +1.13 | 94% | +1.49 [-0.40, +3.39] | yes |
| 2 | scaled | HYP_SOX_W_L2.00_scaled | 10 | 268 | +0.98 | 100% | +1.29 [-5.32, +7.90] | yes |
| 2 | scaled | HYP_SOX_M_L2.00_scaled | 1 | 376 | +1.54 | 70% | +2.95 [-0.27, +6.18] | yes |
| 2 | scaled | HYP_SOX_M_L2.00_scaled | 3 | 352 | +1.71 | 80% | +1.92 [-0.84, +4.68] | yes |
| 2 | scaled | HYP_SOX_M_L2.00_scaled | 5 | 328 | +1.82 | 77% | +1.75 [-2.08, +5.57] | yes |
| 2 | scaled | HYP_SOX_M_L2.00_scaled | 10 | 268 | +1.78 | 69% | +1.61 [-19.87, +23.08] | yes |
| 2 | scaled | HYP_SOX_Q_L2.00_scaled | 1 | 376 | +2.17 | 65% | +1.14 [-3.04, +5.31] | yes |
| 2 | scaled | HYP_SOX_Q_L2.00_scaled | 3 | 352 | +1.74 | 62% | -0.32 [-4.93, +4.29] | yes |
| 2 | scaled | HYP_SOX_Q_L2.00_scaled | 5 | 328 | +1.02 | 52% | -0.50 [-6.81, +5.81] | yes |
| 2 | scaled | HYP_SOX_Q_L2.00_scaled | 10 | 268 | +0.28 | 58% | -0.34 [-38.19, +37.51] | yes |
| 2 | fixed35 | HYP_SOX_W_L2.00_fixed35 | 10 | 268 | +0.98 | 100% | +1.29 [-5.32, +7.90] | yes |
| 2 | fixed35 | HYP_SOX_M_L2.00_fixed35 | 10 | 268 | +1.78 | 69% | +1.61 [-19.87, +23.08] | yes |
| 2 | fixed35 | HYP_SOX_Q_L2.00_fixed35 | 10 | 268 | +0.28 | 58% | -0.34 [-38.19, +37.51] | yes |
| 3 | none | HYP_SOX_W_L3.00_none | 10 | 268 | +1.96 | 74% | +2.57 [-28.27, +33.41] | yes |
| 3 | none | HYP_SOX_M_L3.00_none | 10 | 87 | -51.86 | 0% | n/a [n/a, n/a] | yes |
| 3 | none | HYP_SOX_Q_L3.00_none | 10 | 42 | -55.23 | 0% | n/a [n/a, n/a] | yes |
| 3 | scaled | HYP_SOX_W_L3.00_scaled | 1 | 376 | +1.79 | 71% | +7.81 [-2.84, +18.46] | yes |
| 3 | scaled | HYP_SOX_W_L3.00_scaled | 3 | 352 | +2.03 | 77% | +3.80 [-0.77, +8.38] | yes |
| 3 | scaled | HYP_SOX_W_L3.00_scaled | 5 | 328 | +2.01 | 78% | +3.51 [-2.73, +9.76] | yes |
| 3 | scaled | HYP_SOX_W_L3.00_scaled | 10 | 268 | +1.99 | 82% | +2.95 [-24.03, +29.94] | yes |
| 3 | scaled | HYP_SOX_M_L3.00_scaled | 1 | 376 | +2.95 | 62% | +3.31 [-10.17, +16.78] | yes |
| 3 | scaled | HYP_SOX_M_L3.00_scaled | 3 | 352 | +2.03 | 61% | +0.69 [-8.25, +9.62] | yes |
| 3 | scaled | HYP_SOX_M_L3.00_scaled | 5 | 328 | +1.24 | 51% | +0.17 [-10.71, +11.04] | yes |
| 3 | scaled | HYP_SOX_M_L3.00_scaled | 10 | 268 | +0.88 | 62% | +0.24 [-63.21, +63.68] | yes |
| 3 | scaled | HYP_SOX_Q_L3.00_scaled | 1 | 376 | +5.33 | 64% | +5.13 [-12.88, +23.14] | yes |
| 3 | scaled | HYP_SOX_Q_L3.00_scaled | 3 | 352 | +2.93 | 64% | +2.74 [-5.03, +10.50] | yes |
| 3 | scaled | HYP_SOX_Q_L3.00_scaled | 5 | 328 | +1.88 | 59% | +2.55 [-6.04, +11.13] | yes |
| 3 | scaled | HYP_SOX_Q_L3.00_scaled | 10 | 268 | +1.24 | 62% | +2.57 [-46.93, +52.07] | yes |
| 3 | fixed35 | HYP_SOX_W_L3.00_fixed35 | 10 | 268 | +1.96 | 74% | +2.57 [-28.27, +33.41] | yes |
| 3 | fixed35 | HYP_SOX_M_L3.00_fixed35 | 10 | 87 | -51.86 | 0% | n/a [n/a, n/a] | yes |
| 3 | fixed35 | HYP_SOX_Q_L3.00_fixed35 | 10 | 42 | -55.23 | 0% | n/a [n/a, n/a] | yes |

## The best L (0.05 grid, base cost; plateau = within one SE of the best)

| reset | range | best L | plateau | rising at top | growth %/yr | wiped L |
|---|---|---|---|---|---|---|
| daily | under2 | 1.00 | 1.00-2.00 | no | +11.35 |  |
| daily | to3 | 1.00 | 1.00-2.15 | no | +11.35 |  |
| weekly | under2 | 1.00 | 1.00-2.00 | no | +11.36 |  |
| weekly | to3 | 1.00 | 1.00-2.40 | no | +11.36 |  |
| monthly | under2 | 1.00 | 1.00-2.00 | no | +11.35 |  |
| monthly | to3 | 1.00 | 1.00-2.30 | no | +11.35 |  |
| quarterly | under2 | 1.00 | 1.00-2.00 | no | +11.35 |  |
| quarterly | to3 | 1.00 | 1.00-2.10 | no | +11.35 |  |

## Break-even fee (against the price index, no fee)

| reset | L | fee | status |
|---|---|---|---|
| daily | 1.2 | loses | loses at zero fee |
| daily | 1.5 | loses | loses at zero fee |
| daily | 1.7 | loses | loses at zero fee |
| daily | 2 | loses | loses at zero fee |
| daily | 3 | loses | loses at zero fee |
| weekly | 1.2 | loses | loses at zero fee |
| weekly | 1.5 | loses | loses at zero fee |
| weekly | 1.7 | loses | loses at zero fee |
| weekly | 2 | loses | loses at zero fee |
| weekly | 3 | loses | loses at zero fee |
| monthly | 1.2 | loses | loses at zero fee |
| monthly | 1.5 | loses | loses at zero fee |
| monthly | 1.7 | loses | loses at zero fee |
| monthly | 2 | loses | loses at zero fee |
| monthly | 3 | loses | loses at zero fee |
| quarterly | 1.2 | loses | loses at zero fee |
| quarterly | 1.5 | loses | loses at zero fee |
| quarterly | 1.7 | loses | loses at zero fee |
| quarterly | 2 | loses | loses at zero fee |
| quarterly | 3 | loses | loses at zero fee |

## C13 on semiconductors (zero cost, no trigger; ratio of the full-history log gap to the 2x one)

| reset | 2x gap (log) | 1.2x ratio (pred 0.12) | 1.5x ratio (pred 0.375) | 1.7x ratio (pred 0.595) | 3x ratio (pred 3) |
|---|---|---|---|---|---|
| weekly | +0.4853 | 0.137 | 0.413 | 0.634 | 1.763 |
| monthly | +0.4989 | 0.166 | 0.480 | 0.707 | n/a |
| quarterly | -0.4664 | -0.037 | -0.012 | 0.158 | n/a |

## Costs (trigger scaled)

| L | cost | design | CAGR | twin CAGR | 10y median gap |
|---|---|---|---|---|---|
| 2 | zero | HYP_SOX_W_L2.00_scaled | 12.70% | 11.04% | +1.00 |
| 2 | zero | HYP_SOX_M_L2.00_scaled | 12.52% | 11.04% | +1.84 |
| 2 | zero | HYP_SOX_Q_L2.00_scaled | 9.36% | 11.04% | +0.35 |
| 2 | usd | HYP_SOX_W_L2.00_scaled | 10.57% | 8.94% | +0.98 |
| 2 | usd | HYP_SOX_M_L2.00_scaled | 10.37% | 8.94% | +1.78 |
| 2 | usd | HYP_SOX_Q_L2.00_scaled | 7.18% | 8.94% | +0.28 |
| 2 | double | HYP_SOX_W_L2.00_scaled | 8.47% | 6.88% | +0.97 |
| 2 | double | HYP_SOX_M_L2.00_scaled | 8.25% | 6.88% | +1.73 |
| 2 | double | HYP_SOX_Q_L2.00_scaled | 5.03% | 6.88% | +0.22 |
| 3 | zero | HYP_SOX_W_L3.00_scaled | -3.29% | -6.54% | +2.07 |
| 3 | zero | HYP_SOX_M_L3.00_scaled | -9.77% | -6.54% | +1.00 |
| 3 | zero | HYP_SOX_Q_L3.00_scaled | -6.83% | -6.54% | +1.47 |
| 3 | usd | HYP_SOX_W_L3.00_scaled | -6.05% | -9.18% | +1.99 |
| 3 | usd | HYP_SOX_M_L3.00_scaled | -12.48% | -9.18% | +0.88 |
| 3 | usd | HYP_SOX_Q_L3.00_scaled | -9.69% | -9.18% | +1.24 |
| 3 | double | HYP_SOX_W_L3.00_scaled | -8.74% | -11.75% | +1.91 |
| 3 | double | HYP_SOX_M_L3.00_scaled | -15.13% | -11.75% | +0.78 |
| 3 | double | HYP_SOX_Q_L3.00_scaled | -12.49% | -11.75% | +1.00 |

## $10,000 through the key periods (trigger scaled, base cost)

| period | index | HYP_SOX_W_L2.00_scaled | HYP_SOX_M_L2.00_scaled | HYP_SOX_Q_L2.00_scaled | TWIN_L2 | HYP_SOX_W_L3.00_scaled | HYP_SOX_M_L3.00_scaled | HYP_SOX_Q_L3.00_scaled | TWIN_L3 |
|---|---|---|---|---|---|---|---|---|---|
| 2000-02 | $4,105 | $350 | $277 | $191 | $349 | $6 | $1 | $6 | $8 |
| 2008-09 | $8,820 | $5,234 | $5,253 | $4,294 | $4,920 | $2,329 | $1,522 | $1,505 | $1,959 |
| 2020 Feb-Dec | $15,618 | $20,269 | $21,841 | $20,064 | $18,850 | $22,695 | $19,290 | $17,421 | $18,090 |
| 2022 | $6,417 | $3,358 | $3,210 | $3,278 | $3,238 | $1,521 | $1,268 | $1,368 | $1,376 |

## Real AMEX:SOXL (price only) from 2010-03-11 to 2026-09-30

| series | CAGR |
|---|---|
| real AMEX:SOXL | 38.66% |
| 3x daily twin | 31.74% |
| 3x weekly (scaled) | 38.78% |
| 3x monthly (scaled) | 38.75% |
| 3x quarterly (scaled) | 36.87% |
| SOX price index | 24.03% |

SOXL: price only; it tracked SOX until 2021-08-25 and another semiconductor index since (SECONDARY); its filed swap spread is not resolved, so the 3x twin pays USD's spread per turn on 3 turns and the SOXM fee

## Real AMEX:USD (price only) from 2007-02-01 to 2026-09-30

| series | CAGR |
|---|---|
| real AMEX:USD | 28.12% |
| 2x daily twin | 20.09% |
| 2x weekly (scaled) | 22.36% |
| 2x monthly (scaled) | 23.52% |
| 2x quarterly (scaled) | 21.61% |
| SOX price index | 18.32% |

USD: price only, its own semiconductor index (not SOX); its fee and filed spread differ from the twin's

## 5000 simulated decades (252-day blocks of SOX history, base cost)

| L | trigger | reset | wiped | twin wiped | early reset | gap median (10y) | median wealth | p5 wealth |
|---|---|---|---|---|---|---|---|---|
| 1.2 | none | weekly | 0.0% | 0.0% | 0.0% | +0.17 | 3.20 | 0.315 |
| 1.2 | none | monthly | 0.0% | 0.0% | 0.0% | +0.32 | 3.24 | 0.319 |
| 1.2 | none | quarterly | 0.0% | 0.0% | 0.0% | +0.27 | 3.21 | 0.311 |
| 1.2 | scaled | weekly | 0.0% | 0.0% | 0.0% | +0.17 | 3.20 | 0.315 |
| 1.2 | scaled | monthly | 0.0% | 0.0% | 0.0% | +0.32 | 3.24 | 0.319 |
| 1.2 | scaled | quarterly | 0.0% | 0.0% | 0.0% | +0.27 | 3.21 | 0.311 |
| 1.5 | none | weekly | 0.0% | 0.0% | 0.0% | +0.51 | 3.09 | 0.164 |
| 1.5 | none | monthly | 0.0% | 0.0% | 0.0% | +0.89 | 3.23 | 0.167 |
| 1.5 | none | quarterly | 0.0% | 0.0% | 0.0% | +0.62 | 3.10 | 0.148 |
| 1.5 | scaled | weekly | 0.0% | 0.0% | 0.0% | +0.51 | 3.09 | 0.164 |
| 1.5 | scaled | monthly | 0.0% | 0.0% | 0.0% | +0.89 | 3.23 | 0.167 |
| 1.5 | scaled | quarterly | 0.0% | 0.0% | 24.4% | +0.45 | 3.08 | 0.141 |
| 1.7 | none | weekly | 0.0% | 0.0% | 0.0% | +0.77 | 2.87 | 0.095 |
| 1.7 | none | monthly | 0.0% | 0.0% | 0.0% | +1.31 | 2.98 | 0.097 |
| 1.7 | none | quarterly | 0.0% | 0.0% | 0.0% | +0.70 | 2.81 | 0.075 |
| 1.7 | scaled | weekly | 0.0% | 0.0% | 0.0% | +0.77 | 2.87 | 0.095 |
| 1.7 | scaled | monthly | 0.0% | 0.0% | 5.9% | +1.27 | 2.97 | 0.096 |
| 1.7 | scaled | quarterly | 0.0% | 0.0% | 50.5% | +0.12 | 2.65 | 0.072 |
| 2 | none | weekly | 0.0% | 0.0% | 0.0% | +1.18 | 2.29 | 0.037 |
| 2 | none | monthly | 0.0% | 0.0% | 0.0% | +1.87 | 2.46 | 0.037 |
| 2 | none | quarterly | 6.4% | 0.0% | 0.0% | +0.21 | 1.88 | 0.000 |
| 2 | scaled | weekly | 0.0% | 0.0% | 0.0% | +1.18 | 2.29 | 0.037 |
| 2 | scaled | monthly | 0.0% | 0.0% | 27.3% | +1.64 | 2.40 | 0.035 |
| 2 | scaled | quarterly | 0.0% | 0.0% | 79.0% | -1.03 | 1.87 | 0.021 |
| 3 | none | weekly | 0.0% | 0.0% | 0.0% | +2.06 | 0.43 | 0.000 |
| 3 | none | monthly | 26.3% | 0.0% | 0.0% | -0.71 | 0.11 | 0.000 |
| 3 | none | quarterly | 79.4% | 0.0% | 0.0% | -73.46 | 0.00 | 0.000 |
| 3 | scaled | weekly | 0.0% | 0.0% | 31.3% | +1.73 | 0.41 | 0.000 |
| 3 | scaled | monthly | 0.0% | 0.0% | 93.3% | -1.35 | 0.29 | 0.000 |
| 3 | scaled | quarterly | 0.0% | 0.0% | 99.1% | -3.78 | 0.21 | 0.000 |
