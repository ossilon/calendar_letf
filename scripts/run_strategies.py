"""Step 4: the strategy study. Do simple, pre-fixed timing rules beat buy-and-hold of a 2x calendar-reset fund (or its
daily twin) once trading costs, a delay and the rule's own cash returns are charged?

    py scripts\\run_strategies.py        (from calendar_letf/, with CALENDAR_LETF_DATA / _RATES set)

Order of work
  provenance banners -> per underlying (S&P 500, Nasdaq-100): the passive NAV of each product under both cost
  encodings (study.py, FINDINGS F5) -> every plugin variant x delay 1/2/3 x product x encoding as a full-history run
  from the rule's first valid signal -> 10-year multi-start windows (ratios of one wealth path for the rules that
  do not depend on where the investor starts; one run per start for the drawdown stop) -> in-sample vs out-of-sample
  -> delay sensitivity -> Guppy specifics -> a common-window comparison and charts -> markdown, json, csv.

Every rule was fixed BEFORE testing (PROMPT.md); nothing is tuned. Every series is synthetic: SPYQ / MQQQ / QQQP are
modeled, the other products are MODELED designs (products.MODELED_NOTE), and the daily twins are synthetic comparison series.
Base case (R2 step 5): the early-reset trigger watches the ETF's daily low (SPY from 1993-01-29, QQQ from 1999-03-10; the index
price before). The rules' SIGNALS still read the index price. One labeled sensitivity re-runs the headline with the v1 trigger
(index price, close only).
Writes results/strategies.md and .json, results/strategies_*.png and results/raw/strategies_*.csv (git-ignored).
"""
import json
import sys
import time
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from calendar_letf import backtest, metrics, products, provenance, stats, strategies, study  # noqa: E402

OUT = ROOT / "results"
RAW = OUT / "raw"
CAPTION = "Data: TradingView (via local export), FRED. Modeled / synthetic series, not live funds. Not investment advice."
UNDERLYING_NAME = {"SPX": "S&P 500", "NDX": "Nasdaq-100"}
CAL_PRODUCTS = {"SPX": ("SPYQ", "HYP_SPX_M"), "NDX": ("MQQQ", "QQQP")}      # calendar products; their daily twins are added
SPLIT = {"SPX": "1990-01-01", "NDX": "2005-01-01"}                          # in-sample / out-of-sample split (eras, not tuning)
ENC_NAMES = ("fixed", "rate")
ENC = study.ENCODINGS
DELAYS = (1, 2, 3)
HORIZON_MONTHS = 120
ORDER = ["trend_50d", "trend_200d", "trend_200w", "guppy", "guppy_weekly", "vol_threshold", "drawdown_stop"]
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#8a63d2"]
INK, MUTED = "#0b0b0b", "#52514e"


# ---------------------------------------------------------------- formatting helpers
def pp(x, d=2):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:+.{d}f}"


def pc(x, d=1):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.{d}f}%"


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def clean(o):
    """Make a nested result JSON-safe: numpy numbers to Python, NaN to null, Timestamps to text."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return str(o.date())
    return o


def level_stats(vals, idx):
    """CAGR, volatility, max drawdown, Calmar, Sortino and time under water of a level path."""
    s = pd.Series(np.asarray(vals, dtype=np.float64), index=idx)
    return dict(cagr=metrics.cagr(s), ann_vol=metrics.ann_vol(s), max_dd=metrics.max_drawdown(s), calmar=metrics.calmar(s),
                sortino=metrics.sortino(s), tuw=metrics.time_under_water(s))


# ---------------------------------------------------------------- one underlying and everything cached for it
class Und:
    def __init__(self, name, intraday_trigger=True, trigger_basis="etf"):
        """The base case watches the ETF's daily low (intraday_trigger=True, trigger_basis="etf"); the v1 trigger (index
        price, close only) is Und(name, False, "index"), used only by the labeled trigger sensitivity."""
        self.name = name
        self.world, self.prov = study.build_world(name, intraday_trigger=intraday_trigger, trigger_basis=trigger_basis)
        w = self.world
        self.dates = w.dates
        self.n = len(self.dates)
        # The underlying PRICE index: what every signal reads. It is the INDEX price in both cases (the ETF-based trigger
        # series drifts from it by the ETF's fee), so a rule's signals are the same in the base case and the v1 run.
        self.close = study.TRIGGER_FOR[name]().to_numpy(dtype=np.float64)
        self.u = w.u_arr                                            # total-return level: what the 1x benchmark earns
        self.cash = backtest.cash_rate_with_proxy(self.dates)
        self.r_cash = backtest.cash_returns(self.dates, self.cash.to_numpy())
        self.series = []                                            # product series names, calendar product then its twin
        self.duplicate_twins = {}                                   # twin name -> the identical twin shown instead
        shown = []
        for p in CAL_PRODUCTS[name]:
            self.series.append(p)
            tw = w.twin_name(p)
            same = next((o for o in shown if all(np.array_equal(w.nav(o, ENC[e]).to_numpy(), w.nav(tw, ENC[e]).to_numpy()) for e in ENC_NAMES)), None)
            if same:
                self.duplicate_twins[tw] = same                     # e.g. TWIN_HYP_SPX_M is TWIN_SPYQ: same index, same 1.00% fee
            else:
                self.series.append(tw)
                shown.append(tw)
        self.split_row = w.row_before(SPLIT[name])
        self.s_all, self.e_all = w.month_pairs(HORIZON_MONTHS)
        days = self.dates.values.astype("datetime64[D]").astype(np.int64)
        self.years_all = (days[self.e_all] - days[self.s_all]) / metrics.DAYS_PER_YEAR
        self._nav, self._ctx, self._expo, self._runs, self._passive, self._pwin = {}, {}, {}, {}, {}, {}

    # --- inputs
    def nav(self, enc, series):
        key = (enc, series)
        if key not in self._nav:
            self._nav[key] = self.world.nav(series, ENC[enc]).to_numpy(dtype=np.float64, copy=True)
        return self._nav[key]

    def r_prod(self, enc, series):
        return backtest.returns_from_level(self.nav(enc, series))

    def ctx(self, enc, series):
        key = (enc, series)
        if key not in self._ctx:
            self._ctx[key] = backtest.make_context(self.dates, self.close, self.nav(enc, series), self.u)
        return self._ctx[key]

    # --- signals and runs
    def expo(self, strat, enc, series, row=0):
        key = (strat.name, enc, series, row if strat.path_dependent else 0)
        if key not in self._expo:
            self._expo[key] = backtest.signal_from(strat, self.ctx(enc, series), row if strat.path_dependent else 0)
        return self._expo[key]

    def run(self, strat, enc, series, delay, first_signal=None, cost_mult=1.0):
        key = (strat.name, enc, series, delay, first_signal, cost_mult)
        if key not in self._runs:
            row = first_signal or 0
            self._runs[key] = backtest.run_overlay(self.r_prod(enc, series), self.r_cash, self.expo(strat, enc, series, row), delay,
                                                   backtest.half_spread_for(series), cost_mult,
                                                   None if strat.path_dependent else first_signal)
        return self._runs[key]

    # --- benchmarks over the identical window
    def passive(self, enc, series, a):
        key = (enc, series, a)
        if key not in self._passive:
            self._passive[key] = level_stats(self.nav(enc, series)[a:], self.dates[a:])
        return self._passive[key]

    def index1x(self, a):
        key = ("1x", a)
        if key not in self._passive:
            self._passive[key] = level_stats(self.u[a:], self.dates[a:])
        return self._passive[key]

    def passive_windows(self, enc, series):
        key = (enc, series)
        if key not in self._pwin:
            self._pwin[key] = metrics.window_stats(self.nav(enc, series), self.s_all, self.e_all, years=self.years_all)
        return self._pwin[key]


def ordered_variants():
    vs = strategies.all_variants()
    rank = {k: i for i, k in enumerate(ORDER)}
    return sorted(vs, key=lambda v: (rank.get(v[0], len(ORDER)), v[2].name))


# ---------------------------------------------------------------- section computations
def full_history_rows(und, enc, variants):
    """Delay 1/2/3 full-history run of every variant on every product, from the rule's first valid signal."""
    rows = []
    for series in und.series:
        for key, params, strat in variants:
            for d in DELAYS:
                run = und.run(strat, enc, series, d)
                zero = und.run(strat, enc, series, d, cost_mult=0.0)
                dbl = und.run(strat, enc, series, d, cost_mult=2.0)
                a = run.start
                st = level_stats(run.wealth[a:], und.dates[a:])
                pa, ix = und.passive(enc, series, a), und.index1x(a)
                tr = backtest.trade_stats(run.held[a + 1:])
                years = (und.dates[-1] - und.dates[a]).days / metrics.DAYS_PER_YEAR
                cagr0 = metrics.cagr(pd.Series(zero.wealth[a:], index=und.dates[a:]))
                cagr2 = metrics.cagr(pd.Series(dbl.wealth[a:], index=und.dates[a:]))
                rows.append(dict(underlying=und.name, encoding=enc, product=series, rule=strat.name, key=key, params=params, delay=d,
                                 first_signal=str(und.dates[run.first_signal].date()), start=str(und.dates[a].date()), years=years,
                                 **st, edge=st["cagr"] - pa["cagr"], passive_cagr=pa["cagr"], passive_vol=pa["ann_vol"],
                                 passive_max_dd=pa["max_dd"], passive_calmar=pa["calmar"], passive_sortino=pa["sortino"], passive_tuw=pa["tuw"],
                                 index1x_cagr=ix["cagr"], index1x_max_dd=ix["max_dd"], index1x_vol=ix["ann_vol"],
                                 trades=tr["trades"], trades_per_year=tr["trades"] / years, entries=tr["entries"], exits=tr["exits"],
                                 whipsaws_in=tr["whipsaws_in"], whipsaws_cash=tr["whipsaws_cash"], invested_share=tr["invested_share"],
                                 cost_drag_pp_per_year=cagr0 - st["cagr"], cagr_zero_cost=cagr0, cagr_double_cost=cagr2,
                                 edge_double_cost=cagr2 - pa["cagr"]))
    return rows


def window_arrays(und, enc, series, strat, delay):
    """Per-start arrays for the 10-year month-end windows (aligned with und.s_all): strategy CAGR, passive CAGR, edge,
    strategy and passive max drawdown. Rules that do not depend on the start are read off ONE wealth path as
    ratios W[e]/W[s] (as in step 3); the drawdown stop is run once per start with only the history from that start."""
    n_s = len(und.s_all)
    pw = und.passive_windows(enc, series)
    out = dict(cagr_s=np.full(n_s, np.nan), cagr_p=pw["cagr"].copy(), mdd_s=np.full(n_s, np.nan), mdd_p=pw["max_dd"].copy())
    if not strat.path_dependent:
        run = und.run(strat, enc, series, delay)
        ok = und.s_all >= run.start
        st = metrics.window_stats(run.wealth, und.s_all[ok], und.e_all[ok], years=und.years_all[ok])
        out["cagr_s"][ok], out["mdd_s"][ok] = st["cagr"], st["max_dd"]
    else:
        nav, r_prod, r_cash = und.nav(enc, series), und.r_prod(enc, series), und.r_cash
        hs = backtest.half_spread_for(series)
        ctx = und.ctx(enc, series)
        days = und.dates.values.astype("datetime64[D]").astype(np.int64)
        for i, (s, e) in enumerate(zip(und.s_all, und.e_all)):
            sub = ctx.tail_from(s).cut(e - s + 1)
            run = backtest.run_overlay(r_prod[s:e + 1], r_cash[s:e + 1], strat.exposure(sub), delay, hs)
            a = run.start                                     # the window starts at the first fill close, s + delay
            yrs = (days[e] - days[s + a]) / metrics.DAYS_PER_YEAR
            st = metrics.window_stats(run.wealth[a:], [0], [e - s - a], years=[yrs])
            ps = metrics.window_stats(nav[s + a:e + 1], [0], [e - s - a], years=[yrs])
            out["cagr_s"][i], out["mdd_s"][i] = st["cagr"][0], st["max_dd"][0]
            out["cagr_p"][i], out["mdd_p"][i] = ps["cagr"][0], ps["max_dd"][0]
    out["edge"] = out["cagr_s"] - out["cagr_p"]
    return out


TIE = 1e-9      # an edge this small is a tie: the rule held the product throughout and never traded (float noise only)


def summarize_windows(arr, mask):
    """Statistics of the per-start 10-year edges inside `mask`: median, p10 / p90, win and tie shares, the MEAN, and the
    headline interval of the passive study (R2 step 12d): the phase-pooled interval from non-overlapping windows
    (stats.phase_pooled_mean, step = the horizon in months; mean +/- t(df) x SE; ASSUMPTIONS section 7), with the flag
    `noisy` = that interval covers zero. The edges are in start order (the mask keeps a contiguous run of starts)."""
    idx = np.flatnonzero(mask)
    if len(idx) and (idx[-1] - idx[0] + 1) != len(idx):
        # position mod the horizon is the phase only for an unbroken run of starts; a mask with a hole would mix phases
        raise ValueError("summarize_windows: the mask must select one contiguous run of starts (set excluded starts' edges to NaN instead)")
    e = arr["edge"][mask]
    e_ordered = e                              # start order, NaN kept in place for the phase structure
    e = e[np.isfinite(e)]
    if len(e) == 0:
        return dict(n=0, strat_cagr_median=np.nan, passive_cagr_median=np.nan, edge_median=np.nan, edge_p10=np.nan, edge_p90=np.nan,
                    wins=np.nan, ties=np.nan, strat_maxdd_median=np.nan, passive_maxdd_median=np.nan, edge_mean=np.nan,
                    indep_mean=np.nan, indep_se=np.nan, indep_lo=np.nan, indep_hi=np.nan, indep_df=0, indep_k_min=0, indep_k_max=0,
                    too_few_windows=True, noisy=True)
    ok = mask & np.isfinite(arr["edge"])
    ind = stats.phase_pooled_mean(e_ordered, HORIZON_MONTHS)
    # Policy (R2 step 12e): with fewer than MIN_WINDOWS non-overlapping windows in the smallest phase the interval rests on
    # one degree of freedom and the coverage simulation does not reach it (it covers k = 3 to 75), so the row is marked
    # "too few windows" and counts as noisy whatever the interval says.
    too_few = ind["k_min"] < MIN_WINDOWS
    return dict(n=int(len(e)), strat_cagr_median=float(np.median(arr["cagr_s"][ok])), passive_cagr_median=float(np.median(arr["cagr_p"][ok])),
                edge_median=float(np.median(e)), edge_p10=float(np.percentile(e, 10)), edge_p90=float(np.percentile(e, 90)),
                wins=float((e > TIE).mean()), ties=float((np.abs(e) <= TIE).mean()), strat_maxdd_median=float(np.median(arr["mdd_s"][ok])),
                passive_maxdd_median=float(np.median(arr["mdd_p"][ok])), edge_mean=float(np.mean(e)),
                indep_mean=ind["mean"], indep_se=ind["se"], indep_lo=ind["lo"], indep_hi=ind["hi"], indep_df=int(ind["df"]),
                indep_k_min=int(ind["k_min"]), indep_k_max=int(ind["k_max"]), too_few_windows=bool(too_few),
                noisy=bool(too_few or stats.covers_zero(ind["lo"], ind["hi"])))


MIN_WINDOWS = 3      # smallest phase size at which the phase-pooled interval is read at all (coverage simulated from k = 3)


ERAS = {"SPX": ("1990-01-01", "2009-01-01"), "NDX": ("2005-01-01", "2009-01-01")}      # the sub-era boundaries of FINDINGS F14
NW_LAGS = (21, 63, 252)       # Bartlett lags (a month, a quarter, a year of sessions) for the era-difference test


def era_tests(und, enc, variants):
    """Is a rule's edge in one era different from its edge in another? The daily log edge d_t = ln(W_t / W_{t-1}) -
    ln(N_t / N_{t-1}) (rule wealth over passive NAV, delay 1, from the rule's first valid row); per era its mean (x 252,
    pp a year) and Newey-West standard error at three Bartlett lags; z for the difference between the last two eras
    (e.g. 1990-2008 against 2009-2026) and for all history before the last boundary against after. A z within +/- 2 at
    every lag means the era difference is not distinguishable from chance on this one history. FINDINGS F14's heading
    rests on this test (R2 step 12e)."""
    rows = []
    bounds = [und.world.row_before(d) for d in ERAS[und.name]]
    for series in und.series:
        nav = und.nav(enc, series)
        for key, params, strat in variants:
            run = und.run(strat, enc, series, 1)
            a = run.start
            with np.errstate(divide="ignore", invalid="ignore"):
                d = np.diff(np.log(run.wealth)) - np.diff(np.log(nav))          # d[t - 1] is the edge into row t
            cuts = [a] + [b for b in bounds if b > a] + [und.n - 1]
            eras = []
            for i, j in zip(cuts[:-1], cuts[1:]):
                if j <= i + 1:
                    continue
                x = d[i:j]
                x = x[np.isfinite(x)]
                se = {str(L): float(np.sqrt(stats.newey_west_variance(x, L) / len(x)) * 252 * 100) for L in NW_LAGS} if len(x) > max(NW_LAGS) else {}
                eras.append(dict(start=str(und.dates[i].date()), end=str(und.dates[j].date()), n=int(len(x)),
                                 mean_pp=float(x.mean() * 252 * 100) if len(x) else float("nan"), se_pp=se, _x=x))
            if len(eras) >= 2:
                last_two = {str(L): stats.era_difference_z(eras[-2]["_x"], eras[-1]["_x"], L) for L in NW_LAGS}
                pre = np.concatenate([e["_x"] for e in eras[:-1]])
                pre_post = {str(L): stats.era_difference_z(pre, eras[-1]["_x"], L) for L in NW_LAGS}
            else:
                last_two, pre_post = {}, {}
            for e in eras:
                e.pop("_x")
            rows.append(dict(underlying=und.name, encoding=enc, product=series, rule=strat.name, key=key, lags=list(NW_LAGS),
                             eras=eras, z_last_two=last_two, z_pre_post=pre_post))
    return rows


def era_rows(und, enc, variants):
    """Full-run CAGR edge over passive inside each sub-era (delay 1): the rule's first valid row to the first boundary,
    boundary to boundary, last boundary to the end. Descriptive (one run per era, no interval); the window statistics
    above carry the intervals. Replaces a v1 scratch split that was never re-run."""
    rows = []
    bounds = [und.world.row_before(d) for d in ERAS[und.name]]
    for series in und.series:
        nav = und.nav(enc, series)
        for key, params, strat in variants:
            run = und.run(strat, enc, series, 1)
            cuts = [run.start] + [b for b in bounds if b > run.start] + [und.n - 1]      # a rule that starts after a boundary skips that era
            for i, j in zip(cuts[:-1], cuts[1:]):
                if j <= i:
                    continue
                yrs = (und.dates[j] - und.dates[i]).days / metrics.DAYS_PER_YEAR
                s = metrics.cagr(np.array([run.wealth[i], run.wealth[j]]), years=yrs)
                p = metrics.cagr(np.array([nav[i], nav[j]]), years=yrs)
                rows.append(dict(underlying=und.name, encoding=enc, product=series, rule=strat.name, key=key,
                                 era=f"{und.dates[i].date()} to {und.dates[j].date()}",
                                 start=str(und.dates[i].date()), end=str(und.dates[j].date()), years=float(yrs),
                                 edge=float(s - p), strat_cagr=float(s), passive_cagr=float(p)))
    return rows


def multi_start_rows(und, enc, variants, raw_out):
    """10-year month-end windows, delay 1/2/3, for the whole sample and for windows entirely inside each era."""
    rows = []
    for series in und.series:
        for key, params, strat in variants:
            for d in DELAYS:
                arr = window_arrays(und, enc, series, strat, d)
                masks = {"all": np.ones(len(und.s_all), dtype=bool), "in_sample": und.e_all <= und.split_row,
                         "out_of_sample": und.s_all >= und.split_row}
                for scope, m in masks.items():
                    rows.append(dict(underlying=und.name, encoding=enc, product=series, rule=strat.name, key=key, delay=d, scope=scope,
                                     **summarize_windows(arr, m)))
                if d == 1:
                    raw_out.append(pd.DataFrame(dict(underlying=und.name, encoding=enc, product=series, rule=strat.name,
                                                     start=und.dates[und.s_all].strftime("%Y-%m-%d"), strat_cagr=arr["cagr_s"],
                                                     passive_cagr=arr["cagr_p"], edge=arr["edge"], strat_maxdd=arr["mdd_s"],
                                                     passive_maxdd=arr["mdd_p"])))
    return rows


def subperiod_rows(und, enc, variants):
    """Full-run CAGR edge over passive in the two eras (delay 1): start of the rule to the split, and the split to the end."""
    rows = []
    sp = und.split_row
    for series in und.series:
        nav = und.nav(enc, series)
        for key, params, strat in variants:
            run = und.run(strat, enc, series, 1)
            a = run.start

            def edge(i, j):
                yrs = (und.dates[j] - und.dates[i]).days / metrics.DAYS_PER_YEAR
                s = metrics.cagr(np.array([run.wealth[i], run.wealth[j]]), years=yrs)
                p = metrics.cagr(np.array([nav[i], nav[j]]), years=yrs)
                return s - p, s, p
            e_is, s_is, p_is = edge(a, sp)
            e_oos, s_oos, p_oos = edge(sp, und.n - 1)
            rows.append(dict(underlying=und.name, encoding=enc, product=series, rule=strat.name, key=key, split=str(und.dates[sp].date()),
                             start=str(und.dates[a].date()), edge_in_sample=e_is, strat_cagr_in_sample=s_is, passive_cagr_in_sample=p_is,
                             edge_out_of_sample=e_oos, strat_cagr_out_of_sample=s_oos, passive_cagr_out_of_sample=p_oos))
    return rows


def common_window_rows(und, enc, variants, common_row):
    """Every rule from the SAME first signal row (the latest first-valid row among them), delay 1."""
    rows = []
    for series in und.series:
        for key, params, strat in variants:
            run = und.run(strat, enc, series, 1, first_signal=common_row)
            a = run.start
            st = level_stats(run.wealth[a:], und.dates[a:])
            pa, ix = und.passive(enc, series, a), und.index1x(a)
            rows.append(dict(underlying=und.name, encoding=enc, product=series, rule=strat.name, key=key, start=str(und.dates[a].date()),
                             **st, edge=st["cagr"] - pa["cagr"], passive_cagr=pa["cagr"], passive_max_dd=pa["max_dd"],
                             passive_calmar=pa["calmar"], index1x_cagr=ix["cagr"], index1x_max_dd=ix["max_dd"]))
    return rows


def guppy_rows(und, variants, full_rows):
    """Guppy trade and jump counts on the underlying (product independent), next to the live product's full-history result."""
    out = []
    live = CAL_PRODUCTS[und.name][0]
    ctx = und.ctx("fixed", live)
    for key, params, strat in variants:
        if not key.startswith("guppy"):
            continue
        dg = strat.diagnostics(ctx)
        r = next(x for x in full_rows if x["product"] == live and x["rule"] == strat.name and x["delay"] == 1)
        out.append(dict(underlying=und.name, rule=strat.name, bar="week" if key.endswith("weekly") else "day", filter_200=params["filter_200"],
                        **dg, start=r["start"], trades_after_delay1=r["trades"], trades_per_year=r["trades_per_year"],
                        whipsaws_in=r["whipsaws_in"], whipsaws_cash=r["whipsaws_cash"], invested_share=r["invested_share"],
                        cagr_live_product=r["cagr"], passive_cagr=r["passive_cagr"], edge=r["edge"], product=live))
    return out


def delay_flags(ms_rows, und_name, enc):
    """Per (product, rule): 10-year median edge at delay 1/2/3 and a flag if it changes sign or falls to half or less of
    its delay-1 size at delay 2 or 3."""
    out = []
    sel = [r for r in ms_rows if r["underlying"] == und_name and r["encoding"] == enc and r["scope"] == "all"]
    for series in dict.fromkeys(r["product"] for r in sel):
        for rule in dict.fromkeys(r["rule"] for r in sel):
            e = {r["delay"]: r["edge_median"] for r in sel if r["product"] == series and r["rule"] == rule}
            flag = ""
            if np.isfinite(e[1]) and abs(e[1]) > 1e-6:                  # an edge of 0.0001 pp or less is a tie, not a sign
                for d in (2, 3):
                    if np.isfinite(e[d]) and abs(e[d]) > 1e-6 and np.sign(e[d]) != np.sign(e[1]):
                        flag = "SIGN CHANGES"
                    elif not flag and np.isfinite(e[d]) and abs(e[d]) <= 0.5 * abs(e[1]):
                        flag = "HALVES"
            out.append(dict(underlying=und_name, encoding=enc, product=series, rule=rule, edge_d1=e[1], edge_d2=e[2], edge_d3=e[3], flag=flag))
    return out


def trigger_sensitivity(und, old, ms_rows, variants):
    """The headline under the v1 trigger (index price, close only) next to the base case: 10-year median edge, share of
    starts the rule wins and the passive median CAGR, delay 1, fixed encoding, per product and rule. `und` is the base
    case, `old` the same underlying built with the v1 trigger; the base numbers come from `ms_rows` (the base multi-start
    rows, fixed encoding). Also the early-reset dates of every product under both triggers."""
    rows = []
    all_windows = np.ones(len(old.s_all), dtype=bool)
    rules = list(dict.fromkeys(r["rule"] for r in ms_rows))
    strats = {s.name: s for _, _, s in variants}
    for series in old.series:
        for rule in rules:
            b = next(x for x in ms_rows if x["product"] == series and x["rule"] == rule and x["delay"] == 1 and x["scope"] == "all")
            v = summarize_windows(window_arrays(old, "fixed", series, strats[rule], 1), all_windows)
            rows.append(dict(underlying=old.name, product=series, rule=rule, base_edge_median=b["edge_median"], base_wins=b["wins"],
                             base_passive_cagr_median=b["passive_cagr_median"], v1_edge_median=v["edge_median"], v1_wins=v["wins"],
                             v1_passive_cagr_median=v["passive_cagr_median"]))
    resets = {s: dict(base=list(und.world.nav(s, ENC["fixed"]).attrs["early_resets"]),
                      v1=list(old.world.nav(s, ENC["fixed"]).attrs["early_resets"])) for s in old.series if not s.startswith("TWIN_")}
    return dict(rows=rows, early_resets=resets, v1_trigger=old.prov["trigger_text"], base_trigger=und.prov["trigger_text"])


# ---------------------------------------------------------------- charts
def plot_equity(und, variants, common_row, path):
    enc = "fixed"
    series = CAL_PRODUCTS[und.name][0]
    rows = [r for r in COMMON[und.name][enc] if r["product"] == series]
    best = max(rows, key=lambda r: r["cagr"])
    worst = min(rows, key=lambda r: r["cagr"])
    a = common_row + 1
    fig, ax = plt.subplots(figsize=(10, 6), dpi=130)
    d = und.dates[a:]
    ax.plot(d, und.u[a:] / und.u[a], color=MUTED, lw=1.3, label="1x total return (underlying)")
    nav = und.nav(enc, series)
    ax.plot(d, nav[a:] / nav[a], color=COLORS[0], lw=1.4, label=f"{series} passive (buy and hold)")
    for r, color, tag in ((best, COLORS[2], "best"), (worst, COLORS[1], "worst")):
        strat = next(s for _, _, s in variants if s.name == r["rule"])
        run = und.run(strat, enc, series, 1, first_signal=common_row)
        ax.plot(d, run.wealth[a:], color=color, lw=1.3, label=f"{tag} rule by CAGR: {r['rule']} ({pc(r['cagr'])} vs {pc(r['passive_cagr'])} passive)")
    ax.set_yscale("log")
    ax.set_ylabel("growth of 1 (log scale)", color=MUTED)
    ax.set_title(f"{UNDERLYING_NAME[und.name]}: {series} (modeled, not the live fund) vs best and worst timing rule  [synthetic]\n"
                 f"{d[0].date()} to {d[-1].date()}; delay 1; fixed-spread encoding; level mode; best/worst picked after the fact from 12 variants",
                 fontsize=9, color=INK, loc="left")
    ax.grid(True, which="major", color="#d9d8d3", lw=0.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.text(0.01, 0.005, CAPTION, fontsize=7, color=MUTED)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------- the run
COMMON = {}


def main():
    wall0 = time.perf_counter()
    OUT.mkdir(exist_ok=True)
    RAW.mkdir(exist_ok=True)
    variants = ordered_variants()
    print("=" * 100 + "\nSTEP 4: timing rules on 2x calendar-reset funds and daily twins (all series MODELED / synthetic)")
    unds, t_load = {}, time.perf_counter()
    for name in ("SPX", "NDX"):
        unds[name] = Und(name)
        print("\n" + unds[name].prov["banner"])
        print(f"TRIGGER BASE CASE: {unds[name].prov['trigger_text']}; signals read the index price {unds[name].prov['price_symbol']}.")
        print(f"reference rate: {unds[name].prov['rate']}")
        print(f"cash: {unds[name].cash.attrs['source']}; proxy rows {unds[name].cash.attrs['proxy_rows']} "
              f"(until {unds[name].cash.attrs['proxy_until']}); last DTB3 date {unds[name].cash.attrs['rate_last_date']}; stale rows {unds[name].cash.attrs['stale_rows']}")
        print(products.banner(*unds[name].world.specs, *unds[name].world.twins.values(),
                              overrides="spread_per_nav and the rate multiplier come from the cost encodings, not from the registry"))
    load_s = time.perf_counter() - t_load
    # Provenance: every price and FRED file the worlds read, plus the cash rate (DTB3, and TB3MS where it is the proxy).
    cash_rates = ["DTB3"] + (["TB3MS"] if any(u.cash.attrs["proxy_rows"] for u in unds.values()) else [])
    inputs = study.inputs_for({n: u.world for n, u in unds.items()}, {n: u.prov for n, u in unds.items()}, extra_rates=cash_rates)
    banner = (provenance.banner_lines(inputs) + [ln for u in unds.values() for ln in study.conventions_lines(u.world)]
              + ["Signals read the INDEX price (SP:SPX, NASDAQ:NDX), never the ETF-based trigger series.", products.MODELED_NOTE])
    print("\nINPUTS AND CONVENTIONS:\n" + "\n".join(banner))
    print("\nCOST ENCODINGS (both ASSUMED, both run everywhere):")
    for e in ENC.values():
        print("  " + e.describe() + f"  | {e.source}")
    print("HALF-SPREADS (per unit of position changed):")
    for k, v in backtest.HALF_SPREADS.items():
        print(f"  {k}: {v['value']:.2%} [{v['status']}] {v['source']}")
    print("RULES:")
    for key, params, strat in variants:
        print(f"  {strat.name:20} params {params or '{}'} path_dependent={strat.path_dependent}")
    n_var = len(variants)
    print(f"MULTIPLE-TESTING COUNT: {n_var} rule variants x {len(DELAYS)} delays = {n_var * len(DELAYS)} rule-delay runs per product, "
          f"on 3 (S&P 500) + 4 (Nasdaq-100) distinct products x 2 encodings. All rules fixed before testing; none tuned.")

    R = dict(meta={}, full={}, multi_start={}, subperiod={}, eras={}, era_tests={}, delay={}, common={}, guppy={}, rules=[], trigger_sensitivity={})
    raw_ms, md_common_rows = [], {}
    for name, und in unds.items():
        t0 = time.perf_counter()
        R["full"][name], R["multi_start"][name], R["subperiod"][name], R["delay"][name], R["common"][name] = {}, {}, {}, {}, {}
        R["eras"][name] = {}
        R["era_tests"][name] = {}
        COMMON[name] = {}
        first = {}
        for key, params, strat in variants:                       # first valid signal of each rule on this underlying
            e = und.expo(strat, "fixed", und.series[0], 0)
            first[strat.name] = int(np.argmax(np.isfinite(e)))
        common_row = max(first.values())
        for enc in ENC_NAMES:
            R["full"][name][enc] = full_history_rows(und, enc, variants)
            R["multi_start"][name][enc] = multi_start_rows(und, enc, variants, raw_ms)
            R["subperiod"][name][enc] = subperiod_rows(und, enc, variants)
            R["eras"][name][enc] = era_rows(und, enc, variants)
            R["era_tests"][name][enc] = era_tests(und, enc, variants)
            R["delay"][name][enc] = delay_flags(R["multi_start"][name][enc], name, enc)
            R["common"][name][enc] = common_window_rows(und, enc, variants, common_row)
            COMMON[name][enc] = R["common"][name][enc]
        R["guppy"][name] = guppy_rows(und, variants, R["full"][name]["fixed"])
        R["rules"].append(dict(underlying=name, first_valid={k: str(und.dates[v].date()) for k, v in first.items()},
                               common_first_signal=str(und.dates[common_row].date())))
        plot_equity(und, variants, common_row, OUT / f"strategies_{name}.png")
        und.common_row = common_row
        print(f"{name}: computed in {time.perf_counter() - t0:.2f} s; common first signal {und.dates[common_row].date()}")
        # labeled sensitivity: the v1 trigger (index price, close only), headline only
        t1 = time.perf_counter()
        old = Und(name, intraday_trigger=False, trigger_basis="index")
        R["trigger_sensitivity"][name] = trigger_sensitivity(und, old, R["multi_start"][name]["fixed"], variants)
        print(f"{name}: v1-trigger sensitivity ({old.prov['trigger_text']}) in {time.perf_counter() - t1:.2f} s")

    write_outputs(R, unds, variants, raw_ms, load_s, wall0, inputs, banner)


# ---------------------------------------------------------------- report
def prov(und, enc, window, note=""):
    p = und.prov
    e = ENC[enc]
    live_hs = backtest.HALF_SPREADS["tradr_live"]["value"]
    mod_hs = backtest.HALF_SPREADS["modeled_or_twin"]["value"]
    return (f"*Underlying: {UNDERLYING_NAME[und.name]} total return {p['first']} to {p['last']} (signals read the price index {p['price_symbol']}). "
            f"Window: {window}. Encoding: {e.describe()}. Early-reset trigger: {p['trigger_text']}, drop 35%, mode level. "
            f"Cash: {und.cash.attrs['source']} ({und.cash.attrs['proxy_rows']} proxy rows). "
            f"Half-spread {live_hs:.2%} on SPYQ / MQQQ / QQQP, {mod_hs:.2%} on modeled products and twins "
            f"[ASSUMED]; fees: the products' own (live VERIFIED, others 1.00% ASSUMED). Cost, spread and rate turns ASSUMED (fitted 2024-26)."
            f"{(' ' + note) if note else ''} All series synthetic; products other than SPYQ / MQQQ / QQQP are MODELED designs, twins are comparison series.*\n")


def write_outputs(R, unds, variants, raw_ms, load_s, wall0, inputs, banner):
    run_date = str(pd.Timestamp.today().date())
    pd.concat(raw_ms, ignore_index=True).to_csv(RAW / "strategies_multistart_10y_delay1.csv", index=False)
    for name in unds:
        pd.DataFrame([{k: v for k, v in r.items() if k != "params"} for enc in ENC_NAMES for r in R["full"][name][enc]]).to_csv(
            RAW / f"strategies_full_history_{name}.csv", index=False)

    md = []
    md.append("# Timing rules on 2x calendar-reset funds and their daily twins (step 4)\n")
    md.append(f"Run {run_date}. Script `scripts/run_strategies.py`; numbers in `strategies.json`; tables per start in `results/raw/` (git-ignored). "
              "**Every series here is synthetic. SPYQ, MQQQ and QQQP are modeled, not the live funds; HYP_SPX_M is a MODELED design (" + products.MODELED_NOTE + "); "
              "TWIN_* are synthetic daily-reset comparison funds. Research tooling, not investment advice.**\n")
    md.append("## Inputs and conventions\n")
    md.append("```text\n" + "\n".join(banner) + "\n```\n")
    md.append("## Method in brief\n")
    md.append("- **Rules (all fixed before testing, none tuned).** " + "; ".join(f"`{s.name}`" for _, _, s in variants) + ". Trend rules: hold while the underlying's close is above its "
              "50-day / 200-day / 200-week average (simple or exponential). Clean Guppy: buy when the slow ribbon (EMAs 24..66) stacks up, sell when it stacks down "
              "(from any state), hold through gray, start flat; `_f200` also requires close > 200 EMA; daily and weekly bars. `vol_threshold`: hold while the 21-day "
              "realized volatility of the underlying is below 25% a year. `drawdown_stop`: cash while the product NAV is more than 30% below its running peak, "
              "back in at a new peak (path-dependent).")
    md.append(f"- **Multiple-testing count: {len(variants)} rule variants** ({sum(1 for k, _, _ in variants if k.startswith('trend'))} trend, "
              f"{sum(1 for k, _, _ in variants if k.startswith('guppy'))} Guppy, 1 volatility, 1 drawdown stop), each at 3 delays = {len(variants) * 3} rule-delay runs per product, "
              "on 3 distinct products on the S&P 500 and 4 on the Nasdaq-100 x 2 cost encodings. The best of them is inflated by that count; a pre-fixed rule such as Guppy's original lengths counts as one. "
              "The in/out-of-sample split below is an era check on rules that were never tuned, not a validation of a fitted rule.")
    md.append("- **Execution.** A signal decided on close t is filled at close t+delay and earns the product's return from t+delay to t+delay+1. Base delay 1; 2 and 3 are the delay tests. "
              "Wealth = (position x product NAV return) + (1 - position) x cash return, less half_spread x |change of position| each time the position changes. "
              "Cash earns the 3-month T-bill (FRED DTB3, known the day before). The run starts at the rule's first valid signal, already holding its first position "
              "(no charge for the first purchase, for rules and passive alike). Buying mid-period gets the floated leverage automatically (NAV units).")
    md.append("- **Edge** = the rule's CAGR minus buy-and-hold of the same product over the identical window, in percentage points a year (pp). Positive = the rule did better. "
              "**Cost drag** = CAGR with zero trading cost minus CAGR with the half-spread, pp a year. **Whipsaw** = a COMPLETE in-market spell (entry then exit) or cash spell shorter than 10 trading days. "
              "**Trades** = changes of position (entries + exits).")
    md.append("- **Multi-start.** Every month-end start with 10 years ahead. Rules that read only the past (trend, Guppy, volatility) have one wealth path and the window is the ratio "
              "W[end]/W[start], as in step 3; this treats a Guppy follower as already running (holding its previous state) on the start date. The drawdown stop depends on where the investor starts, "
              "so it is run once per start with only the history from that start (its window begins at the first fill close, start + delay). In-sample / out-of-sample windows lie ENTIRELY "
              f"inside each era (split {SPLIT['SPX']} on the S&P 500, {SPLIT['NDX']} on the Nasdaq-100).")
    md.append("- **Half-spread assumptions.**\n")
    md.append(md_table(["applies to", "per unit of position changed", "status", "source"],
                       [[k, f"{v['value']:.2%}", v["status"], v["source"]] for k, v in backtest.HALF_SPREADS.items()]))
    md.append("- **Cost convention note.** DESIGN section 7 writes the cost as |dw| x 2 x half_spread but also says a round trip costs two half-spreads; the code charges one half-spread per unit "
              "of position changed (round trip = exactly 2 half-spreads). The column `edge @2x cost` in table 1 repeats every run with the literal double charge.\n")
    md.append("## Rules and when each first has a signal\n")
    rule_rows = []
    for key, params, strat in variants:
        rule_rows.append([f"`{strat.name}`", json.dumps(params) if params else "defaults", json.dumps(strat.params), strat.warmup, "yes" if strat.path_dependent else "no"]
                         + [next(x for x in R["rules"] if x["underlying"] == n)["first_valid"][strat.name] for n in unds])
    md.append(md_table(["rule", "variant", "all parameters", "nominal warm-up rows", "path-dependent", "first signal SPX", "first signal NDX"], rule_rows))
    for n in unds:
        x = next(x for x in R["rules"] if x["underlying"] == n)
        md.append(f"- {n}: the common window of table 6 starts with a signal on {x['common_first_signal']} (the latest first signal of any rule).")
    md.append("")

    for name, und in unds.items():
        un = UNDERLYING_NAME[name]
        full, ms, sub, dl = R["full"][name], R["multi_start"][name], R["subperiod"][name], R["delay"][name]
        series_names = und.series
        md.append(f"\n---\n\n# {un}\n")
        md.append("Underlying banner: `" + und.prov["banner"] + "`\n")
        if und.duplicate_twins:
            md.append("Twins shown once: " + "; ".join(f"{a} is identical to {b} (same index, same fee, same costs)" for a, b in und.duplicate_twins.items()) + ".\n")
        md.append(f"Reference rate: {und.prov['rate']['source']}; proxy rows {und.prov['rate']['proxy_rows']}. Cash: {und.cash.attrs['source']}; proxy rows "
                  f"{und.cash.attrs['proxy_rows']} (until {und.cash.attrs['proxy_until']}); last DTB3 date {und.cash.attrs['rate_last_date']}, stale rows {und.cash.attrs['stale_rows']}.\n")

        # ---- headline: 10-year multi-start edge
        md.append(f"## {un} headline. 10-year median edge over buy-and-hold (delay 1, month-end starts): fixed | rate encoding; share of starts the rule beats buy-and-hold\n")
        for enc in ENC_NAMES[:1]:
            md.append(prov(und, enc, "month-end starts, 10-year horizon, delay 1", "Cells: median edge pp | wins; first the fixed-spread encoding, then the rate-proportional one."))
        hdr = ["rule"] + [f"{s}" for s in series_names]
        rows = []
        for key, params, strat in variants:
            cells = [f"`{strat.name}`"]
            for s in series_names:
                parts = []
                for enc in ENC_NAMES:
                    r = next(x for x in ms[enc] if x["product"] == s and x["rule"] == strat.name and x["delay"] == 1 and x["scope"] == "all")
                    parts.append(f"{pp(r['edge_median'])} ({pc(r['wins'], 0)})")
                cells.append(" \\| ".join(parts))
            rows.append(cells)
        md.append(md_table(hdr, rows))

        # ---- 1 full history
        md.append(f"## {un} 1. Full-history runs, delay 1, fixed-spread encoding (each rule from its first valid signal; benchmarks over the identical window)\n")
        md.append(f"![{un} equity curves](strategies_{name}.png)\n")
        md.append("*Chart: " + UNDERLYING_NAME[name] + " common window, " + CAL_PRODUCTS[name][0] + ", delay 1, fixed-spread encoding; best and worst rule by CAGR picked after the fact. " + CAPTION + "*\n")
        for s in series_names:
            md.append(f"**{s}**\n")
            md.append(prov(und, "fixed", f"each rule's own start to {und.prov['last']}"))
            sel = [r for r in full["fixed"] if r["product"] == s and r["delay"] == 1]
            md.append(md_table(["rule", "start", "CAGR", "edge pp", "edge @2x cost", "vol", "max DD", "Calmar", "Sortino", "time under water", "trades/yr", "cost drag pp/yr",
                                "whipsaws in/cash", "invested", "passive CAGR", "passive max DD", "passive Calmar", "1x CAGR", "1x max DD"],
                               [[f"`{r['rule']}`", r["start"], pc(r["cagr"]), pp(r["edge"]), pp(r["edge_double_cost"]), pc(r["ann_vol"], 0), pc(r["max_dd"], 0), f"{r['calmar']:.2f}",
                                 f"{r['sortino']:.2f}", pc(r["tuw"], 0), f"{r['trades_per_year']:.2f}", f"{r['cost_drag_pp_per_year'] * 100:.3f}",
                                 f"{r['whipsaws_in']}/{r['whipsaws_cash']}", pc(r["invested_share"], 0), pc(r["passive_cagr"]), pc(r["passive_max_dd"], 0),
                                 f"{r['passive_calmar']:.2f}", pc(r["index1x_cagr"]), pc(r["index1x_max_dd"], 0)] for r in sel]))
        md.append("**Rate-proportional encoding (compact), delay 1**\n")
        md.append(prov(und, "rate", f"each rule's own start to {und.prov['last']}"))
        rows = []
        for key, params, strat in variants:
            cells = [f"`{strat.name}`"]
            for s in series_names:
                r = next(x for x in full["rate"] if x["product"] == s and x["rule"] == strat.name and x["delay"] == 1)
                cells.append(f"{pc(r['cagr'])} / {pc(r['max_dd'], 0)} (edge {pp(r['edge'])})")
            rows.append(cells)
        md.append(md_table(["rule (CAGR / max DD (edge pp))"] + series_names, rows))
        md.append("**Full-history CAGR by delay 1 / 2 / 3 (fixed encoding)**\n")
        rows = []
        for key, params, strat in variants:
            cells = [f"`{strat.name}`"]
            for s in series_names:
                cells.append(" / ".join(pc(next(x for x in full["fixed"] if x["product"] == s and x["rule"] == strat.name and x["delay"] == d)["cagr"]) for d in DELAYS))
            rows.append(cells)
        md.append(md_table(["rule"] + series_names, rows))

        # ---- 2 multi start
        md.append(f"## {un} 2. Multi-start 10-year windows (delay 1, every month-end start)\n")
        for s in series_names:
            md.append(f"**{s}, fixed-spread encoding**\n")
            md.append(prov(und, "fixed", "month-end starts, 10-year horizon, delay 1"))
            sel = [r for r in ms["fixed"] if r["product"] == s and r["delay"] == 1 and r["scope"] == "all"]
            md.append(md_table(["rule", "starts", "rule median CAGR", "passive median CAGR", "median edge pp (p10 to p90)", "mean edge pp", "phase-pooled 95% interval", "noisy", "rule beats passive", "ties (never traded)", "rule median max DD", "passive median max DD"],
                               [[f"`{r['rule']}`", r["n"], pc(r["strat_cagr_median"]), pc(r["passive_cagr_median"]), f"{pp(r['edge_median'])} ({pp(r['edge_p10'], 1)} to {pp(r['edge_p90'], 1)})",
                                 pp(r["edge_mean"]), f"[{pp(r['indep_lo'])}, {pp(r['indep_hi'])}] (t with {r['indep_df']} df)",
                                 "too few windows" if r["too_few_windows"] else ("NOISY" if r["noisy"] else "clear"),
                                 pc(r["wins"], 0), pc(r["ties"], 0), pc(r["strat_maxdd_median"], 0), pc(r["passive_maxdd_median"], 0)] for r in sel]))
        md.append("Windows overlap heavily (a start shares 119 of its 120 months with the next), so the win shares are not independent observations; do not read them as p-values. "
                  "The interval is the passive study's headline convention (non-overlapping windows pooled over start phases, mean +/- t(df) x SE; ASSUMPTIONS section 7); "
                  f"NOISY = it covers zero; 'too few windows' = fewer than {MIN_WINDOWS} non-overlapping windows in the smallest phase, where the interval is not read "
                  "(the coverage simulation starts at 3). The mean sits next to the median because the edges are skewed by the windows that contain a crash. "
                  "A TIE is a window where the rule stayed invested throughout and never traded, so it equals buy-and-hold to rounding; ties are not counted as wins.\n")
        md.append(f"**Full-run edge by era (delay 1, fixed encoding; one run per era, descriptive)**: boundaries {', '.join(ERAS[name])}.\n")
        era_sel = R["eras"][name]["fixed"]
        era_labels = sorted({(r["start"], r["end"]) for r in era_sel})
        md.append(md_table(["rule"] + [f"{s} to {e}" for s, e in era_labels],
                           [[f"`{strat.name}`"] + [" / ".join(pp(r["edge"]) for r in era_sel if r["rule"] == strat.name and (r["start"], r["end"]) == lab and r["product"] == series_names[0])
                                                   or "-" for lab in era_labels] for _, _, strat in variants]))
        md.append(f"(Edges for {series_names[0]}; the other series are in the JSON under `eras`.)\n")
        md.append(f"**Era-difference test (delay 1, fixed encoding, {series_names[0]})**: daily log edge of the rule over passive; mean per era in pp a year "
                  f"with Newey-West SE at Bartlett lags {', '.join(str(L) for L in NW_LAGS)}; z for the last two eras and for all earlier history against the last era. "
                  "A z within +/- 2 at every lag: not distinguishable from chance on one history.\n")
        et = [r for r in R["era_tests"][name]["fixed"] if r["product"] == series_names[0]]
        md.append(md_table(["rule"] + [f"era {k + 1} mean (SE at lag 63)" for k in range(3)] + ["z last two eras (lags 21 / 63 / 252)", "z all earlier vs last"],
                           [[f"`{r['rule']}`"] + [f"{e['mean_pp']:+.2f} ({e['se_pp'].get('63', float('nan')):.2f})" for e in r["eras"]] + ["-"] * (3 - len(r["eras"]))
                            + [" / ".join(f"{r['z_last_two'].get(str(L), float('nan')):+.2f}" for L in NW_LAGS),
                               " / ".join(f"{r['z_pre_post'].get(str(L), float('nan')):+.2f}" for L in NW_LAGS)] for r in et]))

        # ---- 3 in/out of sample
        md.append(f"## {un} 3. In-sample vs out-of-sample (split {SPLIT[name]}; all rules fixed before testing)\n")
        md.append("A. Median 10-year edge pp (rule beats passive %) for windows ENTIRELY inside each era; delay 1. Cell: in-sample / out-of-sample, fixed encoding | rate encoding.\n")
        md.append(prov(und, "fixed", f"10-year windows inside the era (in-sample ends {SPLIT[name]}; out-of-sample starts {SPLIT[name]})"))
        rows = []
        for key, params, strat in variants:
            cells = [f"`{strat.name}`"]
            for s in series_names:
                parts = []
                for enc in ENC_NAMES:
                    a = next(x for x in ms[enc] if x["product"] == s and x["rule"] == strat.name and x["delay"] == 1 and x["scope"] == "in_sample")
                    b = next(x for x in ms[enc] if x["product"] == s and x["rule"] == strat.name and x["delay"] == 1 and x["scope"] == "out_of_sample")
                    parts.append(f"{pp(a['edge_median'])} ({pc(a['wins'], 0)}) / {pp(b['edge_median'])} ({pc(b['wins'], 0)})")
                cells.append(" \\| ".join(parts))
            rows.append(cells)
        md.append(md_table(["rule"] + series_names, rows))
        ex = next(x for x in ms["fixed"] if x["scope"] == "in_sample")
        ex2 = next(x for x in ms["fixed"] if x["scope"] == "out_of_sample")
        md.append(f"(Number of windows, e.g. `{ex['rule']}` on {ex['product']}: {ex['n']} in-sample, {ex2['n']} out-of-sample.)\n")
        md.append("B. Full-run CAGR edge pp over passive, in-sample era (rule start to split) / out-of-sample era (split to end); delay 1. Cell: fixed | rate.\n")
        rows = []
        for key, params, strat in variants:
            cells = [f"`{strat.name}`"]
            for s in series_names:
                parts = []
                for enc in ENC_NAMES:
                    r = next(x for x in sub[enc] if x["product"] == s and x["rule"] == strat.name)
                    parts.append(f"{pp(r['edge_in_sample'])} / {pp(r['edge_out_of_sample'])}")
                cells.append(" \\| ".join(parts))
            rows.append(cells)
        md.append(md_table(["rule"] + series_names, rows))

        # ---- 4 delay
        md.append(f"## {un} 4. Delay sensitivity: 10-year median edge over passive at delay 1 / 2 / 3 (pp)\n")
        md.append("FLAG = the edge changes sign at delay 2 or 3 (SIGN CHANGES) or falls to half its delay-1 size or less (HALVES). Cell: fixed encoding; flag from the fixed encoding, then from the rate encoding.\n")
        md.append(prov(und, "fixed", "month-end starts, 10-year horizon, delays 1-3"))
        rows = []
        for key, params, strat in variants:
            cells = [f"`{strat.name}`"]
            flags_f, flags_r = [], []
            for s in series_names:
                f = next(x for x in dl["fixed"] if x["product"] == s and x["rule"] == strat.name)
                g = next(x for x in dl["rate"] if x["product"] == s and x["rule"] == strat.name)
                cells.append(f"{pp(f['edge_d1'])} / {pp(f['edge_d2'])} / {pp(f['edge_d3'])}")
                if f["flag"]:
                    flags_f.append(f"{s}: {f['flag']}")
                if g["flag"]:
                    flags_r.append(f"{s}: {g['flag']}")
            cells.append("; ".join(flags_f) or "-")
            cells.append("; ".join(flags_r) or "-")
            rows.append(cells)
        md.append(md_table(["rule"] + series_names + ["flags (fixed)", "flags (rate)"], rows))

        # ---- 5 guppy
        md.append(f"## {un} 5. Clean Guppy specifics\n")
        md.append("Counts are on the underlying's slow ribbon (the bars the rule trades on: days, or weeks for `guppy_weekly`). **Direct jumps** = the state goes straight from red to green or green to red with "
                  f"no gray bar between; the Pine alert fires only on gray->green / gray->red, so those would be silent live. Return columns are for {CAL_PRODUCTS[name][0]} (fixed encoding, delay 1).\n")
        md.append(md_table(["rule", "bars", "green / red / gray share", "direct jumps (red->green, green->red)", "buy / sell events", "trades after delay 1", "trades/yr", "whipsaws in/cash", "invested", "CAGR", "passive CAGR", "edge pp"],
                           [[f"`{g['rule']}`", g["bars"], f"{pc(g['green_share'], 0)} / {pc(g['red_share'], 0)} / {pc(g['gray_share'], 0)}", f"{g['jumps_total']} ({g['jumps_red_to_green']}, {g['jumps_green_to_red']})",
                             f"{g['buy_events']} / {g['sell_events']}", g["trades_after_delay1"], f"{g['trades_per_year']:.2f}", f"{g['whipsaws_in']}/{g['whipsaws_cash']}", pc(g["invested_share"], 0),
                             pc(g["cagr_live_product"]), pc(g["passive_cagr"]), pp(g["edge"])] for g in R["guppy"][name]]))

        # ---- 6 common window
        cw = R["common"][name]["fixed"][0]["start"]
        md.append(f"## {un} 6. Same-window comparison (every rule from the same first signal; start {cw}; delay 1)\n")
        md.append("The 200-week rules need about four years of history, so tables 1-5 start them later. Here every rule starts on the same day. Cell: CAGR / max drawdown (edge pp), fixed | rate encoding.\n")
        md.append(prov(und, "fixed", f"{cw} to {und.prov['last']}, common start for every rule"))
        rows = []
        for series in series_names:
            pa = next(x for x in R["common"][name]["fixed"] if x["product"] == series)
            pr = next(x for x in R["common"][name]["rate"] if x["product"] == series)
            rows.append([f"passive {series}", f"{pc(pa['passive_cagr'])} / {pc(pa['passive_max_dd'], 0)} \\| {pc(pr['passive_cagr'])} / {pc(pr['passive_max_dd'], 0)}"])
        md.append(md_table(["benchmark", "CAGR / max DD (fixed \\| rate)"], rows) + f"1x total return: {pc(R['common'][name]['fixed'][0]['index1x_cagr'])} / {pc(R['common'][name]['fixed'][0]['index1x_max_dd'], 0)}.\n")
        rows = []
        for key, params, strat in variants:
            cells = [f"`{strat.name}`"]
            for s in series_names:
                parts = []
                for enc in ENC_NAMES:
                    r = next(x for x in R["common"][name][enc] if x["product"] == s and x["rule"] == strat.name)
                    parts.append(f"{pc(r['cagr'])} / {pc(r['max_dd'], 0)} ({pp(r['edge'])})")
                cells.append(" \\| ".join(parts))
            rows.append(cells)
        md.append(md_table(["rule"] + series_names, rows))

        # ---- 7 trigger sensitivity (the v1 trigger)
        ts = R["trigger_sensitivity"][name]
        md.append(f"## {un} 7. Sensitivity: the v1 trigger (index price, close only) next to the base case\n")
        md.append(f"Base case: {ts['base_trigger']}. Sensitivity (the trigger of the v1 results): {ts['v1_trigger']}. Signals, costs and delay are the same; "
                  "only the early-reset trigger of the funds changes. Cell: 10-year median edge pp (rule beats passive %), delay 1, fixed encoding; base | v1 trigger. "
                  "Last row: passive median 10-year CAGR of each product over the windows of the first rule listed (a rule's windows start after its warm-up), base | v1 trigger.\n")
        rows = []
        for key, params, strat in variants:
            cells = [f"`{strat.name}`"]
            for s in series_names:
                r = next(x for x in ts["rows"] if x["product"] == s and x["rule"] == strat.name)
                cells.append(f"{pp(r['base_edge_median'])} ({pc(r['base_wins'], 0)}) \\| {pp(r['v1_edge_median'])} ({pc(r['v1_wins'], 0)})")
            rows.append(cells)
        first = ts["rows"][0]["rule"]
        rows.append([f"passive median CAGR (windows of `{first}`)"] +[" \\| ".join(pc(next(x for x in ts["rows"] if x["product"] == s and x["rule"] == first)[f"{t}_passive_cagr_median"])
                                                         for t in ("base", "v1")) for s in series_names])
        md.append(md_table(["rule"] + series_names, rows))
        md.append("Early-reset dates of the passive products (full history, fixed encoding): " + "; ".join(
            f"{s}: base {', '.join(v['base']) or 'none'} | v1 {', '.join(v['v1']) or 'none'}" for s, v in ts["early_resets"].items()) + ".\n")

    total = time.perf_counter() - wall0
    R["meta"] = dict(title="Timing rules on 2x calendar-reset funds and daily twins (step 4)", run_date=run_date, rules=[dict(name=s.name, key=k, params=s.params, path_dependent=s.path_dependent, nominal_warmup=s.warmup) for k, _, s in variants],
                     n_variants=len(variants), delays=list(DELAYS), encodings=ENC_NAMES, split=SPLIT, horizon_months=HORIZON_MONTHS, half_spreads=backtest.HALF_SPREADS,
                     cost_convention="half_spread per unit of position changed; round trip = 2 half-spreads; edge_double_cost columns use the literal DESIGN formula (2x)",
                     encoding_definitions={k: dict(spread_per_nav=e.spread_per_nav, rate_turns=e.rate_turns, status=e.status, source=e.source) for k, e in ENC.items()},
                     caption=CAPTION, timing=dict(total_wall_seconds=total, data_load_seconds=load_s), inputs=inputs, banner=banner,
                     code=provenance.code_fingerprint(__file__),
                     trigger_base_case={n: u.prov["trigger_text"] for n, u in unds.items()},
                     provenance={n: dict(first=u.prov["first"], last=u.prov["last"], banner=u.prov["banner"], rate=u.prov["rate"], cash=dict(u.cash.attrs)) for n, u in unds.items()})
    md.append("\n# Timing\n")
    md.append(f"Whole script {total:.1f} s wall (including numba cache load, data load {load_s:.1f} s, charts and files).\n")
    md.append("\n# What this cannot tell you\n")
    md.append("- **The weekly products and the live funds are modeled.** There is no live calendar fund before 2024-08; every rule result is a simulation on a synthetic NAV with ASSUMED residual costs "
              "(FINDINGS F3-F5), carried into history under two encodings that disagree by more than a point a year when rates move (the passive study's `encoding_gap` table). Regime-dependent exposure does not net that out, which is why both are shown.\n"
              "- **Half-spreads are assumed**, not measured from quotes; QQQP and SPYQ trade a few thousand shares a day, so a real round trip may cost more than 0.20%. The `edge @2x cost` column shows the literal-formula alternative.\n"
              "- **Whole-sample caveats of step 3 still apply**: pre-1988 S&P dividends are Shiller's measured monthly series and pre-2006 Nasdaq-100 dividends are assumed (0.3% a year), pre-1954 reference and cash rates are a TB3MS proxy, the 35% trigger is tested on the ETF's daily low in the base case (the v1 close-only index trigger is section 7) and has never fired live.\n"
              "- **One history.** Windows overlap; the Nasdaq-100 sample has few independent 10-year windows. Few rules x few eras means any single edge can be luck; the multiple-testing count is stated at the top.\n"
              "- **Guppy multi-start treats the follower as already running.** A Guppy investor who starts flat on a given day and waits for the first green is a different (and path-dependent) experiment, not run here.\n"
              "- **Taxes, slippage beyond the half-spread, market impact, intraday execution and cash-account frictions are not modeled.** Signals are close-to-close with at least a one-day delay.\n"
              "- **Best/worst-rule charts are chosen after the fact** from 12 variants and are illustrations, not findings.\n"
              "- Research tooling, not investment advice.\n")

    (OUT / "strategies.md").write_text("\n".join(md), encoding="utf-8")
    (OUT / "strategies.json").write_text(json.dumps(clean(R), indent=1), encoding="utf-8")
    print(f"\nwrote {OUT / 'strategies.md'}, strategies.json, strategies_SPX.png, strategies_NDX.png, raw/strategies_*.csv")
    print(f"TIMING: whole script {total:.1f} s; data load {load_s:.1f} s")

    # ---- console summary
    print("\nHEADLINE 10-year median edge pp (wins), delay 1, fixed | rate:")
    for name, und in unds.items():
        for s in und.series:
            for key, params, strat in variants:
                parts = []
                for enc in ENC_NAMES:
                    r = next(x for x in R["multi_start"][name][enc] if x["product"] == s and x["rule"] == strat.name and x["delay"] == 1 and x["scope"] == "all")
                    parts.append(f"{pp(r['edge_median'])} ({pc(r['wins'], 0)})")
                print(f"  {name} {s:14} {strat.name:20} " + " | ".join(parts))


if __name__ == "__main__":
    main()
