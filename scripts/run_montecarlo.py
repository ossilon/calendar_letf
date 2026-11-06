"""B11: the Monte Carlo simulator. Ten-year paths built from the real history in blocks, every fund and its daily twin on
each path, the spread of outcomes, a fan chart, the volatility / trend split (C5), the spread of B17's best L over paths,
the mechanism on parametric paths, and three stress cases.

    py scripts\\run_montecarlo.py        (from calendar_letf/, with CALENDAR_LETF_DATA / _RATES set; about 2 minutes)

What it does, in order (calendar_letf/montecarlo.py holds the machinery)
  1. Loads both indexes as the B17 study does (scripts/run_sub2x.py: total return, the ETF-price trigger with daily
     lows, fed funds, cut at STUDY_END), and takes the last ten years of NYSE sessions as the calendar of every path.
  2. Block bootstrap at blocks of 21, 63, 126 and 252 days: N_PATHS paths per index and block. On each path: the
     2x calendar funds of the passive study and their daily twins, at the fixed cost encoding and at zero cost.
  3. Per fund and horizon (1, 3, 5, 10 years): the reset gap's distribution, with Monte Carlo errors; at 10 years the
     wealth, drawdown, early-reset and wipeout rates.
  4. C5 on the 252-day paths: the gap by tercile of the path's realized volatility and of its index trend. A path's
     own volatility and trend are known only at the end, so these splits describe a MECHANISM, not a timing rule.
  5. B17 on paths: the best L (grid 1.00-3.00) of each path, at the B19 and Tradr cost anchors.
  6. The mechanism: AR(1) paths at lag-1 autocorrelations from -0.10 to +0.10, against Bessembinder's second-order
     prediction.
  7. Stress: a flat decade (every daily move less the history's mean), a rate shock (blocks drawn only from eras of
     high or rising rates while the S&P 500 fell) and a 1929-39 path (PARAMETRIC: Shiller's monthly prices with random
     daily moves between them).
Writes results/montecarlo.json, results/montecarlo.md and results/montecarlo_fan.png. No path is ever published:
only statistics over paths.
"""
import csv
import json
import math
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
sys.path.insert(0, str(ROOT / "scripts"))
import run_sub2x as sub2x  # noqa: E402
from calendar_letf import kernel, leverage, montecarlo as mc, periods, products, provenance, series, stats, study  # noqa: E402

OUT = ROOT / "results"
CAPTION = "Data: TradingView (via local export), FRED, Shiller. Simulated paths of modeled funds, not forecasts. Not investment advice."
SEED = 20261106                               # the root of every random stream (numpy SeedSequence)
N_PATHS = 5000                                # paths per index and block length
BATCH = 1000                                  # paths held in memory at once
N_LSTAR = 5000                                # paths for the best-L distribution (blocks LSTAR_BLOCKS)
LSTAR_BLOCKS = (63, 252)
N_MECH = 2000                                 # parametric paths per autocorrelation
PHIS = (-0.10, -0.05, 0.0, 0.05, 0.10)
N_STRESS = 2000
HORIZONS = (1, 3, 5, 10)                      # years; the month-end checkpoints 12, 36, 60, 120 of the path calendar
C5_BLOCK = 252
FAN_BLOCK = 252
FAN_DESIGN = {"SPX": "HYP_SPX_M", "NDX": "MQQQ"}       # the monthly design of each index
FAN_SAMPLES = 50
RATE_SHOCK_ERAS = (("1973-01-02", "1974-12-31"), ("1980-12-01", "1982-08-12"), ("2022-01-03", "2022-10-12"))
RATE_SHOCK_BLOCK = 63
DEPRESSION = ("1929-08", "1939-08")           # Shiller months of the 1929-39 bridge (121 month ends = the path calendar's)
DEPRESSION_RATES = (0.0, 0.04)                # no short rate before 1934 here: the run brackets it (ASSUMED)
ENCS = {"fixed": study.ENCODINGS["fixed"], "zero": study.ZERO_COSTS}
COLORS = {"cal": "#eb6834", "twin": "#2a78d6", "index": "#52514e", "real": "#0b0b0b"}
MUTED = "#52514e"
UNDERLYING_NAME = {"SPX": "S&P 500", "NDX": "Nasdaq-100"}


def seq(*key):
    """A reproducible random generator for one stream, named by integers."""
    return np.random.default_rng(np.random.SeedSequence([SEED, *key]))


# ---------------------------------------------------------------- products as kernel arrays
def terms(items, cal):
    """items: [(label, spec, enc)] -> the keyword arrays of montecarlo.simulate_batch, and the labels."""
    pe = np.array([periods.period_end_flags(cal, sp.reset) if sp.reset != "daily" else np.zeros(len(cal), bool) for _, sp, _ in items])
    kw = dict(period_end=pe,
              L=np.array([sp.L for _, sp, _ in items], dtype=np.float64),
              spread=np.array([study.kernel_kwargs(sp, e)["spread_per_nav"] for _, sp, e in items], dtype=np.float64),
              fee=np.array([e.fee if e.fee is not None else sp.fee for _, sp, e in items], dtype=np.float64),
              drop=np.array([sp.early_drop or 0.0 for _, sp, _ in items], dtype=np.float64),
              rate_mult=np.array([e.rate_turns for _, sp, e in items], dtype=np.float64),
              daily=np.array([sp.reset == "daily" for _, sp, _ in items]))
    return kw, [lab for lab, _, _ in items]


def main_items(name):
    out = []
    for en, enc in ENCS.items():
        for p in study.PRODUCT_NAMES[name]:
            sp = products.PRODUCTS[p]
            out += [((en, p, "cal"), sp, enc), ((en, p, "twin"), products.twin_of(sp), enc)]
    return out


# ---------------------------------------------------------------- one world's setup
class Setup:
    def __init__(self, name, w):
        self.name, self.w = name, w
        self.h = mc.history(w.u, w.trigger, w.trigger_low, w.rate)
        self.hist_dates = w.dates[1:]
        self.cal = mc.path_calendar(w.dates, sub2x.STUDY_END)
        self.n = len(self.cal) - 1
        self.af = periods.accrual_fraction(self.cal, kernel.FIN_DAY_COUNT)
        self.ae = periods.accrual_fraction(self.cal, kernel.FEE_DAY_COUNT)
        self.ck = mc.month_end_rows(self.cal)
        if len(self.ck) != 12 * mc.PATH_YEARS + 1:
            raise ValueError(f"{name}: {len(self.ck)} month-end checkpoints, expected {12 * mc.PATH_YEARS + 1}")
        self.col = {hy: 12 * hy for hy in HORIZONS}
        self.years = {hy: (self.cal[self.ck[12 * hy]] - self.cal[0]).days / 365.25 for hy in HORIZONS}


def run_batches(S, items, make, total, key):
    """Run `items` on `total` paths made by make(rng, paths) -> (U, T, TL, R), in batches. Returns the joined navc, mdd,
    early, term, the index level at the checkpoints and the index's realized volatility to each horizon."""
    kw, labels = terms(items, S.cal)
    parts = []
    for b in range(-(-total // BATCH)):
        P = min(BATCH, total - b * BATCH)
        U, T, TL, R = make(seq(*key, b), P)
        navc, mdd, early, term = mc.simulate_batch(U, T, TL, R, S.af, S.ae, checkpoints=S.ck, **kw)
        lr = np.diff(np.log(U), axis=1)
        vol = {hy: lr[:, :S.ck[S.col[hy]]].std(axis=1, ddof=1) * math.sqrt(252.0) for hy in HORIZONS}
        parts.append((navc, mdd, early, term, U[:, S.ck], vol))
    cat = lambda i: np.concatenate([p[i] for p in parts])           # noqa: E731
    return dict(labels=labels, navc=cat(0), mdd=cat(1), early=cat(2), term=cat(3), index=cat(4),
                vol={hy: np.concatenate([p[5][hy] for p in parts]) for hy in HORIZONS})


def k_of(res, label):
    return res["labels"].index(label)


def gap_at(S, res, en, p, hy):
    c = S.col[hy]
    a = mc.cagr_between(res["navc"][:, k_of(res, (en, p, "cal"))], 0, c, S.years[hy])
    b = mc.cagr_between(res["navc"][:, k_of(res, (en, p, "twin"))], 0, c, S.years[hy])
    return a - b


def tails(x):
    d = mc.describe(x)
    return {k: d.get(k) for k in ("n", "mean", "mean_se", "median", "median_lo", "median_hi", "p5", "p25", "p75", "p95")}


def summarize(S, res, extra=None):
    """One row per (encoding, product, horizon): the gap's distribution; at 10 years the wealth, drawdown, early resets
    and wipeouts of the fund and its twin, and the index's wealth."""
    rows = []
    idx_tw = res["index"][:, -1]
    for en in ENCS:
        for p in study.PRODUCT_NAMES[S.name]:
            kc, kt = k_of(res, (en, p, "cal")), k_of(res, (en, p, "twin"))
            for hy in HORIZONS:
                row = dict(encoding=en, product=p, reset=products.PRODUCTS[p].reset, horizon_years=hy, gap=mc.describe(gap_at(S, res, en, p, hy)))
                if hy == mc.PATH_YEARS:
                    row.update(cal_terminal=tails(res["navc"][:, kc, -1]), twin_terminal=tails(res["navc"][:, kt, -1]),
                               index_terminal=tails(idx_tw), cal_maxdd=tails(res["mdd"][:, kc]), twin_maxdd=tails(res["mdd"][:, kt]),
                               early_share=float((res["early"][:, kc] > 0).mean()), early_mean=float(res["early"][:, kc].mean()),
                               wiped_cal=float((res["term"][:, kc] >= 0).mean()), wiped_twin=float((res["term"][:, kt] >= 0).mean()),
                               cal_beats_index=float((res["navc"][:, kc, -1] > idx_tw).mean()))
                if extra:
                    row.update(extra)
                rows.append(row)
    return rows


def c5_split(S, res):
    """The gap by tercile of the path's realized volatility and of its index CAGR, per product and horizon (fixed cost)."""
    out = []
    for p in study.PRODUCT_NAMES[S.name]:
        for hy in HORIZONS:
            g = gap_at(S, res, "fixed", p, hy)
            vol = res["vol"][hy]
            trend = mc.cagr_between(res["index"], 0, S.col[hy], S.years[hy])
            vq, tq = np.quantile(vol, [1 / 3, 2 / 3]), np.quantile(trend, [1 / 3, 2 / 3])
            vt, tt = np.digitize(vol, vq), np.digitize(trend, tq)        # 0 low, 1 middle, 2 high
            cells = []
            for a in range(3):
                for b in range(3):
                    m = (vt == a) & (tt == b)
                    d = mc.describe(g[m])
                    cells.append(dict(vol_tercile=a, trend_tercile=b, n=d["n"], median=d.get("median"), median_lo=d.get("median_lo"),
                                      median_hi=d.get("median_hi"), mean=d.get("mean"), mean_se=d.get("mean_se"), share_pos=d.get("share_pos")))
            by_vol = [mc.describe(g[vt == a]) for a in range(3)]
            by_trend = [mc.describe(g[tt == b]) for b in range(3)]
            hi_lo = by_vol[2]["mean"] - by_vol[0]["mean"]
            z = hi_lo / math.sqrt(by_vol[2]["mean_se"] ** 2 + by_vol[0]["mean_se"] ** 2)
            out.append(dict(product=p, reset=products.PRODUCTS[p].reset, horizon_years=hy, vol_cuts=list(vq), trend_cuts=list(tq),
                            cells=cells, by_vol=[{k: d[k] for k in ("n", "mean", "mean_se", "median", "median_lo", "median_hi", "share_pos")} for d in by_vol],
                            by_trend=[{k: d[k] for k in ("n", "mean", "mean_se", "median", "median_lo", "median_hi", "share_pos")} for d in by_trend],
                            high_minus_low_vol_mean=hi_lo, high_minus_low_vol_z=z))
    return out


def fan(S, res):
    """Percentiles over paths of $1 in the monthly design, its twin and the index at every month-end checkpoint."""
    k_c, k_t = k_of(res, ("fixed", FAN_DESIGN[S.name], "cal")), k_of(res, ("fixed", FAN_DESIGN[S.name], "twin"))
    qs = (5, 25, 50, 75, 95)
    pct = lambda a: {f"p{q}": list(np.percentile(a, q, axis=0)) for q in qs}       # noqa: E731
    return dict(product=FAN_DESIGN[S.name], block=FAN_BLOCK, encoding="fixed",
                months=[int(i) for i in range(len(S.ck))], cal=pct(res["navc"][:, k_c, :]), twin=pct(res["navc"][:, k_t, :]),
                index=pct(res["index"]))


def real_decade(S):
    """The real last ten years through the same model (fixed cost): the history line of the fan chart."""
    sl = slice(S.w.dates.get_loc(S.cal[0]), S.w.dates.get_loc(S.cal[-1]) + 1)
    sp = products.PRODUCTS[FAN_DESIGN[S.name]]
    enc = ENCS["fixed"]
    u = S.w.u.iloc[sl]
    nav = kernel.run(sp, u, study.scaled_rate(S.w.rate.iloc[sl], enc), trigger=S.w.trigger.iloc[sl],
                     trigger_low=None if S.w.trigger_low is None else S.w.trigger_low.iloc[sl], **study.kernel_kwargs(sp, enc))
    tw = kernel.run(products.twin_of(sp), u, study.scaled_rate(S.w.rate.iloc[sl], enc), **study.kernel_kwargs(sp, enc))
    return dict(cal=list(nav.values[S.ck]), twin=list(tw.values[S.ck]), index=list((u / u.iloc[0]).values[S.ck]))


# ---------------------------------------------------------------- B17 on paths
def lstar(S, costs, block, hist_opt):
    items = []
    for cname in sub2x.HEADLINE_COSTS:
        for reset in sub2x.RESETS:
            for L in leverage.GRID:
                spec = sub2x.spec_at(S.name, reset, L, None if reset == "daily" else sub2x.HEADLINE_TRIGGER, sub2x.BASE_BASIS)
                items.append(((cname, reset, L), spec, study.encoding_at(costs[cname], L, sub2x.BASE_BASIS)))
    kw, labels = terms(items, S.cal)
    starts = mc.block_starts(len(S.h["lr_u"]), block)
    last = np.array([S.n], dtype=np.int64)
    finals = []
    for b in range(-(-N_LSTAR // BATCH)):
        P = min(BATCH, N_LSTAR - b * BATCH)
        U, T, TL, R = mc.build_paths(S.h, mc.block_pick(seq(3, S.idx, block, b), starts, block, S.n, P))
        navc, *_ = mc.simulate_batch(U, T, TL, R, S.af, S.ae, checkpoints=last, **kw)
        finals.append(navc[:, :, 0])
    F = np.concatenate(finals)
    yrs = (S.cal[-1] - S.cal[0]).days / 365.25
    with np.errstate(divide="ignore"):
        G = np.where(F > 0, np.log(np.maximum(F, 1e-300)) / yrs, -np.inf)
    grid = np.array(leverage.GRID)
    out = []
    for cname in sub2x.HEADLINE_COSTS:
        for reset in sub2x.RESETS:
            cols = [labels.index((cname, reset, L)) for L in leverage.GRID]
            g = G[:, cols]
            for scope, top in (("under2", leverage.HEADLINE_MAX_L), ("to3", leverage.GRID[-1])):
                m = grid <= top + 1e-12
                ls = grid[m][np.argmax(g[:, m], axis=1)]                   # argmax takes the first: ties go to the lower L
                med = np.median(g[:, m], axis=0)
                h = hist_opt.get((cname, reset, scope))
                out.append(dict(block=block, cost=cname, reset=reset, scope=scope, n=int(len(ls)),
                                L_median=float(np.median(ls)), L_p10=float(np.percentile(ls, 10)), L_p25=float(np.percentile(ls, 25)),
                                L_p75=float(np.percentile(ls, 75)), L_p90=float(np.percentile(ls, 90)),
                                share_at_1=float((ls == 1.0).mean()), share_at_top=float((ls == top).mean()),
                                share_ge_2=float((ls >= 2.0 - 1e-12).mean()),
                                L_best_median_growth=float(grid[m][int(np.argmax(med))]),
                                wiped_share_at_top=float(np.isinf(g[:, m][:, -1]).mean()),
                                hist_L_best=h))
    return out


# ---------------------------------------------------------------- the mechanism on AR(1) paths
def mechanism(S):
    lr = S.h["lr_u"]
    m, sd = float(lr.mean()), float(lr.std(ddof=1))
    items = []
    for reset in sub2x.CAL_RESETS:
        base = products.PRODUCTS[sub2x.DESIGN_OF[S.name][reset]]
        sp = products.at_leverage(base, 2.0, "none")
        items += [((reset, "cal"), sp, study.ZERO_COSTS), ((reset, "twin"), products.twin_of(sp), study.ZERO_COSTS)]
    kw, labels = terms(items, S.cal)
    last = np.array([S.n], dtype=np.int64)
    yrs = (S.cal[-1] - S.cal[0]).days / 365.25
    out = []
    for i, phi in enumerate(PHIS):
        x = mc.ar1_log_returns(seq(4, S.idx, i), N_MECH, S.n, m, sd, phi)
        U, T, TL, R = mc.paths_from_log_returns(x, x, 0.0)
        navc, *_ = mc.simulate_batch(U, T, TL, R, S.af, S.ae, checkpoints=last, **kw)
        simple = np.expm1(x)
        mu_s, sd_s = float(simple.mean()), float(simple.std(ddof=1))
        for reset, T_days in (("weekly", 5), ("monthly", 21), ("quarterly", 63)):
            c, t = navc[:, labels.index((reset, "cal")), 0], navc[:, labels.index((reset, "twin")), 0]
            g = np.log(c / t) / yrs
            pred = stats.predicted_reset_gap(mu_s, sd_s, mc.ar1_variance_ratio(phi, T_days), T_days)["gap_per_period"]
            n_periods = float(kw["period_end"][labels.index((reset, "cal"))][1:].sum())
            out.append(dict(phi=phi, reset=reset, log_gap_per_year=mc.describe(g), predicted_per_year=pred * n_periods / yrs,
                            mean_daily_log=m, sd_daily_log=sd, mu_simple=mu_s, sd_simple=sd_s))
    return out


# ---------------------------------------------------------------- stress paths
def depression_paths(S, rate, rng, P):
    rows = []
    with open(series.SHILLER_FILE, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if DEPRESSION[0] <= r["month"] <= DEPRESSION[1]:
                rows.append((r["month"], float(r["price"]), float(r["dividend_yield"])))
    if len(rows) != len(S.ck):
        raise ValueError(f"1929-39: {len(rows)} Shiller months for {len(S.ck)} checkpoints")
    logp = np.log([p for _, p, _ in rows])
    sd = float(np.diff(logp).std(ddof=1) / math.sqrt(S.n / (len(rows) - 1)))
    lv = mc.bridge_log_levels(rng, P, S.ck, logp - logp[0], sd)
    seg = np.searchsorted(S.ck, np.arange(1, S.n + 1), side="left") - 1        # the month each daily move belongs to
    dy = np.array([y for _, _, y in rows])[seg] / 252.0
    lr_t = np.diff(lv, axis=1)
    return mc.paths_from_log_returns(lr_t + dy[None, :], lr_t, rate), dict(daily_sd=sd, months=[rows[0][0], rows[-1][0]])


def run_world(name, w, costs, idx, hist_opt):
    t0 = time.perf_counter()
    S = Setup(name, w)
    S.idx = idx
    out = dict(calendar=dict(first=str(S.cal[0].date()), last=str(S.cal[-1].date()), sessions=int(len(S.cal)),
                             years={str(k): v for k, v in S.years.items()}), history=dict(first=str(S.hist_dates[0].date()),
                             last=str(S.hist_dates[-1].date()), days=int(len(S.hist_dates))))
    items = main_items(name)
    out["bootstrap"], keep = [], None
    for block in mc.BLOCKS:
        starts = mc.block_starts(len(S.h["lr_u"]), block)
        res = run_batches(S, items, lambda rng, P, block=block, starts=starts: mc.build_paths(S.h, mc.block_pick(rng, starts, block, S.n, P)),
                          N_PATHS, (1, idx, block))
        out["bootstrap"] += summarize(S, res, dict(block=block))
        if block == C5_BLOCK:
            keep = res
        print(f"  {name} block {block}: {time.perf_counter() - t0:.0f} s")
    out["c5"] = c5_split(S, keep)
    out["fan"] = fan(S, keep)
    out["real_decade"] = real_decade(S)
    term = keep["navc"][:, k_of(keep, ("fixed", FAN_DESIGN[name], "cal")), -1]
    out["real_decade"]["share_of_paths_below"] = float((term < out["real_decade"]["cal"][-1]).mean())
    out["real_decade"]["index_share_of_paths_below"] = float((keep["index"][:, -1] < out["real_decade"]["index"][-1]).mean())
    rng_s = np.random.default_rng(np.random.SeedSequence([SEED, 99, idx]))
    out["fan_samples_drawn"] = sorted(int(i) for i in rng_s.choice(N_PATHS, FAN_SAMPLES, replace=False))
    out["_fan_paths"] = keep["navc"][out["fan_samples_drawn"], k_of(keep, ("fixed", FAN_DESIGN[name], "cal")), :]
    out["_fan_terminal"] = dict(cal=keep["navc"][:, k_of(keep, ("fixed", FAN_DESIGN[name], "cal")), -1],
                                twin=keep["navc"][:, k_of(keep, ("fixed", FAN_DESIGN[name], "twin")), -1])
    # stress: a flat decade
    shift = float(S.h["lr_u"].mean())
    starts = mc.block_starts(len(S.h["lr_u"]), FAN_BLOCK)
    res = run_batches(S, items, lambda rng, P: mc.build_paths(S.h, mc.block_pick(rng, starts, FAN_BLOCK, S.n, P), shift=shift),
                      N_STRESS, (5, idx))
    out["stress_flat"] = dict(shift_per_day=shift, block=FAN_BLOCK, rows=summarize(S, res))
    if name == "SPX":
        era = np.zeros(len(S.hist_dates), dtype=bool)
        for a, b in RATE_SHOCK_ERAS:
            era |= (S.hist_dates >= pd.Timestamp(a)) & (S.hist_dates <= pd.Timestamp(b))
        starts = mc.block_starts(len(S.h["lr_u"]), RATE_SHOCK_BLOCK, era)
        res = run_batches(S, items, lambda rng, P: mc.build_paths(S.h, mc.block_pick(rng, starts, RATE_SHOCK_BLOCK, S.n, P)),
                          N_STRESS, (6, idx))
        out["stress_rate_shock"] = dict(eras=[list(e) for e in RATE_SHOCK_ERAS], block=RATE_SHOCK_BLOCK, days=int(era.sum()),
                                        mean_rate=float(S.h["rate"][era].mean()), index_mean_log_per_year=float(S.h["lr_u"][era].mean() * 252),
                                        rows=summarize(S, res))
        dep = []
        for j, rate in enumerate(DEPRESSION_RATES):
            info = {}

            def make(rng, P, rate=rate, info=info):
                paths, meta = depression_paths(S, rate, rng, P)
                info.update(meta)
                return paths
            res = run_batches(S, items, make, N_STRESS, (7, idx, j))
            dep.append(dict(rate=rate, **info, rows=summarize(S, res)))
        out["stress_1929"] = dep
    out["lstar"] = [r for block in LSTAR_BLOCKS for r in lstar(S, costs, block, hist_opt)]
    print(f"  {name} best L: {time.perf_counter() - t0:.0f} s")
    out["mechanism"] = mechanism(S)
    out["mechanism_fit"] = {rs: max(abs(r["log_gap_per_year"]["mean"] - r["predicted_per_year"]) for r in out["mechanism"] if r["reset"] == rs)
                            for rs in sub2x.CAL_RESETS}
    out["wall_seconds"] = time.perf_counter() - t0
    print(f"  {name} done: {out['wall_seconds']:.0f} s")
    return out


# ---------------------------------------------------------------- report and chart
def pp(x, d=2):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:+.{d}f}"


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]) + "\n"


def gap_cells(g):
    return [pp(g["median"]), f"[{pp(g['median_lo'])}, {pp(g['median_hi'])}]", f"{pp(g['mean'])} +/- {g['mean_se'] * 100:.2f}",
            f"{pp(g['p5'])} / {pp(g['p95'])}", f"{g['share_pos']:.0%}"]


def markdown(res):
    m = res["meta"]
    md = [f"# {m['title']}\n", f"*{m['caption']}*\n", "```", *m["banner"], "```\n",
          "Every path is ten years of made-up history on the real NYSE calendar of the ten years to the study end. Its days "
          "copy real days in blocks, so the paths keep the real joint moves of the index, its price, its intraday low and "
          "the rate. These distributions show the spread of outcomes under that resampling. They are not confidence "
          "intervals for the true gap. Each median carries a distribution-free 95% interval for the Monte Carlo error; each "
          "mean carries +/- one Monte Carlo SE.\n"]
    for name, W in res["worlds"].items():
        md.append(f"## {UNDERLYING_NAME[name]} (blocks from {W['history']['first']} to {W['history']['last']})\n")
        md.append("### The reset gap (calendar fund minus daily twin, CAGR points a year), fixed cost encoding\n")
        rows = []
        for r in W["bootstrap"]:
            if r["encoding"] == "fixed":
                rows.append([r["block"], r["product"], r["reset"], r["horizon_years"]] + gap_cells(r["gap"]))
        md.append(md_table(["block", "product", "reset", "years", "median", "median 95% (MC)", "mean +/- SE", "p5 / p95", "calendar ahead"], rows))
        md.append("### Ten years: wealth of $1, drawdown, early resets and wipeouts (fixed cost)\n")
        rows = []
        for r in W["bootstrap"]:
            if r["encoding"] == "fixed" and r["horizon_years"] == 10:
                rows.append([r["block"], r["product"], f"{r['cal_terminal']['p5']:.2f} / {r['cal_terminal']['median']:.2f} / {r['cal_terminal']['p95']:.2f}",
                             f"{r['twin_terminal']['p5']:.2f} / {r['twin_terminal']['median']:.2f} / {r['twin_terminal']['p95']:.2f}",
                             f"{r['index_terminal']['p5']:.2f} / {r['index_terminal']['median']:.2f} / {r['index_terminal']['p95']:.2f}",
                             f"{r['cal_maxdd']['median'] * 100:.0f}%", f"{r['early_share']:.1%}", f"{r['wiped_cal']:.2%} / {r['wiped_twin']:.2%}",
                             f"{r['cal_beats_index']:.0%}"])
        md.append(md_table(["block", "product", "fund p5 / median / p95", "twin", "index", "median max DD", "paths with an early reset",
                            "wiped (fund / twin)", "fund beats index"], rows))
        md.append("### Zero costs (the reset effect alone), 10 years\n")
        md.append(md_table(["block", "product", "median", "median 95% (MC)", "mean +/- SE", "p5 / p95", "calendar ahead"],
                           [[r["block"], r["product"]] + gap_cells(r["gap"]) for r in W["bootstrap"] if r["encoding"] == "zero" and r["horizon_years"] == 10]))
        md.append(f"### C5: the gap by the path's own volatility and trend (block {C5_BLOCK}; a mechanism, not a timing rule)\n")
        rows = []
        for c in W["c5"]:
            bv = c["by_vol"]
            bt = c["by_trend"]
            rows.append([c["product"], c["horizon_years"]] + [pp(d["median"]) for d in bv] + [pp(d["median"]) for d in bt]
                        + [f"{pp(c['high_minus_low_vol_mean'])} (z {c['high_minus_low_vol_z']:+.1f})"])
        md.append(md_table(["product", "years", "low vol", "mid vol", "high vol", "low trend", "mid trend", "high trend", "high - low vol mean"], rows))
        md.append("Median gap in each cell of low / mid / high volatility (rows) by low / mid / high trend (columns), 10 years:\n")
        for c in W["c5"]:
            if c["horizon_years"] != 10:
                continue
            md.append(f"{c['product']}:\n")
            md.append(md_table(["vol \\ trend", "low", "mid", "high"],
                               [[["low", "mid", "high"][a]] + [pp(next(x for x in c["cells"] if x["vol_tercile"] == a and x["trend_tercile"] == b)["median"])
                                                               for b in range(3)] for a in range(3)]))
        md.append("### B17 on paths: the best L of each path (growth over ten years)\n")
        rows = []
        for r in W["lstar"]:
            rows.append([r["block"], r["cost"], r["reset"], "<= 2" if r["scope"] == "under2" else "<= 3", f"{r['L_median']:.2f}",
                         f"{r['L_p10']:.2f}-{r['L_p90']:.2f}", f"{r['share_at_1']:.0%}", f"{r['share_at_top']:.0%}",
                         f"{r['L_best_median_growth']:.2f}", "n/a" if r["hist_L_best"] is None else f"{r['hist_L_best']:.2f}"])
        md.append(md_table(["block", "cost", "reset", "range", "median best L", "p10-p90", "paths at 1x", "paths at the top",
                            "L of the median growth curve", "history (B17)"], rows))
        md.append("### The mechanism: AR(1) paths, 2x, zero cost, no trigger (log gap per year)\n")
        md.append(md_table(["phi", "reset", "mean +/- SE", "predicted (second order)"],
                           [[f"{r['phi']:+.2f}", r["reset"], f"{pp(r['log_gap_per_year']['mean'])} +/- {r['log_gap_per_year']['mean_se'] * 100:.2f}",
                             pp(r["predicted_per_year"])] for r in W["mechanism"]]))
        for key, title in (("stress_flat", "Flat decade (every daily move less the history's mean)"),
                           ("stress_rate_shock", "Rate shock (blocks only from high or rising rates while the S&P 500 fell)")):
            if key not in W:
                continue
            st = W[key]
            md.append(f"### Stress: {title}\n")
            if key == "stress_rate_shock":
                md.append(f"Eras {', '.join(f'{a} to {b}' for a, b in st['eras'])}; {st['days']} days; mean rate {st['mean_rate']:.2%}; "
                          f"index mean log return {pp(st['index_mean_log_per_year'])}% a year.\n")
            md.append(md_table(["product", "gap median (10y)", "gap mean +/- SE", "fund median wealth", "twin", "index", "wiped (fund / twin)", "early reset"],
                               [[r["product"], pp(r["gap"]["median"]), f"{pp(r['gap']['mean'])} +/- {r['gap']['mean_se'] * 100:.2f}",
                                 f"{r['cal_terminal']['median']:.2f}", f"{r['twin_terminal']['median']:.2f}", f"{r['index_terminal']['median']:.2f}",
                                 f"{r['wiped_cal']:.1%} / {r['wiped_twin']:.1%}", f"{r['early_share']:.0%}"]
                                for r in st["rows"] if r["encoding"] == "fixed" and r["horizon_years"] == 10]))
        for d in W.get("stress_1929", []):
            md.append(f"### Stress: 1929-39 (PARAMETRIC: Shiller monthly prices {d['months'][0]} to {d['months'][1]}, daily SD "
                      f"{d['daily_sd']:.2%}, rate {d['rate']:.0%} ASSUMED)\n")
            md.append(md_table(["product", "gap median", "fund median wealth", "twin", "index", "wiped (fund / twin)", "early reset", "fund p5 / p95"],
                               [[r["product"], pp(r["gap"]["median"]), f"{r['cal_terminal']['median']:.2f}", f"{r['twin_terminal']['median']:.2f}",
                                 f"{r['index_terminal']['median']:.2f}", f"{r['wiped_cal']:.1%} / {r['wiped_twin']:.1%}", f"{r['early_share']:.0%}",
                                 f"{r['cal_terminal']['p5']:.2f} / {r['cal_terminal']['p95']:.2f}"]
                                for r in d["rows"] if r["encoding"] == "fixed" and r["horizon_years"] == 10]))
    md.append("![fan](montecarlo_fan.png)\n")
    return "\n".join(md)


def plot_fan(res, raw, path):
    fig, axes = plt.subplots(1, 2, figsize=(13, 6), dpi=130)
    for ax, name in zip(axes, ("SPX", "NDX")):
        W, F = res["worlds"][name], res["worlds"][name]["fan"]
        x = np.array(F["months"]) / 12.0
        for row in raw[name]["paths"]:
            ax.plot(x, row, color=COLORS["cal"], lw=0.4, alpha=0.18)
        ax.fill_between(x, F["cal"]["p5"], F["cal"]["p95"], color=COLORS["cal"], alpha=0.12, lw=0, label="fund, 5th-95th percentile")
        ax.fill_between(x, F["cal"]["p25"], F["cal"]["p75"], color=COLORS["cal"], alpha=0.22, lw=0, label="fund, 25th-75th")
        ax.plot(x, F["cal"]["p50"], color=COLORS["cal"], lw=2.0, label=f"fund median ({F['product']}, 2x monthly)")
        ax.plot(x, F["twin"]["p50"], color=COLORS["twin"], lw=1.4, ls="--", label="daily twin median")
        ax.plot(x, F["index"]["p50"], color=COLORS["index"], lw=1.2, ls=":", label="index median (1x, no fee)")
        ax.plot(x, W["real_decade"]["cal"], color=COLORS["real"], lw=1.2, label=f"the real decade, {W['calendar']['first'][:4]}-{W['calendar']['last'][:4]}")
        for yr in (1, 3, 5, 10):
            v = F["cal"]["p50"][12 * yr]
            ax.annotate(f"{v:.2f}", (yr, v), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=7, color=COLORS["cal"])
        ax.set_yscale("log")
        ax.set_xlim(0, 11.6)
        term = np.sort(raw[name]["terminal"])
        lo, hi = np.percentile(term, [0.5, 99.5])
        bins = np.geomspace(max(lo, 1e-3), hi, 40)
        cnt, edges = np.histogram(term, bins=bins)
        mids = np.sqrt(edges[:-1] * edges[1:])
        ax.barh(mids, cnt / cnt.max() * 1.3, height=np.diff(edges), left=10.15, color=COLORS["cal"], alpha=0.35, lw=0)
        for q in (5, 50, 95):
            v = float(np.percentile(term, q))
            ax.annotate(f"p{q} {v:.2f}", (10.1, v), xytext=(11.5, v), fontsize=7, color=MUTED, ha="right", va="center")
        ax.set_title(f"{UNDERLYING_NAME[name]}: $1 over ten simulated years ({res['meta']['n_paths']:,} paths, {FAN_BLOCK}-day blocks; "
                     f"{FAN_SAMPLES} shown)", fontsize=9, loc="left")
        ax.set_xlabel("years", color=MUTED)
        ax.set_ylabel("wealth of $1 (log scale)", color=MUTED)
        ax.grid(True, color="#ecebe7", lw=0.5)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, fontsize=7, loc="upper left")
    fig.suptitle("Simulated decades of a 2x monthly-reset fund against its daily twin and the index [SIMULATED; MODELED funds; "
                 "fixed cost encoding]", fontsize=10, x=0.01, ha="left")
    fig.text(0.01, 0.005, CAPTION, fontsize=7, color=MUTED)
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    fig.savefig(path)
    plt.close(fig)


def hist_optimum():
    """B17's best L on the history (results/sub2x.json), for the side-by-side; with the file's hash."""
    path = OUT / "sub2x.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for name, W in doc["worlds"].items():
        for o in W["optimum"]:
            if o["basis"] == sub2x.BASE_BASIS and o["trigger"] in ("-", sub2x.HEADLINE_TRIGGER):
                for scope in ("under2", "to3"):
                    out.setdefault(name, {})[(o["cost"], o["reset"], scope)] = o[scope]["L_best"]
    return out, dict(file="results/sub2x.json", sha256=provenance.sha256_of(path))


def main():
    wall0 = time.perf_counter()
    print("=" * 100 + "\nB11: Monte Carlo paths (SIMULATED; all funds MODELED)")
    costs = sub2x.cost_cases(sub2x.b19_anchor())
    worlds, wprov = sub2x.build_worlds()
    inputs = study.inputs_for(worlds, wprov)
    hopt, hopt_src = hist_optimum()
    banner = (provenance.banner_lines(inputs) + [ln for w in worlds.values() for ln in study.conventions_lines(w)]
              + [f"History cut at {sub2x.STUDY_END} (scripts/run_sub2x.py STUDY_END); B17 history optimum read from {hopt_src['file']} "
                 f"(sha256 {hopt_src['sha256'][:12]}); seed {SEED}."])
    print("\n".join(banner))
    res = dict(meta=dict(title="B11: Monte Carlo paths of the calendar-reset funds", run_date=str(pd.Timestamp.today().date()),
                         caption=CAPTION, seed=SEED, n_paths=N_PATHS, batch=BATCH, n_lstar=N_LSTAR, lstar_blocks=list(LSTAR_BLOCKS),
                         n_mech=N_MECH, phis=list(PHIS), n_stress=N_STRESS, blocks=list(mc.BLOCKS), horizons_years=list(HORIZONS),
                         path_years=mc.PATH_YEARS, c5_block=C5_BLOCK, fan_block=FAN_BLOCK, fan_design=FAN_DESIGN,
                         rate_shock_eras=[list(e) for e in RATE_SHOCK_ERAS], rate_shock_block=RATE_SHOCK_BLOCK,
                         depression_months=list(DEPRESSION), depression_rates=list(DEPRESSION_RATES),
                         encodings={k: e.describe() for k, e in ENCS.items()}, study_end=sub2x.STUDY_END,
                         b19_anchor_per_turn=costs["b19"].spread_per_nav / 2.0, sub2x_source=hopt_src,
                         underlyings={n: wprov[n] for n in wprov}, inputs=inputs, banner=banner,
                         code=provenance.code_fingerprint(__file__)), worlds={})
    raw = {}
    for i, (name, w) in enumerate(worlds.items()):
        print(f"\n{name}: history {w.dates[0].date()} to {w.dates[-1].date()}")
        W = run_world(name, w, costs, i, hopt[name])
        raw[name] = dict(paths=W.pop("_fan_paths"), terminal=W.pop("_fan_terminal")["cal"])
        res["worlds"][name] = W
    res["meta"]["timing"] = dict(total_wall_seconds=time.perf_counter() - wall0)
    plot_fan(res, raw, OUT / "montecarlo_fan.png")
    (OUT / "montecarlo.json").write_text(json.dumps(provenance.json_safe(res), indent=1, allow_nan=False) + "\n", encoding="utf-8")
    (OUT / "montecarlo.md").write_text(markdown(res), encoding="utf-8")
    print(f"wrote results/montecarlo.json, results/montecarlo.md, results/montecarlo_fan.png in {time.perf_counter() - wall0:.0f} s")


if __name__ == "__main__":
    main()
