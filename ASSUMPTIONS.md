# Assumptions register

Every number the engine uses, with its status and source. Statuses: **VERIFIED** (document, date and number
written down), **MEASURED** (computed from verified data by code in this repo). **ASSUMED** (a choice; run the
stated sensitivity), **OPEN** (unknown; the code refuses to run without an explicit value).
Started 2026-10-12. Each build step adds its rows; nothing here is a result.

## 1. Live products (Tradr prospectus dated 31 July 2026, read 2026-10-12)

| Fund | Objective | Reset | Early reset | Total annual operating expenses | Inception | Status |
|---|---|---|---|---|---|---|
| NASDAQ:SPYQ | 2x the calendar-quarter return of SPY (the ETF) | quarterly | if SPY falls 35% within the quarter | 1.00% (management 0.95% + other 0.02% + interest/excise 0.02% + acquired fund fees 0.03%), p.17 | 2024-09-30 | VERIFIED |
| NASDAQ:MQQQ | 2x the calendar-month return of QQQ | monthly | if QQQ falls 35% within the month | 1.03% (0.95% + acquired fund fees 0.08%), p.31 | 2024-08-30 | VERIFIED |
| NASDAQ:QQQP | 2x the calendar-quarter return of QQQ | quarterly | if QQQ falls 35% within the quarter | 1.00% (0.95% + 0.05%), p.60 | 2024-09-30 | VERIFIED |

Prospectus definitions used by the engine (pp. 1, 19, 33, 62):
- A calendar month runs from the last NYSE business day's close in one month to the last business day's close in
  the next. A quarter runs the same way. Business day = any day the NYSE is open.
- The fund rebalances its swaps at each period end and otherwise does not rebalance: exposure floats.
- Early reset: if the underlying moves 35% against the fund within a period, the advisor resets the leverage
  "as soon as possible" intraday. If the move hits the trigger in the final 30 minutes, the reset can possibly come
  on the next trading day. The stub after an early reset counts as a new period.
- The swap cost ("embedded cost of the swap") is NOT in the expense table (footnote on each fee table).
- 2025 calendar-year NAV returns, for validation anchors (pp. 29, 44, 73): SPYQ 26.23%, MQQQ 31.50%,
  QQQP 30.24%. MQQQ paid distributions in 2025 (after-tax 30.47%); SPYQ and QQQP did not.

**The full product set (R2 step 2, filings read 2026-10-24).** Tradr ran twelve calendar-reset funds. The three above
are the survivors. The other nine liquidated on 2025-02-28 (last trade 2025-02-21; all cash from the 2025-02-14
close). So the weekly and SPY-monthly designs this repo models (kind `MODELED`, formerly `HYPOTHETICAL`) traded for
six months. Step 2 uses their one published month (semi-annual report to 2024-09-30) as an out-of-sample check.

Trust: Investment Managers Series Trust II (EDGAR CIK 1587982); adviser AXS Investments LLC. Sources:
- the semi-annual financial report for the period ended 2024-09-30: note 1 (commencement dates and leverage) and the
  financial highlights;
- 497 supplements of 2025-01-27 (SPYB, QQQW, SOXW, TLTQ, TSLW) and 2025-01-31 (NVDW, SPYM, SOXM, TLTM);
- the issuer page, read 2026-10-21: the all-cash date and the 1-for-5 reverse split of MQQQ, QQQP, SPYQ (effective
  2025-06-03). MQQQ and QQQP took the name "Innovation 100" on 2025-05-16.

| Ticker | Name (at launch) | Underlying | Leverage | Reset | Launch | Status | Source |
|---|---|---|---|---|---|---|---|
| SPYM | Tradr 2X Long SPY Monthly ETF | SPY | 2.0 | monthly | 2024-08-30 | liquidated 2025-02-28 | semi-annual 2024-09-30 p.47; 497 2025-01-31 |
| MQQQ | Tradr 2X Long Triple Q Monthly ETF | QQQ | 2.0 | monthly | 2024-08-30 | live | semi-annual 2024-09-30 p.48; prospectus 2026-07-31 |
| SOXM | Tradr 2X Long SOXX Monthly ETF | SOXX | 2.0 | monthly | 2024-08-30 | liquidated 2025-02-28 | semi-annual p.49; 497 2025-01-31 |
| SPYB | Tradr 2X Long SPY Weekly ETF | SPY | 2.0 | weekly | 2024-08-30 | liquidated 2025-02-28 | semi-annual p.50; 497 2025-01-27 |
| QQQW | Tradr 2X Long Triple Q Weekly ETF | QQQ | 2.0 | weekly | 2024-08-30 | liquidated 2025-02-28 | semi-annual p.51; 497 2025-01-27 |
| SOXW | Tradr 2X Long SOXX Weekly ETF | SOXX | 2.0 | weekly | 2024-08-30 | liquidated 2025-02-28 | semi-annual p.52; 497 2025-01-27 |
| NVDW | Tradr 1.75X Long NVDA Weekly ETF | NVDA | 1.75 | weekly | 2024-08-30 | liquidated 2025-02-28 | semi-annual p.53; 497 2025-01-31 |
| TSLW | Tradr 1.5X Long TSLA Weekly ETF | TSLA | 1.5 | weekly | 2024-08-30 | liquidated 2025-02-28 | semi-annual p.54; 497 2025-01-27 |
| SPYQ | Tradr 2X Long SPY Quarterly ETF | SPY | 2.0 | quarterly | 2024-09-30 | live | semi-annual note 1; prospectus 2026-07-31 |
| QQQP | Tradr 2X Long Triple Q Quarterly ETF | QQQ | 2.0 | quarterly | 2024-09-30 | live | semi-annual note 1; prospectus 2026-07-31 |
| TLTM | Tradr 2X Long TLT Monthly ETF | TLT | 2.0 | monthly | 2024-09-30 | liquidated 2025-02-28 | semi-annual note 1; 497 2025-01-31 |
| TLTQ | Tradr 1.75X Long TLT Quarterly ETF | TLT | 1.75 | quarterly | 2024-09-30 | liquidated 2025-02-28 | semi-annual note 1; 497 2025-01-27 |

Only the SPY and QQQ designs are in this kit (underlyings SPX / NDX). The tickers SPYM and SPYB now belong to other
products, and QQQW is not a valid symbol. So the price library has no daily prices for the liquidated funds. Their
published NAV figures are in `reference/nav_anchors.csv` with status PRIMARY (filings) or SECONDARY. The SECONDARY
rows come from a brokerage corporate-actions record of the liquidation values: QQQW 30.2606, SPYM 28.3384, TLTQ
20.9744 per share from 25.00, paid 2025-03-04. This project has not yet read these values in a filing, so the file
shows them and never uses them as a check.

Distributions (library prices exclude them; step 2 adds them back before the fit). File: `reference/distributions.csv`,
retrieved 2026-10-12 from the TradingView MCP dividends calendar, cross-checked with stockanalysis.com and the
prospectus after-tax rows. Status SECONDARY (aggregator and vendor data, not the issuer's own schedule, which
tradretfs.com does not publish on the fund pages).
| Fund | Ex-date | Amount / share | Note |
|---|---|---|---|
| MQQQ | 2025-12-23 | 3.65886 | short-term capital gain, ~1.5% of price |
| MQQQ | 2024-12-23 | 0.0341 | pre reverse split; adjusted amount OPEN (0.0341 or 0.1705); immaterial |
| QQQP | none | 0 | agrees with prospectus (after-tax = pre-tax) |
| SPYQ | 2025-12-23 | 0.2711 | ~0.14% of price |

## 2. Costs in the model

| Item | Value | Status | Source / sensitivity |
|---|---|---|---|
| Expense ratio, live funds | as table above | VERIFIED | prospectus 2026-07-31 |
| Expense ratio, modeled and twin series | 1.00% | ASSUMED | same as the live funds today, so the reset rule is the only difference. The liquidated funds of the modeled designs paid the 1.30% cap while they traded. The one-month out-of-sample check in step 2 uses 1.30% |
| Reference rate | effective fed funds (FRED DFF), known the day before; files refreshed 2026-10-12 to 2026-10-08 | VERIFIED data, rule from letf kit | before 1954-07-01: monthly TB3MS (prior month) as a proxy, flagged. The funds' filed reference is OBFR (section 6). FRED `OBFR.csv` from 2016-03-01 is on disk for the step-2 fit. DFF stays the long-history proxy (a few bp above OBFR) |
| Borrowed turns paying the rate | L - 1 = 1 | RULE | a 2x fund borrows one NAV |
| Swap spread (registry default; NOT used by any published table) | `costs.SPREAD_BASE` 1.1% per turn on 2 turns (2.2%/yr of NAV). It is the product registry's default and the convention under which an earlier private kit fitted its spreads. Code ties the turns to L | ASSUMED, superseded in every result. The passive, strategy and bottoms studies pass one of the two historical encodings (row below). The validation runs use the filed spread per fund. So no published number carries 1.1% | origin: an earlier private kit's calibration 2026-10-11 (MQQQ 1.43%, QQQP 0.77% on price return; registry sensitivity 0.8% / 1.4%, which no script runs). Filings (section 6): 0.75-1.00% over OBFR, notional-weighted 0.92-0.99%, on the swap turns of the balance-sheet row below |
| Historical cost encodings (passive study, strategies, bottoms; `study.ENCODINGS`) | two encodings of the 2024-26 residual, carried into history side by side. "fixed": a fixed 2.6% of NAV a year on 1.0 rate turn replaces the filed spread. "rate": the filed 1.4% of NAV plus 1.3 turns of the reference rate. Each runs at the product's steady-state fee (1.00 / 1.03%). Sensitivities: fixed 1.4% and 3.5%; rate 1.0 and 1.5 turns; zero costs and rate-only as definitions | ASSUMED (fitted on 2024-26 price data, FINDINGS F3 / F5) | the two agree in a single rate regime and part when rates move. On the S&P designs, fixed minus rate CAGR is +1.21 to +1.28 pp/yr in 1966-82 (high rates: the fixed charge is the smaller). It is -1.45 to -1.39 in 2009-15 (rates near zero: the rate charge is the smaller; Nasdaq-100 designs -1.6 to -1.5). `encoding_gap` in the passive study's JSON holds these values (R2 step 12e; it replaces a typed "1.4-1.7"). So every historical table shows both. The reset gap moves by at most 0.15 pp between them. The structural reading of 2024-26 (section 6) is not a third historical encoding. The reason: no measurement of its balance-sheet inputs exists before 2024 |
| Buy-once margin benchmark (reset "never"; `kernel.margin_position_nav`; FINDINGS F11) | borrows (L-1) x NAV0 at the encoding's rate turns times the reference rate. That is 1.0 x DFF under the fixed encoding and 1.3 x DFF under the rate encoding, as the funds pay. The loan compounds daily (interest capitalized each row on ACT/360). The benchmark borrows to pay the fund's swap spread (spread per NAV x NAV0) and the fund's fee (on yesterday's equity, 365-day year). So these costs compound from the next row. The spread accrues on the OPENING balance NAV0, not on the growing loan. Equity = L x NAV0 x u_t/u_0 - loan. The benchmark ends (equity 0, stays 0) when the loan overtakes the position. No margin call | CONVENTION (R2 step 1, 2026-10-24): "the benchmark borrows the fund's costs" | Sensitivities: a spread charged on the growing loan takes a further 0.1-0.2 pp/yr off the benchmark (R2 audit). The v1 simple-interest rule flattered it by 0.1-0.2 pp/yr at the median and up to 0.8 in high-rate windows. A 30% maintenance call (v1 audit scratch) triggers in 39% of S&P 10-year windows; the base benchmark does not include it. A retail margin rate (far above the reference rate) is outside the benchmark by design |
| Accrual (day count) | financing legs (reference rate and spread): calendar days / 360 (ACT/360); expense ratio: calendar days / 365; weekends accrue | VERIFIED | standard money-market convention for US overnight-rate swap legs (OBFR, fed funds); dealer floating-rate-option disclosure read 2026-10-22 in the 2x Ledger review. In force from R2 step 1 (2026-10-24); before that both legs used calendar days / 365 (the letf.synth rule), which `fin_day_count=365` restores for the local cross-checks |
| Expense ratio timeline, live funds (validation runs) | net 1.30% from inception to 2025-09-30. MQQQ: 1.31% with excise tax to 2025-03-31 and 1.30% after. Both are VERIFIED: N-CSR FY2025 financial highlights 1.30 / 1.31 / 1.30% annualized; N-CSRS to 2025-09-30 1.30% annualized for all three. Fiscal 2026 as a whole: 1.26% / 1.21% / 1.24% (VERIFIED: N-CSR FY2026 shareholder report, "costs paid as a percentage of a $10,000 investment", EDGAR 0001398344-26-010562 R2). So the realized ratio fell below the cap in the second half of FY2026. The implied average of that half is (12 x FY - 6 x first half) / 6 = 1.22% / 1.12% / 1.18%. Status of this figure: DERIVED from the two filed figures; exact only if the two halves had equal average assets. For a half-year asset ratio between 0.67 and 1.5, the true figure is within 0.05 pp, that is 0.012 on c. Then 1.00% / 1.03% / 1.00% (prospectus 2026-07-31, management fee 0.95%). Start date ASSUMED 2026-04-01 (the first document that shows it is dated 2026-07-31) | VERIFIED to 2026-03-31; DERIVED inside FY2026; switch date ASSUMED | Prospectus 2025-07-31 (497 filed 2025-08-05): expense cap 1.30% through 2026-08-31, management fee 1.00%, gross expenses 3.73% (SPYQ) / 2.68% (MQQQ). So the cap bound in that fee table. Prospectus 2026-07-31: total expenses 1.00% / 1.03% / 1.00%, management fee 0.95%. The kernels take one fee per row (`fee=` a float or a step Series on the index). History and the passive study keep the steady-state figure. **Used in the validation fit (R2 step 8, 2026-10-24, `scripts/run_validate_live.py`):** the script reads the filed ratios from `reference/nav_anchors.csv` (the FY2025, 2025-09-30 and FY2026 rows). It refuses a missing, duplicated or non-PRIMARY row. Code derives the second-half figure. Segments: filed to 2025-09-30 (MQQQ steps 1.31% -> 1.30% on 2025-04-01), derived 1.22 / 1.12 / 1.18% to 2026-03-31, prospectus 1.00 / 1.03 / 1.00% from 2026-04-01. Sensitivity: the FY2026 average held to 2026-07-31, which moves the fitted window-2 cash yield by +0.05 |
| Balance-sheet structure, live funds (validation runs; `validate.Structure`) | Window 1, inception to 2025-09-30: no ETF held directly, swaps s = 2.0 x NAV, cash k = 1.0 x NAV. Window 2, 2025-09-30 on: ETF held directly d = 0.4 x NAV, swaps s = 2 - d = 1.6, cash k = 1 - d = 0.6 (the "at a reset" identity). Net financing per NAV = (s - k c) x OBFR + s x spread. Here c = the fraction of OBFR the cash earns | VERIFIED structure (N-PORT quarters, section 6); d ASSUMED 0 / 0.4. FITTED c: a residual conditional on d (section 6: the d-sensitivity and the invariant all-in financing) | Sensitivity: the N-PORT period-end values as printed (s 2.21 / 1.32, k 1.11 / 0.41). They include the drift at the snapshot date, which the kernel already models. With these notionals the fitted c is 1.02-1.06 in window 1 (cash earning more than OBFR: not credible) and -0.10 to 0.21 in window 2. Fitted c at the base reading: 0.88 / 0.92 / 0.92 (SPYQ / MQQQ / QQQP) in window 1. In window 2, with the filed fee path (section 6), it is 0.65 / 0.52 / 0.73 |
| Period ends (reset dates) | the last NYSE session of each week / month / quarter, from the rule-based calendar in `nyse.py`. That calendar holds holiday rules from 1970 plus a dated list of one-off closures. A period end that has no row in the data raises an error. Before 1970: the last data row of the period. Only the loader's gap and missing-weekday checks guard that rule | VERIFIED against the exchange's own record for 1970-2011 (2026-10-24). Post-2011 closures: checked against the price data (the exchange's notices are not on file) | Prospectus: business day = any day the NYSE is open. Rules: a Saturday holiday closes the Friday before, unless that Friday ends a month. So a Saturday New Year's Day gives no closure, and 1970-05-29 traded. MLK Day from 1998; Juneteenth from 2022; Monday holidays from 1971. Presidential Election Day closures: 1972, 1976, 1980. Source: "History of New York Stock Exchange Holidays" with "New York Stock Exchange Special Closings, 1885-date", the exchange's archivist's document revised through January 2011 (20 pages; copy kept privately, sha256 cbebd122...6f77). It states verbatim: Election Day "closed every year through 1968; closed presidential election years only, 1972-1980". Washington's Birthday and Memorial Day: "observed on Mondays since 1971". MLK Day: "closed all day beginning in 1998". The Saturday rule (adopted 1959-07-03): "when a holiday falls on a Saturday, the Exchange will not be open for business on the preceding Friday". The rule goes on: "unless it ends a monthly or yearly accounting period. See NYSE Rule 51". Its full-day special closings 1970-2011 are exactly the list in `nyse.py`. They are 1972-12-28 (Truman), 1973-01-25 (Johnson), 1977-07-14 (blackout), 1985-09-27 (Hurricane Gloria), 1994-04-27 (Nixon), 2001-09-11 to 14, 2004-06-11 (Reagan) and 2007-01-02 (Ford). Every other entry in those years is an early close, a late opening, a trading halt or a moment of silence. After the document: 2012-10-29 and 10-30 (Hurricane Sandy), 2018-12-05 (Bush) and 2025-01-09 (Carter). The SP:SPX export has no row on any of them and has rows on the sessions either side. The exchange's notices for those days are not on file, so these three rest on the data check and public record. Exports against the calendar from 1970 (checked 2026-10-24): no session is missing from SP:SPX or NASDAQ:NDX. SP:SPX has rows on the closures 1985-09-27 and 1994-04-27, and NASDAQ:NDX on 1985-09-27. The checks allow these rows and never flag them. NASDAQ:XNDX lacks 2012-10-31 and five sessions in its untrusted 2006-2008 block. SP:SPXTR has the stale rows 2001-09-11..14 |
| Early-reset trigger in the model | base case since R2 (2026-10-24): the trigger series is the ETF's price. That is AMEX:SPY from 1993-01-29 and NASDAQ:QQQ from 1999-03-10, with the index price before, spliced to be continuous. The breach test uses the day's LOW where the export has a real one. Index lows are placeholders before 1962 on SPX and 1985-10 on NDX. A low equal to the close counts as no intraday information. A fall of 35% from the level at the last reset fires the trigger. `early_mode`: "level" (base: reset at exactly the level, the rest of the day on the new base), "close", "next_close" | RULE from the prospectus for what the fund watches (the ETF's price, intraday). The fill at the level: ASSUMED. The drop: VERIFIED (35%) | Sensitivities in every study: drop 34% / 36%; index instead of ETF; close instead of low (the v1 run was index + close). The episodes decide the quarterly results. In 2008 they sit within one point of the line: SPY closed -34.95%, and its low breached the line. QQQ's low reached -34.54% on 11-20 and -35.62% on 11-21, while the index low touched -35.08% on 11-20. See FINDINGS F9 and section 7 below. The trigger has never fired live. The passive study computes what the fill mode is worth per episode (`fill_effect_vs_level` in its JSON). So this is not an assumption; section 5 below quotes the range |
| S&P 500 dividend yield before 1988 | Shiller's measured monthly D/P (default since 2026-10-13); decade map {1950s 4.2%, 1960s 3.1%, 1970s 4.0%, 1980s 3.7%} and flat 0 / 3 / 4% as sensitivities | MEASURED (section 3) | the yield moves absolute pre-1988 2x CAGRs ~2 pp per 1 pp of yield, the reset gap ~0.004 pp |

## 3. Underlying data (TradingView exports through a local price library; none is in the repo)

| Series | Symbol | From | Basis | Status |
|---|---|---|---|---|
| S&P 500 price | SP:SPX | 1950-01-03 (daily) | price | VERIFIED (anchor-checked in the local price library) |
| S&P 500 total return | SP:SPXTR | 1988-01-04 | total return | VERIFIED (no MCP feed; checked against SPX for plausibility) |
| S&P 500 total return before 1988 | SPX + Shiller's monthly dividend yield (trailing 12-month dividends / price) | 1950-1987 | constructed | **MEASURED** (B7, 2026-10-13): Robert J. Shiller, "Irrational Exuberance" data, `ie_data.xls` from econ.yale.edu/~shiller/data, downloaded 2026-10-13 (sha256 0df9392b...40db68; data to 2023-06; the file's only notice is an accuracy disclaimer). Derived file `reference/shiller_sp500_monthly.csv`. Mean 4.10%/yr over 1950-87 (by decade 4.9 / 3.2 / 4.0 / 4.2%); the source interpolates quarterly dividends to months. Sensitivities kept: decade map (ASSUMED, mean 3.8%) and flat 0 / 3 / 4%. Effect: pre-1988 2x CAGRs +0.3-0.4 pp/yr against the map; the reset gap unchanged |
| Nasdaq-100 price | NASDAQ:NDX | 1985-01-31 | price | VERIFIED |
| Nasdaq-100 total return | NASDAQ:XNDX from 2010-01-04; 2006-2010 NDX + 0.73% MEASURED; before 2006 NDX + 0.3% | constructed | the convention of an earlier private kit | ASSUMED pre-2006; sensitivity 0 / 0.3 / 1.0% |
| SPY, QQQ, SSO, QLD, MQQQ, QQQP prices | library | various | price, split-adjusted, no dividends | VERIFIED |
| SPYQ price | NASDAQ:SPYQ | 2024-10-01 (first bar; inception 2024-09-30) | price, split-adjusted, no dividends | VERIFIED 2026-10-12: 508 rows = MCP full history, anchor exact at both ends. Thin: ~4.5k shares/day |

Calendar quirks in the exports (MEASURED 2026-10-12, re-checked by hand; `series.banner()` lists them):
- SP:SPXTR has four stale rows on 2001-09-11..14 (level repeats 1533.98) while the NYSE was closed; SPX has none.
  `spx_total_return` drops them (it raises if such a row ever carries a moving value). SPX's calendar is the master.
- SP:SPX has a near-flat bar on 1994-04-27 (NYSE closed for Nixon's funeral) that SPXTR lacks. The constructed
  series carries that day by SPX's move and lists it in `attrs["days_filled_from_price"]`.
- NASDAQ:XNDX lacks 2012-10-31 (reopening after Hurricane Sandy); carried by NDX's move, as in an earlier private kit.
- Reference rate: DFF starts 1954-07-01; on SPX's calendar the TB3MS proxy covers 1,125 rows (1950-01-03 to
  1954-07-01 inclusive, the first DFF day being unknown "the day before"). The code shifts the monthly average to the
  prior month and then lags it one row (one row more conservative than letf's rule; no look-ahead). Tables that
  include those years say so.

## 4. Strategy execution (step 4)

| Item | Value | Status |
|---|---|---|
| Fill | signal on close t, fill at close t+1 (delay 1); also delays 2 and 3 | RULE |
| Half-spread | 0.10% Tradr funds (thin: QQQP ~4k shares/day), 0.02% SPY/QQQ/SSO/QLD | ASSUMED |
| Cash | 3-month T-bill (FRED DTB3), lagged | RULE |
| Cash yield basis | DTB3 (and the TB3MS proxy before 1954) is a bank-discount rate on a 360-day year. It converts to the investment yield 365 d / (360 - 91 d) before cash accrues. That gives 5.134% at d = 5% (+0.134 pp a year) and 1.016% at d = 1% (+0.016 pp). Cash then accrues on calendar days / 365 | RULE (R2 step 3, audit F4) | `backtest.discount_to_investment_yield`, used by `backtest.cash_returns`. Strategy results written before 2026-10-24 accrued the discount rate as if it were a yield (about 0.13 pp a year too little at 5%). `cash_returns(..., discount_basis=False)` reproduces them. 91 days is the bill's term |
| Clean Guppy | the author's Pine Script "Clean Guppy v1", kept locally and not published. `.gitignore` lists `reference/clean_guppy_v1.pine`; its SHA-256 is d605d97b674ea9241d4bf8085883662ecb2206bed0e416291393dd923d52c7f3. The published artifact is the Python port `strategies/guppy.py`. Rule fixed before testing (see PROMPT.md). Port verified: slow/fast/200 states identical to those computed from TradingView's own EMA columns on every daily and weekly row (S4 audit) | FIXED 2026-10-12, VERIFIED port 2026-10-13 |
| Drawdown stop re-entry | exit when the product NAV is 30% below its running peak since the start; re-enter at a NEW all-time NAV high. PROMPT.md did not fix the re-entry; this choice kept SPYQ in cash 17 years after 2000. The result (F13) is a property of this choice; a 25%-rebound re-entry gives a much different number (S4 audit) | DECISION 2026-10-13, ASSUMED |
| Weekly bars | TradingView dates a weekly bar by its FIRST session (usually Monday: 1,307 Mon / 132 Tue / 1 Wed in the QQQ export). Its close is the week's last session close. The engine signals on last-trading-day-of-week closes dated to that day | VERIFIED (1,440 weekly closes equal the daily file's week-end closes) |
| Pine `ta.ema` definition | alpha = 2/(n+1), seeded with the simple average of the first n bars (first n-1 rows empty) | VERIFIED 2026-10-12 on a TradingView export of QQQ daily with Clean Guppy v1 applied. It is a local export (6,940 rows 1999-03-10 to 2026-10-09), local only: price data. All 23 EMA columns match the Python port to 3.2e-12, including the seed rows. Weekly: a local export (1,440 weeks 1999-03-08 to 2026-10-05) matches to 1.7e-12 on all 23 columns. Note for the weekly rule: TradingView labels a weekly bar with its MONDAY, and its close is that week's last session close. So the engine builds its weekly signal from last-trading-day-of-week closes and dates it to that Friday. Step 4 keeps both files as git-ignored local tests |

## 5. What cannot be tested
- The 35% early reset is rare in the data (R2 re-run 2026-10-24, base trigger, level mode). SPX: quarterly 1
  episode (2008-11-20), monthly 0, weekly 0. NDX: quarterly 4 (1987-10-26, 2000-12-20, 2001-09-19, 2008-11-21),
  monthly 1 (1987-10-26), weekly 0. Under the v1 index-close trigger NDX quarterly had 3 episodes, with 2001-09-20
  and no 2008 episode.
- Any conclusion on quarterly against monthly resets rests on these few days. The 2008 episodes sit within one point
  of the line. So the drop (34 / 35 / 36%) and the price watched (ETF or index, low or close) decide whether they
  exist. The fill variant changes fund value by between -16% and +27% per episode relative to the level fill. In
  the passive study's JSON (`fill_effect_vs_level`, section 6 of each underlying), SPYQ's 2008 episode gives +2%
  at the close and +18% at the next close. QQQP's 2000 episode gives -16% at the close, and its 2008 episode gives
  +27% at the next close.
- The liquidated weekly and SPY-monthly funds (section 1) left one published month of NAV. Their daily prices are
  not available. So the project checks the weekly and SPY-monthly designs on one month only (FINDINGS F1b).
- No live calendar-reset fund existed before 2024-08; every earlier number is a model.
- The 35% early reset has never fired in a live fund.
- Financing spreads in a crisis. An earlier private kit found that the model understates them by 2-3%/yr for a 2x
  fund in 2008. This project has not re-derived that figure, so it is unverified here.
- S&P dividends before 1988 are Shiller's measured monthly series (MEASURED, section 2). Nasdaq-100 dividends before
  2006 use an assumed yield (0.3% a year).
- 1929-32 is out of scope: only monthly S&P data exists before 1950 (backlog: TVC:DJI daily).

## 6. What the funds actually hold (SEC Form N-PORT, read 2026-10-12; raw copy in `reference/nport_tradr_2026.json`)

VERIFIED facts, identical across all three funds and every snapshot read (2025-12-31, 2026-03-31, 2026-06-30):
- **Reference rate is OBFR**, the overnight bank funding rate ("OBFR01"), not fed funds and not T-bills. OBFR runs
  a few basis points below effective fed funds; FRED series `OBFR` (from 2016). DFF is a close proxy for history.
- **Spread: 75 bp (TD Cowen) or 100 bp (Clear Street, Wells Fargo)** over OBFR, on total-return swaps.
  Notional-weighted at 2026-06-30, read from the extract by `validate.filed_spread`: SPYQ 91.75 bp, MQQQ 99.30 bp,
  QQQP 92.96 bp. A typed 97 bp for MQQQ stood here until R2 step 12f. Window 1's own mix changed inside the window
  (SPYQ: Cowen and Clear Street at 2025-03-31, Wells Fargo added by 2025-06-30, structure timeline below). Those
  filings are not in the extract, so the fit uses the 2026-06-30 mix for window 1. Re-fits at the two filed
  extremes, 75 and 100 bp, BOUND window 1's cash yield.

  Every swap in the extract carries one or the other. Inside window 1, the N-CSR for the fiscal year to 2025-03-31
  (EDGAR document fp0093842) lists the same two terms. They are TD Cowen at OBFR01 + 75 bp, and Clear Street and
  Wells Fargo at OBFR01 + 100 bp. This project did not read the terms of swaps opened between 2025-04 and 2025-09.
  The bounds: SPYQ 0.802-0.915, MQQQ
  0.813-0.925, QQQP 0.842-0.956, against 0.878 / 0.922 / 0.924 at the 2026-06-30 mix.

  MQQQ's base sits near the top of its bound because its 2026 mix is mostly Wells Fargo at 100 bp. Its window-1 mix
  is not known. A read of the window-1 N-PORTs would narrow the bounds (R2 step 12g).
- **The swaps receive the TOTAL return of SPY / QQQ** ("Total Return on the SPY"), so the fund earns dividends on
  its swap exposure. It also holds the ETF directly (40-62% of NAV), which earns dividends too. This contradicts
  an earlier private kit's reading that the funds "fit only on price return"; step 2 must re-fit with the distributions
  added back and this structure.
- **Not "2 turns of swaps".** Exposure has two parts: a direct ETF holding (SPYQ 40-56%, MQQQ 57-62%, QQQP 45-56% of
  NAV) plus swaps for the rest. The fund pays the spread only on the swap notional. Crude reading: at a reset, about
  0.5 NAV sits in the ETF directly and 1.5 NAV in swaps. So the spread applies to ~1.5 turns, not 2.

  The fund's remaining cash (~0.5 NAV) sits as collateral, presumably earning near OBFR. Net carry then ~ 1.0 x OBFR
  + 1.5 x spread ~ OBFR + 1.4%/yr, versus the model's 1.0 x DFF + 2.2%/yr. (Written 2026-10-12; the R2 step-2 fit
  below measured the cash yield and found the 2026 structure is the end of a change that started mid-2025.)
- The funds do NOT reset swap notionals each period (Clear Street's SPYQ notional is 4,667,258.88 in all three
  snapshots). They manage exposure with trades in the direct holding and with swaps they add or terminate. Reported
  exposure (direct value + swap notional + unrealized appreciation) at the period-end snapshots: SPYQ 198% / 213% /
  179%, MQQQ 212% / 201%, QQQP 217% / 166% of NAV. This is not the clean 200% the model assumes at each reset. The
  cause is OPEN: trade-date against settlement-date timing in the filing, or real slippage from 2x. Step 2 check:
  compare the fund's actual period returns with 2x the ETF's.

| Input | Model (history / passive study) | Model (validation runs, R2 step 2) | Filing | Status |
|---|---|---|---|---|
| Reference rate | DFF (fed funds) | OBFR | OBFR | VERIFIED; DFF is a proxy, 0.0-0.2 bp apart on average over the 2024-26 fit windows |
| Spread | the two F5 encodings (section 2) | filed per fund: 0.92 / 0.99 / 0.93% (notional-weighted at 2026-06-30, read from the extract by `validate.filed_spread`; a typed 0.97% for MQQQ stood until R2 step 12e) | 0.75-1.00% (weighted 0.92-0.99%) | VERIFIED as filed 2026-06-30 |
| Turns paying the spread | 2.0 (notional basis) inside the encodings | at a reset: 2.0 to 2025-09-30, then 1.6 | swap notional / NAV at snapshots: 2.21 (2025-03), 1.75 (2025-06), 1.32 (2025-09), 1.16 / 1.29 / 0.91 (2026-06) | VERIFIED structure; the at-reset reading: ASSUMED (d = 0 / 0.4) |
| Dividend treatment | total-return underlying since F5 | the ETF's own total return (price + its dividends on ex-date) | swaps receive total return; direct holding earns dividends | VERIFIED structure |

| ETF expense ratios (netted from the constructed ETF total return, which the ETFs pay out of dividends) | SPY 0.0945% gross; QQQ 0.18% total | issuer pages read 2026-10-12 (SSGA "Fund Information as of Oct 12 2026"; Invesco product page) | VERIFIED |

**Structure timeline (R2 step 2, filings read 2026-10-24; all PRIMARY).** The 2026 snapshots above are the END of a
change. Earlier filings of the same series (SPYQ unless stated; the sister funds match where read):

| Period end | ETF held directly / NAV | Swap notional / NAV | Cash / NAV | Source |
|---|---|---|---|---|
| 2024-09-30 | 0% | about 2.0x at launch (SPYM 1.97, MQQQ 1.90, SPYB 1.96, QQQW 1.98, SOXM 2.01) | 100% ("other assets in excess of liabilities") | semi-annual financial report to 2024-09-30, schedules of investments |
| 2025-03-31 | 0% | 2.21x (Cowen 0.97, Clear Street 1.24) | 111% | N-PORT, period 2025-03-31 |
| 2025-06-30 | 0% | 1.75x (three counterparties; exposure with appreciation about 1.85x) | 88% | N-PORT, period 2025-06-30 |
| 2025-09-30 | 39.6% | 1.32x | 41% | N-PORT, period 2025-09-30; N-CSRS holdings SPYQ equity 48 / swap value 20 / cash 32, MQQQ 52 / 6 / 42, QQQP 48 / 23 / 29 |
| 2025-12-31 to 2026-06-30 | 40-62% | 0.9-1.3x at the snapshot | the rest | the three snapshots above |
| 2026-03-31 (shareholder report; all three funds) | 52 / 58 / 52% (SPYQ / MQQQ / QQQP) | swap VALUE 5 / -6 / 3% of NAV (the report shows value, not notional) | 43 / 48 / 45% | N-CSR FY2026 R2 (EDGAR 0001398344-26-010562); net assets 11.2m / 101.7m / 15.6m; portfolio turnover 174 / 158 / 263% |

Reading: to mid-2025 the funds ran all cash plus swaps of about 2x NAV. From the quarter ending 2025-09-30 they held
about 0.4-0.6 NAV in the ETF itself plus swaps for the rest. The funds pay the spread on the swap notional only, so
the spread turns fell and the cash balance fell with the switch. At a reset the identity is swaps s = 2 - d, cash
k = 1 - d (d = direct holding). The kernel fixes the notional at each reset and lets it drift inside the period. So
a period-end snapshot (2.21x after a down quarter) is not the number to feed in (section 2, balance-sheet row).

Note the 2025-09-30 snapshot, a reset date: printed notional 1.32 + direct 0.40 = 1.72 < 2. The swaps' unrealized
appreciation carries the rest. Whether the financing leg accrues on the printed notional or on the full exposure
is OPEN. The Clear Street notional never changes across snapshots; the Cowen and Wells Fargo notionals do.

**Cash yield (derived, not filed).** N-CSR FY to 2025-03-31: net investment income after waivers 2.38 / 2.39 / 2.27%
of average net assets (SPYQ / MQQQ / QQQP). Expenses after waivers were 1.30 / 1.31 / 1.30%. So gross investment
income was 3.57-3.70%, on a balance sheet of about 100% cash, while OBFR averaged about 4.5%. The cash earned
roughly 80% of OBFR. Status: ESTIMATE from one fiscal period's income ratios; the step-2 fit measures it as c below.

**R2 step-2 fit (2026-10-24, `scripts/run_validate_live.py`, `results/validate_live.{md,json}`; supersedes the
2026-10-12 fit).** Inputs: the fee timeline (section 2) and the ETF's own total return (price plus its dividends
reinvested on ex-date, `reference/etf_distributions.csv`). Also the filed spread per fund, OBFR, ACT/360, the price
trigger and level mode. Fund prices plus payouts stand in for NAVs.

With the at-reset balance sheet, the cash yield that closes the CAGR gap is **c = 0.88 / 0.92 / 0.92 in window 1**
(inception to 2025-09-30). In window 2 (to 2026-10-09, with the filed fee path of section 2) it is **0.65 / 0.52 /
0.73**. Both windows list SPYQ / MQQQ / QQQP in that order. That is, rate turns s - k c of 1.08-1.12 then 1.16-1.29.

The value **c is a residual conditional on the assumed direct holding d** (R2 audit). In window 1, d = 0 and the fit
assumes nothing else, so c is a fair measurement against the N-CSR income prior of 0.80. In window 2 the fit moves
with d, with a slope of -1.1 to -1.6 of c per unit of d. The fitted c for d = 0.3 / 0.4 / 0.5 / 0.6: SPYQ 0.74 /
0.65 / 0.53 / 0.36, MQQQ 0.63 / 0.52 / 0.37 / 0.15, QQQP 0.80 / 0.73 / 0.62 / 0.47. Across d, the invariant is the
all-in financing per NAV, 5.95 / 6.37 / 5.81% a year at a mean lagged OBFR of 3.71% (`results/validate_live.md`).

At the 2026 snapshots' d of 0.4-0.6, the implied yield (15-73% of OBFR) is not a deposit rate. So c also absorbs the
notional-or-exposure question below, the fee-switch date and the price-against-NAV term. At the derived prior c = 0.8
the model is 0.4-0.8 pp/yr too pessimistic in window 1 and 0.2-0.9 pp/yr too optimistic in window 2. At c = 1.0 it
is +0.4 to +0.7 and +0.8 to +1.5.

The v1 encodings, run on the same windows, stay within -0.5 to +0.3 pp/yr in both. The fixed 2.6% of NAV at the
prospectus fee gives +0.10 / +0.01 / -0.13, then -0.30 / +0.14 / -0.54. So the all-in cost beyond the fee did not
fall by the 1 pp/yr the R1 memo predicted. A lower cash yield (SPYQ rate turns 1.12 -> 1.21) offset the saving from
fewer spread turns (1.84% -> 1.47% of NAV a year). So the financing beyond 1.0 x OBFR fell only from about 2.36% to
2.24% of NAV. The fee itself fell from 1.30% to 1.22-1.00% in window 2 (section 2), which is most of the -0.30 pp the
fixed encoding shows there.

The filings explain the 2026-10-12 residual of 1.40-1.74 pp/yr against the filed 1.5-turn structure at a 1.00% fee.
The decomposition table in `results/validate_live.md` runs the kernel step by step from the v1 filed structure, in
CAGR terms for SPYQ in window 1. In it, the fee cap 1.00 -> 1.30% closes +0.38 pp/yr, and spread turns 1.5 -> 2.0
at 0.92% close +0.57. Rate turns 1.0 -> 1.12 (the cash yield) close +0.66, for a total of +1.61 = the v1 filed gap.
MQQQ: +0.41 / +0.74 / +0.51 = +1.66; QQQP: +0.42 / +0.62 / +0.45 = +1.49.

The nominal items are 0.30 + 0.46 + 0.53 pp of NAV a year for SPYQ. Each shows up about 1.25x in CAGR because the
fund gained about 25% in the window. OBFR against DFF over the fit windows: 0.0-0.2 bp apart on average, 0.00 pp/yr
on the gap. Conventions for history stay the same (F5: both v1 encodings by regime). The structural encoding is the
sourced reading of 2024-26, not a third encoding for history. The reason: no measurement of its balance-sheet inputs
(d, c) exists before 2024.

## 7. Statistics and conventions (R2 step 3, 2026-10-24)

Code: `calendar_letf/stats.py` (statistics), `calendar_letf/study.py` (where they attach to results), tests in
`tests/test_stats.py`. Status CONVENTION = a method choice, written down so a reader can change it; nothing here is a
measured input.

| Item | Convention | Status | Source / test |
|---|---|---|---|
| Interval for a headline gap (THE headline, since R2 step 10) | the phase-pooled interval from independent windows (row below). Every horizon-th start gives one set of non-overlapping windows (a phase). The method pools the phases. Mean +/- t(df, 0.975) x SE with df = smallest phase minus 1 | CONVENTION | Simulated coverage on the project's own overlap structure: the gap at start s = constant + mean of h consecutive iid monthly shocks. `scripts/run_coverage_sim.py` writes `results/coverage_sim.md`, and `tests/test_stats.py` recomputes three entries. Coverage is 0.94-1.00 over the eight published configurations (S&P 10-year 0.983, Nasdaq-100 10-year 0.998, 1-year rows 0.968 and 0.945). At ten years the multiplier the sampling distribution needs is 2.12 (S&P) and 2.21 (Nasdaq-100) against the t(5) = 2.57 and t(2) = 4.30 used. So those intervals are conservative. LIMIT (R2 steps 11-12): the convention takes windows that do not overlap as independent. A test checks this against the simulated distribution of the same statistic under independent months (4,000 iid series per configuration, `coverage.acf_null`). The statistic is negative on average because few windows share one mean. On this test, the S&P monthly design is persistent at 3, 5 and 10 years (lag-h autocorrelation +0.48 / +0.58 / +0.54). These lie 3.4 / 3.6 / 3.2 null standard deviations above the mean. One-sided p is 0.0003 at 3 years; no draw is as high at 5 and 10. Undetermined: its 1-year row (p 0.06), the S&P weekly design (p 0.0517-0.18, borderline at 5 years and noisy on the headline interval regardless). Also undetermined: MQQQ at 1-3 years (p 0.10-0.12) and QQQP at 1 year (p 0.08). MQQQ at 10 years reads p 0.01 on three windows per phase (fragile). SPYQ and the Nasdaq-100 weekly design sit on the independent value (p 0.39-0.61). The rule-of-thumb se 1 / sqrt(n / h) printed beside these is 1.2-3.3 times the simulated SD. So it is a conservative screen only (section 4 of the same file). In regime stresses that give lag-h autocorrelations of +0.08 to +0.34 the pooled interval covers 0.45-0.86 instead of 0.95 (section 3). So where persistence is present, the interval is too SHORT by an amount one history cannot pin down. A too-short interval that already covers zero stays noisy when widened, so no noisy verdict changes. The only clear rows are Nasdaq-100 weekly at 1, 3 and 5 years (t ratios 2.35 / 2.77 / 2.94). They carry two labels: clear under independent windows (2.06 / 2.15 / 2.05 needed). Under the mildest regime stress run they are noisy at 1 year and too close to call at 3 and 5 years. That stress is a 2% persistent share with a 34-month half-life: 3.01 / 2.88 / 2.84 needed. Each is the 95th percentile of 400 runs. Its 95% Monte Carlo interval at 3 and 5 years ([2.60, 3.48] and [2.63, 3.08]) holds the t ratio. The measured persistence cannot rule out that stress |
| Block-bootstrap interval (secondary; shown beside the headline, never the flag) | mean (or median) of the per-start gaps +/- t(k-1, 0.975) x SE. SE = standard deviation of 10,000 circular block-bootstrap means (or medians; seed 0). Block = the horizon in months, k = n // block | CONVENTION, with a known bias | the bootstrap SE has a LOW bias with block = window length. A block bootstrap sees only the dependence inside one block. Let the gap be the mean of h shocks. Then blocks of length h lose about a third of the variance of the series mean at ANY block count. With 201 blocks of 12, for example, the SE is 0.83 of the truth and coverage is 0.89. Few blocks add a further loss: at the eight published configurations (k = 3-75) the SE is 0.52-0.86 of the truth. The "95%" intervals cover 0.85-0.92 (mean) and 0.86-0.93 (median) over 400 runs (`results/coverage_sim.md` sections 1-2). Source: an R2 step 10 audit finding; step 11 corrected the stated mechanism. On iid data the same code covers 0.950 (n = 252, block 21; percentile interval 0.922). On AR(1) with phi 0.5 it covers 0.915 (0.877). That is why the earlier coverage tests missed it. Monte Carlo error of a bound: its movement over seeds 0-3 at 10,000 draws for all 24 rows. Sources: `bb_seed_spread` in `results/coverage_sim.json` (fixed encoding) and `results/coverage_sim.md` section 5. Of these movements, the largest is 0.17 pp, the Nasdaq-100 quarterly median at 3 years. That fund's medians also move 0.06 pp at 5 years and 0.11 at 10 (where t(2) = 4.30 amplifies the SE's own noise). Its means move up to 0.04. Every other row's bounds move by at most 0.026 pp (MQQQ's mean at 3 years) |
| Interval for the median of the gaps (secondary) | the same circular block bootstrap applied to the MEDIAN. Interval: median +/- t(k-1, 0.975) x bootstrap SE of the median. The bootstrap SE of a median is a reasonable device, not an exact one on skewed data. It carries the same low bias at 3-7 blocks as the mean version (row above: coverage 0.86-0.93 at the published configurations) | CONVENTION (R2 step 9; demoted to secondary in step 10) | `stats.block_bootstrap_median`. Coverage test, 400 runs, n = 252, block 21: 0.948 on iid normal data, 0.955 on a skewed (lognormal) sample. A second plain-loop implementation in the tests |
| Block length | the horizon in months (12, 36, 60, 120) | CONVENTION | starts one month apart share all but one month of a window, so a block of `horizon` consecutive starts is about one independent window |
| t multiplier | built-in table for df 1-60 (exact values), four-term series above; matches `scipy.stats.t.ppf` to 5e-7; the code does not need scipy | CONVENTION | `stats.t975`; the tests compare it with scipy when scipy is present |
| "Noisy" flag | the headline (phase-pooled) 95% interval covers zero; the block-bootstrap intervals carry their own flags, labeled `(bb)`, which are not the headline | CONVENTION | `stats.covers_zero`. An interval that the code cannot compute (k < 2) also counts as noisy. In the timing-rule study, a row whose smallest phase holds fewer than 3 non-overlapping windows gets the flag `too_few_windows`. That row counts as noisy whatever its interval (`MIN_WINDOWS = 3` in `scripts/run_strategies.py`, the lower end of the coverage simulation; R2 step 12e). Under the block-bootstrap flags more rows read "clear". They are NDX weekly (mean and median) and MQQQ's median at every horizon, and QQQP's median and SPX monthly's mean at 1 year. Under the headline flag none of the 10-year rows reads clear; only NDX weekly at 1, 3 and 5 years does |
| Interval from non-overlapping windows (the headline interval) | every `horizon`-th start gives one set of independent windows (a phase). Pooled over phases: mean = average of phase means; SE^2 = average of s_p^2 / k_p; df = smallest k_p - 1; t(df) multiplier | CONVENTION | `stats.phase_pooled_mean`. Each phase is a shifted copy of the others, so the average does not cancel their errors. At 10 years k_p is 6-7 on the S&P 500 and 3-4 on the Nasdaq-100 (t = 2.6 and 4.3). Simulated coverage is 0.94-1.00 under independent months, with the stated limit under persistence (first row of this table) |
| Variance ratio | Lo and MacKinlay (1988) unbiased VR(q) with q-period sums that overlap; heteroskedasticity-robust z*(q) from their theorem 2. Horizons q = 5, 21, 63 trading days (weekly, monthly, quarterly). The code computes it on simple daily returns of the total-return series | CONVENTION | `stats.variance_ratio`; hand-computed 6-return case; 1,000 random-walk paths of 2,500 steps: |z*| > 1.96 in 6.2% (q = 5) and 5.2% (q = 21) of paths |
| AR(1) | rho = sum (r_t - mu)(r_{t-1} - mu) / sum (r_t - mu)^2; SE = 1 / sqrt(n); the robust alternative is the z of VR(2) | CONVENTION | `stats.ar1`. The published decade column (`autocorr_lag1`, log returns, correlation of the shifted vectors) stays; it differs from rho by less than 3/n (tested on 2,000 returns) |
| Predicted sign of the reset gap | per reset period of T days, E[calendar - daily] = (beta - beta^2) [C(T,2) mu^2 + T sigma^2 / 2 (VR_T - 1)], with beta = 2. So the factor is -2, and the calendar fund leads when VR_T < 1 - (T-1) mu^2 / sigma^2. Here mu and sigma are the mean and standard deviation of the decade's daily simple return. T = 5 / 21 / 63 for weekly / monthly / quarterly | CONVENTION (second-order expansion) | Bessembinder (2026), SSRN 7376118, eq. 7-13; `stats.predicted_reset_gap`. The expansion drops the (beta - beta^3) terms. They are 2% of the second-order term for iid returns at mu = 0.1% a day, T = 21 (tested). They are 2.4% and 2.2% for planted MA(1) reversals and continuations (tested, simulated against the expansion). Costs, the early-reset trigger and the different financing of the two structures are not in it, so a miss is information, not an error |
| Descriptive correlation across decades | correlation between the decade's AR(1) and the decade's gap, n about 8 | DESCRIPTIVE ONLY | no sampling distribution; the tested statements are the variance-ratio z and the predicted sign |

Trigger basis (R1 E4, audit finding):
- **What the fund watches.** The prospectus trigger is on the price of the ETF (SPY, QQQ), during the day. The base case of
  the passive study tests the ETF's daily low from the ETF's first bar (AMEX:SPY 1993-01-29, NASDAQ:QQQ 1999-03-10).
  Before that it tests the index price (low where the export has a real low, else the close). The index-only, close-only
  run is the long-history case and the v1 result; it is one row of the trigger-basis table.
- **Splice.** Before the ETF's first bar, trigger = index price. From that bar on, trigger = the ETF's price x k, with
  k = index close / ETF close on the first bar. So the series is continuous there, and the trigger test (a fall from the
  level at the last reset) sees no jump.

  The ETF price is split-adjusted and not dividend-adjusted, like the index price. The ETF price drifts below the index
  price by its fee and by dividend timing. At the end of the file the ratio is 0.971 (QQQ) and 0.995 (SPY) of the
  first-day ratio. The test compares each day with the level at the last reset, a few months back, so this drift does
  not matter.
- **Rows with no ETF bar.** Two cases have an index row and no ETF row. One is 1994-04-27, a closure the S&P export
  keeps. The other is the nine days after the SPY export ends. Such a day carries the index move at the last known ETF-to-index ratio.
- **Bad low prints.** An ETF low that sits more than 10% of the close below the index's own low-to-close gap that day
  gets the index's gap instead. This removes 3 days in the QQQ file (2000-04-12: low 31 points under the index's;
  2002-05-03; 2002-06-27) and none in the SPY file. Without the guard, the 2000-04-12 print fires the 35% trigger for
  MQQQ and QQQP, and the 2002-06-27 print fires it for QQQP (measured 2026-10-24). No real fall of that size occurred
  on those days.

  A real dislocation smaller than 10 points (SPY and QQQ on 2010-05-06; QQQ on 2015-08-24, 7.7 points deeper than the
  index) stays. The SP:SPX export has one bad low as well (2003-05-02: 812.38 against a close of 930.08). It is far from
  any trigger level and stays in the index-basis rows.
- **Drop.** The trigger drop is 35% in the base case. The table also runs 34% and 36%, because a close or low within 1
  point of the line decides whether an episode exists. SPY closed 34.95% below its 2008-09-30 close on 2008-11-20.
  QQQ's low reached 35.62% below on 2008-11-21, a day after the index low of 35.08%.
- **Same episode on two bases.** Dates within 4 calendar days in the index run and the ETF run are the same episode
  (`study.match_episodes`). A date with no partner is "index only" (the engine resets, the fund would not) or "ETF only".
- **Fill.** Unchanged: mode `level` fills at the trigger level; `close` and `next_close` are sensitivities.

R2 step 9 simulated the coverage of the non-overlapping-window (phase-pooled) interval (`tests/test_stats.py`). The
test uses 400 synthetic series of 799 monthly starts. In each, the 10-year gap is a constant plus the mean of 120
consecutive iid shocks. So neighboring starts share 119 of 120 shocks, the real overlap structure. The interval covered
the constant in 0.983 of runs. So with 3-7 windows per phase and t with 2-6 degrees of freedom, it is slightly wide,
not short.

The same construction, run at all eight published configurations, a 201-block case and four regime stresses, gives
the ranges in the table above. `scripts/run_coverage_sim.py` runs them (R2 step 11; `results/coverage_sim.md`, three
entries recomputed in the suite). Why the pooled interval is the headline: under independent months it covers at or
near nominal at every configuration this project reports. The lowest is 0.945, within Monte Carlo error of 0.95. In
contrast, the block bootstrap covers 0.85-0.93, and more blocks do not repair it (0.89 at 201).

What neither can do: when windows that do not overlap are themselves persistent, as the S&P monthly gap series is,
both are too short. The table states the measured persistence per product and the simulated coverage under it. No
clear verdict in this project rests on a row with measured persistence.
What this section cannot show: the win shares (descriptive, no interval). Nor can it show any uncertainty from the
cost encodings or the early-reset fill. The sensitivity tables show that uncertainty, but the intervals do not include it.
