"""Known-answer tests for bottoms.py (B13: entries from major bottoms). Made-up data only; no files needed.
Expected numbers are worked out by hand in the comments.
"""
from dataclasses import replace

import numpy as np
import pandas as pd

from _harness import check, raises  # noqa: I001
from calendar_letf import bottoms as b
from calendar_letf import costs, kernel, periods, products, study

TOL = 1e-9


def days(n, start="2024-01-02"):
    return pd.bdate_range(start, periods=n)


# ---------------------------------------------------------------- hindsight troughs
# rows:      0    1   2   3   4    5    6   7   8   9    10  11  12   13   14  15   16
path = np.array([100, 90, 75, 80, 100, 101, 90, 70, 80, 102, 95, 85, 110, 100, 85, 120, 108], dtype=float)
d17 = days(len(path))
tr = b.drawdown_troughs(d17, path, 0.19)
rows = [t["trough_row"] for t in tr]
# episode 1: high 100 (row 0); row 4 EQUALS the high, which is not a new high, so the episode goes on to row 5 (101); trough row 2 = 75 (-25%).
# episode 2: high 101 (row 5) -> trough row 7 = 70 (-30.7%); episode 3: 102 (row 9) -> row 11 = 85 is only -16.7%: not recorded;
# episode 4: 110 (row 12) -> row 14 = 85 (-22.7%); episode 5: 120 (row 15) -> 108 is -10%: not recorded.
check("troughs: hand-made path gives troughs at rows 2, 7 and 14 (the -16.7% and -10% dips are too shallow)", rows == [2, 7, 14], rows)
check("troughs: depths are -25%, -30.69%, -22.73% from each episode's own high",
      np.allclose([t["depth"] for t in tr], [-0.25, 70 / 101 - 1, 85 / 110 - 1]), [t["depth"] for t in tr])
check("troughs: a close equal to the old high does not re-arm: the first episode lasts to row 5 (101), not row 4",
      tr[0]["recovery_row"] == 5 and tr[0]["peak_row"] == 0, (tr[0]["recovery_row"], tr[0]["peak_row"]))
check("troughs: each fall is found once and re-arms only after a new high (peaks at rows 0, 5, 12)", [t["peak_row"] for t in tr] == [0, 5, 12])
check("troughs: dates are the trough rows' dates", tr[1]["trough_date"] == str(d17[7].date()))
check("troughs: a threshold of 10% also finds the -16.7%, and the unfinished -10% dip at the end is found with no recovery",
      [t["trough_row"] for t in b.drawdown_troughs(d17, path, 0.09)] == [2, 7, 11, 14, 16]
      and b.drawdown_troughs(d17, path, 0.09)[-1]["recovery_row"] is None)
check("troughs: a path that never falls 19% has none", b.drawdown_troughs(days(5), np.array([1.0, 1.1, 1.0, 1.2, 1.15]), 0.19) == [])

# a second leg INSIDE a long fall (like the Nasdaq-100 2007-09 inside 2000-15): the old high is never regained
path2 = np.array([100, 50, 70, 90, 60, 75, 101], dtype=float)
t2 = b.drawdown_troughs(days(7), path2, 0.19)
check("troughs: inside a fall that never regained its high, the second leg is found too (rows 1 and 4, levels 0 and 1)",
      [(t["trough_row"], t["level"]) for t in t2] == [(1, 0), (4, 1)], t2)
check("troughs: the second leg's depth is measured from the highest close since the first trough (90 -> 60 = -33.3%)",
      abs(t2[1]["depth"] - (60 / 90 - 1)) < TOL and t2[1]["peak_row"] == 3)

# tiers and the comparison with a list
rows_c, unmatched = b.compare_with_list(tr, [str(d17[2].date()), "2030-01-01"])
check("compare_with_list: a listed date on a trough matches it (0 days); a date far from any trough is reported as not found",
      rows_c[0]["found_date"] == str(d17[2].date()) and rows_c[0]["days_apart"] == 0 and rows_c[1]["found_date"] is None)
check("compare_with_list: the troughs the list did not mention come back as unmatched", [t["trough_row"] for t in unmatched] == [7, 14])
major, shallow, _, _ = b.tier_troughs(tr, [str(d17[2].date())], extra_years=())
check("tier_troughs: the listed trough is major; the others (all shallower than 40%) are shallow",
      [t["trough_row"] for t in major] == [2] and [t["trough_row"] for t in shallow] == [7, 14])
deep = np.array([100, 55, 80, 120], dtype=float)                    # -45%: deeper than 40%, so major even if the list omits it
check("tier_troughs: an unlisted trough deeper than 40% is promoted to major",
      [t["trough_row"] for t in b.tier_troughs(b.drawdown_troughs(days(4), deep, 0.19), [])[0]] == [1])

# ---------------------------------------------------------------- level entries
lp = np.array([100, 95, 79, 70, 60, 101, 90, 79, 105], dtype=float)
ent, worst = b.level_entries(days(len(lp)), lp, (0.20, 0.30, 0.90))
# fall 1: 79 (row 2) is the first close <= 80 (-21%); 70 (row 3) is the first <= 70 (exactly -30%: "at least"); 60 (row 4) is deeper but those levels
# are already used. 101 (row 5) is a new high and re-arms. fall 2 (high 101): 79 (row 7) <= 80.8 fires the 20% level again; 70.7 is not reached.
check("level_entries: the 20% level fires once per fall, at the first close through it (rows 2 and 7)", [e["row"] for e in ent[0.20]] == [2, 7], ent[0.20])
check("level_entries: the 30% level fires at exactly -30% (row 3) and not again in that fall; the second fall never reaches 30%", [e["row"] for e in ent[0.30]] == [3])
check("level_entries: a level that never happened has no entries; the deepest fall is reported (40% on row 4)",
      ent[0.90] == [] and abs(worst["fall"] - 0.40) < TOL and worst["row"] == 4, worst)
check("level_entries: each entry names the all-time high it fell from", ent[0.20][0]["ath_row"] == 0 and ent[0.20][1]["ath_row"] == 5)
check("level_entries: uses closes up to the day only (cutting the path after row 3 gives the same first entries)",
      [e["row"] for e in b.level_entries(days(4), lp[:4], (0.20, 0.30))[0][0.20]] == [2])

# ---------------------------------------------------------------- effective leverage
check("leverage_from_ratio: 2x/(2x-1): 2.67x after -20%, 3.5x after -30%, 4.33x after -35%, 5x after -37.5%, 2x at the reset",
      np.allclose(b.leverage_from_ratio([0.8, 0.7, 0.65, 0.625, 1.0]), [8 / 3, 3.5, 13 / 3, 5.0, 2.0]), b.leverage_from_ratio([0.8, 0.7, 0.65, 0.625, 1.0]))
check("leverage_from_ratio: a ratio of 0.5 or below means the fund is finished (NaN)", np.isnan(b.leverage_from_ratio([0.5, 0.4])).all())
check("leverage_from_ratio: a 3x fund after -20%: 3x/(3x-2) = 2.4/0.4 = 6", abs(float(b.leverage_from_ratio(0.8, 3.0)) - 6.0) < TOL)

# a hand-made calendar path: monthly reset, no costs. Jan 2024 flat at 100; Feb 15 falls to 70; Feb 29 is the reset; March 15 falls a further 35% (to 45.5).
dd = pd.bdate_range("2024-01-02", "2024-04-30")
u = pd.Series(100.0, index=dd)
u[dd >= "2024-02-15"] = 70.0
u[dd >= "2024-03-15"] = 70.0 * 0.651                                 # -34.9% inside March: just before the -35% trigger
ua = u.to_numpy()
acc = periods.accrual_fraction(dd)
pe = periods.period_end_flags(dd, "monthly")
zero = np.zeros(len(dd))


def lev_at(date, drop=None, arr=ua):
    r = int(np.flatnonzero(dd == pd.Timestamp(date))[0])
    return b.effective_leverage(arr, arr, zero, acc, acc, pe, r, 2.0, 0.0, 0.0, drop)     # zero costs: accruals unused


check("effective_leverage: index 100 -> 70 in the middle of the month gives 3.5x", abs(lev_at("2024-02-15") - 3.5) < 1e-6, lev_at("2024-02-15"))
check("effective_leverage: the day before the fall (index still 100) is 2.0x", abs(lev_at("2024-02-14") - 2.0) < 1e-6)
check("effective_leverage: on the month's last close the fund has just reset: exactly 2.0x", lev_at("2024-02-29") == 2.0)
check("effective_leverage: after the reset the next day (index still 70) is 2.0x again", abs(lev_at("2024-03-01") - 2.0) < 1e-6)
check("effective_leverage: -34.9% inside a month, trigger off: 4.31x (= 2 x 0.651 / (2 x 0.651 - 1))",
      abs(lev_at("2024-03-15") - 1.302 / 0.302) < 1e-6, lev_at("2024-03-15"))
check("effective_leverage: -34.9% with the -35% trigger on: not yet triggered, same 4.31x", abs(lev_at("2024-03-15", 0.35) - 1.302 / 0.302) < 1e-6)
u2 = ua.copy()
u2[dd >= "2024-03-15"] = 70.0 * 0.60                                 # a fall through the -35% level: the fund resets at the level (0.65 x 70), then moves on
l_after = lev_at("2024-03-15", 0.35, u2)
want = 2 * (0.60 / 0.65) / (2 * (0.60 / 0.65) - 1)                   # base re-set at 0.65: now at 0.60/0.65 of it
check("effective_leverage: after the early reset at the -35% level the base is the trigger level, so leverage is 2.18x, not 5x",
      abs(l_after - want) < 1e-6 and l_after < 2.3, (l_after, want))
check("effective_leverage: a fund that is finished (index -60% from the reset, no trigger) has no leverage (NaN)",
      np.isnan(b.effective_leverage(np.r_[100.0, 40.0], np.r_[100.0, 40.0], np.zeros(2), np.array([0.0, 1 / 360]), np.array([0.0, 1 / 365]),
                                    np.array([False, False]), 1, 2.0, 0.0, 0.0, None)))

# with costs, on a random walk: the kernel-state leverage equals 2 x (U_t/U_0) / (NAV_t/NAV_0) at the last reset
rng = np.random.default_rng(5)
rw = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, 600))), index=days(600))
rate = pd.Series(0.04, index=rw.index)
nav = kernel.periodic_reset_series(rw, rate, reset="monthly", L=2.0, spread_per_nav=0.026, fee=0.01, early_drop=None)
pe2 = periods.period_end_flags(rw.index, "monthly")
acc2_fin, acc2_fee = periods.accrual_fraction(rw.index, 360), periods.accrual_fraction(rw.index)    # the wrapper's defaults
worst_diff = 0.0
for row in (40, 41, 77, 100, 250, 333, 580):
    if pe2[row]:
        continue
    r0 = int(np.flatnonzero(pe2[:row])[-1])
    a = b.effective_leverage(rw.to_numpy(), rw.to_numpy(), np.full(600, 0.04), acc2_fin, acc2_fee, pe2, row, 2.0, 0.026, 0.01, None)
    c = b.effective_leverage_nav_ratio(rw.to_numpy(), nav.to_numpy(), r0, row)
    worst_diff = max(worst_diff, abs(a - c))
check("effective_leverage: with costs, the kernel-state method equals the NAV-ratio formula 2 x (U_t/U_0) / (NAV_t/NAV_0) to 1e-7", worst_diff < 1e-7, worst_diff)

# ---------------------------------------------------------------- Guppy confirmations
st = np.array([-1, -1, 0, 0, 1, 1, 0, -1, 0, 1])
check("first_transition: first red->gray from the start is at index 2", b.first_transition(st, -1, 0, 0, 9) == 2)
check("first_transition: asking for the first red->gray AFTER index 3 skips the first one and finds index 8", b.first_transition(st, -1, 0, 3, 9) == 8)
check("first_transition: first gray->green after index 5 is index 9", b.first_transition(st, 0, 1, 5, 9) == 9)
check("first_transition: nothing qualifies in a window that ends too early -> None (never)", b.first_transition(st, 0, 1, 0, 3) is None)
check("first_transition: a pattern that does not occur (green->red) -> None", b.first_transition(st, 1, -1, 0, 9) is None)
check("first_transition: a direct red->green jump counts as neither red->gray nor gray->green",
      b.first_transition(np.array([-1, 1]), -1, 0, 0, 1) is None and b.first_transition(np.array([-1, 1]), 0, 1, 0, 1) is None)

# a V-shaped price path: 450 days of steady fall, then 600 days of steady rise
n = 1050
vd = days(n, "2000-01-03")
t = np.arange(n)
vp = np.where(t < 450, 100 * np.exp(-0.002 * t), 100 * np.exp(-0.002 * 450) * np.exp(0.003 * (t - 450)))
book = b.GuppyBook(vd, vp)
conf = book.confirmations(450, n - 1)
sig = {k: (None if v is None else v["signal_row"]) for k, v in conf.items()}
check("guppy: on a V path every confirmation arrives after the bottom row (450)", all(v is not None and v > 450 for v in sig.values()), sig)
check("guppy: red->gray comes before gray->green, daily before weekly, and green & above the 200 EMA is not before gray->green",
      sig["daily_red_to_gray"] < sig["daily_gray_to_green"] <= sig["daily_green_above_200"]
      and sig["daily_red_to_gray"] < sig["weekly_red_to_gray"] and sig["daily_gray_to_green"] < sig["weekly_gray_to_green"], sig)
check("guppy: the ribbon is red at the bottom of a long steady fall", book.state_on(450)[0] == "red", book.state_on(450))
check("guppy: a weekly signal sits on a week-end row (the bar's last session)", sig["weekly_gray_to_green"] in set(book.w_rows.tolist()))
short = book.confirmations(450, 452)
check("guppy: a window that ends two rows after the entry has no confirmations: all None (reported as 'none')", all(v is None for v in short.values()), short)
falling = book.confirmations(200, 400)
check("guppy: while the price keeps falling there is no gray->green and no green & above-200", falling["daily_gray_to_green"] is None and falling["daily_green_above_200"] is None)
cut = b.GuppyBook(vd[:700], vp[:700])
check("guppy: states on the first 700 rows do not change when later data are removed (no look-ahead)",
      np.array_equal(cut.d_state, book.d_state[:700]) and np.array_equal(cut.d_above, book.d_above[:700]))
check("fill_row: the fill is the next close; none after the last row", b.fill_row(10, 100) == 11 and b.fill_row(99, 100) is None)

# ---------------------------------------------------------------- the 3x models
for nm, (sp, tn, fee) in {"UPRO_MODEL": (0.009218, 2.4215, 0.0089), "TQQQ_MODEL": (0.010576, 2.5630, 0.0082)}.items():
    m = products.MODELS_3X[nm]
    costs.check_turns(m.costs, m.L)
    check(f"{nm}: passes check_turns on the swaps basis (turns {tn:g} at L = 3) and carries the filed spread, turns and fee",
          m.costs.spread_basis == "swaps" and m.L == 3.0 and abs(m.costs.turns - tn) < 1e-12 and abs(m.costs.spread - sp) < 1e-12
          and abs(m.costs.fee - fee) < 1e-12 and m.kind == "REAL_FUND" and m.reset == "daily" and m.early_drop is None)
    check(f"{nm}: spread and turns are VERIFIED from the N-PORT filing; the model sits outside PRODUCTS",
          m.costs.spread_status.startswith("VERIFIED_NPORT") and m.costs.turns_status.startswith("VERIFIED_NPORT") and nm not in products.PRODUCTS)
raises("3x model: the same turns on the notional basis (turns = L) are refused", lambda: replace(products.MODELS_3X["UPRO_MODEL"], costs=replace(
    products.MODELS_3X["UPRO_MODEL"].costs, spread_basis="notional")), "does not match")
flat = pd.Series(100.0, index=pd.bdate_range("2024-01-01", periods=262))     # flat index: the fund only pays its costs
nav3 = kernel.run(products.MODELS_3X["UPRO_MODEL"], flat, 0.04)
yrs = (flat.index[-1] - flat.index[0]).days / 365.0
c3 = 2 * 0.04 + 2.4215 * 0.009218 + 0.0089                                   # 2 turns of the rate + spread x swap turns + fee
check("3x model: on a flat index the daily kernel charges 2 x rate + spread x 2.4215 turns + fee (about 11.1% a year)",
      abs(np.log(nav3.iloc[-1]) + c3 * yrs) < 2e-3, (np.log(nav3.iloc[-1]), -c3 * yrs))

# ---------------------------------------------------------------- windows and one NAV-ratio window = a direct run
check("horizon_row: 1 year after 2024-01-02 is the last close on or before 2025-01-02; None when the data end first",
      b.horizon_row(days(300), 0, 1) is not None and b.horizon_row(days(300), 0, 5) is None)
hd = pd.date_range("2020-01-31", periods=3, freq="D")
check("horizon_row: half-year horizons are calendar months (0.5 = 6, 1.5 = 18, 2.5 = 30) and a non-whole-month horizon is refused",
      b.horizon_row(pd.date_range("2020-01-15", "2023-12-31", freq="D"), 0, 0.5) == (pd.Timestamp("2020-07-15") - pd.Timestamp("2020-01-15")).days
      and b.horizon_row(pd.date_range("2020-01-15", "2023-12-31", freq="D"), 0, 2.5) == (pd.Timestamp("2022-07-15") - pd.Timestamp("2020-01-15")).days)
raises("horizon_row: 0.1 years (1.2 months) is not a whole number of months", lambda: b.horizon_row(hd, 0, 0.1), "whole number")

# Dollar layer, planted answer: a NAV that grows exactly 1% per calendar month from 2010-01-15 (a step on each monthly
# anniversary, daily rows). $10,000 held h years must be 10,000 x 1.01^(12 h) at EVERY horizon h = 0.5 ... 3. The old rule
# (entry row + round(252 h) rows) lands on other dates, so it must NOT give these numbers; if it did, this test would not bite.
dd = pd.date_range("2010-01-15", "2014-12-31", freq="D")
months_elapsed = (dd.year - 2010) * 12 + (dd.month - 1) - (dd.day < 15).astype(int)
nav_m = 1.01 ** months_elapsed.to_numpy()
steps = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)
got = b.dollar_values(nav_m, dd, 0, steps)
want = {f"{h:g}y": 10_000.0 * 1.01 ** (12 * h) for h in steps}
err_cal = max(abs(got[k] - want[k]) for k in want)
old = {f"{h:g}y": 10_000.0 * nav_m[int(round(h * 252))] / nav_m[0] for h in steps}
err_252 = min(abs(old[k] - want[k]) for k in want)
check("dollar layer: 1%/month NAV gives $10,000 x 1.01^(12 h) at h = 0.5, 1, 1.5, 2, 2.5, 3 within 1e-9", err_cal < 1e-9, (err_cal, got))
check("dollar layer: the 252-day rule does NOT reproduce it (every horizon is off by more than $100), so the test bites",
      err_252 > 100.0, (err_252, old))
check("dollar layer: a horizon past the last close is NaN", np.isnan(b.dollar_values(nav_m, dd, len(dd) - 400, (3.0,))["3y"]))

wn = b.window_numbers(np.array([1.0, 2.0, 1.0, 3.0]), pd.DatetimeIndex(["2020-01-01", "2020-07-01", "2021-01-01", "2022-01-01"]), 0, 3)
check("window_numbers: return +200%, CAGR (3^(1/yrs) - 1), max drawdown -50% from the high inside the window",
      abs(wn["ret"] - 2.0) < TOL and abs(wn["maxdd"] + 0.5) < TOL and abs(wn["cagr"] - (3 ** (365.25 / 731) - 1)) < 1e-12, wn)

rng = np.random.default_rng(11)
ix = days(3200, "2010-01-04")
uu = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.011, len(ix)))), index=ix, name="u")
rt = pd.Series(0.03, index=ix)
spec = products.PRODUCTS["MQQQ"]
world = study.World("NDX", uu, uu.rename("trig"), rt, [spec], {"MQQQ": products.twin_of(spec)})
ev = b.Evaluator(world, products.MODELS_3X["TQQQ_MODEL"], None)
enc = study.ENCODINGS["fixed"]
s_reset = int(world.me[30])                                            # a month-end close: a reset date for the monthly fund
s_mid = s_reset + 7                                                    # a mid-month close
res = ev.evaluate(s_reset, spec, enc, (1,))
e1 = b.horizon_row(ix, s_reset, 1)
direct_fund = kernel.run(spec, uu.iloc[s_reset:e1 + 1], rt.iloc[s_reset:e1 + 1], trigger=uu.rename("trig").iloc[s_reset:e1 + 1],
                         spread_per_nav=enc.spread_per_nav).iloc[-1] - 1
check("window: the calendar fund's NAV-ratio return equals a direct run from a reset date (the bottom is a period end)",
      abs(res["horizons"][1]["fund"]["ret"] - direct_fund) < 1e-9, (res["horizons"][1]["fund"]["ret"], direct_fund))
res_mid = ev.evaluate(s_mid, spec, enc, (1,))
e_mid = b.horizon_row(ix, s_mid, 1)
direct_twin = kernel.run(world.twins["MQQQ"], uu.iloc[s_mid:e_mid + 1], rt.iloc[s_mid:e_mid + 1], spread_per_nav=enc.spread_per_nav).iloc[-1] - 1
direct_3x = kernel.run(products.MODELS_3X["TQQQ_MODEL"], uu.iloc[s_mid:e_mid + 1], rt.iloc[s_mid:e_mid + 1]).iloc[-1] - 1
check("window: the daily twin and the 3x model equal a direct run from ANY close (every close is a reset), mid-month included",
      abs(res_mid["horizons"][1]["twin"]["ret"] - direct_twin) < 1e-9 and abs(res_mid["horizons"][1]["m3x"]["ret"] - direct_3x) < 1e-9)
direct_mid_fund = kernel.run(spec, uu.iloc[s_mid:e_mid + 1], rt.iloc[s_mid:e_mid + 1], trigger=uu.rename("trig").iloc[s_mid:e_mid + 1],
                             spread_per_nav=enc.spread_per_nav).iloc[-1] - 1
check("window: from a mid-month close a direct run is NOT the fund (it resets on its first row); the NAV ratio is, with its own leverage",
      abs(res_mid["horizons"][1]["fund"]["ret"] - direct_mid_fund) > 1e-5 and res_mid["leverage"] != 2.0)
check("window: the entry leverage on a reset close is exactly 2, of the twin exactly 2 and of the 3x model exactly 3 (by construction)",
      res["leverage"] == 2.0 and spec.L == 2.0 and products.MODELS_3X["TQQQ_MODEL"].L == 3.0)
direct_margin = kernel.periodic_reset_series(uu.iloc[s_mid:e_mid + 1], rt.iloc[s_mid:e_mid + 1], reset="never", L=2.0,
                                             spread_per_nav=enc.spread_per_nav, fee=spec.fee, early_drop=None).iloc[-1] - 1
check("window: the buy-once margin position (per-entry run) equals a direct never-reset run from the entry close",
      abs(res_mid["horizons"][1]["margin"]["ret"] - direct_margin) < 1e-9, (res_mid["horizons"][1]["margin"]["ret"], direct_margin))
check("window: the 1x index return is the plain level ratio and the real fund is None when no real series is given",
      abs(res["horizons"][1]["idx"]["ret"] - (uu.iloc[e1] / uu.iloc[s_reset] - 1)) < 1e-12 and res["horizons"][1]["real"] is None)
ev_px = b.Evaluator(world, products.MODELS_3X["TQQQ_MODEL"], None, price=uu * 2.0)
check("Evaluator: price= sets the series the ENTRIES read, while the leverage keeps reading the world's trigger",
      np.allclose(ev_px.price, 2.0 * ev.price) and np.allclose(ev_px.trigger, ev.trigger) and ev_px.leverage(spec, enc, s_mid) == ev.leverage(spec, enc, s_mid)
      and np.array_equal(ev.price, ev.trigger))
raises("Evaluator: an entry price index on another calendar is refused", lambda: b.Evaluator(world, products.MODELS_3X["TQQQ_MODEL"], None, price=uu.iloc[1:]),
       "calendar")
res_late = ev.evaluate(len(ix) - 100, spec, enc, (1, 3))
check("window: a horizon that runs past the end of the data is None for every series (NaN in the tables)",
      all(v is None for v in res_late["horizons"][3].values()) and all(v is None for v in res_late["horizons"][1].values()))

# ---------------------------------------------------------------- timing offsets
tr_rows = dict(b.timing_rows(world, s_reset))
check("timing_rows: offset 0 is the bottom itself; other offsets are month-end rows", tr_rows[0] == s_reset and all(r in set(world.me.tolist()) for k, r in tr_rows.items() if k))
check("timing_rows: -1 month is earlier than the bottom and +1 month later, -6 earlier than -3",
      tr_rows[-3] < tr_rows[-1] < s_reset < tr_rows[1] < tr_rows[3] < tr_rows[6] and tr_rows[-6] < tr_rows[-3])
