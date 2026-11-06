# Step 2: model vs the live funds and the issuer's NAV figures (R2 re-fit)

**Inputs and conventions.**

```text
Inputs: 13 files; prices from <external>/library, rates from <external>/rates
  NASDAQ_SPYQ_daily.csv: 508 rows, 2024-10-01 to 2026-10-09, sha256 124564fb1a3b
  AMEX_SPY_daily.csv: 8498 rows, 1993-01-29 to 2026-11-02, sha256 643d6ef08b88
  SP_SPX_daily.csv: 19333 rows, 1950-01-03 to 2026-11-02, sha256 b146c9af89cc
  SP_SPXTR_daily.csv: 9787 rows, 1988-01-04 to 2026-11-03, sha256 edab5090825e
  NASDAQ_MQQQ_daily.csv: 542 rows, 2024-09-03 to 2026-10-29, sha256 b71324843b8a
  NASDAQ_QQQ_daily.csv: 6955 rows, 1999-03-10 to 2026-10-30, sha256 f096cd6c6b75
  NASDAQ_NDX_daily.csv: 10519 rows, 1985-01-31 to 2026-10-30, sha256 79d8e8688fa3
  NASDAQ_XNDX_daily.csv: 5019 rows, 2006-11-08 to 2026-10-30, sha256 d7dcc6dffa24
  NASDAQ_QQQP_daily.csv: 522 rows, 2024-10-01 to 2026-10-29, sha256 233444f2dcc7
  AMEX_SSO_daily.csv: 5103 rows, 2006-06-21 to 2026-10-02, sha256 0df3e43a82db
  AMEX_QLD_daily.csv: 5123 rows, 2006-06-21 to 2026-10-30, sha256 9e5453cb02e0
  OBFR.csv: 2683 rows, 2016-03-01 to 2026-11-03, sha256 bbef2a371e62
  DFF.csv: 26424 rows, 1954-07-01 to 2026-11-03, sha256 e84a934a5014
Reference tables (reference/): 5 files
  distributions.csv: 3 rows, 2024-12-23 to 2025-12-23, sha256 8b458ea8ed7c
  etf_distributions.csv: 20 rows, 2024-06-21 to 2026-09-21, sha256 bae169d11be1
  nav_anchors.csv: 23 rows, None to None, sha256 b1a6456897f7
  daily_etf_distributions.csv: 20 rows, 2026-09-23 to 2024-06-26, sha256 e830b4cf86be
  daily_etf_highlights.csv: 4 rows, None to None, sha256 f89a303f5fbf
Fee timeline (annual expense ratio, ACT/365; SPYQ / MQQQ / QQQP):
  inception to 2025-03-31: 1.30 / 1.31 / 1.30%  [FILED: N-CSR FY2025 financial highlights (MQQQ includes 0.01% excise tax); reference/nav_anchors.csv rows 10-12]
  2025-04-01 to 2025-09-30: 1.30 / 1.30 / 1.30%  [FILED: N-CSRS to 2025-09-30, expense ratio annualized; reference/nav_anchors.csv rows 19-21]
  2025-10-01 to 2026-03-31: 1.22 / 1.12 / 1.18%  [DERIVED from two filed figures: 2 x FY2026 realized ratio - first-half ratio, that is (12 x FY2026 - 6 x first half) / 6; fiscal year 2026 1.26 / 1.21 / 1.24% (reference/nav_anchors.csv rows 16-18), first half 1.30 / 1.30 / 1.30%]
  from 2026-04-01: 1.00 / 1.03 / 1.00%  [ASSUMED start date (the first document that shows the 1.00 / 1.03 / 1.00% is the 2026-07-31 prospectus)]
  sensitivity: the fiscal-year 2026 average 1.26 / 1.21 / 1.24% held from 2025-10-01 to 2026-07-31, then 1.00 / 1.03 / 1.00%.
Early-reset trigger: the ETF price close (AMEX:SPY / NASDAQ:QQQ), mode level, drop 35% from the fund's base; close-only here because the deepest in-period fall stays far above it (tables below).
Day counts: financing (OBFR and swap spread) ACT/360; expense ratio ACT/365.
Reset dates: last NYSE session of the week / month / quarter (calendar_letf/nyse.py, from 1970-01-01).
MODELED: a live fund of this design traded 2024-08-30 to 2025-02-28; no live fund exists today (applies to the liquidated-fund section).
```

Script `scripts/run_validate_live.py`. Data: TradingView exports via the local library (fund and ETF closes and lows, split-adjusted, no distributions); FRED OBFR to 2026-11-03 and DFF to 2026-11-03; fund payouts `reference/distributions.csv`; SPY / QQQ dividends `reference/etf_distributions.csv` (SECONDARY: vendor history, latest row cross-checked against a second vendor); NAV anchors `reference/nav_anchors.csv` (23 rows, each with its filing); swap terms `reference/nport_tradr_2026.json`.

**Provenance of the model inputs.**
- Fee timeline (SPYQ / MQQQ / QQQP): inception to 2025-03-31: N-CSR FY2025 (reference/nav_anchors.csv rows 10-12); 2025-04-01 to 2025-09-30: N-CSRS (reference/nav_anchors.csv rows 19-21); fiscal year 2026 realized ratio 1.26 / 1.21 / 1.24%: N-CSR EDGAR 0001398344-26-010562 R2 (reference/nav_anchors.csv rows 16-18); 2026 ratio 1.00 / 1.03 / 1.00%: prospectus 2026-07-31. Inception to 2025-03-31: 1.30 / 1.31 / 1.30% (FILED: N-CSR FY2025 financial highlights (MQQQ includes 0.01% excise tax)). 2025-04-01 to 2025-09-30: 1.30 / 1.30 / 1.30% (FILED: N-CSRS to 2025-09-30, expense ratio annualized). 2025-10-01 to 2026-03-31: 1.22 / 1.12 / 1.18% (DERIVED from two filed figures: 2 x FY2026 realized ratio - first-half ratio, that is (12 x FY2026 - 6 x first half) / 6; the N-CSR reports 1.26 / 1.21 / 1.24% for the whole fiscal year). From 2026-04-01: the prospectus 1.00 / 1.03 / 1.00% (ASSUMED start date (the first document that shows the 1.00 / 1.03 / 1.00% is the 2026-07-31 prospectus)). Sensitivity: the FY2026 average 1.26 / 1.21 / 1.24% held from 2025-10-01 to 2026-07-31, then the prospectus fee.
- Balance sheet, window 1 (inception to 2025-09-30): no ETF held directly (semi-annual report 2024-09-30: 100% cash, swaps 1.90-2.01x; N-PORT 2025-03-31: swaps 2.21x, cash 111%; N-PORT 2025-06-30: swaps 1.75x, cash 88%). Window 2 (2025-09-30 on): ETF held directly about 0.4 x NAV (N-PORT 2025-09-30: 39.6%, swaps 1.32x, cash 41%; N-CSRS holdings SPYQ 48 / 20 / 32; 40-62% in the 2026 snapshots). The switch date is taken as 2025-09-30, the first snapshot with a direct holding.
- BASE reading ('at a reset'): swaps s = 2 - d, cash k = 1 - d: 2 / 1 then 1.6 / 0.6 x NAV. This is the identity the kernel already assumes: it fixes the swap notional at each reset and lets it drift inside the period, so a period-end snapshot's notional / NAV (2.21x after a down quarter) must not be fed in again. SNAPSHOT reading (the N-PORT notionals as printed): 2.21 / 1.11 then 1.32 / 0.41, shown as the sensitivity. Note that at 2025-09-30, a reset date, printed notional 1.32 + direct 0.40 = 1.72 < 2: the swaps' unrealized appreciation carries the rest of the exposure, and whether the financing leg accrues on the printed notional or on the exposure is OPEN.
- Swap spread per turn: SPYQ 0.92%, MQQQ 0.99%, QQQP 0.93% (N-PORT 2026-06-30, notional-weighted 75/100 bp over OBFR, read from reference/nport_tradr_2026.json by validate.filed_spread); reference rate OBFR (lagged one row: the rate set on t-1 accrues over t-1 to t); financing legs ACT/360, fee ACT/365; underlying = the ETF's own total return (price + its dividends reinvested on ex-date, which is what the swaps receive); trigger on the ETF price close, level mode.
- Cash yield c (fraction of OBFR the fund's cash earns): FITTED per fund per window; prior 0.8 derived from the N-CSR income ratios (net investment income after waivers 2.38 / 2.39 / 2.27% plus expenses 1.30 / 1.31 / 1.30% on a 100%-cash balance sheet while OBFR averaged about 4.5%).
- Price vs NAV: N-CSR FY to 2025-03-31: market-price total returns -8.12 / -7.94 / -12.12% against NAV -8.08 / -7.90 / -12.04% (SPYQ / MQQQ / QQQP), so price and NAV differed by 0.04-0.08 pp over six to seven months. Fund PRICES stand in for NAVs in every fit; bid-ask noise inflates tracking error on thin funds.


## SPYQ  (inception 2024-09-30, first price bar 2024-10-01, data to 2026-10-09)

Fee timeline used: 2024-09-30: 1.30%, 2025-10-01: 1.22%, 2026-04-01: 1.00%. Fund payouts added back: {'2025-12-23': 0.2711}. ETF total return on its own dividends ends at 1.3882 vs 1.3887 on the index-ratio basis (-0.04% over the life). Deepest in-period fall of SPY since the last reset: -11.2% on the close (2025-04-08), -13.9% on the day's low (2025-04-07), against the -35% trigger: the early reset never came near, so the three early-reset modes give identical numbers and only level mode is shown.

| window | c, BASE (at-reset s, k) | rate turns s - k c | BASE gap at c = 0.8 | BASE gap at c = 1.0 | c, BASE, FY2026 fee to 2026-07-31 | c, SNAPSHOT (s, k as printed) | SNAPSHOT gap at c = 0.8 | v1 filed (1.5 turns, registry fee 1.00 / 1.03 / 1.00%) | v1 fixed 2.6% | v1 rate 1.4% + 1.3 turns | DFF - OBFR (bp) | gap with DFF | ETF TR own - index basis (pp) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1: 2024-09-30 to 2025-09-30 | 0.878 | 1.122 | -0.42 | +0.66 | 0.878 | 1.020 | -1.32 | +1.61 | +0.10 | -0.05 | +0.0 | +0.00 | -0.01 |
| 2: 2025-09-30 to 2026-10-09 | 0.653 | 1.208 | +0.40 | +0.95 | 0.700 | 0.104 | +1.31 | +1.21 | -0.30 | -0.19 | +0.2 | -0.00 | -0.04 |
| whole life (c per window) | - | 0.878 / 0.653 per window | - | - | - | - | - | +1.41 | -0.11 | -0.13 | +0.1 | -0.00 | -0.06 |

Window 1's cash yield at the filed spread extremes (window 1's own counterparty mix is not in the extract): c = 0.802 at 0.75% and 0.915 at 1.00%, against 0.878 at the 2026-06-30 mix (0.92%).


Gaps are model CAGR minus fund CAGR in pp/yr over the window (fund prices + payouts; the fit zeroes the gap by construction, so the fitted c has no gap column). Whole life with the BASE structural model: TE 3.28%/yr, daily correlation 0.995, 508 rows; price vs NAV bound from the N-CSR: 0.04-0.08 pp over the first six to seven months. The last column is the ETF total return on its own dividends minus the index-ratio construction over the window (return units): the two agree over whole quarters.

| anchor window | source | status | anchor NAV return | fund price + payouts | 2 x ETF TR | BASE, fitted c | gap pp | BASE, c = 0.8 | gap pp | v1 fixed 2.6% | gap pp | v1 rate 1.3 turns | gap pp |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2024-09-30 to 2025-03-31 | N-CSR fiscal year ended 2025-03-31 | PRIMARY | -8.08% | n/a (no price bar on the start date) | -3.77% | -8.00% | +0.08 | -8.17% | -0.09 | -7.96% | +0.12 | -8.03% | +0.05 |
| 2024-12-31 to 2025-12-31 | prospectus 2026-07-31 p.29 calendar-year 2025 NAV return | PRIMARY | 26.23% | 26.22% | 35.43% | 26.31% | +0.08 | 26.12% | -0.11 | 26.34% | +0.11 | 26.27% | +0.04 |
| 2025-03-31 to 2026-03-31 | N-CSR fiscal year ended 2026-03-31 | PRIMARY | 26.49% | 26.48% | 35.18% | 26.36% | -0.13 | 26.39% | -0.10 | 26.31% | -0.18 | 26.31% | -0.18 |

Anchor NAV returns are the issuer's own figures (filing in the source column); the model is run from the inception close, so the inception-dated anchors need no fund price at all. The fitted-c model used the whole fund price path of each window, so anchors inside a window test how evenly the cost is spread and how close price is to NAV, not the level (which the fit sets); the c = 0.8 column is the prior with nothing fitted. '2 x ETF TR' is the gross promise before any cost.

Fund vs ETF price, 7 full quarters: regression slope **2.015** (the delivered multiple), intercept **-1.33 pp per period** (the cost), R² 1.000. Ratio fund/ETF where |ETF| >= 3.0%: median 1.94, range 1.79 to 2.33. Fund minus 2x ETF: mean -1.27 pp per period.

Fund vs ETF total_return, 7 full quarters: regression slope **2.012** (the delivered multiple), intercept **-1.90 pp per period** (the cost), R² 1.000. Ratio fund/ETF where |ETF| >= 3.0%: median 1.90, range 1.72 to 2.49. Fund minus 2x ETF: mean -1.85 pp per period.


## MQQQ  (inception 2024-08-30, first price bar 2024-09-03, data to 2026-10-09)

Fee timeline used: 2024-08-30: 1.31%, 2025-04-01: 1.30%, 2025-10-01: 1.12%, 2026-04-01: 1.03%. Fund payouts added back: {'2024-12-23': 0.17049999999999998, '2025-12-23': 3.65886}. ETF total return on its own dividends ends at 1.5954 vs 1.5946 on the index-ratio basis (+0.05% over the life). Deepest in-period fall of QQQ since the last reset: -11.3% on the close (2025-04-08), -14.2% on the day's low (2025-04-07), against the -35% trigger: the early reset never came near, so the three early-reset modes give identical numbers and only level mode is shown.

| window | c, BASE (at-reset s, k) | rate turns s - k c | BASE gap at c = 0.8 | BASE gap at c = 1.0 | c, BASE, FY2026 fee to 2026-07-31 | c, SNAPSHOT (s, k as printed) | SNAPSHOT gap at c = 0.8 | v1 filed (1.5 turns, registry fee 1.00 / 1.03 / 1.00%) | v1 fixed 2.6% | v1 rate 1.4% + 1.3 turns | DFF - OBFR (bp) | gap with DFF | ETF TR own - index basis (pp) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1: 2024-08-30 to 2025-09-30 | 0.922 | 1.078 | -0.80 | +0.51 | 0.922 | 1.062 | -1.90 | +1.66 | +0.01 | -0.19 | +0.0 | +0.00 | +0.07 |
| 2: 2025-09-30 to 2026-10-09 | 0.521 | 1.287 | +0.86 | +1.49 | 0.566 | -0.103 | +1.92 | +1.69 | +0.14 | +0.26 | +0.2 | -0.00 | -0.00 |
| whole life (c per window) | - | 0.922 / 0.521 per window | - | - | - | - | - | +1.67 | +0.07 | +0.04 | +0.1 | -0.00 | +0.08 |

Window 1's cash yield at the filed spread extremes (window 1's own counterparty mix is not in the extract): c = 0.813 at 0.75% and 0.925 at 1.00%, against 0.922 at the 2026-06-30 mix (0.99%).


Gaps are model CAGR minus fund CAGR in pp/yr over the window (fund prices + payouts; the fit zeroes the gap by construction, so the fitted c has no gap column). Whole life with the BASE structural model: TE 3.05%/yr, daily correlation 0.998, 528 rows; price vs NAV bound from the N-CSR: 0.04-0.08 pp over the first six to seven months. The last column is the ETF total return on its own dividends minus the index-ratio construction over the window (return units): the two agree over whole quarters.

| anchor window | source | status | anchor NAV return | fund price + payouts | 2 x ETF TR | BASE, fitted c | gap pp | BASE, c = 0.8 | gap pp | v1 fixed 2.6% | gap pp | v1 rate 1.3 turns | gap pp |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2024-08-30 to 2024-09-30 | semi-annual report period ended 2024-09-30 p.48 | PRIMARY | 4.56% | n/a (no price bar on the start date) | 5.24% | 4.48% | -0.08 | 4.43% | -0.13 | 4.49% | -0.07 | 4.46% | -0.10 |
| 2024-08-30 to 2025-03-31 | N-CSR fiscal year ended 2025-03-31 financial highlights | PRIMARY | -7.90% | n/a (no price bar on the start date) | -2.21% | -7.94% | -0.04 | -8.25% | -0.35 | -7.93% | -0.03 | -8.02% | -0.12 |
| 2024-12-31 to 2025-12-31 | prospectus 2026-07-31 p.44 calendar-year 2025 NAV return | PRIMARY | 31.50% | 31.65% | 41.53% | 31.63% | +0.13 | 31.33% | -0.17 | 31.69% | +0.19 | 31.61% | +0.11 |
| 2025-03-31 to 2026-03-31 | N-CSR fiscal year ended 2026-03-31 | PRIMARY | 39.19% | 39.33% | 47.36% | 38.97% | -0.22 | 39.07% | -0.12 | 39.08% | -0.11 | 39.07% | -0.12 |

Anchor NAV returns are the issuer's own figures (filing in the source column); the model is run from the inception close, so the inception-dated anchors need no fund price at all. The fitted-c model used the whole fund price path of each window, so anchors inside a window test how evenly the cost is spread and how close price is to NAV, not the level (which the fit sets); the c = 0.8 column is the prior with nothing fitted. '2 x ETF TR' is the gross promise before any cost.

Fund vs ETF price, 24 full months: regression slope **1.993** (the delivered multiple), intercept **-0.55 pp per period** (the cost), R² 1.000. Ratio fund/ETF where |ETF| >= 1.0%: median 1.92, range 1.33 to 2.51. Fund minus 2x ETF: mean -0.56 pp per period.

Fund vs ETF total_return, 24 full months: regression slope **1.998** (the delivered multiple), intercept **-0.64 pp per period** (the cost), R² 1.000. Ratio fund/ETF where |ETF| >= 1.0%: median 1.92, range 1.33 to 2.51. Fund minus 2x ETF: mean -0.65 pp per period.


## QQQP  (inception 2024-09-30, first price bar 2024-10-01, data to 2026-10-09)

Fee timeline used: 2024-09-30: 1.30%, 2025-10-01: 1.18%, 2026-04-01: 1.00%. Fund payouts added back: none. ETF total return on its own dividends ends at 1.5547 vs 1.5550 on the index-ratio basis (-0.02% over the life). Deepest in-period fall of QQQ since the last reset: -11.3% on the close (2025-04-08), -14.2% on the day's low (2025-04-07), against the -35% trigger: the early reset never came near, so the three early-reset modes give identical numbers and only level mode is shown.

| window | c, BASE (at-reset s, k) | rate turns s - k c | BASE gap at c = 0.8 | BASE gap at c = 1.0 | c, BASE, FY2026 fee to 2026-07-31 | c, SNAPSHOT (s, k as printed) | SNAPSHOT gap at c = 0.8 | v1 filed (1.5 turns, registry fee 1.00 / 1.03 / 1.00%) | v1 fixed 2.6% | v1 rate 1.4% + 1.3 turns | DFF - OBFR (bp) | gap with DFF | ETF TR own - index basis (pp) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1: 2024-09-30 to 2025-09-30 | 0.924 | 1.076 | -0.73 | +0.45 | 0.924 | 1.062 | -1.70 | +1.49 | -0.13 | -0.29 | +0.0 | -0.00 | -0.02 |
| 2: 2025-09-30 to 2026-10-09 | 0.727 | 1.164 | +0.22 | +0.81 | 0.775 | 0.210 | +1.20 | +1.07 | -0.54 | -0.43 | +0.2 | -0.00 | -0.00 |
| whole life (c per window) | - | 0.924 / 0.727 per window | - | - | - | - | - | +1.27 | -0.34 | -0.36 | +0.1 | -0.00 | -0.03 |

Window 1's cash yield at the filed spread extremes (window 1's own counterparty mix is not in the extract): c = 0.842 at 0.75% and 0.956 at 1.00%, against 0.924 at the 2026-06-30 mix (0.93%).


Gaps are model CAGR minus fund CAGR in pp/yr over the window (fund prices + payouts; the fit zeroes the gap by construction, so the fitted c has no gap column). Whole life with the BASE structural model: TE 4.27%/yr, daily correlation 0.995, 508 rows; price vs NAV bound from the N-CSR: 0.04-0.08 pp over the first six to seven months. The last column is the ETF total return on its own dividends minus the index-ratio construction over the window (return units): the two agree over whole quarters.

| anchor window | source | status | anchor NAV return | fund price + payouts | 2 x ETF TR | BASE, fitted c | gap pp | BASE, c = 0.8 | gap pp | v1 fixed 2.6% | gap pp | v1 rate 1.3 turns | gap pp |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2024-09-30 to 2025-03-31 | N-CSR fiscal year ended 2025-03-31 financial highlights | PRIMARY | -12.04% | n/a (no price bar on the start date) | -7.26% | -11.92% | +0.12 | -12.18% | -0.14 | -11.96% | +0.08 | -12.03% | +0.01 |
| 2024-12-31 to 2025-12-31 | prospectus 2026-07-31 p.73 calendar-year 2025 NAV return | PRIMARY | 30.24% | 30.21% | 41.53% | 30.44% | +0.20 | 30.00% | -0.24 | 30.25% | +0.01 | 30.17% | -0.07 |
| 2025-03-31 to 2026-03-31 | N-CSR fiscal year ended 2026-03-31 | PRIMARY | 37.94% | 38.17% | 47.36% | 37.88% | -0.06 | 37.70% | -0.24 | 37.59% | -0.35 | 37.59% | -0.35 |

Anchor NAV returns are the issuer's own figures (filing in the source column); the model is run from the inception close, so the inception-dated anchors need no fund price at all. The fitted-c model used the whole fund price path of each window, so anchors inside a window test how evenly the cost is spread and how close price is to NAV, not the level (which the fit sets); the c = 0.8 column is the prior with nothing fitted. '2 x ETF TR' is the gross promise before any cost.

Fund vs ETF price, 7 full quarters: regression slope **2.005** (the delivered multiple), intercept **-1.59 pp per period** (the cost), R² 1.000. Ratio fund/ETF where |ETF| >= 3.0%: median 1.95, range 1.78 to 2.22. Fund minus 2x ETF: mean -1.56 pp per period.

Fund vs ETF total_return, 7 full quarters: regression slope **2.004** (the delivered multiple), intercept **-1.84 pp per period** (the cost), R² 1.000. Ratio fund/ETF where |ETF| >= 3.0%: median 1.94, range 1.76 to 2.25. Fund minus 2x ETF: mean -1.81 pp per period.


## Window 2: the fitted cash yield c depends on the assumed direct holding d

Window 2 starts 2025-09-30. The filings put the direct ETF holding at 40-62% of NAV, so each fund is refitted at d = 0.3 / 0.4 / 0.5 / 0.6 (swaps s = 2 - d, cash k = 1 - d; the fit sets the CAGR gap to zero in every column). **c is a residual conditional on the assumed direct holding d; the invariant is the all-in financing.** The all-in financing per NAV a year is (s - k c) x the day-weighted mean lagged OBFR of the window + s x the filed spread; it does not move with d, because each fit must reproduce the same fund growth.

| fund | c at d = 0.3 | c at d = 0.4 | c at d = 0.5 | c at d = 0.6 | all-in financing, d = 0.3 | all-in financing, d = 0.4 | all-in financing, d = 0.5 | all-in financing, d = 0.6 | mean lagged OBFR (day-weighted) |
|---|---|---|---|---|---|---|---|---|---|
| SPYQ | 0.738 | 0.653 | 0.535 | 0.356 | 5.95% | 5.95% | 5.95% | 5.95% | 3.71% |
| MQQQ | 0.628 | 0.521 | 0.372 | 0.148 | 6.37% | 6.37% | 6.37% | 6.37% | 3.71% |
| QQQP | 0.802 | 0.727 | 0.623 | 0.466 | 5.81% | 5.81% | 5.81% | 5.81% | 3.71% |

## Window 1: which input closes how much of the v1 CAGR gap

Start: the v1 filed structure (fee 1.00 / 1.03 / 1.00% for SPYQ / MQQQ / QQQP; 1.5 swap turns; 1.0 rate turn). Each step changes one input of the step before and shows how many percentage points a year of the CAGR gap (model minus fund) it closes: first the fee to the filed ratio (1.30 / 1.31 / 1.30% to 2025-03-31, then 1.30 / 1.30 / 1.30% to 2025-09-30), then the swap turns to 2.0, then the rate turns to the fitted s - k c. The pieces add up to the v1 gap, because the last model is the fitted one (gap zero).

| fund | v1 filed gap (pp a year) | fee step | spread-turns step | rate-turns step | sum of steps | fitted rate turns |
|---|---|---|---|---|---|---|
| SPYQ | +1.611 | +0.380 | +0.568 | +0.663 | +1.611 | 1.122 |
| MQQQ | +1.655 | +0.410 | +0.735 | +0.510 | +1.655 | 1.078 |
| QQQP | +1.488 | +0.417 | +0.624 | +0.447 | +1.488 | 1.076 |


## Liquidated calendar funds, one month 2024-08-30 to 2024-09-30 (out of sample)

SPYM (2x SPY monthly), SPYB (2x SPY weekly) and QQQW (2x QQQ weekly) launched 2024-08-30 and were liquidated 2025-02-28; their only published NAV figures are the one-month total returns in the semi-annual report to 2024-09-30 (PRIMARY). The registry carries these designs as MODELED (HYP_SPX_M, HYP_SPX_W, HYP_NDX_W). Each is modeled here from the 2024-08-30 close at the live funds' window-1 terms: fee 1.30% (their filed ratio), BASE balance sheet (swaps 2 x NAV at the filed spread of the live fund on the same ETF, cash 1 x NAV) earning c = 0.908 x OBFR (the mean of the three live funds' window-1 fits; c = 0.8 and 1 shown too). Nothing was fitted on these funds. The semi-annual report's swap notionals at 2024-09-30 were SPYM 1.97x, SPYB 1.96x, QQQW 1.98x. The last model column repeats the fitted-c model on the v1 ETF total-return construction (index-ratio basis), which mistimes the ETF's September ex-dividend inside this month. Liquidation values (SECONDARY) are listed, not used.

| fund | design | anchor NAV return | market return | 2 x ETF TR | model c fitted | gap pp | model c = 0.8 | gap pp | model c = 1.0 | gap pp | v1 fixed 2.6% (registry fee 1.00%) | gap pp | fitted c on the index-ratio ETF basis | gap pp | resets in the month |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SPYM | HYP_SPX_M (SPX monthly) | 3.48% | 3.56% | 4.20% | 3.45% | -0.03 | 3.40% | -0.08 | 3.49% | +0.01 | 3.45% | -0.03 | 3.04% | -0.44 | 0 |
| SPYB | HYP_SPX_W (SPX weekly) | 3.12% | 3.32% | 4.20% | 3.10% | -0.02 | 3.05% | -0.07 | 3.14% | +0.02 | 3.10% | -0.02 | 2.69% | -0.43 | 4 |
| QQQW | HYP_NDX_W (NDX weekly) | 3.84% | 3.88% | 5.24% | 3.76% | -0.08 | 3.71% | -0.13 | 3.80% | -0.04 | 3.77% | -0.07 | 3.61% | -0.23 | 4 |

SECONDARY liquidation values (brokerage corporate-actions record, not a filing; shown, not used): QQQW 2025-02-28 30.2606 per share from 25.00 (+21.04%); SPYM 2025-02-28 28.3384 per share from 25.00 (+13.35%); TLTQ 2025-02-28 20.9744 per share from 25.00 (-16.10%).

Out of scope (underlying not in this kit): SOXM, SOXW (SOXX), NVDW (NVDA, 1.75x), TSLW (TSLA, 1.5x), TLTM, TLTQ (TLT); their one-month anchors are in `reference/nav_anchors.csv`.


## Real calendar fund vs real daily fund, inception to 2026-09-30 (BACKLOG B19)

The real 2x DAILY fund on the same index: SSO (S&P 500) and QLD (Nasdaq-100), on market prices plus payouts reinvested on the ex-date close, like the calendar funds. Hard test first: each daily fund's total return rebuilt this way against its own N-CSR market-price total return per fiscal year (within 0.02 points), and its payouts against the filed per-share total (within 0.005): **PASS**.

| daily fund | fiscal year to | rebuilt % | N-CSR market % | N-CSR NAV % | payouts | filed | passed |
|---|---|---|---|---|---|---|---|
| SSO | 2025-05-31 | 15.68 | 15.68 | 16.03 | 0.38798 | 0.39 | True |
| SSO | 2026-05-31 | 57.17 | 57.17 | 56.80 | 0.42632 | 0.43 | True |
| QLD | 2025-05-31 | 17.80 | 17.80 | 18.10 | 0.12223 | 0.12 | True |
| QLD | 2026-05-31 | 88.39 | 88.39 | 88.15 | 0.11820 | 0.12 | True |

Fees: the calendar funds' fee timeline above; the daily funds' the N-CSR net expense ratio of each fiscal year (to May 31); the FY2026 ratio held after 2026-05-31 (ASSUMED: no later filing yet). The model gap runs both kernels at equal costs (zero fee, zero spread, (L - 1) x DFF) on the ETF's own total return; the calendar kernel keeps the fund's -35% trigger. Gaps are CAGR differences in pp a year; 'rest' = fee-adjusted gap minus model gap: everything else (cash yield, swap terms, price vs NAV at the ends).

| calendar | daily | reset | window | years | CAGR calendar % | CAGR daily % | gap | log gap | fee difference | gap fee-adjusted | model gap (equal costs) | rest | residual cost calendar / daily, % of NAV a year | cost drag calendar / daily, pp a year | interval |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SPYQ | AMEX:SSO | quarterly | 2024-10-01 to 2026-09-30 | 2.00 | +25.38 | +26.25 | -0.87 | -0.69 | +0.35 | -0.52 | +1.27 | -1.79 | +2.17 / +0.75 | +4.19 / +2.04 | two years: too few independent years for an interval (too noisy to test) |
| MQQQ | AMEX:QLD | monthly | 2024-09-03 to 2026-09-30 | 2.07 | +43.11 | +43.70 | -0.59 | -0.41 | +0.28 | -0.30 | +2.25 | -2.55 | +2.36 / +0.66 | +5.13 / +2.29 | two years: too few independent years for an interval (too noisy to test) |
| QQQP | AMEX:QLD | quarterly | 2024-10-01 to 2026-09-30 | 2.00 | +38.45 | +40.18 | -1.73 | -1.24 | +0.28 | -1.45 | +0.39 | -1.84 | +2.00 / +0.65 | +4.33 / +2.21 | two years: too few independent years for an interval (too noisy to test) |

Residual cost: the spread per NAV a year, on top of (L - 1) x DFF and the filed fee, that makes each fund's own kernel grow as the fund did on the shared dates (validate.fit_spread), on the ETF's own total return for both funds (the daily funds track the index itself, so theirs also absorbs the ETF's fee). It is a residual: cash yield, swap terms and price vs NAV, not a filed term. Cost drag: the CAGR each fund's kernel loses to its fee plus its residual cost, against the same kernel at zero cost. Because each fit reproduces its fund, the gap splits exactly: gap = model gap - calendar drag + daily drag (to the fit's tolerance).

