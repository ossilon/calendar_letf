"""B14: the compounding decomposition. Why does a calendar fund beat or trail its daily twin? Volatility drag against
enhanced compounding, measured.

    py scripts\\run_compounding.py        (from calendar_letf/, with CALENDAR_LETF_DATA / _RATES set; under a minute)

The mechanism, to second order in the returns (BACKLOG C13): over any window the log gap of a calendar fund against its
daily twin at zero cost is
        log F_cal - log F_daily  ~  L (L - 1) / 2 x (SS_daily - SS_period)
SS_daily is the sum of squared DAILY index returns and SS_period the sum of squared returns over the fund's reset
periods (early resets included). With independent days the two are equal on average (ratio SS_period / SS_daily = 1).
When days reverse, the period moves are smaller than the daily ones add up to (ratio < 1) and the calendar fund gains;
when days follow through (ratio > 1) the daily fund gains. The study measures:
  (a) per month-end window (1, 3, 5, 10 years), zero cost: the share of windows where each fund returned more than L x the
      index (enhanced compounding) and where it returned less (drag), and the calendar-vs-daily gap by tercile of the
      window's trend score (log index return squared over SS_daily: high = trend, low = chop). The trend score uses the
      whole window, so these splits describe a MECHANISM, not a timing rule;
  (b) the ratio SS_period / SS_daily per window, and how well the second-order formula reproduces the real log gap
      (slope, R^2, median error), at 2x and at 3x;
  (c) planted paths: a steady trend, a pure chop, and AR(1) days, where the answer is known;
  (d) the 3x designs of B1 (trigger at 0.70 / 3);
  (e) a worked example: the index ends +50% after one year at 10%, 20% and 40% annual volatility: what each design made.
Writes results/compounding.json and results/compounding.md.
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
import run_3x as r3  # noqa: E402
import run_sub2x as sub2x  # noqa: E402
from calendar_letf import kernel, metrics, periods, products, provenance, study  # noqa: E402

OUT = ROOT / "results"
CAPTION = "Data: TradingView (via local export), FRED. Modeled funds at zero cost (the mechanism alone). Not investment advice."
HORIZONS = (1, 3, 5, 10)
Z = study.ZERO_COSTS
EXAMPLE_VOLS = (0.10, 0.20, 0.40)
EXAMPLE_PATHS = 2000
EXAMPLE_GAIN = 0.50
SEED = 20261106
N_PLANT = 2520


def ss_windows(u, s, e, cuts):
    """Per window [s, e]: SS_daily (sum of squared daily simple returns) and SS_period (sum of squared returns over the
    stretches between consecutive cut rows inside the window, the window's own ends included)."""
    u = np.asarray(u, dtype=np.float64)
    r = u[1:] / u[:-1] - 1.0
    c = np.concatenate(([0.0], np.cumsum(r * r)))
    cut_rows = np.flatnonzero(cuts)
    ssd = c[e] - c[s]
    ssp = np.empty(len(s))
    for i, (a, b) in enumerate(zip(s, e)):
        inner = cut_rows[(cut_rows > a) & (cut_rows < b)]
        bounds = np.concatenate(([a], inner, [b]))
        R = u[bounds[1:]] / u[bounds[:-1]] - 1.0
        ssp[i] = float(np.sum(R * R))
    return ssd, ssp


def fit_line(x, y):
    """Slope and R^2 of y on x through the origin (the formula predicts y = x), and the median absolute error."""
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    slope = float(np.dot(x, y) / np.dot(x, x))
    ss_res = float(np.sum((y - x) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return dict(n=int(ok.sum()), slope=slope, r2_identity=1.0 - ss_res / ss_tot if ss_tot > 0 else None,
                median_abs_error=float(np.median(np.abs(y - x))))


def window_rows(name, w, specs, twin_of_L):
    """(a) and (b) for one world: every calendar design in `specs` against the daily twin at its L, zero cost."""
    out = []
    for p in specs:
        L = p.L
        enc = study.encoding_at(Z, L)
        W = r3.world_with(w, [p])
        nav = W.nav(p.name, enc)
        tw = W.nav(W.twin_name(p.name), enc)
        cuts = periods.period_end_flags(w.dates, p.reset).copy()
        for d in nav.attrs["early_resets"]:
            cuts[w.dates.get_loc(pd.Timestamp(d))] = True
        for hy in HORIZONS:
            s, e = w.month_pairs(12 * hy)
            I = w.u_arr[e] / w.u_arr[s]
            Fc = nav.to_numpy()[e] / nav.to_numpy()[s]
            Fd = tw.to_numpy()[e] / tw.to_numpy()[s]
            ok = (Fc > 0) & (Fd > 0)
            gap = np.where(ok, np.log(np.where(ok, Fc, 1.0)) - np.log(np.where(ok, Fd, 1.0)), np.nan)
            ssd, ssp = ss_windows(w.u_arr, s, e, cuts)
            pred = L * (L - 1.0) / 2.0 * (ssd - ssp)
            trend = np.log(I) ** 2 / ssd
            q1, q2 = np.quantile(trend, [1 / 3, 2 / 3])
            tt = np.digitize(trend, [q1, q2])
            by_trend = []
            for k, lab in enumerate(("chop", "middle", "trend")):
                m = tt == k
                by_trend.append(dict(tercile=lab, n=int(m.sum()), gap_median=float(np.nanmedian(gap[m])),
                                     ratio_median=float(np.median(ssp[m] / ssd[m])),
                                     cal_enhanced=float(np.mean((Fc[m] - 1.0) > L * (I[m] - 1.0))),
                                     daily_enhanced=float(np.mean((Fd[m] - 1.0) > L * (I[m] - 1.0)))))
            out.append(dict(product=p.name, reset=p.reset, L=L, horizon_years=hy, n=int(len(s)),
                            ratio_median=float(np.median(ssp / ssd)), share_ratio_below_1=float(np.mean(ssp < ssd)),
                            gap_median=float(np.nanmedian(gap)),
                            cal_enhanced=float(np.mean((Fc - 1.0) > L * (I - 1.0))),
                            daily_enhanced=float(np.mean((Fd - 1.0) > L * (I - 1.0))),
                            formula=fit_line(pred, gap), by_trend=by_trend))
    return out


# ---------------------------------------------------------------- (c) planted paths and (e) the worked example
def run_on(levels, reset, L):
    ix = pd.bdate_range("2000-01-03", periods=len(levels))
    u = pd.Series(levels, index=ix)
    if reset == "daily":
        return kernel.daily_reset_series(u, 0.0, L=L, spread_per_nav=0.0, fee=0.0).iloc[-1]
    return kernel.periodic_reset_series(u, 0.0, reset=reset, L=L, spread_per_nav=0.0, fee=0.0, early_drop=None).iloc[-1]


def planted():
    """Known-answer paths, 2x, zero cost, no trigger: the return of the index and of each design."""
    n = N_PLANT
    t = np.arange(n + 1)
    paths = {
        "trend +0.05% a day": 100.0 * 1.0005 ** t,
        "chop +-1% every other day": 100.0 * np.cumprod(np.concatenate(([1.0], np.where(t[1:] % 2 == 1, 1.01, 1 / 1.01)))),
    }
    rng = np.random.default_rng(SEED)
    for phi in (-0.2, 0.2):
        z = rng.standard_normal(n)
        x = np.empty(n)
        x[0] = z[0]
        for i in range(1, n):
            x[i] = phi * x[i - 1] + math.sqrt(1 - phi * phi) * z[i]
        paths[f"AR(1) days, phi {phi:+.1f}"] = 100.0 * np.exp(np.concatenate(([0.0], np.cumsum(0.0003 + 0.01 * x))))
    out = []
    for lab, lv in paths.items():
        row = dict(path=lab, index=float(lv[-1] / lv[0] - 1.0))
        for reset in ("daily", "weekly", "monthly", "quarterly"):
            row[reset] = float(run_on(lv, reset, 2.0) - 1.0)
        out.append(row)
    return out


def worked_example():
    """The index ends exactly +50% after one year (252 days); daily log moves with annual volatility v, bridged so they
    sum to log 1.5. Median and 5th / 95th percentile return of each design at 2x and 3x over EXAMPLE_PATHS paths."""
    rng = np.random.default_rng(SEED + 1)
    n = 252
    out = []
    for v in EXAMPLE_VOLS:
        res = {(L, r): [] for L in (2.0, 3.0) for r in ("daily", "weekly", "monthly", "quarterly")}
        for _ in range(EXAMPLE_PATHS):
            x = rng.normal(0.0, v / math.sqrt(252), n)
            x = x - x.mean() + math.log(1.0 + EXAMPLE_GAIN) / n
            lv = 100.0 * np.exp(np.concatenate(([0.0], np.cumsum(x))))
            for (L, r) in res:
                res[(L, r)].append(run_on(lv, r, L) - 1.0)
        for (L, r), vals in res.items():
            a = np.array(vals)
            out.append(dict(vol=v, L=L, reset=r, median=float(np.median(a)), p5=float(np.percentile(a, 5)), p95=float(np.percentile(a, 95)),
                            wiped=float(np.mean(a <= -1.0 + 1e-12)), L_times_index=L * EXAMPLE_GAIN))
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
          "Zero cost throughout: the mechanism alone. Gap = log fund minus log daily twin (a year's figure is the gap over the window, "
          "not per year). Ratio = SS_period / SS_daily (below 1: the days reverse inside the periods). Trend score = (log index "
          "return)^2 / SS_daily over the WHOLE window: a mechanism, not a timing rule.\n"]
    for name, W in res["worlds"].items():
        md.append(f"## {sub2x.UNDERLYING_NAME[name]}\n")
        md.append(md_table(["design", "L", "years", "windows", "ratio median", "ratio < 1", "gap median", "calendar > L x index", "daily > L x index",
                            "formula slope", "R2 (y = x)", "median error", "gap: chop / middle / trend"],
                           [[r["product"], f"{r['L']:g}", r["horizon_years"], r["n"], f"{r['ratio_median']:.3f}", f"{r['share_ratio_below_1']:.0%}",
                             f"{r['gap_median']:+.4f}", f"{r['cal_enhanced']:.0%}", f"{r['daily_enhanced']:.0%}", f"{r['formula']['slope']:.3f}",
                             "n/a" if r["formula"]["r2_identity"] is None else f"{r['formula']['r2_identity']:.3f}", f"{r['formula']['median_abs_error']:.4f}",
                             " / ".join(f"{b['gap_median']:+.4f}" for b in r["by_trend"])] for r in W["windows"]]))
    md.append("## Planted paths (2x, zero cost, no trigger; ten years)\n")
    md.append(md_table(["path", "index", "daily", "weekly", "monthly", "quarterly"],
                       [[r["path"], pc(r["index"]), pc(r["daily"]), pc(r["weekly"]), pc(r["monthly"]), pc(r["quarterly"])] for r in res["planted"]]))
    md.append(f"## Worked example: the index ends +{EXAMPLE_GAIN:.0%} after one year ({EXAMPLE_PATHS} paths, zero cost, no trigger)\n")
    md.append(md_table(["annual vol", "L", "reset", "median return", "p5 / p95", "wiped", "L x index"],
                       [[pc(r["vol"], 0), f"{r['L']:g}", r["reset"], pc(r["median"]), f"{pc(r['p5'])} / {pc(r['p95'])}", f"{r['wiped']:.1%}",
                         pc(r["L_times_index"], 0)] for r in res["worked_example"]]))
    return "\n".join(md)


def main():
    wall0 = time.perf_counter()
    print("=" * 100 + "\nB14: the compounding decomposition (zero cost, MODELED funds)")
    worlds, wprov = sub2x.build_worlds()
    inputs = study.inputs_for(worlds, wprov)
    banner = (provenance.banner_lines(inputs) + [ln for w in worlds.values() for ln in study.conventions_lines(w)]
              + [f"Zero cost. 2x: the passive study's designs (35% trigger); 3x: B1's designs (trigger 0.70 / 3). Study end {sub2x.STUDY_END}."])
    print("\n".join(banner))
    res = dict(meta=dict(title="B14: volatility drag and enhanced compounding, calendar against daily", run_date=str(pd.Timestamp.today().date()),
                         caption=CAPTION, study_end=sub2x.STUDY_END, horizons=list(HORIZONS), example_vols=list(EXAMPLE_VOLS),
                         example_paths=EXAMPLE_PATHS, example_gain=EXAMPLE_GAIN, seed=SEED, underlyings={n: wprov[n] for n in wprov},
                         inputs=inputs, banner=banner, code=provenance.code_fingerprint(__file__)), worlds={})
    for name, w in worlds.items():
        specs = [products.PRODUCTS[p] for p in study.PRODUCT_NAMES[name]] + [r3.design3(name, r, "scaled") for r in sub2x.CAL_RESETS]
        res["worlds"][name] = dict(windows=window_rows(name, w, specs, None))
        print(f"  {name}: {time.perf_counter() - wall0:.0f} s")
    res["planted"] = planted()
    res["worked_example"] = worked_example()
    rows = [r for W in res["worlds"].values() for r in W["windows"]]
    res["summary"] = dict(
        slope_min_2x_10y=min(r["formula"]["slope"] for r in rows if r["L"] == 2.0 and r["horizon_years"] == 10),
        slope_max_2x_10y=max(r["formula"]["slope"] for r in rows if r["L"] == 2.0 and r["horizon_years"] == 10),
        r2_min_2x_weekly_monthly_10y=min(r["formula"]["r2_identity"] for r in rows if r["L"] == 2.0 and r["horizon_years"] == 10 and r["reset"] != "quarterly"))
    res["meta"]["timing"] = dict(total_wall_seconds=time.perf_counter() - wall0)
    (OUT / "compounding.json").write_text(json.dumps(provenance.json_safe(res), indent=1, allow_nan=False) + "\n", encoding="utf-8")
    (OUT / "compounding.md").write_text(markdown(res), encoding="utf-8")
    print(f"wrote results/compounding.json and results/compounding.md in {time.perf_counter() - wall0:.0f} s")


if __name__ == "__main__":
    main()
