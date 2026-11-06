"""Planted-answer tests for calendar_letf/navtr.py (BACKLOG B19): total return from NAV plus reported distributions.

Made-up data only. Independent routes: F17's hand formula for the leverage after a fall, the kernel's own calendar
fund (a second implementation of the drifting leverage), and a planted payout whose total return is known exactly.
"""
import numpy as np
import pandas as pd

from _harness import check, raises  # noqa: I001  (must come first: puts the repo root on sys.path)
from calendar_letf import kernel as k
from calendar_letf import navtr, periods

# ---- effective leverage ----
lev = navtr.effective_leverage([0.10, -0.05, 0.0], 2.0, [False, False, False])
check("effective_leverage: 2 at the reset; after +10% it is 2 x 1.1 / 1.2 = 1.8333 (hand-computed)",
      abs(lev[0] - 2.0) < 1e-15 and abs(lev[1] - 2.0 * 1.1 / 1.2) < 1e-15, lev)
lev_f = navtr.effective_leverage([-0.20, 0.0], 2.0, [False, False])
check("effective_leverage: after a 20% fall it is 2(1-f) / (1-2f) = 1.6 / 0.6 = 2.6667 (F17's formula, an independent route)",
      abs(lev_f[1] - 1.6 / 0.6) < 1e-14, lev_f)
check("effective_leverage: a daily-reset fund (every row a reset) holds L every day",
      np.allclose(navtr.effective_leverage([0.1, -0.2, 0.05], 1.5, [True, True, True]), 1.5))

# ---- residual: zero on a model fund, second implementation = the kernel ----
rng = np.random.default_rng(19)
ix = pd.bdate_range("2015-01-01", periods=400)
u = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, len(ix)))), index=ix)
nav_m = k.periodic_reset_series(u, 0.0, reset="monthly", L=2.0, spread_per_nav=0.0, fee=0.0, early_drop=None)
ends = periods.period_end_flags(ix, "monthly")             # the kernel's own reset rows (NYSE month ends)
idx_ret = u.pct_change().fillna(0.0).to_numpy()
res = navtr.residual(nav_m, idx_ret, 2.0, ends)
check("residual: on the kernel's own 2x monthly fund (zero costs) the unexplained part is 0 on every day (to 1e-12)",
      float(res.abs().max()) < 1e-12, float(res.abs().max()))
nav_d = k.daily_reset_series(u, 0.0, L=1.5, spread_per_nav=0.0, fee=0.0)
res_d = navtr.residual(nav_d, idx_ret, 1.5, np.ones(len(ix), dtype=bool))
check("residual: on the kernel's 1.5x daily fund it is 0 on every day (to 1e-12)", float(res_d.abs().max()) < 1e-12)

# ---- a planted payout: find its ex-date, add it back, recover the fund exactly ----
nav_true = nav_m * 50.0                                   # a fund that never paid out
t_ex = ix[230]
D = 0.08 * float(nav_true.loc[t_ex])                       # an 8% capital-gain payout
paid = nav_true.copy()
paid.loc[t_ex:] = nav_true.loc[t_ex:] * (nav_true.loc[t_ex] - D) / nav_true.loc[t_ex]
res_p = navtr.residual(paid, idx_ret, 2.0, ends)
found = navtr.locate_ex_date(res_p, paid, ix[200], ix[260], D)
check("locate_ex_date: the planted 8% payout's ex-date is found exactly", found == t_ex, (found, t_ex))
tr = navtr.total_return(paid, {t_ex: D})
check("total_return: adding the payout back recovers the fund that never paid out (to 1e-12)",
      float(np.max(np.abs(tr.to_numpy() - (nav_true / nav_true.iloc[0]).to_numpy()))) < 1e-12)
check("locate_ex_date: None when no day falls by half the payout", navtr.locate_ex_date(res, nav_m, ix[10], ix[50], 5.0) is None)
small = paid.copy()
D2 = 0.004 * float(nav_true.loc[ix[120]])                  # a 0.4% income payout: small but still found
small.loc[ix[120]:] = small.loc[ix[120]:] * (small.loc[ix[120]] - D2) / small.loc[ix[120]]
check("locate_ex_date: a 0.4% payout is found too (the model removes the market move)",
      navtr.locate_ex_date(navtr.residual(small, idx_ret, 2.0, ends), small, ix[100], ix[140], D2) == ix[120])

# ---- a payout paid in two parts (half in one month, half later) ----
two = nav_true.copy()
t1, t2 = ix[150], ix[180]
D1, D2b = 0.08 * float(two.loc[t1]), 0.06 * float(two.loc[t2])
two.loc[t1:] = two.loc[t1:] * (two.loc[t1] - D1) / two.loc[t1]
D2 = D2b * float(two.loc[t2]) / float(nav_true.loc[t2])   # 6% of the NAV on the day it is paid
two.loc[t2:] = two.loc[t2:] * (two.loc[t2] - D2) / two.loc[t2]
parts = navtr.locate_ex_dates(navtr.residual(two, idx_ret, 2.0, ends), two, ix[140], ix[200], D1 + D2)
check("locate_ex_dates: a reported payout paid in two parts (8% then 6%) is placed on both days with the right amounts (to 1e-9)",
      [p[0] for p in parts] == [t1, t2] and abs(parts[0][1] - D1) < 1e-9 and abs(parts[1][1] - D2) < 1e-9, parts)
tr2 = navtr.total_return(two, dict(parts))
check("locate_ex_dates + total_return: the two-part payout added back recovers the fund that never paid (to 1e-9)",
      float(np.max(np.abs(tr2.to_numpy() - (nav_true / nav_true.iloc[0]).to_numpy()))) < 1e-9)
one = navtr.locate_ex_dates(navtr.residual(paid, idx_ret, 2.0, ends), paid, ix[200], ix[260], D)
check("locate_ex_dates: a single payout stays on one day with the whole amount", one == [(t_ex, D)], one)

# ---- splits: apply only the ones the data still shows ----
base = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0], index=pd.bdate_range("2018-04-04", periods=5))
raw = base.copy()
raw.iloc[3:] = raw.iloc[3:] / 5.0                          # a 5-for-1 split on day 4 that the vendor did NOT adjust
fixed, log = navtr.apply_splits(raw, [(base.index[3], 5.0)])
check("apply_splits: an unadjusted 5-for-1 split is applied (earlier rows / 5), and the series is continuous again",
      np.allclose(fixed.to_numpy(), (base / 5.0).to_numpy()) and log[0][2] == "applied", (fixed.to_numpy(), log))
again, log2 = navtr.apply_splits(base / 5.0, [(base.index[3], 5.0)])
check("apply_splits: a split the vendor already adjusted is left alone (no double adjustment)",
      np.allclose(again.to_numpy(), (base / 5.0).to_numpy()) and log2[0][2] == "already adjusted")
rev = base.copy()
rev.iloc[2:] = rev.iloc[2:] * 7.0                          # a 1-for-7 reverse split, unadjusted
fixed_r, log3 = navtr.apply_splits(rev, [(base.index[2], 1.0 / 7.0)])
check("apply_splits: an unadjusted 1-for-7 reverse split is applied (earlier rows x 7)",
      np.allclose(fixed_r.to_numpy(), (base * 7.0).to_numpy()) and log3[0][2] == "applied")
check("apply_splits: a split dated outside the data is reported, not applied",
      navtr.apply_splits(base, [(pd.Timestamp("2010-01-04"), 5.0)])[1][0][2] == "outside the data")

# ---- snap_basis: a stale close cannot bend the share basis ----
check("snap_basis: a raw 0.1919 (a stale close; true 0.2) with splits 1-for-10, 1-for-5, 5-for-1 snaps to 0.2",
      navtr.snap_basis(0.1919, (0.1, 0.2, 5.0)) == (0.2, "snapped"))
check("snap_basis: an exact 1.0 stays exact; 5.0 is reachable through the 1-for-5 reverse split (1 / 0.2)",
      navtr.snap_basis(1.0, (0.2,)) == (1.0, "exact") and navtr.snap_basis(5.0, (0.2,))[0] == 5.0)
raises("snap_basis refuses a factor no split product explains (0.5 with only a 5-for-1 split)",
       lambda: navtr.snap_basis(0.5, (5.0,)), "not within")

# ---- payout_windows: half-years from the annual and semiannual rows ----
def _row(s, e, kind, inc, gain, nb=10.0, ne=11.0):
    return dict(period_start=s, period_end=e, report_type=kind, nav_begin=str(nb), nav_end=str(ne), dist_net_income=str(inc),
                dist_realized_gains=str(gain), dist_return_of_capital="", dist_total=str(inc + gain), total_return_pct="1")


wins = navtr.payout_windows([_row("2020-08-01", "2021-07-31", "annual", 0.5, 3.0, 10.0, 12.0),
                             _row("2020-08-01", "2021-01-31", "semiannual", 0.2, 1.0, 10.0, 11.0),
                             _row("2021-08-01", "2022-01-31", "semiannual", 0.1, 0.0, 12.0, 13.0)])
h2 = {w["component"]: w for w in wins if w["start"] == "2021-02-01"}
check("payout_windows: the second half = annual - first half (income 0.5 - 0.2 = 0.3, gains 3.0 - 1.0 = 2.0), from the "
      "half-year's closing NAV", abs(h2["dist_net_income"]["amount"] - 0.3) < 1e-12
      and abs(h2["dist_realized_gains"]["amount"] - 2.0) < 1e-12 and h2["dist_net_income"]["nav_report"] == 11.0, wins)
check("payout_windows: a half-year with no annual report yet stands alone (2021-08-01 to 2022-01-31, income 0.1)",
      any(w["start"] == "2021-08-01" and w["component"] == "dist_net_income" and w["amount"] == 0.1 for w in wins))
check("payout_windows: 3 components x (2 halves + 1 standalone half) = 9 windows", len(wins) == 9, len(wins))

# ---- rebuild: the largest payout of a window is placed first ----
joint = nav_true.copy()
tj, tn = ix[300], ix[290]                                  # tj: gains 6% + income 0.3% on ONE day; tn: a 0.25% decoy
g_amt, i_amt = 0.06 * float(joint.loc[tj]), 0.003 * float(joint.loc[tj])
joint.loc[tj:] = joint.loc[tj:] * (joint.loc[tj] - g_amt - i_amt) / joint.loc[tj]
res_j = navtr.residual(joint, idx_ret, 2.0, ends)
res_j.loc[tn] -= 0.0025                                    # a noise day that matches a 0.3% payout better than nothing
wins_j = [dict(start=str(ix[280].date()), end=str(ix[320].date()), component="dist_net_income", amount=i_amt, nav_report=float(joint.loc[ix[279]])),
          dict(start=str(ix[280].date()), end=str(ix[320].date()), component="dist_realized_gains", amount=g_amt, nav_report=float(joint.loc[ix[279]]))]
tr_j, ev_j, log_j = navtr.rebuild(joint, res_j, wins_j)
check("rebuild: gains and income paid on the same day both land on that day although the income is listed first and a "
      "0.25% decoy day exists (largest first)", list(ev_j) == [tj] and abs(ev_j[tj] - g_amt - i_amt) < 1e-9, ev_j)
small_first = navtr.locate_ex_date(res_j, joint, ix[280], ix[320], i_amt)
check("rebuild (break case): placed on its own first, the 0.3% income would go to the decoy day; this is what "
      "largest-first prevents", small_first == tn, small_first)
check("rebuild: the 0.3% income is marked undatable (under 0.5% of NAV), the 6% gains datable",
      [x["datable"] for x in log_j] == [True, False], [(x["component"], x["datable"]) for x in log_j])

# ---- anchor_bound: only undatable payouts whose window straddles an end of the anchor ----
_log = [dict(start="2019-10-01", end="2020-03-31", frac=0.002, datable=False),
        dict(start="2019-04-01", end="2019-09-30", frac=0.003, datable=False),
        dict(start="2019-10-01", end="2020-03-31", frac=0.05, datable=True)]
check("anchor_bound: calendar 2019 is straddled at its end by the Oct-Mar window only: bound 0.002 (the 0.003 lies "
      "wholly inside 2019; the datable 5% never counts)", abs(navtr.anchor_bound(_log, "2018-12-31", "2019-12-31") - 0.002) < 1e-15)
check("anchor_bound: a window that ends on the anchor date does not straddle it (bound 0)",
      navtr.anchor_bound(_log, "2018-12-31", "2019-09-30") == 0.0)

# ---- report_self_consistent ----
check("report_self_consistent: no distribution and TR = NAV change (10 -> 11, 10.00%) is consistent",
      navtr.report_self_consistent(dict(dist_total="0", nav_begin="10", nav_end="11", total_return_pct="10.00")))
check("report_self_consistent: no distribution but TR -2.40% while the NAV change is -5.37% is not",
      not navtr.report_self_consistent(dict(dist_total="0", nav_begin="100", nav_end="94.63", total_return_pct="-2.40")))
check("report_self_consistent: a row with a distribution cannot be judged by its NAV alone (True)",
      navtr.report_self_consistent(dict(dist_total="1.2", nav_begin="100", nav_end="94.63", total_return_pct="-2.40")))

# ---- basis factor and period return ----
check("basis_factor: after a 5-for-1 split the series NAV 20 vs the report's 100 gives 0.2; a 1-for-5 reverse split gives 5",
      navtr.basis_factor(20.0, 100.0) == 0.2 and navtr.basis_factor(500.0, 100.0) == 5.0)
s = pd.Series([1.0, 1.1, 1.21, 1.331], index=pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-04"]))
check("period_return: from the close before the start to the end: 1.331 / 1.1 - 1 = 21% (hand-computed)",
      abs(navtr.period_return(s, "2020-02-01", "2020-02-04") - 0.21) < 1e-12)
raises("period_return refuses a period with no row before it", lambda: navtr.period_return(s, "2020-01-01", "2020-02-04"), "no row before")
raises("total_return refuses an ex-date that is not a row", lambda: navtr.total_return(s, {pd.Timestamp("2020-02-01"): 0.1}), "not a row")


# ---- the half-payout guard at its boundary (re-grade 2026-11-06: a 0.5 -> 0.1 mutant of the threshold survived) ----
_ix = pd.bdate_range("2021-01-04", periods=30)
_nav = pd.Series(100.0, index=_ix)
_res = pd.Series(0.0, index=_ix)
_res.iloc[10] = -0.3 * 1.0 / 100.0               # a day that falls by 30% of a payout of 1 on a NAV of 100: below the half
check("locate_ex_date BREAK: a day that falls by only 30% of the payout is not an ex-date (None; a 10% threshold would take it)",
      navtr.locate_ex_date(_res, _nav, _ix[1], _ix[-1], 1.0) is None)
_res.iloc[20] = -0.6 * 1.0 / 100.0               # and one that falls by 60% of it: above the half, so it is found
check("locate_ex_date: a day that falls by 60% of the payout is found, and the 30% day is still passed over",
      navtr.locate_ex_date(_res, _nav, _ix[1], _ix[-1], 1.0) == _ix[20])
