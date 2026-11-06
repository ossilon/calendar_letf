# B15: a rolling LEAP against the calendar fund

*Data: TradingView (via local export), FRED. Model option prices and HYPOTHETICAL funds; no real option quotes. Not investment advice.*

```
Inputs: 6 files; prices from <external>/library, rates from <external>/rates
  SP_SPX_daily.csv: 19333 rows, 1950-01-03 to 2026-11-02, sha256 b146c9af89cc
  SP_SPXTR_daily.csv: 9787 rows, 1988-01-04 to 2026-11-03, sha256 edab5090825e
  AMEX_SPY_daily.csv: 8498 rows, 1993-01-29 to 2026-11-02, sha256 643d6ef08b88
  CBOE_VIX_daily.csv: 9275 rows, 1990-01-03 to 2026-10-02, sha256 4dd8691f8a9f
  DFF.csv: 26424 rows, 1954-07-01 to 2026-11-03, sha256 e84a934a5014
  TB3MS.csv: 1112 rows, 1934-01-01 to 2026-08-01, sha256 ebf04b1ae5bc
SPX early-reset trigger: the AMEX:SPY price (daily low) from 1993-01-29, scaled to the SP:SPX price index before that; trigger basis 'etf'; drop 35% from the fund's base; fill mode 'level'.
SPX day counts: financing (reference rate and swap spread) ACT/360; expense ratio ACT/365 (calendar days between rows, so weekends and holidays accrue).
SPX reset dates: last NYSE session of the week / month / quarter from 1970-01-01 (calendar_letf/nyse.py, refuses data that lack it); before that the last row of the period.
Option model: Black-Scholes-Merton with the trailing dividend yield; implied volatility from CBOE:VIX; study end 2026-09-30.
```

Window 1990-01-03 to 2026-09-30 (VIX starts 1990). Two-year calls, leverage set to L at each roll; theta = expanding mean of VIX^2 from 1990 to the day (causal) (0.0437 at the end), kappa 2.0; rate continuous 365 x ln(1 + r / 360) from ACT/360 fed funds; skews {'flat': 0.0, 'base': 0.25, 'steep': 0.5}; base roll cost 0.5% round trip. Index total return: CAGR 11.10%, max DD -55.3%.

## Full window

| L | series | roll / cost | skew | CAGR | max DD | 10y median CAGR | strike / spot (median) | embedded put a year (median) | leverage p5 / median / p95 | untraded |
|---|---|---|---|---|---|---|---|---|---|---|
| 1.2 | LEAP | quarterly / 0.5% | flat | 10.33% | -67.9% | 8.71% | 0.17 | 0.00% | 1.18 / 1.20 / 1.22 | UNTRADED |
| 1.2 | LEAP | quarterly / 0.0% | base | 12.56% | -64.6% | 10.90% | 0.17 | 0.00% | 1.18 / 1.20 / 1.22 | UNTRADED |
| 1.2 | LEAP | quarterly / 0.5% | base | 10.34% | -67.9% | 8.71% | 0.17 | 0.00% | 1.18 / 1.20 / 1.22 | UNTRADED |
| 1.2 | LEAP | quarterly / 1.0% | base | 8.15% | -73.2% | 6.56% | 0.17 | 0.00% | 1.18 / 1.20 / 1.22 | UNTRADED |
| 1.2 | LEAP | quarterly / 0.5% | steep | 10.34% | -67.9% | 8.71% | 0.17 | 0.00% | 1.18 / 1.20 / 1.22 | UNTRADED |
| 1.2 | LEAP | yearly / 0.0% | base | 12.78% | -65.5% | 10.34% | 0.17 | 0.00% | 1.16 / 1.19 / 1.25 | UNTRADED |
| 1.2 | LEAP | yearly / 0.5% | base | 12.22% | -65.8% | 9.79% | 0.17 | 0.00% | 1.16 / 1.19 / 1.25 | UNTRADED |
| 1.2 | LEAP | yearly / 1.0% | base | 11.67% | -66.1% | 9.24% | 0.17 | 0.00% | 1.16 / 1.19 / 1.25 | UNTRADED |
| 1.2 | fund (b19 cost) | quarterly | - | 11.05% | -64.4% | 8.80% | - | - | 1.18 / 1.20 / 1.22 | - |
| 1.2 | fund (base cost) | quarterly | - | 9.95% | -67.6% | 7.72% | - | - | 1.18 / 1.20 / 1.23 | - |
| 1.5 | LEAP | quarterly / 0.5% | flat | 12.05% | -79.3% | 9.51% | 0.34 | 0.00% | 1.44 / 1.49 / 1.57 | UNTRADED |
| 1.5 | LEAP | quarterly / 0.0% | base | 14.36% | -75.0% | 11.76% | 0.34 | 0.01% | 1.44 / 1.49 / 1.56 | UNTRADED |
| 1.5 | LEAP | quarterly / 0.5% | base | 12.09% | -79.1% | 9.54% | 0.34 | 0.01% | 1.44 / 1.49 / 1.56 | UNTRADED |
| 1.5 | LEAP | quarterly / 1.0% | base | 9.87% | -82.6% | 7.37% | 0.34 | 0.01% | 1.44 / 1.49 / 1.56 | UNTRADED |
| 1.5 | LEAP | quarterly / 0.5% | steep | 12.05% | -79.2% | 9.53% | 0.34 | 0.04% | 1.44 / 1.49 / 1.56 | UNTRADED |
| 1.5 | LEAP | yearly / 0.0% | base | 14.37% | -77.7% | 10.95% | 0.34 | 0.01% | 1.38 / 1.47 / 1.65 | UNTRADED |
| 1.5 | LEAP | yearly / 0.5% | base | 13.80% | -78.7% | 10.40% | 0.34 | 0.01% | 1.38 / 1.47 / 1.65 | UNTRADED |
| 1.5 | LEAP | yearly / 1.0% | base | 13.24% | -79.7% | 9.85% | 0.34 | 0.01% | 1.38 / 1.47 / 1.65 | UNTRADED |
| 1.5 | fund (b19 cost) | quarterly | - | 12.81% | -76.1% | 9.58% | - | - | 1.44 / 1.49 / 1.57 | - |
| 1.5 | fund (base cost) | quarterly | - | 11.43% | -78.8% | 8.22% | - | - | 1.44 / 1.49 / 1.57 | - |
| 1.7 | LEAP | quarterly / 0.5% | flat | 13.14% | -84.6% | 9.93% | 0.42 | 0.00% | 1.60 / 1.68 / 1.80 | UNTRADED |
| 1.7 | LEAP | quarterly / 0.0% | base | 15.46% | -81.5% | 12.19% | 0.42 | 0.03% | 1.61 / 1.68 / 1.79 | UNTRADED |
| 1.7 | LEAP | quarterly / 0.5% | base | 13.17% | -84.5% | 9.97% | 0.42 | 0.03% | 1.61 / 1.68 / 1.79 | UNTRADED |
| 1.7 | LEAP | quarterly / 1.0% | base | 10.93% | -87.1% | 7.79% | 0.42 | 0.03% | 1.61 / 1.68 / 1.79 | UNTRADED |
| 1.7 | LEAP | quarterly / 0.5% | steep | 13.02% | -84.8% | 9.88% | 0.43 | 0.12% | 1.62 / 1.69 / 1.78 | UNTRADED |
| 1.7 | LEAP | yearly / 0.0% | base | 15.22% | -84.9% | 11.22% | 0.42 | 0.04% | 1.52 / 1.66 / 1.94 | UNTRADED |
| 1.7 | LEAP | yearly / 0.5% | base | 14.65% | -85.5% | 10.66% | 0.42 | 0.04% | 1.52 / 1.66 / 1.94 | UNTRADED |
| 1.7 | LEAP | yearly / 1.0% | base | 14.09% | -86.2% | 10.11% | 0.42 | 0.04% | 1.52 / 1.66 / 1.94 | UNTRADED |
| 1.7 | fund (b19 cost) | quarterly | - | 13.84% | -82.2% | 9.96% | - | - | 1.60 / 1.68 / 1.81 | - |
| 1.7 | fund (base cost) | quarterly | - | 12.26% | -84.4% | 8.41% | - | - | 1.60 / 1.69 / 1.82 | - |
| 2 | LEAP | quarterly / 0.5% | flat | 14.75% | -90.1% | 10.52% | 0.51 | 0.05% | 1.85 / 1.97 / 2.15 | - |
| 2 | LEAP | quarterly / 0.0% | base | 16.92% | -88.4% | 12.68% | 0.52 | 0.18% | 1.87 / 1.98 / 2.13 | - |
| 2 | LEAP | quarterly / 0.5% | base | 14.60% | -90.3% | 10.44% | 0.52 | 0.18% | 1.87 / 1.98 / 2.13 | - |
| 2 | LEAP | quarterly / 1.0% | base | 12.34% | -91.9% | 8.26% | 0.52 | 0.18% | 1.87 / 1.98 / 2.13 | - |
| 2 | LEAP | quarterly / 0.5% | steep | 14.17% | -90.9% | 10.18% | 0.53 | 0.43% | 1.88 / 1.98 / 2.12 | - |
| 2 | LEAP | yearly / 0.0% | base | 16.22% | -91.9% | 11.04% | 0.52 | 0.20% | 1.73 / 1.94 / 2.41 | - |
| 2 | LEAP | yearly / 0.5% | base | 15.64% | -92.3% | 10.49% | 0.52 | 0.20% | 1.73 / 1.94 / 2.41 | - |
| 2 | LEAP | yearly / 1.0% | base | 15.07% | -92.6% | 9.94% | 0.52 | 0.20% | 1.73 / 1.94 / 2.41 | - |
| 2 | fund (b19 cost) | quarterly | - | 14.10% | -92.0% | 9.50% | - | - | 1.83 / 1.97 / 2.19 | - |
| 2 | fund (base cost) | quarterly | - | 12.23% | -93.3% | 7.68% | - | - | 1.84 / 1.98 / 2.19 | - |

## LEAP minus fund (B19 cost), yearly paired log differences, pp a year [95%] and coverage verdict

| L | roll | cost per roll | years | mean | 95% interval | verdict |
|---|---|---|---|---|---|---|
| 1.2 | quarterly | 0.0% | 1991-2025 (35) | +1.68 | [+1.36, +2.00] | too narrow |
| 1.2 | quarterly | 0.5% | 1991-2025 (35) | -0.32 | [-0.64, -0.00] | too narrow |
| 1.2 | quarterly | 1.0% | 1991-2025 (35) | -2.32 | [-2.64, -2.00] | too narrow |
| 1.2 | yearly | 0.0% | 1991-2025 (35) | +1.54 | [+1.12, +1.95] | too narrow |
| 1.2 | yearly | 0.5% | 1991-2025 (35) | +1.04 | [+0.62, +1.45] | too narrow |
| 1.2 | yearly | 1.0% | 1991-2025 (35) | +0.54 | [+0.12, +0.95] | too narrow |
| 1.5 | quarterly | 0.0% | 1991-2025 (35) | +1.81 | [+1.16, +2.46] | too narrow |
| 1.5 | quarterly | 0.5% | 1991-2025 (35) | -0.19 | [-0.84, +0.46] | too narrow; covers zero |
| 1.5 | quarterly | 1.0% | 1991-2025 (35) | -2.19 | [-2.84, -1.54] | valid |
| 1.5 | yearly | 0.0% | 1991-2025 (35) | +1.34 | [+0.20, +2.48] | too narrow |
| 1.5 | yearly | 0.5% | 1991-2025 (35) | +0.84 | [-0.30, +1.98] | too narrow; covers zero |
| 1.5 | yearly | 1.0% | 1991-2025 (35) | +0.34 | [-0.80, +1.48] | too narrow; covers zero |
| 1.7 | quarterly | 0.0% | 1991-2025 (35) | +1.94 | [+1.06, +2.82] | too narrow |
| 1.7 | quarterly | 0.5% | 1991-2025 (35) | -0.06 | [-0.94, +0.82] | too narrow; covers zero |
| 1.7 | quarterly | 1.0% | 1991-2025 (35) | -2.06 | [-2.94, -1.18] | too narrow |
| 1.7 | yearly | 0.0% | 1991-2025 (35) | +1.16 | [-0.55, +2.88] | too narrow; covers zero |
| 1.7 | yearly | 0.5% | 1991-2025 (35) | +0.66 | [-1.05, +2.38] | too narrow; covers zero |
| 1.7 | yearly | 1.0% | 1991-2025 (35) | +0.16 | [-1.55, +1.88] | too narrow; covers zero |
| 2 | quarterly | 0.0% | 1991-2025 (35) | +3.11 | [+1.48, +4.74] | valid |
| 2 | quarterly | 0.5% | 1991-2025 (35) | +1.11 | [-0.52, +2.74] | valid; covers zero |
| 2 | quarterly | 1.0% | 1991-2025 (35) | -0.89 | [-2.52, +0.74] | valid; covers zero |
| 2 | yearly | 0.0% | 1991-2025 (35) | +1.79 | [+0.55, +3.02] | valid |
| 2 | yearly | 0.5% | 1991-2025 (35) | +1.29 | [+0.05, +2.52] | valid |
| 2 | yearly | 1.0% | 1991-2025 (35) | +0.79 | [-0.45, +2.02] | valid; covers zero |

## Key periods and bottoms ($10,000; base skew, base roll cost, quarterly roll)

| period | bottom | LEAP 1.2x: period / 3y from bottom | fund 1.2x: period / 3y from bottom | LEAP 1.5x: period / 3y from bottom | fund 1.5x: period / 3y from bottom | LEAP 1.7x: period / 3y from bottom | fund 1.7x: period / 3y from bottom | LEAP 2x: period / 3y from bottom | fund 2x: period / 3y from bottom | index: period / 3y from bottom |
|---|---|---|---|---|---|---|---|---|---|---|
| 2000-02 | 2002-10-09 | $4,995 / $16,601 | $5,185 / $16,822 | $3,926 / $18,852 | $4,155 / $18,870 | $3,326 / $20,409 | $3,551 / $20,333 | $2,575 / $22,716 | $2,763 / $22,681 | $6,239 / $16,239 |
| 2008-09 | 2009-03-09 | $6,922 / $23,857 | $7,210 / $23,894 | $5,972 / $29,657 | $6,409 / $29,643 | $5,374 / $34,128 | $5,870 / $34,240 | $4,547 / $41,702 | $3,661 / $42,648 | $7,968 / $21,584 |
| 2020 Feb-Dec | 2020-03-23 | $11,861 / $20,067 | $11,918 / $19,884 | $12,142 / $24,162 | $12,171 / $23,707 | $12,397 / $26,953 | $12,267 / $26,820 | $12,869 / $31,081 | $12,291 / $32,839 | $11,845 / $18,524 |
| 2022 | 2022-10-12 | $7,722 / $20,046 | $7,672 / $20,127 | $7,328 / $23,184 | $7,092 / $23,045 | $7,062 / $25,450 | $6,711 / $25,164 | $6,660 / $29,051 | $6,149 / $28,621 | $8,189 / $19,148 |
