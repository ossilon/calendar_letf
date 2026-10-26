"""Loaders: price CSVs (TradingView exports), FRED rate CSVs, and the "known the day before" rate lag.

Plain-English summary
  * Prices live in one folder (the "data directory"). By default that is `calendar_letf/data/` next to the package.
    Set the environment variable CALENDAR_LETF_DATA to point somewhere else, e.g. on the author's machine
    a local price library (nothing is copied; the package just reads files from that folder).
  * Rates (FRED) are read from `<data_dir>/rates/<NAME>.csv`. If the environment variable CALENDAR_LETF_RATES is
    set it wins and the rates are read from that folder instead.
  * Every loader is strict: a bad row (duplicate date, dates out of order, a price that is zero, negative or not a
    number) raises an error instead of being quietly repaired. A silent repair would change a backtest and nobody
    would know.

Credit: the date parsing and strictness rules in `_parse_one` / `_read_prices` are adapted from a TradingView CSV
loader written for the author's earlier projects (same rules: never guess month-first dates, unix times need an
exchange timezone).

FRED data (DFF, DTB3, TB3MS) is US-government public data from fred.stlouisfed.org. TradingView price data is
licensed for display only, so no price file is shipped with this package; see data/README.md.
"""
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

ENV_DATA = "CALENDAR_LETF_DATA"
ENV_RATES = "CALENDAR_LETF_RATES"
PRICE_COLS = ["open", "high", "low", "close", "volume"]

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")
_DMY = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_NUM = re.compile(r"^-?\d+(\.\d+)?$")
MIN_YEAR, MAX_YEAR = 1800, 2100


# ---------------------------------------------------------------- folders

def data_path(data_dir=None):
    """The folder prices are read from: the argument, else $CALENDAR_LETF_DATA, else <package parent>/data."""
    if data_dir is not None:
        return Path(data_dir)
    env = os.environ.get(ENV_DATA)
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "data"


def rates_path(data_dir=None):
    """The folder FRED files are read from: $CALENDAR_LETF_RATES if set, else <data_dir>/rates."""
    env = os.environ.get(ENV_RATES)
    if env:
        return Path(env)
    return data_path(data_dir) / "rates"


def _file_name(symbol):
    """'SP:SPX' -> 'SP_SPX_daily.csv' (the same naming the author's price library uses)."""
    return symbol.replace(":", "_") + "_daily.csv"


# ---------------------------------------------------------------- date parsing (strict)

def _parse_one(value, date_tz=None):
    """Return (Timestamp or NaT, note). Strict: anything ambiguous is rejected with a note."""
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "none"):
        return pd.NaT, "empty time value"
    if _NUM.match(s):
        v = float(s)
        unit = "ms" if abs(v) >= 1e11 else "s"
        if date_tz is None:
            return pd.NaT, "unix time needs date_tz to derive the session date"
        ts = pd.to_datetime(v, unit=unit, utc=True).tz_convert(date_tz).tz_localize(None).normalize()
    elif _ISO.match(s):
        try:
            ts = pd.Timestamp(s)
        except (ValueError, TypeError):
            return pd.NaT, "unparseable ISO value"
        if ts.tzinfo is not None:
            if date_tz is None:
                return pd.NaT, "timezone-aware value needs date_tz"
            ts = ts.tz_convert(date_tz).tz_localize(None)
        ts = ts.normalize()
    elif _DMY.match(s):
        try:
            ts = pd.to_datetime(s, format="%d/%m/%Y")
        except (ValueError, TypeError):
            return pd.NaT, "invalid day-first date"
    else:
        return pd.NaT, "unsupported date format"
    if not (MIN_YEAR <= ts.year <= MAX_YEAR):
        return pd.NaT, f"implausible year {ts.year}"
    return ts, ""


def _read_prices(path, date_tz):
    """Read one price CSV (clean library format or raw TradingView export) into a validated DataFrame."""
    df = pd.read_csv(path)
    lower = {c.lower(): c for c in df.columns}
    if "date" in lower:
        fmt, time_col = "clean", lower["date"]
    elif "time" in lower:
        fmt, time_col = "tradingview_raw", lower["time"]
    else:
        raise ValueError(f"{Path(path).name}: header has neither a 'date' nor a 'time' column: {list(df.columns)}")
    if "close" not in lower:
        raise ValueError(f"{Path(path).name}: no 'close' column in {list(df.columns)}")

    # Dates: clean files are ISO and need no timezone; raw files may be unix seconds and need date_tz.
    tz = date_tz if fmt == "tradingview_raw" else None
    parsed = [_parse_one(v, tz) for v in df[time_col]]
    dates = pd.DatetimeIndex([p[0] for p in parsed])
    bad = dates.isna()
    if bad.any():
        notes = sorted({p[1] for p in parsed if p[1]})
        raise ValueError(f"{Path(path).name}: {int(bad.sum())} rejected date rows ({'; '.join(notes)}); "
                         f"first: {df.loc[bad, time_col].head(3).tolist()}")
    if dates.has_duplicates:
        raise ValueError(f"{Path(path).name}: duplicate dates, first {dates[dates.duplicated()][0].date()}")
    if not dates.is_monotonic_increasing:
        raise ValueError(f"{Path(path).name}: dates are not in ascending order "
                         "(check day-first vs month-first, or a mixed export)")

    out = pd.DataFrame(index=dates)
    out.index.name = "date"
    for c in PRICE_COLS:
        out[c] = pd.to_numeric(df[lower[c]], errors="coerce").values if c in lower else np.nan
    # Prices must be real positive numbers. open/high/low may be blank (NaN) in some exports, but never <= 0.
    close = out["close"]
    if (~np.isfinite(close) | (close <= 0)).any():
        b = close[~np.isfinite(close) | (close <= 0)]
        raise ValueError(f"{Path(path).name}: {len(b)} non-finite or non-positive close values, first on {b.index[0].date()}")
    for c in ("open", "high", "low"):
        v = out[c]
        if (np.isinf(v) | (v <= 0)).any():
            raise ValueError(f"{Path(path).name}: non-positive or infinite {c} values")
    out = out.astype(float)
    return out, fmt


# ---------------------------------------------------------------- public price loaders

def load_prices(symbol, data_dir=None, date_tz="America/New_York"):
    """Load `<data_dir>/<SYM>_daily.csv` (SYM = symbol with ':' -> '_') as a DataFrame.

    Two file layouts are accepted, detected from the header:
      * clean library format: columns date (ISO), open, high, low, close, volume[, source]
      * raw TradingView export: a `time` column (unix seconds or ISO) plus open/high/low/close[/volume]
    Unix times are turned into session dates in `date_tz` (default New York, right for US symbols).
    Returns float columns open/high/low/close/volume with a DatetimeIndex named 'date'.
    """
    path = data_path(data_dir) / _file_name(symbol)
    if not path.exists():
        raise FileNotFoundError(f"{symbol}: expected file {path} (see data/README.md, or set {ENV_DATA})")
    df, fmt = _read_prices(path, date_tz)
    df.attrs.update(symbol=symbol, file=str(path), format=fmt)
    return df


def close(symbol, data_dir=None, date_tz="America/New_York"):
    """Closing prices as a float64 Series named after the symbol. Raises on non-finite or non-positive values."""
    df = load_prices(symbol, data_dir, date_tz)
    s = df["close"].astype("float64").rename(symbol)
    if not np.isfinite(s.values).all() or (s.values <= 0).any():
        raise ValueError(f"{symbol}: non-finite or non-positive closes")
    s.attrs.update(symbol=symbol, file=df.attrs["file"], format=df.attrs["format"])
    return s


def check_gaps(index, max_gap_days=7):
    """Raise if two consecutive rows are more than max_gap_days calendar days apart.

    Why: period ends (week / month / quarter) are found as "the last row of the period". If a row were missing,
    the day before the hole would be mistaken for a period end. The 2001 closure (last row 2001-09-10, next row
    2001-09-17) is 7 calendar days, so it passes.

    Limit of this check: it cannot see ONE missing weekday (a Wednesday missing between Tuesday and Thursday is
    only a 2-day gap). `check_missing_weekdays` covers that, roughly.
    """
    idx = pd.DatetimeIndex(index)
    if len(idx) < 2:
        return
    gaps = np.diff(idx.values).astype("timedelta64[D]").astype(int)
    big = np.flatnonzero(gaps > max_gap_days)
    if big.size:
        i = int(big[0])
        raise ValueError(f"gap of {int(gaps[i])} calendar days between {idx[i].date()} and {idx[i + 1].date()} "
                         f"(limit {max_gap_days}); a missing row could be mistaken for a period end")


# A normal US trading year has about 250-253 rows. Measured on the real files (S&P 500 1950-2026, Nasdaq-100
# 1985-2026, full calendar years only), the lowest counts are:
#   1968: 226 rows (the exchange closed on Wednesdays for part of the year: the "paperwork crisis")  <- exception below
#   2001: 248 rows (the 9/11 closure)   <- lowest NORMAL year, so the default floor sits exactly here
#   1950: 249 rows
# So the default floor is 248 and 1968 gets its own floor (a little under its real 226).
DEFAULT_MIN_ROWS_PER_YEAR = 248
YEAR_FLOOR_EXCEPTIONS = {1968: 225}


def check_missing_weekdays(index, min_rows_per_year=DEFAULT_MIN_ROWS_PER_YEAR, year_floors=None):
    """Raise if any FULL calendar year has fewer rows than the floor (a hint that weekdays are missing).

    Why: a single missing weekday leaves only a 2-day gap, so `check_gaps` cannot see it, yet a missing month-end
    row would silently move a month-end reset. This counts rows per year instead.
    A year counts as "full" if it is strictly inside the data, or if the data start by 7 Jan, or if the data end on
    the year's final weekday (so a file that stops a few days before year-end is not judged for that year: the
    missing sessions would look like missing weekdays).
    `year_floors` maps a year to its own floor (default: {1968: 225}, the Wednesday-closure year).
    Limit: this catches a pile of missing days (about 4 or more in an ordinary year), not a single one.
    """
    idx = pd.DatetimeIndex(index)
    if len(idx) == 0:
        return
    floors = YEAR_FLOOR_EXCEPTIONS if year_floors is None else year_floors
    counts = pd.Series(1, index=idx).groupby(idx.year).sum()
    first, last = idx[0], idx[-1]
    for year, n in counts.items():
        year = int(year)
        if year == first.year and not (first.month == 1 and first.day <= 7):
            continue
        if year == last.year and (last + pd.offsets.BDay(1)).year == last.year:
            continue                              # more weekdays follow in this year: it is not complete yet
        floor = floors.get(year, min_rows_per_year)
        if n < floor:
            raise ValueError(f"year {year} has only {int(n)} rows (floor {floor}); weekdays look missing, "
                             "so a period-end reset could land on the wrong day")


# ---------------------------------------------------------------- rates

def load_fred(name, data_dir=None):
    """FRED CSV `<rates folder>/<name>.csv` (date, value in PERCENT) -> Series of DECIMAL rates (0.05 = 5%).

    Blank or '.' values (FRED's missing marker) are dropped. FRED data is US-government public data.
    """
    path = rates_path(data_dir) / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{name}: expected FRED file {path} (see data/README.md, or set {ENV_RATES})")
    df = pd.read_csv(path)
    vals = pd.to_numeric(df.iloc[:, 1], errors="coerce").values / 100.0
    s = pd.Series(vals, index=pd.to_datetime(df.iloc[:, 0])).dropna()
    if s.index.duplicated().any() or not s.index.is_monotonic_increasing:
        raise ValueError(f"{name}: bad date index (duplicates or not ascending)")
    if len(s) == 0:
        raise ValueError(f"{name}: file has no values")
    s.name = name
    return s


def _lagged(index, rate):
    """Rate dated on or before the PREVIOUS row of `index`. Row 0 is NaN; rows before the rate starts are NaN."""
    src = rate.sort_index()
    out = src.reindex(src.index.union(index)).ffill().reindex(index)
    return out.shift(1)


def check_rate_holes(rate, index, max_hole_days, name="rate"):
    """Raise if a DAILY rate series has an interior hole longer than max_hole_days calendar days.

    Only holes that overlap the dates in `index` matter (a hole in 1960 is irrelevant to a 2000 backtest).
    DFF is published every calendar day (weekends too); DTB3 on business days (a long weekend is 4-5 days).
    Without this, a missing stretch would be silently filled with the last value before it.
    """
    if max_hole_days is None:
        return
    idx = pd.DatetimeIndex(index)
    d = rate.index
    if len(d) < 2 or len(idx) == 0:
        return
    gaps = np.diff(d.values).astype("timedelta64[D]").astype(int)
    for i in np.flatnonzero(gaps > max_hole_days):
        if d[i + 1] > idx[0] and d[i] < idx[-1]:
            raise ValueError(f"{name}: hole of {int(gaps[i])} calendar days between {d[i].date()} and {d[i + 1].date()} "
                             f"(limit {max_hole_days}); re-download {name}.csv from FRED")


def _stale_rows(index, rate, name, max_stale_rows):
    """Count rows of `index` dated after the rate's last published date (they are forward-filled). Refuse if too many."""
    last = rate.index[-1]
    stale = int((pd.DatetimeIndex(index) > last).sum())
    if max_stale_rows is not None and stale > max_stale_rows:
        raise ValueError(f"{name}: published rate ends {last.date()}, {stale} rows before the end of the price data "
                         f"(limit {max_stale_rows}); refresh {name}.csv from FRED (see data/README.md)")
    return last, stale


def rate_known_before(index, rate, name="rate", max_stale_rows=15, max_hole_days=None):
    """Rate for each row using only values dated before that row (no same-day look-ahead).

    An overnight rate set on day t-1 is what accrues over t-1 -> t. The first row has no earlier row; it accrues
    nothing, so it is filled with the first available value. Raises if any value is still missing.
    The result carries attrs['rate_last_date'] (last published date) and attrs['stale_rows'] (rows after it, which
    were forward-filled). More than `max_stale_rows` stale rows raises, naming `name` as the file to refresh.
    `max_hole_days` (default off here; cash_rate / reference_rate turn it on) refuses interior holes in a daily series.
    """
    index = pd.DatetimeIndex(index)
    check_rate_holes(rate.sort_index(), index, max_hole_days, name)
    last, stale = _stale_rows(index, rate.sort_index(), name, max_stale_rows)
    out = _lagged(index, rate)
    if out.isna().iloc[0] and out.notna().any():
        out.iloc[0] = out.dropna().iloc[0]
    if out.isna().any():
        raise ValueError(f"rate has no value before {out[out.isna()].index[0].date()}")
    out.attrs["rate_last_date"] = str(last.date())
    out.attrs["stale_rows"] = stale
    return out


def tb3ms_prior_month(tb):
    """TB3MS (monthly average, dated the 1st) moved forward one month: the value dated 1951-02-01 is the JANUARY
    average and a value dated 1951-03-01 is the FEBRUARY average.

    Why: a month's average is only known at the end of that month. Using it from the 2nd day of its own month would
    look into the future. A private financing kit uses the same "prior month" idea but aligns
    on or before the same date with no row lag; here the usual one-row lag is applied on top, so the first trading
    day of each month still sees the month before last. One row more conservative than letf, never look-ahead.
    """
    s = tb.copy()
    s.index = s.index + pd.DateOffset(months=1)
    return s


def reference_rate(index, data_dir=None, max_stale_rows=15, max_hole_days=10):
    """Financing reference rate for each row: effective fed funds (DFF), known the day before.

    DFF starts 1954-07-01. Rows before that use TB3MS (monthly 3-month T-bill) as a PROXY, moved forward one month
    first (see tb3ms_prior_month) so a month's average is never used inside its own month. The result carries
    attrs['proxy_rows'] (how many rows used the proxy), attrs['proxy_until'] (the last such date, or None) and
    attrs['proxy_rule'] so tables can flag those years; also attrs['rate_last_date'] (last DFF date) and
    attrs['stale_rows'] (rows after it, forward-filled). Refuses more than `max_stale_rows` stale rows or an
    interior DFF hole longer than `max_hole_days` calendar days, naming DFF.csv as the file to refresh.
    """
    index = pd.DatetimeIndex(index)
    dff = load_fred("DFF", data_dir)
    check_rate_holes(dff, index, max_hole_days, "DFF")
    dff_last, stale = _stale_rows(index, dff, "DFF", max_stale_rows)
    lag = _lagged(index, dff)
    proxy = lag.isna().to_numpy().copy()
    if proxy[0] and dff.index[0] <= index[0] and lag.notna().any():
        # DFF existed on day 1; only the lag leaves row 0 empty. Fill it exactly like rate_known_before does.
        lag.iloc[0] = lag.dropna().iloc[0]
        proxy[0] = False
    if proxy.any():
        try:
            tb = tb3ms_prior_month(load_fred("TB3MS", data_dir))
        except FileNotFoundError as e:
            raise ValueError(f"rows before DFF starts ({dff.index[0].date()}) need TB3MS as a proxy: {e}") from e
        tb_lag = _lagged(index, tb)
        if tb_lag.isna().iloc[0] and tb.index[0] <= index[0] and tb_lag.notna().any():
            tb_lag.iloc[0] = tb_lag.dropna().iloc[0]
        lag = lag.where(~proxy, tb_lag)
    if lag.isna().any():
        raise ValueError(f"no DFF or TB3MS value before {lag[lag.isna()].index[0].date()}")
    lag.name = "reference_rate"
    lag.attrs["proxy_rows"] = int(proxy.sum())
    lag.attrs["proxy_until"] = str(index[proxy][-1].date()) if proxy.any() else None
    lag.attrs["source"] = "FRED DFF (effective fed funds), lagged one row; TB3MS proxy where DFF is not yet published"
    lag.attrs["proxy_rule"] = ("TB3MS monthly average shifted forward one month (month t uses month t-1's average), "
                               "then lagged one row")
    lag.attrs["rate_last_date"] = str(dff_last.date())
    lag.attrs["stale_rows"] = stale
    return lag


def cash_rate(index, data_dir=None, max_stale_rows=15, max_hole_days=10):
    """What cash earns in strategy tests: FRED DTB3 (3-month T-bill), known the day before.

    Same stale-tail and interior-hole refusals as reference_rate (the file to refresh is DTB3.csv).
    """
    out = rate_known_before(index, load_fred("DTB3", data_dir), "DTB3", max_stale_rows, max_hole_days)
    out.name = "cash_rate"
    out.attrs["source"] = "FRED DTB3 (3-month T-bill), lagged one row"
    return out
