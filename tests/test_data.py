"""Tests for the data layer (loader.py and series.py), on made-up data only. No real files are needed.

Each test writes small CSVs into a temporary folder and points `data_dir` at it. Test code runs when this file is
imported, like the other test files; `check` and `raises` come from tests/_harness.py.
"""
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from _harness import check, raises  # noqa: E402
from calendar_letf import loader, series  # noqa: E402

# A user's shell may have these set; the tests must not depend on them.
os.environ.pop(loader.ENV_DATA, None)
os.environ.pop(loader.ENV_RATES, None)

TMP = Path(tempfile.mkdtemp(prefix="cletf_data_test_"))


def write_clean(folder, symbol, close, extra=None):
    """Write a clean-format file (date,open,high,low,close,volume,source)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"date": [d.strftime("%Y-%m-%d") for d in close.index], "open": close.values,
                       "high": close.values * 1.01, "low": close.values * 0.99, "close": close.values,
                       "volume": 1000.0, "source": "made-up"})
    if extra is not None:
        df = extra(df)
    df.to_csv(folder / loader._file_name(symbol), index=False)


def walk(start, end, seed, level=100.0, vol=0.01):
    ix = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    return pd.Series(level * np.exp(np.cumsum(rng.normal(0, vol, len(ix)))), index=ix)


# ---------- 1. price files ----------
px = walk("2020-01-01", "2020-06-30", 1)
d1 = TMP / "formats"
write_clean(d1, "SP:SPX", px)
# the same data as a raw TradingView export: unix seconds at 14:30 UTC (10:30 New York, same session date)
raw = pd.DataFrame({"time": [int((d + pd.Timedelta(hours=14, minutes=30)).timestamp()) for d in px.index],
                    "open": px.values, "high": px.values * 1.01, "low": px.values * 0.99, "close": px.values,
                    "Volume": 1000.0})
raw.to_csv(d1 / "RAW_X_daily.csv", index=False)
a = loader.load_prices("SP:SPX", d1)
b = loader.load_prices("RAW:X", d1)
check("loader: file name for 'SP:SPX' is SP_SPX_daily.csv", Path(a.attrs["file"]).name == "SP_SPX_daily.csv")
check("loader: formats are detected from the header", a.attrs["format"] == "clean" and b.attrs["format"] == "tradingview_raw")
check("loader: clean and raw TradingView files load identically",
      a.index.equals(b.index) and np.allclose(a.values, b.values, equal_nan=True, rtol=0, atol=1e-12))
check("loader: columns and index name", list(a.columns) == loader.PRICE_COLS and a.index.name == "date"
      and (a.dtypes == "float64").all())
check("loader: close() is float64 and named after the symbol",
      loader.close("SP:SPX", d1).dtype == "float64" and loader.close("SP:SPX", d1).name == "SP:SPX")
raises("loader: missing file raises", lambda: loader.load_prices("NOPE:NOPE", d1), "expected file")
raises("loader: unix time without a timezone is refused",
       lambda: loader._read_prices(d1 / "RAW_X_daily.csv", None), "date_tz")

# environment variable selects the folder
os.environ[loader.ENV_DATA] = str(d1)
check("loader: CALENDAR_LETF_DATA is honoured", len(loader.load_prices("SP:SPX")) == len(px))
os.environ.pop(loader.ENV_DATA)

# bad files
dup = px.iloc[:10].copy()
write_clean(TMP / "bad", "DUP:X", dup, extra=lambda df: pd.concat([df, df.iloc[[3]]], ignore_index=True))
raises("loader: duplicate dates raise", lambda: loader.load_prices("DUP:X", TMP / "bad"), "duplicate")
write_clean(TMP / "bad", "UNS:X", px.iloc[:10], extra=lambda df: df.iloc[[0, 2, 1, 3, 4, 5, 6, 7, 8, 9]])
raises("loader: dates out of order raise", lambda: loader.load_prices("UNS:X", TMP / "bad"), "ascending")
bad_close = px.iloc[:10].copy()
bad_close.iloc[4] = 0.0
write_clean(TMP / "bad", "ZER:X", bad_close)
raises("loader: a zero close raises", lambda: loader.load_prices("ZER:X", TMP / "bad"), "non-positive")
bad_close.iloc[4] = -5.0
write_clean(TMP / "bad", "NEG:X", bad_close)
raises("loader: a negative close raises", lambda: loader.close("NEG:X", TMP / "bad"), "non-positive")
write_clean(TMP / "bad", "NAN:X", px.iloc[:10], extra=lambda df: df.assign(close=[*df["close"].iloc[:4], np.nan, *df["close"].iloc[5:]]))
raises("loader: a missing close raises", lambda: loader.load_prices("NAN:X", TMP / "bad"), "non-positive")
write_clean(TMP / "bad", "DAT:X", px.iloc[:10], extra=lambda df: df.assign(date=["01/02/2020"] + list(df["date"].iloc[1:])))
raises("loader: a day-first date (01/02/2020 = 1 Feb) that breaks the order raises", lambda: loader.load_prices("DAT:X", TMP / "bad"), "ascending")
write_clean(TMP / "bad", "DMY:X", px.iloc[:3], extra=lambda df: df.assign(date=["13/01/2020", "14/01/2020", "15/01/2020"]))
check("loader: day-first dates are read day first", loader.load_prices("DMY:X", TMP / "bad").index[0] == pd.Timestamp("2020-01-13"))

# ---------- 2. gaps ----------
ix_ok = pd.DatetimeIndex(["2001-09-10", "2001-09-17", "2001-09-18"])      # the real 2001 closure: 7 days Mon->Mon
ix_6 = pd.DatetimeIndex(["2001-09-10", "2001-09-16", "2001-09-17"])       # exactly 6 days
ix_8 = pd.DatetimeIndex(["2020-01-02", "2020-01-03", "2020-01-11", "2020-01-13"])
try:
    loader.check_gaps(ix_6)
    loader.check_gaps(ix_ok)
    ok_pass = True
except ValueError:
    ok_pass = False
check("check_gaps: 6-day and 7-day gaps pass (2001-09-11 closure)", ok_pass)
raises("check_gaps: an 8-day gap raises and names the first gap", lambda: loader.check_gaps(ix_8), "2020-01-03 and 2020-01-11")

# ---------- 3. the one-row rate lag ----------
ix = pd.bdate_range("2020-03-02", "2020-03-31")
rate = pd.Series(0.01, index=pd.date_range("2020-03-01", "2020-03-31"))
rate.loc["2020-03-15":] = 0.05                                    # jump on the 15th (a Sunday)
rate2 = pd.Series(0.01, index=pd.date_range("2020-03-01", "2020-03-31"))
rate2.loc["2020-03-12":] = 0.05                                   # jump on Thursday the 12th
lag = loader.rate_known_before(ix, rate2)
check("rate lag: a jump on the 12th is first used on the next row (the 13th)",
      lag.loc["2020-03-12"] == 0.01 and lag.loc["2020-03-13"] == 0.05)
lag15 = loader.rate_known_before(pd.DatetimeIndex(["2020-03-13", "2020-03-14", "2020-03-15", "2020-03-16", "2020-03-17"]), rate)
check("rate lag: a jump on the 15th is first used on the 16th",
      list(lag15.values) == [0.01, 0.01, 0.01, 0.05, 0.05], str(list(lag15.values)))
check("rate lag: first row is filled with the first available value", lag.iloc[0] == 0.01 and not lag.isna().any())
raises("rate lag: a missing value raises", lambda: loader.rate_known_before(pd.DatetimeIndex(["2019-01-01", "2019-01-02"]),
                                                                          pd.Series([0.01], index=pd.DatetimeIndex(["2020-01-01"]))),
       "no value before")

# ---------- 4. reference rate with proxy ----------
rd = TMP / "rates_case"
(rd / "rates").mkdir(parents=True)
dff_ix = pd.bdate_range("2000-03-01", "2000-05-31")
pd.DataFrame({"observation_date": dff_ix.strftime("%Y-%m-%d"), "DFF": np.where(dff_ix < "2000-04-15", 6.0, 6.5)}).to_csv(rd / "rates" / "DFF.csv", index=False)
pd.DataFrame({"observation_date": ["2000-01-01", "2000-02-01", "2000-03-01", "2000-04-01", "2000-05-01"],
              "TB3MS": [5.0, 5.1, 5.2, 5.3, 5.4]}).to_csv(rd / "rates" / "TB3MS.csv", index=False)
pd.DataFrame({"observation_date": ["2000-02-01", "2000-04-03"], "DTB3": ["5.5", "."]}).to_csv(rd / "rates" / "DTB3.csv", index=False)
idx = pd.bdate_range("2000-02-14", "2000-05-12")
ref = loader.reference_rate(idx, rd)
n_proxy = int((idx <= "2000-03-01").sum())          # row on 03-01 still looks back to 02-29, before DFF existed
check("reference_rate: proxy_rows counts rows before DFF can be known", ref.attrs["proxy_rows"] == n_proxy, f"{ref.attrs['proxy_rows']} vs {n_proxy}")
check("reference_rate: proxy_until is the last proxy date", ref.attrs["proxy_until"] == "2000-03-01")
# TB3MS is a monthly AVERAGE dated the 1st: the Feb value (5.1) is only known after February, so Feb rows get the
# January value (5.0) and March rows get Feb's. (This was a same-month look-ahead before the S1 audit fix.)
check("reference_rate: proxy rows use TB3MS of the PRIOR month, then lagged one row",
      abs(ref.loc["2000-02-15"] - 0.050) < 1e-12 and abs(ref.loc["2000-03-01"] - 0.050) < 1e-12)
check("reference_rate: attrs record the proxy rule and the last DFF date",
      "one month" in ref.attrs["proxy_rule"] and ref.attrs["rate_last_date"] == "2000-05-31" and ref.attrs["stale_rows"] == 0)
check("reference_rate: after DFF starts it is DFF lagged one row",
      abs(ref.loc["2000-03-02"] - 0.06) < 1e-12 and abs(ref.loc["2000-04-17"] - 0.06) < 1e-12 and abs(ref.loc["2000-04-18"] - 0.065) < 1e-12,
      f"{ref.loc['2000-04-17']} {ref.loc['2000-04-18']}")
check("reference_rate: no missing values", not ref.isna().any())
ref_late = loader.reference_rate(pd.bdate_range("2000-04-03", "2000-04-28"), rd)
check("reference_rate: no proxy rows when the index starts after DFF", ref_late.attrs["proxy_rows"] == 0 and ref_late.attrs["proxy_until"] is None)
(rd2 := TMP / "rates_notb").mkdir()
(rd2 / "rates").mkdir()
pd.read_csv(rd / "rates" / "DFF.csv").to_csv(rd2 / "rates" / "DFF.csv", index=False)
raises("reference_rate: proxy needed but TB3MS missing raises", lambda: loader.reference_rate(idx, rd2), "TB3MS")
cash = loader.cash_rate(pd.bdate_range("2000-02-14", "2000-02-18"), rd)
check("cash_rate: DTB3 lagged, FRED '.' dropped", abs(cash.iloc[-1] - 0.055) < 1e-12)
check("cash_rate: attrs record the last published date and stale rows (5 index rows after 2000-02-01)",
      cash.attrs["rate_last_date"] == "2000-02-01" and cash.attrs["stale_rows"] == 5)
os.environ[loader.ENV_RATES] = str(rd / "rates")
check("rates: CALENDAR_LETF_RATES overrides the rates folder", loader.rates_path(TMP / "elsewhere") == rd / "rates")
os.environ.pop(loader.ENV_RATES)
check("rates: default is <data_dir>/rates", loader.rates_path(rd) == rd / "rates")

# ---------- 5. dividend accrual ----------
flat = pd.Series(100.0, index=pd.bdate_range("2000-01-03", "2019-12-31"))
y = 0.03
lvl = series._accrue(flat, pd.Series(y, index=flat.index))
years = (flat.index[-1] - flat.index[0]).days / 365.0
check("accrue: flat 3% yield on a flat index compounds to exp(y x years) within 0.5%",
      abs(lvl.iloc[-1] / np.exp(y * years) - 1) < 0.005, f"{lvl.iloc[-1]:.4f} vs {np.exp(y * years):.4f}")
check("accrue: first day is 1.0", lvl.iloc[0] == 1.0)

# ---------- 6. S&P 500 splice ----------
spx = walk("1985-01-02", "1992-12-31", 7, level=170.0)
pub_start = pd.Timestamp("1988-01-04")
gap_day = spx.index[spx.index > pub_start][50]                       # a day SPX has and SPXTR lacks
tr_pub = (spx.loc[pub_start:] * np.exp(np.linspace(0, 0.3, (spx.index >= pub_start).sum())) * 3.7).drop(gap_day)
d2 = TMP / "spx"
write_clean(d2, "SP:SPX", spx)
write_clean(d2, "SP:SPXTR", tr_pub)
out = series.spx_total_return(pre_yield=0.03, data_dir=d2)
post = out.loc[pub_start:].drop(gap_day)
ratio = post / tr_pub
check("SPX TR: equals the published series times a constant after the splice (1e-12)",
      (ratio / ratio.iloc[0] - 1).abs().max() < 1e-12, f"{(ratio / ratio.iloc[0] - 1).abs().max():.2e}")
check("SPX TR: on SPX's calendar, 1.0 on day one, no NaN", out.index.equals(spx.index) and out.iloc[0] == 1.0 and not out.isna().any())
check("SPX TR: the missing SPXTR day is carried by SPX's move and listed in attrs",
      out.attrs["days_filled_from_price"] == [str(gap_day.date())]
      and abs(out.loc[gap_day] / out.shift(1).loc[gap_day] - spx.loc[gap_day] / spx.shift(1).loc[gap_day]) < 1e-12)
check("SPX TR: attrs record yield, status and splice date",
      out.attrs["pre_yield"] == 0.03 and out.attrs["pre_yield_status"] == "ASSUMED" and out.attrs["splice_date"] == "1988-01-04"
      and out.attrs["basis"] == "constructed")
sat = pd.Timestamp("1988-03-12")                                     # a Saturday: SPX has no row
stale = pd.concat([tr_pub, pd.Series([tr_pub.loc["1988-03-11"]], index=[sat])]).sort_index()
write_clean(TMP / "spx_stale", "SP:SPX", spx)
write_clean(TMP / "spx_stale", "SP:SPXTR", stale)
o_st = series.spx_total_return(pre_yield=0.03, data_dir=TMP / "spx_stale")      # same flat yield as `out`, to compare like with like
check("SPX TR: a flat published row on a non-trading day is dropped and listed",
      o_st.index.equals(spx.index) and o_st.attrs["published_stale_days_dropped"] == ["1988-03-12"]
      and (o_st - out).abs().max() < 1e-12)
moving = stale.copy()
moving.loc[sat] *= 1.01
write_clean(TMP / "spx_mov", "SP:SPX", spx)
write_clean(TMP / "spx_mov", "SP:SPXTR", moving)
raises("SPX TR: a MOVING published value on a non-trading day raises", lambda: series.spx_total_return(pre_yield=0.03, data_dir=TMP / "spx_mov"), "does not trade")
zero = series.spx_total_return(pre_yield=0.0, data_dir=d2)
pre = zero.loc[:pub_start]
r2 = pre / spx.loc[:pub_start]
check("SPX TR: zero yield -> pre-splice part is the price index times a constant (1e-12)",
      (r2 / r2.iloc[0] - 1).abs().max() < 1e-12)
hi = series.spx_total_return(pre_yield=0.04, data_dir=d2)
check("SPX TR: a higher assumed yield grows the level more by the splice date (1.0 on day one in both)",
      hi.iloc[0] == 1.0 and hi.loc[pub_start] > out.loc[pub_start] > zero.loc[pub_start])
check("banner: names the status and splice", "ASSUMED" in series.banner(out) and "1988-01-04" in series.banner(out))
check("banner: price series says price only", "price index only" in series.banner(series.underlying("SPX", "price", d2)))

# ---------- 7. Nasdaq-100 construction ----------
ndx = walk("2004-01-02", "2012-12-31", 11, level=1500.0)
x_start = pd.Timestamp("2010-01-04")
sandy = pd.Timestamp("2012-10-31")
xn_vals = ndx.loc[x_start:] * np.exp(np.linspace(0, 0.1, (ndx.index >= x_start).sum())) * 0.9
xn = xn_vals.drop(sandy)
# a few early XNDX rows (2006-11-08 .. 2010) exist in the real file; they must be ignored apart from trust_from
xn_early = ndx.loc["2006-11-08":"2009-12-31"] * 0.5
d3 = TMP / "ndx"
write_clean(d3, "NASDAQ:NDX", ndx)
write_clean(d3, "NASDAQ:XNDX", pd.concat([xn_early, xn]))
nt = series.ndx_total_return(data_dir=d3)
ratio = nt.loc[x_start:].drop(sandy) / xn
check("NDX TR: equals the published XNDX times a constant from 2010-01-04 (1e-12)", (ratio / ratio.iloc[0] - 1).abs().max() < 1e-12)
check("NDX TR: Sandy-style missing day is filled and listed", nt.attrs["days_filled_from_ndx"] == [str(sandy.date())])
check("NDX TR: on NDX's calendar and starts at 1.0", nt.index.equals(ndx.index) and nt.iloc[0] == 1.0)
nz = series.ndx_total_return(pre_yield=0.0, mid_yield=0.0, data_dir=d3)
rz = nz.loc[:x_start] / ndx.loc[:x_start]
check("NDX TR: zero yields -> pre-splice part is the price index times a constant (1e-12)", (rz / rz.iloc[0] - 1).abs().max() < 1e-12)
# one expected value by hand: between 2006-11-08 and the splice the growth is price x (1 + 0.73% x days/365)
seg = nt.loc["2008-03-03":"2008-03-04"]
expect = ndx.loc["2008-03-04"] / ndx.loc["2008-03-03"] * (1 + series.MID_YIELD * 1 / 365)
check("NDX TR: mid-period daily growth = price move x (1 + 0.73% x days/365)", abs(seg.iloc[1] / seg.iloc[0] - expect) < 1e-12)
seg = nt.loc["2005-03-03":"2005-03-04"]
expect = ndx.loc["2005-03-04"] / ndx.loc["2005-03-03"] * (1 + series.NDX_PRE_YIELD * 1 / 365)
check("NDX TR: early daily growth = price move x (1 + 0.3% x days/365)", abs(seg.iloc[1] / seg.iloc[0] - expect) < 1e-12)
raises("NDX TR: trust_from must be an XNDX trading day", lambda: series.ndx_total_return(trust_from="2010-01-02", data_dir=d3), "trading day")
check("underlying(): names and basis", series.underlying("NDX", "total_return", d3).name == "NDX_TR"
      and series.underlying("SPX", "total_return", d2).name == "SPX_TR" and series.underlying("NDX", "price", d3).name == "NDX")
raises("underlying(): bad name raises", lambda: series.underlying("DJI", "price", d3), "must be SPX or NDX")
check("banner: NDX banner shows both yields", "0.73%" in series.banner(nt) and "0.30%" in series.banner(nt))

# a data folder with a hole bigger than a week must be refused by the price loaders used for period ends
holey = spx.drop(spx.index[100:106])
write_clean(TMP / "holey", "SP:SPX", holey)
raises("series: spx_price refuses a data hole over 7 days", lambda: series.spx_price(TMP / "holey"), "gap of")

# ---------- 8. data banner ----------
db = series.data_banner(d2)
check("data_banner: lists files with dates and source values", "SP_SPX_daily.csv" in db and "made-up" in db and "1985-01-02" in db)

# ---------- 9. S1 audit fixes: decade-map yield, missing weekdays, silent tails, stale/holey rates, month shift ----------
# 9a. S&P 500 dividend yield by decade (flat price, so the whole move is the assumed yield)
check("decade map: values copied from letf (4.2, 3.1, 4.0, 3.7 % for the 1950s-1980s)",
      [series.SPX_YIELD_BY_DECADE[k] for k in (1950, 1960, 1970, 1980)] == [0.042, 0.031, 0.040, 0.037]
      and series.SPX_YIELD_STATUS == "ASSUMED")
flat_ix = pd.bdate_range("1962-01-02", "1992-12-31")
d9 = TMP / "spx_flat"
write_clean(d9, "SP:SPX", pd.Series(100.0, index=flat_ix))
write_clean(d9, "SP:SPXTR", pd.Series(400.0, index=flat_ix[flat_ix >= "1988-01-04"]))
fl = series.spx_total_return(pre_yield=None, data_dir=d9)      # pre_yield=None = the decade map (a sensitivity since B7; the default is Shiller)


def year_growth(level, a, b):
    """Level growth between two dates, and the number of calendar days between them."""
    return level.loc[b] / level.loc[a], (pd.Timestamp(b) - pd.Timestamp(a)).days


g65, days65 = year_growth(fl, "1965-01-04", "1965-12-31")
g75, days75 = year_growth(fl, "1975-01-02", "1975-12-31")
g85, days85 = year_growth(fl, "1985-01-02", "1985-12-31")
check("decade map: growth inside the 1960s uses the 1960s yield (3.1%)", abs(g65 / np.exp(0.031 * days65 / 365) - 1) < 1e-4, g65)
check("decade map: growth inside the 1970s uses the 1970s yield (4.0%)", abs(g75 / np.exp(0.040 * days75 / 365) - 1) < 1e-4, g75)
check("decade map: growth inside the 1980s uses the 1980s yield (3.7%)", abs(g85 / np.exp(0.037 * days85 / 365) - 1) < 1e-4, g85)
check("decade map: attrs say decade_map, carry the map and the ASSUMED status",
      fl.attrs["pre_yield"] == "decade_map" and fl.attrs["pre_yield_map"] == series.SPX_YIELD_BY_DECADE
      and fl.attrs["pre_yield_status"] == "ASSUMED")
check("decade map: the banner names it", "decade-map" in series.banner(fl) and "1960s 3.1%" in series.banner(fl))
flat3 = series.spx_total_return(pre_yield=0.03, data_dir=d9)
g65f, _ = year_growth(flat3, "1965-01-04", "1965-12-31")
check("flat yield option still works and records the float", abs(g65f / np.exp(0.03 * days65 / 365) - 1) < 1e-4
      and flat3.attrs["pre_yield"] == 0.03 and flat3.attrs["pre_yield_map"] is None)
check("decade map: no trailing fill on a complete SPXTR file", fl.attrs["trailing_rows_filled_from_price"] == 0)

# 9b. missing weekdays
full_ix = pd.bdate_range("1990-01-01", "1992-12-31")
loader.check_missing_weekdays(full_ix)
check("check_missing_weekdays: a full run of years passes", True)
ix240 = full_ix.drop(full_ix[full_ix.year == 1991][::12][:21])              # 21 scattered single days gone: 1991 has 240 rows
check("check_missing_weekdays: (test setup) 1991 has 240 rows and the 7-day gap check does NOT notice",
      (ix240.year == 1991).sum() == 240 and loader.check_gaps(ix240) is None, (ix240.year == 1991).sum())
raises("check_missing_weekdays: a year with 240 rows raises and names year and count",
       lambda: loader.check_missing_weekdays(ix240), "year 1991 has only 240")
loader.check_missing_weekdays(pd.bdate_range("1990-06-01", "1990-09-30"))
check("check_missing_weekdays: a partial first/last year is not judged", True)
y68 = pd.bdate_range("1967-01-02", "1969-12-31")
n68 = int((y68.year == 1968).sum())
loader.check_missing_weekdays(y68.drop(y68[y68.year == 1968][:n68 - 226]))   # 1968 down to 226 rows: its own floor
check("check_missing_weekdays: 1968 (Wednesday closures, 226 real rows) has its own lower floor", True)
raises("check_missing_weekdays: even 1968 has a floor",
       lambda: loader.check_missing_weekdays(y68.drop(y68[y68.year == 1968][:n68 - 215])), "year 1968")
sc = pd.bdate_range("1986-01-01", "1990-12-31")
sc_bad = sc.drop(sc[sc.year == 1988][::12][:21])
write_clean(TMP / "scatter", "SP:SPX", pd.Series(100.0, index=sc_bad))
write_clean(TMP / "scatter", "NASDAQ:NDX", pd.Series(100.0, index=sc_bad))
raises("series: spx_price refuses scattered missing weekdays", lambda: series.spx_price(TMP / "scatter"), "weekdays look missing")
raises("series: ndx_price refuses scattered missing weekdays", lambda: series.ndx_price(TMP / "scatter"), "weekdays look missing")

# 9c. trailing fill at the END of the series
for n_short in (5, 12):
    write_clean(TMP / f"tail{n_short}", "SP:SPX", spx)
    write_clean(TMP / f"tail{n_short}", "SP:SPXTR", tr_pub.iloc[:-n_short])
t5 = series.spx_total_return(data_dir=TMP / "tail5")
check("trailing fill: 5 missing end rows are counted separately and carried by the price move",
      t5.attrs["trailing_rows_filled_from_price"] == 5 and len(t5.attrs["days_filled_from_price"]) == 6
      and t5.index.equals(spx.index) and not t5.isna().any())
check("trailing fill: banner prints the trailing count", "LAST 5 rows" in series.banner(t5))
check("trailing fill: an isolated interior gap is NOT counted as trailing", out.attrs["trailing_rows_filled_from_price"] == 0)
raises("trailing fill: 12 missing end rows (> 10) is refused and says to re-export",
       lambda: series.spx_total_return(data_dir=TMP / "tail12"), "re-export")
raises("trailing fill: the limit is an argument", lambda: series.spx_total_return(max_trailing_fill=3, data_dir=TMP / "tail5"), "ends 5 rows before")
write_clean(TMP / "ndxtail", "NASDAQ:NDX", ndx)
write_clean(TMP / "ndxtail", "NASDAQ:XNDX", pd.concat([xn_early, xn.iloc[:-15]]))
raises("trailing fill: NDX total return is guarded the same way", lambda: series.ndx_total_return(data_dir=TMP / "ndxtail"), "re-export")

# 9e. the published series is FRESHER than the price file (re-exported after the price file's last top-up): rows
#     after the price file's last date carry nothing for a series on the price calendar, so they are dropped and
#     listed, not refused. A moving value INSIDE the price range on a non-trading day still raises (test 9a above).
ahead_ix = pd.bdate_range(spx.index[-1] + pd.Timedelta(days=1), periods=2)
ahead = pd.concat([tr_pub, pd.Series([tr_pub.iloc[-1] * 1.01, tr_pub.iloc[-1] * 1.02], index=ahead_ix)])
write_clean(TMP / "spx_ahead", "SP:SPX", spx)
write_clean(TMP / "spx_ahead", "SP:SPXTR", ahead)
ah = series.spx_total_return(pre_yield=0.03, data_dir=TMP / "spx_ahead")
check("fresher published file: 2 rows after the price file's end are dropped and listed, and the series equals the plain run",
      ah.attrs["published_rows_after_price_end"] == [str(d.date()) for d in ahead_ix] and ah.index.equals(spx.index)
      and np.allclose(ah.values, out.values, rtol=0, atol=1e-12), ah.attrs.get("published_rows_after_price_end"))
check("fresher published file: the banner says so and tells the reader to top up the price file",
      "after the price file" in series.banner(ah) and "top up" in series.banner(ah))

# 9d. stale rates (published series ends before the price data)
idx_s = pd.bdate_range("2000-04-03", "2000-06-09")                          # DFF last date is 2000-05-31: 7 rows after
rs = loader.reference_rate(idx_s, rd)
check("stale rate: reference_rate records the last DFF date and counts forward-filled rows",
      rs.attrs["rate_last_date"] == "2000-05-31" and rs.attrs["stale_rows"] == 7, str(rs.attrs))
raises("stale rate: more than 15 stale rows is refused and names DFF.csv",
       lambda: loader.reference_rate(pd.bdate_range("2000-04-03", "2000-06-30"), rd), "DFF.csv")
raises("stale rate: the limit is an argument", lambda: loader.reference_rate(idx_s, rd, max_stale_rows=3), "DFF.csv")
raises("stale rate: cash_rate refuses too and names DTB3.csv",
       lambda: loader.cash_rate(pd.bdate_range("2000-02-14", "2000-04-14"), rd), "DTB3.csv")

# 9e. interior hole in a daily rate series
dff_hole = dff_ix.drop(dff_ix[(dff_ix >= "2000-04-03") & (dff_ix <= "2000-04-18")])     # 16-day hole
hd = TMP / "rates_hole"
(hd / "rates").mkdir(parents=True)
pd.DataFrame({"observation_date": dff_hole.strftime("%Y-%m-%d"), "DFF": 6.0}).to_csv(hd / "rates" / "DFF.csv", index=False)
pd.DataFrame({"observation_date": ["2000-01-01"], "TB3MS": [5.0]}).to_csv(hd / "rates" / "TB3MS.csv", index=False)
raises("rate hole: a 16-day hole inside the dates being used raises",
       lambda: loader.reference_rate(pd.bdate_range("2000-03-06", "2000-05-12"), hd), "hole of")
loader.reference_rate(pd.bdate_range("2000-05-01", "2000-05-12"), hd)
check("rate hole: a hole before the first date used is ignored", True)

# 9f. TB3MS month shift (proxy rows only)
rd4 = TMP / "rates_shift"
(rd4 / "rates").mkdir(parents=True)
late = pd.bdate_range("2000-04-03", "2000-05-31")
pd.DataFrame({"observation_date": late.strftime("%Y-%m-%d"), "DFF": 6.0}).to_csv(rd4 / "rates" / "DFF.csv", index=False)
pd.read_csv(rd / "rates" / "TB3MS.csv").to_csv(rd4 / "rates" / "TB3MS.csv", index=False)
sh = loader.reference_rate(pd.bdate_range("2000-02-14", "2000-03-31"), rd4)
check("month shift: no Feb row ever uses the Feb average (5.1); Jan's 5.0 is used in Feb",
      (sh.loc["2000-02-14":"2000-03-01"] == 0.050).all(), str(sh.loc["2000-02-14":"2000-03-02"].unique()))
check("month shift: the Feb average is first used in March (the row after 2000-03-01 under the one-row lag)",
      abs(sh.loc["2000-03-02"] - 0.051) < 1e-12 and abs(sh.loc["2000-03-31"] - 0.051) < 1e-12)
check("month shift: attrs[proxy_rule] says so", "shifted forward one month" in sh.attrs["proxy_rule"])
tbs = loader.tb3ms_prior_month(pd.Series([5.0, 5.1], index=pd.DatetimeIndex(["1951-01-01", "1951-02-01"])))
check("tb3ms_prior_month: the value dated 1951-01-01 is moved to 1951-02-01", tbs.index[0] == pd.Timestamp("1951-02-01") and tbs.iloc[0] == 5.0)
