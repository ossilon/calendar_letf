# Findings

Results ledger. Code in this repo produced every number here, and each number names its script, data and settings.
A number becomes a result only when this file records it with its provenance. The build-step outcomes come first, so
that a later reader knows the state of the code when it produced each result.

## Build log

**S0, 2026-10-12.** DESIGN.md written; its section 10 records the decisions.

**S1, 2026-10-12 (kernel and loader built separately; reviewed).**
- `py tests\run_tests.py` prints `0 failure(s)` (137 checks + 2 local cross-checks; re-run by the reviewer).
- Local cross-check: `periodic_reset_series` equals an earlier private kit's reset function, and
  `daily_reset_series` equals a private financing kit's daily-reset function. The max relative error is 0.00e+00 on
  every row in 15 cases. The cases cover random walks at 1.5% and 3.5% daily vol, monthly and quarterly, with the
  trigger on and off. They also cover the real NDX price index 1985-2026 at a constant 4% rate. The constructed
  Nasdaq-100 total return equals that kit's Nasdaq-100 total-return builder to 1e-12.
- Timing: 30 calendar + 10 daily runs on 20,000 rows in 0.12 s after numba warm-up.
- Reviewer changes: `calendar.py` became `periods.py`, because the old name shadows Python's `calendar` module when a
  file runs from inside the package. The reviewer also corrected ASSUMPTIONS and DESIGN: the close-only trigger does
  not bracket the fund's intraday trigger.
- Not done: no pip install of the package (it runs from the repo root); README not yet written; SPYQ not yet in the
  price library. No backtest result exists yet.

**S1 audit, 2026-10-12 (an independent audit).** Verdict: usable with caveats. No wrong formula. Ranked findings:
1. The early-reset variant matters. On SPX 2008-11-20, delay 0 and delay 1 differ by 13.7% of fund value in one day
   and by 0.2 pp/yr of whole-history quarterly CAGR. The audit asked for a "reset at the trigger level" base variant
   and a price-index trigger for TR runs.
2. The pre-1988 S&P yield of 3% (ASSUMED) is low against letf's decade map (about 3.8%). It moves absolute pre-1988
   CAGRs by about 2 pp and the reset gap by 0.004 pp.
3. `turns` not tied to L (3x would under-charge).
4. The gap check cannot see one missing weekday.
5. Silent tails: TR series extended price-only at the end; stale DFF forward-filled.
6. The TB3MS proxy has a same-month look-ahead in 1950-54 (about 0.01 pp/yr).
7. The twin fee should copy the compared fund.
8. Row 0 is a reset (results need ratios of full-history NAV).
9. The 1.1% spread is weak, but the reset gap is insensitive to it (+1.15 +/- 0.01 pp/yr for spreads 0-1.5%).
10. Hygiene: absolute paths in PROMPT.md, stale module name in `__init__`.

Auditor's episode counts (scratch, base costs; step 3 re-runs them) for SPX: quarterly early resets 1 (2008-11-20),
monthly 0, weekly 0. For NDX: quarterly 3 (1987-10-26, 2000-12-20, 2001-09-20), monthly 1, weekly 0. Could not test:
live fit, Tradr N-PORT terms, intraday trigger (SPX lows are placeholders before ~1970; NDX has real lows from 1985).

**S1c audit fixes, 2026-10-12 (kernel and loader; reviewed).**
- Suite: `0 failure(s)`, 240 checks (re-run by the reviewer). The cross-check against funds.py / letf.synth still
  gives 0.00e+00 in all 15 cases (mode "close").
- Kernel:
  - `early_mode` level / close / next_close replaces `early_delay`.
  - A separate price trigger for total-return runs.
  - The trigger re-arms on a fall through two levels in a day.
  - Turns tied to L with a `spread_basis`; `products.twin_of`.
  - The row-0-is-a-reset rule documented and tested (a mid-period slice is 1.02% off; a reset-date slice matches
    to 1e-15).
- Loader:
  - Decade-map pre-1988 yield.
  - `check_missing_weekdays` (floor 248 rows, 1968 exception 225: real minimum 226).
  - The loader counts trailing price-only rows on a TR series and refuses more than 10 (today SPX_TR has 5: SPXTR
    ends 2026-10-02).
  - It counts stale rates and refuses more than 15 (today 12: DFF/DTB3 end 2026-09-23).
  - It refuses interior rate holes over 10 days.
  - TB3MS proxy shifted to the prior month.
- Not fixed: a single missing month-end row still passes the guards (the fix needs an NYSE holiday calendar).
- Data read the same day: Tradr N-PORT filings (ASSUMPTIONS section 6, `reference/nport_tradr_2026.json`) and
  distributions (`reference/distributions.csv`). SPYQ added to the price library (anchor exact).

**S1c re-audit, 2026-10-12 (an independent audit).** Verdict: usable for step 2 with caveats.
- The audit verified the level-mode math by hand (five tests).
- On both historical trigger days the index traded through the level. SPX 2008-11-20: open +5.0%, low -1.4% against
  the level; NDX 1987-10-26: open +8.9%, low -4.0%. So "fill at the level" is defensible there.
- Episode counts equal across modes.
- Findings:
  - costs.py comments contradicted the N-PORT structure (reworded).
  - Turns can still reach the kernel inconsistent with L through the bare wrappers (step 2 adds a
    `kernel.run(spec, ...)` entry point).
  - Level mode never wipes out in one day (now in the docstring).
  - The TB3MS shift is one row more conservative than letf (reworded).
  - `check_missing_weekdays` would false-refuse a file ending 24-27 December (step 2 fix).
  - The proxy ends 1954-07-01 (register corrected).
- Auditor scratch (not a result): the quarterly-minus-daily gap on SPX TR 1950-2026 is insensitive to the spread. It
  runs from -0.644 to -0.573 pp/yr for spread 0 to 3.0% of NAV. But it moves 0.2 pp/yr with the early-reset mode
  (level -0.589, close -0.619, next_close -0.413).
- Day-count caveat: OBFR swaps are normally ACT/360; the model uses calendar/365 (+6 bp/yr at 4%, shared by fund and
  twin).
- Rates refreshed to 2026-10-08; OBFR added the same day.

**S2 audit, 2026-10-12 (an independent audit).** Verdict: usable for step 3 with caveats; every number reproduced.
Findings applied:
1. The ETF total return had left the ETFs' own fees in. The ETFs pay these fees from dividends, so the price never
   shows them. Now netted; residual 1.3-1.7 pp/yr.
2. The residual must go into history as BOTH a fixed spread and a rate-proportional charge. The two differ by 1.4-1.7
   pp/yr in 1966-82 and 2009-15 (a v1 estimate; its R2 values are the `encoding_gap` table of ASSUMPTIONS section
   2). The reset gap does not move.
3. "price basis + filed costs" is a lower bound, not a sensitivity.
4. A regression slope / intercept replaced the per-period ratio; the small-move filter rose to 1% monthly / 3%
   quarterly.
5. F1 confirmed (ex-date convention and the $3.66 payout both needed).
6. Model start, costs, case C algebra and the OBFR lag confirmed.
7. Hygiene: rate loader called with name and hole check, fund symbols carry their exchange, split cut-off sourced.

Suite after the fixes: `0 failure(s)`, 272 checks.

**S3, 2026-10-12 (the step also wrote metrics.py and the multi-start sweep; reviewed).** New: `metrics.py`, `study.py`, `scripts/run_calendar_vs_daily.py`,
`tests/test_metrics.py` (54 checks), reset "never" in `periods.py` (the buy-once margin benchmark; the reviewer
opened it in `kernel.periodic_reset_series` with a test). Suite `0 failure(s)`, 326 checks. Script: 3,960 kernel
runs in 0.61 s, whole study 2.3 s. Results F6-F12 below; full tables in `results/calendar_vs_daily.md`.

**S3 audit, 2026-10-12 (an independent audit).** Verdict: math right. Every F6-F8 number reproduced byte-for-byte.
The audit checked month-ends, window lengths, calendar-day CAGR, numba max-drawdown, twin costs and metrics by hand.
Interpretation reworded in F6, F7, F9, F10, F11:
- SPYQ's negative S&P result is the single 2008-11-20 episode (trigger off: +0.26, ties monthly).
- Quarterly's gap follows the market level, not autocorrelation.
- F10's "dip" is an annualization artifact.
- The margin benchmark depends on the margin-call rule and counts wiped-out windows as fund wins.
- The S&P +0.3 pp is 4 of 7 independent windows.

The study gained a trigger-off sensitivity row, an inside/outside-episode split (section 6b) and non-overlapping-window
win shares (section 2b). Those numbers now come from the script. Suite `0 failure(s)`, 326 checks; script 2.4 s.

**S4, 2026-10-13 (indicators module and tests; plugins, backtest and study; reviewed).** The indicators work replaced a
separate EMA task, because a hand check had already verified the EMA. New files:
- `indicators.py` (`pine_ema` = TradingView's ta.ema, `guppy` ribbon states, `week_end_rows`) and
  `tests/test_indicators.py`.
- `tests/guppy_ema_local.py` (git-ignored): all 23 EMA columns of the daily and weekly QQQ exports reproduced to
  3e-12. The weekly export's 1,440 closes equal the daily file's week-end closes.
- `backtest.py` (numba wealth loop, delay, costs).
- `strategies/` (base contract, registry, `discover`, generic look-ahead check; 7 plugins, 12 variants).
- `scripts/run_strategies.py` and `tests/test_strategies.py` (103 checks).

Suite `0 failure(s)`, 446 checks; script 5.4 s. DESIGN section 7's cost formula corrected (one half-spread per unit
of position changed). Results F13-F16 below; full tables in `results/strategies.md`.

**S4 audit, 2026-10-13 (an independent audit).** Verdict: usable for the README with caveats; engine right.
- Every F13-F16 number reproduced.
- Guppy states identical to TradingView's own: 0 of 8,380 rows differ.
- Delay 0 lower than delay 1, so no rule needs a same-close fill.
- Costs and cash verified.

Reworded:
- F14: the 200-day rule is not positive out-of-sample on a whole-era basis (-0.2 pp 1990-2026, -8.4 in 2009-26).
- F15: delay 1 is the sweep maximum.
- F13: drawdown-stop re-entry unspecified; guppy_weekly wording.

Added: an every-5th-row look-ahead cut. The fixed cuts missed a rule that peeks only late in the sample; all 12
shipped variants pass. Nits:
- TradingView dates a weekly bar by its first session (not always Monday).
- `week_end_rows` flags the final row whatever its weekday (harmless on history; it would emit a partial-week signal
  live).
- DTB3 is a discount yield (about 13 bp low at 5%).

**S5a (B7), 2026-10-13.** Shiller's monthly S&P 500 dividend yield replaces the assumed decade map before 1988.
- Source: `reference/shiller_sp500_monthly.csv`, derived from `ie_data.xls` (downloaded 2026-10-13 with the user's
  permission).
- `series.spx_total_return(pre_yield="shiller")` is the default; the decade map and flat yields stay as
  sensitivities.
- 4 new tests; suite `0 failure(s)`, 464 checks.
- Both studies re-run: no reset gap moved by more than 0.01 pp; pre-1988 S&P absolute 2x CAGRs rose 0.3-0.4 pp/yr.
  F11, F12, F13, F14 and the S3 settings line updated.

Still open in B7: QQQ distributions 1999-2006 for the Nasdaq-100 (0.3% assumed).

**S5b packaging, 2026-10-13 (the README written in this step because the headline wording is audit-bound).** User
decisions:
- Publish code + results + reference files with no personal identifiers.
- Do NOT publish the Pine source (git-ignored; SHA-256 kept); publish only the verified Python port.
- Regime-first headline.
- Private GitHub repository first.

Done:
- README.md (headline, reset rules, model, reproduction, plugin how-to, caveats, licenses and attribution).
- pyproject 0.1.0 with readme; `.gitignore` for the Pine files.
- `scripts/plot_guppy.py` (candles + ribbons + rule events for any symbol; `results/guppy_SPY_weekly.png` for the
  README).
- Identifier scan of every file (clean); suite `0 failure(s)`, 464 checks.

The build machine has no Git: the user initializes and pushes. Open: B7(b) QQQ distributions 1999-2006 (no public
source found); everything else in BACKLOG.md.

**B13, 2026-10-13 (built, reviewed, and checked by an independent audit).** Entries from major bottoms:
`bottoms.py`, `scripts/run_from_bottoms.py`, `tests/test_bottoms.py` (61 checks), `products.MODELS_3X`
(UPRO_MODEL / TQQQ_MODEL at the filed 3x terms). Suite `0 failure(s)`, 525 checks; script 5.8 s. Audit verdict:
usable with corrections, all applied:
- "a full quarter after March 2009" was wrong (sixteen trading days, to the 2009-03-31 reset).
- QQQP's 4.40x on 2008-11-20 is a close-only-trigger artifact (the day's low was through the level).
- The 30-40% level entries were no better than the plain index.
- The bottom-against-confirmation comparison is true by construction. The rule-entry comparison is the informative
  one, and it goes against the confirmations on the S&P.
- "cannot be wiped out" softened to the design intent.
- The 3x comparison now carries its drawdowns; the 1962 and 1970 troughs noted.
- UPRO's fee status carries letf's RECHECK flag; README reproduction list updated.

Results F17-F20.

**R2 step 1, kernel exactness, 2026-10-24 (kernel changes built in an independent session at the highest effort,
reviewed in the main session, then audited independently).** Suite 599 checks after the step, 0 failures outside one
stale data file (below). Changes:
- (E1) The buy-once margin benchmark has its own kernel, `margin_position_nav`, whose loan compounds daily with the
  spread and fee borrowed. Over ten years at 5% the planted position ends at 4.339 against 4.493 under simple
  interest. Inside one quarter the two conventions differ by 8.0e-5 of NAV. The calendar kernel keeps simple accrual
  inside a period, the swap convention.
- (E2) Financing legs accrue ACT/360 and the fee on 365 days; a flat year at 5% costs 5.069%.
- (E3) Period ends come from a rule-based NYSE calendar (`nyse.py`, rules from 1970 plus fifteen one-off closures). A
  missing period-end row raises an error. The engine flags the final row when it ends its period. Against the exports
  from 1970, no session is missing from SPX or NDX. SPX and NDX both carry a row on the 1985-09-27 closure, which
  moves that week's reset to 09-26.
- (E4) An optional intraday-low trigger (`trigger_low`). A low equal to the close counts as no information. Real lows
  start 1962-01-02 on SPX and 1985-10-01 on NDX.
- (E5) One fee per row (a step series).

Canon tests (`tests/test_canon.py`):
- Bessembinder's exact identity holds to 3e-15 on 150 random periods and three S&P quarters.
- The daily twin satisfies the Avellaneda-Zhang log formula within its bound. Its error is first order in dt (10.2
  times smaller for a tenfold finer grid).
- Planted MA(3) correlation reproduces the sign rule: the calendar fund wins when VR_21 < 0.968. It also reproduces
  the third-order expansion within 4 standard errors.
- Property tests pass; a vectorized second implementation matches to 2e-15.

The cross-checks against the two earlier engines still print 0.00e+00 in all 15 cases with the old conventions
passed explicitly (`fin_day_count=365`, `calendar=None`). Data the same day:
- The SP:SPXTR export was 13 rows stale. A new export replaced it (identical on all 9,765 overlapping rows, 15 rows
  added).
- The price library gained a tested `reimport` command for that purpose.
- `series.spx_total_return` now drops and lists published rows dated after the price file's last row; before, it
  refused them (test 9e).

Suite 606 checks, 0 failures.

**R2 step 1 audit, 2026-10-24 (independent reviewer, highest effort).** Verdict: usable.
- Kernel arithmetic right; every changed test number re-derived by hand and matched; no look-ahead in the low
  trigger.
- The closure list and the 1972-80 election closures agree with the exchange's history and both data files.
- The old conventions are reachable only through explicit keyword arguments that no production path uses.

High finding: the trigger BASIS. The prospectus trigger watches the ETF's price; the engine watched the index.
- On 2008-11-20 the Nasdaq-100 index low touched -35.08%, while QQQ's low stopped at -34.54% (it reached -35.62% the
  next day).
- SPY closed at -34.95% with only its low through the line.
- So a close-only index trigger finds SPYQ's episode for the wrong reason, and a low-only index trigger gives QQQP an
  episode a day early.

Also:
- The margin compounding correction is 0.1-0.2 pp/yr at the median on real windows (the review memo had said about
  0.4).
- The benchmark's spread accrues on the opening balance (ASSUMPTIONS now states this).
- The strategies' cash rate was a discount yield, accrued as if it were an investment yield.
- An intraday low through zero would not finish a close-mode fund (no 2x fund came within 0.14 of that line
  1950-2026).

Grades after the audit: EXACT A-, PROVEN B+.

**R2 step 2, 2026-10-24 (validation re-fit against the issuer's NAV figures).**
- `validate.py` gains `fee_timeline`, `Structure`, `structural_rate`, `fit_cash_yield`, `window_return`,
  `worst_in_period_fall`.
- `run_validate_live.py` rewritten (fee timeline, two-window structural fit, NAV anchors, liquidated funds, ETF total
  return on the ETF's own dividends).
- In `products.py`, kind `HYPOTHETICAL` became `MODELED`, with the live record of each design.
- New reference files: `reference/nav_anchors.csv` (23 published NAV figures with their filings) and
  `reference/etf_distributions.csv` (SPY / QQQ dividends 2024-06 to 2026-09, SECONDARY).
- ASSUMPTIONS sections 1, 2, 6 updated (twelve-fund table, fee timeline, balance-sheet rows, structure timeline,
  derived cash yield).
- Tests: `tests/test_validate.py` section 4c (+16 checks), `tests/test_kernel.py` section 4 (+2).

Results F1-F5 below replace the 2026-10-12 block.

**R2 step 3, 2026-10-24 (uncertainty).**
- New `stats.py` and `tests/test_stats.py` (81 checks). `stats.py` holds:
  - a circular block bootstrap with t(k-1) x SE intervals;
  - a built-in t table that matches scipy to 5e-7;
  - the Lo-MacKinlay variance ratio with the heteroskedasticity-robust z;
  - AR(1) with its standard error;
  - the predicted-sign formula.
- `study.py` gains:
  - intervals and "noisy" flags on every headline gap;
  - VR(5/21/63) with z and the predicted sign per decade;
  - means next to medians in the margin table;
  - the trigger-basis sensitivity (drop 34 / 35 / 36%; index or ETF price; close or daily low). It also splices the
    ETF price onto the index before the ETF's first bar and guards against three bad low prints in the QQQ export.
- `backtest.py` converts DTB3 from a discount rate to the investment yield before cash accrues.
- ASSUMPTIONS section 7 (conventions) and the section 4 cash row.

The passive study's base case became the ETF's daily low from the ETF's first bar.

**R2 step 4, 2026-10-24 (traceability).**
- `provenance.py`: sha256, rows and dates of every input, written into each study's JSON and banner.
- `tests/golden/` with one file per study that pins every published number; `tests/test_golden.py`;
  `scripts/refreeze_golden.py` (refuses without a reason; keeps a dated list of re-freezes).
- `scripts/fresh_clone_check.py` copies the publishable files to a temp folder and runs the suite with the data
  variables unset. The data-free tests pass; the data-bound ones skip.
- `scripts/scan_identifiers.py` and `scripts/ste_check.py`, with tests. The categories the suite enforces (home
  paths, e-mail addresses, secrets and daily data series) are at zero. Until the release pass, the scan reports three
  categories but does not enforce them. They are model names (25, all in this file's v1 build log), British spellings
  (559) and sibling-folder names (29). Until then the script's own exit code is 1.
- PROMPT.md, DESIGN.md and BACKLOG.md moved out of the public tree.
- `data/README.md` lists the exports a stranger needs, with today's row counts and dates.

**R2 step 5, 2026-10-24 (re-run and restatement).** All four studies re-run on the R2 engine with the provenance
block. The strategies and bottoms scripts moved to the same base trigger as the passive study. Each has a labeled run
of the v1 trigger as a sensitivity. What moved against the v1 results, and why:
- ACT/360 took about 0.1 pp/yr off every 2x CAGR (reset gaps within 0.01 pp).
- The exchange calendar changed nothing on these files.
- The compounding loan moved the margin benchmark (F11).
- The ETF-price intraday trigger moved the quarterly products, QQQP by 2.4 pp/yr at ten years (F6, F9).
- The cash yield conversion added 0.1-0.2 pp/yr to the S&P rules that hold cash (F13-F15).
- The SPX data refresh to 2026-10-22 took 0.07 pp off S&P full-history CAGRs.

Three v1 statements were wrong on the v1 numbers; the Results below correct them:
- F17's "4.40x is a close-only artifact" (it is the trigger-basis knife edge);
- F20's "ten times" (six);
- F13 / F15 figures that predated the Shiller re-run.

Golden files re-frozen with the reason "R2 engine exactness ... and the ETF-price intraday base trigger" (the v1 pins
stay in the private results snapshot). Suite 908 checks, 0 failures.

Engine grade after the step-5 restatement, as the independent final audit gave it (the restatement had claimed A- on
all four):
- EXACT A-: level fill ASSUMED; closure list checked against the data and memory, not an exchange document. The
  bottoms dollar tables used 252-day horizons where every other table uses calendar years.
- PROVEN B+: planted tests cover the kernel, the canon and the statistics, and the suite caught three planted breaks.
  No planted test on the dollar layer, which is how the horizon slip passed. The t-table check needed scipy.
- UNCERTAINTY B+: every headline carries an interval or a noisy flag and every regime claim a z. The prose had read
  the fitted cash yield as a measurement, without its d-sensitivity. One arithmetic and one attribution slip.
- TRACEABLE B+: hashed inputs, golden files with reasons, fresh clone passes. Two register rows that FINDINGS pointed
  to were missing. Nine transcription slips, two of them v1 figures presented as current.

The audit re-derived by hand:
- the SPYQ anchor (-7.98% against the kernel's -8.00% and the N-CSR's -8.08%);
- the trigger table (24 of 24 cells);
- one decade's variance ratio;
- the raw SPY and QQQ lows around the 2008 line.

Step 6 below closes the named gaps.

**R2 step 6, 2026-10-24 (audit fixes).**
1. The bottoms dollar tables now use the calendar-year horizon rule of every other table (`bottoms.horizon_row`
   accepts half years as whole months; `bottoms.dollar_values`). A planted test covers it: a NAV that grows 1% a
   calendar month gives $10,000 x 1.01^(12h) to 1e-9. The old 252-day rule misses it by over $100 at every horizon.
   Medians at 3 years moved from $28,239 to $27,323 (SPYQ). For the Nasdaq-100 fund / twin / 3x / index they moved
   from $37,484 / $35,326 / $52,873 / $21,865 to $37,994 / $36,697 / $56,003 / $22,277. The S&P twin, 3x and index
   medians did not move.
2. `run_validate_live.py` prints the d-sensitivity of the fitted cash yield and the step-by-step CAGR decomposition of
   the v1 residual. New code: `validate.fixed_turns_structure`, `gap_decomposition`; the three steps sum to the total
   within 1e-6 on a planted case. F3 and F5 reworded: c is a residual conditional on d.
3. The passive study's caveat text no longer calls the pre-1988 yield assumed.
4. `tests/test_stats.py` anchors the built-in t table to the textbook quantiles without scipy and proves a wrong entry
   fails.
5. The identifier scan prints which categories the suite enforces and which it only reports, from one list the test
   reads too.
6. Nine FINDINGS slips corrected. Five are F6 degrees of freedom, F7 attribution, F9 trigger cells, F12 size of the
   CAGR move and F13 guppy_weekly shares. The other four are F14 era edge, F16 whipsaw bases, F17 +407%, and F19
   figures and the v1-scratch label. Two ASSUMPTIONS rows added (historical cost encodings; buy-once margin benchmark
   conventions). The fee-cap wording limited to what the filings evidence.

Golden files for `from_bottoms` (476 keys, the dollar blocks) and `validate_live` (99 new keys) re-frozen with the
reason; suite 919 checks, 0 failures.

**R2 step 7, 2026-10-24 (the fee page the re-grade asked for).** The re-grade held TRACEABLE because "cap binding,
evidenced to 2026-03-31" rested on a page nobody had read. This step read it. The FY2026 N-CSR shareholder report
gives realized expense ratios of 1.26 / 1.21 / 1.24% for the year to 2026-03-31. So the realized ratio fell below the
1.30% cap in that year's second half (implied average 1.22 / 1.12 / 1.18%).
- The validation fee path now follows the filings (section 2 of ASSUMPTIONS; `reference/nav_anchors.csv` corrected;
  tests pin the segments and their dates).
- Effect: window-2 fitted c falls 0.06-0.08 to 0.65 / 0.52 / 0.73. The invariant all-in financing rises 0.14-0.19 pp
  to 5.95 / 6.37 / 5.81% a year. The anchor gaps move by at most 0.14 pp. The window-1 decomposition and the
  one-month out-of-sample gaps move by 0.01 at most. Every historical number stays the same; F3 and F5 restated.
- Also, the re-grade's smaller points closed:
  - the register's old nominal split rewritten in CAGR terms;
  - "one-for-one" replaced by the measured slope;
  - the margin row names the encoding's rate turns;
  - t anchors at 18 degrees of freedom.
- `validate_live` re-frozen with the reason; suite 0 failures; fresh clone passes.

**R2 step 8, 2026-10-24 (prose pins; one fee source; the closure list against the exchange's record).** The
re-grade after step 7 found eleven cells of the F1 anchor table and four sentences still at their step-6 values. The
suite was green, because nothing tied the prose to the frozen JSON.
- Prose pins: `tests/test_prose_pins.py` with `tests/prose_pins.json` (72 pins) reads the numbers quoted in FINDINGS
  and ASSUMPTIONS. It compares them with the results JSON as printed. On its first run it failed 26 pins (10 of them
  older than step 7), all corrected here.
- One fee source: `scripts/run_validate_live.py` reads the filed ratios from `reference/nav_anchors.csv` and derives
  the second-half figure in code. Tests check the segments against the CSV and check that the script refuses broken
  rows. This also fixed MQQQ's first half of fiscal 2026, coded 1.31% where the N-CSRS says 1.30%. Window-2 c went
  0.502 -> 0.505; nothing else moved at two decimals.
- The closure list: this step checked the exchange calendar's one-off closures and rules against the exchange's own
  "History of New York Stock Exchange Holidays" and "Special Closings, 1885-date" (revised January 2011). All eight
  full-day closures 1970-2011 agree. ASSUMPTIONS quotes the Election Day and Saturday rules verbatim. The three later
  closures are consistent with the price data.
- `validate_live` re-frozen with the reason.

**R2 step 9, 2026-10-24 (the last named gaps).** The re-grade after step 8 gave EXACT A, PROVEN A, UNCERTAINTY A-,
TRACEABLE A- and named every remaining gap as fixable. Closed here:
1. The medians that lead F6 (the multi-start rows at 1 / 3 / 5 / 10 years) now carry their own interval. F8's
   rolling-1990 rows and F10's horizon curve carry none; their k would be 2. The interval is
   `stats.block_bootstrap_median`, a block bootstrap of the median with the same t(k-1) x SE rule. Its coverage is
   0.948 on iid normal and 0.955 on skewed data (400 runs each). `calendar_vs_daily` re-frozen for the 192 added
   keys; no existing number changed.
2. A simulation now measures the phase-pooled interval's coverage: 0.980 on 400 synthetic series with the real
   overlap structure of 120-month windows. So the interval is slightly wide, not short.
3. Three more prose pins (F2, F4; 75 in all). One of them found that F2's "3.1-4.3%" should read 3.0-4.3% (MQQQ
   3.05).
4. The two sentences that still blamed the window-2 residual on the fee cap now give the measured reason. It is fewer
   spread turns (1.84% -> 1.47% of NAV), offset by a lower cash yield; the fee itself fell. The swap-spread registry
   row now says that it is a default no published table uses. The banners no longer promise a sensitivity run that no
   script performs. The "exchange's notices" phrase is gone where none is on file. The two fee figures typed into a
   script's output now render from the CSV-read values.

Suite 1,053 checks, 0 failures; fresh clone passes.

**R2 step 10, 2026-10-24 (the headline interval).** The re-grade after step 9 found a bias at the headline
configuration (block = horizon: 6 blocks on the S&P, 3 on the Nasdaq-100). There the circular block bootstrap's
standard error is low by a third to a half. So its "95%" intervals cover only 0.86-0.94 on the project's own
synthetic overlap structure. The coverage tests shipped in step 3 used 12 blocks and could not see it.
- The suite now has a coverage test at the headline configuration. Coverage: mean 0.875 / 0.922 / 0.885 and median
  0.892 / 0.943 / 0.877 at k = 6, k = 3 and block 12. The bootstrap SE is 0.68 / 0.57 / 0.79 of the true standard
  deviation. The phase-pooled interval covers 0.980 / 0.998 / 0.955 on the same series.
- The phase-pooled interval from independent windows is now the headline interval and the only source of the "noisy"
  flag. The block-bootstrap mean and median intervals stay as secondary columns, labeled with their coverage. Draws
  rose to 10,000.
- Effect: the four rows that the block bootstrap called clear are noisy on the headline interval. They are NDX weekly
  mean and median at 10 years, MQQQ median at 10 years and SPX monthly mean at 1 year. No 10-year reset gap is
  distinguishable from zero on one history. NDX weekly at 1, 3 and 5 years is the only clear row at any horizon. F6
  restated.
- The prose-pin sweep that ran alongside added 83 pins against the three other results files (158 pins, 383 values).
  It found three more stale digits and corrected them: S&P twin drawdown -91%, the 2022 index 3-year return +91%, the
  -20% entry median +75%.
- `calendar_vs_daily` re-frozen with the reason: 528 keys added, 48 renamed. The block-bootstrap bounds moved by at
  most 0.05 pp with the draw count (0.04 at ten years), 0.12 for QQQP's median.
- Two validation-table headers that typed "fee 1.00%" now render the registry fee.

Suite 1,156 checks, 0 failures (160 prose pins); fresh clone 1,117 checks, PASS.

**R2 step 11, 2026-10-24 and 2026-10-25 (the gate re-grade after step 10 read EXACT A, PROVEN A-, UNCERTAINTY A-,
TRACEABLE A-).** Done on the first evening:
1. PROVEN: `phase_pooled_mean` has a plain-loop second implementation and a planted case with unequal phases (k = 3
   and 2), the shape the real data takes.
2. UNCERTAINTY: a coverage simulation at every published configuration (`scripts/run_coverage_sim.py`,
   `results/coverage_sim.md`). The suite recomputes three entries, bit for bit.
   - Under independent months the pooled interval covers 0.94-1.00. It is conservative at ten years (multiplier
     needed 2.23 / 2.34 against 2.57 / 4.30 used).
   - The block bootstrap's bias is a block-length effect (SE 0.83 of the truth with 201 blocks), not a few-blocks
     effect alone. The register now says so.
   - The limit of the headline interval is now a measurement, not an assumption. The measurement found the real gap series
     autocorrelated across non-overlapping windows for the S&P monthly design (+0.48 at 3 years, +0.54 at 10). The
     same holds for the S&P weekly design and MQQQ at 1-3 years. Under regime stresses of that size the pooled
     interval covers 0.42-0.91.
   - The register states that no noisy verdict can change. It also states that the only clear rows belong to the
     series with no measured persistence.
3. TRACEABLE:
   - Every results JSON carries a code fingerprint (SHA-256 over the package and its script, line endings
     normalized), and the suite recomputes it. So a results file rendered by older code fails the suite with the
     script to re-run.
   - `validate_live.md` re-rendered (its two typed fee headers were stale).
   - F7's 1.48 and 0.70 corrected to 1.47 and 0.69 against the JSON.
   - The README's episode count corrected (four Nasdaq-100 quarterly episodes, not three).

All four studies re-run; no published value moved (goldens unchanged). Suite 1,207 checks, 0 failures.

Done on the second day: the pin sweep, 237 pins. It added 77: F7 11, F10 3, F19 4, ASSUMPTIONS section 7 15, F6 and
this log 10, README 34. It found and corrected more stale README digits and F19's -22%. The README digits:
- the 2020 dollar figures $31,391 / $26,113 / $36,394;
- the 1987 and 2020 rows of the crash section;
- "ten times" to "about six times";
- the kernel time 1.2 s and the script run times.

Other changes on the second day:
- The README headline paragraph now carries the interval verdict.
- The README states its cost claim per design: 0.06 pp for the monthly and weekly designs, 0.15 for the quarterly
  ones. These figures are the span of the six 10-year medians in the sensitivity table, re-derived; F6 restated the
  same way.
- The README's drawdown sentence names the index (89-93% on the S&P 500, about 99% on the Nasdaq-100).
- The README's 200-day sentence quotes the one-run whole-era edge (-0.05 pp/yr) and the 50-day in- and
  out-of-sample edges (+4.8 / -10.2). These replace a scratch sub-era figure.
- F7's crossover values state their inputs: 0.97 / 0.90 at a round drift and volatility; 0.95 / 0.85 at the S&P's
  own moments.
- F10's v1 parenthesis now says that it is the v1 run.

Left as text, not pinnable:
- counts quoted from formatted strings in F19;
- the F7 correlations (-0.94 / -0.83 / -0.57, re-derived by hand);
- the test-sourced coverage figures in ASSUMPTIONS section 7 (iid and AR(1) data at n = 252).

Suite 1,284 checks, 0 failures; fresh clone PASS.

**R2 step 12, 2026-10-25 (the gate re-grade after step 11 read EXACT A, PROVEN A, UNCERTAINTY A-, TRACEABLE A-; the
named gaps and their closure).** UNCERTAINTY:
- The three clear rows (NDX weekly at 1, 3 and 5 years) now carry two labels in F6, ASSUMPTIONS section 7 and the
  README. The labels show the t ratios (2.34 / 2.75 / 2.93, new column `indep_t`) against two multipliers. One is the
  multiplier needed under independent windows (2.07 / 2.13 / 2.25). The other is the multiplier needed under the
  mildest regime stress run (3.07 / 2.92 / 2.95), which the measured persistence cannot rule out.
- The persistence claim is now a tested one. The test sets the measured lag-h autocorrelation against the iid
  simulation's own value, in units of 1 / sqrt(n / h). New columns: `acf_iid_expected` and `excess_se` in
  `results/coverage_sim.json`. Persistent for the S&P monthly design at 3 and 5 years (2.6 and 2.5 se); suggestive
  at 10 years (1.9). Undetermined elsewhere (within 1.3 se); on the independent value for SPYQ and the NDX weekly
  design (within 0.2 se).
- The Monte Carlo error sentence corrected (four seeds at 10,000 draws). At ten years the error is below 0.02 pp,
  except the Nasdaq-100 quarterly median: 0.09 pp, where t(2) = 4.30 amplifies the SE's noise. At 1-5 years it is up
  to 0.04 pp for that fund's means and 0.16 pp for its 3-year median.
- The nearest-case table in `results/coverage_sim.md` carries its caveat.
- The Nasdaq-100 coverage (1.00) now stands next to the S&P's (0.98).

TRACEABLE:
- A computed and pinned result replaces the typed v1 figure "10-14% of fund value" (README, ASSUMPTIONS section 6,
  the passive study's closing text). The result is the fill rule's effect on fund value per early-reset episode
  (`fill_effect_vs_level`, `study.fill_effects`). It is the change in the close- or next-close path's NAV relative to
  the level path, across a 70-session window that spans the episode. The ratio is constant between episodes, tested
  on a planted 36% fall. The effect runs from -16% (QQQP's 2000 episode at the close) to +27% (QQQP's 2008 episode at
  the next close). Both signs occur: a fill below the level carries 2x from a lower base; a fill after the rebound
  keeps the drifted leverage through it.
- The README's trigger sentence now says daily low.
- The script now computes the cost spans (`cost_span_10y_median`); F6 and the README pin them.
- Corrected: the README's "three studies" and its link to a file that is not public.
- `validate_live.json` carries a run date.
- The break case in `tests/test_validate.py` silences the expected numpy warning, so it fails only on the wrong error.

PROVEN: planted tests for `cost_span`, `fill_effect_range` and `fill_effects` (`tests/test_study.py`). All studies and
the coverage simulation re-run; `calendar_vs_daily` re-frozen for the added columns only (no existing value moved).
Left as text, not pinnable:
- the 0.09 pp Monte Carlo spread (a review measurement, not a results key);
- the "$900" and the "4 of 6 and 3 of 5" in the README's crash section (differences and counts of pinned values,
  checked by hand).

*Step 12b, the same evening.* The review of step 12 caught a defect in the new helper:
- For the next-close fill, the window opened on the fill day, one session after the trigger, when the level path had
  already reset. So three of the six next-close effects had the wrong sign, and the helper understated the maximum
  (+15% where +27% is right). The planted test could not see it, because it retyped the same formula.
- Fixed: the window opens the session before the TRIGGER day for every mode. Trigger days come from the level path;
  the helper records the mode's fill date beside it.
- The test is now a zero-cost closed form: a one-day fall from 100 to 64 and a rebound to 80. Close fill -4.2105%,
  next-close fill +36.842%, to 1e-12. It also exercises the two-triggers-within-the-window branch.
- The persistence test gained a calibrated form. A simulation gives the null distribution of the lag-h
  autocorrelation (4,000 iid series per configuration, `acf_null`). Each product's row carries the excess in null
  standard deviations and a one-sided Monte Carlo p-value. These sit next to the rule-of-thumb se, which proved
  1.2-3.3 times too wide.
- The typed "10-14%" clause in ASSUMPTIONS section 2 and the stale "Could not test" line at the end of this file are
  gone.

*Step 12c, 2026-10-25, later the same day.* The re-grade after 12b read EXACT A, PROVEN A, UNCERTAINTY A, TRACEABLE A-
on prose alone. Changes:
- The coverage script now computes the Monte Carlo error of the bootstrap bounds for all 24 rows over seeds 0-3
  (`bb_seed_spread`). The largest is 0.16 pp, the Nasdaq-100 quarterly median at 3 years; every row outside that fund
  is below 0.03 pp. A pin ties the register's sentence to it.
- F6 states the measured lower edge of the "undetermined" p-values (0.0485, the S&P weekly design at 5 years) instead
  of a rounded "at or above 0.05".
- The rule-of-thumb se is "1.2-3.3 times" the simulated SD, as measured.
- This step fixed a wrong section reference in ASSUMPTIONS section 2 and a duplicated no-op entry in the golden
  history. `refreeze_golden.py` now refuses a re-freeze that changes nothing.
- The fill-effect docstring says that the two paths carry different leverage until the next ordinary period end. It
  also says that the 70-session window is long enough, by design, to reach past it.

*Step 12d, 2026-10-25, evening.* A reviewer from a different model line re-graded after 12c (EXACT A, PROVEN A,
UNCERTAINTY A-, TRACEABLE A-). It found what the earlier passes had not looked at: the timing-rule study carried no
interval, noisy flag or mean.
- Now every multi-start row of `results/strategies.json` has the mean and the headline interval with its noisy flag.
  It pools the phases over non-overlapping 10-year windows, the passive study's convention. On it every
  rule's 10-year edge is noisy on both funds. MQQQ's 200-day means have the opposite sign to their medians (F13
  restated, pinned).
- The script now computes F14's sub-era split (`eras`, full-run edge per era: +5.29 / +6.91 / -8.37 for the S&P
  200-day rule). It replaces a v1 scratch figure. The script reports the out-of-sample window interval with its one
  degree of freedom.

Other corrections from that review:
- The README's residual sentence now states the R2 reading: the balance sheet explains the 1.40-1.74 pp/yr above the
  filed swap terms (F3).
- Pre-1988 S&P dividends now carry the label MEASURED (Shiller) in the three places that said "assumed".
- F13's rate move reads "at most 0.55 pp" (SPYQ trend_50d_sma) instead of "< 0.4".
- The three v1-trigger figures in F6 and F8 now carry the label "v1 run, not re-run".
- The coverage simulation has a golden file. The suite checks its raw-input hashes and its seed-0 bounds against the
  passive study. The README's run order is passive study, coverage, passive study again.
- The date of step 12c corrected.
- Reworded: "seven example rules", "up to 0.12 higher", the audits sentence, and two references to a private kit.

Suite 1,336 checks, 0 failures; 253 prose pins; fresh clone PASS.

*Step 12e, 2026-10-25, late evening (in progress).* The re-grade after 12d (A- on all four) found an input error:
- MQQQ's filed swap spread had the typed value 0.97% and the label VERIFIED. The shipped N-PORT extract gives
  0.9930% notional-weighted at 2026-06-30 (Clear Street 78.1m at 100 bp, Cowen 10.1m at 75, Wells Fargo 274.8m at
  100). SPYQ (0.9175%) and QQQP (0.9296%) were right to the second decimal.
- `validate.filed_spread` now READS the three spreads from the extract (planted test, break cases, and the three
  hand-weighted values in `tests/test_validate.py`). So a typed number can no longer stand in for a filed one.
- The validation re-fit moved MQQQ's cash yield from 0.91 to 0.92 in window 1 and from 0.50 to 0.52 in window 2. It
  also moved SPYQ's and QQQP's third decimals; no historical number moved.
- The 34 prose pins that read those digits failed, as they should. This step corrected the digits in F1, F1b, F3, F5
  and ASSUMPTIONS sections 2 and 6 to the re-fit.

Also in this step:
- Multi-start rows with fewer than three non-overlapping windows in the smallest phase now carry the flag
  `too_few_windows` and count as noisy. Eight Nasdaq-100 out-of-sample rows at delays 2-3 had read "clear" on one
  degree of freedom.
- The README's timing-rule sentence now reads "no reliable improvement" (vol_threshold's median is positive on both
  funds) and "the largest positive median".
- `data/README.md` says MEASURED for the pre-1988 Shiller yields.
- The unsourced "2-3%/yr" crisis-spread figure now carries the label: not re-derived here.
- F15's "+0.12 before 1990" now carries the label: a reading of F7.

The build log's steps 6-8 record fits made with the typed MQQQ spread; they stand as history. Second part,
2026-10-26:
- The F14 heading's "pre-2009 phenomenon" now rests on a test, `era_tests` in the strategies JSON. The test takes the
  daily log edge of the rule over passive, with Newey-West standard errors at Bartlett lags 21 / 63 / 252.
  `stats.newey_west_variance` has a hand-computed planted case, a plain-loop second implementation and a planted
  MA(1). The test gives z for the last two eras, and for all earlier history against the last. For the S&P 200-day
  rule, z = 1.6 at every lag between 1990-2008 and 2009-2026. So the heading now says that the difference is not
  distinguishable from chance.
- Script-level planted tests (`tests/test_run_strategies.py`) cover three functions:
  - `summarize_windows`: equality with the pooled interval with the NaN kept in place; the break case that drops
    them; the too-few flag.
  - `era_rows`: a piecewise-exponential path with exact per-era edges, the compounding identity, the boundary rows, a
    rule that starts after a boundary, an off-by-one break.
  - `era_tests`.
- A computed value replaces the typed "1.4-1.7 pp/yr" encoding gap (`study.encoding_gap`, tested): +1.21 to +1.28 on
  the S&P designs in 1966-82, -1.45 to -1.39 in 2009-15. ASSUMPTIONS section 2 pins it. The two scripts' closing
  texts render from it or drop the digits.
- F11's fund-minus-margin medians and F15's delay medians now carry the pooled interval (all noisy).
- The README's residual range is the whole-life figure from the current fit, pinned.
- ASSUMPTIONS section 5 now precedes section 6. The validate_live golden's duplicated history reason says what its
  second pass changed.

*Step 12f, 2026-10-26, evening.* A scoped re-grade after 12e checked the named gaps, a fresh sample and the new code.
It gave A- on all four; every gap was in prose or tests. Findings and fixes:
- Two register lines still carried the typed MQQQ spread. Fixed and pinned: 91.75 / 99.30 / 92.96 bp, range
  0.92-0.99%.
- The fit of window 1 used the 2026-06-30 counterparty mix, while the 2025-03-31 filing gives SPYQ 89.03 bp. So the
  validation now re-fits SPYQ's window 1 at that mix, and the register brackets its cash yield 0.866-0.878. This step
  did not read MQQQ's and QQQP's window-1 mixes.
- `era_difference_z` gained an exact hand case (2 / sqrt(0.46875)) and a plain-loop second implementation. A test
  checks `era_tests` for equality with hand-sliced edges.
- F14's heading now ties z 1.6 to 1990-2008 against 2009-2026. It states that the pre- against post-2009 z of 1.9-2.7
  rests on a boundary chosen after a look at the data. A break test with a data-chosen date needs a larger critical
  value (Andrews 1993, cited from memory).
- F11's survivor medians and Nasdaq-100 rows carry phase-pooled intervals, all noisy, and its heading says so. For the
  survivors, finished windows stay out of their phases.
- The README names the largest median per fund: SPYQ 200-day +4.0; MQQQ and QQQP volatility threshold +2.3 and +5.9.
- The k_min < 3 policy is in the ASSUMPTIONS section 7 register.
- README notes: "beat the monthly design in every decade" (the weekly design won the 1950s); the nine other Tradr
  funds and their two launch dates.
- F7's sentence on the decade signs states the two barely positive decades.
- `encoding_gap` gained a second-route test.

Suite 1,387 checks, 0 failures; 266 prose pins; fresh clone PASS.

*Step 12g, 2026-10-26, evening.* The scoped re-grade after 12f (EXACT A-, PROVEN A-, UNCERTAINTY A, TRACEABLE A-) found
two faults in 12f's SPYQ "bracket" of window 1's cash yield. It was not a bound: a 2025-06-30 snapshot with Wells
Fargo as a third counterparty falls outside it. And it rested on typed 2025-03-31 notionals. Both are gone.
- Re-fits at the smallest and largest spread that any filed swap carries now bound window 1's c for all three funds.
  `validate.filed_spread_range` reads these spreads from the extract: 75 and 100 bp. `validate.cash_yield_at_spreads`
  does the re-fits; `tests/test_validate.py` checks its planted identity, the bound direction and the closed-form
  size. The bounds: SPYQ 0.802-0.915, MQQQ 0.813-0.925, QQQP 0.842-0.956. F3 (vi) and ASSUMPTIONS section 6 pin
  them; `results/validate_live.md` renders them.
- The survivor interval of F11 gained a planted test with two crashes six months apart. So the finished block of 18
  starts is not a multiple of the 12-month step. The test checks equality with the pooled interval with NaN in
  place. Its break case drops the finished windows first.
- Open, not blocking: the window-1 N-PORTs of the three funds would narrow the bounds. They are public; R2 step 2
  read them for notionals, not for spreads.

*Step 12h, the same evening.* The scoped re-grade after 12g gave EXACT A-, PROVEN A-, UNCERTAINTY A, TRACEABLE A-. The
reviewer re-derived all six bounds by a second route to 1e-5. The re-grade named four small items, now closed:
- The window-1 bound cites its own source for window 1, the N-CSR to 2025-03-31. That report lists Cowen at OBFR01
  + 75 bp and Clear Street and Wells Fargo at + 100 bp. The docstring and comments say the bound holds if every swap
  carries a filed term.
- The 2026-06-30 mix is the latest snapshot in the extract, not the earliest.
- The validation's input manifest now fingerprints the N-PORT extract, and its provenance holds the spread bounds.
- The bound sentence in `results/validate_live.md` sits below each table and no longer splits it.
- Tests now run `filed_spread_range` on an extract whose extremes sit in a later snapshot and a second fund, and on an
  unreadable pay leg.

Still open, a note not a gap: F3 (ii), F5 and ASSUMPTIONS section 2 quote window-1 c 0.88-0.92 without its bound.
F3 (vi) and ASSUMPTIONS section 6 carry it.

*Steps 12i-12j and the code review (R3), 2026-10-26, late evening.* Two scoped re-grades closed the last items:
- The spread-range test now kills a latest-snapshot-only version (a middle-snapshot extreme).
- ASSUMPTIONS section 6 cites the window-1 source.
- The episode guard in `fill_effects` became a pure function, `study.match_fills`. Its tests use planted row numbers:
  early fills, a period-end fill, no fill, an unmatched reset, a late reset, a reset used once. They also cover the
  order of the two fill kinds, the search bounds, and the window that opens the session before the trigger. Two
  planted worlds test it too. In the first, a next-close fill on an ordinary quarter end comes out aligned, with the
  closed-form +36.842%. In the second, a second fall triggers the next-close path but not the level path; it comes
  out misaligned and stays out of the range.
- Every mutant of the guard that the review wrote fails the suite.

The code review of the package and scripts (eight findings) led to four fixes:
- one pay-leg parser that accepts only an OBFR01 leg, shared by `filed_spread` and `filed_spread_range`;
- a half-life of 0 instead of a math error for a regime with no persistence;
- `summarize_windows` refuses a mask that is not one unbroken run of starts;
- the episode guard above.

No published value moved.

*Step 12k and the gate, 2026-10-26.* Three more checks pin the last edges of `match_fills`:
- an early fill 5 sessions after the trigger counts, and 6 does not;
- an unmatched reset on the window's last row misaligns, and one row after does not;
- a reset two sessions before the trigger is outside the window.

Every one of 27 mutants of the guard fails the suite. **Engine grade after the final independent audit: EXACT A,
PROVEN A, UNCERTAINTY A, TRACEABLE A. The engine meets the release gate (A on all four).**

*R4 release-wording pass, 2026-10-26.*
- British spellings changed to American across code, prose, prose-pin anchors and key paths, and golden keys (269
  replacements).
- The identifier scan's British list now counts the -ise verbs only, so "optimistic" and "realistic" pass.
- Model and vendor names removed from this build log (each audit is "an independent audit").
- Neutral descriptions replaced the names of private sibling folders.
- A jurisdiction reference removed from the README.
- CHANGELOG.md and CITATION.cff added.
- The suite now enforces the identifier scan's release tier (0 problems in 93 public files).

*R4 plain-English pass, 2026-10-26.* The ASD-STE100 lint (`scripts/ste_check.py`) finds 0 problems in README,
FINDINGS, ASSUMPTIONS and data/README. The Guppy state name is "gray" in the code, tests, golden keys and results.

*R4 addition, 2026-10-26.* The GFC oracle entry (F21): `scripts/run_gfc_oracle.py`, `tests/test_gfc_oracle.py` and a
golden file. The test reads the raw price files with the csv module, a second route to the entry dates and the real-fund
and index dollars.

*R4 audit of the addition, 2026-10-27.* An independent audit graded the study EXACT B, PROVEN C, UNCERTAINTY C,
TRACEABLE B. The fixes:
- The README and F21 now show both cost encodings. F21 states that the comparison with the real funds measures the
  assumed costs.
- The leverage sentence was wrong: the extra exposure lasts only until the index regains its last reset level. F21
  now names QQQP's early reset on the next session.
- F21 no longer claims without a source that the real funds cost less. It compares the twins with the real funds.
- `tests/run_tests.py` now restores the environment after each test module. `tests/test_data.py` had removed the data
  variables, so the second route skipped in the full suite.
- New: early-reset counts, an entry-shift table, a cost banner and a leverage cross-check with
  `results/from_bottoms.json`. Raw-file routes now check the launch rows, the end date and QQQP's trigger day.
- Nine planted bugs now each fail the suite, among them all three that passed the audit's mutation test.

A scoped re-check graded the study EXACT A, PROVEN B, UNCERTAINTY B, TRACEABLE B. It found two new defects, now fixed:
- The strict second route failed on any data other than the published files, so a routine top-up turned the suite red.
  The route now runs only on files whose sha256 matches the results manifest, and a skip names the file and the reason.
- The entry-shift grid skipped -2 and -1, and QQQP also trails its twin at -2. The grid now holds every session from
  -10 to +21. The results publish its summary only, because one lead per session is a daily series.

The re-check's PROVEN gaps are closed too. Plain loops rebuild the Nasdaq-100 total-return index and both 3x models
from the raw files. They match the published rows.

## Results

### S2: model against the live funds and the issuer's NAV figures (R2 step 2, 2026-10-24; `scripts/run_validate_live.py`, `results/validate_live.{json,md}`)
Settings of the run:
- Data: fund and ETF closes and lows from the TradingView library (split-adjusted, no payouts) to 2026-10-09. Fund
  payouts come from `reference/distributions.csv`. SPY / QQQ dividends come from `reference/etf_distributions.csv`
  (SECONDARY, vendor history; the latest row agrees with a second vendor). FRED OBFR and DFF run to 2026-10-08.
- NAV anchors: `reference/nav_anchors.csv` (filings: semi-annual report to 2024-09-30, N-CSR FY2025 and FY2026,
  prospectus 2026-07-31).
- Start: the model runs from each fund's inception close (SPYQ / QQQP 2024-09-30, MQQQ 2024-08-30).
- Fee timeline: 1.30% to 2025-09-30, filed, MQQQ 1.31% to 2025-03-31 and 1.30% after; then 1.22 / 1.12 / 1.18% to
  2026-03-31. The filed FY2026 ratios 1.26 / 1.21 / 1.24% and the filed first half give these values. Then 1.00 /
  1.03 / 1.00% from 2026-04-01, an ASSUMED start.
- Underlying: the ETF's own total return.
- Financing: the filed spread per fund over OBFR, ACT/360.
- Trigger: price trigger, level mode.

The deepest in-period fall of SPY or QQQ since a reset was -11.3% on a close and -14.2% on a low (2025-04-07/08). So
the -35% trigger never came near, and the three early-reset modes are identical. Fund PRICES stand in for NAVs except
where an anchor is the issuer's NAV figure.

**F1. The fund series are right, and so are the model's levels against the issuer's own NAV figures.** Price +
payouts reproduces the published NAV returns where both exist:
- calendar 2025 SPYQ 26.22% against 26.23%, MQQQ 31.65% against 31.50% (its $3.66 December payout is 1.5% of
  price), QQQP 30.21% against 30.24%;
- fiscal 2026 (2025-03-31 to 2026-03-31) 26.48% against 26.49%, 39.33% against 39.19%, 38.17% against 37.94%.

The table compares the model with every PRIMARY anchor. The model starts from the inception close and needs no fund
price at all. Each cell shows model minus anchor (pp) for the structural encoding with the fitted cash yield / with
the derived prior c = 0.8 / v1 fixed 2.6%.
| Anchor (NAV total return) | SPYQ | MQQQ | QQQP |
|---|---|---|---|
| inception to 2025-03-31 (N-CSR FY2025: -8.08 / -7.90 / -12.04%) | +0.08 / -0.09 / +0.12 | -0.04 / -0.35 / -0.03 | +0.12 / -0.14 / +0.08 |
| calendar 2025 (prospectus 2026-07-31: 26.23 / 31.50 / 30.24%) | +0.08 / -0.11 / +0.11 | +0.13 / -0.17 / +0.19 | +0.20 / -0.24 / +0.01 |
| 2025-03-31 to 2026-03-31 (N-CSR FY2026: 26.49 / 39.19 / 37.94%) | -0.13 / -0.10 / -0.18 | -0.22 / -0.12 / -0.11 | -0.06 / -0.24 / -0.35 |
| one month 2024-08-30 to 2024-09-30 (semi-annual: MQQQ 4.56%) | | -0.08 / -0.13 / -0.07 | |
Every gap is inside 0.35 pp of a 6- to 12-month return; the prior with nothing fitted is inside 0.35 pp. The
inception-dated anchors are the cleanest test: no fund price enters them.

**F1b. Out of sample: the liquidated SPY-monthly, SPY-weekly and QQQ-weekly funds.** SPYM, SPYB and QQQW (the designs
the registry now calls MODELED) traded 2024-08-30 to 2025-02-28. Their one published NAV figure is the month to
2024-09-30 (semi-annual report, PRIMARY): +3.48 / +3.12 / +3.84%. The model runs from the 2024-08-30 close at the live
funds' window-1 terms:
- fee 1.30%;
- swaps 2.0 x NAV at the filed spread of the live fund on the same ETF;
- cash 1.0 x NAV at c = 0.908, the mean of the three live funds' window-1 fits.

Results (nothing fitted on these funds): **+3.45 / +3.10 / +3.76%, gaps -0.03 / -0.02 / -0.08 pp**. At c = 0.8 the
gaps are -0.08 / -0.07 / -0.13; at c = 1.0, +0.01 / +0.02 / -0.04. The weekly funds reset four times inside the
month. The same model on the v1 ETF total-return construction (ETF price x index TR / price ratio) misses by -0.44 /
-0.43 / -0.23 pp. That construction mistimes the ETF's September ex-dividend. The ex-dividend falls inside a month
that starts with two months of accrued dividend in the ETF's price.

Over whole quarters the two constructions agree to 0.01-0.08 pp (table column "ETF TR own - index basis"). That is
why none of the other anchors moved. The ETF's own dividends are now the model's underlying. The liquidation values
(QQQW 30.2606, SPYM 28.3384 per share, paid 2025-03-04) are SECONDARY; the study shows them but does not use them.

**F2. The model's PATH is right; price and NAV are close enough to fit on.** Daily correlation is 0.995-0.998 over
the whole life (0.991-0.994 in window 2 for the quarterly funds). Tracking error is 3.0-4.3%/yr whole life (SPYQ
3.28, MQQQ 3.05, QQQP 4.27), mostly bid-ask noise on funds that trade a few thousand shares a day.

The N-CSR FY2025 bounds the difference between price and NAV. Its market-price returns are -8.12 / -7.94 / -12.12% against NAV
returns of -8.08 / -7.90 / -12.04%, a difference of 0.04-0.08 pp over six to seven months. The fiscal-2026 anchors
show 0.01 / 0.14 / 0.23 pp. So a fit on prices can be off by about 0.1-0.2 pp/yr from a fit on NAVs, which is below
every residual discussed in F3.

**F3. The cost structure, read from the filings and fitted in two windows.** The filings (ASSUMPTIONS sections 2
and 6) give these terms:
- The expense cap 1.30% binds from inception to 2025-09-30 (MQQQ 1.31% to 2025-03-31 with excise tax, then 1.30%;
  N-CSR FY2025 and N-CSRS to 2025-09-30).
- Fiscal 2026 as a whole has a realized 1.26 / 1.21 / 1.24% (N-CSR FY2026 shareholder report, read after the final
  audit asked for the page). So the realized ratio fell below the cap in the second half of FY2026 (implied average
  1.22 / 1.12 / 1.18%). This average is exact only if average assets were equal in the two halves. The bound is
  0.05 pp on that half-year fee and 0.012 on c.
- Then the 1.00-1.03% of the 2026 prospectus applies.
- The funds hold all cash plus swaps of about 2x NAV to mid-2025. Then they hold about 0.4 NAV in the ETF itself plus
  swaps for the rest (N-PORT 2025-09-30).
- The swaps charge OBFR + 75 / 100 bp (weighted 0.92-0.99%), and the fund receives the ETF's total return.

The kernel takes these terms as inputs, with the balance sheet at a reset. The swaps are s = 2 - d, the cash is k =
1 - d, and the cash earns c x OBFR. So net financing = (s - k c) x OBFR + s x spread. Nobody files one number, c. The
study fits it by bisection on the CAGR gap per fund per window (fee timeline on, ETF's own total return, filed
spread):
| | SPYQ | MQQQ | QQQP |
|---|---|---|---|
| window 1 (inception to 2025-09-30, d = 0): fitted c | 0.878 | 0.922 | 0.924 |
| rate turns s - k c | 1.12 | 1.08 | 1.08 |
| gap at the derived prior c = 0.8 / at c = 1.0 (pp/yr) | -0.42 / +0.66 | -0.80 / +0.51 | -0.73 / +0.45 |
| window 2 (2025-09-30 to 2026-10-09, d = 0.4): fitted c | 0.653 | 0.521 | 0.727 |
| rate turns s - k c | 1.21 | 1.29 | 1.16 |
| gap at c = 0.8 / at c = 1.0 | +0.40 / +0.95 | +0.86 / +1.49 | +0.22 / +0.81 |
| window 2, c with the FY2026 average fee held to 2026-07-31 (fee-path sensitivity) | 0.700 | 0.566 | 0.775 |
| v1 filed structure (1.5 turns, fee 1.00%), gap window 1 / window 2 | +1.61 / +1.21 | +1.66 / +1.69 | +1.49 / +1.07 |
| v1 fixed 2.6% of NAV (fee 1.00%), gap window 1 / window 2 | +0.10 / -0.30 | +0.01 / +0.14 | -0.13 / -0.54 |
| v1 rate 1.4% + 1.3 turns (fee 1.00%), gap window 1 / window 2 | -0.05 / -0.19 | -0.19 / +0.26 | -0.29 / -0.43 |

Reading:
- (i) The filings explain the 2026-10-12 residual of 1.40-1.74 pp/yr against the filed 1.5-turn structure; it is not
  mysterious. The R2 audit ran the kernel step by step from the v1 filed structure (SPYQ, window 1, CAGR terms):
  - the fee cap 1.00 -> 1.30% closes +0.38 pp/yr;
  - spread turns 1.5 -> 2.0 at 0.92% close +0.57;
  - rate turns 1.0 -> 1.12 (the cash yield) close +0.66;
  - the total is +1.61, against the published v1-filed gap +1.61.

  The nominal items are 0.30 + 0.46 + 0.53 pp of NAV a year. Each shows up about 1.25x in CAGR because the fund
  gained about 25% in the window.
- (ii) c is a RESIDUAL conditional on the assumed direct holding d, not a measured deposit rate. In window 1 (d = 0,
  nothing else to absorb) the fit c = 0.88-0.92 against the N-CSR income prior of 0.80 is a fair measurement. In
  window 2 the fitted c moves with d. The fitted values are (d = 0.3 / 0.4 / 0.5 / 0.6: SPYQ 0.74 / 0.65 / 0.53 /
  0.36, MQQQ 0.63 / 0.52 / 0.37 / 0.15, QQQP 0.80 / 0.73 / 0.62 / 0.47). The slope is -1.1 to -1.6 of c per unit of
  d.

  Across d, the invariant is the all-in financing per NAV, 5.95 / 6.37 / 5.81% a year at a mean lagged OBFR of 3.71%
  (`results/validate_live.md`, d-sensitivity table). At the 2026 snapshots' d of 0.4-0.6 the implied yield is 15-73%
  of OBFR, which is not a deposit rate. So c also absorbs whether financing accrues on the printed notional or the
  exposure, the fee-switch date and the price-to-NAV term.
- (iii) The R1 memo predicted that the residual would fall by about 1 pp/yr after the structure change. That did NOT
  come true. The all-in cost beyond the fee stayed about the same (the v1 fixed encoding stays within -0.5 to +0.3
  pp/yr in both windows). Fewer spread turns cut cost (1.84% -> 1.47% of NAV a year), but a lower cash yield offset
  that (equivalently, more rate turns: 1.08-1.12 then 1.16-1.29). So the financing beyond 1.0 x OBFR fell only from
  about 2.36% to 2.24% of NAV for SPYQ. The fee itself fell from 1.30% to 1.22-1.00% in window 2, which is most of the
  -0.30 pp the fixed encoding shows there.
- (iv) The N-PORT period-end notionals as printed are swaps 2.2 then 1.3 x NAV and cash 1.0 then 0.45. With these
  inputs fed in, the fit gives c = 1.12-1.17 in window 1 (cash earning more than OBFR) and -0.15 to 0.14 in window 2.
  These values are not credible. The kernel already fixes the notional at each reset and lets it drift, so a run
  must not feed in a snapshot's drifted notional twice. Also, at 2025-09-30, a reset date, printed notional 1.32 +
  direct 0.40 = 1.72 < 2; the swaps' unrealized appreciation is the rest. Whether the financing leg accrues on the
  printed notional or the full exposure is OPEN.
- (v) OBFR against DFF: 0.0-0.2 bp apart on average over the windows, 0.00 pp/yr on any gap.
- (vi) A 10 bp change in the assumed spread moves c by about 0.05. The fit for window 1 uses the 2026-06-30
  counterparty mix, the latest snapshot in the extract. The study does not read window 1's own mix for spreads (the
  N-CSR to 2025-03-31 shows the same two terms inside window 1). So its c has bounds from re-fits at the two filed
  extremes, 75 and 100 bp: SPYQ 0.802-0.915, MQQQ 0.813-0.925, QQQP 0.842-0.956 (R2 step 12g).

  Holding the FY2026 average fee to 2026-07-31 instead of the derived second-half path moves window-2 c by +0.05.
  The R2 step-6 run still assumed the 1.30% cap through window 2. It had c 0.06-0.09 higher (0.72 / 0.59 / 0.80 at
  two decimals; the step-6 JSON no longer exists) and the all-in financing 0.14-0.19 pp lower. The fee and the
  cash yield trade off inside the same residual.

**F4. The product keeps its promise per period, less a constant cost (unchanged).** The regression of fund return
on ETF return uses full periods: SPYQ 7 quarters, MQQQ 24 months, QQQP 7 quarters. On the price basis the slope is
**2.015 / 1.993 / 2.005** and R² is 1.000. The intercept is **-1.33 pp per quarter / -0.55 pp per month / -1.59 pp
per quarter**. On the ETF's own total return the slopes are 2.012 / 1.998 / 2.004 and the intercepts -1.90 / -0.64 /
-1.84 pp: the all-in cost per period.

The plain ratio fund/ETF (median 1.9, range 1.3-2.5 after the 1% / 3%
small-move filter) swings only because a variable move divides a near-constant cost.

**F5. The model convention (decision, restated).** For 2024-26 the sourced reading is the structural one (ASSUMPTIONS
sections 2 and 6). It has the fee timeline, the at-reset balance sheet and the filed spread. It has a cash yield c =
0.88-0.92 in window 1, then a residual c = 0.52-0.73 at d = 0.4 (0.15-0.80 across d = 0.3-0.6).

For history nothing changes. The two v1 encodings (fixed 2.6% of NAV; filed 1.4% + 1.3 rate turns, each at the
product's steady-state fee) stay side by side by regime. The reason: they still bracket both windows within 0.5
pp/yr, and no source measures the structural inputs (direct holding, cash yield) before 2024. The underlying for
validation runs is the ETF's own total return; the index-ratio construction is a cross-check only (F1b). The study
no longer reports the price-basis run.

Could not test:
- the 35% trigger (it never fired; the deepest in-period fall was -14.2% on a low);
- the funds' daily NAVs (the fit uses prices; the N-CSR bounds the difference at 0.04-0.23 pp over 6-12 months);
- the fee inside the second half of fiscal 2026. The value is a plain 6 + 6 month average of two filed ratios. The
  filed ratio weights by assets, and MQQQ's assets fell from 165m to 102m in that half, so its 1.12% is the least
  certain. The exact second-half ratio is FY + (FY - first half) x (183 A1)/(182 A2), with A1, A2 the half-year
  average assets. For an A1/A2 ratio between 0.67 and 1.5 the fee lies within 0.05 pp of the derived value, which
  moves c by at most 0.012. Sensitivity: the FY2026 average held to 2026-07-31 moves c by +0.05;
- the start date of the 1.00-1.03% fee (ASSUMED 2026-04-01);
- whether swap financing accrues on the printed notional or on the exposure;
- the liquidated funds beyond their first month (no daily prices: tickers reused or retired; liquidation values
  SECONDARY);
- SOXX, NVDA, TSLA and TLT funds (underlyings not in the kit);
- crisis financing spreads.

### S3: calendar reset against daily reset, the passive study (2026-10-12; re-run 2026-10-24 after R2; `scripts/run_calendar_vs_daily.py`, `results/calendar_vs_daily.{md,json}`)
Settings for every number unless stated:
- Index data: S&P 500 total return 1950-01-03 to 2026-10-22 (Shiller's MEASURED monthly dividend yield before 1988,
  B7). Nasdaq-100 total return 1985-01-31 to 2026-10-09 (0.3% yield before 2006, ASSUMED).
- Rates: reference rate DFF lagged (TB3MS proxy before 1954-07); financing legs on ACT/360 and the fee on 365 (R2).
- Reset dates: from the NYSE session calendar (R2).
- Early-reset trigger: it watches the ETF's price (its daily low) from the ETF's first bar (SPY 1993-01-29, QQQ
  1999-03-10) and the index price before that. Drop 35%, fill at the level (R2; v1 watched the index close).
- Costs: both cost encodings of F5 (fixed 2.6% of NAV; filed 1.4% + 1.3 rate turns), both ASSUMED. Each calendar
  product runs against its daily twin at identical costs.
- Margin benchmark: the buy-once position's loan compounds daily (R2).
- Starts: every month-end with a full horizon ahead. "gap" = calendar CAGR minus twin CAGR in pp/yr.
- Intervals: the headline interval is the phase-pooled one from independent windows, mean +/- t(df) x SE, and it
  alone sets the "noisy" flag. Block-bootstrap intervals (block = horizon, 10,000 draws) are secondary: with block =
  window length their standard error has a low bias (ASSUMPTIONS section 7; R2 steps 10-11).

Every series is synthetic. The SPYQ / MQQQ / QQQP series model the live funds. The other products are designs that
the registry calls MODELED; their live funds traded 2024-08-30 to 2025-02-28 (F1b). What the R2 re-run moved and why:
- ACT/360 took about 0.1 pp/yr off every 2x CAGR and left the reset gaps within 0.01 pp.
- The exchange calendar changed nothing on these files.
- The compounding loan moved only the margin benchmark (F11).
- The ETF-price intraday trigger moved only the quarterly products, and QQQP by a large amount (F9).

Each study's JSON carries the sha256 of every input file.

**F6. Ten-year answer, with intervals: monthly and weekly resets beat daily by a little on the S&P 500 and by more
on the Nasdaq-100. But on one history none of the six ten-year gaps is distinguishable from zero. Quarterly does not
beat daily on the S&P, and on the Nasdaq-100 its sign depends on one day in 2008.** Median 10-year gap (fixed | rate
encoding; share of starts the calendar fund wins):
- SPYQ **-0.54 | -0.59 pp (44%)**, SPX monthly +0.29 | +0.29 (58%), SPX weekly +0.28 | +0.28 (68%), over 801 starts
  1950-2016;
- MQQQ **+1.36 | +1.35 (91%)**, QQQP **-2.10 | -2.13 (30%)**, NDX weekly +1.13 | +1.14 (96%), over 381 starts
  1985-2016.

Mean and 95% interval (phase-pooled from independent windows, the headline; ASSUMPTIONS section 7), fixed encoding:
- SPYQ -0.68 [-1.90, +0.54]; SPX monthly +0.38 [-0.59, +1.34]; SPX weekly +0.19 [-0.36, +0.74];
- MQQQ +1.02 [-2.34, +4.37]; QQQP -2.44 [-10.77, +5.89]; NDX weekly +1.16 [-0.26, +2.58].

**All six cover zero.** The interval uses t with 5 degrees of freedom on the S&P and 2 on the Nasdaq-100 (3-7
independent windows per phase). Its simulated coverage on this overlap structure is 0.98 on the S&P and 1.00 on the
Nasdaq-100, so it is wide rather than short. That coverage takes windows that do not overlap as independent.

The S&P monthly gap series contradicts that at 3, 5 and 10 years (autocorrelation across such windows +0.48 / +0.58 /
+0.54). That is 3.4 / 3.5 / 3.2 standard deviations above what independent months give. The one-sided Monte Carlo p
is 0.0005 at 3 years, and no draw of 4,000 is as high at 5 and 10 years. So its intervals are too short by an amount
one history cannot fix. That error cannot turn a noisy row clear.

MQQQ at 10 years is borderline (p 0.01 on three windows per phase). Everywhere else p runs from 0.0485 to 0.76. The
low end is the S&P weekly design at 5 years: one of 24 rows screened, and noisy on the headline interval regardless.
SPYQ and the Nasdaq-100 weekly series sit on the independent value (ASSUMPTIONS section 7, R2 steps 11-12).

Block-bootstrap intervals (10,000 draws, block = horizon) are secondary, because with block = window length their
standard error runs 0.57-0.84 of the truth at the published configurations. The ratio is 0.83 even with 201 blocks,
and their coverage is 0.86-0.94 (results/coverage_sim.md). Their intervals read:
- mean SPYQ [-1.49, +0.14], SPX monthly [-0.42, +1.18], SPX weekly [-0.24, +0.62], MQQQ [-0.55, +2.50], QQQP [-7.03,
  +2.10], NDX weekly [+0.38, +1.93];
- median SPYQ [-2.21, +1.14], SPX monthly [-0.85, +1.42], SPX weekly [-0.28, +0.83], MQQQ [+0.21, +2.50], QQQP
  [-9.90, +5.71], NDX weekly [+0.35, +1.91].

On those secondary intervals NDX weekly (mean and median) and MQQQ (median) would read as clear at 10 years. The
headline interval does not support that. With three blocks on the Nasdaq-100, a reader should not take a bootstrap
clearance as a finding.

MQQQ's mean (+0.98 over all starts, +1.02 phase-pooled) sits well below its median (+1.36). The gaps have a skew, so
the median flatters the calendar side. At shorter horizons, NDX weekly at 1, 3 and 5 years (+1.05 [+0.14, +1.95];
+1.06 [+0.21, +1.91]; +1.10 [+0.18, +2.02]) are the only clear rows. That holds on the headline interval, and these
rows carry two labels:
- clear under independent windows (t ratios 2.34 / 2.75 / 2.93, where independent windows need 2.07 / 2.13 / 2.25);
- noisy under the mildest regime stress the project ran (a 2% persistent share with a 34-month half-life needs 3.07 /
  2.92 / 2.95). This history cannot rule out that stress: the series' autocorrelation across non-overlapping windows
  sits within 0.2 se of the independent case.

SPX monthly at 1 year (+0.30 [-0.03, +0.63]) is noisy by a hair, where the block bootstrap had read [+0.03, +0.57].
Independent-window phases (120 phases of 6-7 windows on the S&P, 3-4 on the Nasdaq-100) give this picture:
- S&P monthly wins a majority of its windows in 87% of phases, median win share 57%, no phase all-positive;
- weekly 90% / 71%; SPYQ 11% / 43%;
- MQQQ every phase a majority, 72% all-positive; NDX weekly 100% / 86%;
- QQQP 15% / 33% (48% / 50% in the v1 run with the index-close trigger, not re-run).

The cost encoding and its sensitivities (1.4% / 3.5%; 1.0 / 1.5 turns) move the monthly and weekly gaps on the S&P by
at most 0.02 pp. They move the Nasdaq-100 weekly design by 0.02, MQQQ by 0.06, SPYQ by 0.15 and QQQP by 0.05. These
are the spans of the six 10-year medians in the sensitivity table. Also, the fill mode moves SPYQ by 0.3 pp
(next_close -0.29), and the trigger basis moves QQQP by 2.4 pp (F9). So:
- the S&P +0.3 pp is a modest edge that a coin could mimic;
- the Nasdaq-100 monthly and weekly medians are large and consistent across phases, but their means are not
  distinguishable from zero on 3-4 independent decades;
- the Nasdaq-100 quarterly gap is negative on the prospectus-faithful reading (the ETF's price, intraday, 35%: -2.10
  pp, 30% of starts). It is not distinguishable from zero on one history, and it is reversible by the fill
  assumption (next_close +0.09) and by one 2008 day.

**F7. For monthly and weekly resets the sign follows the index's day-to-day autocorrelation (C2 confirmed, with
corrections). The formula behind it is Bessembinder's second-order expansion. The decade regime is weaker as evidence
than the correlation suggests. Quarterly follows the market's level.**

Decades with clearly positive lag-1 autocorrelation of daily returns (the 1950s-70s) favored the daily twin. The two barely positive ones (1980s, 1990s)
and the three negative ones favored the calendar fund. For the 1950s to 2020s:
- SPX autocorrelation +0.09 / +0.15 / +0.25 / +0.05 / +0.02 / -0.09 / -0.05 / -0.16 (standard error 0.02 each);
- SPX monthly gap -0.21 / -0.49 / -0.73 / +0.37 / +0.18 / +1.84 / +0.74 / +1.53 pp.

Correlation across the 8 decades -0.94 (monthly), -0.83 (weekly), -0.57 (SPYQ): descriptive, eight points. The
tested statement (R2, `stats.variance_ratio`, Lo-MacKinlay robust z) reads:
- The S&P's 21-day variance ratio differs from 1 at the 5% level only in the 1960s (1.47, z +2.8) and the 1970s
  (1.41, z +3.0). The reversal decades since 2000 read 0.69-0.77 with z -0.7 to -1.9.
- VR(5) is significant in three decades (1960s, 1970s, 2000s) and VR(63) in none.
- The full sample VR(21) is 0.895 (z -1.3) on the S&P and 0.820 (z -2.0) on the Nasdaq-100.

The formula gives E[calendar - daily] per period = -2 [C(T,2) mu^2 + T sigma^2/2 (VR_T - 1)]. So the calendar fund
leads when VR_T < 1 - (T-1) mu^2/sigma^2. The bound is about 0.97 for a month and 0.90 for a quarter at a round daily
drift of 0.04% and volatility of 1%. It is 0.95 and 0.85 at the S&P's full-sample moments (mean 0.049% and standard
deviation 0.99% a day). This prediction matches the realized sign in 8 of 8 S&P decades for monthly, 6 of 8 for
weekly and 5 of 8 for quarterly.

The quarterly 2000s miss (predicted +1.70, realized -1.86) is the 2008-11-20 trigger episode, which the formula does
not contain. On the Nasdaq-100 the prediction matches 4 of 5 decades for MQQQ and for QQQP. With zero autocorrelation
the daily fund leads by the drift term alone: about 0.08 pp/yr for a monthly reset and 0.25 for a quarterly one. That
is why a quarter needs a strongly reverting market to win. It is also why quarterly's gap follows the window's 1x
return more than the autocorrelation (+0.60 on 5-year blocks, auditor scratch 2026-10-12, not re-run).

Summitward's "daily won every decade before 2000" is wrong for the 1980s and 1990s, which were already positive for
monthly and weekly. The post-1990 result is a regime, not a law. The only decades whose 21-day variance ratio differs
from 1 at 5% are the continuation decades of the 1960s and 1970s. No reversal decade since 1990 reaches 5% at VR(21)
(the 2000s do at VR(5)).

**F8. C1 replicated (unchanged by R2).** Rolling 10-year windows from 1990-01-31 (321 windows), SPX monthly against
its twin: +1.14 pp at zero costs, +1.16 (fixed), +1.15 (rate), 321/321 wins. Earlier runs agree (scratch: +1.13,
321/321; Summitward: +1.15, 317/317). Weekly +0.37 to +0.39, 321/321.

Quarterly +0.11 at zero costs (188/321), +0.29
at base costs (201/321), min -2.86 pp (the 2008 windows). The v1 run with the index-close trigger had -2.35 (not
re-run). On NDX over the same starts: MQQQ +1.60 (321/321); QQQP -2.08 (104/321) under the base trigger, +0.78
(188/321) in the v1 run, not re-run.

The gap is the reset effect: costs move it by 0.05 pp or less for monthly and weekly (C3 confirmed).

**F9. The early-reset days decide the quarterly results, and whether a day counts depends on what the trigger
watches (R2 audit finding).** The prospectus trigger is the ETF's price during the day. The engine's base case since
R2 watches the ETF's daily low from the ETF's first bar and the index price before that. In v1 the trigger watched
the index close. Episodes in level mode:
- SPYQ: 2008-11-20 only. SPY's low breached -35%; its close was -34.95%, so the v1 close trigger found this episode
  on the index only.
- MQQQ: 1987-10-26 only.
- QQQP: 1987-10-26, 2000-12-20, 2001-09-19 and **2008-11-21**. On 2008-11-21 QQQ's low was 35.62% below its
  2008-09-30 close. The index low had touched -35.08% the day before, while QQQ's low stopped at -34.54%.
- SPX monthly, SPX weekly and NDX weekly: none.

At a 34% drop QQQP also fires on 2000-05-24 and 2001-03-29; at 36% the 2008 episode vanishes for both quarterly
funds. `results/calendar_vs_daily.md` section 6b: the 120 S&P 10-year windows that contain 2008-11-20 have median gap
**-2.10 pp and 0% wins**. The other 681 have **+0.06 pp, 52%**. With the trigger switched off (a sensitivity, not the
product), SPYQ is **+0.27 pp, 59%**, the same as monthly.

On the Nasdaq-100, MQQQ's single 1987 episode costs -3.35 pp inside its 33 windows but +1.55 outside and +1.36 with
the trigger off. QQQP is **-5.07 pp over the 248 windows that contain an episode (1% wins), +0.97 over the other
133**. With the trigger off it is **+0.35**, against MQQQ's +1.36. The quarter's leverage drift does damage with or
without the trigger, and the trigger decides the sign of the headline.

Trigger-basis table (section 9b; 10-year median, fixed):
- QQQP: -2.10 with the ETF low at 35% and -1.78 with the index low. It is +0.32 with the ETF close, the index close
  or the ETF low at 36%.
- SPYQ: -0.54 in every cell except four. It is +0.27 with the ETF close at 35% or 36%, the index close at 36%, or the
  ETF low at 36%. The index low at 36% still fires, on 2008-11-21, index only.
- MQQQ: +1.36 in every cell.

No fund of any kind hit zero 1950-2026; the daily twin's worst day was 1987-10-19 (-41%).

**F10. The monthly advantage is flat for a year and grows after three. (C8: Trainor's "dissipates beyond six
months" is what the annualized curve shows over 1-12 months. What he did not see is the rise after 3 years).**

SPX monthly median gap by holding period, annualized: +0.41 / +0.17 / +0.11 / +0.04 / +0.11 / +0.18 / +0.29 pp at
1 / 3 / 6 / 12 / 36 / 60 / 120 months. In total-return terms (auditor scratch 2026-10-12, not re-run) these
medians are about +0.04% at 1-12 months, +0.27% at 36, +0.73% at 60, +2.5% at 120. The "dip" is 0.035% x 12. The
median hides a heavy left tail at short horizons: the mean 1-month gap is negative for every product. October 1987
alone makes MQQQ's 1-month mean -20 pp (annualized, scratch). Weekly +0.01 to +0.28, rising.

QQQP by horizon under the base trigger: +1.04 / +0.77 / +0.38 / -2.10 at 12 / 36 / 60 / 120 months. The v1 run with
the index-close trigger (not re-run) gave +1.14 / +0.96 / +0.96 / +0.31.

**F11. A buy-once margin position beats every 2x fund on the S&P 500 at the median only among the windows it
survives. (The position never resets, has the same costs, and its loan compounds daily). Over all windows, including
those where its equity goes to zero, the S&P medians are about zero. No fund-minus-margin interval, over all windows
or over the survivors, excludes zero.**

The loan now compounds in the R2 re-run. The v1 run charged simple interest over the window. That flattered the margin side by 0.1-0.2 pp/yr at the median and up to 0.8 in high-rate windows.
Now the margin position finishes (equity zero) in **24% of S&P 10-year windows (190 of 801) and 16% of Nasdaq-100
windows (60 of 381)**.

Fund minus margin at 10 years (pp/yr). A finished window counts as -100% CAGR, that is, as an automatic fund win.
- Median over all windows: SPYQ -0.45, monthly +0.08, weekly -0.12 pp/yr (fund wins 48-50%).
- Median among surviving windows: **-2.07 / -1.78 / -1.52 pp (fund wins 32-35%)**.
- The all-window MEAN is +21.7 to +22.8 pp because of the finished windows.
- Phase-pooled intervals of the mean (R2 step 12e: SPYQ +22.01 [-22.37, +66.40], monthly +23.07 [-22.38, +68.52],
  weekly +22.88 [-22.32, +68.08]). All are noisy; a finished window counts as -100% here.
- Intervals over the survivors only, with finished windows left out of their phases (R2 step 12f: -1.32 [-5.39,
  +2.75], -0.83 [-4.72, +3.07], -0.89 [-4.66, +2.89]). All are noisy.

Nasdaq-100: MQQQ +2.61, QQQP +1.06, weekly +2.28 over all windows (52-54%), and **-1.17 / -4.71 / -1.71 among
survivors (43-45%)**. The pooled means over all windows are +14.41 / +10.97 / +14.58 and over the survivors +0.06 /
-2.60 / +0.17. They rest on one or two degrees of freedom and are all noisy (for example, MQQQ over the survivors
[-52.73, +52.86]). Over all windows, the monthly fund beats the margin position by +0.97 / +1.26 / +2.61 pp at 3 / 5 /
10 years. The daily twin beats it by -0.62 / -0.45 / +1.35.

The study did not re-run the 30% maintenance-call variants. In the S3 audit scratch of 2026-10-12, a call came in 39%
of S&P 10-year windows. Liquidate-to-cash turned the comparison in the funds' favor; deleverage-to-1x did not.

Reading for C7: at fed funds + 1.4% financing, "buy once with borrowed money and never touch it" earns more than any
reset structure in the windows where it survives. It loses all its equity in one S&P window in four. This benchmark
leaves out the margin call it cannot get and the margin rate a retail account actually pays (far above
fed funds + 1.4%). The benchmark borrows the fund's costs, with the spread accrued on the opening balance
(ASSUMPTIONS section 2). A spread charge on the growing loan would take a further 0.1-0.2 pp/yr off it (R2 audit).

**F12. Risk is the same story for every 2x structure.** Full history 1950-2026, fixed encoding, Shiller yields, R2
conventions:
- SPX 1x 11.7% CAGR, -55% max drawdown; SPYQ 11.5%, -93%; its twin 12.2%, -91%; monthly 12.6%, -89%; weekly 12.3%,
  -90%.
- Nasdaq-100 1985-2026: 1x 14.8%, -83%; MQQQ 15.1%, -99%; twin 14.9%, -99%; QQQP 11.8%, -99.6% (it did not hit
  zero).

Time under water 94% for all S&P 2x series, 96-97% on the Nasdaq-100. Against v1 the S&P 2x CAGRs are 0.2 pp lower
and the Nasdaq-100 ones 0.1 pp lower. The causes are ACT/360 and, on the S&P, the data refresh to 2026-10-22. QQQP is
a further 0.7 lower (the 2008-11-21 reset). The reset rule changes the CAGR by a few tenths and the drawdown by a few
points; the leverage sets both.

### S4: timing rules on the calendar funds (2026-10-13; re-run 2026-10-24 after R2; `scripts/run_strategies.py`, `results/strategies.{md,json}`)
Settings: as S3 (total-return underlying, price-index signals, the R2 base trigger, level mode, both cost encodings),
plus:
- Signal and fill: signal on close t, fill at close t+1 (delays 2 and 3 also run).
- Cash: it earns the 3-month T-bill's investment yield, lagged, with the TB3MS proxy before 1954. FRED DTB3 is a
  discount rate; R2 converts it (+0.13 pp/yr at 5% against v1).
- Trade cost: half-spread 0.10% on the live Tradr products, 0.02% on modeled designs and twins (ASSUMED; the results
  also report the doubled cost).
- Rules: every rule fixed before testing, none tuned; 12 variants x 3 delays per product (the multiple-testing count).
- Windows: every month-end start, 10 years.

Every series is synthetic. Against v1 the SPYQ and MQQQ edges moved by 0.3 pp or less (ACT/360, the cash yield, the
ETF-low trigger). QQQP's edges moved by 2-3 pp because its passive benchmark did (F9).

**F13. No timing rule is a reliable improvement on buy-and-hold across both indexes.** Ten-year median edge over
the passive fund (pp/yr; share of starts the rule wins), delay 1, fixed encoding, on SPYQ | MQQQ:
- trend_200d_sma **+4.0 (70%) | -5.2 (37%)**; trend_200d_ema +1.9 (65%) | -5.7 (37%);
- trend_50d_sma -1.0 | -6.9; trend_50d_ema -0.9 | -9.9;
- trend_200w_sma -0.9 | -0.6; trend_200w_ema -2.1 | +0.5;
- guppy +0.1 (53%) | -3.6; guppy_f200 +1.8 (59%) | -5.4;
- guppy_weekly 0.0 (wins 39%, ties 17%, losses 44%) | -4.2; guppy_weekly_f200 -2.1 | -0.4;
- vol_threshold +0.6 (57%) | +2.3 (59%);
- drawdown_stop -4.7 | -9.3 **with re-entry at a new all-time NAV high**. PROMPT.md never fixed the re-entry. That
  choice kept SPYQ in cash 17 years from 2000 and MQQQ 21 years. In the v1 run, the auditor's scratch variant
  re-entering on a 25% rebound from the trough gave SPYQ +1.0 pp, 59% wins, and MQQQ -3.4. So the drawdown-stop
  number is a property of the re-entry rule, recorded in ASSUMPTIONS section 4.

Means and the headline interval (phase-pooled over non-overlapping 10-year windows, ASSUMPTIONS section 7; R2 step
12d): **every rule's 10-year edge is NOISY on both funds**. SPYQ (t with 5 degrees of freedom): trend_200d_sma +3.32
[-4.13, +10.76]; trend_200d_ema +1.66 [-5.62, +8.94]; guppy_f200 +1.16 [-7.15, +9.47]. Two more rules: vol_threshold
+0.01 [-5.12, +5.13]; drawdown_stop -2.92 [-11.07, +5.24]. MQQQ has 3-4 windows per phase, so t has 2 degrees of
freedom. There the means of the 200-day rules have the opposite sign to their medians:
- trend_200d_sma +1.21 [-46.10, +48.52] against a median of -5.25;
- trend_200d_ema +2.38 [-49.72, +54.48] against -5.73.

The windows that contain the 2000-02 crash carry the mean. The other two: vol_threshold +2.25 [-32.56, +37.07];
drawdown_stop -3.24 [-56.65, +50.18]. The rate encoding moves the medians by at most 0.55 pp (SPYQ trend_50d_sma:
-1.01 fixed, -0.46 rate). On QQQP the edges depend on the trigger basis as much as on the rule, because the passive
benchmark moved by 2.4 pp (F9). The rules show it (trend_200d_sma -5.0 under the v1 trigger, -2.3 under the base;
vol_threshold +3.0 and +5.9).

Full-history CAGR / max drawdown, same window, SPYQ from 1953 (Shiller yields, R2 conventions): passive
10.6% / -93%; trend_200d_sma 13.5% / -46%; guppy_f200 11.7% / -48%; drawdown_stop 6.3% / -64%. MQQQ from 1988:
passive 17.8% / -99%; vol_threshold 21.1% / -60%; trend_200d_ema 19.8% / -65%; drawdown_stop 8.0% / -51%.

**F14. The S&P 200-day rule's edge was positive before 2009 and negative after. No test on one history establishes
that split: 1990-2008 against 2009-2026 gives z 1.6. The higher z for all history before 2009 against after
(1.9-2.7) rests on a boundary chosen after a look at the data. On a whole-era basis the edge is NOT positive
out-of-sample, and no window statistic of it is distinguishable from zero.**

The overlapping 10-year medians read +5.2 before 1990 and +4.1 after. But the full-run out-of-sample edge
(`results/strategies.md` table 3B, 1990-2026 as one run) is **-0.05 pp/yr** (fixed) / -0.17 (rate). The full-run
edge by sub-era (`eras` in the JSON, fixed, delay 1; one run per era, descriptive) is **+5.29 (1950-89), +6.91
(1990-2008), -8.37 (2009-2026)**. So 2000-02 and 2008 alone carry the out-of-sample window medians.

The era-difference test (R2 step 12e) uses the daily log edge of the rule over passive with Newey-West standard
errors (`era_tests` in the JSON):
- 1990-2008 against 2009-2026 gives z = 1.60 / 1.64 / 1.61 at Bartlett lags 21 / 63 / 252, not significant;
- all history before 2009 against after gives 1.90 / 2.18 / 2.73, above 2 at the longer lags. The longer lags are the more
  robust choice for a series of persistent positions.

But the analysis picked the 2009 boundary after a look at the data. A test whose break date comes from the data needs
a critical value well above 1.96 (Andrews 1993, cited from memory and not computed here). So the "pre-2009" reading
is suggestive, not established.

The out-of-sample 10-year windows (322 starts, 1990-2016) give a pooled mean of +1.89 [-79.80, +83.59] with one
degree of freedom. That is two independent windows per phase, so no test is possible there; the whole-sample interval
above is noisy. Over non-overlapping 10-year windows the rule won a majority in 63% of out-of-sample phases and all
windows in 20% (v1 run, not re-run). The rules guppy_f200 (+3.8 / +1.8) and vol_threshold (+0.9 / +0.7) have the same
shape with smaller numbers.

On MQQQ nothing is positive in both eras (the pre-2005 "in-sample" +12 pp for the 200-week rules and
guppy_weekly_f200 is the 2000-02 crash alone). The fast 50-day rules flip from clearly positive in-sample to strongly
negative out-of-sample on both indexes (SPYQ ema +4.8 / -10.2): whipsaw cost. One history cannot tell whether
2009-2026 is the regime or the rule.

**F15. Delay matters, and delay 1 is the sweep's best case.** For trend_200d_sma on SPYQ: +4.0 / +2.1 / +1.0 pp at
delays 1 / 2 / 3. All three are noisy on the pooled interval, R2 step 12e: +3.32 [-4.13, +10.76], +0.97 [-7.24,
+9.17], +1.22 [-5.81, +8.24]. Over delays 0-10 (v1 auditor scratch, not re-run) the edge is +3.0, +4.0, +2.0, +1.4,
+3.1, +1.6, +1.7, +0.8, +0.7, +0.7, +1.0. So the headline is the maximum, and a typical fill is nearer +1.5.

Delay 0 is LOWER than delay 1, so no rule depends on a same-close fill (the good news). Two rules, guppy_f200 (+1.8 /
+2.3 / +2.2) and vol_threshold on SPYQ (+0.6 / +1.1 / +1.0), are stable to delay 3 and turn negative at delays 9-10
(scratch). The rule vol_threshold on MQQQ is erratic (+2.3 / +0.4 / +5.7); trend_50d_sma worsens (-1.0 / -3.2 /
-4.0). On the daily twins one rule changes sign with delay in the results table (guppy on the S&P twin). SPX lag-1
autocorrelation was about +0.12 before 1990 (a reading of F7's decade values, not a results key) and negative after.
This is consistent with the idea that part of the pre-1990 edge is one-day follow-through that a day's delay removes
(not proven).

**F16. Clean Guppy, as fixed in PROMPT.md (unchanged by R2).** Daily on SPX: 70 buys / 69 sells in 76 years (1.8
trades/yr, 1 whipsaw round trip). With the 200 EMA filter: 306 trades (4.0/yr; 145 whipsaw legs, 61 entries and 84
exits). The results table counts entries and exits separately, so the two whipsaw figures are on different bases. The
filter doubles trading.

Weekly: 20 trades (0.26/yr) on SPX, 8 on NDX; it sold ten times in 76 years. Direct red<->green jumps: zero in all
eight cases, so the Pine alert would have caught every transition. Multi-start uses wealth-path ratios (a follower
already running). The study did not run a "start flat, wait for green" investor.

### B13: drawdown-conditioned entries (entries after major drawdowns) (2026-10-13; re-run 2026-10-24 after R2; `scripts/run_from_bottoms.py`, `results/from_bottoms.{md,json}`)
Settings as S3 (total-return underlyings, Shiller yields, the R2 base trigger and day counts, the compounding margin
loan, level mode, fixed encoding unless stated). Every entry is a NAV ratio of the full-history run; the margin
benchmark is a per-entry run. Against v1:
- the fund, twin and 3x figures moved by 0-2 points of 3-year return from ACT/360;
- the margin column moved by up to 7 points from the compounding loan;
- QQQP's 2008 entry moved by the trigger basis.

Comparators:
- the calendar fund and its daily 2x twin;
- a synthetic 3x daily fund at the filed UPRO / TQQQ swap terms (`products.MODELS_3X`, VERIFIED N-PORT 2026-05-31
  spreads and turns; TQQQ's 0.82% fee ASSUMED);
- the real UPRO / TQQQ prices where they exist (2020 and 2022 only; price-only);
- a buy-once margin position (no margin call);
- the 1x index.

The study found the bottoms in the data as drawdown troughs and checked them against the list. All S&P dates matched.
NDX's 2008-11-20 (-53.7%) is the data's low; the study keeps 2009-03-09 as "listed, not the low". The NDX 2020 low is
03-20.

**F17. Bought at a bottom, a calendar fund is a 2-3.7x position and it shows.** Effective leverage on the entry day
(SPYQ): 1974 2.04x, 1982 2.18x, 1987-12-04 3.67x, 2002 2.11x, 2009-03-09 3.01x, 2020-03-23 3.66x, 2022 2.01x.

QQQP at the 2008-11-20 close is 4.40x under the base trigger. The R2 audit showed why v1's "close-only artifact"
reading was wrong:
- Under an index trigger the fund would have reset at the level that day. That is 2.00x at the close with the index
  low as the trigger, an R2 audit scratch figure and not a stored result.
- But the prospectus trigger is QQQ's own price, whose low stopped at -34.54% that day and reached -35.62% the next.
- So the fund would have closed 2008-11-20 at about 4.4x and reset on 11-21.

That is the trigger-basis knife edge of F9, not an artifact; its 3-year return from that entry is +279% (v1,
resetting on 11-20, +407%). MQQQ's 2.82x that day is a mid-month float. Three-year returns from the S&P bottoms,
SPYQ / twin / 3x model / margin / 1x:
- 1974 +113 / +121 / +195 / +118 / +76%;
- 1982 +186 / +179 / +296 / +170 / +110%;
- 1987 +97 / +70 / +86 / +81 / +62%;
- 2002 +116 / +111 / +191 / +106 / +62%;
- 2009 +307 / +263 / +504 / +216 / +116%;
- 2020 +214 / +161 / +264 / +152 / +85% (real UPRO +268%);
- 2022 +173 / +163 / +280 / +153 / +91% (UPRO +274%).

Medians: SPYQ +173%, twin +161%, 3x +264%, margin +152%, 1x +85%. SPYQ beat its twin in 6 of 7 bottoms, and by most
where its entry leverage was highest (1987, 2020). The 3x daily fund beat SPYQ in 6 of 7. Nasdaq-100 medians (MQQQ /
twin / 3x / margin / 1x): +280 / +267 / +460 / +229 / +123%. MQQQ's entry leverage is 2.1-2.8x. The extra leverage
lasts until the next reset (six trading days after the 2020 bottom, sixteen after 2009-03-09 to the 2009-03-31
quarter-end: `results/from_bottoms_leverage.png`).

Caveats from the B13 audit:
- The "seven bottoms" are the listed ones. The data also hold 1962 (-28%) and 1970 (-36%) troughs tiered as shallow.
  With them the medians are SPYQ +151% / twin +140% / 3x +264% / 1x +76%, and the fund beats the twin 8 of 9.
- The fund beats the twin 6 of 7 at 1 and 3 years, 4 of 6 at 5 years and 3 of 5 at 10.
- The 3x model's max drawdown inside the three years after entry was -38% to -64% (S&P) and -44% to -82% (NDX). From
  the 2002 entry its 10-year result (+52%) trailed the plain index (+127%).
- The 3x result was robust to its spread in the v1 run (0 to 1.5% per turn; not re-run). Across those spreads the
  median ran +250% to +290%, and the 3x fund beat SPYQ in 6-7 of 7.
- Real UPRO is within 7 points of the model at 3 and 5 years for 2020 and 2022 (v1 audit scratch).

**F18. Drawdown-threshold entries: the first close X below the prior high, 3-year median return of the fund.**
- S&P 500 (SPYQ): -20% fired 11 times 1957-2022, median +75%; -30% six times, +38%; -40% three times (1974-08-23,
  2002-07-16, 2008-10-09), +46%; -50% once (2008-11-20), +127%.
- Nasdaq-100 (MQQQ): -20% eight times, +66%; -30% four times, +74%. The -40% / -50% / -60% / -70% levels fired once
  each, all in 2000-01 and all 3-year LOSSES (-89 / -79 / -65 / -30%). Then -80% once (2002-07-22), +121%.

Deepest falls in the data: S&P -56.8%, Nasdaq-100 -82.9%. On the S&P every level was positive on median at three
years, but the levered fund beat the unlevered index only at 20% and 50%. At 30% SPYQ's +38% trailed the index's
+45%, and at 40% it matched it (+46% against +44%; daily twin +61%). On the Nasdaq-100 the 40-70% threshold entries of
2000-01 were traps, and only the 80% level paid. Note: the NDX -20% rule has no 2008 entry, because its anchor stayed
at the 2000-03-27 high until 2015. The rule takes one entry per fall from the prior all-time high.

**F19. A wait for Guppy confirmation cost more than it saved after the major bottoms.** After the S&P bottoms the
daily slow ribbon's red->gray came a median 18 trading days later, with the index already +15%. Daily gray->green
came after 71 days and +20%; the weekly gray->green after 224 days and +42%. Nasdaq-100: 20 days / +22%, 38 days /
+32%, 180 days / +64%.

No confirmed entry beat the bottom entry at the same end date, which is true BY CONSTRUCTION. The confirmed entry
starts at a NAV 21-97% above the hindsight bottom's (audit). The informative comparison is against the rule-based
level entries, which can be early. There the confirmations LOST more often than they won on the S&P (8-9 of 21 at
their own 3-year windows). At the same end date the count is 6-8 of 21, and the median gap is -14 to -22%. On the
Nasdaq-100 they helped on median only because the 2000-01 parent entries were catastrophic (own windows +34.8%
against -26.4%).

At the same end date the Nasdaq-100 count is 6 of 16. Robust to the fill delay in the v1 audit's scratch run (1-5
sessions unchanged; 10 sessions 6-8 of 21; not re-run in R2). The weekly red->gray never came within two years of the
1987 and 2020 bottoms on either index (the weekly ribbon never went red). Reading: the Guppy is a trend filter, not a
bottom finder. It protected the buyer who was badly early (Nasdaq-100 2000-01) and cost the buyer who was roughly
right.

**F20. Timing beats costs.** An entry three months early changed the 3-year return by a median 113 points (S&P) and
136 points (Nasdaq-100) across the bottoms. The six cost encodings of F5 span 18 and 25 points. Crisis financing is
outside that range: an earlier private kit found it understated by 2-3 pp/yr in 2008, a figure not re-derived here.
An entry three months late changed it by 43 and 86 points.

The design builds part of this in (the hindsight bottom is the best possible entry), but the order of magnitude is the
point. For a drawdown-conditioned entry, when matters about six times more than which cost encoding is right (6.2x on
the S&P, 5.5x on the Nasdaq-100). The v1 text said "ten times", which its own numbers did not support.

Addendum (user request 2026-10-13): `results/from_bottoms.md` now carries the overlay charts in dollars. They show
what $10,000 at each bottom's close became at 0.5 / 1 / 1.5 / 2 / 2.5 / 3 years. The charts cover the calendar fund,
its twin, the 3x model and the index. A key-facts table gives entry leverage, 3-year CAGR, max drawdown inside the 3
years and early resets. Medians across the S&P bottoms at 3 years (R2 step 6, calendar-year horizons): SPYQ $27,323,
twin $26,113, 3x $36,394, index $18,524. Across the Nasdaq-100 bottoms: MQQQ $37,994, twin $36,697, 3x $56,003, index
$22,277.

The v1 tables ($28,319 / $26,151 / $36,457 / $18,524 and $37,590 / $35,367 / $52,940 / $21,865) measured the horizons
in 252 trading days. Every other table in the study uses calendar years (R2 audit finding). The dollar tables now use
the same calendar rule, with a planted test, and ACT/360 accounts for the rest. The 2020 SPYQ row at 3 years is
$31,391 (+214%, as in the 3-year table). The 3-year CAGRs behind them run 25-60%/yr for SPYQ and 4-76% for MQQQ (1987
is the 4%). So the dispersion is the story as much as the median.

**F21. From the GFC low, every calendar design ended above its daily twin. The comparison with the real 2x funds
depends on the assumed costs.**

The study is `scripts/run_gfc_oracle.py`, with `results/gfc_oracle.{json,md}` (R4
addition, 2026-10-26). The entry is the lowest index close from 2007 to 2009: 2009-03-09 on the S&P 500 and 2008-11-20
on the Nasdaq-100. The end is the last date that the index, the real 2x fund and the real 3x fund all hold. What
$10,000 became, fixed encoding:
- S&P 500 (to 2026-10-02): SPYQ $715,067, monthly design $703,542, weekly design $625,447, daily twin $590,843, real
  SSO $776,671 (price only), 3x model $2,608,783, index $158,186.
- Nasdaq-100 (to 2026-10-09): MQQQ $3,080,655, QQQP $2,499,635, weekly design $2,576,009, MQQQ's daily twin
  $2,200,375, real QLD $3,053,260 (price only), 3x model $11,505,261, index $355,113.

Under the rate encoding the monthly design and MQQQ end at $804,289 and $3,531,497, above SSO and QLD. Under the fixed
encoding the monthly design ends below SSO. Each daily twin is a daily fund like SSO and QLD, with the costs fitted to
the live calendar funds. Every twin ends below the real fund under both encodings. So the comparison with the real
funds measures the assumed costs, not the reset design. The real funds are price only, so their true lead over the
twins is larger.

Bought at the low, a calendar fund holds more than 2x until the index regains its last reset level. At the entry
close MQQQ held 2.82x and the S&P monthly design 2.19x. QQQP held 4.40x, but its 35% early reset fired on the next session, 2008-11-21, and set
it back to 2x. With an entry 2 to 10 sessions before the low, QQQP ends below its twin. The other five designs end
above their twins at every entry shift from -10 to +21 sessions. This study does not split each lead into its causes.

The real UPRO and TQQQ (price only) started after the low. From their first closes they ended above their 3x models:
$1,251,553 and $3,758,161, with models at $1,126,404 and $3,191,084. One hindsight path has no interval, so F21 is an
illustration, not a statistic.

Could not test (B13):
- the trigger's fill (the model assumes the level; the basis and the drop are sensitivities, F9);
- no live calendar fund before 2024;
- the margin benchmark has no margin call;
- in the bottoms tables, UPRO / TQQQ real prices exist only for the 2020 and 2022 entries and exclude dividends;
- F21's real funds are price only: the issuer's distribution table (fund pages, read 2026-10-26) starts in 2017, and
  older annual reports stay unread;
- seven bottoms per index is a small sample;
- NDX pre-2006 yield assumed.

Could not test (S4):
- real bid-ask costs (assumed; thin funds may cost more);
- live behavior (synthetic NAV with fitted costs);
- taxes, slippage beyond the half-spread, intraday fills;
- independence of the overlapping windows (the win shares are not p-values; NDX has few independent 10-year windows);
- the study chose the best rule after the fact from 12 variants, so that count inflates its edge.

Could not test (S3):
- no live calendar fund before 2024-08 (the liquidated weekly and SPY-monthly funds left one published month, F1b);
- the trigger never fired live, and the model assumes its fill at the level. Whether the 2008 episodes count depends
  on one point of the drop and on which price the trigger watches (F9). So the quarterly results are conditional on
  that choice;
- costs fitted on 2024-26 (the encodings diverge when rates move, see F5);
- pre-1988 S&P yields are Shiller's measured monthly series, and pre-2006 Nasdaq-100 yields assumed;
- pre-1954 rates a proxy; prices not NAVs in the fit;
- the headline interval (non-overlapping windows pooled over phases, 3-7 windows per phase at ten years) has simulated
  coverage under independent months only. The S&P monthly gap series is persistent across such windows, so its
  intervals are too short by an unknown amount (ASSUMPTIONS section 7). The block-bootstrap intervals of the mean and
  the median are secondary and biased short;
- the win shares carry no interval;
- C5 (volatility terciles) not computed; B10 / B11 not done.
