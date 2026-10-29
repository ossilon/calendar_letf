#!/usr/bin/env python3
"""Simulated coverage of the interval conventions at every configuration the passive study publishes.

    py scripts\\run_coverage_sim.py          writes results/coverage_sim.json and results/coverage_sim.md (about a minute)

What it does, in plain English
  1. For each (starts n, window h) the passive study publishes (S&P 500 and Nasdaq-100 at 1, 3, 5 and 10 years; n is
     READ from results/calendar_vs_daily.json, so a data top-up cannot leave it stale) it builds 400 synthetic gap series with the study's
     own overlap structure and independent monthly shocks (calendar_letf/coverage.py), applies the block-bootstrap
     mean and median intervals and the phase-pooled interval, and records how often each contains the true constant
     (the coverage), how far each standard error sits from the true one, and the t multiplier the pooled statistic
     would need for 95 percent coverage next to the one the convention uses.
  2. One large configuration (2,412 starts of 12-month windows: 201 blocks) separates the two causes of the block
     bootstrap's short standard error: block = window length (present at any block count) and few blocks.
  3. Regime stress: the eight configurations again, with a slow AR(1) component in the monthly shocks (phi 0.98 and
     0.995, half-lives about 34 and 138 months; 2 and 5 percent of the shock variance), which makes windows that do
     not overlap depend on each other. Each case reports the simulated lag-h autocorrelation of its gap series next
     to the coverage, so it can be matched to the data.
  4. Measured persistence: the autocorrelation at lags h, 2h and 3h of the REAL per-start gap series in
     results/raw/multi_start_{SPX,NDX}_fixed.csv (written by run_calendar_vs_daily.py), per product and horizon;
     then, for each product and horizon, the regime case whose simulated lag-h autocorrelation is nearest the
     measured one, with that case's coverage: the stated limit of the headline interval.
  Deterministic: every case carries its seed; tests/test_stats.py recomputes three cases and compares them with the
  file. The cases run in parallel processes.
"""
import json
import math
import sys
import time
from datetime import date
from multiprocessing import Pool, cpu_count
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from calendar_letf import coverage, provenance, stats, study  # noqa: E402

OUT = HERE.parent / "results"
RAW = OUT / "raw"
RUNS, N_BOOT = 400, 1000
# (world, horizon years, seed). Seeds 3101-3103 are the three cases tests/test_stats.py has recomputed since R2 step 10;
# the suite compares its recomputation with this file's entries. The starts n come from the passive study (iid_configs).
IID_SEEDS = (("SPX", 10, 3101), ("NDX", 10, 3102), ("SPX", 1, 3103), ("SPX", 3, 3104), ("SPX", 5, 3105),
             ("NDX", 1, 3106), ("NDX", 3, 3107), ("NDX", 5, 3108))
CVD_JSON = OUT / "calendar_vs_daily.json"


def published_starts(cvd, world, hy):
    """The number of month-end starts the passive study published for (world, horizon); every product shares it."""
    ns = {r["n_starts"] for r in cvd["worlds"][world]["multi_start"]["fixed"] if r["horizon_years"] == hy}
    if len(ns) != 1:
        raise ValueError(f"{world} {hy}y: products disagree on n_starts {sorted(ns)}")
    return ns.pop()


def iid_configs():
    """(world, horizon years, starts n, window h in months, seed) for every published configuration, n read from
    results/calendar_vs_daily.json (run scripts/run_calendar_vs_daily.py first)."""
    if not CVD_JSON.exists():
        raise SystemExit("results/calendar_vs_daily.json is absent: run py scripts\\run_calendar_vs_daily.py first")
    cvd = json.loads(CVD_JSON.read_text(encoding="utf-8"))
    return tuple((w, hy, published_starts(cvd, w, hy), 12 * hy, s) for w, hy, s in IID_SEEDS)
MECHANISM = ("large k", 0, 2412, 12, 3109)                               # 201 blocks of 12: the block-length cause alone
REGIMES = ((0.98, 0.02), (0.98, 0.05), (0.995, 0.02), (0.995, 0.05))     # (phi of the slow component, share of the shock variance)
REGIME_SEED0 = 4000
PERSISTENT_ACF = 0.08                                                    # a regime case at or above this lag-h autocorrelation counts as persistent
NULL_RUNS, NULL_SEED0 = 4000, 5000                                       # the iid null distribution of the lag-h autocorrelation
RAW_FILES = {"SPX": "multi_start_SPX_fixed.csv", "NDX": "multi_start_NDX_fixed.csv"}


SPREAD_SEEDS = (0, 1, 2, 3)        # the Monte Carlo error of a published bootstrap bound: its movement over these seeds


def _spread_task(args):
    """Monte Carlo error of the block-bootstrap bounds for one real gap series: the movement of each bound (mean and
    median intervals, lower and upper) over SPREAD_SEEDS at the study's own draw count. args = (world, product,
    horizon_years, gaps). Seed 0 is the published value."""
    world, product, hy, gaps = args
    g = np.asarray(gaps, dtype=float)
    block = 12 * hy
    ms = [stats.block_bootstrap_mean(g, block, n_boot=study.N_BOOT, seed=s) for s in SPREAD_SEEDS]
    md = [stats.block_bootstrap_median(g, block, n_boot=study.N_BOOT, seed=s) for s in SPREAD_SEEDS]

    def spread(rows, key):
        return float(max(r[key] for r in rows) - min(r[key] for r in rows))

    rec = dict(world=world, product=product, horizon_years=hy, n=int(len(g)), block=block, seeds=list(SPREAD_SEEDS), n_boot=int(study.N_BOOT),
               mean_lo_spread=spread(ms, "lo"), mean_hi_spread=spread(ms, "hi"), median_lo_spread=spread(md, "lo"), median_hi_spread=spread(md, "hi"),
               seed0_mean_lo=float(ms[0]["lo"]), seed0_mean_hi=float(ms[0]["hi"]), seed0_median_lo=float(md[0]["lo"]), seed0_median_hi=float(md[0]["hi"]))
    rec["mean_spread"] = max(rec["mean_lo_spread"], rec["mean_hi_spread"])
    rec["median_spread"] = max(rec["median_lo_spread"], rec["median_hi_spread"])
    rec["max_spread"] = max(rec["mean_spread"], rec["median_spread"])
    return rec


def _read_gaps(path):
    """{(product, horizon_years): [gap per start, in start order]} from a results/raw/multi_start_*.csv file."""
    import csv
    from collections import defaultdict
    out = defaultdict(list)
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            out[(row["product"], int(float(row["horizon_years"])))].append((row["start"], float(row["gap"])))
    return {k: [v for _, v in sorted(rows)] for k, rows in out.items()}


def _task(args):
    """One simulation case, in a worker process. args = (kind, world, horizon_years, n, h, seed, regime)."""
    kind, world, hy, n, h, seed, regime = args
    r = coverage.simulate(n, h, seed, runs=RUNS, n_boot=N_BOOT, regime=regime)
    r.update(kind=kind, world=world, horizon_years=hy)
    if regime is not None:
        r.update(phi=float(regime[0]), share=float(regime[1]))        # flat copies, so a row can be selected by them
    return r


def _clean(obj):
    """NaN and infinities become null so the JSON is strict and loads anywhere."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def _fmt(x, nd=3):
    return "n/a" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.{nd}f}"


def main():
    wall0 = time.perf_counter()
    OUT.mkdir(exist_ok=True)
    IID_CONFIGS = iid_configs()
    tasks = [("iid", w, hy, n, h, s, None) for w, hy, n, h, s in IID_CONFIGS]
    tasks.append(("mechanism", MECHANISM[0], MECHANISM[1], MECHANISM[2], MECHANISM[3], MECHANISM[4], None))
    for j, reg in enumerate(REGIMES):
        for i, (w, hy, n, h, _s) in enumerate(IID_CONFIGS):
            tasks.append(("regime", w, hy, n, h, REGIME_SEED0 + 100 * j + i, reg))
    # the real gap series (present after run_calendar_vs_daily.py): the seed spread of the published bootstrap bounds
    spread_tasks = []
    for world, name in RAW_FILES.items():
        path = RAW / name
        if path.exists():
            for (product, hy), gaps in sorted(_read_gaps(path).items()):
                spread_tasks.append((world, product, hy, gaps))
    print(f"coverage simulation: {len(tasks)} cases x {RUNS} runs, {N_BOOT} bootstrap resamples per run, plus the seed spread of "
          f"{len(spread_tasks)} published bootstrap rows ({len(SPREAD_SEEDS)} seeds x {study.N_BOOT:,} draws), on {min(cpu_count(), len(tasks))} processes")
    with Pool(processes=min(cpu_count(), len(tasks))) as pool:
        done = pool.map(_task, tasks)
        spreads = pool.map(_spread_task, spread_tasks) if spread_tasks else []
    spread_summary = None
    if spreads:
        worst = max(spreads, key=lambda r: r["max_spread"])
        spread_summary = dict(max_spread=worst["max_spread"], max_spread_row=f"{worst['world']} {worst['product']} {worst['horizon_years']}y",
                              max_mean_spread=max(r["mean_spread"] for r in spreads), max_median_spread=max(r["median_spread"] for r in spreads),
                              max_spread_10y=max(r["max_spread"] for r in spreads if r["horizon_years"] == 10), rows=len(spreads))
    iid = [r for r in done if r["kind"] == "iid"]
    mech = next(r for r in done if r["kind"] == "mechanism")
    regime = [r for r in done if r["kind"] == "regime"]

    # 4. measured persistence of the real gap series, its Monte Carlo null, and the nearest regime case per product and horizon
    measured, matched, raw_used, nulls = {}, [], [], {}
    for world, name in RAW_FILES.items():
        path = RAW / name
        if not path.exists():
            print(f"note: {path.name} absent (run scripts/run_calendar_vs_daily.py); measured persistence for {world} skipped")
            continue
        raw_used.append(provenance.file_record(path))
        measured[world] = coverage.measured_persistence(path)
        for rec in measured[world]:
            cases = [r for r in regime if r["world"] == world and r["horizon_years"] == rec["horizon_years"]]
            base = next((r for r in iid if r["world"] == world and r["horizon_years"] == rec["horizon_years"]), None)
            # The lag-h autocorrelation of overlapping-window means is NEGATIVE under independent months (few windows,
            # one shared mean), so the measured value is judged against the iid case's own value: first in units of the
            # rough standard error 1 / sqrt(n / h) (excess_se, a conservative screen: that se is 1.2-3.3 times the true
            # sampling SD), then against the simulated null distribution itself (NULL_RUNS iid series, no bootstrap):
            # excess_mc_sd = (measured - null mean) / null SD, p_mc = share of null draws at or above the measured value.
            rec["acf_iid_expected"] = None if base is None else base["acf_gap_h"]
            rec["excess_se"] = (None if base is None or rec["acf_lag_1h"] is None or not math.isfinite(rec["acf_lag_1h"])
                                else (rec["acf_lag_1h"] - base["acf_gap_h"]) / rec["se_if_independent"])
            key = (world, rec["horizon_years"])
            if key not in nulls and base is not None:
                nulls[key] = coverage.acf_null(base["n"], base["h"], NULL_SEED0 + 10 * len(nulls), runs=NULL_RUNS)
            null = nulls.get(key)
            if null is not None and rec["acf_lag_1h"] is not None and math.isfinite(rec["acf_lag_1h"]):
                rec["null_acf_mean"], rec["null_acf_sd"] = float(null.mean()), float(null.std(ddof=1))
                rec["null_acf_q95"], rec["null_acf_q99"] = float(np.quantile(null, 0.95)), float(np.quantile(null, 0.99))
                rec["excess_mc_sd"] = (rec["acf_lag_1h"] - rec["null_acf_mean"]) / rec["null_acf_sd"]
                rec["p_mc"] = coverage.mc_p_value(null, rec["acf_lag_1h"])
                rec["null_runs"] = int(len(null))
            else:
                rec["null_acf_mean"] = rec["null_acf_sd"] = rec["null_acf_q95"] = rec["null_acf_q99"] = rec["excess_mc_sd"] = rec["p_mc"] = None
                rec["null_runs"] = 0
            if not cases or base is None or rec["acf_lag_1h"] is None or not math.isfinite(rec["acf_lag_1h"]):
                continue
            pool_ = cases + [base]                                     # the iid case is the "no persistence" candidate
            best = min(pool_, key=lambda r: abs(r["acf_gap_h"] - rec["acf_lag_1h"]))
            matched.append(dict(world=world, product=rec["product"], horizon_years=rec["horizon_years"], n=rec["n"],
                                measured_acf_h=rec["acf_lag_1h"], se_if_independent=rec["se_if_independent"],
                                regime=best["regime"], simulated_acf_h=best["acf_gap_h"],
                                coverage_pooled=best["coverage_pooled"], coverage_bb_mean=best["coverage_bb_mean"],
                                t_needed_pooled=best["t_needed_pooled"], t_used_pooled=best["t_used_pooled"]))

    # The regime cases that carry real persistence: lag-h autocorrelation at or above PERSISTENT_ACF. ASSUMPTIONS section 7
    # quotes this subset's range; it is computed here from its definition, not frozen as a list of seeds (R4 re-grade).
    persistent = [r for r in regime if r["acf_gap_h"] is not None and math.isfinite(r["acf_gap_h"]) and r["acf_gap_h"] >= PERSISTENT_ACF]
    summary = dict(
        regime_persistent_acf=PERSISTENT_ACF, regime_persistent_n=len(persistent),
        regime_persistent_acf_min=min(r["acf_gap_h"] for r in persistent), regime_persistent_acf_max=max(r["acf_gap_h"] for r in persistent),
        regime_persistent_pooled_min=min(r["coverage_pooled"] for r in persistent), regime_persistent_pooled_max=max(r["coverage_pooled"] for r in persistent),
        bb_mean_min=min(r["coverage_bb_mean"] for r in iid), bb_mean_max=max(r["coverage_bb_mean"] for r in iid),
        bb_median_min=min(r["coverage_bb_median"] for r in iid), bb_median_max=max(r["coverage_bb_median"] for r in iid),
        pooled_min=min(r["coverage_pooled"] for r in iid), pooled_max=max(r["coverage_pooled"] for r in iid),
        se_ratio_bb_min=min(r["se_ratio_bb"] for r in iid), se_ratio_bb_max=max(r["se_ratio_bb"] for r in iid),
        se_ratio_bb_large_k=mech["se_ratio_bb"], large_k=mech["k"],
        ten_year_t_needed={f"{r['world']}": r["t_needed_pooled"] for r in iid if r["horizon_years"] == 10},
        ten_year_t_used={f"{r['world']}": r["t_used_pooled"] for r in iid if r["horizon_years"] == 10},
        regime_pooled_min=min(r["coverage_pooled"] for r in regime), regime_acf_h_max=max(r["acf_gap_h"] for r in regime))
    R = dict(meta=dict(title="Simulated coverage of the interval conventions (R2 step 11)", run_date=str(date.today()), runs=RUNS,
                       n_boot=N_BOOT, true_gap=coverage.TRUE_GAP, shock_sd=coverage.SHOCK_SD, regimes=[dict(phi=p, share=s) for p, s in REGIMES],
                       code=provenance.code_fingerprint(__file__), raw_inputs=raw_used, wall_seconds=time.perf_counter() - wall0,
                       caption="Coverage = share of 400 synthetic histories whose 95% interval contains the true constant. Synthetic gap at start s = "
                               "constant + mean of the h monthly shocks from s (the study's overlap). Block-bootstrap intervals: block = h, t(k-1) x SE. "
                               "Phase-pooled: non-overlapping windows per start phase, pooled, t(min k_p - 1) x SE (the headline). 't needed' = 95th "
                               "percentile of |pooled mean - truth| / SE over runs; 't used' = the t multiplier the convention applies."),
             summary=summary, iid=iid, mechanism=mech, regime=regime, measured_persistence=measured, matched=matched,
             bb_seed_spread=spreads, bb_seed_spread_summary=spread_summary)
    (OUT / "coverage_sim.json").write_text(json.dumps(_clean(R), indent=1), encoding="utf-8")

    md = ["# Simulated coverage of the interval conventions\n", R["meta"]["caption"] + "\n",
          f"{RUNS} runs per case, {N_BOOT} bootstrap resamples per run; seeds in the JSON. Code fingerprint {R['meta']['code']['sha256'][:12]}.\n",
          "## 1. Published configurations, independent monthly shocks\n",
          "| world | horizon | starts n | h = block | k | df | coverage: bb mean | bb median | phase-pooled | bootstrap SE / true SD | pooled SE / true SD | t needed (pooled) | t used | acf of gaps at lag h |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(iid, key=lambda r: (r["world"], r["horizon_years"])):
        md.append(f"| {r['world']} | {r['horizon_years']}y | {r['n']} | {r['h']} | {r['k']} | {r['df']} | {r['coverage_bb_mean']:.3f} | {r['coverage_bb_median']:.3f} | "
                  f"{r['coverage_pooled']:.3f} | {r['se_ratio_bb']:.2f} | {r['se_ratio_pooled']:.2f} | {r['t_needed_pooled']:.2f} | {r['t_used_pooled']:.2f} | {_fmt(r['acf_gap_h'], 2)} |")
    md.append(f"\nRange over the eight cases: block-bootstrap mean {summary['bb_mean_min']:.3f}-{summary['bb_mean_max']:.3f}, median "
              f"{summary['bb_median_min']:.3f}-{summary['bb_median_max']:.3f}, phase-pooled {summary['pooled_min']:.3f}-{summary['pooled_max']:.3f}; "
              f"bootstrap SE ratio {summary['se_ratio_bb_min']:.2f}-{summary['se_ratio_bb_max']:.2f}.\n")
    md.append("## 2. Why the block bootstrap is short: block = window length, not only few blocks\n")
    md.append(f"| case | starts n | h = block | k | coverage: bb mean | bb median | phase-pooled | bootstrap SE / true SD |\n|---|---|---|---|---|---|---|---|\n"
              f"| {mech['world']} | {mech['n']} | {mech['h']} | {mech['k']} | {mech['coverage_bb_mean']:.3f} | {mech['coverage_bb_median']:.3f} | {mech['coverage_pooled']:.3f} | {mech['se_ratio_bb']:.2f} |\n")
    md.append("A block bootstrap sees only the dependence inside one block. For a gap that is the mean of h shocks, blocks of length h lose about a third of "
              "the variance of the series mean at ANY block count (the Bartlett-type truncation at one window), and the few-block cases lose more on top.\n")
    md.append("## 3. Regime stress: a slow AR(1) component in the monthly shocks\n")
    md.append(f"'t needed' is the 95th percentile of {RUNS} runs, so it carries Monte Carlo error; the bracket is its distribution-free 95% "
              "interval (order statistics, `coverage.quantile_interval`). A t ratio inside the bracket cannot be called clear or noisy under that case.\n")
    md.append("| world | horizon | phi | share | half-life (months) | acf of gaps at lag h | at lag 2h | coverage: bb mean | phase-pooled | t needed (pooled) [95% MC] | t used |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(regime, key=lambda r: (r["world"], r["horizon_years"], r["regime"]["phi"], r["regime"]["share"])):
        g = r["regime"]
        md.append(f"| {r['world']} | {r['horizon_years']}y | {g['phi']:g} | {g['share']:g} | {g['half_life_months']:.0f} | {_fmt(r['acf_gap_h'], 2)} | {_fmt(r['acf_gap_2h'], 2)} | "
                  f"{r['coverage_bb_mean']:.3f} | {r['coverage_pooled']:.3f} | {r['t_needed_pooled']:.2f} [{_fmt(r['t_needed_pooled_lo'], 2)}, {_fmt(r['t_needed_pooled_hi'], 2)}] | {r['t_used_pooled']:.2f} |")
    md.append("\n## 4. Persistence measured in the real gap series (results/raw), and the nearest simulated case\n")
    if not measured:
        md.append("results/raw/multi_start_*_fixed.csv absent: run scripts/run_calendar_vs_daily.py first.\n")
    for world, recs in measured.items():
        md.append(f"\n{world}: autocorrelation of the per-start gap at lags h, 2h, 3h (h = horizon in months); se if independent = 1 / sqrt(n / h) "
                  "(a conservative rule of thumb, 1.2-3.3 times the true sampling SD); 'iid expected' = the same statistic in the iid simulation "
                  f"(negative: few windows share one mean); 'excess' = (measured - iid expected) / se; the Monte Carlo columns use {NULL_RUNS:,} "
                  "iid series per configuration: null SD, excess in null SDs, and the one-sided p (share of null draws at or above the measured value).\n")
        md.append("| product | horizon | starts n | acf lag h | lag 2h | lag 3h | se if independent | iid expected | excess (se) | null SD | excess (MC SD) | p (MC) |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
        for rec in recs:
            md.append(f"| {rec['product']} | {rec['horizon_years']}y | {rec['n']} | {_fmt(rec['acf_lag_1h'], 2)} | {_fmt(rec['acf_lag_2h'], 2)} | {_fmt(rec['acf_lag_3h'], 2)} | "
                      f"{rec['se_if_independent']:.2f} | {_fmt(rec.get('acf_iid_expected'), 2)} | {_fmt(rec.get('excess_se'), 1)} | {_fmt(rec.get('null_acf_sd'), 3)} | "
                      f"{_fmt(rec.get('excess_mc_sd'), 1)} | {_fmt(rec.get('p_mc'), 4)} |")
    if matched:
        md.append("\nNearest simulated case by lag-h autocorrelation (the iid case counts as 'no persistence'). READ WITH CARE: one lag-h number is a "
                  "poor summary of a slow regime (the phi 0.995 cases show a small lag-h autocorrelation but a large dependence spread over many "
                  "lags), so this matching is rough; the register quotes the RANGE of coverage over the regime cases, not a matched value.\n")
        md.append("| world | product | horizon | measured acf lag h | nearest case | its acf lag h | its phase-pooled coverage | its bb-mean coverage | t needed | t used |")
        md.append("|---|---|---|---|---|---|---|---|---|---|")
        for m in matched:
            case = "iid" if m["regime"] is None else f"phi {m['regime']['phi']:g}, share {m['regime']['share']:g}"
            md.append(f"| {m['world']} | {m['product']} | {m['horizon_years']}y | {_fmt(m['measured_acf_h'], 2)} | {case} | {_fmt(m['simulated_acf_h'], 2)} | "
                      f"{m['coverage_pooled']:.3f} | {m['coverage_bb_mean']:.3f} | {m['t_needed_pooled']:.2f} | {m['t_used_pooled']:.2f} |")
    if spreads:
        md.append(f"\n## 5. Monte Carlo error of the published bootstrap bounds\n\nEach bound of the block-bootstrap mean and median intervals (block = horizon, "
                  f"{study.N_BOOT:,} draws; seed 0 is the published value) recomputed with seeds {', '.join(str(s) for s in SPREAD_SEEDS)}; the spread is the largest "
                  "minus the smallest value of that bound, in pp a year. Fixed encoding.\n")
        md.append("| world | product | horizon | mean lo | mean hi | median lo | median hi | largest |\n|---|---|---|---|---|---|---|---|")
        for r in sorted(spreads, key=lambda r: (r["world"], r["product"], r["horizon_years"])):
            md.append(f"| {r['world']} | {r['product']} | {r['horizon_years']}y | {r['mean_lo_spread'] * 100:.3f} | {r['mean_hi_spread'] * 100:.3f} | "
                      f"{r['median_lo_spread'] * 100:.3f} | {r['median_hi_spread'] * 100:.3f} | {r['max_spread'] * 100:.3f} |")
        md.append(f"\nLargest movement: {spread_summary['max_spread'] * 100:.3f} pp ({spread_summary['max_spread_row']}); largest at ten years "
                  f"{spread_summary['max_spread_10y'] * 100:.3f} pp; largest for any mean bound {spread_summary['max_mean_spread'] * 100:.3f} pp.\n")
    md.append(f"\nWall time {R['meta']['wall_seconds']:.1f} s.\n")
    (OUT / "coverage_sim.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:4]))
    for r in sorted(iid, key=lambda r: (r["world"], r["horizon_years"])):
        print(f"{r['world']} {r['horizon_years']:2d}y n={r['n']} k={r['k']}: bb mean {r['coverage_bb_mean']:.3f} median {r['coverage_bb_median']:.3f} "
              f"pooled {r['coverage_pooled']:.3f} se ratio {r['se_ratio_bb']:.2f} t needed {r['t_needed_pooled']:.2f} vs {r['t_used_pooled']:.2f}")
    print(f"mechanism k={mech['k']}: se ratio {mech['se_ratio_bb']:.2f}, bb mean coverage {mech['coverage_bb_mean']:.3f}")
    for m in matched:
        print(f"matched {m['world']} {m['product']} {m['horizon_years']}y: measured acf {m['measured_acf_h']:+.2f} -> case {m['regime']} acf {m['simulated_acf_h']:+.2f} pooled coverage {m['coverage_pooled']:.3f}")
    print(f"wrote {OUT / 'coverage_sim.json'} and coverage_sim.md in {R['meta']['wall_seconds']:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
