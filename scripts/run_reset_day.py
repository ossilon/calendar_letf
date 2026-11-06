"""B12 (with B10's remainder): does the DAY the reset lands on change the result, and what does entry on any trading day
look like?

    py scripts\\run_reset_day.py        (from calendar_letf/, with CALENDAR_LETF_DATA / _RATES set; about 1 minute)

B12. The prospectus resets at the last session of the week / month / quarter. The study moves the reset to other days
(periods.anchored_period_end_flags): a weekly fund on Monday to Thursday; a monthly fund on or before the 5th, 10th, 15th
or 20th; a quarterly fund on or before the 5th / 10th / 15th / 20th of the quarter's last month or the 15th of its middle
month. Same index, costs (fixed encoding), 35% trigger (level fill) and daily twin as the passive study. Two layers:
  history          every anchor over the full history: CAGR, the yearly gap against the twin, the yearly difference
                   against the standard day (interval and coverage), the 10-year multi-start gap
  simulated paths  the same anchors on 5000 block-bootstrap decades (calendar_letf/montecarlo.py). A path copies real
                   days onto another calendar, so a calendar anomaly (turn of the month, a weekday effect) does not survive
                   there; an effect that survives is mechanical. An effect in history only is a calendar effect.
B10. Entry on EVERY trading day (not only month-ends), for each design at its standard day: the gap against the twin at
1 and 10 years, by the leverage the fund holds at entry (L (1 + R) / (1 + L R), R the index return since the last reset;
read from the kernel's state, costs and early resets included: bottoms.leverage_series).
Writes results/reset_day.json and results/reset_day.md.
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
from calendar_letf import bottoms as B  # noqa: E402
from calendar_letf import leverage, metrics, montecarlo as mc, periods, products, provenance, stats, study  # noqa: E402

OUT = ROOT / "results"
CAPTION = "Data: TradingView (via local export), FRED. Modeled funds, not live funds. Not investment advice."
ENC = study.ENCODINGS["fixed"]
ANCHORS = {"weekly": ("std", "mon", "tue", "wed", "thu"),
           "monthly": ("std", 5, 10, 15, 20),
           "quarterly": ("std", (3, 5), (3, 10), (3, 15), (3, 20), (2, 15))}
N_MC = 5000
MC_BLOCK = 252
B10_HORIZONS = (1, 10)
LEV_BUCKETS = (1.9, 2.1)          # entry leverage below / between / above, for a 2x fund


def anchor_label(a):
    if a == "std":
        return "std"
    if isinstance(a, tuple):
        return f"m{a[0]}d{a[1]}"
    return a if isinstance(a, str) else f"d{a}"


def flags_for(dates, reset, a):
    return periods.period_end_flags(dates, reset) if a == "std" else periods.anchored_period_end_flags(dates, reset, a)


def items_for(name, dates):
    """(label, spec, period_end flags) for every design and anchor, and one daily twin per design."""
    out = []
    for p in study.PRODUCT_NAMES[name]:
        sp = products.PRODUCTS[p]
        for a in ANCHORS[sp.reset]:
            out.append(((p, anchor_label(a)), sp, flags_for(dates, sp.reset, a)))
        out.append(((p, "twin"), products.twin_of(sp), np.zeros(len(dates), bool)))
    return out


def kw_for(items):
    return dict(period_end=np.array([f for _, _, f in items]),
                L=np.array([sp.L for _, sp, _ in items], dtype=np.float64),
                spread=np.full(len(items), ENC.spread_per_nav), fee=np.array([sp.fee for _, sp, _ in items], dtype=np.float64),
                drop=np.array([sp.early_drop or 0.0 for _, sp, _ in items], dtype=np.float64),
                rate_mult=np.full(len(items), ENC.rate_turns), daily=np.array([sp.reset == "daily" for _, sp, _ in items]))


def history(name, w):
    """Every design at every anchor over the full history, in one batch call on the real path."""
    items = items_for(name, w.dates)
    low = w.trigger if w.trigger_low is None else w.trigger_low
    navc, mdd, early, term = mc.simulate_batch(w.u_arr[None, :], w.trigger.to_numpy()[None, :], low.to_numpy()[None, :],
                                               w.rate_arr[None, :], w.accrual_fin, w.accrual_fee, checkpoints=np.arange(len(w.dates)),
                                               **kw_for(items))
    navs = {lab: pd.Series(navc[0, k], index=w.dates) for k, (lab, _, _) in enumerate(items)}
    # the standard anchor through the batch must equal the passive study's own run (kernel.run), to rounding
    for p in study.PRODUCT_NAMES[name]:
        ref = w.nav(p, ENC)
        err = float(np.max(np.abs(ref.to_numpy() - navs[(p, "std")].to_numpy())))
        if err > 1e-10:
            raise ValueError(f"{name} {p}: the batch run differs from kernel.run by {err:.2e}")
    s, e = w.month_pairs(120)
    rows = []
    for p in study.PRODUCT_NAMES[name]:
        sp = products.PRODUCTS[p]
        tw = navs[(p, "twin")]
        ytw = leverage.yearly_log_returns(tw)
        ystd = leverage.yearly_log_returns(navs[(p, "std")])
        c_tw = metrics.window_stats(tw, s, e)["cagr"]
        for a in ANCHORS[sp.reset]:
            lab = anchor_label(a)
            nav = navs[(p, lab)]
            k = [x[0] for x in items].index((p, lab))
            y = leverage.yearly_log_returns(nav)
            yrs = sorted(y)
            g10 = metrics.window_stats(nav, s, e)["cagr"] - c_tw
            pp_ = stats.phase_pooled_mean(g10, 120)
            row = dict(product=p, reset=sp.reset, anchor=lab, cagr=metrics.cagr(nav), max_dd=float(mdd[0, k]), early_resets=int(early[0, k]),
                       terminated=bool(term[0, k] >= 0), resets=int(items[k][2].sum()),
                       gap_yearly=sub2x.interval_with_coverage(np.array([y[t] - ytw[t] for t in yrs]), f"resetday {name} {p} {lab} gap"),
                       gap10_median=float(np.nanmedian(g10)), gap10_indep=dict(mean=pp_["mean"], lo=pp_["lo"], hi=pp_["hi"], df=pp_["df"]))
            if lab != "std":
                d = np.array([y[t] - ystd[t] for t in yrs])
                mi = sub2x.interval_with_coverage(d, f"resetday {name} {p} {lab} minus std")
                if mi.get("se") and np.isfinite(mi["se"]) and mi["se"] > 0:      # the t statistic and its two-sided p (k - 1 df)
                    mi["t"] = float(mi["mean"] / mi["se"])
                    mi["p"] = stats.t_two_sided_p(mi["t"], mi["k"] - 1)
                row["minus_std_yearly"] = mi
            rows.append(row)
    return rows, navs


def simulated(name, w, idx):
    """The same anchors on block-bootstrap decades: the 10-year gap against the twin and the paired difference against the
    standard day."""
    S = rmc.Setup(name, w)
    S.idx = idx
    items = items_for(name, S.cal)
    kw = kw_for(items)
    labels = [lab for lab, _, _ in items]
    starts = mc.block_starts(len(S.h["lr_u"]), MC_BLOCK)
    gaps = {lab: [] for lab in labels}
    for b in range(-(-N_MC // rmc.BATCH)):
        P = min(rmc.BATCH, N_MC - b * rmc.BATCH)
        U, T, TL, R = mc.build_paths(S.h, mc.block_pick(rmc.seq(11, idx, b), starts, MC_BLOCK, S.n, P, random_phase=True))
        navc, *_ = mc.simulate_batch(U, T, TL, R, S.af, S.ae, checkpoints=np.array([0, S.n], dtype=np.int64), **kw)
        yrs = (S.cal[-1] - S.cal[0]).days / 365.25
        for k, lab in enumerate(labels):
            gaps[lab].append(mc.cagr_between(navc[:, k, :], 0, 1, yrs))
    G = {lab: np.concatenate(v) for lab, v in gaps.items()}
    rows = []
    for p in study.PRODUCT_NAMES[name]:
        sp = products.PRODUCTS[p]
        tw = G[(p, "twin")]
        base = G[(p, "std")] - tw
        for a in ANCHORS[sp.reset]:
            lab = anchor_label(a)
            g = G[(p, lab)] - tw
            d = g - base
            se = float(d.std(ddof=1) / math.sqrt(len(d))) if lab != "std" else 0.0
            rows.append(dict(product=p, reset=sp.reset, anchor=lab, gap=rmc.tails(g),
                             minus_std_mean=float(d.mean()), minus_std_se=se,
                             minus_std_z=float(d.mean() / se) if se > 0 else None))
    return rows


def every_day(name, w):
    """B10: entry at the close of every trading day, each design at its standard day, against its twin."""
    out = []
    dates = w.dates
    days = dates.values.astype("datetime64[D]")
    for p in study.PRODUCT_NAMES[name]:
        sp = products.PRODUCTS[p]
        nav, tw = w.nav(p, ENC), w.nav(w.twin_name(p), ENC)
        # the leverage held after the close of each day (the entry leverage), read from the kernel's state with the run's
        # own costs: L (1 + R) / (1 + L R) with costs, and with the trigger level as the base after a level-fill early reset
        lev = B.leverage_series(w, sp, ENC)
        first = int(np.flatnonzero(periods.period_end_flags(dates, sp.reset))[0])    # the first real reset
        for hy in B10_HORIZONS:
            target = (dates + pd.DateOffset(years=hy)).values.astype("datetime64[D]")
            e = np.searchsorted(days, target, side="right") - 1
            s = np.arange(len(dates))
            ok = (s >= first) & (target <= days[-1])
            s, e = s[ok], e[ok]
            g = metrics.window_stats(nav, s, e)["cagr"] - metrics.window_stats(tw, s, e)["cagr"]
            step = int(round(np.median(e - s)))
            pp_ = stats.phase_pooled_mean(g, step)
            me = periods.period_end_flags(dates, "monthly")[s]
            L0 = lev[s]
            buckets = []
            for lab, m in (("below", L0 < LEV_BUCKETS[0]), ("near", (L0 >= LEV_BUCKETS[0]) & (L0 <= LEV_BUCKETS[1])), ("above", L0 > LEV_BUCKETS[1])):
                buckets.append(dict(bucket=lab, n=int(m.sum()), gap_median=float(np.nanmedian(g[m])) if m.any() else None,
                                    wins=float((g[m] > 0).mean()) if m.any() else None))
            out.append(dict(product=p, reset=sp.reset, horizon_years=hy, n_starts=int(len(s)), gap_median=float(np.nanmedian(g)),
                            gap_mean=float(np.nanmean(g)), wins=float((g > 0).mean()), indep=dict(mean=pp_["mean"], lo=pp_["lo"], hi=pp_["hi"], df=pp_["df"]),
                            month_end_gap_median=float(np.nanmedian(g[me])), month_end_n=int(me.sum()),
                            entry_leverage=dict(p5=float(np.nanpercentile(L0, 5)), median=float(np.nanmedian(L0)), p95=float(np.nanpercentile(L0, 95))),
                            by_entry_leverage=buckets))
    return out


# ---------------------------------------------------------------- report
def pp(x, d=2):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:+.{d}f}"


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]) + "\n"


def iv(x):
    return "-" if not x or x.get("lo") is None or not np.isfinite(x["lo"]) else f"[{pp(x['lo'])}, {pp(x['hi'])}] {x['verdict']}"


def tp(x):
    return "-" if not x or "p_holm" not in x else f"{x['t']:+.2f} / {x['p']:.3f} / {x['p_holm']:.2f}"


def markdown(res):
    m = res["meta"]
    md = [f"# {m['title']}\n", f"*{m['caption']}*\n", "```", *m["banner"], "```\n",
          "Anchors: std = the prospectus day (last session of the period); mon-thu = the last session on or before that weekday; "
          "dN = on or before day N of the month; mKdN = on or before day N of the quarter's K-th month.\n"]
    for name, W in res["worlds"].items():
        md.append(f"## {sub2x.UNDERLYING_NAME[name]}\n### History (fixed cost, level fill)\n")
        md.append(md_table(["design", "anchor", "resets", "CAGR", "early resets", "yearly gap vs twin (95%)", "minus std, yearly (95%)",
                            "t / p / Holm p", "10y median gap", "10y mean [95%]"],
                           [[r["product"], r["anchor"], r["resets"], f"{r['cagr'] * 100:.2f}%", r["early_resets"], iv(r["gap_yearly"]),
                             iv(r.get("minus_std_yearly")), tp(r.get("minus_std_yearly")), pp(r["gap10_median"]),
                             f"{pp(r['gap10_indep']['mean'])} [{pp(r['gap10_indep']['lo'])}, {pp(r['gap10_indep']['hi'])}]"] for r in W["history"]]))
        md.append(f"### {N_MC} simulated decades ({MC_BLOCK}-day blocks): 10-year gap and the paired difference against std\n")
        md.append(md_table(["design", "anchor", "gap median", "gap mean +/- SE", "minus std (mean +/- SE)", "z"],
                           [[r["product"], r["anchor"], pp(r["gap"]["median"]), f"{pp(r['gap']['mean'])} +/- {r['gap']['mean_se'] * 100:.2f}",
                             f"{pp(r['minus_std_mean'], 3)} +/- {r['minus_std_se'] * 100:.3f}", "-" if r["minus_std_z"] is None else f"{r['minus_std_z']:+.1f}"]
                            for r in W["simulated"]]))
        md.append("### B10: entry on every trading day (standard day)\n")
        md.append(md_table(["design", "years", "starts", "median gap", "wins", "mean [95%]", "month-end starts median", "entry L p5 / median / p95",
                            "gap by entry L: <1.9 / 1.9-2.1 / >2.1"],
                           [[r["product"], r["horizon_years"], r["n_starts"], pp(r["gap_median"]), f"{r['wins']:.0%}",
                             f"{pp(r['indep']['mean'])} [{pp(r['indep']['lo'])}, {pp(r['indep']['hi'])}]", pp(r["month_end_gap_median"]),
                             f"{r['entry_leverage']['p5']:.2f} / {r['entry_leverage']['median']:.2f} / {r['entry_leverage']['p95']:.2f}",
                             " / ".join(f"{pp(b['gap_median'])} (n {b['n']})" for b in r["by_entry_leverage"])] for r in W["every_day"]]))
    return "\n".join(md)


def main():
    wall0 = time.perf_counter()
    print("=" * 100 + "\nB12 + B10: reset day and entry on any day (MODELED funds)")
    worlds, wprov = sub2x.build_worlds()
    # the passive study's products (2x, registry) on the B17 worlds, cut at the fixed study end
    worlds = {n: study.World(n, w.u, w.trigger, w.rate, [products.PRODUCTS[p] for p in study.PRODUCT_NAMES[n]],
                             {p: products.twin_of(products.PRODUCTS[p]) for p in study.PRODUCT_NAMES[n]},
                             trigger_low=w.trigger_low, trigger_basis=w.trigger_basis, trigger_info=w.trigger_info)
              for n, w in worlds.items()}
    inputs = study.inputs_for(worlds, wprov)
    banner = (provenance.banner_lines(inputs) + [ln for w in worlds.values() for ln in study.conventions_lines(w)]
              + [f"Encoding: {ENC.describe()}. Study end fixed at {sub2x.STUDY_END}; Monte Carlo seed {rmc.SEED}."])
    print("\n".join(banner))
    res = dict(meta=dict(title="B12 + B10: the reset day and entry on any day", run_date=str(pd.Timestamp.today().date()), caption=CAPTION,
                         study_end=sub2x.STUDY_END, anchors={k: [anchor_label(a) for a in v] for k, v in ANCHORS.items()},
                         encoding=ENC.describe(), n_mc=N_MC, mc_block=MC_BLOCK, seed=rmc.SEED, b10_horizons=list(B10_HORIZONS),
                         lev_buckets=list(LEV_BUCKETS), underlyings={n: wprov[n] for n in wprov}, inputs=inputs, banner=banner,
                         code=provenance.code_fingerprint(__file__)), worlds={})
    b11_path = OUT / "montecarlo.json"
    b11 = json.loads(b11_path.read_text(encoding="utf-8"))
    res["meta"]["b11_source"] = dict(file="results/montecarlo.json", sha256=provenance.sha256_of(b11_path))
    for i, (name, w) in enumerate(worlds.items()):
        t0 = time.perf_counter()
        hist, _ = history(name, w)
        sim = simulated(name, w, 30 + i)
        ed = every_day(name, w)
        # B11 drew its blocks with seams on fixed rows (near the standard period ends); here every path has a random phase.
        # The difference in the standard day's 10-year median gap says how much that alignment moved B11's figures.
        aligned = {r["product"]: r["gap"]["median"] for r in b11["worlds"][name]["bootstrap"]
                   if r["block"] == MC_BLOCK and r["encoding"] == "fixed" and r["horizon_years"] == 10}
        phase = [dict(product=r["product"], b11_aligned=aligned[r["product"]], random_phase=r["gap"]["median"],
                      difference=aligned[r["product"]] - r["gap"]["median"]) for r in sim if r["anchor"] == "std"]
        res["worlds"][name] = dict(history=hist, simulated=sim, every_day=ed, seam_alignment=phase)
        print(f"  {name}: {time.perf_counter() - t0:.0f} s")
    allw = res["worlds"].values()
    # One family: every anchor against the standard day, both indexes (they overlap in time, so this is not two
    # independent tests). Holm's adjustment over the whole family (re-grade 2026-11-06, finding U1).
    fam = [r["minus_std_yearly"] for W in allw for r in W["history"] if r["anchor"] != "std" and "p" in r.get("minus_std_yearly", {})]
    for x, ph in zip(fam, stats.holm([x["p"] for x in fam])):
        x["p_holm"] = float(ph)
    res["summary"] = dict(
        history_family=len(fam), history_max_abs_t=max(abs(x["t"]) for x in fam), history_min_p=min(x["p"] for x in fam),
        history_min_p_holm=min(x["p_holm"] for x in fam), history_n_holm_below_005=sum(1 for x in fam if x["p_holm"] < 0.05),
        n_history_comparisons=sum(1 for W in allw for r in W["history"] if r["anchor"] != "std"),
        sim_max_abs_minus_std=max(abs(r["minus_std_mean"]) for W in allw for r in W["simulated"]),
        seam_alignment_max_abs=max(abs(x["difference"]) for W in allw for x in W["seam_alignment"]),
        b10_max_abs_vs_month_end=max(abs(r["gap_median"] - r["month_end_gap_median"]) for W in allw for r in W["every_day"]
                                     if r["horizon_years"] == 10))
    res["meta"]["timing"] = dict(total_wall_seconds=time.perf_counter() - wall0)
    (OUT / "reset_day.json").write_text(json.dumps(provenance.json_safe(res), indent=1, allow_nan=False) + "\n", encoding="utf-8")
    (OUT / "reset_day.md").write_text(markdown(res), encoding="utf-8")
    print(f"wrote results/reset_day.json and results/reset_day.md in {time.perf_counter() - wall0:.0f} s")


if __name__ == "__main__":
    main()
