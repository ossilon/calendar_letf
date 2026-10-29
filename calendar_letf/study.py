"""Step 3, the passive study: does a 2x fund that resets weekly / monthly / quarterly lose less to volatility than a
2x fund that resets daily, on the same index with the same costs?  (DESIGN sections 1, 7-9; BACKLOG C1-C8, B3.)

This module holds the math and the bookkeeping; `scripts/run_calendar_vs_daily.py` runs it and writes the report.

Plain-English map
  * A "world" is one underlying index (S&P 500 or Nasdaq-100) with its total-return level, its price index (the
    -35% trigger watches the PRICE), the reference rate and the trading calendar.
  * A "cost encoding" is one way of writing the 2024-26 cost fit (FINDINGS F3-F5) into history. Both encodings
    agree on 2024-26 and differ when rates move, so every table shows both. They are ASSUMED, not measured.
  * Every fund NAV is computed ONCE over the full history per (product, encoding, early-reset mode). A result for
    "buy at month-end s, hold h months" is the ratio nav[e] / nav[s] of that one series (DESIGN section 8). The
    kernel is never re-run per start date. The one exception is the buy-once margin benchmark: it has no
    reset dates to share, so its base is fixed at each purchase and it needs one short run per start.
  * "Reset gap" = calendar fund CAGR minus its daily twin's CAGR over the same window, in percentage points a year.
Nothing here is a result until the script records it with its provenance.
"""
import time
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from . import kernel, loader, metrics, periods, products, provenance, series, stats

HORIZONS_YEARS = (1, 3, 5, 10)                 # multi-start horizons (item 2, 7)
RESET_DAYS = {"weekly": 5, "monthly": 21, "quarterly": 63}      # trading days in one reset period (decade prediction)
VR_HORIZONS = (5, 21, 63)                      # variance-ratio horizons: weekly / monthly / quarterly
TRIGGER_ETF = {"SPX": "AMEX:SPY", "NDX": "NASDAQ:QQQ"}          # the ETF whose PRICE the prospectus trigger watches
TRIGGER_DROPS = (0.34, 0.35, 0.36)             # early-reset drop sensitivity (R1 E4)
BAD_LOW_TOL = 0.10                             # an ETF low this far (as a fraction of the close) below the index's own low is a bad print
CURVE_MONTHS = (1, 3, 6, 12, 36, 60, 120)      # horizon curve (item 4, C8)
MODES = ("level", "close", "next_close")
BASE_MODE = "level"
TRIGGER_OFF = "off"                            # pseudo-mode: the 35% trigger switched off (sensitivity, audit S3 finding 1)
BASE_ENCODING = "fixed"                        # the encoding used where a table shows only one ("base")
ROLLING_FROM = "1990-01-31"                    # first start of the rolling 10-year windows (C1)
N_BOOT = 10000                                 # block-bootstrap resamples per interval (secondary intervals; R2 step 10)

# Products per underlying, in the order tables list them.
PRODUCT_NAMES = {"SPX": ("SPYQ", "HYP_SPX_M", "HYP_SPX_W"), "NDX": ("MQQQ", "QQQP", "HYP_NDX_W")}
TRIGGER_FOR = {"SPX": series.spx_price, "NDX": series.ndx_price}

KEY_PERIODS = (                                # (label, first day, last day), fixed list; start = the close BEFORE the first day
    ("1973-74", "1973-01-01", "1974-12-31"),
    ("1987 Aug-Dec", "1987-08-01", "1987-12-31"),
    ("2000-02", "2000-01-01", "2002-12-31"),
    ("2008-09", "2008-01-01", "2009-12-31"),
    ("2020 Feb-Dec", "2020-02-01", "2020-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
)


# ---------------------------------------------------------------- cost encodings

@dataclass(frozen=True)
class CostEncoding:
    """One way of writing the 2024-26 cost fit into history (FINDINGS F5).

    spread_per_nav  annual swap-spread cost as a fraction of NAV (replaces spec.costs' spread x turns)
    rate_turns      how many NAVs of borrowing pay the reference rate: 1.0 is the kernel's own (L-1) = 1; 1.3 means the
                    rate series is multiplied by 1.3 before it reaches the kernel
    fee             None = the product's own expense ratio; a number overrides it (zero-cost runs only)
    status/source   every number says where it came from; both fitted encodings are ASSUMED
    """
    name: str
    spread_per_nav: float
    rate_turns: float
    status: str = "ASSUMED"
    source: str = ""
    fee: float | None = None
    label: str = ""

    def describe(self):
        fee = "product fee" if self.fee is None else f"fee {self.fee:.2%}"
        return (f"{self.label or self.name}: spread {self.spread_per_nav:.2%} of NAV a year + {self.rate_turns:g} x reference "
                f"rate on the borrowed turn + {fee} [{self.status}]")


_FIT = "FINDINGS F3/F5: residual of the filed costs fitted on 2024-26 (SPYQ/MQQQ/QQQP), not measured before 2024"
ENCODINGS = {
    "fixed": CostEncoding("fixed", 0.026, 1.0, source=f"(i) fixed spread per NAV 2.6%; {_FIT}", label="fixed spread 2.6% of NAV"),
    "rate": CostEncoding("rate", 0.014, 1.3, source=f"(ii) filed 1.4% spread + 1.3 turns of the rate; {_FIT}",
                         label="rate-proportional (1.4% spread + 1.3 x rate)"),
}
SENSITIVITIES = {                              # each next to its base (item 9)
    "fixed_lo": CostEncoding("fixed_lo", 0.014, 1.0, source="sensitivity: the filed spread alone (FINDINGS F5)", label="fixed spread 1.4%"),
    "fixed_hi": CostEncoding("fixed_hi", 0.035, 1.0, source="sensitivity: F5 upper value", label="fixed spread 3.5%"),
    "rate_lo": CostEncoding("rate_lo", 0.014, 1.0, source="sensitivity: kernel base, 1.0 rate turn (F5)", label="rate 1.0 turn + 1.4%"),
    "rate_hi": CostEncoding("rate_hi", 0.014, 1.5, source="sensitivity: spare cash earns nothing, 1.5 rate turns (F5)", label="rate 1.5 turns + 1.4%"),
}
ZERO_COSTS = CostEncoding("zero", 0.0, 0.0, status="DEFINITION", fee=0.0, label="ZERO costs (no rate, spread or fee)",
                          source="defined to isolate the reset effect (C1)")
RATE_ONLY = CostEncoding("rate_only", 0.0, 1.0, status="DEFINITION", fee=0.0, label="rate only (no spread, no fee)",
                         source="defined to separate financing from the reset effect (C1)")
ALL_ENCODINGS = {**ENCODINGS, **SENSITIVITIES, "zero": ZERO_COSTS, "rate_only": RATE_ONLY}


def kernel_kwargs(spec, enc):
    """The keyword arguments for kernel.run that express `enc` for `spec`.

    The rate multiplier cannot be passed through kernel.run (the kernel takes the rate Series itself), so use
    `scaled_rate` for that part; `run_product` does both. A 2x-only guard: the encodings were fitted on 2x funds.
    """
    if abs(spec.L - 2.0) > 1e-12:
        raise ValueError(f"{spec.name}: cost encodings were fitted on 2x funds only (L = {spec.L:g})")
    out = {"spread_per_nav": enc.spread_per_nav}
    if enc.fee is not None:
        out["fee"] = enc.fee
    return out


def scaled_rate(rate, enc):
    """The reference rate multiplied by the encoding's rate turns (the kernel charges (L-1) x rate = 1 x rate)."""
    return rate * enc.rate_turns


# ---------------------------------------------------------------- the world: one underlying and its cached runs

@dataclass
class World:
    name: str                                  # "SPX" or "NDX"
    u: pd.Series                               # total-return level
    trigger: pd.Series                         # price index
    rate: pd.Series                            # reference rate, lagged, with attrs (proxy rows, stale rows)
    specs: list                                # calendar ProductSpecs in table order
    twins: dict                                # product name -> daily twin spec
    trigger_low: pd.Series = None              # optional daily LOW of the price index (B4: intraday trigger); None =
                                               # close-only trigger. Passed to every calendar run of this world.
    dates: pd.DatetimeIndex = None
    me: np.ndarray = None                      # row numbers of month-end closes
    navs: dict = field(default_factory=dict)   # (product, encoding, mode) -> NAV Series
    kernel_seconds: float = 0.0
    kernel_runs: int = 0
    _ws: dict = field(default_factory=dict)
    _margin: dict = field(default_factory=dict)
    trigger_basis: str = "index"               # "index" (the index price) or "etf" (the ETF's price after it exists)
    trigger_info: dict = field(default_factory=dict)   # where the trigger series came from (build_world / trigger_series)

    def variant(self, trigger=None, trigger_low="keep", early_drop=None, trigger_basis=None, trigger_info=None):
        """The same world with another trigger series and/or early-reset drop, and EMPTY caches (a NAV computed
        under one trigger is never reused under another). trigger_low="keep" keeps the current lows; None switches to a
        close-only trigger. early_drop replaces the drop of every calendar product (the daily twins have none)."""
        specs = self.specs
        if early_drop is not None:
            specs = [replace(s, early_drop=float(early_drop), early_drop_status="ASSUMED",
                             early_drop_source=f"sensitivity: the early-reset drop set to {early_drop:.0%}") for s in self.specs]
        return replace(self, trigger=self.trigger if trigger is None else trigger,
                       trigger_low=self.trigger_low if isinstance(trigger_low, str) else trigger_low, specs=specs,
                       navs={}, _ws={}, _margin={}, kernel_seconds=0.0, kernel_runs=0,
                       trigger_basis=self.trigger_basis if trigger_basis is None else trigger_basis,
                       trigger_info=self.trigger_info if trigger_info is None else trigger_info)

    def __post_init__(self):
        self.dates = self.u.index
        self.u_arr = self.u.to_numpy(dtype=np.float64, copy=True)
        self.rate_arr = self.rate.to_numpy(dtype=np.float64, copy=True)
        # The kernel's default day counts: ACT/360 on the financing legs, 365 days for the fee (R2 step 1, E2).
        self.accrual_fin = periods.accrual_fraction(self.dates, kernel.FIN_DAY_COUNT)
        self.accrual_fee = periods.accrual_fraction(self.dates, kernel.FEE_DAY_COUNT)
        ends = np.flatnonzero(periods.period_end_flags(self.dates, "monthly"))     # NYSE month ends from 1970
        ym = self.dates.year.to_numpy()[ends] * 12 + self.dates.month.to_numpy()[ends]
        if len(ym) < 2 or not (np.diff(ym) == 1).all():
            raise ValueError("month-end rows are not one per consecutive month (a missing month in the data): "
                             "a horizon of h month-ends would not be h months")
        self.me = ends
        # The first month-end START on which every calendar product of this world has had a REAL reset at or before it.
        # The kernel treats row 0 as a reset, so a start before a product's first period end would inherit a base no
        # fund held (e.g. QQQP from 1985-01-31, a month before the first quarter end). All products share one start list.
        first_real = 0
        for sp in self.specs:
            if sp.reset in ("weekly", "monthly", "quarterly"):
                pe = np.flatnonzero(periods.period_end_flags(self.dates, sp.reset))
                first_real = max(first_real, int(pe[0]) if len(pe) else len(self.dates))
        self.me_start = int(np.searchsorted(self.me, first_real))      # index into self.me of the first valid start

    # --- runs
    def nav(self, product, enc, mode=BASE_MODE):
        """NAV Series of a calendar product (mode = early-reset mode) or of a twin (name starts with TWIN_, mode ignored)."""
        is_twin = product.startswith("TWIN_")
        key = (product, enc.name, "daily" if is_twin else mode)
        if key not in self.navs:
            spec = next(t for t in self.twins.values() if t.name == product) if is_twin else next(s for s in self.specs if s.name == product)
            run_mode = mode
            if not is_twin and mode == TRIGGER_OFF:
                # Sensitivity: the same product with no early reset at all (shows how much one trigger day is worth).
                spec = replace(spec, early_drop=None, early_drop_status="ASSUMED",
                               early_drop_source="sensitivity: the 35% trigger switched off")
                run_mode = BASE_MODE
            t0 = time.perf_counter()
            self.navs[key] = kernel.run(spec, self.u, scaled_rate(self.rate, enc), trigger=None if is_twin else self.trigger,
                                        trigger_low=None if is_twin else self.trigger_low,
                                        early_mode=run_mode, **kernel_kwargs(spec, enc))
            self.kernel_seconds += time.perf_counter() - t0
            self.kernel_runs += 1
        return self.navs[key]

    def twin_name(self, product):
        return self.twins[product].name

    # --- windows
    def month_pairs(self, months):
        """(start rows, end rows) for every month-end start with `months` more month-ends ahead, from the first start
        on which every calendar product has a real reset (`me_start`, set in __post_init__)."""
        me = self.me[self.me_start:]
        if months >= len(me):
            return np.array([], dtype=np.int64), np.array([], dtype=np.int64)
        return me[:-months], me[months:]

    def stats(self, product, enc, mode, months):
        """window_stats of a NAV over all month-end windows of `months` months (cached)."""
        key = (product, enc.name, "daily" if product.startswith("TWIN_") else mode, months)
        if key not in self._ws:
            s, e = self.month_pairs(months)
            self._ws[key] = metrics.window_stats(self.nav(product, enc, mode), s, e)
        return self._ws[key]

    def underlying_stats(self, months):
        key = ("1x", months)
        if key not in self._ws:
            s, e = self.month_pairs(months)
            self._ws[key] = metrics.window_stats(self.u, s, e)
        return self._ws[key]

    def start_dates(self, months):
        return self.dates[self.month_pairs(months)[0]]

    def row_before(self, date):
        """Row of the last close strictly before `date` (-1 if none)."""
        return int(np.searchsorted(self.dates.values, np.datetime64(pd.Timestamp(date)), side="left")) - 1

    def row_on_or_before(self, date):
        return int(np.searchsorted(self.dates.values, np.datetime64(pd.Timestamp(date)), side="right")) - 1

    # --- the buy-once margin benchmark
    def margin_navs(self, enc, fee, months_list=CURVE_MONTHS):
        """Terminal NAV of a buy-once 2x margin position bought at each month-end, for each horizon in months_list.

        The position's base is fixed at the purchase and never reset, so it cannot share one full-history run:
        one short run of kernel.margin_position_nav per start (reset "never", periods.NEVER; no trigger). Its loan
        compounds daily (R2 step 1, E1; before that the engine charged simple interest for the whole window, which
        overstated the benchmark by about 0.4 pp/yr at a 5% rate over 10 years). It is financed at the same rate
        (ACT/360) + spread and pays the same fee as the fund it is compared with, all borrowed. It is finished (NAV 0)
        when its equity reaches 0 (the index about 50% below the purchase, a little less after costs). A real margin
        account is called well before that, so this benchmark is OPTIMISTIC.
        Returns {months: array of terminal NAV, one per start of month_pairs(months) (the same starts, same order)}.
        """
        key = (enc.name, fee if enc.fee is None else enc.fee, tuple(months_list))
        if key in self._margin:
            return self._margin[key]
        fee_arr = np.full(len(self.dates), float(fee if enc.fee is None else enc.fee))
        rate = self.rate_arr * enc.rate_turns
        me = self.me[self.me_start:]                                   # the same starts as month_pairs
        nme, hmax = len(me), max(months_list)
        out = {h: np.full(max(nme - h, 0), np.nan) for h in months_list}
        t0 = time.perf_counter()
        for i in range(nme - min(months_list)):
            s = me[i]
            last = me[min(i + hmax, nme - 1)]
            seg = slice(s, last + 1)
            nav, _ = kernel.margin_position_nav(self.u_arr[seg], rate[seg], self.accrual_fin[seg], self.accrual_fee[seg],
                                                2.0, enc.spread_per_nav, fee_arr[seg])
            for h in months_list:
                if i + h < nme:
                    out[h][i] = nav[me[i + h] - s]
        self.kernel_seconds += time.perf_counter() - t0
        self.kernel_runs += nme - min(months_list)
        self._margin[key] = out
        return out

    def margin_slice(self, enc, fee, s, e):
        """NAV path (1.0 at row s) of a margin position bought at the close of row s, to row e (compounding loan,
        same kernel and costs as margin_navs)."""
        rate = self.rate_arr * enc.rate_turns
        seg = slice(s, e + 1)
        fee_arr = np.full(e + 1 - s, float(fee if enc.fee is None else enc.fee))
        nav, _ = kernel.margin_position_nav(self.u_arr[seg], rate[seg], self.accrual_fin[seg], self.accrual_fee[seg],
                                            2.0, enc.spread_per_nav, fee_arr)
        return nav


def splice_etf_trigger(idx_close, idx_low, etf, symbol, bad_low_tol=BAD_LOW_TOL):
    """The trigger series when the prospectus watches the ETF's price: the index price before the ETF existed, the
    ETF's own price from its first bar on, scaled so the series is continuous at the splice.

    idx_close  the index PRICE close on the study calendar (a Series)
    idx_low    the index's daily low on the same rows, or None for a close-only trigger
    etf        DataFrame with close (and low) columns on a DatetimeIndex (loader.load_prices)
    Rules
      * splice day d0 = the ETF's first bar (it must be an index trading day); scale k = idx_close[d0] / etf_close[d0],
        so trigger[d0] = idx_close[d0] and the ETF's later closes are multiplied by k.
      * a day the ETF has no bar (a closure only the index calendar has; the days after the ETF file ends) is carried by the
        index's move at the last known ETF-to-index ratio, and listed in info["rows_carried_from_index"].
      * the ETF low is used as it is, with ONE guard: an ETF low more than `bad_low_tol` (10 percent of the close) deeper
        than the index's own low-to-close gap that day is a bad print (QQQ 2000-04-12 shows a low 31 points below the
        index's; a trigger would fire on it) and the index's gap is used instead. The days are listed in
        info["bad_low_days"]. A real ETF-only dislocation (SPY on 2010-05-06) is smaller than the tolerance and stays.
    Returns (trigger, low or None, info)."""
    dates = idx_close.index
    d0 = etf.index[0]
    if d0 not in dates:
        raise ValueError(f"{symbol}: the ETF's first bar {d0.date()} is not a trading day of the index calendar")
    k = float(idx_close.loc[d0] / etf["close"].iloc[0])
    e_close = etf["close"].astype("float64").reindex(dates)
    after = dates >= d0
    have = e_close.notna().to_numpy() & after
    ratio = (e_close * k / idx_close).ffill()                    # ETF-to-index ratio after scaling; 1.0 on d0
    trig = idx_close.copy()
    trig[have] = (e_close * k)[have]
    carried = after & ~have
    trig[carried] = (idx_close * ratio)[carried]
    trig.name = f"{idx_close.name}_{symbol.split(':')[-1]}_trigger"
    info = dict(basis="etf", etf_symbol=symbol, etf_first_bar=str(d0.date()), etf_last_bar=str(etf.index[-1].date()),
                scale=k, rows_carried_from_index=[str(d.date()) for d in dates[carried]], bad_low_days=[])
    if idx_low is None:
        return trig, None, info
    low = idx_low.copy()
    e_low = etf["low"].astype("float64").reindex(dates)
    idx_gap = idx_low / idx_close - 1.0
    etf_gap = e_low / e_close - 1.0
    bad = have & (etf_gap < idx_gap - bad_low_tol).to_numpy()
    use_etf = have & ~bad
    low[use_etf] = (e_low * k)[use_etf]
    low[bad] = (trig * (1.0 + idx_gap))[bad]                     # the index's own gap, applied to the ETF close
    low[carried] = (idx_low * ratio)[carried]
    low.name = f"{idx_close.name}_{symbol.split(':')[-1]}_trigger_low"
    info["bad_low_days"] = [dict(date=str(d.date()), etf_gap=float(etf_gap.loc[d]), index_gap=float(idx_gap.loc[d]))
                            for d in dates[bad]]
    return trig, low, info


def trigger_series(name, basis="index", intraday=False, data_dir=None):
    """(trigger close, trigger low or None, info) for one underlying under one trigger convention.

    basis="index": the index price (SP:SPX / NASDAQ:NDX), as in the published v1 results.
    basis="etf":   the ETF price (AMEX:SPY from 1993-01-29 / NASDAQ:QQQ from 1999-03-10) spliced onto the index price
                   before that (splice_etf_trigger); the prospectus watches the ETF.
    intraday=True adds the daily low (a breach is a low at or below the trigger level), False tests closes only."""
    if basis not in ("index", "etf"):
        raise ValueError(f"trigger_basis must be 'index' or 'etf', got {basis!r}")
    idx = TRIGGER_FOR[name](data_dir)
    low = series.price_low(name, data_dir).reindex(idx.index) if intraday else None
    if basis == "index":
        return idx, low, dict(basis="index", symbol=series.PRICE_SYMBOL[name], intraday=bool(intraday))
    sym = TRIGGER_ETF[name]
    trig, elow, info = splice_etf_trigger(idx, low, loader.load_prices(sym, data_dir), sym)
    info["intraday"] = bool(intraday)
    return trig, elow, info


def compact_trigger_info(info):
    """The trigger provenance for a results file: the days carried by the index move after the ETF file ends are a run of
    consecutive dates, so they are reported as a count and a range (a results file must not hold a daily series)."""
    out = {k: v for k, v in info.items() if k != "rows_carried_from_index"}
    carried = info.get("rows_carried_from_index", [])
    if info["basis"] == "etf":
        end = info["etf_last_bar"]
        out["rows_carried_inside_etf_range"] = [d for d in carried if d < end]
        tail = [d for d in carried if d >= end]
        out["rows_carried_after_etf_end"] = dict(count=len(tail), first=tail[0] if tail else None, last=tail[-1] if tail else None)
    return out


def trigger_text(info):
    """One sentence saying what the early-reset trigger watches (for banners and table notes)."""
    what = "daily low" if info.get("intraday") else "close"
    if info["basis"] == "index":
        return f"the {info['symbol']} price index, {what}"
    return (f"the {info['etf_symbol']} price ({what}) from {info['etf_first_bar']}, scaled to the {TRIGGER_FOR_SYMBOL[info['etf_symbol']]} "
            f"price index before that")


TRIGGER_FOR_SYMBOL = {"AMEX:SPY": "SP:SPX", "NASDAQ:QQQ": "NASDAQ:NDX"}


def build_world(name, intraday_trigger=False, trigger_basis="index"):
    """Load one underlying (total return, price trigger, reference rate) and its products and twins.

    intraday_trigger=True also loads the daily LOW of the trigger series so the -35% trigger reads the low (BACKLOG B4);
    the default False keeps the close-only trigger of the published v1 results.
    trigger_basis="index" watches the index price (v1); "etf" watches the ETF's price from the day the ETF exists
    (R1 E4: the prospectus trigger is on SPY / QQQ; see `trigger_series`).
    Returns (world, provenance dict with the series banner and the rate attrs)."""
    u = series.underlying(name, "total_return")
    trigger, low, info = trigger_series(name, trigger_basis, intraday_trigger)
    if not trigger.index.equals(u.index):
        raise ValueError(f"{name}: the price index and the total-return series do not share a calendar")
    rate = loader.reference_rate(u.index)
    specs = [products.PRODUCTS[p] for p in PRODUCT_NAMES[name]]
    twins = {s.name: products.twin_of(s) for s in specs}
    world = World(name, u, trigger, rate, specs, twins, trigger_low=low, trigger_basis=trigger_basis, trigger_info=info)
    prov = dict(banner=series.banner(u), first=str(u.index[0].date()), last=str(u.index[-1].date()), rows=int(len(u)),
                rate=dict(source=rate.attrs["source"], proxy_rows=rate.attrs["proxy_rows"], proxy_until=rate.attrs["proxy_until"],
                          proxy_rule=rate.attrs["proxy_rule"], rate_last_date=rate.attrs["rate_last_date"],
                          stale_rows=rate.attrs["stale_rows"]),
                price_symbol=series.PRICE_SYMBOL[name], trigger=compact_trigger_info(info), trigger_text=trigger_text(info))
    return world, prov


def world_inputs(world, prov):
    """The price symbols and the FRED rate names that `build_world` read for this world, in load order, without repeats.

    Taken from what the world holds: the series' own symbol list (price index and total-return index), the trigger's ETF
    when the trigger watches the ETF, DFF for the financing rate, and TB3MS only when the proxy rows exist (the rows
    before DFF starts). `prov` is the second value `build_world` returns."""
    symbols = list(world.u.attrs["symbols"])
    if world.trigger_info.get("basis") == "etf":
        symbols.append(world.trigger_info["etf_symbol"])
    rates = ["DFF"] + (["TB3MS"] if prov["rate"]["proxy_rows"] else [])
    return list(dict.fromkeys(symbols)), rates


def inputs_for(worlds, provs, extra_symbols=(), extra_rates=()):
    """The provenance manifest (calendar_letf.provenance.inputs_manifest) of every file the worlds read, plus the
    `extra_symbols` / `extra_rates` a script loads on its own (the real 3x funds, the cash rate). `worlds` and `provs` are
    dicts keyed by the underlying's name; a missing file raises FileNotFoundError."""
    symbols, rates = [], []
    for name, w in worlds.items():
        s, r = world_inputs(w, provs[name])
        symbols += s
        rates += r
    m = provenance.inputs_manifest(list(dict.fromkeys(symbols + list(extra_symbols))),
                                   list(dict.fromkeys(rates + list(extra_rates))))
    # Files inside the repository that a world reads (R4 review): the Shiller yields behind every S&P total return
    # before 1988. They ship with the repo, so tests/test_provenance.py fails a result whose copy no longer matches.
    if any(w.u.attrs.get("pre_yield") == "shiller" for w in worlds.values()):
        m["reference_dir"] = "reference"
        m["reference_files"] = provenance.manifest([series.SHILLER_FILE])
    return m


def conventions_lines(world, mode=BASE_MODE):
    """Banner lines that state the conventions behind every number of a study: what the early-reset trigger watches, the
    drop that fires it, the fill mode, the day counts of financing and fee, and the exchange calendar for reset dates."""
    drops = sorted({s.early_drop for s in world.specs if s.early_drop is not None})
    drop_txt = " / ".join(f"{d:.0%}" for d in drops) if drops else "none"
    return [
        f"{world.name} early-reset trigger: {trigger_text(world.trigger_info)}; trigger basis '{world.trigger_basis}'; "
        f"drop {drop_txt} from the fund's base; fill mode '{mode}'.",
        f"{world.name} day counts: financing (reference rate and swap spread) ACT/{kernel.FIN_DAY_COUNT}; expense ratio "
        f"ACT/{kernel.FEE_DAY_COUNT} (calendar days between rows, so weekends and holidays accrue).",
        f"{world.name} reset dates: last NYSE session of the week / month / quarter from {periods.NYSE_FROM.date()} "
        f"(calendar_letf/nyse.py, refuses data that lack it); before that the last row of the period.",
    ]


# ---------------------------------------------------------------- small helpers

def pct_summary(x):
    """(median, 10th, 90th percentile) ignoring NaN."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return (float("nan"),) * 3
    return tuple(float(v) for v in np.percentile(x, [50, 10, 90]))


def share_wins(gap):
    g = np.asarray(gap, dtype=float)
    g = g[np.isfinite(g)]
    return float((g > 0).mean()) if len(g) else float("nan")


def _gap(world, product, enc, mode, months):
    """Per-start arrays for one product and its twin: (calendar window stats, twin window stats, gap CAGR difference)."""
    c = world.stats(product, enc, mode, months)
    t = world.stats(world.twin_name(product), enc, mode, months)
    return c, t, c["cagr"] - t["cagr"]


# ---------------------------------------------------------------- item 2: multi-start summary

def gap_interval(g, months, n_boot=N_BOOT):
    """Uncertainty of a headline gap: the per-start gaps `g` (CAGR differences, one per month-end start, in time order)
    for a horizon of `months` months.  Returns the columns multi_start adds to each row.

    HEADLINE interval (R2 step 10): the PHASE-POOLED interval (stats.phase_pooled_mean, step = the horizon in months).
    Every `months`-th start gives one set of windows that do not overlap; there are `months` such sets (phases); the
    sets are pooled (SE^2 = mean of s_p^2 / k_p, df = smallest k_p - 1, interval = mean +/- t(df) x SE).  Its columns
    are `indep_*` (mean, se, lo, hi, df, t = mean / se, k_min, k_max, phases, share of phases whose own interval
    excludes zero) and
    the headline flag `noisy` (True when that interval covers zero) is taken from it; `noisy_indep` is the same flag
    under its older name.  Its simulated coverage on gap series with the overlap of rolling windows, at every
    published configuration, is in results/coverage_sim.md (scripts/run_coverage_sim.py; tests/test_stats.py
    recomputes three entries): at or near nominal (within Monte Carlo error) under independent months, so not short;
    the same file shows the limit of that claim when windows that do not overlap are themselves persistent.
    SECONDARY intervals: the circular block bootstrap with block = horizon (starts one month apart share months - 1 of
    their `months` months, so a block of `months` consecutive starts is roughly ONE independent window).  Its mean
    columns are `bb_mean`, `bb_se`, `bb_lo`, `bb_hi`, `bb_k` (k = n // months; interval = mean +/- t(k-1) x SE) with the
    flag `noisy_bb_mean`; the median columns are `bb_median_se`, `bb_median_lo`, `bb_median_hi` with `noisy_bb_median`
    (same blocks, same resamples; the interval is for the median of the window gaps and the bootstrap SE of a median is
    a reasonable device, not an exact one).  The bootstrap SE is BIASED LOW with block = the window length (the block
    bootstrap sees only the dependence inside one block, which for a mean-of-h-shocks series loses about a third of
    the variance at any block count, and more at 3 to 6 blocks; coverage in results/coverage_sim.md; ASSUMPTIONS
    section 7), so no headline rests on it.
    The old column names `gap_mean`, `gap_se`, `gap_lo`, `gap_hi`, `gap_k`, `gap_n_windows`, `gap_block_months` and
    `median_se`, `median_lo`, `median_hi` stay: they hold the same block-bootstrap numbers as the `bb_*` columns.
    The median and the win share stay the headline statistics; the mean is next to them because a median structurally
    favors the less convex structure (Bessembinder).  `n_boot` resamples per bootstrap (N_BOOT)."""
    b = stats.block_bootstrap_mean(g, block=months, n_boot=n_boot)
    bm = stats.block_bootstrap_median(g, block=months, n_boot=n_boot)
    ind = stats.phase_pooled_mean(g, months)
    noisy_bb_mean = stats.covers_zero(b["lo"], b["hi"])
    noisy_bb_median = stats.covers_zero(bm["lo"], bm["hi"])
    noisy_pp = stats.covers_zero(ind["lo"], ind["hi"])
    return dict(gap_mean=b["mean"], gap_se=b["se"], gap_lo=b["lo"], gap_hi=b["hi"], gap_k=b["k"], gap_n_windows=b["n"],
                gap_block_months=months,
                median_se=bm["se"], median_lo=bm["lo"], median_hi=bm["hi"],
                indep_mean=ind["mean"], indep_se=ind["se"], indep_lo=ind["lo"], indep_hi=ind["hi"], indep_df=ind["df"],
                indep_t=(ind["mean"] / ind["se"] if ind["se"] > 0 else float("nan")),      # the t ratio, to read against t(df) and the regime-stress multipliers
                indep_k_min=ind["k_min"], indep_k_max=ind["k_max"], indep_phases=ind["phases"],
                indep_share_phases_excl_zero=ind["share_phases_excl_zero"], noisy_indep=noisy_pp,
                noisy=noisy_pp,
                bb_mean=b["mean"], bb_se=b["se"], bb_lo=b["lo"], bb_hi=b["hi"], bb_k=b["k"], bb_n_boot=int(n_boot),
                bb_median_se=bm["se"], bb_median_lo=bm["lo"], bb_median_hi=bm["hi"],
                noisy_bb_mean=noisy_bb_mean, noisy_bb_median=noisy_bb_median)


def multi_start(world, enc, mode=BASE_MODE, horizons_years=HORIZONS_YEARS):
    """One row per (product, horizon): calendar and twin CAGR (median, p10, p90), median max drawdown, worst terminal
    wealth, the reset gap (median, p10, p90, share of starts the calendar fund wins), and the gap's mean with its
    uncertainty (`gap_interval`). Also the raw per-start table.

    Starts are EVERY month-end with a full horizon ahead. A month-end is mid-period for a quarterly or weekly fund
    (a real investor's situation); the NAV ratio already carries the floating leverage that implies.
    """
    rows, raw = [], []
    for p in world.specs:
        for hy in horizons_years:
            months = 12 * hy
            c, t, g = _gap(world, p.name, enc, mode, months)
            u1 = world.underlying_stats(months)
            cm, c10, c90 = pct_summary(c["cagr"])
            tm, t10, t90 = pct_summary(t["cagr"])
            gm, g10, g90 = pct_summary(g)
            rows.append(dict(product=p.name, reset=p.reset, horizon_years=hy, n_starts=int(np.isfinite(g).sum()),
                             first_start=str(world.start_dates(months)[0].date()), last_start=str(world.start_dates(months)[-1].date()),
                             cal_cagr_median=cm, cal_cagr_p10=c10, cal_cagr_p90=c90,
                             cal_maxdd_median=float(np.nanmedian(c["max_dd"])), cal_worst_terminal=float(np.nanmin(c["terminal"])),
                             twin_cagr_median=tm, twin_cagr_p10=t10, twin_cagr_p90=t90,
                             twin_maxdd_median=float(np.nanmedian(t["max_dd"])), twin_worst_terminal=float(np.nanmin(t["terminal"])),
                             gap_median=gm, gap_p10=g10, gap_p90=g90, calendar_wins=share_wins(g),
                             underlying_1x_cagr_median=float(np.nanmedian(u1["cagr"])), **gap_interval(g, months)))
            raw.append(pd.DataFrame(dict(start=world.start_dates(months).strftime("%Y-%m-%d"), horizon_years=hy, product=p.name,
                                         cal_cagr=c["cagr"], twin_cagr=t["cagr"], gap=g, cal_maxdd=c["max_dd"],
                                         twin_maxdd=t["max_dd"], cal_terminal=c["terminal"], twin_terminal=t["terminal"])))
    return rows, pd.concat(raw, ignore_index=True)


# ---------------------------------------------------------------- item 3: decades (C2)

def return_statistics(level):
    """Daily-return statistics of a level series (first value = the close before the first return): the lag-1
    autocorrelation of LOG returns with its standard error and z (stats.ar1), and the Lo-MacKinlay variance ratio at
    VR_HORIZONS with the robust z, computed on SIMPLE returns (Bessembinder defines VR_T on simple returns, and the
    prediction below uses their mean and standard deviation).  Returns a dict."""
    v = np.asarray(level, dtype=np.float64)
    simple = v[1:] / v[:-1] - 1.0
    a = stats.ar1(np.diff(np.log(v)))
    vr = {q: stats.variance_ratio(simple, q) for q in VR_HORIZONS}
    return dict(n_returns=int(len(simple)), mean_daily=float(simple.mean()), sd_daily=float(simple.std(ddof=1)),
                ar1_rho=a["rho"], ar1_se=a["se"], ar1_z=a["z"], ar1_z_robust=a["z_robust"],
                vr={str(q): dict(vr=r["vr"], z_robust=r["z_robust"], significant=bool(abs(r["z_robust"]) > 1.96)) for q, r in vr.items()})


def decade_table(world, enc, mode=BASE_MODE):
    """Per decade: CAGR of each product and twin, the gap, lag-1 autocorrelation of the underlying's daily log returns
    with its standard error, the variance ratios VR(5), VR(21), VR(63) with the robust z, and the share of that decade's
    month-end starts (1-year horizon) where the calendar fund beat its twin.

    Prediction (R1 memo section 3.2; stats.predicted_reset_gap): per product, the sign of the calendar-minus-daily gap
    that Bessembinder's second-order formula gives from the decade's mean and standard deviation of the daily simple
    return and the variance ratio at the product's reset horizon (5 / 21 / 63 days for weekly / monthly / quarterly),
    next to the realized sign. It leaves out costs, the early-reset trigger and the financing difference between the
    structures, so a disagreement is information, not an error.

    A decade runs from the last close before 1 January of its first year (or the first row of data) to the last
    close of its last year (or the last row of data: the 2020s are partial; the 1980s on NDX start in 1985)."""
    first_year, last_year = world.dates[0].year, world.dates[-1].year
    out = []
    starts_1y = world.start_dates(12)
    for dec in range((first_year // 10) * 10, last_year + 1, 10):
        s = max(world.row_before(f"{dec}-01-01"), 0)
        e = world.row_on_or_before(f"{dec + 9}-12-31")
        if e - s < 250:
            continue
        rs = return_statistics(world.u.iloc[s:e + 1])
        row = dict(decade=f"{dec}s", first_close=str(world.dates[s].date()), last_close=str(world.dates[e].date()),
                   years=float((world.dates[e] - world.dates[s]).days / 365.25),
                   partial=bool(world.dates[s] > pd.Timestamp(f"{dec}-01-31") or world.dates[e].year < dec + 9),
                   autocorr_lag1=metrics.lag1_autocorr(world.u.iloc[s:e + 1]), returns=rs,
                   underlying_1x_cagr=float(metrics.window_stats(world.u, [s], [e])["cagr"][0]), products={})
        in_dec = (starts_1y >= pd.Timestamp(f"{dec}-01-01")) & (starts_1y <= pd.Timestamp(f"{dec + 9}-12-31"))
        row["n_1y_starts"] = int(in_dec.sum())
        for p in world.specs:
            c = metrics.window_stats(world.nav(p.name, enc, mode), [s], [e])["cagr"][0]
            t = metrics.window_stats(world.nav(world.twin_name(p.name), enc, mode), [s], [e])["cagr"][0]
            _, _, g1 = _gap(world, p.name, enc, mode, 12)
            T = RESET_DAYS[p.reset]
            pr = stats.predicted_reset_gap(rs["mean_daily"], rs["sd_daily"], rs["vr"][str(T)]["vr"], T)
            realized = 1 if c - t > 0 else -1
            row["products"][p.name] = dict(cal_cagr=float(c), twin_cagr=float(t), gap=float(c - t),
                                           win_share_1y=share_wins(g1[in_dec]) if in_dec.any() else float("nan"),
                                           reset_days=T, predicted_gap_pp_year=float(pr["gap_per_period"] * 252.0 / T * 100.0),
                                           predicted_sign=pr["sign"], realized_sign=realized,
                                           sign_agrees=bool(pr["sign"] == realized), crossover_vr=pr["crossover_vr"],
                                           vr_at_reset=rs["vr"][str(T)]["vr"])
        out.append(row)
    return out


def prediction_summary(decades, product):
    """How many decades the predicted sign of the gap equals the realized sign (decades with a prediction of exactly 0 count
    as disagreements). Descriptive: a handful of decades, and the formula leaves out costs and the trigger."""
    flags = [d["products"][product]["sign_agrees"] for d in decades]
    return dict(product=product, n_decades=len(flags), n_agree=int(sum(flags)))


def sign_pattern(decades, product):
    """String like '1950s -, 1960s -, ..., 2020s +' of the sign of the decade gap."""
    return ", ".join(f"{d['decade']} {'+' if d['products'][product]['gap'] > 0 else '-'}" for d in decades)


def gap_vs_autocorr(decades, product):
    """Correlation across decades between the lag-1 autocorrelation and the decade gap (n decades; DESCRIPTIVE ONLY:
    eight or so points, no sampling distribution, and the decades differ in drift and volatility too; the tested
    statement is the predicted sign in `decade_table`, which uses the variance ratio and the standard errors)."""
    a = np.array([d["autocorr_lag1"] for d in decades])
    g = np.array([d["products"][product]["gap"] for d in decades])
    if len(a) < 4:
        return float("nan")
    return float(np.corrcoef(a, g)[0, 1])


# ---------------------------------------------------------------- item 4: horizon curve (C8)

def horizon_curve(world, enc, mode=BASE_MODE, months_list=CURVE_MONTHS):
    rows = []
    for p in world.specs:
        for m in months_list:
            _, _, g = _gap(world, p.name, enc, mode, m)
            gm, g10, g90 = pct_summary(g)
            rows.append(dict(product=p.name, reset=p.reset, months=m, n_starts=int(np.isfinite(g).sum()), gap_median=gm,
                             gap_p10=g10, gap_p90=g90, calendar_wins=share_wins(g)))
    return rows


# ---------------------------------------------------------------- item 5: rolling 10-year windows (C1)

def rolling_10y(world, enc, mode=BASE_MODE):
    """Rolling 10-year windows from 1990-01-31 on: median / min / max gap and the share of windows the calendar fund wins."""
    months = 120
    s, _ = world.month_pairs(months)
    keep = world.dates[s] >= pd.Timestamp(ROLLING_FROM)
    rows = []
    for p in world.specs:
        _, _, g = _gap(world, p.name, enc, mode, months)
        g = g[keep]
        rows.append(dict(product=p.name, reset=p.reset, encoding=enc.name, n_windows=int(np.isfinite(g).sum()),
                         first_start=str(world.start_dates(months)[keep][0].date()), last_start=str(world.start_dates(months)[keep][-1].date()),
                         gap_median=float(np.nanmedian(g)), gap_min=float(np.nanmin(g)), gap_max=float(np.nanmax(g)),
                         wins=int((g > 0).sum()), calendar_wins=share_wins(g)))
    return rows


# ---------------------------------------------------------------- item 6: early resets, wipeouts (C6)

FILL_WINDOW = 70      # sessions after an episode over which the fill rule's effect on fund value is read (past a quarter end)


def fill_effects(world, p_name, enc, mode):
    """What the fill rule of an early reset is worth, per episode: the change in fund value under `mode` (close or
    next_close) relative to the base fill at the trigger level.

    Episodes are the TRIGGER days, read from the level path (the level fill resets on the trigger day; so does the
    close fill; the next-close fill resets one session later, so that path's own early-reset dates lag the trigger
    by a session and must not be used to open the window). The window opens the session BEFORE the trigger day, when
    the two paths still agree, and closes FILL_WINDOW sessions after the trigger (shortened to the session before the
    next trigger, or the end of the data). Between the fills and the next ORDINARY period end the two paths carry
    different leverage (each resets to 2x at its own fill, then drifts), so their NAV ratio moves with the market;
    from that period end on both are 2x again and the ratio stays constant until the next trigger. FILL_WINDOW is
    sized to reach past a quarter end, so the ratio's change across the window is the fill rule's whole effect on
    fund value (SPYQ 2008: +16.4% on the fill day, +18.0% by the quarter end).
    Returns [{date (trigger day), fill_date (the mode's reset day: its early reset, or the ordinary period end it lands
    on, which the kernel does not flag as early), fill_kind ("early", "period_end" or None), episodes_aligned (see
    match_fills), sessions, pct}] with pct = (ratio at the close of the window / ratio before the trigger) - 1: negative when the
    mode's fill leaves the fund poorer than the level fill, positive when richer (a fill after a rebound keeps the
    drifted leverage through it). An empty list for mode "level" or when there is no episode.
    Closed form at zero costs, one-day fall from 100 to 64 then 80 (tests/test_study.py): level fills at 65, NAV 0.30
    then 0.30 x (2 x 80/65 - 1) = 0.438462; close fills at 64: 0.28 x 1.5 = 0.42 (-4.2105%); next close fills at 80:
    2 x 0.80 - 1 = 0.60 (+36.842%).
    """
    if mode == "level":
        return []
    a = world.nav(p_name, enc, mode).to_numpy()
    level = world.nav(p_name, enc, "level")
    b = level.to_numpy()
    to_idx = lambda d: int(np.searchsorted(world.dates.values, np.datetime64(pd.Timestamp(d))))      # noqa: E731
    trig = [to_idx(d) for d in level.attrs["early_resets"]]
    fills = [to_idx(d) for d in world.nav(p_name, enc, mode).attrs["early_resets"]]
    spec = next(s for s in world.specs if s.name == p_name)
    ends = np.flatnonzero(periods.period_end_flags(world.dates, spec.reset))
    stops = []
    for j, i in enumerate(trig):
        stop = min(i + FILL_WINDOW, len(a) - 1)
        if j + 1 < len(trig):
            stop = min(stop, trig[j + 1] - 1)
        stops.append(stop)
    matched = match_fills(trig, fills, ends, stops)
    out = []
    for i, stop, (fill, kind, ok) in zip(trig, stops, matched):
        start = max(i - 1, 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            before, after = a[start] / b[start], a[stop] / b[stop]
            pct = float(after / before - 1.0) if np.isfinite(before) and np.isfinite(after) and before != 0.0 else float("nan")
        out.append(dict(date=str(world.dates[i].date()), fill_date=None if fill is None else str(world.dates[fill].date()),
                        fill_kind=kind, sessions=int(stop - i), pct=pct, episodes_aligned=bool(ok)))
    return out


MAX_FILL_LAG = 5      # sessions within which a mode's reset is taken to be the fill of a level-path trigger


def match_fills(trig, fills, period_ends, stops, max_lag=MAX_FILL_LAG):
    """Match each level-path trigger to the mode path's fill, per episode (R3 review guard, made per episode in R2 step 12i).

    trig       row numbers of the level path's early resets (the trigger days), ascending
    fills      row numbers of the mode path's early resets, ascending
    period_ends row numbers of the product's ordinary period ends
    stops      the last row of each trigger's window (as fill_effects places it)
    For trigger i the fill is the first mode early reset in [i, i + max_lag] not already used ("early"); if there is
    none, an ordinary period end in [i, i + max_lag] ("period_end": the mode resets there anyway, and the kernel does not
    flag that reset as early); else no fill (None). An episode is ALIGNED when it has a fill and no UNMATCHED mode early
    reset (one that is no trigger's fill) falls inside its window [i - 1, stop]: such a reset means the mode's path
    triggered on a day the level path did not, so the window would compare unrelated resets.
    Returns [(fill row or None, kind or None, aligned bool)] in trigger order.
    """
    ends = set(int(e) for e in period_ends)
    used, picks = set(), []
    for i in trig:
        f = next((x for x in fills if i <= x <= i + max_lag and x not in used), None)
        if f is not None:
            used.add(f)
            picks.append((f, "early"))
            continue
        pe = next((e for e in range(i, i + max_lag + 1) if e in ends), None)
        picks.append((pe, "period_end") if pe is not None else (None, None))
    unmatched = [x for x in fills if x not in used]
    out = []
    for (f, kind), i, stop in zip(picks, trig, stops):
        clean = not any(i - 1 <= x <= stop for x in unmatched)
        out.append((f, kind, bool(f is not None and clean)))
    return out


def fill_effect_range(rows):
    """Smallest and largest per-episode fill effect over early_events rows of modes close and next_close:
    {min_pct, max_pct, n_episodes}; NaNs when there is none."""
    vals = [e["pct"] for r in rows if r["mode"] in ("close", "next_close") for e in r.get("fill_effect_vs_level", [])
            if e["pct"] is not None and np.isfinite(e["pct"]) and e.get("episodes_aligned", True)]
    if not vals:
        return dict(min_pct=float("nan"), max_pct=float("nan"), n_episodes=0)
    return dict(min_pct=float(min(vals)), max_pct=float(max(vals)), n_episodes=len(vals))


def early_events(world, enc, mode):
    """Per product: early-reset dates, whether the fund hit zero, the fill rule's effect per episode (fill_effects);
    per twin: days with a daily loss worse than -40%."""
    out = []
    for p in world.specs:
        nav = world.nav(p.name, enc, mode)
        tw = world.nav(world.twin_name(p.name), enc, mode)
        r = tw.to_numpy()[1:] / np.where(tw.to_numpy()[:-1] > 0, tw.to_numpy()[:-1], np.nan) - 1.0
        bad = np.flatnonzero(r < -0.40) + 1
        out.append(dict(product=p.name, reset=p.reset, encoding=enc.name, mode=mode,
                        early_resets=list(nav.attrs["early_resets"]), n_early_resets=len(nav.attrs["early_resets"]),
                        terminated=nav.attrs["terminated"], fill_effect_vs_level=fill_effects(world, p.name, enc, mode),
                        twin_days_below_minus_40=[f"{world.dates[i].date()} ({r[i - 1]:+.1%})" for i in bad],
                        twin_n_days_below_minus_40=int(len(bad)), twin_terminated=tw.attrs["terminated"],
                        twin_worst_day=float(np.nanmin(r))))
    return out


COST_ENCODING_NAMES = ("fixed", "fixed_lo", "fixed_hi", "rate", "rate_lo", "rate_hi")     # the six cost cases of sensitivity_table


def cost_span(rows):
    """Per product, the span (largest minus smallest) of the 10-year median gap over the six cost cases of
    `sensitivity_table` at the base fill (mode level): how much the cost encoding and its sensitivities move the
    answer. {product: span}."""
    cases = [r for r in rows if r["mode"] == "level" and r["encoding"] in COST_ENCODING_NAMES]
    products = sorted({p for r in cases for p in r["gap_10y_median"]})
    out = {}
    for p in products:
        vals = [r["gap_10y_median"][p] for r in cases if p in r["gap_10y_median"] and np.isfinite(r["gap_10y_median"][p])]
        out[p] = float(max(vals) - min(vals)) if vals else float("nan")
    return out


ENCODING_GAP_ERAS = (("1966-82", "1966-01-03", "1982-12-31"), ("2009-15", "2009-01-02", "2015-12-31"), ("full", None, None))


def encoding_gap(world, eras=ENCODING_GAP_ERAS, enc_a="fixed", enc_b="rate"):
    """How far the two historical cost encodings disagree: CAGR under `enc_a` minus CAGR under `enc_b`, per product,
    over named eras and the full history, {era label: {product: gap}}. The fixed encoding charges a constant 2.6% of
    NAV; the rate encoding 1.4% plus 1.3 turns of the reference rate, so they part when rates are far from the 2024-26
    level (1966-82 rates high: fixed above rate; 2009-15 rates near zero: rate above fixed). Replaces a typed
    "1.4-1.7 pp/yr" (R2 step 12e)."""
    out = {}
    for label, s, e in eras:
        out[label] = {}
        for p in world.specs:
            a = world.nav(p.name, ALL_ENCODINGS[enc_a])
            b = world.nav(p.name, ALL_ENCODINGS[enc_b])
            sa = a.loc[s:e] if s is not None else a
            sb = b.loc[s:e] if s is not None else b
            if len(sa) < 2 or len(sb) < 2 or sa.iloc[0] <= 0 or sa.iloc[-1] <= 0 or sb.iloc[0] <= 0 or sb.iloc[-1] <= 0:
                out[label][p.name] = float("nan")
                continue
            yrs = (sa.index[-1] - sa.index[0]).days / 365.25
            ca = (sa.iloc[-1] / sa.iloc[0]) ** (1.0 / yrs) - 1.0
            cb = (sb.iloc[-1] / sb.iloc[0]) ** (1.0 / yrs) - 1.0
            out[label][p.name] = float(ca - cb)
    return out


# ---------------------------------------------------------------- item 7: buy-once margin benchmark (C7 / B3)

def margin_comparison(world, enc, horizons_years=HORIZONS_YEARS):
    """At every month-end start: fund CAGR minus margin-position CAGR (negative = the fund fell short of buying once),
    for each calendar fund and each daily twin; median AND MEAN gap and share of starts the fund wins.

    The margin position compounds its loan (R2 step 1), so fewer windows finish than before. A window the margin
    position finishes counts as -100% CAGR for it (an automatic fund win), so each statistic is also given over the
    SURVIVING windows only (`*_survivors`); `margin_finished` is the number of such windows. The mean is next to the
    median because the margin payoff is linear and the fund's is convex: a median comparison favors the linear side,
    a mean the convex one (R1 memo section 3.1; Wang 2025 eq. 10)."""
    rows = []
    for p in world.specs:
        fee = p.fee
        mg = world.margin_navs(enc, fee, tuple(sorted(set(CURVE_MONTHS) | {12 * h for h in horizons_years})))
        for hy in horizons_years:
            months = 12 * hy
            s, e = world.month_pairs(months)
            years = (world.dates[e] - world.dates[s]).days.to_numpy() / 365.25
            term = mg[months]
            with np.errstate(divide="ignore", invalid="ignore"):
                mcagr = np.where(term > 0, np.where(term > 0, term, 1.0) ** (1.0 / years) - 1.0, -1.0)
            alive = term > 0
            row = dict(product=p.name, reset=p.reset, encoding=enc.name, horizon_years=hy, n_starts=int(len(s)),
                       margin_cagr_median=float(np.median(mcagr)), margin_cagr_mean=float(np.mean(mcagr)),
                       margin_finished=int((~alive).sum()), margin_finished_share=float((~alive).mean()),
                       n_survivors=int(alive.sum()),
                       margin_cagr_median_survivors=float(np.median(mcagr[alive])) if alive.any() else float("nan"))
            for label, name in (("fund", p.name), ("twin", world.twin_name(p.name))):
                st = world.stats(name, enc, BASE_MODE, months)
                g = st["cagr"] - mcagr
                row[f"{label}_cagr_median"] = float(np.median(st["cagr"]))
                row[f"{label}_cagr_mean"] = float(np.mean(st["cagr"]))
                row[f"{label}_minus_margin_median"] = float(np.median(g))
                row[f"{label}_minus_margin_mean"] = float(np.mean(g))
                row[f"{label}_beats_margin"] = share_wins(g)
                ind = stats.phase_pooled_mean(g, months)                   # the headline interval convention (R2 step 12e)
                row[f"{label}_minus_margin_indep_mean"] = ind["mean"]
                row[f"{label}_minus_margin_indep_lo"] = ind["lo"]
                row[f"{label}_minus_margin_indep_hi"] = ind["hi"]
                row[f"{label}_minus_margin_indep_df"] = int(ind["df"])
                row[f"{label}_minus_margin_noisy"] = stats.covers_zero(ind["lo"], ind["hi"])
                # the same interval over the SURVIVING windows only: finished windows set to NaN IN PLACE, so every phase
                # keeps its own windows (phase_pooled_mean drops the NaN inside each phase) (R2 step 12f)
                ind_s = stats.phase_pooled_mean(np.where(alive, g, np.nan), months)
                row[f"{label}_minus_margin_survivors_indep_mean"] = ind_s["mean"]
                row[f"{label}_minus_margin_survivors_indep_lo"] = ind_s["lo"]
                row[f"{label}_minus_margin_survivors_indep_hi"] = ind_s["hi"]
                row[f"{label}_minus_margin_survivors_indep_df"] = int(ind_s["df"])
                row[f"{label}_minus_margin_survivors_noisy"] = stats.covers_zero(ind_s["lo"], ind_s["hi"])
                row[f"{label}_minus_margin_median_survivors"] = float(np.median(g[alive])) if alive.any() else float("nan")
                row[f"{label}_minus_margin_mean_survivors"] = float(np.mean(g[alive])) if alive.any() else float("nan")
                row[f"{label}_beats_margin_survivors"] = share_wins(g[alive]) if alive.any() else float("nan")
            rows.append(row)
    return rows


# ---------------------------------------------------------------- item 8: key periods

def key_periods(world, enc):
    """Return and max drawdown inside each fixed key period for every product, its twin, the margin benchmark and the 1x index.

    Start = the close before the period's first day (so the first day's move counts); end = the last close in the period.
    Level mode. The margin position is bought at the start close, same costs as the product."""
    out = []
    for label, d0, d1 in KEY_PERIODS:
        s, e = world.row_before(d0), world.row_on_or_before(d1)
        if s < 0 or world.dates[0] > pd.Timestamp(d0) or e <= s:
            out.append(dict(period=label, covered=False, note=f"not covered: {world.name} data start {world.dates[0].date()}"))
            continue
        sd, ed = world.dates[s], world.dates[e]
        row = dict(period=label, covered=True, first_close=str(sd.date()), last_close=str(ed.date()),
                   underlying_1x=dict(ret=float(world.u_arr[e] / world.u_arr[s] - 1.0), maxdd=metrics.max_drawdown(world.u_arr[s:e + 1])),
                   products={})
        for p in world.specs:
            fund, twin = world.nav(p.name, enc, BASE_MODE), world.nav(world.twin_name(p.name), enc, BASE_MODE)
            mg = world.margin_slice(enc, p.fee, s, e)
            early = [d for d in fund.attrs["early_resets"] if sd < pd.Timestamp(d) <= ed]
            row["products"][p.name] = dict(
                fund=dict(ret=float(fund.iloc[e] / fund.iloc[s] - 1.0), maxdd=metrics.max_drawdown(fund.to_numpy()[s:e + 1])),
                twin=dict(ret=float(twin.iloc[e] / twin.iloc[s] - 1.0), maxdd=metrics.max_drawdown(twin.to_numpy()[s:e + 1])),
                margin=dict(ret=float(mg[-1] - 1.0), maxdd=metrics.max_drawdown(mg)),
                early_resets_in_window=early)
        out.append(row)
    return out


# ---------------------------------------------------------------- item 9: sensitivities

def sensitivity_table(world):
    """The 10-year median gap per product under every encoding, sensitivity and early-reset mode (item 9)."""
    scenarios = [("fixed 2.6% of NAV (base), level", ENCODINGS["fixed"], "level"),
                 ("fixed 1.4%, level", SENSITIVITIES["fixed_lo"], "level"),
                 ("fixed 3.5%, level", SENSITIVITIES["fixed_hi"], "level"),
                 ("rate 1.3 turns + 1.4% (base), level", ENCODINGS["rate"], "level"),
                 ("rate 1.0 turn + 1.4%, level", SENSITIVITIES["rate_lo"], "level"),
                 ("rate 1.5 turns + 1.4%, level", SENSITIVITIES["rate_hi"], "level"),
                 ("fixed (base), early reset at close", ENCODINGS["fixed"], "close"),
                 ("fixed (base), early reset next close", ENCODINGS["fixed"], "next_close"),
                 ("rate (base), early reset at close", ENCODINGS["rate"], "close"),
                 ("rate (base), early reset next close", ENCODINGS["rate"], "next_close"),
                 ("fixed (base), 35% trigger OFF (not the product; shows what the trigger days are worth)", ENCODINGS["fixed"], TRIGGER_OFF),
                 ("rate (base), 35% trigger OFF", ENCODINGS["rate"], TRIGGER_OFF)]
    rows = []
    for label, enc, mode in scenarios:
        row = dict(scenario=label, encoding=enc.name, mode=mode, gap_10y_median={})
        for p in world.specs:
            _, _, g = _gap(world, p.name, enc, mode, 120)
            row["gap_10y_median"][p.name] = float(np.nanmedian(g))
        rows.append(row)
    return rows


# ---------------------------------------------------------------- audit S3 additions: episode split, independent windows

def episode_split(world, enc, months=120, mode=BASE_MODE):
    """For each product: 10-year windows that CONTAIN an early-reset day versus those that do not (median gap, wins),
    plus the same product with the trigger switched off. Shows how much of a headline is one modeled day."""
    rows = []
    s, e = world.month_pairs(months)
    for p in world.specs:
        nav = world.nav(p.name, enc, mode)
        _, _, g = _gap(world, p.name, enc, mode, months)
        _, _, g_off = _gap(world, p.name, enc, TRIGGER_OFF, months)
        dates = [pd.Timestamp(d) for d in nav.attrs["early_resets"]]
        inside = np.zeros(len(s), dtype=bool)
        for d in dates:
            i = int(np.searchsorted(world.dates.values, np.datetime64(d)))
            inside |= (s < i) & (i <= e)
        rows.append(dict(product=p.name, reset=p.reset, encoding=enc.name, mode=mode, horizon_years=months // 12,
                         early_reset_dates=[str(d.date()) for d in dates],
                         n_inside=int(inside.sum()), gap_median_inside=float(np.nanmedian(g[inside])) if inside.any() else float("nan"),
                         wins_inside=share_wins(g[inside]) if inside.any() else float("nan"),
                         n_outside=int((~inside).sum()), gap_median_outside=float(np.nanmedian(g[~inside])), wins_outside=share_wins(g[~inside]),
                         gap_median_all=float(np.nanmedian(g)), wins_all=share_wins(g),
                         gap_median_trigger_off=float(np.nanmedian(g_off)), wins_trigger_off=share_wins(g_off)))
    return rows


def independent_windows(world, enc, months=120, mode=BASE_MODE):
    """Non-overlapping windows: starting at month-end k and every `months` month-ends after it gives one set of independent
    windows; there are `months` such sets (phases). Per product: windows per phase, and the share of phases in which the
    calendar fund won a majority, plus the median / min / max win share across phases. Overlapping starts are not
    independent observations (audit S3 finding 5); this is the honest count."""
    rows = []
    for p in world.specs:
        _, _, g = _gap(world, p.name, enc, mode, months)
        shares, per_phase, all_pos = [], [], 0
        for ph in range(months):
            gp = g[ph::months]
            gp = gp[np.isfinite(gp)]
            if len(gp) == 0:
                continue
            shares.append(float((gp > 0).mean()))
            per_phase.append(int(len(gp)))
            all_pos += int((gp > 0).all())
        shares = np.array(shares)
        rows.append(dict(product=p.name, reset=p.reset, encoding=enc.name, horizon_years=months // 12, phases=int(len(shares)),
                         windows_per_phase_min=int(min(per_phase)), windows_per_phase_max=int(max(per_phase)),
                         win_share_median=float(np.median(shares)), win_share_min=float(shares.min()), win_share_max=float(shares.max()),
                         phases_majority_wins=float((shares > 0.5).mean()), phases_all_positive=float(all_pos / len(shares))))
    return rows


# ---------------------------------------------------------------- R1 E4: what the early-reset trigger watches

TRIGGER_TABLE_PRODUCTS = ("SPYQ", "MQQQ", "QQQP")


def trigger_basis_table(world, products_=TRIGGER_TABLE_PRODUCTS, encodings=("fixed", "rate"), drops=TRIGGER_DROPS, months=120):
    """The 10-year headline under every trigger convention: {close, daily low} x {index price, ETF price} x each drop.

    One row per (product, encoding, basis, trigger, drop): the early-reset dates the model finds, the 10-year median gap
    and the calendar fund's win share (level mode). The index run and the ETF run are compared cell by cell: an
    episode in the index run that the ETF run does not have is `episodes_index_only` (the engine fires on an index move the
    fund, which watches the ETF, would not see), one the ETF run alone has is `episodes_etf_only`.
    Before the ETF's first bar the two bases are the same series, so older episodes always match."""
    cells = {}
    for basis in ("index", "etf"):
        for intraday in (False, True):
            trig, low, info = trigger_series(world.name, basis, intraday)
            w0 = world.variant(trigger=trig, trigger_low=low, trigger_basis=basis, trigger_info=info)
            for drop in drops:
                wv = w0.variant(early_drop=drop)
                for en in encodings:
                    enc = ALL_ENCODINGS[en]
                    for p in wv.specs:
                        if p.name not in products_:
                            continue
                        nav = wv.nav(p.name, enc, BASE_MODE)
                        _, _, g = _gap(wv, p.name, enc, BASE_MODE, months)
                        cells[(p.name, en, basis, "low" if intraday else "close", drop)] = dict(
                            product=p.name, reset=p.reset, underlying=world.name, encoding=en, basis=basis,
                            trigger="low" if intraday else "close", early_drop=drop, horizon_years=months // 12,
                            episodes=list(nav.attrs["early_resets"]), n_episodes=len(nav.attrs["early_resets"]),
                            n_windows=int(np.isfinite(g).sum()), gap_median=float(np.nanmedian(g)), calendar_wins=share_wins(g),
                            terminated=nav.attrs["terminated"])
    rows = []
    for key, row in cells.items():
        p, en, basis, trig, drop = key
        idx_run = row if basis == "index" else cells[(p, en, "index", trig, drop)]
        etf_run = row if basis == "etf" else cells[(p, en, "etf", trig, drop)]
        row.update(match_episodes(idx_run["episodes"], etf_run["episodes"]))
        rows.append(row)
    return rows


def match_episodes(index_dates, etf_dates, window_days=4):
    """Pair the early-reset dates of an index-trigger run with those of an ETF-trigger run of the same product.

    Two dates within `window_days` calendar days are the SAME episode seen on two bases (the market fell through the
    level on the index one day and on the ETF the next). Returns
        episodes_index_only  index-run dates with no ETF-run date near them (the engine fires, the fund would not)
        episodes_etf_only    ETF-run dates with no index-run date near them
        episodes_shifted     "index date -> ETF date" for a pair on different days
    Greedy in date order; each date is used once."""
    idx = sorted(pd.Timestamp(d) for d in index_dates)
    etf = sorted(pd.Timestamp(d) for d in etf_dates)
    used, shifted, idx_only = set(), [], []
    for d in idx:
        near = [j for j, e in enumerate(etf) if j not in used and abs((e - d).days) <= window_days]
        if not near:
            idx_only.append(str(d.date()))
            continue
        j = min(near, key=lambda j: abs((etf[j] - d).days))
        used.add(j)
        if etf[j] != d:
            shifted.append(f"{d.date()} -> {etf[j].date()}")
    etf_only = [str(e.date()) for j, e in enumerate(etf) if j not in used]
    return dict(episodes_index_only=idx_only, episodes_etf_only=etf_only, episodes_shifted=shifted)


def full_sample_returns(world):
    """return_statistics of the whole sample (the decade table's statistics over the full history)."""
    return return_statistics(world.u)


# ---------------------------------------------------------------- full-history statistics (risk table)

def full_history_stats(world, enc, mode=BASE_MODE):
    rows = []
    series_list = [("1x total return", world.u)]
    for p in world.specs:
        series_list += [(p.name, world.nav(p.name, enc, mode)), (world.twin_name(p.name), world.nav(world.twin_name(p.name), enc, mode))]
    for name, s in series_list:
        rows.append(dict(series=name, cagr=metrics.cagr(s), ann_vol=metrics.ann_vol(s), max_drawdown=metrics.max_drawdown(s),
                         calmar=metrics.calmar(s), sortino=metrics.sortino(s), ulcer_index=metrics.ulcer_index(s),
                         time_under_water=metrics.time_under_water(s), longest_recovery_rows=metrics.recovery_days(s),
                         terminal_wealth=float(s.iloc[-1] / s.iloc[0])))
    return rows
