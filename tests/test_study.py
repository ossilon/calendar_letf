"""Planted-answer tests for the study helpers added in R2 step 12 (calendar_letf/study.py): the cost span of the
sensitivity table, the fill rule's effect on fund value per early-reset episode, and its range. Made-up data only.
"""
import math

import numpy as np
import pandas as pd

from _harness import check
from calendar_letf import nyse, products, study

# ---- cost_span: the span of the 10-year median over the six cost cases at the level fill ----
rows = [dict(mode="level", encoding="fixed", gap_10y_median={"A": 0.010, "B": 0.020}),
        dict(mode="level", encoding="rate_hi", gap_10y_median={"A": 0.013, "B": 0.015}),
        dict(mode="level", encoding="fixed_lo", gap_10y_median={"A": 0.011, "B": 0.018}),
        dict(mode="close", encoding="fixed", gap_10y_median={"A": 0.500, "B": 0.500}),          # another fill mode: ignored
        dict(mode="level", encoding="trigger_off", gap_10y_median={"A": 9.000, "B": 9.000})]    # not a cost case: ignored
span = study.cost_span(rows)
check("cost_span: A spans 0.013 - 0.010 = 0.003 and B 0.020 - 0.015 = 0.005 over the level-fill cost cases only",
      abs(span["A"] - 0.003) < 1e-15 and abs(span["B"] - 0.005) < 1e-15 and set(span) == {"A", "B"}, span)
check("cost_span: no cost rows gives an empty dict", study.cost_span([dict(mode="close", encoding="fixed", gap_10y_median={"A": 1.0})]) == {})
check("cost_span: the six cost case names are the sensitivity table's", set(study.COST_ENCODING_NAMES) == {"fixed", "fixed_lo", "fixed_hi", "rate", "rate_lo", "rate_hi"})

# ---- fill_effect_range: min, max and count over the close and next_close rows ----
ev = [dict(mode="level", fill_effect_vs_level=[]),
      dict(mode="close", fill_effect_vs_level=[dict(date="a", sessions=70, pct=-0.11), dict(date="b", sessions=70, pct=0.03)]),
      dict(mode="next_close", fill_effect_vs_level=[dict(date="c", sessions=70, pct=0.15), dict(date="d", sessions=70, pct=float("nan"))]),
      dict(mode="trigger_off", fill_effect_vs_level=[dict(date="e", sessions=70, pct=-0.9)])]        # not a fill mode: ignored
fr = study.fill_effect_range(ev)
check("fill_effect_range: min -0.11, max +0.15, 3 finite episodes (NaN and non-fill modes dropped)",
      fr == dict(min_pct=-0.11, max_pct=0.15, n_episodes=3), fr)
fr0 = study.fill_effect_range([dict(mode="close", fill_effect_vs_level=[])])
# ---- match_fills: the per-episode alignment guard, on planted row numbers ----
_m = study.match_fills(trig=[100, 300], fills=[100, 301], period_ends=[63, 126, 189], stops=[170, 370])
check("match_fills: fills on the trigger day and one session later are 'early' fills and both episodes are aligned",
      _m == [(100, "early", True), (301, "early", True)], _m)
_m = study.match_fills(trig=[125], fills=[], period_ends=[63, 126, 189], stops=[195])
check("match_fills: no early reset but an ordinary period end one session after the trigger: the fill is that period end, aligned",
      _m == [(126, "period_end", True)], _m)
_m = study.match_fills(trig=[100], fills=[], period_ends=[63, 189], stops=[170])
check("match_fills: no early reset and no period end within 5 sessions: no fill, not aligned", _m == [(None, None, False)], _m)
_m = study.match_fills(trig=[100, 300], fills=[100, 150, 301], period_ends=[], stops=[170, 370])
check("match_fills: a mode early reset on a day the level path did not trigger (150) is unmatched and misaligns the episode whose window holds it, not the other",
      _m == [(100, "early", False), (301, "early", True)], _m)
_m = study.match_fills(trig=[100], fills=[108], period_ends=[], stops=[170])
check("match_fills: a mode reset 8 sessions after the trigger is not its fill; it is unmatched inside the window, so the episode is misaligned",
      _m == [(None, None, False)], _m)
_m = study.match_fills(trig=[100, 103], fills=[101], period_ends=[], stops=[102, 173])
check("match_fills: one mode reset is used once: the first trigger takes it, the second (within 5 sessions too) gets none",
      _m[0] == (101, "early", True) and _m[1] == (None, None, False), _m)

ev_mis = [dict(mode="close", fill_effect_vs_level=[dict(date="a", sessions=70, pct=0.50, episodes_aligned=False),
                                                   dict(date="b", sessions=70, pct=0.02, episodes_aligned=True)])]
check("fill_effect_range: an episode flagged misaligned (the mode's path triggered on another day) is left out of the range",
      study.fill_effect_range(ev_mis) == dict(min_pct=0.02, max_pct=0.02, n_episodes=1), study.fill_effect_range(ev_mis))
check("fill_effect_range: no episode gives NaN bounds and a count of 0", math.isnan(fr0["min_pct"]) and math.isnan(fr0["max_pct"]) and fr0["n_episodes"] == 0)

# ---- fill_effects, planted closed form at ZERO costs: a flat index falls 36% in one day (100 -> 64) and rebounds to 80 ----
# Trigger 35% from the period-start level 100, close-only trigger (no low series). Level fill: reset at 65, NAV 0.30
# (= 2 x 0.65 - 1); the new period runs from 65, so at 80 the NAV is 0.30 x (2 x 80/65 - 1) = 0.4384615. Close fill: reset at
# the close 64, NAV 0.28, then 0.28 x (2 x 80/64 - 1) = 0.42: ratio 0.42 / 0.4384615 = 0.9578947, pct -4.2105%. Next-close
# fill: no reset on the trigger day (the position drifts), reset at the next close 80 with NAV 2 x 0.80 - 1 = 0.60: ratio
# 0.60 / 0.4384615 = 1.3684211, pct +36.842%. Before the trigger the paths are identical (ratio 1), so the window must open
# the session before the TRIGGER day for both modes (the next-close path's own reset date is one session later: a window
# opened there reads the trigger-day drift as if it were the starting point and gives +42.105% instead; the R2 step-12
# review caught exactly that). Zero costs: the ZERO encoding (no spread, fee 0) and a zero rate series, so the closed forms
# hold to rounding.
days = pd.DatetimeIndex(nyse.sessions(pd.Timestamp("2000-01-03").date(), pd.Timestamp("2003-12-31").date()))
lvl = np.full(len(days), 100.0)
crash = 300
lvl[crash] = 64.0                       # -36% close
lvl[crash + 1:] = 80.0                  # rebound and flat
u = pd.Series(lvl, index=days, name="PLANT")
specs = [products.PRODUCTS[p] for p in study.PRODUCT_NAMES["SPX"]]
w0 = study.World("SPX", u, u, pd.Series(0.0, index=days), specs, {s.name: products.twin_of(s) for s in specs})
enc0 = study.ZERO_COSTS
LEVEL_80 = 0.30 * (2.0 * 80.0 / 65.0 - 1.0)
WANT = {"close": 0.28 * (2.0 * 80.0 / 64.0 - 1.0) / LEVEL_80 - 1.0, "next_close": 0.60 / LEVEL_80 - 1.0}
for mode in ("close", "next_close"):
    eff = study.fill_effects(w0, "SPYQ", enc0, mode)
    check(f"fill_effects ({mode}), zero costs: one episode dated on the TRIGGER day, fill date {'the same day' if mode == 'close' else 'one session later'}, 70-session window",
          len(eff) == 1 and eff[0]["date"] == str(days[crash].date()) and eff[0]["sessions"] == 70
          and eff[0]["fill_date"] == str(days[crash + (0 if mode == "close" else 1)].date()), eff)
    check(f"fill_effects ({mode}), zero costs: equals the hand closed form {WANT[mode]:+.5%} to 1e-12", abs(eff[0]["pct"] - WANT[mode]) < 1e-12, (eff[0]["pct"], WANT[mode]))
    check(f"fill_effects ({mode}): the mode's reset follows the level path's trigger within 0-5 sessions, so the episode is flagged aligned",
          eff[0]["episodes_aligned"] is True)
check("fill_effects closed forms have the expected signs: close -4.2105% (poorer), next close +36.842% (richer)",
      abs(WANT["close"] + 0.042105263) < 1e-9 and abs(WANT["next_close"] - 0.368421053) < 1e-9)
check("fill_effects: the level mode has no effect to report (empty list)", study.fill_effects(w0, "SPYQ", enc0, "level") == [])

# the same path WITH costs (fixed encoding, 3% rate): the direct ratio-of-ratios identity and the constancy of the ratio
# beyond the window (the premise of the measure), read from the level path's trigger day
w = study.World("SPX", u, u, pd.Series(0.03, index=days), specs, {s.name: products.twin_of(s) for s in specs})
enc = study.ENCODINGS["fixed"]
for mode in ("close", "next_close"):
    eff = study.fill_effects(w, "SPYQ", enc, mode)
    a, b = w.nav("SPYQ", enc, mode).to_numpy(), w.nav("SPYQ", enc, "level").to_numpy()
    direct = (a[crash + 70] / b[crash + 70]) / (a[crash - 1] / b[crash - 1]) - 1.0
    check(f"fill_effects ({mode}), with costs: equals the ratio at trigger + 70 over the ratio at trigger - 1, minus 1, to 1e-12",
          len(eff) == 1 and abs(eff[0]["pct"] - direct) < 1e-12, (eff, direct))
    tail = a[crash + 70:crash + 300] / b[crash + 70:crash + 300]
    check(f"fill_effects ({mode}), with costs: the NAV ratio is constant beyond the window (spread below 1e-9)",
          np.nanmax(tail) - np.nanmin(tail) < 1e-9, (np.nanmin(tail), np.nanmax(tail)))
    # With costs the two paths still carry different leverage until the next ordinary period end (each reset to 2x at its own
    # fill, then drifted), and financing and fees accrue on different NAV bases, so the ratio differs from the zero-cost closed
    # form by a few points over 70 sessions; the sign and the order of size must survive them.
    check(f"fill_effects ({mode}), with costs: same sign as the closed form and within 5 pp of it",
          np.sign(eff[0]["pct"]) == np.sign(WANT[mode]) and abs(eff[0]["pct"] - WANT[mode]) < 0.05, (eff[0]["pct"], WANT[mode]))

# break case: two triggers 30 sessions apart (monthly design, so the base resets to 80 at the month end in between):
# the first window is cut to the session before the second trigger (29 sessions), the second opens the session before
# the second trigger and runs 70 sessions.
lvl2 = lvl.copy()
lvl2[crash + 30] = 51.2                 # -36% from the new base 80
lvl2[crash + 31:] = 64.0
u2 = pd.Series(lvl2, index=days, name="PLANT2")
w2 = study.World("SPX", u2, u2, pd.Series(0.0, index=days), specs, {s.name: products.twin_of(s) for s in specs})
eff2 = study.fill_effects(w2, "HYP_SPX_M", enc0, "next_close")
a2, b2 = w2.nav("HYP_SPX_M", enc0, "next_close").to_numpy(), w2.nav("HYP_SPX_M", enc0, "level").to_numpy()
check("fill_effects, two episodes 30 sessions apart: two rows, the first window cut to 29 sessions, the second 70",
      len(eff2) == 2 and eff2[0]["sessions"] == 29 and eff2[1]["sessions"] == 70 and eff2[0]["date"] == str(days[crash].date())
      and eff2[1]["date"] == str(days[crash + 30].date()), eff2)
check("fill_effects, two episodes: each row equals the direct ratio over its own window (trigger - 1 to its stop)",
      len(eff2) == 2 and abs(eff2[0]["pct"] - ((a2[crash + 29] / b2[crash + 29]) / (a2[crash - 1] / b2[crash - 1]) - 1.0)) < 1e-12
      and abs(eff2[1]["pct"] - ((a2[crash + 100] / b2[crash + 100]) / (a2[crash + 29] / b2[crash + 29]) - 1.0)) < 1e-12, eff2)
u_flat = pd.Series(100.0, index=days, name="FLAT")
w_flat = study.World("SPX", u_flat, u_flat, pd.Series(0.0, index=days), specs, {s.name: products.twin_of(s) for s in specs})
check("fill_effects: a path with no trigger gives an empty list for every mode",
      study.fill_effects(w_flat, "SPYQ", enc0, "close") == [] and study.fill_effects(w_flat, "HYP_SPX_W", enc0, "next_close") == [])
# ---- encoding_gap: fixed minus rate CAGR per era ----
eg0 = study.encoding_gap(w_flat, eras=(("all", None, None),), enc_a="zero", enc_b="zero")
check("encoding_gap: the same encoding on both sides gives a gap of exactly 0 for every product", all(v == 0.0 for v in eg0["all"].values()) and set(eg0["all"]) == {s.name for s in specs})
w_rate = study.World("SPX", u_flat, u_flat, pd.Series(0.03, index=days), specs, {s.name: products.twin_of(s) for s in specs})
eg = study.encoding_gap(w_rate, eras=(("all", None, None),))
# flat index, rate 3%: the fixed encoding pays 2.6% of NAV plus 1.0 turn of the rate (5.6%), the rate encoding 1.4% plus 1.3 turns (5.3%):
# fixed minus rate CAGR is about -0.3 pp a year (accrual conventions move the third decimal)
check("encoding_gap: on a flat index at a 3% rate the fixed encoding costs about 0.3 pp a year more than the rate encoding (gap -0.3 +/- 0.1 pp)",
      all(-0.004 < v < -0.002 for v in eg["all"].values()), eg["all"])
# second route: the same gap computed by hand from the two NAV paths' end points (CAGR over 365.25-day years)
_hand = {}
for _p in specs:
    _a, _b = w_rate.nav(_p.name, study.ENCODINGS["fixed"]), w_rate.nav(_p.name, study.ENCODINGS["rate"])
    _yrs = (_a.index[-1] - _a.index[0]).days / 365.25
    _hand[_p.name] = (_a.iloc[-1] / _a.iloc[0]) ** (1 / _yrs) - (_b.iloc[-1] / _b.iloc[0]) ** (1 / _yrs)
check("encoding_gap: equals the hand computation from the two NAV paths' end points to 1e-12 for every product",
      all(abs(eg["all"][k] - _hand[k]) < 1e-12 for k in _hand), (eg["all"], _hand))
check("encoding_gap: an era outside the data gives NaN, not a crash", all(math.isnan(v) for v in study.encoding_gap(w_rate, eras=(("x", "2030-01-01", "2031-01-01"),))["x"].values()))
check("fill_effects: on the planted path every calendar design triggers (the weekly one too), each with one episode on the crash day",
      all(len(study.fill_effects(w0, p, enc0, "close")) == 1 and study.fill_effects(w0, p, enc0, "close")[0]["date"] == str(days[crash].date())
          for p in ("SPYQ", "HYP_SPX_M", "HYP_SPX_W")))

# ---- a crash one session before a quarter end (R2 step 12i) ----
# The next-close fill lands on the quarter end, an ordinary reset the kernel does not flag as early; the episode must stay
# aligned and keep the closed-form effect +36.842% (level 0.30 x (2 x 80/65 - 1); next close 2 x 0.80 - 1 = 0.60).
_qe = [k for k, d in enumerate(days) if d == pd.Timestamp("2000-03-31")][0]
lvl_q = np.full(len(days), 100.0)
lvl_q[_qe - 1] = 64.0
lvl_q[_qe:] = 80.0
u_q = pd.Series(lvl_q, index=days, name="PLANTQ")
w_q = study.World("SPX", u_q, u_q, pd.Series(0.0, index=days), specs, {s.name: products.twin_of(s) for s in specs})
eff_q = study.fill_effects(w_q, "SPYQ", study.ZERO_COSTS, "next_close")
check("fill_effects: a next-close fill on an ordinary quarter end is a 'period_end' fill, aligned, with the closed-form effect +36.842% (1e-12)",
      len(eff_q) == 1 and eff_q[0]["fill_kind"] == "period_end" and eff_q[0]["episodes_aligned"] is True
      and eff_q[0]["fill_date"] == "2000-03-31" and abs(eff_q[0]["pct"] - (0.60 / (0.30 * (2.0 * 80.0 / 65.0 - 1.0)) - 1.0)) < 1e-12, eff_q)
check("fill_effect_range: the period-end fill is kept in the range (one episode)",
      study.fill_effect_range([dict(mode="next_close", fill_effect_vs_level=eff_q)])["n_episodes"] == 1)

# ---- match_fills boundaries and the order of the two fill kinds (R2 step 12j) ----
check("match_fills: an early reset is preferred to a period end in the same span (101 early, not the period end at 103)",
      study.match_fills(trig=[100], fills=[101], period_ends=[103], stops=[170]) == [(101, "early", True)])
check("match_fills: the period-end search starts on the trigger day itself (a trigger on a period end fills there)",
      study.match_fills(trig=[100], fills=[], period_ends=[100], stops=[170]) == [(100, "period_end", True)])
check("match_fills: the period-end search ends 5 sessions after the trigger (105 is a fill, 106 is not)",
      study.match_fills(trig=[100], fills=[], period_ends=[105], stops=[170]) == [(105, "period_end", True)]
      and study.match_fills(trig=[100], fills=[], period_ends=[106], stops=[170]) == [(None, None, False)])
check("match_fills: the window opens the session BEFORE the trigger: an unmatched mode reset on that session misaligns the episode",
      study.match_fills(trig=[100], fills=[99, 100], period_ends=[], stops=[170]) == [(100, "early", False)])

# ---- a planted world where the mode's path triggers on a day the level path does not (R2 step 12j) ----
# Zero costs. A one-day fall to 64 twenty sessions before the 2000-03-31 quarter end, a rebound to 80, then a second fall to 51
# five sessions later and 60 after. The level path reset at 65 on the first fall, so its next line is 0.65 x 65 = 42.25 and 51
# does not trigger it; the next-close path reset at 80, so its line is 0.65 x 80 = 52 and 51 triggers it. The second mode reset
# has no level trigger, sits inside the first episode's window, and must flag that episode misaligned and keep it out of the range.
_qe2 = [k for k, d in enumerate(days) if d == pd.Timestamp("2000-03-31")][0]
_cr = _qe2 - 20
lvl_m = np.full(len(days), 100.0)
lvl_m[_cr] = 64.0
lvl_m[_cr + 1:] = 80.0
lvl_m[_cr + 5] = 51.0
lvl_m[_cr + 6:] = 60.0
u_m = pd.Series(lvl_m, index=days, name="PLANT_MIS")
w_m = study.World("SPX", u_m, u_m, pd.Series(0.0, index=days), specs, {s.name: products.twin_of(s) for s in specs})
eff_m = study.fill_effects(w_m, "SPYQ", study.ZERO_COSTS, "next_close")
check("fill_effects: the level path triggers once (2000-03-03) and the next-close path twice (2000-03-06 and 2000-03-13), as planted",
      list(w_m.nav("SPYQ", study.ZERO_COSTS, "level").attrs["early_resets"]) == ["2000-03-03"]
      and list(w_m.nav("SPYQ", study.ZERO_COSTS, "next_close").attrs["early_resets"]) == ["2000-03-06", "2000-03-13"],
      (w_m.nav("SPYQ", study.ZERO_COSTS, "level").attrs["early_resets"], w_m.nav("SPYQ", study.ZERO_COSTS, "next_close").attrs["early_resets"]))
check("fill_effects: the episode has its early fill on 2000-03-06 but is flagged MISALIGNED (an unmatched mode reset inside its window)",
      len(eff_m) == 1 and eff_m[0]["fill_date"] == "2000-03-06" and eff_m[0]["fill_kind"] == "early" and eff_m[0]["episodes_aligned"] is False, eff_m)
check("fill_effect_range: the misaligned episode from fill_effects is left out (n_episodes 0)",
      study.fill_effect_range([dict(mode="next_close", fill_effect_vs_level=eff_m)])["n_episodes"] == 0)
# the remaining edges of match_fills (R2 step 12k): the early-fill search ends 5 sessions after the trigger; an unmatched reset
# misaligns only inside [trigger - 1, stop], both ends included
check("match_fills: an early reset 5 sessions after the trigger is its fill; 6 sessions after is not",
      study.match_fills(trig=[100], fills=[105], period_ends=[], stops=[170]) == [(105, "early", True)]
      and study.match_fills(trig=[100], fills=[106], period_ends=[], stops=[170]) == [(None, None, False)])
check("match_fills: an unmatched reset ON the window's last row misaligns; one row after it does not",
      study.match_fills(trig=[100], fills=[100, 170], period_ends=[], stops=[170]) == [(100, "early", False)]
      and study.match_fills(trig=[100], fills=[100, 171], period_ends=[], stops=[170]) == [(100, "early", True)])
check("match_fills: an unmatched reset two sessions before the trigger is outside the window and does not misalign",
      study.match_fills(trig=[100], fills=[98, 100], period_ends=[], stops=[170]) == [(100, "early", True)])
