"""Underlying index series: S&P 500 and Nasdaq-100, as price or total return.

"Price" means the index level alone. "Total return" means price plus reinvested dividends. A leveraged fund earns
a multiple of the TOTAL return, so using a price-only index understates it by roughly L x dividend yield a year.

Where the data does not include a published total-return index we CONSTRUCT one: take the price index and grow
it by a flat, ASSUMED dividend yield (accrued per calendar day), then splice the published series on from the
first date we trust it (for the S&P 500 the assumed yield depends on the decade, see SPX_YIELD_BY_DECADE). The splice is scaled so the result is continuous (no jump on the splice day). Every
constructed series carries `.attrs` saying exactly what was assumed, and `banner(series)` prints it.

Nothing here is a fund NAV; synthetic fund prices are built elsewhere.
"""
from pathlib import Path

import pandas as pd

from . import loader

XNDX_TRUST_FROM = "2010-01-04"   # first date the XNDX daily bars line up with NDX
XNDX_LEVEL_FROM = "2006-11-08"   # XNDX starts here; before XNDX_TRUST_FROM only its LEVEL change is trusted
MID_YIELD = 0.0073               # measured: annual level change of ln(XNDX/NDX) 2006-11-08 -> 2010-01-04
NDX_PRE_YIELD = 0.003            # ASSUMED dividend yield before 2006-11-08
# S&P 500 dividend yield before SPXTR starts (1988-01-04), by decade (key = first year of the decade, value = yield
# per year as a decimal). COPIED from a private financing kit (DECADE_DIV, in
# percent); that kit's register quotes it as "4.2, 3.1, 4.0, 3.7, 2.6, 1.8% ..."
# and records its status as ASSUMED ("rough decade averages"; Shiller monthly dividends would be better). Only the
# 1950s-1980s entries are used here (SPXTR takes over in 1988); the rest are kept so the map matches letf exactly.
SPX_YIELD_BY_DECADE = {1950: 0.042, 1960: 0.031, 1970: 0.040, 1980: 0.037, 1990: 0.026, 2000: 0.018, 2010: 0.020, 2020: 0.015}
SPX_YIELD_STATUS = "ASSUMED"     # status as letf records it (the decade map is now a sensitivity; see SHILLER below)

# Measured monthly S&P 500 dividend yield (trailing 12-month dividends / price) from Robert J. Shiller's "Irrational
# Exuberance" data set (ie_data.xls, Yale; downloaded 2026-10-13, data to 2023-06; monthly dividends are Shiller's
# interpolation of quarterly figures). reference/shiller_sp500_monthly.csv is derived from it: month, price,
# dividend_ttm, dividend_yield. Used before 1988, where no published total-return index exists (BACKLOG B7).
SHILLER_FILE = Path(__file__).resolve().parent.parent / "reference" / "shiller_sp500_monthly.csv"
SHILLER_STATUS = "MEASURED (Shiller monthly D/P; quarterly dividends interpolated to months by the source)"
MAX_TRAILING_FILL = 10           # most rows at the END that may be carried by the price move (see _splice)


# ---------------------------------------------------------------- price series

def spx_price(data_dir=None):
    """S&P 500 price index (SP:SPX) daily close."""
    s = loader.close("SP:SPX", data_dir)
    loader.check_gaps(s.index)               # no hole longer than 7 days
    loader.check_missing_weekdays(s.index)   # no year with too few rows (catches scattered missing weekdays)
    return s.rename("SPX")


def ndx_price(data_dir=None):
    """Nasdaq-100 price index (NASDAQ:NDX) daily close."""
    s = loader.close("NASDAQ:NDX", data_dir)
    loader.check_gaps(s.index)
    loader.check_missing_weekdays(s.index)
    return s.rename("NDX")


PRICE_SYMBOL = {"SPX": "SP:SPX", "NDX": "NASDAQ:NDX"}


def price_low(name, data_dir=None):
    """Daily LOW of the price index ("SPX" or "NDX"), on the same rows as spx_price / ndx_price, for the intraday
    -35% trigger (BACKLOG B4). The early bars of both exports are placeholders with low == close (SPX every row
    before 1962-01-02, NDX before 1985-10-01; measured 2026-10-24); the kernel treats low == close as "no intraday
    information" and tests the close there."""
    if name not in PRICE_SYMBOL:
        raise ValueError(f"price_low: name must be one of {tuple(PRICE_SYMBOL)}, got {name!r}")
    df = loader.load_prices(PRICE_SYMBOL[name], data_dir)
    low = df["low"].astype("float64").rename(f"{name}_low")
    low.attrs.update(symbol=PRICE_SYMBOL[name], file=df.attrs["file"], column="low")
    return low


def spy_price(data_dir=None):
    """SPY ETF price (split-adjusted, not dividend-adjusted). For live-fund validation later."""
    return loader.close("AMEX:SPY", data_dir).rename("SPY")


def qqq_price(data_dir=None):
    """QQQ ETF price (split-adjusted, not dividend-adjusted). For live-fund validation later."""
    return loader.close("NASDAQ:QQQ", data_dir).rename("QQQ")


# ---------------------------------------------------------------- total-return construction

def _accrue(price, yield_by_date):
    """Grow a price series by a dividend yield: level_t = level_{t-1} x (P_t / P_{t-1}) x (1 + y_t x days / 365).

    `yield_by_date` is a Series of annual yields (decimal) on the same index. Calendar-day accrual, so weekends
    and holidays earn their share (the same convention the financing costs use).
    """
    days = pd.Series(price.index, index=price.index).diff().dt.days.fillna(0.0)
    growth = (price / price.shift(1)).fillna(1.0) * (1.0 + yield_by_date * days / 365.0)
    growth.iloc[0] = 1.0
    return growth.cumprod()


def _splice(px, pub, pre_yield, yield_by_date, name, max_trailing_fill=MAX_TRAILING_FILL, refresh_hint="the published series"):
    """Build [synthetic total return up to pub's first date] + [published series from then], on px's calendar.

    Returns (series, filled_days, trailing_rows). Days that `px` has but `pub` lacks are carried by the price
    index's move (the next published bar re-syncs the level) and listed in filled_days (ALL of them, interior and
    trailing). Two kinds exist:
      * isolated interior days (a holiday only one calendar has): harmless, the next published bar re-syncs.
      * TRAILING days at the very end (the published file simply stops earlier): nothing re-syncs them, so the end
        of the series would quietly be price-only. They are counted in trailing_rows and refused above
        `max_trailing_fill`.
    """
    start = pub.index[0]
    if start not in px.index:
        raise ValueError(f"published series starts {start.date()}, which is not a trading day of the price index")
    if pub.index.difference(px.index).size:
        raise ValueError(f"published series has days the price index lacks: "
                         f"{[str(d.date()) for d in pub.index.difference(px.index)[:5]]}")
    built = _accrue(px.loc[:start], yield_by_date.loc[:start])       # synthetic TR up to and including the splice day
    scale = built.iloc[-1] / pub.iloc[0]

    tail_days = px.index[px.index >= start]
    tail = (pub * scale).reindex(tail_days)
    missing = tail_days[tail.isna()]
    filled = [str(d.date()) for d in missing]
    trailing = int((tail_days > pub.index[-1]).sum())
    if trailing > max_trailing_fill:
        raise ValueError(f"{name}: published series ends {trailing} rows before the price series "
                         f"({pub.index[-1].date()} vs {px.index[-1].date()}; limit {max_trailing_fill}); "
                         f"re-export {refresh_hint}")
    if len(missing):
        pr = px.loc[tail_days]
        for d in missing:
            i = tail_days.get_loc(d)
            tail.iloc[i] = tail.iloc[i - 1] * pr.iloc[i] / pr.iloc[i - 1]
    # Bookkeeping check: the days we filled must be exactly the days the two calendars disagree on.
    after = px.index[px.index >= start]
    if not after.difference(pub.index).equals(pd.DatetimeIndex(pd.to_datetime(filled))):
        raise ValueError("internal: filled-day bookkeeping disagrees with the calendar difference")

    out = pd.concat([built.iloc[:-1], tail]).rename(name)
    if out.index.duplicated().any() or not out.index.is_monotonic_increasing or out.isna().any():
        raise ValueError("splice produced a bad date index")
    return out, filled, trailing


def spx_yield_series(index):
    """Yield per row from SPX_YIELD_BY_DECADE (the decade the row's year belongs to). Raises outside the map."""
    decades = (index.year // 10) * 10
    missing = sorted(set(decades) - set(SPX_YIELD_BY_DECADE))
    if missing:
        raise ValueError(f"no S&P 500 dividend yield in SPX_YIELD_BY_DECADE for decade(s) {missing}")
    return pd.Series([SPX_YIELD_BY_DECADE[d] for d in decades], index=index, dtype=float)


def shiller_yield_series(index, path=SHILLER_FILE):
    """Measured dividend yield per row: each trading day gets its calendar month's trailing-12-month D/P from
    Shiller's series. Raises if any month in the range is missing (no silent gaps)."""
    tbl = pd.read_csv(path)
    by_month = dict(zip(tbl["month"], tbl["dividend_yield"].astype(float)))
    months = index.strftime("%Y-%m")
    missing = sorted(set(months) - set(by_month))
    if missing:
        raise ValueError(f"Shiller yield file has no value for month(s) {missing[:5]}{'...' if len(missing) > 5 else ''}")
    return pd.Series([by_month[m] for m in months], index=index, dtype=float)


def spx_total_return(pre_yield="shiller", max_trailing_fill=MAX_TRAILING_FILL, data_dir=None):
    """S&P 500 total-return level on SPX's calendar, 1.0 on the first day.

    From SPXTR's first date (1988-01-04) the published SP:SPXTR is used (scaled to be continuous). Before that
    it is SPX price + a dividend yield:
      * pre_yield="shiller" (default): Shiller's MEASURED monthly dividend yield (reference/shiller_sp500_monthly.csv).
      * pre_yield=None: the decade map SPX_YIELD_BY_DECADE (ASSUMED; the earlier default, kept as a sensitivity).
      * pre_yield=a number (decimal): that flat yield every year (0 / 0.03 / 0.04 are the documented sensitivities).
    The yield only matters before 1988; after the splice all three give the published index.
    The published SPXTR file ends earlier than the SPX price file at times (no MCP feed; it is a manual export):
    up to `max_trailing_fill` trailing rows are carried by the price move and counted in
    attrs['trailing_rows_filled_from_price']; more than that raises.
    """
    px = spx_price(data_dir)
    pub = loader.close("SP:SPXTR", data_dir)
    # SPXTR carries stale rows on the 2001-09-11..14 market closure (the level just repeats). SPX's calendar is the
    # truth, so drop published days SPX lacks, but only when they merely repeat the previous level.
    extra = pub.index.difference(px.index)
    # Rows AFTER the price file's last date mean the published export is simply fresher than the price file (it is
    # a manual export; the price file is topped up separately). They carry nothing for a series on the price
    # calendar, so they are dropped and listed, not refused. Rows INSIDE the price range are the stale-closure case.
    after_end = extra[extra > px.index[-1]]
    extra = extra[extra <= px.index[-1]]
    for d in extra:
        prev = pub.loc[:d].iloc[-2] if len(pub.loc[:d]) > 1 else None
        if prev is None or pub.loc[d] != prev:
            raise ValueError(f"SPXTR has a moving value on {d.date()}, a day SPX does not trade; check the files")
    pub = pub.drop(extra.union(after_end))
    if isinstance(pre_yield, str) and pre_yield == "shiller":
        # _splice accrues the yield up to AND INCLUDING the splice day (the step into the first published row), so the
        # splice day needs its month's yield too; rows after it are never used and carry 0.
        yld, label, status = shiller_yield_series(px.index[px.index <= pub.index[0]]), "shiller", SHILLER_STATUS
        yld = yld.reindex(px.index).fillna(0.0)
    elif pre_yield is None:
        yld, label, status = spx_yield_series(px.index), "decade_map", SPX_YIELD_STATUS
    else:
        yld, label, status = pd.Series(float(pre_yield), index=px.index, dtype=float), float(pre_yield), SPX_YIELD_STATUS
    out, filled, trailing = _splice(px, pub, label, yld, "SPX_TR", max_trailing_fill, "SP:SPXTR (no MCP feed; export it from TradingView)")
    pre = yld[px.index < pub.index[0]]
    out.attrs.update(symbols=["SP:SPX", "SP:SPXTR"], basis="constructed",
                     series="S&P 500 total return (constructed)",
                     splice_date=str(pub.index[0].date()),
                     pre_yield=label, pre_yield_status=status,
                     pre_yield_map=dict(SPX_YIELD_BY_DECADE) if pre_yield is None else None,
                     pre_yield_mean_pct=float(pre.mean() * 100) if len(pre) else None,
                     published_from=str(pub.index[0].date()),
                     published_status="PUBLISHED (SP:SPXTR as exported)",
                     days_filled_from_price=filled,
                     trailing_rows_filled_from_price=trailing,
                     published_stale_days_dropped=[str(d.date()) for d in extra],
                     published_rows_after_price_end=[str(d.date()) for d in after_end])
    return out


def ndx_total_return(pre_yield=NDX_PRE_YIELD, mid_yield=MID_YIELD, trust_from=XNDX_TRUST_FROM,
                     max_trailing_fill=MAX_TRAILING_FILL, data_dir=None):
    """Nasdaq-100 total-return level on NDX's calendar, 1.0 on the first day.

    2010-01-04 on: published NASDAQ:XNDX (the official total-return index).
    2006-11-08 .. 2010: XNDX bars are mis-dated, so only its level change is used: NDX + `mid_yield` (0.73%/yr,
        measured) per year.
    Before 2006-11-08: NDX + `pre_yield` per year (0.3%, ASSUMED).
    A trading day XNDX lacks (2012-10-31, Hurricane Sandy reopening) is carried by NDX's move and listed in attrs.
    """
    px = ndx_price(data_dir)
    xn = loader.close("NASDAQ:XNDX", data_dir)
    if pd.Timestamp(trust_from) not in xn.index:
        raise ValueError(f"trust_from {trust_from} is not an XNDX trading day; use an exact date")
    xn = xn.loc[trust_from:]
    # As for SPXTR: rows after the price file's last date mean the XNDX export is fresher than the NDX file. They carry
    # nothing for a series on the price calendar, so they are dropped and listed, not refused.
    after_end = xn.index[xn.index > px.index[-1]]
    xn = xn.drop(after_end)
    y = pd.Series(pre_yield, index=px.index, dtype=float)
    y.loc[XNDX_LEVEL_FROM:] = mid_yield
    out, filled, trailing = _splice(px, xn, pre_yield, y, "NDX_TR", max_trailing_fill, "NASDAQ:XNDX")
    out.attrs.update(symbols=["NASDAQ:NDX", "NASDAQ:XNDX"], basis="constructed",
                     series="Nasdaq-100 total return (constructed)",
                     splice_date=str(xn.index[0].date()),
                     days_filled_from_ndx=filled,
                     trailing_rows_filled_from_price=trailing,
                     published_rows_after_price_end=[str(d.date()) for d in after_end],
                     pre_yield=pre_yield, pre_yield_status="ASSUMED", mid_yield=mid_yield,
                     mid_yield_status="MEASURED (level change of mis-dated XNDX block)",
                     mid_from=XNDX_LEVEL_FROM,
                     published_from=str(xn.index[0].date()),
                     published_status="VERIFIED (NASDAQ:XNDX, anchor-checked)")
    return out


def underlying(name, basis, data_dir=None):
    """Return the series for name in {'SPX','NDX'} and basis in {'price','total_return'}; named e.g. 'SPX_TR'."""
    table = {("SPX", "price"): spx_price, ("SPX", "total_return"): spx_total_return,
             ("NDX", "price"): ndx_price, ("NDX", "total_return"): ndx_total_return}
    if (name, basis) not in table:
        raise ValueError(f"underlying({name!r}, {basis!r}): name must be SPX or NDX, basis price or total_return")
    s = table[(name, basis)](data_dir=data_dir)
    s.attrs.setdefault("basis", "price" if basis == "price" else "total_return")
    s.attrs.setdefault("symbols", [s.attrs.get("symbol", name)])
    return s


# ---------------------------------------------------------------- provenance

def banner(series):
    """One paragraph saying what this series is, from its attrs."""
    a = series.attrs
    if not a:
        return f"[{series.name}] no provenance recorded"
    syms = ", ".join(a.get("symbols") or [a.get("symbol", "?")])
    txt = f"[{series.name}] symbols: {syms}; basis: {a.get('basis', '?')}"
    if a.get("basis") == "constructed":
        if "mid_yield" in a:
            txt += (f"; published {a['published_from']} on ({a['published_status']}); "
                    f"{a['mid_from']}..{a['splice_date']} price + {a['mid_yield']:.2%}/yr ({a['mid_yield_status']}); "
                    f"before {a['mid_from']} price + {a['pre_yield']:.2%}/yr ({a['pre_yield_status']})")
        else:
            if a["pre_yield"] == "shiller":
                yl = f"Shiller's measured monthly dividend yield (mean {a.get('pre_yield_mean_pct', float('nan')):.2f}%/yr over the pre-splice years)"
            elif isinstance(a["pre_yield"], str):    # the decade map
                m = a.get("pre_yield_map") or {}
                yl = "decade-map yield (" + ", ".join(f"{k}s {v:.1%}" for k, v in m.items() if k < 1990) + ")"
            else:
                yl = f"{a['pre_yield']:.2%}/yr"
            txt += (f"; published {a['published_from']} on ({a['published_status']}); "
                    f"before that price + {yl} ({a['pre_yield_status']})")
        txt += f"; splice date {a['splice_date']}"
        if a.get("trailing_rows_filled_from_price"):
            txt += (f"; LAST {a['trailing_rows_filled_from_price']} rows are price-only "
                    "(the published series ends earlier than the price series)")
        filled = a.get("days_filled_from_ndx") or a.get("days_filled_from_price")
        if filled:
            txt += f"; days missing from the published series carried by the price move: {filled}"
        if a.get("published_stale_days_dropped"):
            txt += f"; stale published rows on non-trading days dropped: {a['published_stale_days_dropped']}"
        if a.get("published_rows_after_price_end"):
            txt += (f"; published rows after the price file's last date dropped: {a['published_rows_after_price_end']}"
                    " (top up the price file)")
    else:
        txt += "; price index only (no dividends)"
    return txt


def data_banner(data_dir=None):
    """List every *_daily.csv in the data folder with its first/last date and distinct `source` values."""
    folder = loader.data_path(data_dir)
    files = sorted(folder.glob("*_daily.csv"))
    lines = [f"[data] folder: {folder.name}/  ({len(files)} price files); rates: {loader.rates_path(data_dir).name}/"]
    for f in files:
        head = pd.read_csv(f, nrows=0).columns
        cols = [c for c in head if c.lower() in ("date", "time", "source")]
        df = pd.read_csv(f, usecols=cols)
        tcol = next(c for c in df.columns if c.lower() in ("date", "time"))
        first, last = str(df[tcol].iloc[0]), str(df[tcol].iloc[-1])
        line = f"  {f.name}: {first} .. {last}, {len(df)} rows"
        if "source" in df.columns:
            src = sorted(df["source"].dropna().astype(str).unique())
            line += f"; source: {', '.join(src[:5])}" + (f" (+{len(src) - 5} more)" if len(src) > 5 else "")
        lines.append(line)
    return "\n".join(lines)
