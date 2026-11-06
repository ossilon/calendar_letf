"""BACKLOG B12 (with B10's remainder): periods.anchored_period_end_flags, montecarlo.block_pick(random_phase=True), and
results/reset_day.json.

Part A, planted (made-up calendars with hand-picked holidays; each expected reset day found by hand) and one real-data
check (the Friday anchor equals the exchange-calendar rule on the S&P 500 sessions from 1970). Part B checks the results
file and the qualitative claims of FINDINGS F27.
"""
import json

import numpy as np
import pandas as pd

from _harness import ROOT, check, raises
from calendar_letf import loader, montecarlo as mc, periods, stats

# ---- A1. anchored reset days, by hand ----
days = pd.bdate_range("2024-01-01", "2024-06-28")
days = days[~days.isin(pd.to_datetime(["2024-01-01", "2024-01-15", "2024-02-14", "2024-05-15", "2024-03-29"]))]   # made-up holidays


def on(reset, a):
    return [str(d.date()) for d in days[periods.anchored_period_end_flags(days, reset, a)]]


check("anchored weekly: Wednesday 2024-02-14 has no row, so that week resets on Tuesday 2024-02-13",
      "2024-02-13" in on("weekly", "wed") and "2024-02-14" not in on("weekly", "wed"))
check("anchored weekly: Monday anchor and a Monday holiday (2024-01-01, 2024-01-15): no reset that week",
      "2024-01-08" in on("weekly", "mon") and not any(d.startswith("2024-01-0") and d < "2024-01-08" for d in on("weekly", "mon"))
      and "2024-01-15" not in on("weekly", "mon") and "2024-01-12" not in on("weekly", "mon"))
check("anchored monthly 15: 2024-06-15 is a Saturday, so June resets on Friday 2024-06-14; May 15 has no row, so 2024-05-14",
      "2024-06-14" in on("monthly", 15) and "2024-05-14" in on("monthly", 15) and len(on("monthly", 15)) == 6)
check("anchored quarterly: (3, 5) gives 2024-03-05 and 2024-06-05; (2, 15) gives 2024-02-15 and 2024-05-14",
      on("quarterly", (3, 5)) == ["2024-03-05", "2024-06-05"] and on("quarterly", (2, 15)) == ["2024-02-15", "2024-05-14"])
check("anchored: an anchor after the last row is not flagged (the data stop before the reset)",
      on("monthly", 28) == ["2024-01-26", "2024-02-28", "2024-03-28", "2024-04-26", "2024-05-28", "2024-06-28"]
      and periods.anchored_period_end_flags(days[:39], "monthly", 28).sum() == 1)
check("anchored: a stray row on a non-session day (1985-09-27, NYSE shut for Hurricane Gloria) never carries the reset",
      [str(d.date()) for d in pd.DatetimeIndex(["1985-09-23", "1985-09-24", "1985-09-25", "1985-09-26", "1985-09-27"])[
          periods.anchored_period_end_flags(pd.DatetimeIndex(["1985-09-23", "1985-09-24", "1985-09-25", "1985-09-26", "1985-09-27"]),
                                            "weekly", "fri")]] == ["1985-09-26"])
raises("anchored: a weekly anchor must be a weekday name", lambda: periods.anchored_period_end_flags(days, "weekly", "sat"), "weekly anchor")
raises("anchored: a monthly anchor above 28 is refused", lambda: periods.anchored_period_end_flags(days, "monthly", 31), "1-28")
raises("anchored: a quarterly anchor needs (month 1-3, day)", lambda: periods.anchored_period_end_flags(days, "quarterly", 15), "quarterly anchor")
try:
    spx = loader.close("SP:SPX").loc["1970-01-02":"2026-09-30"].index
except FileNotFoundError as _e:            # a fresh clone has no price data: this one check needs the real sessions
    spx = None
    print(f"skip: anchored weekly 'fri' on the real S&P 500 sessions is not run ({_e})")
if spx is not None:
    check("anchored weekly 'fri' on the real S&P 500 sessions 1970-2026 equals the exchange-calendar rule (period_end_flags)",
          np.array_equal(periods.anchored_period_end_flags(spx, "weekly", "fri"), periods.period_end_flags(spx, "weekly")))

# ---- A2. random block phase ----
st = mc.block_starts(5000, 50)
a = mc.block_pick(np.random.default_rng(1), st, 50, 300, 400, random_phase=True)
b = mc.block_pick(np.random.default_rng(1), st, 50, 300, 400, random_phase=True)
seam = [int(np.flatnonzero(np.diff(a[p]) != 1)[0]) + 1 for p in range(400)]
check("block_pick random_phase: same seed, same picks; the first seam falls on many different rows (1-50), not always row 50",
      np.array_equal(a, b) and len(set(seam)) > 40 and min(seam) >= 1 and max(seam) <= 50, (len(set(seam)), min(seam), max(seam)))
check("block_pick random_phase: between seams the days stay consecutive, every 50 days",
      all(np.all(np.diff(a[p, s:s + 50]) == 1) for p in range(20) for s in range(seam[p], 250, 50)))
plain = mc.block_pick(np.random.default_rng(1), st, 50, 300, 4)
check("block_pick without random_phase is unchanged: seams on rows 50, 100, ...",
      all(np.flatnonzero(np.diff(plain[p]) != 1)[0] == 49 for p in range(4)))
_st = np.random.default_rng(1).choice(st, size=(4, 6), replace=True)       # the B11 construction, written out again
check("block_pick without random_phase draws exactly the B11 stream (so B11's published paths cannot move)",
      np.array_equal(plain, (_st[:, :, None] + np.arange(50)[None, None, :]).reshape(4, 300)[:, :300]))

# ================================================================ Part B: the results file
res = json.loads((ROOT / "results" / "reset_day.json").read_text(encoding="utf-8"))
S = res["summary"]
for name, W in res["worlds"].items():
    check(f"{name}: every non-standard anchor carries a yearly difference against the standard day; the standard day has none",
          all(("minus_std_yearly" in r) == (r["anchor"] != "std") for r in W["history"]))
    check(f"{name}: on the simulated paths the standard day differs from itself by exactly 0",
          all(r["minus_std_mean"] == 0.0 for r in W["simulated"] if r["anchor"] == "std"))
check("results: 26 history comparisons (13 per index)", S["n_history_comparisons"] == 26)
# the qualitative claims of FINDINGS F27
check("F27: on the simulated paths no reset day moves the 10-year gap by 0.1 points a year or more",
      S["sim_max_abs_minus_std"] < 0.001, S["sim_max_abs_minus_std"])
mon = {n: (next(r for r in W["history"] if r["anchor"] == "mon"), next(r for r in W["simulated"] if r["anchor"] == "mon"))
       for n, W in res["worlds"].items()}
check("F27: in history the Monday reset trails the standard day on both indexes (mean below zero); on the simulated paths "
      "it does not (its mean difference is positive)",
      all(h["minus_std_yearly"]["mean"] < 0 and s_["minus_std_mean"] > 0 for h, s_ in mon.values()))
# U1 (re-grade 2026-11-06): the Monday lag is not established. The F27 wording rests on these three facts.
fam = [r["minus_std_yearly"] for W in res["worlds"].values() for r in W["history"] if r["anchor"] != "std"]
check("F27: every one of the 26 history comparisons carries a t statistic, its p-value and a Holm-adjusted p",
      len(fam) == 26 and all({"t", "p", "p_holm"} <= set(x) for x in fam))
check("F27: no history comparison survives Holm's adjustment over the 26 (every adjusted p at or above 0.05)",
      S["history_n_holm_below_005"] == 0 and S["history_min_p_holm"] >= 0.05, S["history_min_p_holm"])
check("F27: the summary's Holm values equal stats.holm over the family, recomputed here",
      all(abs(a_ - b_) < 1e-15 for a_, b_ in zip([x["p_holm"] for x in fam], stats.holm([x["p"] for x in fam]))))
check("F27 (B10): entry on any trading day gives the 10-year median of the month-end starts within 0.02 points",
      S["b10_max_abs_vs_month_end"] < 0.0002 + 1e-12, S["b10_max_abs_vs_month_end"])
