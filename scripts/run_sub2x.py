"""B17: sub-2x calendar leverage and the best L. Below 2x, which leverage and which reset (daily / weekly / monthly /
quarterly) does best on the S&P 500 and the Nasdaq-100, and does a 1.2x weekly design make sense on an index?

    py scripts\\run_sub2x.py        (from calendar_letf/, with CALENDAR_LETF_DATA / _RATES set)

What it does, in order
  1. Loads both indexes (total return, the ETF-price trigger with daily lows, fed funds), cut at STUDY_END.
  2. Runs one fund per (L on the 0.05 grid 1.0-3.0, reset, trigger rule, cost case, balance-sheet basis) over the full
     history, and its daily twin at the same L and costs. Every number of a fund is read off that one NAV series.
  3. Per variant: full-history CAGR and drawdown, wipeout, early resets, rolling 10-year objectives, yearly log returns.
  4. The best L per (reset, trigger, cost) as a PLATEAU (calendar_letf/leverage.py), at or under 2x (the headline)
     and on the whole curve to 3x, with the yearly t intervals for 1x and 2x against the best and their coverage.
  5. The break-even fee at each L: the largest fee at which the fund grows as fast as the index (total return, no fee).
  6. Out of sample: L chosen on the early era, scored on the later one; walk-forward re-choice every 10 years; the era
     test before any "the best L changed" claim.
  7. C13 (the gap scales with L(L-1)) and C14 (Kelly) on the real data, C10 (the break-even formula) against the kernel.
Writes results/sub2x.json, results/sub2x.md and results/sub2x_curve.png. Every fund is HYPOTHETICAL: no index fund
below 2x with a calendar reset exists (BACKLOG B17), and the 1.2x weekly design copies the rules of single-stock funds.
"""
import json
import math
import sys
import time
import zlib
from dataclasses import replace
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from calendar_letf import coverage, kernel, leverage, metrics, products, provenance, stats, study  # noqa: E402

OUT = ROOT / "results"
CAPTION = "Data: TradingView (via local export), FRED. Hypothetical funds, not live funds. Not investment advice."
STUDY_END = "2026-09-30"                      # a fixed end (a quarter end), so the results do not move as the data grow
FEE_BASE = 0.0100                             # Tradr's 1.00% (SPYQ / QQQP, VERIFIED prospectus 2026-07-31), every design
FEE_BASE_SOURCE = "Tradr 1.00% (SPYQ / QQQP, prospectus 2026-07-31, VERIFIED), applied to every B17 design"
FEE_WEEKLYPAY = 0.0099                        # Roundhill WeeklyPay unitary fee (497K, VERIFIED; BACKLOG C12)
FEE_WEEKLYPAY_SOURCE = "Roundhill WeeklyPay unitary fee 0.99% (497K DKNW 2025-05-16, TOPW 2026-05-01; BACKLOG C12)"
CAL_RESETS = ("weekly", "monthly", "quarterly")
RESETS = ("daily",) + CAL_RESETS
BASES = ("notional", "borrowed")
BASE_BASIS = "notional"                       # the live calendar funds' structure: swaps on the whole exposure
BORROWED_COSTS = ("b19", "base")              # the borrowed basis runs at the two measured cost anchors only
COST_ORDER = ("spread0", "b19", "base", "double")
HEADLINE_COSTS = ("b19", "base")
HEADLINE_TRIGGER = "scaled"
IN_SAMPLE_LAST = {"SPX": 1989, "NDX": 2005}   # choose L on these years and earlier, score it on the later ones (B17)
WALK_FIRST = {"SPX": 1961, "NDX": 1996}       # first walk-forward decision (10 years of history before it)
WALK_STEP = 10
ERA_LAGS = (0, 1, 2)                          # Bartlett lags in years for the era test
COVERAGE_RUNS = 4000
COVERAGE_FLOOR = 0.92                         # the interval is "valid" when both simulated worlds cover at least this
BREAK_EVEN_HI = 0.20
LIVE_MONTHLY = OUT / "live_monthly.json"
UNDERLYING_NAME = {"SPX": "S&P 500", "NDX": "Nasdaq-100"}
DESIGN_OF = {"SPX": {"weekly": "HYP_SPX_W", "monthly": "HYP_SPX_M", "quarterly": "SPYQ"},
             "NDX": {"weekly": "HYP_NDX_W", "monthly": "MQQQ", "quarterly": "QQQP"}}
COLORS = {"daily": "#0b0b0b", "weekly": "#2a78d6", "monthly": "#eb6834", "quarterly": "#1baf7a"}
MUTED = "#52514e"


# ---------------------------------------------------------------- inputs
def b19_anchor():
    """The third cost anchor: the median fitted residual cost per swap turn of the REAL monthly-reset funds (B19 primary
    fits, results/live_monthly.json), carried to a 2x encoding (x 2 turns). Read from the file, never typed."""
    doc = json.loads(LIVE_MONTHLY.read_text(encoding="utf-8"))
    fits = [f for f in doc["fits"] if f["reset"] == "monthly" and f["label"] == "primary"]
    per_turn = [f["spread_per_turn"] for f in fits]
    med = float(np.median(per_turn))
    return dict(per_turn=med, spread_per_nav_2x=2.0 * med, n=len(fits), lo=min(per_turn), hi=max(per_turn),
                fits=[dict(fund=f["fund"], L=f["L"], first_day=f["first_day"], last_day=f["last_day"],
                           spread_per_turn=f["spread_per_turn"], spread_per_nav=f["spread_per_nav"]) for f in fits],
                file="results/live_monthly.json", sha256=provenance.sha256_of(LIVE_MONTHLY))


def cost_cases(b19):
    """The four cost cases, each a 2x encoding that encoding_at carries to L (ASSUMED there)."""
    base = study.ENCODINGS["fixed"]
    return {
        "spread0": study.CostEncoding("spread0", 0.0, 1.0, source="sensitivity: no swap spread (rate and fee only)",
                                      label="no spread"),
        "b19": study.CostEncoding("b19", b19["spread_per_nav_2x"], 1.0,
                                  source=(f"B19: median fitted residual of {b19['n']} real monthly-reset fund fits "
                                          f"({b19['per_turn']:.3%} per turn, range {b19['lo']:.3%} to {b19['hi']:.3%}), x 2 turns"),
                                  label="B19 real-fund residual"),
        "base": replace(base, name="base", label="Tradr 2024-26 fit (fixed 2.6% of NAV at 2x)"),
        "double": replace(base, name="double", spread_per_nav=2.0 * base.spread_per_nav,
                          source="sensitivity: 2 x the base spread", label="2 x base"),
    }


def cut(s, end):
    out = s.loc[:end].copy()
    out.attrs = dict(s.attrs)
    return out


def build_worlds():
    worlds, wprov = {}, {}
    for name in ("SPX", "NDX"):
        w, p = study.build_world(name, intraday_trigger=True, trigger_basis="etf")
        if w.dates[-1] < pd.Timestamp(STUDY_END):
            raise ValueError(f"{name}: the data end {w.dates[-1].date()} is before STUDY_END {STUDY_END}")
        specs = [design(name, r) for r in CAL_RESETS]
        wc = study.World(name, cut(w.u, STUDY_END), cut(w.trigger, STUDY_END), cut(w.rate, STUDY_END), specs, {},
                         trigger_low=None if w.trigger_low is None else cut(w.trigger_low, STUDY_END),
                         trigger_basis=w.trigger_basis, trigger_info=w.trigger_info)
        if wc.dates[-1] != pd.Timestamp(STUDY_END):
            raise ValueError(f"{name}: no close on STUDY_END {STUDY_END}")
        p = dict(p, last=str(wc.dates[-1].date()), rows=int(len(wc.dates)))
        worlds[name], wprov[name] = wc, p
    return worlds, wprov


def design(world, reset, fee=FEE_BASE, fee_source=FEE_BASE_SOURCE):
    """The 2x design of this reset on this index with the B17 fee: the base that products.at_leverage moves to L."""
    base = products.PRODUCTS[DESIGN_OF[world][reset]]
    return replace(base, costs=replace(base.costs, fee=fee, fee_status="ASSUMED", fee_source=fee_source))


def spec_at(world, reset, L, trigger, basis, fee=FEE_BASE, fee_source=FEE_BASE_SOURCE):
    if reset == "daily":
        return products.twin_of(products.at_leverage(design(world, "monthly", fee, fee_source), L, "none", basis))
    return products.at_leverage(design(world, reset, fee, fee_source), L, trigger, basis)


# ---------------------------------------------------------------- runs
class Runner:
    def __init__(self, w):
        self.w = w
        self.s10, self.e10 = w.month_pairs(120)
        self.runs, self.seconds = 0, 0.0

    def nav(self, spec, enc, fee=None):
        kw = study.kernel_kwargs(spec, enc)
        if fee is not None:
            kw["fee"] = fee
        daily = spec.reset == "daily"
        t0 = time.perf_counter()
        out = kernel.run(spec, self.w.u, study.scaled_rate(self.w.rate, enc), trigger=None if daily else self.w.trigger,
                         trigger_low=None if daily else self.w.trigger_low, early_mode=study.BASE_MODE, **kw)
        self.seconds += time.perf_counter() - t0
        self.runs += 1
        return out

    def summary(self, nav):
        ws = metrics.window_stats(nav, self.s10, self.e10)
        c, tw, dd = ws["cagr"], ws["terminal"], ws["max_dd"]
        ok = np.isfinite(c)
        y = leverage.yearly_log_returns(nav)
        med_c, med_dd = (float(np.median(c[ok])), float(np.median(dd[ok]))) if ok.any() else (math.nan, math.nan)
        early = nav.attrs.get("early_resets", [])
        return dict(cagr=metrics.cagr(nav), max_dd=metrics.max_drawdown(nav), terminated=nav.attrs.get("terminated"),
                    early_resets=len(early), early_reset_dates=list(early),
                    n10=int(ok.sum()), cagr10_median=med_c, cagr10_mean=float(np.mean(c[ok])) if ok.any() else math.nan,
                    tw10_p5=float(np.percentile(tw[ok], 5)) if ok.any() else math.nan, maxdd10_median=med_dd,
                    ratio10=(med_c / abs(med_dd)) if ok.any() and med_dd < 0 else math.nan,
                    _yearly=np.array([y[k] for k in sorted(y)]), _years=sorted(y), _cagr10=c, _log_end=math.log(nav.iloc[-1]) if nav.iloc[-1] > 0 else -math.inf)


def seed(key):
    return zlib.crc32(key.encode("utf-8"))


def interval_with_coverage(d, key):
    """The yearly t(k-1) interval of the mean of `d` and its simulated coverage (coverage.yearly_t_coverage)."""
    iv = leverage.mean_interval(d)
    if not np.isfinite(d).all() or len(d) < 3:
        return dict(iv, coverage=None, verdict="no interval (a wiped-out year)")
    cov = coverage.yearly_t_coverage(d, seed(key), runs=COVERAGE_RUNS)
    ok = min(cov["coverage_bootstrap"], cov["coverage_ar1"]) >= COVERAGE_FLOOR
    return dict(iv, coverage=cov, verdict="valid" if ok else "too narrow")


# ---------------------------------------------------------------- the study per world
def run_world(name, w, costs):
    R = Runner(w)
    t0 = time.perf_counter()
    years = None
    V = {}                                                     # (basis, cost, reset, trigger, L) -> summary
    for basis in BASES:
        for cname in (COST_ORDER if basis == BASE_BASIS else BORROWED_COSTS):
            for L in leverage.GRID:
                enc = study.encoding_at(costs[cname], L, basis)
                V[(basis, cname, "daily", "-", L)] = R.summary(R.nav(spec_at(name, "daily", L, None, basis), enc))
                for reset in CAL_RESETS:
                    for trig in products.TRIGGER_RULES:
                        V[(basis, cname, reset, trig, L)] = R.summary(R.nav(spec_at(name, reset, L, trig, basis), enc))
        print(f"  {name} {basis}: {R.runs} runs, {time.perf_counter() - t0:.0f} s")
    years = next(iter(V.values()))["_years"]
    idx_nav = w.u / w.u.iloc[0]
    idx = R.summary(idx_nav)
    idx_y = idx["_yearly"]

    # ---- the curve: one row per variant
    curve = []
    for (basis, cname, reset, trig, L), s in V.items():
        row = dict(basis=basis, cost=cname, reset=reset, trigger=trig, L=L,
                   **{k: v for k, v in s.items() if not k.startswith("_")})
        row.pop("early_reset_dates")
        row["growth"] = float(np.mean(s["_yearly"])) if np.isfinite(s["_yearly"]).all() else None
        if reset != "daily":
            d = V[(basis, cname, "daily", "-", L)]
            row["gap10_median"] = float(np.nanmedian(s["_cagr10"] - d["_cagr10"]))
            row["gap_full_log"] = s["_log_end"] - d["_log_end"]
        curve.append(row)

    # ---- the best L as a plateau
    optimum = []
    for basis in BASES:
        for cname in (COST_ORDER if basis == BASE_BASIS else BORROWED_COSTS):
            for reset in RESETS:
                for trig in (("-",) if reset == "daily" else products.TRIGGER_RULES):
                    yearly = {L: V[(basis, cname, reset, trig, L)]["_yearly"] for L in leverage.GRID}
                    rec = dict(basis=basis, cost=cname, reset=reset, trigger=trig)
                    for scope, max_L in (("under2", leverage.HEADLINE_MAX_L), ("to3", None)):
                        p = leverage.plateau(yearly, max_L=max_L)
                        best = p["L_best"]
                        cmp_ = {}
                        for ref in (1.0, 2.0):
                            if ref == best or ref not in yearly or (max_L is not None and ref > max_L):
                                continue
                            d = yearly[best] - yearly[ref]
                            cmp_[f"best_minus_{ref:g}x"] = interval_with_coverage(d, f"{name} {basis} {cname} {reset} {trig} {scope} best-{ref}")
                        cmp_["best_minus_index"] = interval_with_coverage(yearly[best] - idx_y, f"{name} {basis} {cname} {reset} {trig} {scope} best-index")
                        sel = [L for L in leverage.GRID if max_L is None or L <= max_L + 1e-12]
                        p5 = {L: V[(basis, cname, reset, trig, L)]["tw10_p5"] for L in sel}
                        ra = {L: V[(basis, cname, reset, trig, L)]["ratio10"] for L in sel}
                        rec[scope] = dict(L_best=best, plateau_lo=p["lo"], plateau_hi=p["hi"], plateau=p["plateau"],
                                          contiguous=p["contiguous"], wiped=p["wiped"], rising_at_top=p["rising_at_top"],
                                          growth_best=p["growth"][best], growth_at_2=p["growth"].get(2.0),
                                          L_best_p5=max((L for L in sel if np.isfinite(p5[L])), key=lambda L: (p5[L], -L)),
                                          L_best_ratio=max((L for L in sel if np.isfinite(ra[L])), key=lambda L: (ra[L], -L)),
                                          **cmp_)
                    optimum.append(rec)

    # ---- named points
    named = []
    for L in leverage.NAMED + (2.0,):
        for cname in HEADLINE_COSTS:
            for reset in RESETS:
                for trig in (("-",) if reset == "daily" else products.TRIGGER_RULES):
                    s = V[(BASE_BASIS, cname, reset, trig, L)]
                    b = V[("borrowed", cname, reset, trig, L)]
                    row = dict(L=L, cost=cname, reset=reset, trigger=trig, **{k: v for k, v in s.items() if not k.startswith("_")},
                               cagr_borrowed=b["cagr"], growth=float(np.mean(s["_yearly"])) if np.isfinite(s["_yearly"]).all() else None,
                               growth_borrowed=float(np.mean(b["_yearly"])) if np.isfinite(b["_yearly"]).all() else None)
                    if reset != "daily":
                        d = V[(BASE_BASIS, cname, "daily", "-", L)]
                        row["gap10_median"] = float(np.nanmedian(s["_cagr10"] - d["_cagr10"]))
                        row["gap_yearly"] = interval_with_coverage(s["_yearly"] - d["_yearly"], f"{name} named {L} {cname} {reset} {trig} gap")
                    row["minus_index_yearly"] = interval_with_coverage(s["_yearly"] - idx_y, f"{name} named {L} {cname} {reset} {trig} index")
                    named.append(row)
    # the WeeklyPay design: 1.2x, weekly, no intra-week reset, the 0.99% unitary fee
    weeklypay = []
    for cname in HEADLINE_COSTS:
        spec = spec_at(name, "weekly", 1.2, "none", BASE_BASIS, FEE_WEEKLYPAY, FEE_WEEKLYPAY_SOURCE)
        s = R.summary(R.nav(spec, study.encoding_at(costs[cname], 1.2, BASE_BASIS)))
        d = V[(BASE_BASIS, cname, "daily", "-", 1.2)]
        weeklypay.append(dict(L=1.2, reset="weekly", trigger="none", cost=cname, fee=FEE_WEEKLYPAY,
                              **{k: v for k, v in s.items() if not k.startswith("_")},
                              growth=float(np.mean(s["_yearly"])),
                              gap_yearly_vs_daily_at_1pct=interval_with_coverage(s["_yearly"] - d["_yearly"], f"{name} weeklypay {cname} gap"),
                              minus_index_yearly=interval_with_coverage(s["_yearly"] - idx_y, f"{name} weeklypay {cname} index")))

    # ---- break-even fee at every L (scaled trigger; both bases; the two measured cost anchors)
    target = math.log(idx_nav.iloc[-1])
    break_even = []
    for basis in BASES:
        for cname in BORROWED_COSTS:
            for reset in RESETS:
                trig = "-" if reset == "daily" else HEADLINE_TRIGGER
                for L in leverage.GRID:
                    spec = spec_at(name, reset, L, trig if reset != "daily" else None, basis)
                    enc = study.encoding_at(costs[cname], L, basis)

                    def growth_at(f, spec=spec, enc=enc):
                        v = R.nav(spec, enc, fee=f).iloc[-1]
                        return math.log(v) if v > 0 else -math.inf
                    be = leverage.break_even_fee(growth_at, target, hi=BREAK_EVEN_HI)
                    rec = dict(basis=basis, cost=cname, reset=reset, trigger=trig, L=L, **be)
                    if reset == "daily":
                        r = w.u.pct_change().fillna(0.0).to_numpy()
                        rate = study.scaled_rate(w.rate, enc).to_numpy()
                        k = ((L - 1.0) * rate + enc.spread_per_nav) * w.accrual_fin
                        rec["second_order"] = leverage.break_even_fee_second_order(r[1:], k[1:], w.accrual_fee[1:], L)
                    break_even.append(rec)
        print(f"  {name} break-even {basis}: {R.runs} runs, {time.perf_counter() - t0:.0f} s")
    # The break-even fee's uncertainty: growth falls about one for one with the fee, so the yearly interval of (fund at
    # the base fee minus the index) moved by the base fee brackets the break-even fee (an approximation, labeled).
    for row in named:
        if row["cost"] in BORROWED_COSTS and row["trigger"] in ("-", HEADLINE_TRIGGER):
            be = find(break_even, basis=BASE_BASIS, cost=row["cost"], reset=row["reset"], L=row["L"])
            iv = row["minus_index_yearly"]
            row["break_even_fee"] = be["fee"]
            row["break_even_approx"] = FEE_BASE + iv["mean"]
            row["break_even_interval"] = dict(lo=FEE_BASE + iv["lo"], hi=FEE_BASE + iv["hi"], verdict=iv["verdict"],
                                              rule="base fee + the yearly interval of (fund minus index); approximate")

    # ---- out of sample and walk-forward (the headline range, at or under 2x)
    ys = np.array(years)
    under2 = [L for L in leverage.GRID if L <= leverage.HEADLINE_MAX_L + 1e-12]
    oos, walk = [], []
    split = IN_SAMPLE_LAST[name] + 1
    for cname in COST_ORDER:
        for reset in RESETS:
            for trig in (("-",) if reset == "daily" else products.TRIGGER_RULES):
                yearly = {L: V[(BASE_BASIS, cname, reset, trig, L)]["_yearly"] for L in leverage.GRID}
                ins, out_ = ys < split, ys >= split
                L_in = leverage.best_L(yearly, ys, ins, under2)
                L_out = leverage.best_L(yearly, ys, out_, under2)
                g = {L: float(np.mean(yearly[L][out_])) for L in (L_in, L_out, 1.0, 2.0)}
                regret = yearly[L_out][out_] - yearly[L_in][out_]
                rec = dict(cost=cname, reset=reset, trigger=trig, in_sample=f"{ys[ins][0]}-{ys[ins][-1]}",
                           out_of_sample=f"{ys[out_][0]}-{ys[out_][-1]}", L_in=L_in, L_out=L_out,
                           growth_oos_at_L_in=g[L_in], growth_oos_at_L_out=g[L_out], growth_oos_at_1=g[1.0],
                           growth_oos_at_2=g[2.0], growth_oos_index=float(np.mean(idx_y[out_])),
                           regret=interval_with_coverage(regret, f"{name} oos {cname} {reset} {trig} regret")
                           if L_in != L_out else None,
                           era_z=leverage.era_split_z(yearly, ys, split, L_in, L_out, ERA_LAGS) if L_in != L_out else None)
                if rec["era_z"]:
                    rec["era_differs"] = all(abs(z) > 1.96 for z in rec["era_z"].values() if np.isfinite(z))
                oos.append(rec)
                wf = leverage.walk_forward(yearly, ys, WALK_FIRST[name], WALK_STEP, Ls=under2)
                held = (ys >= wf["chain"]["first_year"])
                f2 = float(np.mean(yearly[2.0][held]))
                walk.append(dict(cost=cname, reset=reset, trigger=trig, rows=wf["rows"], chain=wf["chain"],
                                 fixed_2=f2, fixed_1=float(np.mean(yearly[1.0][held])), index=float(np.mean(idx_y[held])),
                                 minus_fixed_2=wf["chain"]["growth"] - f2))

    # ---- C13 on the real data: the zero-cost gap at L against L(L-1)/2 x the 2x gap
    c13 = []
    for reset in CAL_RESETS:
        z = {}
        for L in leverage.GRID:
            enc = study.encoding_at(study.ZERO_COSTS, L)
            cal = R.nav(spec_at(name, reset, L, "none", BASE_BASIS), enc).iloc[-1]
            dly = R.nav(spec_at(name, "daily", L, None, BASE_BASIS), enc).iloc[-1]
            z[L] = math.log(cal) - math.log(dly) if cal > 0 and dly > 0 else None
        g2 = z[2.0]
        rows = [dict(L=L, gap_log=z[L], ratio=(z[L] / g2) if z[L] is not None and g2 else None, predicted=L * (L - 1.0) / 2.0)
                for L in leverage.GRID if L > 1.0]
        under = [r for r in rows if r["L"] <= 2.0 + 1e-12 and r["ratio"] is not None]
        c13.append(dict(reset=reset, gap_2x_log=g2, rows=rows,
                        max_abs_rel_error_under2=max(abs(r["ratio"] / r["predicted"] - 1.0) for r in under)))

    # ---- C14 on the real data: Kelly's closed form against the daily curve's grid optimum
    r = w.u.pct_change().fillna(0.0).to_numpy()[1:]
    c14 = []
    for cname in COST_ORDER:
        enc2 = costs[cname]
        rate = study.scaled_rate(w.rate, enc2).to_numpy()[1:]
        kel = leverage.kelly_daily(r, rate, w.accrual_fin[1:], enc2.spread_per_nav / 2.0)
        grid_full = {L: V[(BASE_BASIS, cname, "daily", "-", L)]["_log_end"] for L in leverage.GRID}
        Lg = max(leverage.GRID, key=lambda L: (grid_full[L], -L))
        c14.append(dict(cost=cname, kelly_closed_form=kel, grid_best_full_history=Lg,
                        kelly_beyond_grid=bool(kel > leverage.GRID[-1]),
                        mean_daily=float(r.mean()), sd_daily=float(r.std(ddof=1))))

    # ---- C10 on the real data: the second-order break-even fee of the daily fund against the kernel's
    c10_rows = [b for b in break_even if b["reset"] == "daily" and b["fee"] is not None and b["L"] > 1.0
                and b["L"] <= leverage.HEADLINE_MAX_L + 1e-12]
    c10 = dict(n=len(c10_rows), max_abs_diff_under2=max(abs(b["fee"] - b["second_order"]) for b in c10_rows),
               rule="daily funds, 1 < L <= 2, both bases and both cost anchors, where a break-even fee exists")

    wipes = sorted({(c["reset"], c["trigger"], c["L"], c["terminated"]) for c in curve
                    if c["terminated"] and c["basis"] == BASE_BASIS and c["cost"] == "base"})
    out = dict(years=dict(first=years[0], last=years[-1], n=len(years)),
               index=dict(cagr=idx["cagr"], max_dd=idx["max_dd"], growth=float(np.mean(idx_y)), cagr10_median=idx["cagr10_median"],
                          tw10_p5=idx["tw10_p5"], maxdd10_median=idx["maxdd10_median"], ratio10=idx["ratio10"], n10=idx["n10"]),
               curve=curve, optimum=optimum, named=named, weeklypay=weeklypay, break_even=break_even,
               out_of_sample=oos, walk_forward=walk, c10=c10, c13=c13, c14=c14,
               wipeouts_base=[dict(reset=a, trigger=b, L=c, date=d) for a, b, c, d in wipes],
               wipe_first_L={f"{a}/{b}": min(c for a2, b2, c, _ in wipes if (a2, b2) == (a, b)) for a, b, _, _ in wipes},
               runs=R.runs, kernel_seconds=R.seconds, wall_seconds=time.perf_counter() - t0)
    return out


# ---------------------------------------------------------------- report
def pp(x, d=2):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:+.{d}f}"


def pc(x, d=1):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.{d}f}%"


def ci(iv, d=2):
    if not iv or iv.get("lo") is None or not np.isfinite(iv["lo"]):
        return "n/a"
    return f"[{iv['lo'] * 100:+.{d}f}, {iv['hi'] * 100:+.{d}f}] {iv['verdict']}"


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]) + "\n"


def be_text(r):
    if "break_even_interval" not in r:
        return "-"
    iv = r["break_even_interval"]
    fee = "loses" if r["break_even_fee"] is None else pc(r["break_even_fee"], 2)
    return f"{fee} [{pc(iv['lo'], 2)}, {pc(iv['hi'], 2)}] {iv['verdict']}"


def find(rows, **kw):
    return next(r for r in rows if all(r.get(k) == v for k, v in kw.items()))


def markdown(res):
    m = res["meta"]
    md = [f"# {m['title']}\n", f"*{m['caption']}*\n", "```", *m["banner"], "```\n",
          "All funds here are HYPOTHETICAL: no index fund below 2x with a calendar reset exists. The results answer what "
          "the design would have done, at the stated costs, on the history of each index.\n",
          "## Cost cases (spread per NAV at 2x; carried to L on the stated basis)\n",
          md_table(["case", "spread at 2x", "source"], [[k, pc(v["spread_per_nav_2x"], 2), v["source"]] for k, v in m["cost_cases"].items()]),
          f"Fee {pc(FEE_BASE, 2)} on every design ({FEE_BASE_SOURCE}); the 1.2x weekly design is also run at "
          f"{pc(FEE_WEEKLYPAY, 2)}. Financing: (L - 1) x fed funds on the borrowed part. Basis: '{BASE_BASIS}' (spread on L "
          f"turns) is the base; 'borrowed' (spread on L - 1 turns, the index held directly) is shown next to it.\n",
          m["multiple_testing"] + "\n"]
    for name, W in res["worlds"].items():
        md.append(f"## {UNDERLYING_NAME[name]} ({W['years']['first']}-{W['years']['last']} full years; data to {STUDY_END})\n")
        ix = W["index"]
        md.append(f"Index (total return, no fee): CAGR {pc(ix['cagr'], 2)}, max drawdown {pc(ix['max_dd'])}, 10-year median "
                  f"CAGR {pc(ix['cagr10_median'], 2)}, 10-year 5th-percentile wealth {ix['tw10_p5']:.2f}.\n")
        md.append("### The best L (growth = mean yearly log return; plateau = within one SE of the best)\n")
        rows = []
        for o in W["optimum"]:
            if o["basis"] != BASE_BASIS or o["cost"] not in HEADLINE_COSTS or o["trigger"] not in ("-", HEADLINE_TRIGGER, "none"):
                continue
            for scope in ("under2", "to3"):
                s = o[scope]
                rows.append([o["cost"], o["reset"], o["trigger"], "<= 2" if scope == "under2" else "<= 3",
                             f"{s['L_best']:.2f}", f"{s['plateau_lo']:.2f}-{s['plateau_hi']:.2f}" + ("" if s["contiguous"] else " (gaps)"),
                             "yes" if s["rising_at_top"] else "no", pp(s["growth_best"]),
                             ci(s.get("best_minus_2x")), ci(s.get("best_minus_1x")), ci(s.get("best_minus_index")),
                             f"{s['L_best_p5']:.2f}", f"{s['L_best_ratio']:.2f}"])
        md.append(md_table(["cost", "reset", "trigger", "range", "best L", "plateau", "rising at top", "growth %/yr",
                            "best - 2x (95%)", "best - 1x (95%)", "best - index (95%)", "best L (p5 10y)", "best L (CAGR/DD)"], rows))
        md.append("### Named points (notional basis)\n")
        rows = []
        for r in W["named"]:
            if r["trigger"] not in ("-", HEADLINE_TRIGGER, "none"):
                continue
            rows.append([f"{r['L']:g}", r["cost"], r["reset"], r["trigger"], pc(r["cagr"], 2), pc(r["max_dd"]),
                         pc(r["cagr10_median"], 2), f"{r['tw10_p5']:.2f}", ci(r.get("gap_yearly")), ci(r["minus_index_yearly"]),
                         pc(r["cagr_borrowed"], 2), r["early_resets"], r["terminated"] or "-", be_text(r)])
        md.append(md_table(["L", "cost", "reset", "trigger", "CAGR", "max DD", "10y median CAGR", "10y p5 wealth",
                            "gap vs daily (yearly, 95%)", "minus index (yearly, 95%)", "CAGR borrowed basis", "early resets", "wiped out",
                            "break-even fee (approx. 95%)"], rows))
        md.append("### The 1.2x weekly design with no intra-week reset (fee 0.99%)\n")
        md.append(md_table(["cost", "CAGR", "max DD", "gap vs 1.2x daily (yearly, 95%)", "minus index (yearly, 95%)", "wiped out"],
                           [[r["cost"], pc(r["cagr"], 2), pc(r["max_dd"]), ci(r["gap_yearly_vs_daily_at_1pct"]),
                             ci(r["minus_index_yearly"]), r["terminated"] or "-"] for r in W["weeklypay"]]))
        md.append("### Break-even fee: the largest fee at which the fund grows as fast as the index (full history)\n")
        rows = []
        for basis in BASES:
            for cname in BORROWED_COSTS:
                for reset in RESETS:
                    be = {r["L"]: r for r in W["break_even"] if r["basis"] == basis and r["cost"] == cname and r["reset"] == reset}
                    best = max((L for L in be if be[L]["fee"] is not None), key=lambda L: be[L]["fee"], default=None)
                    rows.append([basis, cname, reset] + [pc(be[L]["fee"], 2) if be[L]["fee"] is not None else "loses" for L in (1.2, 1.5, 1.7, 2.0, 3.0)]
                                + [f"{best:.2f} ({pc(be[best]['fee'], 2)})" if best is not None else "-"])
        md.append(md_table(["basis", "cost", "reset", "1.2x", "1.5x", "1.7x", "2x", "3x", "L with the highest"], rows))
        md.append("### Out of sample (L chosen on the early era, at or under 2x)\n")
        rows = []
        for o in W["out_of_sample"]:
            if o["cost"] not in HEADLINE_COSTS or o["trigger"] not in ("-", HEADLINE_TRIGGER):
                continue
            z = o["era_z"]
            rows.append([o["cost"], o["reset"], o["in_sample"], f"{o['L_in']:.2f}", o["out_of_sample"], f"{o['L_out']:.2f}",
                         pp(o["growth_oos_at_L_in"]), pp(o["growth_oos_at_L_out"]), pp(o["growth_oos_at_2"]), pp(o["growth_oos_index"]),
                         ci(o["regret"]) if o["regret"] else "same L",
                         " / ".join(f"{v:+.2f}" for v in z.values()) if z else "-"])
        md.append(md_table(["cost", "reset", "chosen on", "L", "scored on", "best L there", "growth at chosen", "growth at best",
                            "growth at 2x", "index", "regret (95%)", f"era z (lags {', '.join(map(str, ERA_LAGS))})"], rows))
        md.append("### Walk-forward (L chosen again every 10 years on all earlier years, at or under 2x)\n")
        rows = []
        for o in W["walk_forward"]:
            if o["cost"] not in HEADLINE_COSTS or o["trigger"] not in ("-", HEADLINE_TRIGGER):
                continue
            rows.append([o["cost"], o["reset"], " ".join(f"{r['decision']}:{r['L']:.2f}" for r in o["rows"]),
                         f"{o['chain']['first_year']}-{W['years']['last']}", pp(o["chain"]["growth"]), pp(o["fixed_2"]), pp(o["fixed_1"]), pp(o["index"])])
        md.append(md_table(["cost", "reset", "choices", "years", "walk-forward growth", "fixed 2x", "fixed 1x fund", "index"], rows))
        md.append("### C13: the zero-cost reset gap at L against L(L-1)/2 x the 2x gap\n")
        md.append(md_table(["reset", "2x gap (log, full history)", "1.2x ratio (pred 0.12)", "1.5x ratio (pred 0.375)", "1.7x ratio (pred 0.595)",
                            "3x ratio (pred 3)", "largest error at or under 2x"],
                           [[c["reset"], f"{c['gap_2x_log']:+.4f}"] + [f"{find(c['rows'], L=L)['ratio']:.3f}" if find(c['rows'], L=L)['ratio'] is not None else "n/a"
                                                                       for L in (1.2, 1.5, 1.7, 3.0)] + [f"{c['max_abs_rel_error_under2']:.1%}"] for c in W["c13"]]))
        md.append(f"### C10: the second-order break-even fee of a daily fund against the kernel's\n\nLargest difference "
                  f"{W['c10']['max_abs_diff_under2'] * 100:.3f} points over {W['c10']['n']} cases ({W['c10']['rule']}).\n")
        md.append("### C14: Kelly's closed form against the daily curve's best L (full history)\n")
        md.append(md_table(["cost", "closed form L*", "grid best L (1-3)"],
                           [[c["cost"], f"{c['kelly_closed_form']:.2f}", f"{c['grid_best_full_history']:.2f}"] for c in W["c14"]]))
        md.append("### Wipeouts (notional basis, base cost)\n")
        md.append(", ".join(f"{x['reset']} {x['trigger']} {x['L']:.2f}x on {x['date']}" for x in W["wipeouts_base"]) or "none")
        md.append("\n")
    md.append(f"![curve](sub2x_curve.png)\n")
    return "\n".join(md)


def plot(res, path):
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), dpi=130, sharex=True)
    for i, name in enumerate(("SPX", "NDX")):
        W = res["worlds"][name]
        for j, cname in enumerate(HEADLINE_COSTS):
            ax = axes[i][j]
            for reset in RESETS:
                trig = "-" if reset == "daily" else HEADLINE_TRIGGER
                pts = sorted((c["L"], c["growth"]) for c in W["curve"] if c["basis"] == BASE_BASIS and c["cost"] == cname
                             and c["reset"] == reset and c["trigger"] == trig and c["growth"] is not None)
                ax.plot([p[0] for p in pts], [100 * p[1] for p in pts], color=COLORS[reset], lw=1.4,
                        ls="--" if reset == "daily" else "-", label=reset)
                o = find(W["optimum"], basis=BASE_BASIS, cost=cname, reset=reset, trigger=trig)["under2"]
                ax.plot([o["L_best"]], [100 * o["growth_best"]], "o", color=COLORS[reset], ms=4)
            ax.axhline(100 * W["index"]["growth"], color=MUTED, lw=0.8, ls=":", label="index (no fee)")
            for L in leverage.NAMED:
                ax.axvline(L, color="#d9d8d3", lw=0.6)
            ax.axvline(2.0, color=MUTED, lw=0.6)
            ax.set_title(f"{UNDERLYING_NAME[name]}, cost: {res['meta']['cost_cases'][cname]['label']}", fontsize=9, loc="left")
            ax.grid(True, color="#ecebe7", lw=0.5)
            ax.spines[["top", "right"]].set_visible(False)
            if i == 1:
                ax.set_xlabel("leverage L", color=MUTED)
            if j == 0:
                ax.set_ylabel("growth, mean yearly log return (%)", color=MUTED)
            if i == 0 and j == 0:
                ax.legend(frameon=False, fontsize=8)
    fig.suptitle(f"Growth against leverage, trigger '{HEADLINE_TRIGGER}' (dots: best at or under 2x) [HYPOTHETICAL]\n"
                 "At 1.0 the fund holds the index (no swap spread); from 1.05 the spread is paid on L turns. "
                 "Steps in the calendar lines are single early-reset events.", fontsize=9, x=0.01, ha="left")
    fig.text(0.01, 0.005, CAPTION, fontsize=7, color=MUTED)
    fig.tight_layout(rect=(0, 0.02, 1, 0.95))
    fig.savefig(path)
    plt.close(fig)


def main():
    wall0 = time.perf_counter()
    OUT.mkdir(exist_ok=True)
    print("=" * 100 + "\nB17: sub-2x calendar leverage and the best L (all funds HYPOTHETICAL)")
    b19 = b19_anchor()
    costs = cost_cases(b19)
    worlds, wprov = build_worlds()
    inputs = study.inputs_for(worlds, wprov)
    banner = (provenance.banner_lines(inputs) + [ln for w in worlds.values() for ln in study.conventions_lines(w)]
              + [f"B17 trigger rules replace the 35% drop above: none (a 1/L in-period fall wipes the fund out), scaled "
                 f"(early reset at a {products.SCALED_FUND_LOSS:.0%} / L index fall), fixed35 (35% at any L).",
                 f"Study end fixed at {STUDY_END}; B19 cost anchor read from {b19['file']} (sha256 {b19['sha256'][:12]})."])
    print("\n".join(banner))
    n_var = len(leverage.GRID) * (len(CAL_RESETS) * len(products.TRIGGER_RULES) + 1) * len(COST_ORDER)
    res = dict(meta=dict(
        title="B17: sub-2x calendar leverage and the best L", run_date=str(pd.Timestamp.today().date()),
        caption=CAPTION, study_end=STUDY_END, grid=list(leverage.GRID), named=list(leverage.NAMED),
        headline_max_L=leverage.HEADLINE_MAX_L, plateau_se=leverage.PLATEAU_SE, base_basis=BASE_BASIS,
        headline_trigger=HEADLINE_TRIGGER, fee_base=FEE_BASE, fee_base_source=FEE_BASE_SOURCE, fee_weeklypay=FEE_WEEKLYPAY,
        fee_weeklypay_source=FEE_WEEKLYPAY_SOURCE, trigger_rules=list(products.TRIGGER_RULES),
        scaled_fund_loss=products.SCALED_FUND_LOSS, in_sample_last=IN_SAMPLE_LAST, walk_first=WALK_FIRST, walk_step=WALK_STEP,
        era_lags=list(ERA_LAGS), coverage_runs=COVERAGE_RUNS, coverage_floor=COVERAGE_FLOOR, break_even_hi=BREAK_EVEN_HI,
        b19_anchor=b19,
        cost_cases={k: dict(spread_per_nav_2x=v.spread_per_nav, rate_turns=v.rate_turns, status=v.status, source=v.source, label=v.label)
                    for k, v in costs.items()},
        n_variants_per_index=n_var,
        multiple_testing=(f"Multiple testing: {n_var:,} variants per index on the notional basis ({len(leverage.GRID)} L x "
                          f"({len(CAL_RESETS)} resets x {len(products.TRIGGER_RULES)} trigger rules + daily) x {len(COST_ORDER)} cost cases), "
                          f"plus the borrowed basis. The 0.05 grid is one curve per design, and the best L is a plateau, "
                          f"not a pick from the list; even so, the largest of many noisy numbers is biased up."),
        underlyings={n: wprov[n] for n in wprov}, inputs=inputs, banner=banner, code=provenance.code_fingerprint(__file__)),
        worlds={})
    for name, w in worlds.items():
        print(f"\n{name}: {w.dates[0].date()} to {w.dates[-1].date()}, {len(w.dates)} rows")
        res["worlds"][name] = run_world(name, w, costs)
    res["meta"]["timing"] = dict(total_wall_seconds=time.perf_counter() - wall0)
    plot(res, OUT / "sub2x_curve.png")
    (OUT / "sub2x.json").write_text(json.dumps(provenance.json_safe(res), indent=1, allow_nan=False) + "\n", encoding="utf-8")
    (OUT / "sub2x.md").write_text(markdown(res), encoding="utf-8")
    print(f"wrote results/sub2x.json, results/sub2x.md, results/sub2x_curve.png in {time.perf_counter() - wall0:.0f} s")


if __name__ == "__main__":
    main()
