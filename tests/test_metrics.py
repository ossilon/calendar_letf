"""Known-answer tests for metrics.py and for the "never reset" margin benchmark (step 3).
Made-up data only; no files needed. Expected numbers are worked out by hand in the comments.
"""
from dataclasses import replace

import numpy as np
import pandas as pd

from _harness import check, raises  # noqa: I001
from calendar_letf import kernel as k
from calendar_letf import metrics as m
from calendar_letf import periods as cal
from calendar_letf import validate


def walk(start, n, seed, vol=0.012, drift=0.0003):
    ix = pd.bdate_range(start, periods=n)
    rng = np.random.default_rng(seed)
    return pd.Series(100.0 * np.exp(np.cumsum(rng.normal(drift, vol, n))), index=ix, name="walk")


# ---- cagr ----
check("cagr: doubling in 2 years = 41.42% (explicit years)", abs(m.cagr(np.array([1.0, 2.0]), years=2.0) - (2 ** 0.5 - 1)) < 1e-12)
check("cagr: doubling in 2 years = 41.42% (1e-4 relative: sqrt(2) - 1 = 0.414214)", abs(m.cagr(np.array([1.0, 2.0]), years=2.0) - 0.414214) < 1e-6)
two_y = pd.Series([1.0, 2.0], index=pd.DatetimeIndex(["2020-01-01", "2022-01-01"]))        # 731 days = 2.0014 years
check("cagr: Series uses days / 365.25 (731 days -> 41.35%) and equals validate.cagr",
      abs(m.cagr(two_y) - validate.cagr(two_y)) < 1e-15 and abs(m.cagr(two_y) - (2 ** (365.25 / 731) - 1)) < 1e-12, m.cagr(two_y))
check("cagr: plain array with 252 rows per year: 504 steps doubling -> 41.42%",
      abs(m.cagr(np.linspace(1.0, 2.0, 505)) - (2 ** 0.5 - 1)) < 1e-12)
check("cagr: a finished fund (end level 0) is -100%", m.cagr(np.array([1.0, 0.5, 0.0]), years=1.0) == -1.0)
check("cagr: a start level of 0 is NaN, not an error", np.isnan(m.cagr(np.array([0.0, 1.0]), years=1.0)))

# ---- max drawdown, time under water, recovery ----
dip = np.array([1.0, 0.5, 1.0])
check("max drawdown: [1, 0.5, 1] is -50%", abs(m.max_drawdown(dip) + 0.5) < 1e-15)
check("time under water: [1, 0.5, 1] is 1/3 (one of three rows below the peak)", abs(m.time_under_water(dip) - 1 / 3) < 1e-15)
check("recovery days: [1, 0.5, 1] is 2 rows (peak on row 0, back on row 2)", m.recovery_days(dip) == 2)
check("recovery days: the longest of two spells counts ([1,.9,1, 2,1,1.5,1.6,2] -> 4 rows, not 2)",
      m.recovery_days(np.array([1.0, 0.9, 1.0, 2.0, 1.0, 1.5, 1.6, 2.0])) == 4)
check("recovery days: an unfinished spell counts to the last row ([1, 0.5, 0.7] -> 2) unless count_open=False (-> 0)",
      m.recovery_days(np.array([1.0, 0.5, 0.7])) == 2 and m.recovery_days(np.array([1.0, 0.5, 0.7]), count_open=False) == 0)
check("recovery days: a rising series has none; max drawdown 0; time under water 0",
      m.recovery_days(np.array([1.0, 2.0, 3.0])) == 0 and m.max_drawdown(np.array([1.0, 2.0, 3.0])) == 0
      and m.time_under_water(np.array([1.0, 2.0, 3.0])) == 0)
rw = walk("2000-01-03", 3000, 11)
check("max drawdown equals validate.max_drawdown on a random walk (1e-15)", abs(m.max_drawdown(rw) - validate.max_drawdown(rw)) < 1e-15)
check("max drawdown: a finished fund (zeros after the fall) is -100%", m.max_drawdown(np.array([1.0, 0.4, 0.0, 0.0])) == -1.0)

# ---- ulcer index ----
line = np.linspace(1.0, 3.0, 50)
check("ulcer index: a straight rising line is 0", m.ulcer_index(line) == 0.0)
check("ulcer index: [1, 0.5, 1] = sqrt((0 + 0.25 + 0) / 3) = 0.288675", abs(m.ulcer_index(dip) - np.sqrt(0.25 / 3)) < 1e-15)

# ---- vol, Calmar, Sortino ----
alt = pd.Series(np.cumprod(np.r_[1.0, np.tile([1.01, 0.99], 200)]))
check("ann_vol: alternating +1% / -1% days: about 0.01 x sqrt(252) = 15.87%", abs(m.ann_vol(alt) - 0.01 * np.sqrt(252)) < 2e-4, m.ann_vol(alt))
flat_vol = m.ann_vol(np.full(10, 5.0))
check("ann_vol: a flat series has zero volatility", flat_vol == 0.0)
check("calmar: CAGR 41.42% over a 25% max drawdown = 1.657 (levels 1 -> 0.75 -> 2 over 2 years)",
      abs(m.calmar(np.array([1.0, 0.75, 2.0]), years=2.0) - (2 ** 0.5 - 1) / 0.25) < 1e-12)
# daily returns +2%, -1%, +2%, -1%: mean 0.5%; downside mean square = (0.01^2 x 2) / 4 = 5e-5 -> dd = 0.0070711
# sortino = (0.005 x 252) / (0.0070711 x sqrt(252)) = 0.70711 x sqrt(252) = 11.2250
lv = np.cumprod(np.r_[1.0, 1.02, 0.99, 1.02, 0.99])
check("sortino: returns +2%,-1%,+2%,-1% give 0.70711 x sqrt(252) = 11.225", abs(m.sortino(lv) - 0.70710678 * np.sqrt(252)) < 1e-4, m.sortino(lv))
check("sortino: a risk-free rate lowers it (rf 5% a year -> mean excess 0.5% - 0.0198%)", m.sortino(lv, rf=0.05) < m.sortino(lv))
check("sortino: no down day gives NaN, not infinity", np.isnan(m.sortino(np.array([1.0, 1.1, 1.2, 1.3]))))

# ---- lag-1 autocorrelation ----
check("lag-1 autocorrelation of alternating +1% / -1% days is about -1", m.lag1_autocorr(alt) < -0.99, m.lag1_autocorr(alt))
trend = pd.Series(np.cumprod(np.r_[1.0, np.where(np.arange(400) % 40 < 20, 1.01, 0.99)]))
check("lag-1 autocorrelation of a series moving in runs of 20 up / 20 down days is strongly positive", m.lag1_autocorr(trend) > 0.8, m.lag1_autocorr(trend))
check("lag-1 autocorrelation of random normal returns is near 0 (|rho| < 0.05 on 20,000 days)",
      abs(m.lag1_autocorr(walk("1950-01-02", 20000, 5, drift=0.0))) < 0.05)

# ---- rolling_cagr ----
bd = pd.bdate_range("2000-01-03", "2012-12-31")
days_el = (bd - bd[0]).days.to_numpy()
smooth = pd.Series(1.1 ** (days_el / 365.25), index=bd)                       # exactly 10% a year, in calendar time
rc = m.rolling_cagr(smooth, 3)
check("rolling_cagr: a series growing exactly 10%/yr gives 10% for every full 3-year window (1e-9)",
      rc.dropna().sub(0.10).abs().max() < 1e-9 and rc.notna().sum() > 2000, rc.dropna().sub(0.10).abs().max())
check("rolling_cagr: NaN until a full window exists (first 3 years)", rc.loc[:"2002-12-31"].isna().all() and rc.loc["2003-01-10":].notna().all())
ra = m.rolling_cagr(np.asarray(smooth), 1)
check("rolling_cagr: plain array uses 252-row windows (first 252 rows NaN, then values)", np.isnan(ra[:252]).all() and np.isfinite(ra[252:]).all())

# ---- window_stats: a window equals the direct computation on the slice ----
nav = walk("1990-01-02", 2500, 3)
st = np.array([0, 100, 700, 1200])
en = np.array([252, 900, 1700, 2499])
ws = m.window_stats(nav, st, en)
direct_cagr = np.array([validate.cagr(nav.iloc[a:b + 1]) for a, b in zip(st, en)])
direct_dd = np.array([validate.max_drawdown(nav.iloc[a:b + 1]) for a, b in zip(st, en)])
direct_tw = np.array([nav.iloc[b] / nav.iloc[a] for a, b in zip(st, en)])
check("window_stats: CAGR of each window equals validate.cagr on the slice (1e-12)", np.abs(ws["cagr"] - direct_cagr).max() < 1e-12)
check("window_stats: max drawdown of each window equals validate.max_drawdown on the slice (1e-15)", np.abs(ws["max_dd"] - direct_dd).max() < 1e-15)
check("window_stats: terminal wealth equals level[end] / level[start] (1e-15)", np.abs(ws["terminal"] - direct_tw).max() < 1e-15)
check("window_stats: the same windows on a plain array use rows / 252 for the years",
      abs(m.window_stats(np.asarray(nav), st, en)["years"][0] - 252 / 252) < 1e-15)
broken = np.array([1.0, 1.5, 0.0, 0.0, 0.0])
wb = m.window_stats(broken, [0, 1], [4, 4], years=[2.0, 1.0])
check("window_stats: a finished fund: terminal 0, CAGR -100%, drawdown -100%",
      np.allclose(wb["terminal"], [0, 0]) and np.allclose(wb["cagr"], [-1, -1]) and np.allclose(wb["max_dd"], [-1, -1]))
check("window_stats: a window that starts at a zero level is NaN, not an error",
      np.isnan(m.window_stats(broken, [3], [4], years=[1.0])["cagr"][0]))
raises("window_stats: an end row past the data is refused", lambda: m.window_stats(nav, [0], [len(nav)]), "window rows")
raises("window_stats: an end before the start is refused", lambda: m.window_stats(nav, [10], [5]), "window rows")

# ---- the "never reset" margin benchmark (periods.NEVER; BACKLOG C7 / B3) ----
nd = pd.bdate_range("2024-01-02", periods=300)
check("periods: 'never' gives one id for every row, so no row is a period end (not even a candidate)",
      (cal.period_ids(nd, "never") == 0).all() and not cal.period_end_flags(nd, "never").any()
      and not cal.period_end_flags(nd, "never", calendar=None).any())
check("periods: 'never' is in ALL_RESETS but not in RESETS (the kernel tests loop over RESETS)",
      cal.NEVER in cal.ALL_RESETS and cal.NEVER not in cal.RESETS)
raises("periods: an unknown reset is still refused", lambda: cal.period_ids(nd, "yearly"), "reset must be one of")

u_m = walk("2024-01-02", 300, 21, vol=0.008, drift=0.0004)
r_m = np.linspace(0.02, 0.05, 300)
a_fin_m, a_fee_m = cal.accrual_fraction(u_m.index, 360), cal.accrual_fraction(u_m.index)   # ACT/360 and 365-day fee
fee_m = np.full(300, 0.01)
never_flags = cal.period_end_flags(u_m.index, "never")
# The calendar kernel with no period end in the window: SIMPLE carry on the amounts fixed at row 0 (the in-period
# formula of a calendar fund). Independent re-statement: NAV0 x (L x u_t/u_0 - (L-1)) - carry_t - fees_t, with
# carry_t = sum of ((L-1) x rate + spread) x accrual_fin and fees_t = sum of fee x NAV_{t-1} x accrual_fee (the fee
# is charged on yesterday's NAV, so it is a running sum, not a formula in t alone).
nav_m, fl_m, term_m = k.periodic_reset_nav(u_m.values.copy(), u_m.values.copy(), u_m.values.copy(), r_m, a_fin_m, a_fee_m,
                                           never_flags, 2.0, 0.026, fee_m, 0.0, k.EARLY_LEVEL)
want = np.zeros(300)
want[0], carry, fees = 1.0, 0.0, 0.0
for t in range(1, 300):
    carry += (1.0 * r_m[t] + 0.026) * a_fin_m[t]
    fees += 0.01 * want[t - 1] * a_fee_m[t]
    want[t] = 1.0 * (2.0 * u_m.values[t] / u_m.values[0] - 1.0) - carry - fees
check("calendar kernel with no period end: NAV = NAV0 x (L x u_t/u_0 - (L-1)) minus the simple carry and fees on every row (1e-12)",
      np.abs(nav_m - want).max() < 1e-12 and not fl_m.any() and term_m == -1, np.abs(nav_m - want).max())
# The buy-once margin position (reset "never", R2 E1): the loan compounds. Independent re-statement:
#   loan_0 = 1; loan_t = loan_{t-1} x (1 + rate_t x a_fin_t) + 0.026 x a_fin_t + 0.01 x equity_{t-1} x a_fee_t;
#   equity_t = 2 x u_t/u_0 - loan_t.
mg_m, term_mg = k.margin_position_nav(u_m.values.copy(), r_m, a_fin_m, a_fee_m, 2.0, 0.026, fee_m)
want_mg, loan = np.zeros(300), 1.0
want_mg[0] = 1.0
for t in range(1, 300):
    loan = loan * (1.0 + r_m[t] * a_fin_m[t]) + 0.026 * a_fin_m[t] + 0.01 * want_mg[t - 1] * a_fee_m[t]
    want_mg[t] = 2.0 * u_m.values[t] / u_m.values[0] - loan
check("never reset (margin position): equity = 2 x u_t/u_0 - a loan that compounds daily with the spread and fee borrowed (1e-12)",
      np.abs(mg_m - want_mg).max() < 1e-12 and term_mg == -1, np.abs(mg_m - want_mg).max())
check("never reset: compounding makes the margin position worth less than the simple-carry formula after 300 rows (~14 months)",
      mg_m[-1] < nav_m[-1] - 1e-4, (mg_m[-1], nav_m[-1]))
nav_free, _ = k.margin_position_nav(u_m.values.copy(), np.zeros(300), a_fin_m, a_fee_m, 2.0, 0.0, np.zeros(300))
check("never reset: with zero costs it is exactly 2 x u_t/u_0 - 1 (1e-13): no in-period compounding ever",
      np.abs(nav_free - (2.0 * u_m.values / u_m.values[0] - 1.0)).max() < 1e-13)
check("never reset: it differs from the monthly-reset fund (it has no resets)",
      np.abs(nav_free - k.periodic_reset_series(u_m, 0.0, reset="monthly", L=2.0, spread_per_nav=0.0, fee=0.0, early_drop=None).values).max() > 1e-4)
crash = pd.Series([100.0, 80.0, 60.0, 49.0, 80.0, 120.0], index=pd.bdate_range("2024-01-02", periods=6))
nav_c, term_c = k.margin_position_nav(crash.values.copy(), np.zeros(6), cal.accrual_fraction(crash.index, 360),
                                      cal.accrual_fraction(crash.index), 2.0, 0.0, np.zeros(6))
check("never reset: the position is finished when the index falls 50% from the purchase (49 < 50), and stays at 0 although the index recovers",
      term_c == 3 and np.allclose(nav_c, [1.0, 0.6, 0.2, 0, 0, 0]), (term_c, nav_c))

# ---- the study's bookkeeping on made-up data: ratios of one full-history NAV equal fresh runs from a reset date ----
from calendar_letf import products, study  # noqa: E402

u_s = walk("2010-01-04", 1800, 31, vol=0.011, drift=0.0004)
r_s = pd.Series(0.02, index=u_s.index)
spec_m = products.PRODUCTS["HYP_SPX_M"]
world = study.World("SPX", u_s, u_s, r_s, [spec_m], {spec_m.name: products.twin_of(spec_m)})
enc = study.ENCODINGS["fixed"]
check("study: month-end rows are the last trading day of each month, one per month (consecutive)",
      len(world.me) > 70 and (np.diff(world.dates.year.to_numpy()[world.me] * 12 + world.dates.month.to_numpy()[world.me]) == 1).all())
i0 = 5
s0, e0 = world.me[i0], world.me[i0 + 24]
full = world.nav("HYP_SPX_M", enc)
fresh = k.periodic_reset_series(u_s.iloc[s0:e0 + 1], r_s.iloc[s0:e0 + 1], reset="monthly", L=2.0, spread_per_nav=enc.spread_per_nav,
                                fee=spec_m.fee, early_drop=0.35, trigger=u_s.iloc[s0:e0 + 1])
check("study: nav[e] / nav[s] of the full-history monthly NAV equals a fresh run started on that month-end (1e-12)",
      abs(full.iloc[e0] / full.iloc[s0] - fresh.iloc[-1]) < 1e-12, (full.iloc[e0] / full.iloc[s0], fresh.iloc[-1]))
tw_full = world.nav("TWIN_HYP_SPX_M", enc)
tw_fresh = k.daily_reset_series(u_s.iloc[s0:e0 + 1], r_s.iloc[s0:e0 + 1], L=2.0, spread_per_nav=enc.spread_per_nav, fee=spec_m.fee)
check("study: the same for the daily twin from any row (1e-12)", abs(tw_full.iloc[e0] / tw_full.iloc[s0] - tw_fresh.iloc[-1]) < 1e-12)
ms_rows, _ = study.multi_start(world, enc, horizons_years=(1, 3))
row3 = next(r for r in ms_rows if r["horizon_years"] == 3)
ws_c, ws_t = world.stats("HYP_SPX_M", enc, "level", 36), world.stats("TWIN_HYP_SPX_M", enc, "level", 36)
check("study: the reported 3-year median gap is the median of (calendar CAGR - twin CAGR) over every month-end start",
      abs(row3["gap_median"] - np.median(ws_c["cagr"] - ws_t["cagr"])) < 1e-15 and row3["n_starts"] == len(world.me) - 36)
# the margin benchmark: one run per start equals a closed-form check at zero costs, and the multi-start number matches a direct run
zero = study.ZERO_COSTS
mg = world.margin_navs(zero, spec_m.fee, (12,))
i1 = 7
want = 2.0 * u_s.iloc[world.me[i1 + 12]] / u_s.iloc[world.me[i1]] - 1.0
check("study: margin benchmark at zero costs = 2 x u_e/u_s - 1 at each start (1e-12)", abs(mg[12][i1] - want) < 1e-12 or want <= 0 and mg[12][i1] == 0.0, (mg[12][i1], want))
mg_fixed = world.margin_navs(enc, spec_m.fee, (12,))
direct = world.margin_slice(enc, spec_m.fee, world.me[i1], world.me[i1 + 12])[-1]
check("study: margin_navs and margin_slice agree for the same start (1e-14)", abs(mg_fixed[12][i1] - direct) < 1e-14)
spec_w = products.PRODUCTS["HYP_SPX_W"]
spec_3x = replace(spec_w, L=3.0, costs=replace(spec_w.costs, turns=3.0, label="x"))      # a 3x copy (turns follow L)
raises("study: a 2x cost encoding refuses a 3x product unless carried with encoding_at (B17 guard)",
       lambda: study.kernel_kwargs(spec_3x, enc), "is set for L = 2 but the product has L = 3")
check("study: the rate encoding multiplies the rate by 1.3 and the fixed one leaves it alone",
      np.allclose(study.scaled_rate(r_s, study.ENCODINGS["rate"]), 0.026) and np.allclose(study.scaled_rate(r_s, enc), 0.02))
check("study: both fitted encodings and every sensitivity are labeled ASSUMED",
      all(e.status == "ASSUMED" for e in list(study.ENCODINGS.values()) + list(study.SENSITIVITIES.values())))

# ---- margin_comparison on a planted crash (R2 step 3): finished windows, survivors, mean next to median ----
# A flat index with ONE day on which it falls 60% (a gap): every buy-once margin position held across that day is finished
# (equity 2 x 0.4 - 1 - costs < 0); every other window is flat and survives. So the finished count must equal the number of
# month-end starts whose window contains that day, and the daily twin (2 x -60% wipes it out) finishes in the same windows.
from calendar_letf import nyse as _nyse  # noqa: E402

_days = pd.DatetimeIndex(_nyse.sessions(pd.Timestamp("2000-01-03").date(), pd.Timestamp("2006-12-29").date()))
_lvl = np.full(len(_days), 100.0)
_crash = 1300
_lvl[_crash:] = 40.0
_u = pd.Series(_lvl, index=_days, name="CRASH")
_specs = [products.PRODUCTS[p] for p in study.PRODUCT_NAMES["SPX"]]
_w = study.World("SPX", _u, _u, pd.Series(0.03, index=_days), _specs, {s.name: products.twin_of(s) for s in _specs})
_mc = study.margin_comparison(_w, enc, horizons_years=(1,))
_row = next(r for r in _mc if r["product"] == "SPYQ")
_s, _e = _w.month_pairs(12)
_want = int(((_s < _crash) & (_crash <= _e)).sum())
check("margin_comparison, planted crash: the finished count is the number of 12-month windows that contain the crash day",
      _row["margin_finished"] == _want and _row["n_starts"] == len(_s) and _row["n_survivors"] == len(_s) - _want and _want > 0, (_row["margin_finished"], _want))
check("margin_comparison, planted crash: the finished share is finished / starts", abs(_row["margin_finished_share"] - _want / len(_s)) < 1e-15)
_mg = _w.margin_navs(enc, products.PRODUCTS["SPYQ"].fee, tuple(sorted(set(study.CURVE_MONTHS) | {12})))[12]
_fin = _mg <= 0
_st = _w.stats("SPYQ", enc, "level", 12)
check("margin_comparison, planted crash: all-window mean x starts = survivors' mean x survivors + the sum over finished windows of (fund CAGR + 1), "
      "because a finished margin position counts as -100%",
      abs(_row["fund_minus_margin_mean"] * _row["n_starts"] - (_row["fund_minus_margin_mean_survivors"] * _row["n_survivors"] + (_st["cagr"][_fin] + 1.0).sum())) < 1e-9
      and int(_fin.sum()) == _want, (_row["fund_minus_margin_mean"], _row["fund_minus_margin_mean_survivors"]))
check("margin_comparison, planted crash: the median and mean are both reported for the fund, the twin and the margin position",
      all(k_ in _row for k_ in ("fund_minus_margin_median", "fund_minus_margin_mean", "twin_minus_margin_median", "twin_minus_margin_mean",
                                "margin_cagr_median", "margin_cagr_mean", "margin_cagr_median_survivors")))
check("margin_comparison, planted crash: on the flat survivors the margin position loses only its costs (survivor median margin CAGR between -8% and 0)",
      -0.08 < _row["margin_cagr_median_survivors"] < 0.0, _row["margin_cagr_median_survivors"])

# ---- the survivor interval (R2 step 12f): phase-pooled over the SURVIVING windows, finished windows NaN IN PLACE ----
# A noisy index with TWO one-day -60% crashes six months apart: every 12-month window containing either day finishes the
# margin position, an 18-start block (12 + 6), which is not a multiple of the 12-month step. Dropping those starts first would
# shift every later start into another phase; NaN in place keeps each window in its own phase.
from calendar_letf import stats as _stats  # noqa: E402

_rng2 = np.random.default_rng(8)
_lvl2 = 100.0 * np.exp(np.cumsum(_rng2.normal(0.0004, 0.01, len(_days))))
_c1, _c2 = 700, 700 + 126
_lvl2[_c1:] *= 0.40
_lvl2[_c2:] *= 0.40
_u2 = pd.Series(_lvl2, index=_days, name="CRASH2")
_w2 = study.World("SPX", _u2, _u2, pd.Series(0.03, index=_days), _specs, {s.name: products.twin_of(s) for s in _specs})
_row2 = next(r for r in study.margin_comparison(_w2, enc, horizons_years=(1,)) if r["product"] == "SPYQ")
_s2, _e2 = _w2.month_pairs(12)
_yrs2 = (_w2.dates[_e2] - _w2.dates[_s2]).days.to_numpy() / 365.25
_term2 = _w2.margin_navs(enc, products.PRODUCTS["SPYQ"].fee, tuple(sorted(set(study.CURVE_MONTHS) | {12})))[12]
with np.errstate(divide="ignore", invalid="ignore"):
    _mc2 = np.where(_term2 > 0, np.where(_term2 > 0, _term2, 1.0) ** (1.0 / _yrs2) - 1.0, -1.0)
_g2 = _w2.stats("SPYQ", enc, "level", 12)["cagr"] - _mc2
_alive2 = _term2 > 0
_want_in_place = _stats.phase_pooled_mean(np.where(_alive2, _g2, np.nan), 12)
_dropped = _stats.phase_pooled_mean(_g2[_alive2], 12)
check("survivor interval, two planted crashes: the finished block is not a multiple of the 12-month step (so the treatment matters)",
      int((~_alive2).sum()) % 12 != 0 and int((~_alive2).sum()) == _row2["margin_finished"], (int((~_alive2).sum()), _row2["margin_finished"]))
check("survivor interval: mean, lo, hi and df equal stats.phase_pooled_mean on the gaps with the finished windows NaN in place (1e-15)",
      all(abs(_row2[f"fund_minus_margin_survivors_indep_{k_}"] - _want_in_place[k_]) < 1e-15 for k_ in ("mean", "lo", "hi"))
      and _row2["fund_minus_margin_survivors_indep_df"] == _want_in_place["df"], (_row2["fund_minus_margin_survivors_indep_mean"], _want_in_place["mean"]))
check("survivor interval: dropping the finished windows first would give a different interval (the break case the code avoids)",
      abs(_dropped["mean"] - _want_in_place["mean"]) > 1e-12 or abs(_dropped["se"] - _want_in_place["se"]) > 1e-12, (_dropped["mean"], _want_in_place["mean"]))
check("survivor interval: the noisy flag is the interval covering zero", _row2["fund_minus_margin_survivors_noisy"] == _stats.covers_zero(_want_in_place["lo"], _want_in_place["hi"]))
