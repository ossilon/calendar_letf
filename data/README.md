# Data folder

Price files are **not** in the repository. TradingView licenses its data for display only, so the repository never
ships it. You export your own copy and put it here. FRED rates are US-government public data; you download them
yourself as well.

## Where the package looks

1. The folder in the environment variable `CALENDAR_LETF_DATA`, if set.
2. Otherwise this folder (`calendar_letf/data/`).

The package reads rates from `<data folder>/rates/`. If the environment variable `CALENDAR_LETF_RATES` is set, the
package reads them from that folder instead.

If you already keep a price library elsewhere, copy nothing. Point the variables at it:

```powershell
$env:CALENDAR_LETF_DATA  = "C:\path\to\your\prices"
$env:CALENDAR_LETF_RATES = "C:\path\to\your\rates"
```

## Prices: what to export from TradingView

Export daily bars, full history, for these 25 symbols. The 0.1.0 studies need the first 13, and
the 0.1.1 studies need the rest. Choose the data as **split-adjusted and NOT
dividend-adjusted**. The package adds dividends itself, and every banner says so. Use ISO dates (`2024-08-15`) if the
export dialog offers a choice.

File name rule: the symbol with `:` replaced by `_`, then `_daily.csv`.

| TradingView symbol | File name | Used for |
|---|---|---|
| SP:SPX | `SP_SPX_daily.csv` | S&P 500 price index |
| SP:SPXTR | `SP_SPXTR_daily.csv` | S&P 500 total return (from 1988) |
| NASDAQ:NDX | `NASDAQ_NDX_daily.csv` | Nasdaq-100 price index |
| NASDAQ:XNDX | `NASDAQ_XNDX_daily.csv` | Nasdaq-100 total return |
| AMEX:SPY | `AMEX_SPY_daily.csv` | live-fund validation (S&P 500 ETF) |
| NASDAQ:QQQ | `NASDAQ_QQQ_daily.csv` | live-fund validation (Nasdaq-100 ETF) |
| NASDAQ:SPYQ | `NASDAQ_SPYQ_daily.csv` | live calendar-reset fund (S&P 500) |
| NASDAQ:MQQQ | `NASDAQ_MQQQ_daily.csv` | live calendar-reset fund (Nasdaq-100, monthly) |
| NASDAQ:QQQP | `NASDAQ_QQQP_daily.csv` | live calendar-reset fund (Nasdaq-100, quarterly) |
| AMEX:UPRO | `AMEX_UPRO_daily.csv` | real 3x daily fund, S&P 500 (bottom-entry study) |
| NASDAQ:TQQQ | `NASDAQ_TQQQ_daily.csv` | real 3x daily fund, Nasdaq-100 (bottom-entry study) |
| AMEX:SSO | `AMEX_SSO_daily.csv` | real 2x daily fund, S&P 500 (GFC oracle entry) |
| AMEX:QLD | `AMEX_QLD_daily.csv` | real 2x daily fund, Nasdaq-100 (GFC oracle entry) |
| NASDAQ:DXSLX | `NASDAQ_DXSLX_daily.csv` | real monthly-reset mutual fund, S&P 500 (live monthly check) |
| NASDAQ:DXQLX | `NASDAQ_DXQLX_daily.csv` | real monthly-reset mutual fund, Nasdaq-100 (live monthly check) |
| NASDAQ:RMQHX | `NASDAQ_RMQHX_daily.csv` | real monthly-reset mutual fund, Nasdaq-100 (live monthly check) |
| NASDAQ:ULPIX | `NASDAQ_ULPIX_daily.csv` | real 2x daily mutual fund, S&P 500 (live monthly check) |
| NASDAQ:UOPIX | `NASDAQ_UOPIX_daily.csv` | real 2x daily mutual fund, Nasdaq-100 (live monthly check) |
| NASDAQ:RYVYX | `NASDAQ_RYVYX_daily.csv` | real 2x daily mutual fund, Nasdaq-100 (live monthly check) |
| NASDAQ:RYNVX | `NASDAQ_RYNVX_daily.csv` | real 1.5x daily mutual fund, S&P 500 (live monthly check) |
| NASDAQ:SOX | `NASDAQ_SOX_daily.csv` | PHLX Semiconductor index, price only (semiconductor study) |
| NASDAQ:SOXX | `NASDAQ_SOXX_daily.csv` | semiconductor ETF (the SOXM / SOXW check) |
| AMEX:SOXL | `AMEX_SOXL_daily.csv` | real 3x daily semiconductor fund, price only (semiconductor study) |
| AMEX:USD | `AMEX_USD_daily.csv` | real 2x daily semiconductor fund, price only (semiconductor study) |
| CBOE:VIX | `CBOE_VIX_daily.csv` | implied volatility (LEAP comparator) |

The package accepts two layouts and detects them from the header row:

* **Raw TradingView export**: columns `time,open,high,low,close,...`. `time` may hold unix seconds or an ISO date.
  The loader converts unix times to the session date in New York time.
* **Clean library format**: columns `date,open,high,low,close,volume[,source]` with ISO dates.

The loader is strict. It stops with an error on duplicate dates, dates out of order, or a close that is zero,
negative or not a number. It never repairs data silently.

For SPX and NDX it also refuses a hole longer than 7
calendar days. It refuses any full calendar year with too few rows (floor 248). The year 1968, when the exchange
closed on Wednesdays, has its own floor. One missing month-end row would otherwise move a reset without notice.

## Rates: FRED

Download these four series as CSV from <https://fred.stlouisfed.org> (series page, "Download", CSV). Save them in
`rates/` with exactly these names. The first column holds the date. The second column holds the value in percent.

| FRED series | File | Meaning |
|---|---|---|
| DFF | `rates/DFF.csv` | effective federal funds rate, daily; the fund financing reference |
| DTB3 | `rates/DTB3.csv` | 3-month Treasury bill, daily; what cash earns |
| TB3MS | `rates/TB3MS.csv` | 3-month Treasury bill, monthly; proxy for rows before DFF starts (1954-07-01) |
| OBFR | `rates/OBFR.csv` | overnight bank funding rate, daily; the live-fund validation reference |

## Compare your files with ours

The table lists the copy of each file that the published results read. The `inputs` block of each results JSON
names it. Rows count data rows that carry a date and a value. The fingerprint is the first 12 characters of the
file's SHA-256, with line endings folded to LF first.

Your export will have the same first date and similar row counts. It will end on a later date, and its fingerprint
will differ, because a later export has later bars. A different first date or a much lower row count means a
different symbol or a partial export.

To print the same table for your own files, run this from the repository folder:

```powershell
py -c "from calendar_letf import provenance as p; print(chr(10).join(p.banner_lines(p.inputs_manifest(['SP:SPX'], ['DFF']))))"
```

Name any symbols and rate files in the two lists.

| File | Rows | First date | Last date | Fingerprint |
|---|---:|---|---|---|
| `SP_SPX_daily.csv` | 19333 | 1950-01-03 | 2026-11-02 | b146c9af89cc |
| `SP_SPXTR_daily.csv` | 9787 | 1988-01-04 | 2026-11-03 | edab5090825e |
| `NASDAQ_NDX_daily.csv` | 10519 | 1985-01-31 | 2026-10-30 | 79d8e8688fa3 |
| `NASDAQ_XNDX_daily.csv` | 5019 | 2006-11-08 | 2026-10-30 | d7dcc6dffa24 |
| `AMEX_SPY_daily.csv` | 8498 | 1993-01-29 | 2026-11-02 | 643d6ef08b88 |
| `NASDAQ_QQQ_daily.csv` | 6955 | 1999-03-10 | 2026-10-30 | f096cd6c6b75 |
| `NASDAQ_SPYQ_daily.csv` | 508 | 2024-10-01 | 2026-10-09 | 124564fb1a3b |
| `NASDAQ_MQQQ_daily.csv` | 542 | 2024-09-03 | 2026-10-29 | b71324843b8a |
| `NASDAQ_QQQP_daily.csv` | 522 | 2024-10-01 | 2026-10-29 | 233444f2dcc7 |
| `AMEX_UPRO_daily.csv` | 4345 | 2009-06-25 | 2026-10-02 | 17d862355823 |
| `NASDAQ_TQQQ_daily.csv` | 4206 | 2010-02-11 | 2026-10-30 | ae88fcb39ab3 |
| `AMEX_SSO_daily.csv` | 5103 | 2006-06-21 | 2026-10-02 | 0df3e43a82db |
| `AMEX_QLD_daily.csv` | 5123 | 2006-06-21 | 2026-10-30 | 9e5453cb02e0 |
| `NASDAQ_DXSLX_daily.csv` | 5162 | 2006-05-01 | 2026-11-03 | a6e3afa93793 |
| `NASDAQ_DXQLX_daily.csv` | 5162 | 2006-05-01 | 2026-11-03 | 38ab92c0e8a7 |
| `NASDAQ_RMQHX_daily.csv` | 2998 | 2014-11-28 | 2026-11-03 | d7c2dea8de9e |
| `NASDAQ_ULPIX_daily.csv` | 7214 | 1998-03-30 | 2026-11-03 | f2384904a6ef |
| `NASDAQ_UOPIX_daily.csv` | 7227 | 1998-03-11 | 2026-11-03 | d5d37b3e6fc5 |
| `NASDAQ_RYVYX_daily.csv` | 6639 | 2000-06-16 | 2026-11-03 | 7b5c44ec408d |
| `NASDAQ_RYNVX_daily.csv` | 8285 | 1994-01-04 | 2026-11-03 | 279fad5006a8 |
| `NASDAQ_SOX_daily.csv` | 8159 | 1994-05-04 | 2026-10-02 | 0f8d336a1666 |
| `NASDAQ_SOXX_daily.csv` | 6367 | 2001-07-13 | 2026-11-05 | 661618bb2798 |
| `AMEX_SOXL_daily.csv` | 4167 | 2010-03-11 | 2026-10-02 | 1a134c80a653 |
| `AMEX_USD_daily.csv` | 4967 | 2007-02-01 | 2026-11-05 | 434a39d64efa |
| `CBOE_VIX_daily.csv` | 9275 | 1990-01-03 | 2026-10-02 | 4dd8691f8a9f |
| `rates/DFF.csv` | 26424 | 1954-07-01 | 2026-11-03 | e84a934a5014 |
| `rates/DTB3.csv` | 18201 | 1954-01-04 | 2026-11-03 | e5fa1cb67237 |
| `rates/TB3MS.csv` | 1112 | 1934-01-01 | 2026-08-01 | ebf04b1ae5bc |
| `rates/OBFR.csv` | 2683 | 2016-03-01 | 2026-11-03 | bbef2a371e62 |

From v0.1.0 on, each results JSON holds an `inputs` block with these fields for the files that run read. Each
results table prints the same fields in its banner. The files in `tests/golden/` pin the published numbers.

## Dividends before the total-return files start

* **S&P 500 before 1988-01-04** (when SPXTR starts): SPX price plus Shiller's MEASURED monthly dividend yield
  (`reference/`, the default since S5a; ASSUMPTIONS section 3). The sensitivity runs use the earlier ASSUMED yield
  **by decade** (1950s 4.2%, 1960s 3.1%, 1970s 4.0%, 1980s 3.7%). They also use a flat yield
  (`spx_total_return(pre_yield=0.03)`, or 0 or 0.04). Every result's `attrs` and `banner()` name the yield used.
* **Nasdaq-100 before 2010**: 0.73% measured from 2006-11-08; QQQ's MEASURED fiscal-year income yields from
  1999-03-05 to 2006-11-07 (`reference/qqq_income_ratios.csv`, since v0.1.1); 0.3% ASSUMED before 1999. The
  option `ndx_total_return(qqq_yield=None)` gives the v0.1.0 series. See `series.py`.

## Refresh rules (the package refuses stale or holey files instead of guessing)

* **SP:SPXTR has no automatic feed.** Export it from TradingView by hand. If SPXTR ends more than 10 rows before
  SPX, `spx_total_return()` raises ("re-export"). The package carries up to 10 trailing rows with SPX's price move
  and reports them in `attrs["trailing_rows_filled_from_price"]` and in the banner.
* **Download the FRED files by hand.** If DFF or DTB3 ends more than 15 rows before the last price date,
  `reference_rate` and `cash_rate` raise and name the file. `attrs["rate_last_date"]` and `attrs["stale_rows"]`
  record what the package forward-filled. A hole longer than 10 calendar days inside a daily rate file also raises.
* **TB3MS** (monthly average dated the 1st) stands in only for rows before DFF starts (1954-07-01). The package
  shifts it by one month (it first uses the February average in March), then applies the one-row lag.

## Licensing

TradingView data is display-only. Do not commit, upload or share the exported files. The `.gitignore` of this
repository excludes everything in this folder except this README. The repository publishes no data files and no
daily series. Its tables hold aggregates (medians, dated episode lists), and some charts plot prices with
"Data: TradingView".
