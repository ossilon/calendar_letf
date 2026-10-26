# Changelog

All notable changes to this project. Dates are release dates (UTC).

## 0.1.0 (unreleased)

First public release.

### Engine grade

EXACT A, PROVEN A, UNCERTAINTY A, TRACEABLE A (independent audit, 2026-10-26). The project grades every engine on
four properties before a release and publishes only at A on all four: every formula and convention matches a filing
or a market standard (EXACT); every formula has a planted-answer test, a break case and a second implementation
(PROVEN); every headline number carries a valid interval or a noisy label, and every regime claim a significance test
(UNCERTAINTY); every result is fingerprinted, pinned and reproducible from a fresh clone (TRACEABLE).

### What the engine does

- Models calendar-reset 2x funds (reset weekly, monthly or quarterly, with the 35% early reset) and a daily-reset
  twin on the same index at the same costs, over the S&P 500 since 1950 and the Nasdaq-100 since 1985.
- Validates the model against the three live Tradr funds (SPYQ, MQQQ, QQQP) and against the one published month of
  the nine funds that closed in 2025.
- Tests timing rules (moving-average trends, Clean Guppy, a volatility threshold, a drawdown stop) with fill delays
  and costs, and entries from major market bottoms.

### How the numbers are checked

- Conventions from filings and market practice: ACT/360 financing, ACT/365 fee, an NYSE session calendar checked
  against the exchange's own record, a fee timeline read from the funds' filings, swap spreads read from the N-PORT
  filings.
- Every formula has a planted-answer test, a break case and a second implementation; the suite runs about 1,400
  checks.
- Every headline gap carries a phase-pooled interval from non-overlapping windows; its coverage is simulated at
  every published configuration; regime claims carry a significance test.
- Every result file carries a fingerprint of its inputs and of the code that wrote it; golden files pin the results;
  prose pins tie each number quoted in README, FINDINGS and ASSUMPTIONS to the results; a fresh-clone test runs the
  suite on the public tree alone.

### Main results

- Monthly and weekly resets beat daily resets by about +0.3 pp a year on the S&P 500 and +1.1 to +1.4 pp a year on
  the Nasdaq-100 at the median over 10-year holds. None of the six 10-year gaps is distinguishable from zero on one
  history.
- Quarterly resets do not beat daily resets: -0.5 pp a year on the S&P 500, -2.1 on the Nasdaq-100.
- No timing rule is a reliable improvement on buy-and-hold; every rule's 10-year edge is noisy.

### Known limits

- No calendar-reset fund existed before August 2024; everything earlier is a model.
- The 35% early reset has never fired in a live fund.
- Window 1 of the live fit (inception to 2025-09-30) is bounded, not fitted, at its own counterparty mix: the
  filings for that window were not read for swap spreads.
