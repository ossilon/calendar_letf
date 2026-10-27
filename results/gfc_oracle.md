# The GFC oracle entry: $10,000 at the crash low, held to the end of the data

A HINDSIGHT entry: the close of the lowest index close from 2007-01-01 to 2009-12-31. Nobody knew that day on the day. One path from one date, so no interval exists; read it as an illustration, not a statistic. The calendar products and the daily twins are MODELED (no calendar fund existed before 2024-08-30); the real 2x and 3x funds are price only, distributions NOT reinvested (the export holds prices only), so the real funds' total return is higher. Not investment advice.

## Inputs, costs and conventions

```text
Inputs: 12 files; prices from <external>/library, rates from <external>/rates
  SP_SPX_daily.csv: 19326 rows, 1950-01-03 to 2026-10-22, sha256 8b0c1596b57e
  SP_SPXTR_daily.csv: 9780 rows, 1988-01-04 to 2026-10-23, sha256 ac309a0b90f5
  AMEX_SPY_daily.csv: 8482 rows, 1993-01-29 to 2026-10-09, sha256 38bb2ae821ff
  NASDAQ_NDX_daily.csv: 10504 rows, 1985-01-31 to 2026-10-09, sha256 4c3219bda720
  NASDAQ_XNDX_daily.csv: 5004 rows, 2006-11-08 to 2026-10-09, sha256 a10dab98993e
  NASDAQ_QQQ_daily.csv: 6940 rows, 1999-03-10 to 2026-10-09, sha256 1bf106f83579
  AMEX_SSO_daily.csv: 5103 rows, 2006-06-21 to 2026-10-02, sha256 9f248b1bedac
  AMEX_UPRO_daily.csv: 4345 rows, 2009-06-25 to 2026-10-02, sha256 2462a547956a
  AMEX_QLD_daily.csv: 5108 rows, 2006-06-21 to 2026-10-09, sha256 298046184b2f
  NASDAQ_TQQQ_daily.csv: 4191 rows, 2010-02-11 to 2026-10-09, sha256 d3dc0fa8dc69
  DFF.csv: 26398 rows, 1954-07-01 to 2026-10-08, sha256 a93504210b53
  TB3MS.csv: 1112 rows, 1934-01-01 to 2026-08-01, sha256 ebf04b1ae5bc
SPX early-reset trigger: the AMEX:SPY price (daily low) from 1993-01-29, scaled to the SP:SPX price index before that; trigger basis 'etf'; drop 35% from the fund's base; fill mode 'level'.
SPX day counts: financing (reference rate and swap spread) ACT/360; expense ratio ACT/365 (calendar days between rows, so weekends and holidays accrue).
SPX reset dates: last NYSE session of the week / month / quarter from 1970-01-01 (calendar_letf/nyse.py, refuses data that lack it); before that the last row of the period.
NDX early-reset trigger: the NASDAQ:QQQ price (daily low) from 1999-03-10, scaled to the NASDAQ:NDX price index before that; trigger basis 'etf'; drop 35% from the fund's base; fill mode 'level'.
NDX day counts: financing (reference rate and swap spread) ACT/360; expense ratio ACT/365 (calendar days between rows, so weekends and holidays accrue).
NDX reset dates: last NYSE session of the week / month / quarter from 1970-01-01 (calendar_letf/nyse.py, refuses data that lack it); before that the last row of the period.
PRODUCT SPYQ: kind=LIVE underlying=SPX reset=quarterly L=2 early reset at -35% [VERIFIED_prospectus_2026-07-31] inception=2024-09-30
  costs: SPYQ: fee 1.00% [VERIFIED_prospectus_2026-07-31]; spread 1.10% per turn over DFF [ASSUMED] x 2 turns [ASSUMED, notional basis] = 2.20% of NAV a year
PRODUCT HYP_SPX_M: kind=MODELED underlying=SPX reset=monthly L=2 early reset at -35% [ASSUMED]
  costs: HYP_SPX_M: fee 1.00% [ASSUMED]; spread 1.10% per turn over DFF [ASSUMED] x 2 turns [ASSUMED, notional basis] = 2.20% of NAV a year
  MODELED: a live fund of this design traded 2024-08-30 to 2025-02-28; no live fund exists today
PRODUCT HYP_SPX_W: kind=MODELED underlying=SPX reset=weekly L=2 early reset at -35% [ASSUMED]
  costs: HYP_SPX_W: fee 1.00% [ASSUMED]; spread 1.10% per turn over DFF [ASSUMED] x 2 turns [ASSUMED, notional basis] = 2.20% of NAV a year
  MODELED: a live fund of this design traded 2024-08-30 to 2025-02-28; no live fund exists today
PRODUCT TWIN_SPYQ: kind=DAILY_TWIN underlying=SPX reset=daily L=2 no early reset
  costs: TWIN_SPYQ: fee 1.00% [VERIFIED_prospectus_2026-07-31]; spread 1.10% per turn over DFF [ASSUMED] x 2 turns [ASSUMED, notional basis] = 2.20% of NAV a year
  DAILY TWIN: synthetic comparison series
PRODUCT TWIN_HYP_SPX_M: kind=DAILY_TWIN underlying=SPX reset=daily L=2 no early reset
  costs: TWIN_HYP_SPX_M: fee 1.00% [ASSUMED]; spread 1.10% per turn over DFF [ASSUMED] x 2 turns [ASSUMED, notional basis] = 2.20% of NAV a year
  DAILY TWIN: synthetic comparison series
PRODUCT TWIN_HYP_SPX_W: kind=DAILY_TWIN underlying=SPX reset=daily L=2 no early reset
  costs: TWIN_HYP_SPX_W: fee 1.00% [ASSUMED]; spread 1.10% per turn over DFF [ASSUMED] x 2 turns [ASSUMED, notional basis] = 2.20% of NAV a year
  DAILY TWIN: synthetic comparison series
SPREAD SENSITIVITY: the registry spread (1.10% per turn) is a default that every published table overrides (the two historical encodings or the filed spread); sensitivity range 0.80% to 1.40% per turn; no calendar fund publishes its swap spread
OVERRIDES: spread_per_nav and the rate multiplier come from the cost encodings below
WARNING: SPYQ: spread 0.011 is ASSUMED (an earlier private kit's calibration 2026-10-11, midpoint of MQQQ 1.43% and QQQP 0.77% fitted on price return)
WARNING: SPYQ: turns 2.0 is ASSUMED (notional basis, turns = L: the 2x convention an earlier private kit's spreads were fitted under (DESIGN 4.1). Contradicted by the N-PORT structure in ASSUMPTIONS section 6 (~1.5 swap turns plus a direct ETF holding); superseded by the step-2 refit and overridden in every published table)
WARNING: HYP_SPX_M: fee 0.01 is ASSUMED (same as the live funds today (1.00% for SPYQ and QQQP); the liquidated fund of this design paid the 1.30% expense cap while it traded)
WARNING: HYP_SPX_M: spread 0.011 is ASSUMED (an earlier private kit's calibration 2026-10-11, midpoint of MQQQ 1.43% and QQQP 0.77% fitted on price return)
WARNING: HYP_SPX_M: turns 2.0 is ASSUMED (notional basis, turns = L: the 2x convention an earlier private kit's spreads were fitted under (DESIGN 4.1). Contradicted by the N-PORT structure in ASSUMPTIONS section 6 (~1.5 swap turns plus a direct ETF holding); superseded by the step-2 refit and overridden in every published table)
WARNING: HYP_SPX_M: early-reset trigger 0.35 is ASSUMED (same -35% trigger as the live funds; the liquidated fund of this design had the same trigger)
WARNING: HYP_SPX_W: fee 0.01 is ASSUMED (same as the live funds today (1.00% for SPYQ and QQQP); the liquidated fund of this design paid the 1.30% expense cap while it traded)
WARNING: HYP_SPX_W: spread 0.011 is ASSUMED (an earlier private kit's calibration 2026-10-11, midpoint of MQQQ 1.43% and QQQP 0.77% fitted on price return)
WARNING: HYP_SPX_W: turns 2.0 is ASSUMED (notional basis, turns = L: the 2x convention an earlier private kit's spreads were fitted under (DESIGN 4.1). Contradicted by the N-PORT structure in ASSUMPTIONS section 6 (~1.5 swap turns plus a direct ETF holding); superseded by the step-2 refit and overridden in every published table)
WARNING: HYP_SPX_W: early-reset trigger 0.35 is ASSUMED (same -35% trigger as the live funds; the liquidated fund of this design had the same trigger)
WARNING: TWIN_SPYQ: spread 0.011 is ASSUMED (an earlier private kit's calibration 2026-10-11, midpoint of MQQQ 1.43% and QQQP 0.77% fitted on price return)
WARNING: TWIN_SPYQ: turns 2.0 is ASSUMED (notional basis, turns = L: the 2x convention an earlier private kit's spreads were fitted under (DESIGN 4.1). Contradicted by the N-PORT structure in ASSUMPTIONS section 6 (~1.5 swap turns plus a direct ETF holding); superseded by the step-2 refit and overridden in every published table)
WARNING: TWIN_HYP_SPX_M: fee 0.01 is ASSUMED (copied from HYP_SPX_M: same as the live funds today (1.00% for SPYQ and QQQP); the liquidated fund of this design paid the 1.30% expense cap while it traded)
WARNING: TWIN_HYP_SPX_M: spread 0.011 is ASSUMED (an earlier private kit's calibration 2026-10-11, midpoint of MQQQ 1.43% and QQQP 0.77% fitted on price return)
WARNING: TWIN_HYP_SPX_M: turns 2.0 is ASSUMED (notional basis, turns = L: the 2x convention an earlier private kit's spreads were fitted under (DESIGN 4.1). Contradicted by the N-PORT structure in ASSUMPTIONS section 6 (~1.5 swap turns plus a direct ETF holding); superseded by the step-2 refit and overridden in every published table)
WARNING: TWIN_HYP_SPX_W: fee 0.01 is ASSUMED (copied from HYP_SPX_W: same as the live funds today (1.00% for SPYQ and QQQP); the liquidated fund of this design paid the 1.30% expense cap while it traded)
WARNING: TWIN_HYP_SPX_W: spread 0.011 is ASSUMED (an earlier private kit's calibration 2026-10-11, midpoint of MQQQ 1.43% and QQQP 0.77% fitted on price return)
WARNING: TWIN_HYP_SPX_W: turns 2.0 is ASSUMED (notional basis, turns = L: the 2x convention an earlier private kit's spreads were fitted under (DESIGN 4.1). Contradicted by the N-PORT structure in ASSUMPTIONS section 6 (~1.5 swap turns plus a direct ETF holding); superseded by the step-2 refit and overridden in every published table)
3x MODEL UPRO_MODEL (filed terms, plain reference rate, daily reset): UPRO_MODEL: fee 0.89% [VERIFIED_issuer_page_2026-09-25_RECHECK]; spread 0.92% per turn over DFF [VERIFIED_NPORT_2026-05-31] x 2.4215 turns [VERIFIED_NPORT_2026-05-31, swaps basis] = 2.23% of NAV a year
PRODUCT MQQQ: kind=LIVE underlying=NDX reset=monthly L=2 early reset at -35% [VERIFIED_prospectus_2026-07-31] inception=2024-08-30
  costs: MQQQ: fee 1.03% [VERIFIED_prospectus_2026-07-31]; spread 1.10% per turn over DFF [ASSUMED] x 2 turns [ASSUMED, notional basis] = 2.20% of NAV a year
PRODUCT QQQP: kind=LIVE underlying=NDX reset=quarterly L=2 early reset at -35% [VERIFIED_prospectus_2026-07-31] inception=2024-09-30
  costs: QQQP: fee 1.00% [VERIFIED_prospectus_2026-07-31]; spread 1.10% per turn over DFF [ASSUMED] x 2 turns [ASSUMED, notional basis] = 2.20% of NAV a year
PRODUCT HYP_NDX_W: kind=MODELED underlying=NDX reset=weekly L=2 early reset at -35% [ASSUMED]
  costs: HYP_NDX_W: fee 1.00% [ASSUMED]; spread 1.10% per turn over DFF [ASSUMED] x 2 turns [ASSUMED, notional basis] = 2.20% of NAV a year
  MODELED: a live fund of this design traded 2024-08-30 to 2025-02-28; no live fund exists today
PRODUCT TWIN_MQQQ: kind=DAILY_TWIN underlying=NDX reset=daily L=2 no early reset
  costs: TWIN_MQQQ: fee 1.03% [VERIFIED_prospectus_2026-07-31]; spread 1.10% per turn over DFF [ASSUMED] x 2 turns [ASSUMED, notional basis] = 2.20% of NAV a year
  DAILY TWIN: synthetic comparison series
PRODUCT TWIN_QQQP: kind=DAILY_TWIN underlying=NDX reset=daily L=2 no early reset
  costs: TWIN_QQQP: fee 1.00% [VERIFIED_prospectus_2026-07-31]; spread 1.10% per turn over DFF [ASSUMED] x 2 turns [ASSUMED, notional basis] = 2.20% of NAV a year
  DAILY TWIN: synthetic comparison series
PRODUCT TWIN_HYP_NDX_W: kind=DAILY_TWIN underlying=NDX reset=daily L=2 no early reset
  costs: TWIN_HYP_NDX_W: fee 1.00% [ASSUMED]; spread 1.10% per turn over DFF [ASSUMED] x 2 turns [ASSUMED, notional basis] = 2.20% of NAV a year
  DAILY TWIN: synthetic comparison series
SPREAD SENSITIVITY: the registry spread (1.10% per turn) is a default that every published table overrides (the two historical encodings or the filed spread); sensitivity range 0.80% to 1.40% per turn; no calendar fund publishes its swap spread
OVERRIDES: spread_per_nav and the rate multiplier come from the cost encodings below
WARNING: MQQQ: spread 0.011 is ASSUMED (an earlier private kit's calibration 2026-10-11, midpoint of MQQQ 1.43% and QQQP 0.77% fitted on price return)
WARNING: MQQQ: turns 2.0 is ASSUMED (notional basis, turns = L: the 2x convention an earlier private kit's spreads were fitted under (DESIGN 4.1). Contradicted by the N-PORT structure in ASSUMPTIONS section 6 (~1.5 swap turns plus a direct ETF holding); superseded by the step-2 refit and overridden in every published table)
WARNING: QQQP: spread 0.011 is ASSUMED (an earlier private kit's calibration 2026-10-11, midpoint of MQQQ 1.43% and QQQP 0.77% fitted on price return)
WARNING: QQQP: turns 2.0 is ASSUMED (notional basis, turns = L: the 2x convention an earlier private kit's spreads were fitted under (DESIGN 4.1). Contradicted by the N-PORT structure in ASSUMPTIONS section 6 (~1.5 swap turns plus a direct ETF holding); superseded by the step-2 refit and overridden in every published table)
WARNING: HYP_NDX_W: fee 0.01 is ASSUMED (same as the live funds today (1.00% for SPYQ and QQQP); the liquidated fund of this design paid the 1.30% expense cap while it traded)
WARNING: HYP_NDX_W: spread 0.011 is ASSUMED (an earlier private kit's calibration 2026-10-11, midpoint of MQQQ 1.43% and QQQP 0.77% fitted on price return)
WARNING: HYP_NDX_W: turns 2.0 is ASSUMED (notional basis, turns = L: the 2x convention an earlier private kit's spreads were fitted under (DESIGN 4.1). Contradicted by the N-PORT structure in ASSUMPTIONS section 6 (~1.5 swap turns plus a direct ETF holding); superseded by the step-2 refit and overridden in every published table)
WARNING: HYP_NDX_W: early-reset trigger 0.35 is ASSUMED (same -35% trigger as the live funds; the liquidated fund of this design had the same trigger)
WARNING: TWIN_MQQQ: spread 0.011 is ASSUMED (an earlier private kit's calibration 2026-10-11, midpoint of MQQQ 1.43% and QQQP 0.77% fitted on price return)
WARNING: TWIN_MQQQ: turns 2.0 is ASSUMED (notional basis, turns = L: the 2x convention an earlier private kit's spreads were fitted under (DESIGN 4.1). Contradicted by the N-PORT structure in ASSUMPTIONS section 6 (~1.5 swap turns plus a direct ETF holding); superseded by the step-2 refit and overridden in every published table)
WARNING: TWIN_QQQP: spread 0.011 is ASSUMED (an earlier private kit's calibration 2026-10-11, midpoint of MQQQ 1.43% and QQQP 0.77% fitted on price return)
WARNING: TWIN_QQQP: turns 2.0 is ASSUMED (notional basis, turns = L: the 2x convention an earlier private kit's spreads were fitted under (DESIGN 4.1). Contradicted by the N-PORT structure in ASSUMPTIONS section 6 (~1.5 swap turns plus a direct ETF holding); superseded by the step-2 refit and overridden in every published table)
WARNING: TWIN_HYP_NDX_W: fee 0.01 is ASSUMED (copied from HYP_NDX_W: same as the live funds today (1.00% for SPYQ and QQQP); the liquidated fund of this design paid the 1.30% expense cap while it traded)
WARNING: TWIN_HYP_NDX_W: spread 0.011 is ASSUMED (an earlier private kit's calibration 2026-10-11, midpoint of MQQQ 1.43% and QQQP 0.77% fitted on price return)
WARNING: TWIN_HYP_NDX_W: turns 2.0 is ASSUMED (notional basis, turns = L: the 2x convention an earlier private kit's spreads were fitted under (DESIGN 4.1). Contradicted by the N-PORT structure in ASSUMPTIONS section 6 (~1.5 swap turns plus a direct ETF holding); superseded by the step-2 refit and overridden in every published table)
3x MODEL TQQQ_MODEL (filed terms, plain reference rate, daily reset): TQQQ_MODEL: fee 0.82% [ASSUMED]; spread 1.06% per turn over DFF [VERIFIED_NPORT_2026-05-31] x 2.563 turns [VERIFIED_NPORT_2026-05-31, swaps basis] = 2.71% of NAV a year
  WARNING: TQQQ_MODEL: fee 0.0082 is ASSUMED (0.82% as given in the B13 brief (issuer page); no TQQQ expense ratio is on file, so not re-verified here)
COST ENCODING fixed (ASSUMED): fixed spread 2.6% of NAV: spread 2.60% of NAV a year + 1 x reference rate on the borrowed turn + product fee [ASSUMED]
COST ENCODING rate (ASSUMED): rate-proportional (1.4% spread + 1.3 x rate): spread 1.40% of NAV a year + 1.3 x reference rate on the borrowed turn + product fee [ASSUMED]
Real funds: price only, distributions NOT reinvested (the export holds prices only), so the real funds' total return is higher.
MODELED: a live fund of this design traded 2024-08-30 to 2025-02-28; no live fund exists today
```

## S&P 500

Entry: the close of 2009-03-09, after a fall of 56.8% from the highest close since 2007-01-01. End: 2026-10-02, the last date common to the index, SSO and UPRO; 17.6 years. Leverage at entry: the calendar fund's exposure after the entry close. It is above 2x while the index stays below the level of the fund's last reset and below 2x once the index climbs above it; an early reset sets it back to 2x.

| product | kind | leverage at entry | $10,000 became (fixed) | CAGR (fixed) | worst fall after entry (fixed) | early resets | $10,000 became (rate) | end value / SSO (fixed / rate) |
|---|---|---|---|---|---|---|---|---|
| SPYQ (quarterly) | MODELED calendar (live design) | 3.01x | $715,067 | +27.5% | -65% | 0 | $813,868 | 0.92 / 1.05 |
| its 2x daily twin | MODELED, same costs | 2.00x | $590,843 | +26.1% | -59% |  | $676,995 | 0.76 / 0.87 |
| HYP_SPX_M (monthly) | MODELED calendar | 2.19x | $703,542 | +27.4% | -61% | 0 | $804,289 | 0.91 / 1.04 |
| its 2x daily twin | MODELED, same costs | 2.00x | $590,843 | +26.1% | -59% |  | $676,995 | 0.76 / 0.87 |
| HYP_SPX_W (weekly) | MODELED calendar | 2.02x | $625,447 | +26.5% | -59% | 0 | $716,350 | 0.81 / 0.92 |
| its 2x daily twin | MODELED, same costs | 2.00x | $590,843 | +26.1% | -59% |  | $676,995 | 0.76 / 0.87 |
| UPRO_MODEL | MODEL, filed terms | 3.00x | $2,608,783 | +37.3% | -77% |  |  |  |
| SSO | REAL, price only | 2x daily | $776,671 | +28.1% | -59% |  |  |  |
| 1x index | 1x total-return index | 1.00x | $158,186 | +17.0% | -34% |  |  |  |

**UPRO launched after the low.** From its first close (2009-06-25, 17.3 years), the real fund next to its model (a check of the model):

| series | kind | $10,000 became | CAGR | worst fall |
|---|---|---|---|---|
| UPRO | REAL 3x fund (price only) | $1,251,553 | +32.3% | -77% |
| UPRO_MODEL | MODEL 3x daily (filed terms) | $1,126,404 | +31.5% | -77% |
| SSO | REAL 2x fund (price only) | $432,012 | +24.4% | -59% |
| 1x index | 1x total-return index | $115,481 | +15.2% | -34% |

**Sensitivity: the entry moved around the low**, every session from -10 to +21. The lead is the calendar fund's end value divided by its daily twin's, both bought at the close of that session and held to the end; above 1 the calendar fund ends ahead. The table gives the summary only: one lead per session would be a daily series (data/README, licensing).

| product | lowest lead (shift) | highest lead (shift) | shifts below 1 (fixed) | shifts below 1 (rate) |
|---|---|---|---|---|
| SPYQ (quarterly) | 1.068 (+13) | 1.210 (+0) | none | none |
| HYP_SPX_M (monthly) | 1.170 (+15) | 1.191 (+0) | none | none |
| HYP_SPX_W (weekly) | 1.056 (-3) | 1.064 (+7) | none | none |

**Sensitivity: the other index's low date (2008-11-20), fixed encoding.**

| series | $10,000 became | CAGR |
|---|---|---|
| SPYQ | $501,554 | +24.5% |
| TWIN_SPYQ | $454,480 | +23.8% |
| HYP_SPX_M | $601,404 | +25.8% |
| TWIN_HYP_SPX_M | $454,480 | +23.8% |
| HYP_SPX_W | $498,520 | +24.5% |
| TWIN_HYP_SPX_W | $454,480 | +23.8% |
| UPRO_MODEL | $1,621,093 | +33.0% |
| SSO | $594,045 | +25.7% |
| 1x index | $143,627 | +16.1% |

## Nasdaq-100

Entry: the close of 2008-11-20, after a fall of 53.7% from the highest close since 2007-01-01. End: 2026-10-09, the last date common to the index, QLD and TQQQ; 17.9 years. Leverage at entry: the calendar fund's exposure after the entry close. It is above 2x while the index stays below the level of the fund's last reset and below 2x once the index climbs above it; an early reset sets it back to 2x.

| product | kind | leverage at entry | $10,000 became (fixed) | CAGR (fixed) | worst fall after entry (fixed) | early resets | $10,000 became (rate) | end value / QLD (fixed / rate) |
|---|---|---|---|---|---|---|---|---|
| MQQQ (monthly) | MODELED calendar (live design) | 2.82x | $3,080,655 | +37.8% | -64% | 0 | $3,531,497 | 1.01 / 1.16 |
| its 2x daily twin | MODELED, same costs | 2.00x | $2,200,375 | +35.2% | -64% |  | $2,529,850 | 0.72 / 0.83 |
| QQQP (quarterly) | MODELED calendar (live design) | 4.40x | $2,499,635 | +36.2% | -64% | 1 (first 2008-11-21) | $2,853,159 | 0.82 / 0.93 |
| its 2x daily twin | MODELED, same costs | 2.00x | $2,212,211 | +35.2% | -64% |  | $2,543,458 | 0.72 / 0.83 |
| HYP_NDX_W (weekly) | MODELED calendar | 2.32x | $2,576,009 | +36.4% | -64% | 0 | $2,960,223 | 0.84 / 0.97 |
| its 2x daily twin | MODELED, same costs | 2.00x | $2,212,211 | +35.2% | -64% |  | $2,543,458 | 0.72 / 0.83 |
| TQQQ_MODEL | MODEL, filed terms | 3.00x | $11,505,261 | +48.3% | -82% |  |  |  |
| QLD | REAL, price only | 2x daily | $3,053,260 | +37.7% | -64% |  |  |  |
| 1x index | 1x total-return index | 1.00x | $355,113 | +22.1% | -35% |  |  |  |

**TQQQ launched after the low.** From its first close (2010-02-11, 16.7 years), the real fund next to its model (a check of the model):

| series | kind | $10,000 became | CAGR | worst fall |
|---|---|---|---|---|
| TQQQ | REAL 3x fund (price only) | $3,758,161 | +42.8% | -82% |
| TQQQ_MODEL | MODEL 3x daily (filed terms) | $3,191,084 | +41.4% | -82% |
| QLD | REAL 2x fund (price only) | $1,171,667 | +33.1% | -64% |
| 1x index | 1x total-return index | $205,477 | +19.9% | -35% |

**Sensitivity: the entry moved around the low**, every session from -10 to +21. The lead is the calendar fund's end value divided by its daily twin's, both bought at the close of that session and held to the end; above 1 the calendar fund ends ahead. The table gives the summary only: one lead per session would be a daily series (data/README, licensing).

| product | lowest lead (shift) | highest lead (shift) | shifts below 1 (fixed) | shifts below 1 (rate) |
|---|---|---|---|---|
| MQQQ (monthly) | 1.268 (+21) | 1.400 (+0) | none | none |
| QQQP (quarterly) | 0.865 (-9) | 1.175 (+4) | -10, -9, -8, -7, -6, -5, -4, -3, -2 | -10, -9, -8, -7, -6, -5, -4, -3, -2 |
| HYP_NDX_W (weekly) | 1.129 (+21) | 1.164 (+0) | none | none |

**Sensitivity: the other index's low date (2009-03-09), fixed encoding.**

| series | $10,000 became | CAGR |
|---|---|---|
| MQQQ | $2,876,947 | +38.0% |
| TWIN_MQQQ | $2,307,470 | +36.3% |
| QQQP | $2,683,335 | +37.4% |
| TWIN_QQQP | $2,319,672 | +36.3% |
| HYP_NDX_W | $2,603,969 | +37.2% |
| TWIN_HYP_NDX_W | $2,319,672 | +36.3% |
| TQQQ_MODEL | $13,346,584 | +50.6% |
| QLD | $3,213,221 | +38.9% |
| 1x index | $351,842 | +22.4% |

## How to read it

- A calendar fund bought at the low partway through its period holds more than 2x until the index regains the level of its last reset (see the leverage note above), so its start into the rebound carries extra exposure. This study does not split each lead into its causes.
- Each daily twin is a daily-reset fund like the real 2x fund, with the costs fitted to the live calendar funds (ASSUMPTIONS section 2, two ASSUMED encodings). The twins end at 0.72 to 0.87 times the real 2x fund's value (price only), so whether a calendar design ends above the real fund depends on the assumed costs: see the last column of each table.
- Calendar products whose end value falls below their twin's at some entry shift (fixed encoding): QQQP (Nasdaq-100) at shifts -10, -9, -8, -7, -6, -5, -4, -3, -2.
- After the entry every 2x path fell -59% to -65% and the 3x models -77% to -82% from a high; the dollar figures assume a holder kept the position through those falls.
- An entry three months early or late moves a 3-year result far more than the reset design does (results/from_bottoms.md, section D), so the exact low matters more than the design.

Data: TradingView (via local export), FRED. Modeled / synthetic series, not live funds. Not investment advice.
