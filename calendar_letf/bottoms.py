"""B13: drawdown-conditioned entries (entries after major market drawdowns). The math and the bookkeeping; `scripts/run_from_bottoms.py`
runs it and writes the report.

The question: someone buys a calendar-reset 2x fund (SPYQ, MQQQ, ...) after a crash. What do they actually own, and how
does it compare with a daily-reset 2x twin, a daily 3x fund, buying the 2x once on margin, and the plain index?

Plain-English map
  * A "trough" is the lowest close of a fall. `drawdown_troughs` finds them from the data: a fall of more than 19% from the
    highest close since the previous all-time high (and, inside a long fall that never regained its old high, from the
    highest close since the previous trough: that is how the Nasdaq-100's 2009 low is found inside its 2000-2015 fall).
  * A "level entry" is the first close at least X below the all-time high, once per fall (`level_entries`): knowable at the time.
  * A "Guppy confirmation" is a trend signal after an entry (`GuppyBook.confirmations`): the slow ribbon of Clean Guppy
    v1 going red -> gray or gray -> green on daily or weekly closes. The fill is the NEXT close after the signal.
  * "Effective leverage" is the leverage a calendar fund really has on a given day. A calendar fund sets its exposure to
    2 x NAV once per period (week / month / quarter) and then lets it drift. After the index has fallen to a fraction x
    of its level at the last reset, the NAV is (2x - 1) of its old value and the exposure is 2x of it, so the leverage is
    2x / (2x - 1): 2.67x after -20%, 3.5x after -30%, 4.33x after -35% (the early-reset trigger), 5x after -37.5%.
    A daily fund is always at its stated leverage.
  * Every fund NAV is computed ONCE over the full history (study.World caches them) and a result for "buy at row s, hold h
    years" is the ratio nav[e] / nav[s] (DESIGN section 8). The exception is the buy-once margin benchmark, which has no
    resets to share and needs one short run per entry (`World.margin_slice`).
Nothing here is a result until the script records it with its provenance.
"""
import numpy as np
import pandas as pd

from . import indicators as ind
from . import kernel, metrics, periods, products, study

HORIZONS_YEARS = study.HORIZONS_YEARS          # 1, 3, 5, 10
MIN_DEPTH = 0.19                               # a fall "deeper than 19%" counts as a drawdown
SHALLOW_MAX = 0.30                             # the brief's name for the shallow group: falls of 19-30%
DEEP_EXTRA = 0.40                              # a trough deeper than this is "major" even if the brief's list omits it
LIST_MATCH_DAYS = 10                          # a listed date matches a found trough within this many calendar days
HINDSIGHT_LIST = {                             # the brief's list of hindsight bottoms (ISO dates)
    "SPX": ("1974-10-03", "1982-08-12", "1987-12-04", "2002-10-09", "2009-03-09", "2020-03-23", "2022-10-12"),
    "NDX": ("2002-10-07", "2009-03-09", "2020-03-23", "2022-12-28"),
}
LIST_EXTRA_YEARS = {"SPX": (), "NDX": (1987, 1990)}   # "plus 1987 and 1990 if the data show them" (brief, NDX)
LEVELS = {"SPX": (0.20, 0.30, 0.40, 0.50), "NDX": (0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80)}
TIMING_MONTHS = (-6, -3, -1, 0, 1, 3, 6)       # entry-timing sensitivity around each hindsight bottom
COST_ENCODINGS = ("fixed", "rate", "fixed_lo", "fixed_hi", "rate_lo", "rate_hi")   # every cost assumption of F5
CONFIRM_YEARS = 2                              # a confirmation later than this after the entry is "never"
LEVERAGE_EPS = 1e-6                            # size of the nudge used to read a fund's exposure from the kernel
CONFIRM_KEYS = ("daily_red_to_gray", "daily_gray_to_green", "weekly_red_to_gray", "weekly_gray_to_green", "daily_green_above_200")
CONFIRM_LABELS = {"daily_red_to_gray": "daily red->gray", "daily_gray_to_green": "daily gray->green",
                  "weekly_red_to_gray": "weekly red->gray", "weekly_gray_to_green": "weekly gray->green",
                  "daily_green_above_200": "daily green & close > 200 EMA"}
SERIES_KEYS = ("fund", "twin", "m3x", "real", "margin", "idx")


# ---------------------------------------------------------------- A. hindsight troughs, found from the data

def _episodes(close, lo, hi):
    """All-time-high episodes of close[lo..hi]: a list of (peak_row, last_row). An episode starts at a close strictly
    above every earlier close in the window and lasts until the row before the next such close (or `hi`)."""
    eps, peak, top = [], lo, close[lo]
    for t in range(lo + 1, hi + 1):
        if close[t] > top:
            eps.append((peak, t - 1))
            peak, top = t, close[t]
    eps.append((peak, hi))
    return eps


def drawdown_troughs(dates, close, min_depth=MIN_DEPTH):
    """Troughs of every drawdown deeper than `min_depth`, found from a close series.

    A drawdown starts at a new all-time high (a close strictly above every earlier close) and lasts until the next one;
    its trough is the lowest close in between (first one if tied). If the fall is deeper than min_depth it is recorded.
    The search then repeats INSIDE that drawdown, starting at the trough: the highest close since the trough is the new
    peak, so a second leg of a long fall (the Nasdaq-100 in 2007-09, inside its 2000-2015 drawdown) and a later 19-30%
    drop (the S&P 500 in 2011) are found too. `level` is 0 for an all-time-high drawdown and 1+ for one found inside
    another. A new all-time high re-arms the search: only a strictly higher close ends a drawdown.
    Returns a list of dicts sorted by trough date: peak_row/peak_date, trough_row/trough_date, depth (negative),
    level, recovery_row/recovery_date (None if the series ends first: the fall is not over), days_to_trough.
    """
    close = np.asarray(close, dtype=np.float64)
    n = len(close)
    out = []

    def scan(lo, hi, level):
        for peak, last in _episodes(close, lo, hi):
            if last == peak:
                continue
            trough = peak + int(np.argmin(close[peak:last + 1]))
            if trough == peak:
                continue
            depth = float(close[trough] / close[peak] - 1.0)
            if depth < -min_depth:
                above = np.flatnonzero(close[peak + 1:] > close[peak])
                rec = int(peak + 1 + above[0]) if len(above) else None
                out.append(dict(peak_row=int(peak), peak_date=str(dates[peak].date()), trough_row=int(trough),
                                trough_date=str(dates[trough].date()), depth=depth, level=level,
                                recovery_row=rec, recovery_date=None if rec is None else str(dates[rec].date()),
                                days_to_trough=int(trough - peak)))
                if trough < last:
                    scan(trough, last, level + 1)

    if n >= 2:
        scan(0, n - 1, 0)
    return sorted(out, key=lambda r: r["trough_row"])


def compare_with_list(troughs, listed, tol_days=LIST_MATCH_DAYS):
    """Match the brief's list against the troughs found. Returns (rows, unmatched):
    rows: one per listed date: dict(listed, found_date or None, days_apart, depth, trough_row)
    unmatched: the found troughs that no listed date matched (differences in the other direction)."""
    rows, used = [], set()
    for d in listed:
        t0 = pd.Timestamp(d)
        best, gap = None, None
        for i, t in enumerate(troughs):
            g = abs((pd.Timestamp(t["trough_date"]) - t0).days)
            if g <= tol_days and (gap is None or g < gap):
                best, gap = i, g
        if best is None:
            rows.append(dict(listed=d, found_date=None, days_apart=None, depth=None, trough_row=None))
        else:
            used.add(best)
            t = troughs[best]
            rows.append(dict(listed=d, found_date=t["trough_date"], days_apart=int((pd.Timestamp(t["trough_date"]) - t0).days),
                             depth=t["depth"], trough_row=t["trough_row"]))
    return rows, [t for i, t in enumerate(troughs) if i not in used]


def tier_troughs(troughs, listed, extra_years=(), deep_extra=DEEP_EXTRA):
    """Split the troughs into 'major' and 'shallow'. Major = matched to the brief's list, or a trough in `extra_years`
    deeper than 30% (the brief's "plus 1987 and 1990"), or any other trough deeper than `deep_extra` (40%: a crash that
    deep is not "shallow" whatever the list says). Shallow = every other trough deeper than 19%.
    Returns (major, shallow, comparison rows, unmatched): `unmatched` is every found trough that no listed date matched
    (what the brief's list left out, whichever tier it fell in)."""
    rows, unmatched = compare_with_list(troughs, listed)
    major_rows = {r["trough_row"] for r in rows if r["trough_row"] is not None}
    for t in unmatched:
        if (int(t["trough_date"][:4]) in extra_years and t["depth"] < -SHALLOW_MAX) or t["depth"] < -deep_extra:
            major_rows.add(t["trough_row"])
    major = [t for t in troughs if t["trough_row"] in major_rows]
    shallow = [t for t in troughs if t["trough_row"] not in major_rows]
    return major, shallow, rows, unmatched


# ---------------------------------------------------------------- B. rule-based entries, knowable at the time

def level_entries(dates, close, levels):
    """For each level X (0.20 = 20%): the rows of the FIRST close at least X below the prior all-time high, one per fall.

    A level is armed at the start and after every new all-time high (a close strictly above all earlier closes). It
    fires on the first close <= ATH x (1 - X), then stays quiet until the next all-time high re-arms it. Uses only the
    closes up to the day itself, so it is knowable at the time.
    Returns (entries, deepest): entries = {X: [dict(row, date, ath_row, ath_date, fall)]},
    deepest = dict(fall, date, ath_date, row): the deepest close-to-high fall in the whole series (a positive number)."""
    close = np.asarray(close, dtype=np.float64)
    top, top_row = close[0], 0
    armed = {x: True for x in levels}
    entries = {x: [] for x in levels}
    worst = dict(fall=0.0, row=0, ath_row=0)
    for t in range(1, len(close)):
        if close[t] > top:
            top, top_row = close[t], t
            armed = {x: True for x in levels}
            continue
        fall = 1.0 - close[t] / top
        if fall > worst["fall"]:
            worst = dict(fall=float(fall), row=t, ath_row=top_row)
        for x in levels:
            if armed[x] and close[t] <= top * (1.0 - x) * (1.0 + 1e-12):
                armed[x] = False
                entries[x].append(dict(row=t, date=str(dates[t].date()), ath_row=top_row, ath_date=str(dates[top_row].date()),
                                       fall=float(fall)))
    worst["date"] = str(dates[worst["row"]].date())
    worst["ath_date"] = str(dates[worst["ath_row"]].date())
    return entries, worst


# ---------------------------------------------------------------- C. Guppy-confirmed entries

def first_transition(state, frm, to, first_index, last_index):
    """Index t of the first bar with first_index <= t <= last_index where state[t-1] == frm and state[t] == to, else None."""
    state = np.asarray(state)
    lo = max(int(first_index), 1)
    hi = min(int(last_index), len(state) - 1)
    if hi < lo:
        return None
    hit = np.flatnonzero((state[lo - 1:hi] == frm) & (state[lo:hi + 1] == to))
    return int(lo + hit[0]) if len(hit) else None


class GuppyBook:
    """Clean Guppy v1 states for one price series, daily and weekly, and the five confirmations after any row.

    Daily: `indicators.guppy` on the daily closes. Weekly: the same on the week-end closes (`week_end_rows`), so a weekly
    bar is dated by its last session. Slow-ribbon state: +1 green (stacked up), -1 red (stacked down), 0 gray. Every
    state on row t uses closes up to row t only (the EMAs are causal), so a signal on row t is known at that close.
    """

    def __init__(self, dates, close):
        self.dates = pd.DatetimeIndex(dates)
        close = np.asarray(close, dtype=np.float64)
        g = ind.guppy(close)
        self.d_state, self.d_above = g["slow_state"], g["above_long"]
        self.w_rows = ind.week_end_rows(self.dates)
        gw = ind.guppy(close[self.w_rows])
        self.w_state = gw["slow_state"]
        self.warm_daily = max(ind.GUPPY_SLOW) - 1                      # first row with a valid slow ribbon (EMA 66)
        self.warm_weekly_row = int(self.w_rows[max(ind.GUPPY_SLOW) - 1]) if len(self.w_rows) >= max(ind.GUPPY_SLOW) else None

    def state_on(self, row):
        """(daily state, weekly state) on `row` as words; the weekly state is that of the last COMPLETED week-end bar."""
        word = {1: "green", 0: "gray", -1: "red"}
        j = int(np.searchsorted(self.w_rows, row, side="right")) - 1
        return word[int(self.d_state[row])], (word[int(self.w_state[j])] if j >= 0 else "n/a")

    def confirmations(self, row, last_row):
        """The first signal strictly after `row` and no later than `last_row`, for each of CONFIRM_KEYS.

        Returns {key: dict(signal_row, signal_date) or None}. None = it did not happen inside the window.
        Daily bars: signal on row t, transition between t-1 and t. Weekly bars: the transition is between two week-end
        bars; the signal row is the week-end row of the later bar (it must be after `row`)."""
        out = {}
        first_d = row + 1
        for key, frm, to in (("daily_red_to_gray", -1, 0), ("daily_gray_to_green", 0, 1)):
            t = first_transition(self.d_state, frm, to, first_d, last_row)
            out[key] = None if t is None else dict(signal_row=t, signal_date=str(self.dates[t].date()))
        j0 = int(np.searchsorted(self.w_rows, row, side="right"))           # first week-end bar after `row`
        j1 = int(np.searchsorted(self.w_rows, last_row, side="right")) - 1
        for key, frm, to in (("weekly_red_to_gray", -1, 0), ("weekly_gray_to_green", 0, 1)):
            j = first_transition(self.w_state, frm, to, j0, j1)
            out[key] = None if j is None else dict(signal_row=int(self.w_rows[j]), signal_date=str(self.dates[self.w_rows[j]].date()))
        both = (self.d_state == 1) & (self.d_above == 1)
        hit = np.flatnonzero(both[first_d:last_row + 1]) if last_row >= first_d else []
        out["daily_green_above_200"] = (dict(signal_row=int(first_d + hit[0]), signal_date=str(self.dates[first_d + hit[0]].date()))
                                        if len(hit) else None)
        return out


# ---------------------------------------------------------------- effective leverage of a calendar fund

def leverage_from_ratio(x, L=2.0):
    """Leverage of a fund that set its exposure to L x NAV when the index stood at 1 and now sees it at x (no costs):
    exposure L x NAV0 x x, NAV NAV0 x (L x - (L - 1)), so the leverage is L x / (L x - (L - 1)). L = 2: 2x / (2x - 1)."""
    x = np.asarray(x, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(L * x - (L - 1.0) > 0, L * x / (L * x - (L - 1.0)), np.nan)


def effective_leverage(u, trig, rate, accrual_fin, accrual_fee, period_end, row, L, spread_per_nav, fee, early_drop,
                       early_mode=kernel.EARLY_LEVEL, trig_low=None):
    """Leverage (exposure / NAV) a buyer holds after the close of `row`, read from the kernel's own state.

    accrual_fin / accrual_fee are the kernel's two accrual arrays (ACT/360 financing, 365-day fee: World.accrual_fin
    and World.accrual_fee); fee is a float; trig_low is the trigger's daily low (None = close-only trigger).

    If `row` is a period end the fund has just reset: exactly L. Otherwise the kernel is re-run from the last period end
    (a reset date, so the run equals the full-history fund from there, DESIGN section 8) to `row`, and then once more with
    the last close nudged up by LEVERAGE_EPS. Between resets the NAV is linear in the index level, with slope equal to the
    fixed exposure, so  exposure = (NAV_nudged - NAV) / eps  and  leverage = exposure / NAV.
    This holds after an early reset too (the kernel's base is then the trigger level, which is not a close).
    Returns NaN if the fund is finished or the nudge would change an early-reset decision."""
    u, trig, rate, accrual_fin, accrual_fee, period_end = (np.asarray(a) for a in (u, trig, rate, accrual_fin,
                                                                                     accrual_fee, period_end))
    if period_end[row]:
        return float(L)
    before = np.flatnonzero(period_end[:row])
    r = int(before[-1]) if len(before) else 0
    seg = slice(r, row + 1)
    args = (np.array(rate[seg], dtype=np.float64), np.array(accrual_fin[seg], dtype=np.float64),
            np.array(accrual_fee[seg], dtype=np.float64), period_end[seg].copy(), float(L), float(spread_per_nav),
            np.full(row + 1 - r, float(fee)), 0.0 if early_drop is None else float(early_drop), early_mode)
    u0, t0 = np.array(u[seg], dtype=np.float64), np.array(trig[seg], dtype=np.float64)
    lo0 = t0.copy() if trig_low is None else np.array(np.asarray(trig_low)[seg], dtype=np.float64)
    nav, flags, _ = kernel.periodic_reset_nav(u0, t0, lo0, *args)
    u1, t1, lo1 = u0.copy(), t0.copy(), lo0.copy()
    u1[-1] *= 1.0 + LEVERAGE_EPS
    t1[-1] *= 1.0 + LEVERAGE_EPS
    lo1[-1] *= 1.0 + LEVERAGE_EPS
    nav1, flags1, _ = kernel.periodic_reset_nav(u1, t1, lo1, *args)
    if nav[-1] <= 0.0 or not np.array_equal(flags, flags1):
        return float("nan")
    return float((nav1[-1] - nav[-1]) / LEVERAGE_EPS / nav[-1])


def leverage_series(world, spec, enc, rows=None, period_end=None):
    """Effective leverage after the close of each row in `rows` (default: every row) of a calendar `spec`, run exactly as
    World.nav runs it (encoding `enc`: spread per NAV, the encoding's fee or the product's, rate x rate turns; the
    world's trigger and its lows; the base early mode). Read from the kernel's own state (effective_leverage), so it
    holds after an early reset too, where the base is the trigger level and not a close (re-grade 2026-11-06: the
    B10 and B15 loops had re-based at the close). NaN where the fund is finished or a nudge flips an early reset."""
    spread, fee, turns = enc.spread_per_nav, (spec.fee if enc.fee is None else enc.fee), enc.rate_turns
    pe = periods.period_end_flags(world.dates, spec.reset) if period_end is None else np.asarray(period_end, dtype=bool)
    trig = world.trigger.to_numpy(dtype=np.float64)
    low = None if world.trigger_low is None else world.trigger_low.to_numpy(dtype=np.float64)
    rate = world.rate_arr * turns
    rows = range(len(world.dates)) if rows is None else rows
    return np.array([effective_leverage(world.u_arr, trig, rate, world.accrual_fin, world.accrual_fee, pe, int(r), spec.L,
                                        spread, fee, spec.early_drop, trig_low=low) for r in rows], dtype=np.float64)


def effective_leverage_nav_ratio(u, nav, reset_row, row, L=2.0):
    """The same leverage from a NAV series and the level at the last reset: L x (U_t / U_0) / (NAV_t / NAV_0).
    Valid when the fund's base is the close of `reset_row` (no early reset since)."""
    return float(L * (u[row] / u[reset_row]) / (nav[row] / nav[reset_row]))


# ---------------------------------------------------------------- windows

def horizon_row(dates, s, years):
    """Row of the last close on or before dates[s] + `years` calendar years; None if the data end first.

    `years` may be fractional (0.5, 1.5, 2.5): the offset is the whole number of calendar months round(years x 12), so
    0.5 years is 6 months and 2.5 years is 30 months. For whole years this equals pandas' years offset exactly (a 29 February
    entry lands on 28 February, as for years=1). A horizon that is not a whole number of months raises ValueError."""
    months = int(round(years * 12))
    if abs(years * 12 - months) > 1e-9:
        raise ValueError(f"horizon_row: {years} years is not a whole number of calendar months")
    target = dates[s] + pd.DateOffset(months=months)
    if target > dates[-1]:
        return None
    return int(np.searchsorted(dates.values, np.datetime64(target), side="right")) - 1


def dollar_values(arr, dates, s, steps, start=10_000.0):
    """What `start` dollars bought at row s became at each horizon in `steps` (years, may be 0.5 / 1.5 / 2.5): the dict
    {"0.5y": ..., "1y": ...} of start x arr[end] / arr[s], with `end` = horizon_row (the last close on or before the entry date
    + round(years x 12) calendar months). NaN where the data end first. The same calendar rule as every other table."""
    vals = {}
    for yrs in steps:
        end = horizon_row(dates, s, yrs)
        vals[f"{yrs:g}y"] = float(start * arr[end] / arr[s]) if end is not None else float("nan")
    return vals


def window_numbers(level, dates, s, e):
    """Return, CAGR (days / 365.25, the repo's rule) and max drawdown of level[s..e] (drawdown measured from the entry
    level and any later high). None if the entry level is not positive."""
    v0, v1 = float(level[s]), float(level[e])
    if not v0 > 0:
        return None
    years = (dates[e] - dates[s]).days / metrics.DAYS_PER_YEAR
    cagr = -1.0 if v1 <= 0 else ((v1 / v0) ** (1.0 / years) - 1.0 if years > 0 else float("nan"))
    return dict(ret=v1 / v0 - 1.0, cagr=cagr, maxdd=metrics.max_drawdown(np.asarray(level[s:e + 1], dtype=np.float64)))


def _on_or_before(dates, d):
    return int(np.searchsorted(dates.values, np.datetime64(pd.Timestamp(d)), side="right")) - 1


# ---------------------------------------------------------------- the evaluator: one underlying, all comparators

class Evaluator:
    """All the comparators for one underlying (a study.World), evaluated at any entry row.

    world      study.World (total-return level, price index, rate, calendar products and twins)
    model_3x   products.ProductSpec of the 3x daily model (UPRO_MODEL / TQQQ_MODEL)
    real       price Series of the real 3x fund (price only, dividends not reinvested) or None
    price      the price index that defines the ENTRIES (drawdowns, falls from the high, index moves) as a Series on the
               world's calendar. Default: the world's own trigger series. Pass the index price when the world's trigger
               watches an ETF: an entry is defined on the index, while the leverage below always reads the world's
               trigger (`self.trigger`) and its daily low, the same series the NAVs were built with.
    """

    def __init__(self, world, model_3x, real=None, price=None):
        self.world = world
        self.model_3x = model_3x
        self.nav3 = kernel.run(model_3x, world.u, world.rate).to_numpy()      # plain rate: the costs are filed, not fitted
        self.real = real
        self.dates = world.dates
        self.idx = world.u_arr
        self.trigger = world.trigger.to_numpy(dtype=np.float64)              # what the early-reset trigger watches
        if price is None:
            self.price = self.trigger
        else:
            if not price.index.equals(world.dates):
                raise ValueError("Evaluator: the entry price index must share the world's calendar")
            self.price = price.to_numpy(dtype=np.float64)
        self._flags = {}

    # --- calendar bookkeeping
    def period_end(self, reset):
        if reset not in self._flags:
            self._flags[reset] = periods.period_end_flags(self.dates, reset)     # the kernel's NYSE period ends
        return self._flags[reset]

    @staticmethod
    def cost_args(spec, enc):
        """(spread per NAV, fee, rate multiplier) of `enc` for `spec`, exactly as World.nav / World.margin_slice use them."""
        return enc.spread_per_nav, (spec.fee if enc.fee is None else enc.fee), enc.rate_turns

    def leverage(self, spec, enc, row):
        spread, fee, turns = self.cost_args(spec, enc)
        w = self.world
        low = None if w.trigger_low is None else w.trigger_low.to_numpy(dtype=np.float64)
        return effective_leverage(w.u_arr, self.trigger, w.rate_arr * turns, w.accrual_fin, w.accrual_fee,
                                  self.period_end(spec.reset), row, spec.L, spread, fee, spec.early_drop, trig_low=low)

    def leverage_path(self, spec, enc, s, n):
        """Effective leverage after each close of rows s .. s+n."""
        return np.array([self.leverage(spec, enc, r) for r in range(s, min(s + n, len(self.dates) - 1) + 1)])

    def last_reset_row(self, spec, row):
        """Row of the last ordinary reset on or before `row` (the fund's base U_0)."""
        pe = np.flatnonzero(self.period_end(spec.reset)[:row + 1])
        return int(pe[-1]) if len(pe) else 0

    # --- one entry
    def evaluate(self, s, spec, enc, horizons=HORIZONS_YEARS):
        """Everything for buying at the close of row s: effective leverage and, per horizon, the return / CAGR / max
        drawdown of the calendar fund, its daily twin, the 3x model, the real 3x fund (None before its first bar), the
        buy-once margin position and the 1x index. Early resets of the calendar fund inside the window are counted.
        Returns dict(date, leverage, horizons={h: {series: numbers or None}})."""
        w = self.world
        fund = w.nav(spec.name, enc).to_numpy()
        twin = w.nav(w.twin_name(spec.name), enc).to_numpy()
        early = [pd.Timestamp(d) for d in w.nav(spec.name, enc).attrs["early_resets"]]
        ends = {h: horizon_row(self.dates, s, h) for h in horizons}
        have = [e for e in ends.values() if e is not None]
        margin = w.margin_slice(enc, spec.fee, s, max(have)) if have else None
        d0 = self.dates[s]
        real_s = None
        if self.real is not None and d0 >= self.real.index[0]:
            real_s = _on_or_before(self.real.index, d0)
        out = dict(date=str(d0.date()), row=int(s), leverage=self.leverage(spec, enc, s), horizons={})
        for h, e in ends.items():
            if e is None:
                out["horizons"][h] = {k: None for k in SERIES_KEYS}
                continue
            row = {"fund": window_numbers(fund, self.dates, s, e), "twin": window_numbers(twin, self.dates, s, e),
                   "m3x": window_numbers(self.nav3, self.dates, s, e), "idx": window_numbers(self.idx, self.dates, s, e),
                   "margin": window_numbers(margin, self.dates[s:e + 1], 0, e - s), "real": None}
            row["fund"]["early_resets"] = int(sum(d0 < d <= self.dates[e] for d in early))
            if real_s is not None and self.dates[e] <= self.real.index[-1]:
                real_e = _on_or_before(self.real.index, self.dates[e])
                row["real"] = window_numbers(self.real.to_numpy(), self.real.index, real_s, real_e)
            out["horizons"][h] = row
        return out

    def quick(self, s, spec, enc, horizons=(1, 3)):
        """Returns only: {h: {fund, twin, m3x, idx}} total returns (None if the data end first)."""
        r = self.evaluate(s, spec, enc, horizons)
        return {h: {k: (None if v is None else v["ret"]) for k, v in r["horizons"][h].items() if k in ("fund", "twin", "m3x", "idx")}
                for h in horizons}


# ---------------------------------------------------------------- timing sensitivity

def timing_rows(world, bottom_row, months=TIMING_MONTHS):
    """For each offset k months: the month-end row nearest to dates[bottom] + k months (offset 0 is the bottom itself).
    Returns [(k, row)]."""
    out = []
    d0 = world.dates[bottom_row]
    me_dates = world.dates[world.me]
    for k in months:
        if k == 0:
            out.append((0, int(bottom_row)))
            continue
        target = d0 + pd.DateOffset(months=k)
        i = int(np.argmin(np.abs((me_dates - target).days.to_numpy())))          # ties: the earlier month-end
        out.append((k, int(world.me[i])))
    return out


def fill_row(signal_row, n_rows):
    """The close at which a signal on `signal_row` is acted on: the NEXT close (the repo's delay-1 convention), or None."""
    return signal_row + 1 if signal_row + 1 < n_rows else None
