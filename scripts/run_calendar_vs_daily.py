"""Step 3: the passive study. Does a 2x fund that resets weekly / monthly / quarterly lose less to volatility than a
2x fund that resets daily, on the same index with the same costs?

    py scripts\\run_calendar_vs_daily.py        (from calendar_letf/, with CALENDAR_LETF_DATA / _RATES set)

Order of work (each section is one function in calendar_letf/study.py):
  provenance banners first -> per underlying: equity curves, full-history risk table, multi-start summary, decade
  table (C2), horizon curve (C8), rolling 10-year windows (C1), early resets and wipeouts (C6), the buy-once margin
  benchmark (C7 / B3), key periods, sensitivities -> timing.
Writes results/calendar_vs_daily.md and .json, results/*.png, and per-start tables in results/raw/ (git-ignored:
only aggregates are published, because a daily series can be reversed into index prices).
Every fund NAV is computed once per (product, encoding, early-reset mode) and every multi-start number is a ratio
of that series. All series are MODELED or synthetic; none is a live fund (products.MODELED_NOTE).
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
from calendar_letf import products, provenance, stats, study  # noqa: E402

OUT = ROOT / "results"
RAW = OUT / "raw"
CAPTION = "Data: TradingView (via local export), FRED. Modeled / synthetic series, not live funds. Not investment advice."
ENC = study.ENCODINGS
UNDERLYING_NAME = {"SPX": "S&P 500", "NDX": "Nasdaq-100"}
C1_SCRATCH = "BACKLOG C1 preliminary scratch (pre-audit, step-1 kernels, S&P 500 monthly vs daily): +1.13 pp median, 321/321 windows"
def coverage_note():
    """The simulated coverage of the interval conventions, read from results/coverage_sim.json (one source, written by
    scripts/run_coverage_sim.py) so the same numbers appear everywhere; a pointer when that file is absent."""
    path = OUT / "coverage_sim.json"
    if not path.exists():
        return ("Block-bootstrap SE biased low with block = window length: coverage in results/coverage_sim.md "
                "(py scripts\\run_coverage_sim.py); see ASSUMPTIONS section 7.")
    s = json.loads(path.read_text(encoding="utf-8"))["summary"]
    return (f"Block-bootstrap SE biased low with block = window length: simulated coverage of its 95% intervals "
            f"{s['bb_mean_min']:.2f}-{s['bb_mean_max']:.2f} (mean) and {s['bb_median_min']:.2f}-{s['bb_median_max']:.2f} (median) at the "
            f"published configurations, against {s['pooled_min']:.2f}-{s['pooled_max']:.2f} for the phase-pooled interval under independent "
            f"months (results/coverage_sim.md, which also states the limit under persistent regimes; ASSUMPTIONS section 7).")


BB_NOTE = coverage_note()


def coverage_10y_text():
    """The simulated coverage of the phase-pooled interval at the 10-year configurations, read from
    results/coverage_sim.json (iid rows), as 'a-b' text; a pointer when that file is absent."""
    path = OUT / "coverage_sim.json"
    if not path.exists():
        return "in results/coverage_sim.md"
    iid = [r for r in json.loads(path.read_text(encoding="utf-8"))["iid"] if r["horizon_years"] == 10]
    lo, hi = min(r["coverage_pooled"] for r in iid), max(r["coverage_pooled"] for r in iid)
    return f"{lo:.2f}-{hi:.2f}"


def encoding_gap_text(R):
    """'fixed minus rate CAGR +1.2 to +1.3 pp a year in 1966-82 and -1.6 to -1.4 in 2009-15' over every product of both underlyings."""
    parts = []
    for label in ("1966-82", "2009-15"):
        vals = [v for W in R["worlds"].values() for v in W.get("encoding_gap", {}).get(label, {}).values() if v is not None and np.isfinite(v)]
        if vals:
            parts.append(f"{min(vals) * 100:+.1f} to {max(vals) * 100:+.1f} pp a year in {label}")
    return "fixed minus rate CAGR " + " and ".join(parts) if parts else "see the encoding_gap table"


def fill_range_text(R):
    """'between -16% and +15%' style text for the fill rule's effect on fund value over every episode of both underlyings
    (study.fill_effects: the change in fund value under the close or next-close fill relative to the level fill; both
    signs occur, because a later fill resets the leverage at a different level before the rebound)."""
    vals = []
    for W in R["worlds"].values():
        fr = W.get("fill_effect_range", {})
        for k in ("min_pct", "max_pct"):
            v = fr.get(k)
            if v is not None and np.isfinite(v):
                vals.append(v)
    if not vals:
        return "by an unmeasured share"
    return f"by between {min(vals):+.0%} and {max(vals):+.0%}"
COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]          # categorical slots 1-3 of the dataviz reference palette
INK, MUTED = "#0b0b0b", "#52514e"


# ---------------------------------------------------------------- formatting helpers
def pp(x, d=2):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:+.{d}f}"


def pc(x, d=1):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.{d}f}%"


def ci(lo, hi, d=2):
    """A 95% interval in pp: [+0.12, +0.45]; n/a when it does not exist."""
    return "n/a" if lo is None or hi is None or not (np.isfinite(lo) and np.isfinite(hi)) else f"[{lo * 100:+.{d}f}, {hi * 100:+.{d}f}]"


def flag(noisy):
    """The reading of an interval: 'noisy' = it covers zero, so one history cannot tell the sign."""
    return "NOISY" if noisy else "clear"


def zs(z):
    """A z value with a star when it passes the 5% two-sided bar."""
    return "n/a" if z is None or not np.isfinite(z) else f"{z:+.1f}{'*' if abs(z) > 1.96 else ''}"


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
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o.date())
    return o


def fee_text(world):
    return "; ".join(f"{p.name} {p.fee:.2%} [{p.costs.fee_status}]" for p in world.specs) + "; daily twins copy their fund's fee"


def prov(world, wprov, enc, mode, window):
    """The provenance line printed above every table."""
    return (f"*Underlying: {UNDERLYING_NAME[world.name]} total return {wprov['first']} to {wprov['last']} (early-reset trigger: {wprov['trigger_text']}). "
            f"Window: {window}. Encoding: {enc.describe()}. Early-reset mode: {mode}. Fees: {fee_text(world)}. "
            f"Spread and rate turns: ASSUMED (fitted on 2024-26). All series synthetic; the live funds are modeled, and the other "
            f"calendar-reset products are MODELED designs ({products.MODELED_NOTE}).*\n")


def label(world, p):
    return f"{p.name} ({p.reset})"


# ---------------------------------------------------------------- charts
def plot_equity(world, wprov, path):
    enc = ENC[study.BASE_ENCODING]
    fig, ax = plt.subplots(figsize=(10, 6), dpi=130)
    ax.plot((world.u / world.u.iloc[0]).index, (world.u / world.u.iloc[0]).values, color=MUTED, lw=1.4, label="1x total return (underlying)")
    twins = {p.name: world.nav(world.twin_name(p.name), enc) for p in world.specs}
    ref = next(iter(twins.values()))
    same = all(np.max(np.abs(t.values / ref.values - 1)) < 0.03 for t in twins.values())
    for i, p in enumerate(world.specs):
        ax.plot(world.dates, world.nav(p.name, enc).values, color=COLORS[i], lw=1.4, label=f"{p.name}: 2x {p.reset}")
        if not same:
            ax.plot(world.dates, twins[p.name].values, color=COLORS[i], lw=1.0, ls="--", label=f"daily twin of {p.name}")
    if same:
        ax.plot(world.dates, ref.values, color=INK, lw=1.2, ls="--", label="2x daily twins (same costs; the three lines overlap within 3%)")
    ax.set_yscale("log")
    ax.set_ylabel("growth of 1 (log scale)", color=MUTED)
    ax.set_title(f"{UNDERLYING_NAME[world.name]}: 2x calendar-reset funds vs daily twin  [MODELED]\n"
                 f"{wprov['first']} to {wprov['last']}; encoding: {enc.label}; early-reset mode: level", fontsize=10, color=INK, loc="left")
    ax.grid(True, which="major", color="#d9d8d3", lw=0.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.text(0.01, 0.005, CAPTION, fontsize=7, color=MUTED)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path)
    plt.close(fig)


def plot_horizon(curves, path):
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), dpi=130, sharex=True)
    for r, name in enumerate(("SPX", "NDX")):
        for c, ename in enumerate(("fixed", "rate")):
            ax = axes[r][c]
            rows = curves[name][ename]
            prods = list(dict.fromkeys(x["product"] for x in rows))
            for i, p in enumerate(prods):
                pr = [x for x in rows if x["product"] == p]
                ax.plot([x["months"] for x in pr], [x["gap_median"] * 100 for x in pr], marker="o", ms=4, lw=1.4, color=COLORS[i],
                        label=f"{p} ({pr[0]['reset']})")
            ax.axhline(0, color=MUTED, lw=0.8)
            ax.set_xscale("log")
            ax.set_xticks(study.CURVE_MONTHS)
            ax.set_xticklabels([str(m) for m in study.CURVE_MONTHS])
            ax.set_title(f"{UNDERLYING_NAME[name]}, encoding: {ENC[ename].label}", fontsize=9, color=INK, loc="left")
            ax.grid(True, color="#d9d8d3", lw=0.5)
            ax.spines[["top", "right"]].set_visible(False)
            ax.legend(frameon=False, fontsize=8)
            if r == 1:
                ax.set_xlabel("holding period (months, month-end starts)", color=MUTED)
            if c == 0:
                ax.set_ylabel("median reset gap (pp a year)", color=MUTED)
    fig.suptitle("Calendar fund minus daily twin by holding period [MODELED; level mode]", fontsize=10, color=INK, x=0.01, ha="left")
    fig.text(0.01, 0.005, CAPTION, fontsize=7, color=MUTED)
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    fig.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------- the run
def main():
    wall0 = time.perf_counter()
    OUT.mkdir(exist_ok=True)
    RAW.mkdir(exist_ok=True)
    R = {"meta": {}, "worlds": {}}
    md = []

    # ---- provenance banners first
    print("=" * 100 + "\nSTEP 3: calendar-reset vs daily-reset 2x funds, passive study (all series MODELED / synthetic)")
    worlds, wprov = {}, {}
    t_load = time.perf_counter()
    for name in ("SPX", "NDX"):
        # BASE CASE (R2 step 3, R1 E4): the prospectus trigger watches the ETF's price, intraday. From the day the ETF exists
        # the trigger is the ETF's own price and daily low; before that it is the index price (close and daily low where the
        # export has a real low). The index-only, close-only run of the v1 results stays as a row of the trigger-basis table.
        worlds[name], wprov[name] = study.build_world(name, intraday_trigger=True, trigger_basis="etf", end=study.V010_END[name])
        print("\n" + wprov[name]["banner"])
        print(f"rate: {wprov[name]['rate']}")
        tr = wprov[name]["trigger"]
        print(f"TRIGGER BASE CASE: {wprov[name]['trigger_text']}. ETF low prints rejected as bad (more than {study.BAD_LOW_TOL:.0%} below the "
              f"index's own low-to-close gap): {[d['date'] for d in tr['bad_low_days']] or 'none'}. Rows carried by the index move: "
              f"{len(tr['rows_carried_inside_etf_range']) + tr['rows_carried_after_etf_end']['count']}. Long-history case (index price, close only) = the v1 results: see the trigger-basis table.")
        print(products.banner(*worlds[name].specs, *worlds[name].twins.values(),
                              overrides="spread_per_nav and the rate multiplier come from the cost encodings below, not from the registry"))
    load_s = time.perf_counter() - t_load
    # Provenance: every price and FRED file the worlds read (index price, total-return index, trigger ETF, DFF, TB3MS proxy).
    inputs = study.inputs_for(worlds, wprov)
    banner = provenance.banner_lines(inputs) + [ln for w in worlds.values() for ln in study.conventions_lines(w)] + [products.MODELED_NOTE]
    print("\nINPUTS AND CONVENTIONS:\n" + "\n".join(banner))
    print("\nCOST ENCODINGS (both ASSUMED, both shown everywhere):")
    for e in list(study.ALL_ENCODINGS.values()):
        print("  " + e.describe() + f"  | {e.source}")
    print(f"Early-reset modes: base {study.BASE_MODE}; sensitivities close, next_close. Base encoding for single-encoding charts: {study.BASE_ENCODING}.")

    R["meta"] = dict(
        title="Calendar-reset vs daily-reset 2x funds: passive study (step 3)", run_date=str(pd.Timestamp.today().date()),
        base_encoding=study.BASE_ENCODING, base_mode=study.BASE_MODE, modes=list(study.MODES), horizons_years=list(study.HORIZONS_YEARS),
        curve_months=list(study.CURVE_MONTHS), rolling_from=study.ROLLING_FROM,
        encodings={k: dict(spread_per_nav=e.spread_per_nav, rate_turns=e.rate_turns, fee=e.fee, status=e.status, source=e.source, label=e.label)
                   for k, e in study.ALL_ENCODINGS.items()},
        key_periods=[dict(label=a, first_day=b, last_day=c) for a, b, c in study.KEY_PERIODS],
        underlyings={n: {k: v for k, v in wprov[n].items()} for n in wprov}, caption=CAPTION, c1_scratch=C1_SCRATCH,
        inputs=inputs, banner=banner, code=provenance.code_fingerprint(__file__),
        trigger_base_case="ETF price and daily low from the ETF's first bar (AMEX:SPY 1993-01-29, NASDAQ:QQQ 1999-03-10), index price before",
        statistics=dict(
            headline_interval="HEADLINE (R2 step 10): non-overlapping windows of each start phase pooled (step = horizon in months): mean +/- t(df, 0.975) x SE, SE^2 = mean of s_p^2 / k_p, df = smallest k_p - 1; columns indep_*; simulated coverage at every published configuration, and its limit under persistent regimes, in results/coverage_sim.md",
            interval=f"SECONDARY: mean +/- t(k-1, 0.975) x block-bootstrap SE; circular blocks; block = horizon in months; k = n // block; {study.N_BOOT:,} resamples; seed 0; columns bb_* (and gap_*, same numbers). {BB_NOTE}",
            median_interval="SECONDARY: median of the window gaps +/- t(k-1, 0.975) x block-bootstrap SE of the median; same blocks, resamples and seed as the mean interval; columns bb_median_* (and median_*, same numbers); a reasonable device, not exact on skewed data; its coverage sits next to the mean's in results/coverage_sim.md",
            bootstrap_resamples=study.N_BOOT,
            independent_interval="same as headline_interval (kept under its earlier name)",
            noisy="HEADLINE flag: the phase-pooled interval covers zero; noisy_bb_mean / noisy_bb_median: the block-bootstrap interval covers zero (secondary)",
            variance_ratio="Lo-MacKinlay (1988) unbiased VR(q), heteroskedasticity-robust z*(q); on simple daily returns of the total-return series",
            prediction="Bessembinder second order: -2 x [C(T,2) mu^2 + T sigma^2 / 2 (VR_T - 1)] per period, T = 5 / 21 / 63 days"))

    # ---- compute everything
    for name, w in worlds.items():
        t_w = time.perf_counter()
        W = R["worlds"][name] = dict(multi_start={}, decades={}, horizon_curve={}, rolling_10y={}, early_events=[], margin={}, key_periods=[],
                                     sensitivity=[], full_history={}, products=[p.name for p in w.specs])
        for en in ("fixed", "rate"):
            enc = ENC[en]
            rows, raw = study.multi_start(w, enc)
            W["multi_start"][en] = rows
            raw.to_csv(RAW / f"multi_start_{name}_{en}.csv", index=False)
            W["decades"][en] = study.decade_table(w, enc)
            W["horizon_curve"][en] = study.horizon_curve(w, enc)
            W["margin"][en] = study.margin_comparison(w, enc)
            W["key_periods"].append(dict(encoding=en, rows=study.key_periods(w, enc)))
            W["full_history"][en] = study.full_history_stats(w, enc)
            for mode in study.MODES:
                W["early_events"] += study.early_events(w, enc, mode)
        for en in ("fixed", "rate", "rate_only", "zero"):
            W["rolling_10y"][en] = study.rolling_10y(w, study.ALL_ENCODINGS[en])
        W["sensitivity"] = study.sensitivity_table(w)
        W["cost_span_10y_median"] = study.cost_span(W["sensitivity"])          # per product: span over the six cost cases (level fill)
        W["encoding_gap"] = study.encoding_gap(w)                              # fixed minus rate CAGR per product, 1966-82 / 2009-15 / full
        W["fill_effect_range"] = study.fill_effect_range(W["early_events"])    # fill rule's effect on fund value per episode, min / max
        W["episode_split"] = {en: study.episode_split(w, ENC[en]) for en in ("fixed", "rate")}
        W["independent"] = {en: study.independent_windows(w, ENC[en]) for en in ("fixed", "rate")}
        W["returns_full_sample"] = study.full_sample_returns(w)
        W["prediction_summary"] = {en: [study.prediction_summary(W["decades"][en], p.name) for p in w.specs] for en in ("fixed", "rate")}
        W["trigger_basis"] = study.trigger_basis_table(w)
        plot_equity(w, wprov[name], OUT / f"equity_{name}.png")
        print(f"{name}: computed in {time.perf_counter() - t_w:.2f} s; kernel runs {w.kernel_runs} in {w.kernel_seconds:.2f} s")
    plot_horizon({n: R["worlds"][n]["horizon_curve"] for n in worlds}, OUT / "horizon_curve.png")

    # ---- markdown
    md.append("# Calendar-reset vs daily-reset 2x funds: the passive study (step 3)\n")
    md.append(f"Run {R['meta']['run_date']}. Script `scripts/run_calendar_vs_daily.py`; numbers in `calendar_vs_daily.json`; per-start tables in "
              "`results/raw/` (git-ignored). **Every series here is synthetic. SPYQ, MQQQ and QQQP are modeled, not the live funds; the S&P 500 monthly, S&P 500 weekly and "
              "Nasdaq-100 weekly products are modeled designs (funds of those designs traded 2024-08-30 to 2025-02-28 and were liquidated; none trades "
              "today). Research tooling, not investment advice.**\n")
    md.append("## Inputs and conventions\n")
    md.append("```text\n" + "\n".join(banner) + "\n```\n")
    md.append("## Method in brief\n")
    md.append("- **Question.** Does a 2x fund that resets weekly / monthly / quarterly lose less to volatility than a 2x fund that resets daily, "
              "on the same index with the same fee, rate and spread? **Reset gap** = calendar fund CAGR minus its daily twin's CAGR over the "
              "same window, in percentage points a year (pp). Positive = the calendar fund did better.")
    md.append("- **Underlyings.** S&P 500 and Nasdaq-100 TOTAL RETURN (constructed before the published total-return indexes begin; see the "
              "banners). Reference rate: effective fed funds (DFF), lagged one row; TB3MS proxy before 1954-07-01.")
    md.append("- **Early-reset trigger (base case, R2 step 3).** The prospectus trigger watches the price of the ETF (SPY, QQQ) during the day. "
              "The base case therefore tests the ETF's daily LOW from the ETF's first bar (SPY 1993-01-29, QQQ 1999-03-10) and the index "
              "price (daily low where the export has a real one, else the close) before that; the two series are scaled to be continuous. "
              + "; ".join(f"{UNDERLYING_NAME[n]}: ETF low prints rejected as bad: {', '.join(d['date'] for d in wprov[n]['trigger']['bad_low_days']) or 'none'}"
                          for n in worlds)
              + ". The v1 results used the index price close only (the long-history case, 1950 on); it is one row of table 9b, next to the drop "
              "sensitivity (34 / 35 / 36%) and the ETF-versus-index comparison. Fill rule: at the trigger level (mode `level`).")
    md.append("- **Cost encodings (both ASSUMED, always side by side).** The 2024-26 fit leaves a residual cost beyond the filed one "
              "(FINDINGS F3-F5). It is written into history two ways:\n")
    md.append(md_table(["encoding", "spread per NAV", "rate turns", "status", "sensitivities"],
                       [["fixed", "2.6% a year", "1.0 x DFF", "ASSUMED", "spread 1.4% / 3.5%"],
                        ["rate", "1.4% a year", "1.3 x DFF", "ASSUMED", "rate turns 1.0 / 1.5"]]))
    md.append("- **Early reset.** Base mode `level` (resets at exactly -35% of the trigger); `close` and `next_close` are sensitivities "
              f"(table 9). Fees: {'; '.join(fee_text(w) for w in worlds.values())}.")
    md.append("- **Multi-start.** Each NAV is computed once over the full history; a result for \"buy at month-end s, hold h\" is nav[e]/nav[s]. "
              "A month-end start is MID-PERIOD for a quarterly or weekly fund (a real investor's situation): the fund's leverage on the day of "
              "purchase is whatever it has floated to since its last reset. Starts: every month-end with a full horizon ahead.")
    md.append("- **Margin benchmark.** A 2x position bought once on margin, never reset (`periods.NEVER`), financed at the same rate and spread "
              "and paying the same fee, finished when the index falls 50% from the purchase. A real margin account is called well before "
              "equity hits zero, so the benchmark is OPTIMISTIC. It is bought at 2.0x on the start date, whereas a calendar fund bought "
              "mid-period has floated leverage.\n")

    # headline
    md.append("## Headline: the 10-year median reset gap (all month-end starts, level mode)\n")
    md.append("Each row: the median gap in pp a year (the headline statistic), the share of starts the calendar fund wins, and the mean gap with its "
              "**headline 95% interval, the phase-pooled one**: the non-overlapping 10-year windows of each of the 120 start phases are pooled, "
              "interval = mean +/- t(df) x SE with df = the fewest windows in a phase - 1 (shown per row). **NOISY** = that interval covers zero, "
              "so this one history cannot tell the sign; **clear** = it excludes zero. Only this interval defines \"clear\". "
              f"The block-bootstrap intervals (block = 120 months, t(k-1) x SE, {study.N_BOOT:,} resamples) of the median and of the mean are "
              "SECONDARY columns. " + BB_NOTE + " The median interval is for the median of the window gaps; the bootstrap SE of a median is a "
              "reasonable device, not an exact one. Detail: section \"What one history can tell\".\n")
    hl_rows = []
    for name, w in worlds.items():
        for p in w.specs:
            for en in ("fixed", "rate"):
                r = next(x for x in R["worlds"][name]["multi_start"][en] if x["product"] == p.name and x["horizon_years"] == 10)
                hl_rows.append([UNDERLYING_NAME[name], label(w, p), en, pp(r["gap_median"]), pc(r["calendar_wins"], 0),
                                f"{pp(r['indep_mean'])} {ci(r['indep_lo'], r['indep_hi'])} (df {r['indep_df']})", flag(r["noisy"]),
                                f"{pp(r['gap_median'])} {ci(r['bb_median_lo'], r['bb_median_hi'])}", flag(r["noisy_bb_median"]),
                                f"{pp(r['bb_mean'])} {ci(r['bb_lo'], r['bb_hi'])}", flag(r["noisy_bb_mean"]), str(r["n_starts"])])
    md.append(md_table(["underlying", "product", "encoding", "median gap pp", "wins",
                        "HEADLINE: mean, phase-pooled [95% interval]", "reading",
                        "secondary: median, block bootstrap [95% interval]", "reading (bb)",
                        "secondary: mean, block bootstrap [95% interval]", "reading (bb)", "windows"], hl_rows))
    md.append("Provenance: as the multi-start tables below (section 2 of each underlying); underlying total return, level mode, both ASSUMED cost encodings.\n")

    # what one history can tell (R2 step 3)
    md.append("## What one history can tell\n")
    md.append("Every headline above is one number from one history. Two intervals say how far it could move. (1) **HEADLINE: non-overlapping windows, "
              "pooled over start phases.** Every 120th start forms one set of independent windows; the 120 sets (phases) are pooled (SE^2 = average "
              "of each phase's s^2/k; df = smallest k - 1; interval = mean +/- t(df) x SE). It uses only independent windows and is wide because "
              f"there are 3-7 of them. Simulated coverage on gap series with the overlap of rolling 120-month windows is {coverage_10y_text()} "
              "at 10 years under independent months (results/coverage_sim.md). A headline is **NOISY** when this interval covers zero: the data cannot separate it from no effect; \"clear\" "
              "is defined on this interval only. (2) **SECONDARY: block bootstrap over all month-end starts.** Windows that start a month apart "
              "share all but one month, so the bootstrap resamples blocks of consecutive starts, one block = the horizon in months; interval = "
              f"mean +/- t(k-1) x SE, k = starts // block, {study.N_BOOT:,} resamples, seed 0. " + BB_NOTE + " The median has its own block-bootstrap "
              "interval (same blocks, same resamples; median +/- t(k-1) x SE of the median); the bootstrap SE of a median is a reasonable device, not "
              "an exact one on skewed data. Median and mean sit side by side because a median comparison favors the less convex structure (the "
              "calendar fund).\n")
    rows_t = []
    for name, w in worlds.items():
        for p in w.specs:
            for en in ("fixed", "rate"):
                r = next(x for x in R["worlds"][name]["multi_start"][en] if x["product"] == p.name and x["horizon_years"] == 10)
                rows_t.append([UNDERLYING_NAME[name], label(w, p), en, pp(r["gap_median"]), pp(r["gap_mean"]),
                               pp(r["indep_se"]), f"{r['indep_df']} (t = {stats.t975(max(r['indep_df'], 1)):.2f}; windows {r['indep_k_min']}-{r['indep_k_max']})",
                               ci(r["indep_lo"], r["indep_hi"]), flag(r["noisy"]), pc(r["indep_share_phases_excl_zero"], 0),
                               pp(r["bb_se"]), f"{r['bb_k']} (t = {stats.t975(max(r['bb_k'] - 1, 1)):.2f})", ci(r["bb_lo"], r["bb_hi"]), flag(r["noisy_bb_mean"]),
                               pp(r["bb_median_se"]), ci(r["bb_median_lo"], r["bb_median_hi"]), flag(r["noisy_bb_median"])])
    md.append(md_table(["underlying", "product", "encoding", "median pp", "mean pp",
                        "HEADLINE: phase-pooled SE of the mean", "df (t; windows per phase)", "95% interval of the mean", "reading", "phases whose own interval excludes 0",
                        "secondary: bootstrap SE of mean", "blocks k (t)", "95% interval of the mean (block bootstrap)", "reading (bb)",
                        "secondary: bootstrap SE of median", "95% interval of the median (block bootstrap)", "reading (bb)"], rows_t))
    n_noisy = {en: sum(1 for name in worlds for r in R["worlds"][name]["multi_start"][en] if r["horizon_years"] == 10 and r["noisy"]) for en in ("fixed", "rate")}
    n_noisy_bb = {en: sum(1 for name in worlds for r in R["worlds"][name]["multi_start"][en] if r["horizon_years"] == 10 and r["noisy_bb_mean"]) for en in ("fixed", "rate")}
    md.append(f"Ten-year headlines whose phase-pooled interval covers zero (NOISY): {n_noisy['fixed']} of 6 (fixed encoding), {n_noisy['rate']} of 6 (rate encoding). "
              f"For comparison, the secondary block-bootstrap interval of the mean covers zero in {n_noisy_bb['fixed']} of 6 (fixed) and {n_noisy_bb['rate']} of 6 (rate). "
              "Provenance: `multi_start` in `calendar_letf/study.py`; intervals from `calendar_letf/stats.py`; ASSUMPTIONS section 7 states the conventions.\n")

    for name, w in worlds.items():
        wp, W = wprov[name], R["worlds"][name]
        un = UNDERLYING_NAME[name]
        md.append(f"\n---\n\n# {un}\n")
        md.append("Underlying banner: `" + wp["banner"] + "`\n")
        md.append(f"Rate: {wp['rate']['source']}. Proxy rows (TB3MS, before 1954-07-01): {wp['rate']['proxy_rows']} "
                  f"({'until ' + wp['rate']['proxy_until'] if wp['rate']['proxy_until'] else 'none: DFF covers the whole sample'}); rule: {wp['rate']['proxy_rule']}. Last published DFF date {wp['rate']['rate_last_date']}; "
                  f"stale (forward-filled) rows: {wp['rate']['stale_rows']}.\n")

        # 1 equity curves + risk table
        md.append(f"## {un} 1. Full-history equity curves and risk statistics\n")
        md.append(f"![{un} equity curves](equity_{name}.png)\n")
        md.append("*Chart: fixed-spread encoding, level mode. " + CAPTION + "*\n")
        for en in ("fixed", "rate"):
            md.append(prov(w, wp, ENC[en], "level", f"full history {wp['first']} to {wp['last']}"))
            md.append(md_table(["series", "CAGR", "ann. vol", "max drawdown", "Calmar", "Sortino", "Ulcer index", "time under water", "longest recovery (trading days)", "growth of 1"],
                               [[r["series"], pc(r["cagr"]), pc(r["ann_vol"]), pc(r["max_drawdown"]), f"{r['calmar']:.2f}", f"{r['sortino']:.2f}",
                                 f"{r['ulcer_index']:.3f}", pc(r["time_under_water"], 0), r["longest_recovery_rows"], f"{r['terminal_wealth']:,.1f}"]
                                for r in W["full_history"][en]]))

        # 2 multi-start
        md.append(f"## {un} 2. Multi-start summary (every month-end start; horizons 1 / 3 / 5 / 10 years)\n")
        md.append("CAGR columns: median (10th to 90th percentile). Max drawdown: median over windows. Worst terminal: lowest growth of 1 over any window. "
                  "Gap = calendar CAGR minus twin CAGR (pp a year). A month-end start is mid-period for a quarterly or weekly fund.\n")
        for en in ("fixed", "rate"):
            md.append(f"**Encoding {en}.**\n")
            rows = W["multi_start"][en]
            md.append(prov(w, wp, ENC[en], "level", f"{rows[0]['first_start']} start to {rows[0]['last_start']} start, 1-10 year horizons"))
            md.append(md_table(["product", "years", "starts", "calendar CAGR", "cal. max DD", "cal. worst x", "twin CAGR", "twin max DD", "twin worst x", "gap pp (p10 to p90)", "calendar wins", "1x CAGR"],
                               [[f"{r['product']} ({r['reset']})", r["horizon_years"], r["n_starts"],
                                 f"{pc(r['cal_cagr_median'])} ({pc(r['cal_cagr_p10'], 0)} to {pc(r['cal_cagr_p90'], 0)})", pc(r["cal_maxdd_median"], 0), f"{r['cal_worst_terminal']:.2f}",
                                 f"{pc(r['twin_cagr_median'])} ({pc(r['twin_cagr_p10'], 0)} to {pc(r['twin_cagr_p90'], 0)})", pc(r["twin_maxdd_median"], 0), f"{r['twin_worst_terminal']:.2f}",
                                 f"{pp(r['gap_median'])} ({pp(r['gap_p10'], 1)} to {pp(r['gap_p90'], 1)})", pc(r["calendar_wins"], 0), pc(r["underlying_1x_cagr_median"])]
                                for r in rows]))
            md.append("Uncertainty of the gap (mean over starts). HEADLINE interval: non-overlapping windows pooled over start phases (step = the horizon in "
                      "months; mean +/- t(df) x SE); NOISY = it covers zero. Secondary intervals: block bootstrap (block = horizon in months, "
                      f"{study.N_BOOT:,} resamples) for the mean and the median. " + BB_NOTE + "\n")
            md.append(md_table(["product", "years", "median gap pp", "mean gap pp", "HEADLINE: phase-pooled mean [95% interval]", "df", "reading",
                                "secondary: bootstrap mean [95% interval]", "SE", "blocks k", "reading (bb)",
                                "secondary: bootstrap median [95% interval]", "reading (bb)"],
                               [[f"{r['product']} ({r['reset']})", r["horizon_years"], pp(r["gap_median"]), pp(r["gap_mean"]),
                                 f"{pp(r['indep_mean'])} {ci(r['indep_lo'], r['indep_hi'])}", r["indep_df"], flag(r["noisy"]),
                                 ci(r["bb_lo"], r["bb_hi"]), pp(r["bb_se"]), r["bb_k"], flag(r["noisy_bb_mean"]),
                                 ci(r["bb_median_lo"], r["bb_median_hi"]), flag(r["noisy_bb_median"])]
                                for r in rows]))

        # 2b independent windows (audit S3 finding 5)
        md.append(f"## {un} 2b. The same 10-year gap over NON-overlapping windows (how many independent samples there really are)\n")
        n10 = next(x for x in W["multi_start"]["fixed"] if x["horizon_years"] == 10)["n_starts"]
        md.append(f"The month-end starts above overlap, so {n10} windows are far fewer independent observations. Taking every 120th month-end gives "
                  "one set of non-overlapping 10-year windows; there are 120 such sets (phases). Cells: windows per phase, the share of phases in "
                  "which the calendar fund won a majority of its windows, and the median (min to max) win share across phases.\n")
        for en in ("fixed", "rate"):
            rows = W["independent"][en]
            md.append(f"**Encoding {en}.**\n")
            md.append(md_table(["product", "windows per phase", "phases with a majority of wins", "phases all positive", "win share: median (min to max)"],
                               [[label(w, next(p for p in w.specs if p.name == r["product"])), f"{r['windows_per_phase_min']}-{r['windows_per_phase_max']}",
                                 pc(r["phases_majority_wins"], 0), pc(r["phases_all_positive"], 0),
                                 f"{pc(r['win_share_median'], 0)} ({pc(r['win_share_min'], 0)} to {pc(r['win_share_max'], 0)})"] for r in rows]))

        # 3 decades
        md.append(f"## {un} 3. By decade (C2): does the sign follow the index's day-to-day autocorrelation?\n")
        md.append("A decade runs from the last close before 1 January of its first year to the last close of its last year (partial decades marked). "
                  "Autocorrelation: lag-1 of the total-return series' daily log returns, with its standard error 1/sqrt(n) and z (and the robust z of "
                  "VR(2)). Win share: month-end starts in the decade, 1-year horizon. Variance ratios VR(5) / VR(21) / VR(63) (weekly / monthly / "
                  "quarterly horizon) are Lo-MacKinlay unbiased estimates on simple daily returns with the heteroskedasticity-robust z; "
                  "**\\*** marks |z| > 1.96, a ratio that differs from 1 at the 5% level. VR below 1 = daily moves tend to reverse.\n")
        dec0 = W["decades"]["fixed"]
        md.append(md_table(["decade", "days", "mean daily", "sd daily", "AR(1) (se; z; robust z)", "VR(5) (z)", "VR(21) (z)", "VR(63) (z)"],
                           [[d["decade"] + (" (partial)" if d["partial"] else ""), d["returns"]["n_returns"], f"{d['returns']['mean_daily'] * 100:+.3f}%", f"{d['returns']['sd_daily'] * 100:.2f}%",
                             f"{d['autocorr_lag1']:+.3f} ({d['returns']['ar1_se']:.3f}; {zs(d['returns']['ar1_z'])}; {zs(d['returns']['ar1_z_robust'])})"] +
                            [f"{d['returns']['vr'][str(q)]['vr']:.3f} ({zs(d['returns']['vr'][str(q)]['z_robust'])})" for q in study.VR_HORIZONS] for d in dec0]
                           + [["**full sample**", W["returns_full_sample"]["n_returns"], f"{W['returns_full_sample']['mean_daily'] * 100:+.3f}%", f"{W['returns_full_sample']['sd_daily'] * 100:.2f}%",
                               f"{W['returns_full_sample']['ar1_rho']:+.3f} ({W['returns_full_sample']['ar1_se']:.3f}; {zs(W['returns_full_sample']['ar1_z'])}; {zs(W['returns_full_sample']['ar1_z_robust'])})"] +
                              [f"{W['returns_full_sample']['vr'][str(q)]['vr']:.3f} ({zs(W['returns_full_sample']['vr'][str(q)]['z_robust'])})" for q in study.VR_HORIZONS]]))
        nsig = {q: sum(1 for d in dec0 if d["returns"]["vr"][str(q)]["significant"]) for q in study.VR_HORIZONS}
        md.append(f"Decades whose variance ratio differs from 1 at the 5% level (robust z): VR(5) {nsig[5]} of {len(dec0)}, VR(21) {nsig[21]} of {len(dec0)}, "
                  f"VR(63) {nsig[63]} of {len(dec0)}. Ratios and z do not depend on the cost encoding.\n")
        for en in ("fixed", "rate"):
            dec = W["decades"][en]
            md.append(f"**Encoding {en}.**\n")
            md.append(prov(w, wp, ENC[en], "level", f"{dec[0]['first_close']} to {dec[-1]['last_close']} by decade"))
            hdr = ["decade", "autocorr lag-1", "1x CAGR"] + [f"{p.name} gap pp / 1y wins" for p in w.specs]
            md.append(md_table(hdr, [[d["decade"] + (" (partial)" if d["partial"] else ""), f"{d['autocorr_lag1']:+.3f}", pc(d["underlying_1x_cagr"])] +
                                     [f"{pp(d['products'][p.name]['gap'])} / {pc(d['products'][p.name]['win_share_1y'], 0)}" for p in w.specs] for d in dec]))
            md.append(md_table(["decade"] + [f"{p.name} cal / twin CAGR" for p in w.specs],
                               [[d["decade"]] + [f"{pc(d['products'][p.name]['cal_cagr'])} / {pc(d['products'][p.name]['twin_cagr'])}" for p in w.specs] for d in dec]))
            md.append("Predicted versus realized sign of the calendar-minus-daily gap, per decade. Prediction = Bessembinder's second-order formula "
                      "-2 x [C(T,2) mu^2 + T sigma^2 / 2 (VR_T - 1)] per reset period, with mu and sigma the decade's mean and sd of the daily simple return and "
                      "VR_T at the product's own horizon (T = 5 weekly, 21 monthly, 63 quarterly), shown in pp a year. It leaves out costs, the early-reset "
                      "trigger and the financing difference; the calendar fund is ahead when VR_T < 1 - (T-1) mu^2 / sigma^2 (the crossover VR). "
                      "Cells: predicted pp a year / realized pp a year; ok = same sign, MISS = different sign.\n")
            md.append(md_table(["decade"] + [f"{p.name} ({p.reset}, T={study.RESET_DAYS[p.reset]}): crossover VR; VR_T; predicted / realized" for p in w.specs],
                               [[d["decade"]] + [f"{d['products'][p.name]['crossover_vr']:.3f}; {d['products'][p.name]['vr_at_reset']:.3f}; "
                                                 f"{d['products'][p.name]['predicted_gap_pp_year']:+.2f} / {pp(d['products'][p.name]['gap'])} "
                                                 f"{'ok' if d['products'][p.name]['sign_agrees'] else 'MISS'}" for p in w.specs] for d in dec]))
            for p in w.specs:
                ps = next(x for x in W["prediction_summary"][en] if x["product"] == p.name)
                md.append(f"- {p.name} sign of the decade gap: {study.sign_pattern(dec, p.name)}. Predicted sign equals the realized sign in "
                          f"{ps['n_agree']} of {ps['n_decades']} decades. Correlation across decades between autocorrelation and gap: "
                          f"{study.gap_vs_autocorr(dec, p.name):+.2f} (n = {len(dec)} decades; descriptive only: no sampling distribution, and the decades differ in drift and volatility too).")
            md.append("")

        # 4 horizon curve
        md.append(f"## {un} 4. Horizon curve (C8): median reset gap by holding period (month-end starts)\n")
        md.append("Chart: `horizon_curve.png` (both underlyings, both encodings). Cells: median gap in pp a year (annualized, so the 1-month figures are the "
                  "monthly difference scaled up).\n")
        for en in ("fixed", "rate"):
            rows = W["horizon_curve"][en]
            md.append(f"**Encoding {en}.**\n")
            md.append(prov(w, wp, ENC[en], "level", f"month-end starts, holding periods {', '.join(str(m) for m in study.CURVE_MONTHS)} months"))
            md.append(md_table(["product"] + [f"{m}m" for m in study.CURVE_MONTHS],
                               [[label(w, p)] + [pp(next(x for x in rows if x["product"] == p.name and x["months"] == m)["gap_median"]) for m in study.CURVE_MONTHS] for p in w.specs]))

        # 5 rolling 10y
        md.append(f"## {un} 5. Rolling 10-year windows from {study.ROLLING_FROM} (C1, the Summitward replication)\n")
        md.append(f"Next to it: {C1_SCRATCH}. Zero costs = no rate, no spread, no fee for fund and twin (the gap is then the reset effect alone); "
                  "rate only = real DFF carry, no spread, no fee.\n")
        rows5 = []
        for p in w.specs:
            for en in ("zero", "rate_only", "fixed", "rate"):
                r = next(x for x in W["rolling_10y"][en] if x["product"] == p.name)
                rows5.append([label(w, p), study.ALL_ENCODINGS[en].label, pp(r["gap_median"]), pp(r["gap_min"]), pp(r["gap_max"]), f"{r['wins']}/{r['n_windows']}"])
        r0 = W["rolling_10y"]["fixed"][0]
        if name == "SPX":
            m = {en: next(x for x in W["rolling_10y"][en] if x["product"] == "HYP_SPX_M") for en in ("zero", "fixed", "rate")}
            md.append(f"**Reproduction check (monthly, S&P 500, 1990 on):** this run gives {pp(m['zero']['gap_median'])} pp median with zero costs "
                      f"({m['zero']['wins']}/{m['zero']['n_windows']} windows), {pp(m['fixed']['gap_median'])} under the fixed encoding "
                      f"({m['fixed']['wins']}/{m['fixed']['n_windows']}) and {pp(m['rate']['gap_median'])} under the rate encoding "
                      f"({m['rate']['wins']}/{m['rate']['n_windows']}); the scratch result was +1.13 pp, 321/321. "
                      "(The scratch run's costs, price/total-return basis and early-reset variant are not recorded, so agreement is approximate.)\n")
        md.append(f"*Underlying: {un} total return; windows: {r0['n_windows']} month-end starts {r0['first_start']} to {r0['last_start']}, 10 years each; mode level. "
                  f"Fees: {fee_text(w)} (zero-cost rows: 0). Spread and rate turns per row: ASSUMED (fitted on 2024-26) or defined.*\n")
        md.append(md_table(["product", "cost case", "median gap pp", "min", "max", "calendar wins"], rows5))

        # 6 early resets
        md.append(f"## {un} 6. Early resets and wipeouts (C6)\n")
        md.append("The daily twin cannot force-reset; its column counts days with a loss worse than -40% (the 2x daily move of an index fall of about 20%). "
                  "'fund hit zero' = the NAV reached zero and the fund was finished.\n")
        md.append(prov(w, wp, ENC["fixed"], "level / close / next_close (as listed)", "full history; encodings fixed and rate as listed"))
        md.append(md_table(["product", "encoding", "mode", "early resets (n)", "dates", "fund hit zero", "twin days < -40%", "twin hit zero"],
                           [[f"{e['product']} ({e['reset']})", e["encoding"], e["mode"], e["n_early_resets"], ", ".join(e["early_resets"]) or "none", e["terminated"] or "no",
                             "; ".join(e["twin_days_below_minus_40"]) or "none", e["twin_terminated"] or "no"] for e in W["early_events"]]))

        # 6b episode split (audit S3 finding 1)
        md.append(f"## {un} 6b. How much of the 10-year gap is the early-reset days? (windows containing one vs not; trigger switched off)\n")
        md.append("A 10-year window 'contains' an early reset if one of the dates in table 6 falls inside it. 'Trigger off' is the same product "
                  "with no early reset at all: NOT the product, a sensitivity that prices the trigger days.\n")
        for en in ("fixed", "rate"):
            rows = W["episode_split"][en]
            md.append(f"**Encoding {en}.**\n")
            md.append(prov(w, wp, ENC[en], "level", "month-end starts, 10-year horizon"))
            md.append(md_table(["product", "early-reset dates", "windows containing one", "gap / wins inside", "windows without", "gap / wins outside",
                                "all windows", "trigger OFF: gap / wins"],
                               [[label(w, next(p for p in w.specs if p.name == r["product"])), ", ".join(r["early_reset_dates"]) or "none", r["n_inside"],
                                 (f"{pp(r['gap_median_inside'])} / {pc(r['wins_inside'], 0)}" if r["n_inside"] else "-"), r["n_outside"],
                                 f"{pp(r['gap_median_outside'])} / {pc(r['wins_outside'], 0)}", f"{pp(r['gap_median_all'])} / {pc(r['wins_all'], 0)}",
                                 f"{pp(r['gap_median_trigger_off'])} / {pc(r['wins_trigger_off'], 0)}"] for r in rows]))

        # 7 margin
        md.append(f"## {un} 7. Buy-once margin benchmark (C7 / B3)\n")
        md.append("Cells: MEDIAN and MEAN over month-end starts of (fund CAGR minus margin-position CAGR) in pp a year, and the share of starts where the fund beats the "
                  "margin position. Negative = the fund fell short of buying once. `margin finished` = number (share) of windows in which the margin position's equity "
                  "hit zero (the index fell about 50% from purchase at some point); a finished window counts as -100% CAGR, an automatic fund win, so the "
                  "`survivors` columns repeat the comparison over the windows the margin position survives. The loan compounds (R2 step 1). Median and mean "
                  "differ because the fund's payoff is convex and the margin position's is linear: the median favors the linear side, the mean the convex one. "
                  "The all-window mean is dominated by the finished windows (each adds about +100 pp to fund minus margin), so read the mean from the "
                  "survivors table. OPTIMISTIC benchmark: a real account is called earlier.\n")
        for en in ("fixed", "rate"):
            rows = W["margin"][en]
            md.append(f"**Encoding {en}.**\n")
            md.append(prov(w, wp, ENC[en], "level", f"month-end starts, horizons 1 / 3 / 5 / 10 years; margin position 2.0x at purchase, never reset, same rate, spread and fee"))
            md.append(md_table(["product", "years", "starts", "margin CAGR median / mean", "margin finished", "fund - margin pp: median / mean", "fund beats margin", "twin - margin pp: median / mean", "twin beats margin"],
                               [[label(w, next(p for p in w.specs if p.name == r["product"])), r["horizon_years"], r["n_starts"],
                                 f"{pc(r['margin_cagr_median'])} / {pc(r['margin_cagr_mean'])}", f"{r['margin_finished']} ({pc(r['margin_finished_share'], 0)})",
                                 f"{pp(r['fund_minus_margin_median'])} / {pp(r['fund_minus_margin_mean'])}", pc(r["fund_beats_margin"], 0),
                                 f"{pp(r['twin_minus_margin_median'])} / {pp(r['twin_minus_margin_mean'])}", pc(r["twin_beats_margin"], 0)] for r in rows]))
            md.append("Survivors only (windows in which the margin position was not finished):\n")
            md.append(md_table(["product", "years", "survivor windows", "fund - margin pp: median / mean", "fund beats margin", "twin - margin pp: median / mean", "twin beats margin"],
                               [[label(w, next(p for p in w.specs if p.name == r["product"])), r["horizon_years"], r["n_survivors"],
                                 f"{pp(r['fund_minus_margin_median_survivors'])} / {pp(r['fund_minus_margin_mean_survivors'])}", pc(r["fund_beats_margin_survivors"], 0),
                                 f"{pp(r['twin_minus_margin_median_survivors'])} / {pp(r['twin_minus_margin_mean_survivors'])}", pc(r["twin_beats_margin_survivors"], 0)]
                                for r in rows if r["n_survivors"]]))

        # 8 key periods
        md.append(f"## {un} 8. Key periods (fixed list)\n")
        md.append("Periods: " + "; ".join(f"{a} ({b} to {c})" for a, b, c in study.KEY_PERIODS) + ". Start = the close before the first day; end = the last close in "
                  "the period. Each cell is return / max drawdown inside the window.\n")
        kp = next(x for x in W["key_periods"] if x["encoding"] == study.BASE_ENCODING)["rows"]
        md.append(prov(w, wp, ENC[study.BASE_ENCODING], "level", "each period as listed"))
        rows8 = []
        for k in kp:
            if not k["covered"]:
                rows8.append([k["period"], "-", k["note"], "", "", ""])
                continue
            u1 = k["underlying_1x"]
            rows8.append([f"{k['period']} ({k['first_close']} to {k['last_close']})", "1x total return", f"{pc(u1['ret'])} / {pc(u1['maxdd'])}", "", "", ""])
            for p in w.specs:
                x = k["products"][p.name]
                rows8.append(["", label(w, p), f"{pc(x['fund']['ret'])} / {pc(x['fund']['maxdd'])}", f"{pc(x['twin']['ret'])} / {pc(x['twin']['maxdd'])}",
                              f"{pc(x['margin']['ret'])} / {pc(x['margin']['maxdd'])}", ", ".join(x["early_resets_in_window"]) or "none"])
        md.append(md_table(["period", "series", "fund (or 1x)", "daily twin", "margin benchmark", "early resets inside"], rows8))

    # 9 sensitivities
    md.append("\n---\n\n# 9. What moves the answer: the 10-year median gap under every encoding, sensitivity and early-reset mode\n")
    md.append("One number per cell: median over all month-end starts of the 10-year reset gap (pp a year), total-return underlying. Columns are "
              "per underlying (S&P 500: 1950-2026, Nasdaq-100: 1985-2026). Fee and costs as in the encodings above; all ASSUMED.\n")
    names = [(n, p) for n, w in worlds.items() for p in w.specs]
    rows9 = []
    for i in range(len(R["worlds"]["SPX"]["sensitivity"])):
        sc = R["worlds"]["SPX"]["sensitivity"][i]
        rows9.append([sc["scenario"]] + [pp(R["worlds"][n]["sensitivity"][i]["gap_10y_median"][p.name]) for n, p in names])
    md.append(md_table(["scenario"] + [f"{'SPX' if n == 'SPX' else 'NDX'} {p.name}" for n, p in names], rows9))

    # 9b trigger basis (R1 E4)
    md.append("\n---\n\n# 9b. What the early reset watches: the trigger-basis sensitivity (R1 E4)\n")
    md.append("The prospectus trigger watches the ETF's price (SPY, QQQ), not the index, and the fund reacts during the day. The engine can test the index or the "
              "ETF price, on the close or on the day's low, and the drop that fires it is itself a rounding of the prospectus text. This table runs all "
              "combinations for the three live products: {close, daily low} x {index price, ETF price} x early-reset drop 34 / 35 / 36%. ETF price = "
              "AMEX:SPY from 1993-01-29 / NASDAQ:QQQ from 1999-03-10, scaled to be continuous with the index price before that (so an episode before "
              "those dates is the same on both bases). Cells: 10-year median gap in pp a year (fixed encoding) and the share of starts the calendar fund wins; "
              "level mode. The BASE CASE of this report is the row 'daily low, ETF price' at 35%; the v1 results are 'close, index price' at 35%.\n")
    tb_rows = [r for name in worlds for r in R["worlds"][name]["trigger_basis"]]
    trig_label = {"close": "close", "low": "daily low"}
    basis_label = {"index": "index price", "etf": "ETF price"}
    combos = [(t, b) for t in ("close", "low") for b in ("index", "etf")]
    rows_g, rows_e = [], []
    for pname in study.TRIGGER_TABLE_PRODUCTS:
        for t, b in combos:
            rs = {d: next(x for x in tb_rows if x["product"] == pname and x["encoding"] == "fixed" and x["trigger"] == t and x["basis"] == b and x["early_drop"] == d)
                  for d in study.TRIGGER_DROPS}
            rows_g.append([pname, trig_label[t], basis_label[b]] + [f"{pp(rs[d]['gap_median'])} / {pc(rs[d]['calendar_wins'], 0)}" for d in study.TRIGGER_DROPS])

            def cell(x, b=b):
                parts = []
                for d in x["episodes"]:
                    lab = ""
                    if b == "index" and d in x["episodes_index_only"]:
                        lab = " (index only)"
                    elif b == "etf" and d in x["episodes_etf_only"]:
                        lab = " (ETF only)"
                    else:
                        for s_ in x["episodes_shifted"]:
                            a_, b_ = s_.split(" -> ")
                            if (b == "index" and a_ == d) or (b == "etf" and b_ == d):
                                lab = f" (same episode as {b_ if b == 'index' else a_} on the {'ETF' if b == 'index' else 'index'})"
                    parts.append(d + lab)
                return ", ".join(parts) or "none"
            rows_e.append([pname, trig_label[t], basis_label[b]] + [cell(rs[d]) for d in study.TRIGGER_DROPS])
    md.append("**10-year median gap pp a year / calendar wins (fixed encoding).**\n")
    md.append(md_table(["product", "trigger tested on", "price", "drop 34%", "drop 35%", "drop 36%"], rows_g))
    md.append("**Early-reset dates found (fixed encoding).** An episode marked \"index only\" fires on the index but has no counterpart (within 4 days) on the ETF "
              "price, so the fund would not have reset; \"same episode as\" marks one episode seen a day apart on the two bases.\n")
    md.append(md_table(["product", "trigger tested on", "price", "drop 34%", "drop 35%", "drop 36%"], rows_e))
    diff = max(abs(next(x for x in tb_rows if (x["product"], x["trigger"], x["basis"], x["early_drop"], x["encoding"]) == (r["product"], r["trigger"], r["basis"], r["early_drop"], "fixed"))["gap_median"] - r["gap_median"])
               for r in tb_rows if r["encoding"] == "rate")
    same_eps = all(next(x for x in tb_rows if (x["product"], x["trigger"], x["basis"], x["early_drop"], x["encoding"]) == (r["product"], r["trigger"], r["basis"], r["early_drop"], "fixed"))["episodes"] == r["episodes"]
                   for r in tb_rows if r["encoding"] == "rate")
    md.append(f"The rate encoding moves any cell of the gap table by at most {diff * 100:.2f} pp, and its episode dates are {'identical' if same_eps else 'NOT identical (see the JSON)'}. "
              "Both encodings are in `calendar_vs_daily.json` under `trigger_basis`. Provenance: `trigger_basis_table` in `calendar_letf/study.py`; "
              "ETF and index prices and lows from the local price library (TradingView exports); ETF low prints rejected as bad: "
              + "; ".join(f"{UNDERLYING_NAME[n]} {', '.join(d['date'] for d in wprov[n]['trigger']['bad_low_days']) or 'none'}" for n in worlds) + ".\n")

    # 10 timing
    total = time.perf_counter() - wall0
    kernel_s = sum(w.kernel_seconds for w in worlds.values())
    runs = sum(w.kernel_runs for w in worlds.values())
    R["meta"]["timing"] = dict(total_wall_seconds=total, data_load_seconds=load_s, kernel_seconds=kernel_s, kernel_runs=runs)
    md.append("\n# 10. Timing\n")
    md.append(f"Whole script {total:.1f} s wall (including numba compile/cache load, data load {load_s:.1f} s, charts and files); kernel runs {runs} in {kernel_s:.2f} s "
              "(full-history NAVs plus the per-start margin runs).\n")

    md.append("\n# What this cannot tell you\n")
    md.append("- **No live calendar fund existed before 2024-08.** Everything earlier is a model; the live check (step 2) covers 2024-26 only, a bull market with no "
              "35% fall, so it says nothing about stress behavior.\n"
              "- **The 35% early-reset trigger has never fired in a live fund.** The base case tests the ETF's daily low from the ETF's first bar (index "
              "price before), so an intraday touch that recovers by the close fires the model as it would the fund; the real trigger time, the fill price "
              "and a gap through the level are not known (mode `level` fills exactly at the level; `close` and `next_close` change fund value "
              f"{fill_range_text(R)} per historical episode relative to it, `fill_effect_vs_level` in section 6 of each underlying). Whether a headline holds depends on single episodes at the edge of the "
              "rounding of the trigger (table 9b): the S&P and one Nasdaq-100 quarterly episode sit within 0.1 point of the 35% line on a close or a low.\n"
              "- **Costs were fitted on 2024-26 only** and are carried back as two different ASSUMED encodings (a fixed spread; a rate-proportional charge). They agree in "
              f"2024-26 and part when rates move ({encoding_gap_text(R)}; `encoding_gap` under each underlying). The fitted residual is not a verified input; crisis financing spreads are not modeled.\n"
              "- **Pre-1988 S&P 500 dividend yields are Shiller's measured monthly series** (MEASURED; the decade map and flat yields are sensitivities). "
              "Nasdaq-100 yields 1999-2006 are QQQ's measured fiscal-year income yields (MEASURED); before 1999 they are assumed (0.3% a year, ASSUMED).\n"
              "- **Pre-1954-07 reference rates are a proxy** (monthly 3-month T-bill, shifted one month); the 1950-54 rows are flagged.\n"
              "- **Prices, not NAVs.** The funds' own validation compared model with traded prices (bid-ask noise on thin funds); the underlying indexes are index levels.\n"
              "- **Few early-reset events.** Any quarterly-versus-monthly difference that rests on 1-3 days (see section 6 of each underlying) is an anecdote, not a statistic.\n"
              "- **Overlapping windows.** Month-end starts overlap heavily (a 10-year window shares 119 of its 120 months with its neighbor), so win shares are NOT independent "
              "observations; do not read them as p-values. The headline intervals in \"What one history can tell\" (phase-pooled) use only non-overlapping windows and rest on 3-7 "
              "independent windows at 10 years, so the t multiplier is 2.5-4.3 and the intervals are wide. The block-bootstrap intervals next to them are "
              "narrower because their SE is biased low with block = window length (coverage in results/coverage_sim.md). The headline interval "
              "takes windows that do not overlap as independent; where the real gap series shows persistence between such windows (the S&P monthly "
              "design at 1-5 years, results/coverage_sim.md section 4) the interval is too short, and the register states by how much. Both describe "
              "the sampling error of ONE history; they do not cover a different market regime, a different cost level or the model's own assumptions.\n"
              "- **Autocorrelation regime.** The variance ratios and z in section 3 test whether each decade's returns reverse or continue; the predicted sign "
              "is a second-order formula that leaves out costs and the trigger. "
              + " and ".join(f"{len(R['worlds'][n]['decades']['fixed'])} decades ({UNDERLYING_NAME[n]})" for n in worlds)
              + " are too few for a correlation to carry weight.\n"
              "- **One history.** 1950-2026 on one market; the daily-versus-calendar answer depends on the order of days, which a single path cannot vary (the Monte Carlo item B11 "
              "is not built). Entry on every trading day with the leverage at entry (B10) is not done here.\n"
              "- **Margin benchmark is optimistic** (no margin call before equity is zero, no financing spread widening) and starts at exactly 2.0x.\n"
              "- Research tooling, not investment advice.\n")

    (OUT / "calendar_vs_daily.md").write_text("\n".join(md), encoding="utf-8")
    (OUT / "calendar_vs_daily.json").write_text(json.dumps(clean(R), indent=1), encoding="utf-8")
    print(f"\nwrote {OUT / 'calendar_vs_daily.md'}, calendar_vs_daily.json, equity_SPX.png, equity_NDX.png, horizon_curve.png, raw/*.csv")
    print(f"TIMING: whole script {total:.1f} s; data load {load_s:.1f} s; kernel runs {runs} in {kernel_s:.2f} s")

    # ---- console summary of the headline numbers
    print("\nHEADLINE (10-year median gap pp/yr, level mode; fixed | rate; calendar wins):")
    for name, w in worlds.items():
        for p in w.specs:
            a = next(x for x in R["worlds"][name]["multi_start"]["fixed"] if x["product"] == p.name and x["horizon_years"] == 10)
            b = next(x for x in R["worlds"][name]["multi_start"]["rate"] if x["product"] == p.name and x["horizon_years"] == 10)
            print(f"  {name} {p.name:10} {pp(a['gap_median'])} | {pp(b['gap_median'])}  wins {pc(a['calendar_wins'], 0)} | {pc(b['calendar_wins'], 0)}  (n={a['n_starts']})")
    print("\nROLLING 10Y from 1990 (median gap pp, wins):")
    for name, w in worlds.items():
        for en in ("zero", "rate_only", "fixed", "rate"):
            for r in R["worlds"][name]["rolling_10y"][en]:
                print(f"  {name} {en:9} {r['product']:10} {pp(r['gap_median'])} min {pp(r['gap_min'])} max {pp(r['gap_max'])} wins {r['wins']}/{r['n_windows']}")


if __name__ == "__main__":
    main()

