# Changelog

All notable changes to this project. Dates are release dates (UTC).

## 0.1.1, README: entries at market bottoms (2026-11-07)

- README.md now leads its bottom-entry results with the fair comparison, the 2x daily twin at the same costs. A
  summary-table row, a short section and the headline facts give it (F17, F21). From the GFC low, all six calendar
  designs ended above their own twins under both cost encodings.
- A new section, "How big the edge is, and when it appears", gives the size of the edge in every test, with its
  interval or the reason it has none. A second table lists the conditions under which the calendar design led, and
  which of them a buyer can see in advance.
- A new section, "What leverage itself did", answers whether 2x beat the index at all. It gives the full-history
  growth rates and drawdowns (F12) and the spread of simulated outcomes with the bad decades (F24). It also gives 3x
  on both sides (F25) and a buy-once margin position (F11). The horizon chart now appears in the README. No code,
  input or result changed.

## 0.1.1, one wording fix in a results table (2026-11-07)

- `results/validate_live.md` no longer calls SOXM and SOXW out of scope, because F26 checks them. One sentence in
  `scripts/run_validate_live.py` changed. So validate_live and semis re-ran on unchanged inputs, and no number moved.
  The semis golden file now records the new hash of `results/validate_live.json`.

## 0.1.1, documentation fixes (2026-11-06)

No code, input or result changed.

- README.md now features the 0.1.1 results. A summary table opens it. New sections cover the best leverage (on
  history and on simulated decades), the semiconductors and the real monthly-reset mutual funds. Two charts show
  them. Prose pins cover every new number.
- data/README.md lists all 25 symbols that the studies read. Its fingerprint table now shows the copy of each file
  that the published results read.
- Correction: no calendar-reset ETF existed before August 2024, but monthly-reset mutual funds have existed since
  October 2009 (F22). README.md, ASSUMPTIONS.md, FINDINGS.md and THEORY.md had said that no calendar-reset fund
  existed.

## 0.1.1 (2026-11-06)

The final release. It closes the backlog; nobody maintains the repository after it.

### Engine grade

EXACT A, PROVEN A, UNCERTAINTY A, TRACEABLE A (independent audit, 2026-11-06, confirmed after two fix loops). The first
pass read EXACT A, PROVEN A-, UNCERTAINTY B, TRACEABLE B. FINDINGS.md (build log) lists its findings and the fixes.

### New studies

- Leverage from 1x to 3x on both indexes, with the fee at which each design breaks even (FINDINGS F23).
- A block-bootstrap Monte Carlo of the reset gap, for the uncertainty of the best leverage (F24).
- The 3x weekly, monthly and quarterly designs, with several early-reset triggers (F25).
- The semiconductor index (SOX), with the real 2x and 3x funds as checks (F26).
- The reset day, and entries on any trading day (F27).
- The reset gap split into its sum-of-squares parts (F28).
- A rolling two-year LEAP on the S&P 500 as a comparator (F29).
- The real monthly-reset mutual funds since 2009, as a live check of the cost model (F22, extended).

### Changed inputs

- The Nasdaq-100 dividend yield for 1999-2006 comes from QQQ's filings, not from an assumption (F30).
- The five studies of 0.1.0 re-run on their 0.1.0 data ends, so a later top-up of the price library moves nothing.
  The new studies stop at a fixed end, 2026-09-30.
- The engine replaces a bad SOX low on 1997-08-08 with the close. Every reset anchor is an NYSE session.

### Theory

- THEORY.md explains the products, their risks, the mathematics of the payoff and every formula the engine uses. It
  maps each equation to its code and to a test.
- `docs/theory_examples.py` computes every number THEORY.md quotes, from planted inputs, so it needs no market data.

### Maintenance

- Golden files record the fingerprints of their inputs. A study re-run on other data skips its golden test and
  names the files that differ.
- `constraints.txt` holds the tested version of each package; the README also names the Python version.
- The README names every fund sponsor and the cuts: short funds are out of scope.

## 0.1.0 (2026-10-31)

First public release.

### Engine grade

EXACT A, PROVEN A, UNCERTAINTY A, TRACEABLE A (independent audit, 2026-10-26; confirmed again after a full code
review and its fixes, 2026-10-29). The project grades every engine on
four properties before a release, and it publishes only at A on all four:
- EXACT: every formula and convention matches a filing or a market standard.
- PROVEN: every formula has a planted-answer test, a break case and a second implementation.
- UNCERTAINTY: every headline number carries a valid interval or a noisy label, and every regime claim carries a
  significance test.
- TRACEABLE: every result carries a fingerprint, golden files pin it, and a fresh clone reproduces it.

### What the engine does

- It models calendar-reset 2x funds and a daily-reset twin on the same index at the same costs. The funds reset
  weekly, monthly or quarterly, with the 35% early reset.
- The history covers the S&P 500 since 1950 and the Nasdaq-100 since 1985.
- It validates the model against the three live Tradr funds (SPYQ, MQQQ, QQQP). It also checks the one published
  month of the nine funds that closed in 2025.
- It tests timing rules with fill delays and costs: moving-average trends, Clean Guppy, a volatility threshold and a
  drawdown stop.
- It studies entries from major market bottoms, with one hindsight entry at the 2007-2009 low next to the real 2x
  and 3x funds.

### How the numbers are checked

- Conventions come from filings and market practice: ACT/360 financing and an ACT/365 fee. An NYSE session calendar
  matches the exchange's own record.
- The fee timeline comes from the funds' filings, and the swap spreads come from the N-PORT filings.
- Every formula has a planted-answer test, a break case and a second implementation. The suite runs about 1,600
  checks.
- Every headline gap carries a phase-pooled interval from non-overlapping windows. A simulation checks its coverage
  at every published configuration, and regime claims carry a significance test.
- Every result file carries a fingerprint of its inputs and of the code that wrote it. Golden files pin the results.
- Prose pins tie each number in README, FINDINGS and ASSUMPTIONS to the results. A fresh-clone test runs the suite
  on the public tree alone.

### Main results

- At the median over 10-year holds, monthly and weekly resets beat daily resets by about +0.3 pp a year on the
  S&P 500. On the Nasdaq-100 the lead is +1.1 to +1.4 pp a year.
- None of the six 10-year gaps is distinguishable from zero on one history.
- Quarterly resets do not beat daily resets: -0.5 pp a year on the S&P 500, -2.1 on the Nasdaq-100.
- No timing rule is a reliable improvement on buy-and-hold; every rule's 10-year edge is noisy.

### Known limits

- No calendar-reset fund existed before August 2024; everything earlier is a model.
- The 35% early reset has never fired in a live fund.
- Window 1 of the live fit runs from inception to 2025-09-30. There the model bounds the cash yield and does not fit
  it at the window's own counterparty mix. This project did not read the filings for that window's swap spreads.
