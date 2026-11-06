"""B1: 3x calendar resets (weekly, monthly, quarterly) on the S&P 500 and the Nasdaq-100, each against a 3x daily twin
at the same costs. Every 3x calendar fund is HYPOTHETICAL: none has existed, to the author's knowledge.

    py scripts\\run_3x.py        (from calendar_letf/, with CALENDAR_LETF_DATA / _RATES set; about 1 minute)

The key 3x issue is the trigger. A 3x fund is wiped out by an in-period index fall of 1/3, so the live funds' 35%
trigger can never fire first. The study runs six trigger rules: none (a 1/3 fall wipes the fund out), scaled (an early
reset at a 70% / 3 = 23.3% fall, the fund loss that 35% gives at 2x), 20%, 25%, 30%, and 35% (to show it never fires).
Costs: the swap spread per turn and the swap turns of the real 3x daily funds (UPRO on the S&P 500, TQQQ on the
Nasdaq-100; SEC N-PORT, products.MODELS_3X), the reference rate on the 2 borrowed turns, and the 1.00% fee of the
calendar designs; sensitivity: no spread and twice the spread.
What it reports, per index:
  1. per trigger rule and design: full-history CAGR and drawdown, every early reset and wipeout (with its era), the
     yearly gap against the twin with its interval and coverage;
  2. the multi-start gap at 1, 3, 5 and 10 years with the passive study's phase-pooled interval;
  3. the fill: the close and next-close fills can lose more than the trigger level (gap risk): the worst fill;
  4. costs at no spread, the filed spread and twice it;
  5. C13 on the real data (the 3x gap against the 2x gap at zero cost; the second-order ratio is 3), and C9;
  6. $10,000 through the key periods, the real UPRO / TQQQ (price only) next to the models from their first bar;
  7. wipeout and early-reset rates on 5000 simulated decades (calendar_letf/montecarlo.py, 252-day blocks).
Writes results/three_x.json and results/three_x.md.
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import run_montecarlo as rmc  # noqa: E402
import run_sub2x as sub2x  # noqa: E402
from calendar_letf import kernel, leverage, loader, metrics, montecarlo as mc, periods, products, provenance, study  # noqa: E402

OUT = ROOT / "results"
CAPTION = ("Data: TradingView (via local export), FRED. Every 3x calendar fund is HYPOTHETICAL; the real UPRO and TQQQ are "
           "price-only overlays. Not investment advice.")
L3 = 3.0
TRIGGERS = {"none": None, "scaled": products.SCALED_FUND_LOSS / L3, "d20": 0.20, "d25": 0.25, "d30": 0.30, "fixed35": 0.35}
BASE_TRIGGER = "scaled"
FILL_TRIGGERS = ("scaled", "d20", "d25", "d30")
FILL_MODES = ("close", "next_close")
COST_FACTORS = {"zero": 0.0, "nport": 1.0, "double": 2.0}
BASE_COST = "nport"
REAL = {"SPX": "AMEX:UPRO", "NDX": "NASDAQ:TQQQ"}
N_MC = 5000
MC_BLOCK = 252
KEEP = ("product", "reset", "horizon_years", "n_starts", "first_start", "last_start", "cal_cagr_median", "twin_cagr_median",
        "cal_maxdd_median", "twin_maxdd_median", "cal_worst_terminal", "twin_worst_terminal", "gap_median", "gap_p10", "gap_p90",
        "calendar_wins", "indep_mean", "indep_se", "indep_lo", "indep_hi", "indep_df", "noisy", "underlying_1x_cagr_median")


def drop_source(trig):
    if trig == "none":
        return "no intra-period reset: an in-period index fall of 1/3 wipes the fund out"
    if trig == "scaled":
        return f"early reset at a {TRIGGERS[trig]:.2%} index fall: the {products.SCALED_FUND_LOSS:.0%} fund loss that 35% gives at 2x"
    if trig == "fixed35":
        return "the live 2x funds' 35% trigger kept at 3x: a 1/3 fall wipes the fund out first, so it can never fire"
    return f"sensitivity: early reset at a {TRIGGERS[trig]:.0%} index fall"


def design3(name, reset, trig):
    model = products.MODELS_3X[products.MODEL_3X_FOR[name]]
    return products.at_leverage_filed(sub2x.design(name, reset), L3, model, TRIGGERS[trig], drop_source(trig),
                                      f"{sub2x.DESIGN_OF[name][reset]}_3x_{trig}")


def encodings(name):
    m = products.MODELS_3X[products.MODEL_3X_FOR[name]].costs
    out = {}
    for k, f in COST_FACTORS.items():
        out[k] = study.CostEncoding(f"3x_{k}", m.spread * m.turns * f, 1.0, status="ASSUMED", L=L3,
                                    source=f"{f:g} x the filed spread {m.spread:.4%} per turn on {m.turns:.4f} swap turns ({m.label}, SEC N-PORT), "
                                           "carried to a calendar design",
                                    label=f"{f:g} x {m.label} filed spread")
    return out


def world_with(w, specs):
    return study.World(w.name, w.u, w.trigger, w.rate, specs, {s.name: products.twin_of(s) for s in specs},
                       trigger_low=w.trigger_low, trigger_basis=w.trigger_basis, trigger_info=w.trigger_info)


def era(d):
    return leverage.era_of(d, study.KEY_PERIODS)


def design_rows(name, W3, enc, trig):
    out = []
    for p in W3.specs:
        nav, tw = W3.nav(p.name, enc), W3.nav(W3.twin_name(p.name), enc)
        yc, yt = leverage.yearly_log_returns(nav), leverage.yearly_log_returns(tw)
        d = np.array([yc[y] - yt[y] for y in sorted(yc)])
        out.append(dict(trigger=trig, drop=TRIGGERS[trig], product=p.name, reset=p.reset,
                        cagr=metrics.cagr(nav), max_dd=metrics.max_drawdown(nav), terminated=nav.attrs["terminated"],
                        terminated_era=era(nav.attrs["terminated"]) if nav.attrs["terminated"] else None,
                        early_resets=list(nav.attrs["early_resets"]), n_early_resets=len(nav.attrs["early_resets"]),
                        early_eras=sorted({era(x) or "other" for x in nav.attrs["early_resets"]}),
                        twin_cagr=metrics.cagr(tw), twin_max_dd=metrics.max_drawdown(tw), twin_terminated=tw.attrs["terminated"],
                        designed_level_fill_loss=None if TRIGGERS[trig] is None else -L3 * TRIGGERS[trig],
                        gap_yearly=sub2x.interval_with_coverage(d, f"3x {name} {p.name} {trig} yearly gap")))
    return out


def multi(W3, enc, trig, horizons=study.HORIZONS_YEARS):
    rows, _ = study.multi_start(W3, enc, horizons_years=horizons)
    return [dict(trigger=trig, encoding=enc.name, **{k: r[k] for k in KEEP}) for r in rows]


def fills(W3, enc, trig):
    out = []
    for p in W3.specs:
        pe = periods.period_end_flags(W3.dates, p.reset)
        for mode in FILL_MODES:
            nav = W3.nav(p.name, enc, mode)
            fl = leverage.fill_losses(nav, pe, nav.attrs["early_resets"])
            out.append(dict(trigger=trig, product=p.name, reset=p.reset, mode=mode, cagr=metrics.cagr(nav),
                            terminated=nav.attrs["terminated"], n_early_resets=len(fl),
                            worst_fill=min((x for _, x in fl), default=None), worst_fill_date=min(fl, key=lambda t: t[1])[0] if fl else None,
                            designed_level_fill_loss=-L3 * TRIGGERS[trig], fills=[dict(date=a, loss=b) for a, b in fl]))
    return out


def key_periods(w, worlds3, enc, real):
    out = []
    for label, d0, d1 in study.KEY_PERIODS:
        s, e = w.row_before(d0), w.row_on_or_before(d1)
        if s < 0 or e <= s:
            out.append(dict(period=label, covered=False))
            continue
        sd, ed = w.dates[s], w.dates[e]
        row = dict(period=label, covered=True, first_close=str(sd.date()), last_close=str(ed.date()),
                   index=10000.0 * float(w.u.iloc[e] / w.u.iloc[s]), funds={})
        for trig in (BASE_TRIGGER, "none"):
            W3 = worlds3[trig]
            for p in W3.specs:
                nav = W3.nav(p.name, enc)
                row["funds"][p.name] = dict(value=10000.0 * float(nav.iloc[e] / nav.iloc[s]) if nav.iloc[s] > 0 else 0.0,
                                            early_resets=[x for x in nav.attrs["early_resets"] if sd < pd.Timestamp(x) <= ed],
                                            wiped=bool(nav.attrs["terminated"] and sd < pd.Timestamp(nav.attrs["terminated"]) <= ed))
            tw = W3.nav(W3.twin_name(W3.specs[0].name), enc)
            row["twin"] = 10000.0 * float(tw.iloc[e] / tw.iloc[s])
        if real is not None and real.index[0] <= sd:
            row["real"] = 10000.0 * float(real.loc[:ed].iloc[-1] / real.loc[:sd].iloc[-1])
        out.append(row)
    return out


def overlay(name, w, W3, enc, real):
    """From the real fund's first bar to the study end: the real price (price only), the 3x daily twin at the filed
    spread and the 1.00% fee, the model of the real fund at its filed terms, the 3x calendar designs and the index."""
    first = real.index[0]
    s = int(np.searchsorted(w.dates.values, np.datetime64(first)))
    e = len(w.dates) - 1
    yrs = (w.dates[e] - w.dates[s]).days / 365.25
    g = lambda a: (a[e] / a[s]) ** (1.0 / yrs) - 1.0 if a[s] > 0 and a[e] > 0 else -1.0     # noqa: E731
    model = products.MODELS_3X[products.MODEL_3X_FOR[name]]
    m = kernel.run(model, w.u.iloc[s:], w.rate.iloc[s:]).to_numpy()
    rr = real.loc[w.dates[s]:w.dates[e]]
    out = dict(real=REAL[name], first=str(w.dates[s].date()), last=str(w.dates[e].date()), years=yrs,
               real_cagr=float((rr.iloc[-1] / rr.iloc[0]) ** (1.0 / yrs) - 1.0), real_max_dd=metrics.max_drawdown(rr.to_numpy()),
               model_cagr=float((m[-1] / m[0]) ** (1.0 / yrs) - 1.0), model_max_dd=metrics.max_drawdown(m),
               index_cagr=float(g(w.u.to_numpy())), twin_cagr=float(g(W3.nav(W3.twin_name(W3.specs[0].name), enc).to_numpy())),
               designs={p.name: float(g(W3.nav(p.name, enc).to_numpy())) for p in W3.specs},
               note="real fund: price only (distributions left out); model: the real fund's filed terms; twin and designs: 1.00% fee")
    return out


def c13(name, w):
    z2 = [products.at_leverage(sub2x.design(name, r), 2.0, "none") for r in sub2x.CAL_RESETS]
    z3 = [design3(name, r, "none") for r in sub2x.CAL_RESETS]
    W2, W3 = world_with(w, z2), world_with(w, z3)
    e2, e3 = study.ZERO_COSTS, study.encoding_at(study.ZERO_COSTS, L3)
    r2 = {r["reset"]: r for r in study.multi_start(W2, e2, horizons_years=(10,))[0]}
    r3 = {r["reset"]: r for r in study.multi_start(W3, e3, horizons_years=(10,))[0]}
    out = []
    for p2, p3 in zip(z2, z3):
        n2, n3 = W2.nav(p2.name, e2), W3.nav(p3.name, e3)
        t2, t3 = W2.nav(W2.twin_name(p2.name), e2), W3.nav(W3.twin_name(p3.name), e3)
        full2 = math.log(n2.iloc[-1] / t2.iloc[-1])
        full3 = math.log(n3.iloc[-1] / t3.iloc[-1]) if n3.iloc[-1] > 0 else None
        wiped = n3.attrs["terminated"] is not None              # a wiped fund's gap is not a reset effect: no ratio
        out.append(dict(reset=p2.reset, gap10_median_2x=r2[p2.reset]["gap_median"], gap10_median_3x=r3[p3.reset]["gap_median"],
                        ratio_10y_median=None if wiped else r3[p3.reset]["gap_median"] / r2[p2.reset]["gap_median"],
                        full_log_gap_2x=full2, full_log_gap_3x=full3, ratio_full=None if full3 is None else full3 / full2,
                        wiped_3x=n3.attrs["terminated"], predicted=L3 * (L3 - 1.0) / 2.0))
    return out


def montecarlo(name, w, idx, enc):
    S = rmc.Setup(name, w)
    S.idx = idx
    items = [((trig, r, "cal"), design3(name, r, trig), enc) for trig in TRIGGERS for r in sub2x.CAL_RESETS]
    items.append((("twin",), products.twin_of(design3(name, "monthly", "none")), enc))
    starts = mc.block_starts(len(S.h["lr_u"]), MC_BLOCK)
    res = rmc.run_batches(S, items, lambda rng, P: mc.build_paths(S.h, mc.block_pick(rng, starts, MC_BLOCK, S.n, P)), N_MC, (8, idx))
    kt = res["labels"].index(("twin",))
    yrs = S.years[10]
    tw = mc.cagr_between(res["navc"][:, kt, :], 0, S.col[10], yrs)
    out = []
    for trig in TRIGGERS:
        for r in sub2x.CAL_RESETS:
            k = res["labels"].index((trig, r, "cal"))
            g = mc.cagr_between(res["navc"][:, k, :], 0, S.col[10], yrs) - tw
            out.append(dict(trigger=trig, reset=r, paths=N_MC, wiped=float((res["term"][:, k] >= 0).mean()),
                            wiped_twin=float((res["term"][:, kt] >= 0).mean()), early=float((res["early"][:, k] > 0).mean()),
                            gap=rmc.tails(g), wealth=rmc.tails(res["navc"][:, k, -1]), twin_wealth=rmc.tails(res["navc"][:, kt, -1]),
                            index_wealth=rmc.tails(res["index"][:, -1])))
    return out


def run_world(name, w, idx, real):
    t0 = time.perf_counter()
    encs = encodings(name)
    enc = encs[BASE_COST]
    worlds3 = {trig: world_with(w, [design3(name, r, trig) for r in sub2x.CAL_RESETS]) for trig in TRIGGERS}
    out = dict(cost_cases={k: dict(spread_per_nav=e.spread_per_nav, source=e.source) for k, e in encs.items()},
               model=products.MODEL_3X_FOR[name], designs=[], multi_start=[], fills=[], cost_sensitivity=[])
    for trig, W3 in worlds3.items():
        out["designs"] += design_rows(name, W3, enc, trig)
        out["multi_start"] += multi(W3, enc, trig)
        if trig in FILL_TRIGGERS:
            out["fills"] += fills(W3, enc, trig)
    for k, e in encs.items():
        W3 = worlds3[BASE_TRIGGER]
        rows = multi(W3, e, BASE_TRIGGER, horizons=(10,))
        for r, p in zip(rows, W3.specs):
            r.update(cost=k, cagr=metrics.cagr(W3.nav(p.name, e)), twin_cagr=metrics.cagr(W3.nav(W3.twin_name(p.name), e)))
        out["cost_sensitivity"] += rows
    cs = {(r["cost"], r["product"]): r for r in out["cost_sensitivity"]}
    prods = [p.name for p in worlds3[BASE_TRIGGER].specs]
    out["cost_effect"] = dict(
        cagr_drop_min=min(cs[(BASE_COST, p)]["cagr"] - cs[("double", p)]["cagr"] for p in prods),
        cagr_drop_max=max(cs[(BASE_COST, p)]["cagr"] - cs[("double", p)]["cagr"] for p in prods),
        gap_move_max=max(abs(cs[("double", p)]["gap_median"] - cs[(BASE_COST, p)]["gap_median"]) for p in prods),
        rule="twice the filed spread against the filed spread, trigger scaled: CAGR drop and the move of the 10-year median gap")
    out["c13"] = c13(name, w)
    out["key_periods"] = key_periods(w, worlds3, enc, real)
    out["overlay"] = overlay(name, w, worlds3[BASE_TRIGGER], enc, real)
    print(f"  {name} history done: {time.perf_counter() - t0:.0f} s")
    out["montecarlo"] = montecarlo(name, w, idx, enc)
    out["fixed35_never_fires"] = all(d["n_early_resets"] == 0 for d in out["designs"] if d["trigger"] == "fixed35")
    # The 35% rule never fires first, but it watches the day's LOW: a low past 1/3 ends the fund at that moment, while
    # with no trigger the kernel judges a wipeout at the close. The difference in wipe rates on the simulated decades is
    # what an intraday wipeout test would add to the "none" rule.
    mcw = {(r["trigger"], r["reset"]): r["wiped"] for r in out["montecarlo"]}
    out["intraday_wipe_extra"] = {r: mcw[("fixed35", r)] - mcw[("none", r)] for r in sub2x.CAL_RESETS}
    out["history_none_equals_fixed35"] = all(
        abs(a["cagr"] - b["cagr"]) < 1e-12 for a in out["designs"] if a["trigger"] == "none"
        for b in out["designs"] if b["trigger"] == "fixed35" and b["reset"] == a["reset"])
    out["wall_seconds"] = time.perf_counter() - t0
    print(f"  {name} done: {out['wall_seconds']:.0f} s")
    return out


# ---------------------------------------------------------------- report
def pp(x, d=2):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:+.{d}f}"


def pc(x, d=1):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.{d}f}%"


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]) + "\n"


def markdown(res):
    m = res["meta"]
    md = [f"# {m['title']}\n", f"*{m['caption']}*\n", "```", *m["banner"], "```\n",
          "Every 3x calendar fund here is HYPOTHETICAL. Trigger rules: " + "; ".join(f"{k} = {drop_source(k)}" for k in TRIGGERS) + ".\n"]
    for name, W in res["worlds"].items():
        md.append(f"## {sub2x.UNDERLYING_NAME[name]}\n")
        md.append("Cost cases (spread per NAV a year): " + "; ".join(f"{k} {pc(v['spread_per_nav'], 2)}" for k, v in W["cost_cases"].items())
                  + f" (base: {BASE_COST}); the rate on 2 borrowed turns; fee 1.00%.\n")
        md.append("### Full history per trigger rule (base cost, level fill)\n")
        md.append(md_table(["trigger", "design", "CAGR", "max DD", "twin CAGR", "wiped out", "early resets", "eras", "yearly gap vs twin (95%)"],
                           [[d["trigger"], d["product"], pc(d["cagr"], 2), pc(d["max_dd"]), pc(d["twin_cagr"], 2),
                             f"{d['terminated']} ({d['terminated_era'] or 'other'})" if d["terminated"] else "-", d["n_early_resets"],
                             ", ".join(d["early_eras"]) or "-",
                             "n/a" if d["gap_yearly"].get("lo") is None or not np.isfinite(d["gap_yearly"]["lo"]) else
                             f"[{pp(d['gap_yearly']['lo'])}, {pp(d['gap_yearly']['hi'])}] {d['gap_yearly']['verdict']}"] for d in W["designs"]]))
        md.append("### Multi-start gap against the 3x daily twin (base cost; phase-pooled 95% interval)\n")
        md.append(md_table(["trigger", "design", "years", "starts", "median gap", "p10 / p90", "calendar wins", "mean [95%]", "noisy"],
                           [[r["trigger"], r["product"], r["horizon_years"], r["n_starts"], pp(r["gap_median"]), f"{pp(r['gap_p10'])} / {pp(r['gap_p90'])}",
                             f"{r['calendar_wins']:.0%}", f"{pp(r['indep_mean'])} [{pp(r['indep_lo'])}, {pp(r['indep_hi'])}]", "yes" if r["noisy"] else "no"]
                            for r in W["multi_start"] if r["trigger"] in (BASE_TRIGGER, "none")]))
        md.append("### Fills: the close and next-close fills against the level fill (gap risk)\n")
        md.append(md_table(["trigger", "design", "fill", "early resets", "worst fill loss", "on", "level fill loss", "wiped", "CAGR"],
                           [[f["trigger"], f["product"], f["mode"], f["n_early_resets"], pc(f["worst_fill"]), f["worst_fill_date"] or "-",
                             pc(f["designed_level_fill_loss"]), f["terminated"] or "-", pc(f["cagr"], 2)] for f in W["fills"]]))
        md.append("### Costs (trigger scaled, 10-year multi-start)\n")
        md.append(md_table(["cost", "design", "CAGR", "twin CAGR", "median gap", "mean [95%]"],
                           [[r["cost"], r["product"], pc(r["cagr"], 2), pc(r["twin_cagr"], 2), pp(r["gap_median"]),
                             f"{pp(r['indep_mean'])} [{pp(r['indep_lo'])}, {pp(r['indep_hi'])}]"] for r in W["cost_sensitivity"]]))
        md.append("### C13: the 3x gap against the 2x gap at zero cost, no trigger (prediction: 3)\n")
        md.append(md_table(["reset", "10y median 2x", "10y median 3x", "ratio", "full-history log gap 2x", "3x", "ratio", "3x wiped"],
                           [[c["reset"], pp(c["gap10_median_2x"]), pp(c["gap10_median_3x"]),
                             "n/a (wiped)" if c["ratio_10y_median"] is None else f"{c['ratio_10y_median']:.2f}",
                             f"{c['full_log_gap_2x']:+.4f}", "n/a" if c["full_log_gap_3x"] is None else f"{c['full_log_gap_3x']:+.4f}",
                             "n/a" if c["ratio_full"] is None else f"{c['ratio_full']:.2f}", c["wiped_3x"] or "-"] for c in W["c13"]]))
        md.append("### $10,000 through the key periods (base cost)\n")
        names = [d["product"] for d in W["designs"] if d["trigger"] in (BASE_TRIGGER, "none")]
        rows = []
        for k in W["key_periods"]:
            if not k["covered"]:
                continue
            rows.append([k["period"], f"${k['index']:,.0f}", f"${k['twin']:,.0f}"] +
                        [f"${k['funds'][n]['value']:,.0f}" + (" WIPED" if k["funds"][n]["wiped"] else "") for n in names]
                        + [f"${k['real']:,.0f}" if "real" in k else "-"])
        md.append(md_table(["period", "index", "3x daily twin"] + names + [REAL[name]], rows))
        o = W["overlay"]
        md.append(f"### Real {o['real']} (price only) from its first bar, {o['first']} to {o['last']}\n")
        md.append(md_table(["series", "CAGR"], [[f"real {o['real']} (price only)", pc(o["real_cagr"], 2)], ["model at its filed terms", pc(o["model_cagr"], 2)],
                                                ["3x daily twin (1.00% fee)", pc(o["twin_cagr"], 2)]] + [[k, pc(v, 2)] for k, v in o["designs"].items()]
                           + [["index (total return)", pc(o["index_cagr"], 2)]]))
        md.append(f"### {N_MC} simulated decades ({MC_BLOCK}-day blocks, base cost)\n")
        md.append(md_table(["trigger", "reset", "wiped", "early reset", "gap median (10y)", "median wealth", "p5 wealth", "twin median"],
                           [[r["trigger"], r["reset"], f"{r['wiped']:.1%}", f"{r['early']:.1%}", pp(r["gap"]["median"]),
                             f"{r['wealth']['median']:.2f}", f"{r['wealth']['p5']:.3f}", f"{r['twin_wealth']['median']:.2f}"] for r in W["montecarlo"]]))
        md.append(f"Twin wiped on {W['montecarlo'][0]['wiped_twin']:.1%} of the paths. The 35% rule fired before a wipeout in no design: "
                  f"{'confirmed' if W['fixed35_never_fires'] else 'NOT confirmed'}. It watches the day's low, so it ends a fund whose low "
                  "passes 1/3 even when the close recovers; with no trigger the kernel judges a wipeout at the close. Extra wipe rate of that "
                  "intraday test: " + ", ".join(f"{r} {v:+.1%}" for r, v in W["intraday_wipe_extra"].items())
                  + f"; on the history the two rules give the same funds: {W['history_none_equals_fixed35']}.\n")
    return "\n".join(md)


def main():
    wall0 = time.perf_counter()
    print("=" * 100 + "\nB1: 3x calendar resets (all HYPOTHETICAL)")
    worlds, wprov = sub2x.build_worlds()
    real = {}
    for name, sym in REAL.items():
        r = loader.close(sym)
        real[name] = r.loc[:sub2x.STUDY_END]
    inputs = study.inputs_for(worlds, wprov, extra_symbols=list(REAL.values()))
    banner = (provenance.banner_lines(inputs) + [ln for w in worlds.values() for ln in study.conventions_lines(w)]
              + ["B1 trigger rules replace the 35% drop above: " + ", ".join(f"{k} {'none' if v is None else f'{v:.2%}'}" for k, v in TRIGGERS.items()) + ".",
                 f"Study end fixed at {sub2x.STUDY_END}; Monte Carlo seed {rmc.SEED}."])
    print("\n".join(banner))
    res = dict(meta=dict(title="B1: 3x calendar resets against 3x daily twins", run_date=str(pd.Timestamp.today().date()),
                         caption=CAPTION, study_end=sub2x.STUDY_END, L=L3, triggers=TRIGGERS, base_trigger=BASE_TRIGGER,
                         cost_factors=COST_FACTORS, base_cost=BASE_COST, fee=sub2x.FEE_BASE, fill_modes=list(FILL_MODES),
                         key_periods=[list(k) for k in study.KEY_PERIODS], n_mc=N_MC, mc_block=MC_BLOCK, seed=rmc.SEED,
                         underlyings={n: wprov[n] for n in wprov}, inputs=inputs, banner=banner, code=provenance.code_fingerprint(__file__)),
               worlds={})
    for i, (name, w) in enumerate(worlds.items()):
        print(f"\n{name}")
        res["worlds"][name] = run_world(name, w, 10 + i, real[name])
    res["meta"]["timing"] = dict(total_wall_seconds=time.perf_counter() - wall0)
    (OUT / "three_x.json").write_text(json.dumps(provenance.json_safe(res), indent=1, allow_nan=False) + "\n", encoding="utf-8")
    (OUT / "three_x.md").write_text(markdown(res), encoding="utf-8")
    print(f"wrote results/three_x.json and results/three_x.md in {time.perf_counter() - wall0:.0f} s")


if __name__ == "__main__":
    main()
