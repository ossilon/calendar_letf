# Changelog

All notable changes to this project. Dates are release dates (UTC).

## 0.1.0 (unreleased)

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
