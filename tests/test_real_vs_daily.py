"""BACKLOG B19, section 7 of scripts/run_validate_live.py: the live calendar funds against the real 2x daily funds.

Part A, planted (made-up data, closed forms): the daily fund's hard test (peer_checks), its fee path (peer_fee_series)
and the real-vs-real row (real_vs_real_daily) on a world built from the kernels with known costs, whose fits must
give the planted costs back. Part B reads results/validate_live.json and the two reference tables with the csv
module and re-derives the hard test's payout sums.
"""
import csv
import importlib.util
import json

import numpy as np
import pandas as pd

from _harness import ROOT, check
from calendar_letf import kernel, products

spec_ = importlib.util.spec_from_file_location("run_validate_live", ROOT / "scripts" / "run_validate_live.py")
RV = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(RV)

# ---- A1. peer_checks: a flat $50 price and one $0.50 payout give exactly +1.00% ----
ix = pd.bdate_range("2024-05-01", "2025-06-30")
px = pd.Series(50.0, index=ix)
div = pd.Series([0.50], index=[pd.Timestamp("2024-12-23")])


def hl_row(tr_pct, dist_total):
    return pd.DataFrame([dict(fiscal_year_end=pd.Timestamp("2025-05-31"), total_return_market_pct=tr_pct,
                              total_return_nav_pct=tr_pct, dist_total=dist_total)])


ok = RV.peer_checks("X", px, div, hl_row(1.00, -0.50))[0]
check("peer_checks: flat price + one 1% payout -> rebuilt +1.00% and payouts 0.50, passed",
      abs(ok["total_return_rebuilt_pct"] - 1.0) < 1e-9 and abs(ok["payouts"] - 0.5) < 1e-12 and ok["passed"], ok)
check("peer_checks: the fiscal year runs from the last close on or before 2024-05-31 to the last on or before 2025-05-31",
      ok["start_row"] == "2024-05-31" and ok["end_row"] == "2025-05-30", (ok["start_row"], ok["end_row"]))
check("peer_checks BREAK: a filed return 0.03 points away fails (tolerance 0.02)",
      not RV.peer_checks("X", px, div, hl_row(1.03, -0.50))[0]["passed"])
check("peer_checks BREAK: a filed payout one cent away fails (tolerance half a cent)",
      not RV.peer_checks("X", px, div, hl_row(1.00, -0.51))[0]["passed"])
edge = RV.peer_checks("X", px, pd.Series([0.50], index=[pd.Timestamp("2024-05-31")]), hl_row(0.0, 0.0))[0]
check("peer_checks: a payout ON the previous year-end belongs to the previous year (window (s, e])",
      edge["payouts"] == 0.0 and abs(edge["total_return_rebuilt_pct"]) < 1e-12 and edge["passed"], edge)

# ---- A2. peer_fee_series: each fiscal year's ratio over its own year, the last one held after its end ----
hl2 = pd.DataFrame([dict(fiscal_year_end=pd.Timestamp("2025-05-31"), expense_ratio_net_pct=0.87),
                    dict(fiscal_year_end=pd.Timestamp("2026-05-31"), expense_ratio_net_pct=0.84)])
fx = pd.bdate_range("2024-05-01", "2026-09-30")
fee = RV.peer_fee_series(hl2, fx)
check("peer_fee_series: 2025-05-30 carries FY2025, 2025-06-02 FY2026, 2026-09-30 still FY2026, 2024-05-01 FY2025 (carried back)",
      [round(fee[pd.Timestamp(d)], 6) for d in ("2025-05-30", "2025-06-02", "2026-09-30", "2024-05-01")]
      == [0.0087, 0.0084, 0.0084, 0.0087], fee[[pd.Timestamp(d) for d in ("2025-05-30", "2025-06-02", "2026-09-30")]].tolist())

fd_ = RV.peer_fee_series(hl2, pd.date_range("2025-05-29", "2025-06-02"))     # calendar days: the boundary itself
check("peer_fee_series BOUNDARY: May 31 itself is the last day of its fiscal year; June 1 starts the next",
      round(fd_[pd.Timestamp("2025-05-31")], 6) == 0.0087 and round(fd_[pd.Timestamp("2025-06-01")], 6) == 0.0084,
      fd_.tolist())

# ---- A3. real_vs_real_daily on a planted world: both funds ARE the kernels at known costs ----
rng = np.random.default_rng(7)
ux = pd.bdate_range("2024-09-30", "2026-09-30")
u = pd.Series(100.0 * np.exp(np.cumsum(np.r_[0.0, rng.normal(0.0004, 0.011, len(ux) - 1)])), index=ux)
rate = pd.Series(0.04, index=ux)
spec = products.PRODUCTS["SPYQ"]
S_CAL, F_CAL, S_DAY, F_DAY = 0.020, 0.0100, 0.005, 0.0090
cal = kernel.periodic_reset_series(u, rate, reset="quarterly", L=2.0, spread_per_nav=S_CAL, fee=F_CAL, early_drop=spec.early_drop,
                                   early_mode="level", trigger=u).iloc[1:]          # the first price bar is one session later
day = kernel.daily_reset_series(u, rate, L=2.0, spread_per_nav=S_DAY, fee=F_DAY)
row = RV.real_vs_real_daily("SPYQ", spec, cal, pd.Series(F_CAL, index=ux), day, pd.Series(F_DAY, index=ux), u, u, rate)
check("real_vs_real_daily: the fits give the planted residual costs back (2.00% and 0.50% of NAV, to 1e-5)",
      abs(row["residual_spread_calendar"] - S_CAL) < 1e-5 and abs(row["residual_spread_daily"] - S_DAY) < 1e-5,
      (row["residual_spread_calendar"], row["residual_spread_daily"]))
check("real_vs_real_daily: fee difference = 0.10 points, window from the first price bar to 2026-09-30",
      abs(row["fee_difference"] - 0.001) < 1e-12 and row["start"] == "2024-10-01" and row["end"] == "2026-09-30", row)
def cagr_(s):
    """Plain compound growth a year (an independent one-liner, not validate.cagr)."""
    return (s.iloc[-1] / s.iloc[0]) ** (365.25 / (s.index[-1] - s.index[0]).days) - 1.0


m0_cal = kernel.periodic_reset_series(u, rate, reset="quarterly", L=2.0, spread_per_nav=0.0, fee=0.0,
                                      early_drop=spec.early_drop, trigger=u).iloc[1:]
m0_day = kernel.daily_reset_series(u, rate, L=2.0, spread_per_nav=0.0, fee=0.0).iloc[1:]
check("real_vs_real_daily: model gap = equal-cost calendar less daily kernel on the shared dates (independent run)",
      abs(row["model_gap"] - (cagr_(m0_cal) - cagr_(m0_day))) < 1e-12, row["model_gap"])
check("real_vs_real_daily: each cost drag = zero-cost kernel growth less the planted fund's growth (to 1e-6)",
      abs(row["cost_drag_calendar"] - (cagr_(m0_cal) - cagr_(cal))) < 1e-6
      and abs(row["cost_drag_daily"] - (cagr_(m0_day) - cagr_(day.iloc[1:]))) < 1e-6,
      (row["cost_drag_calendar"], cagr_(m0_cal) - cagr_(cal)))
check("real_vs_real_daily: the gap splits exactly into model gap - calendar drag + daily drag (error < 1e-6)",
      abs(row["decomposition_error"]) < 1e-6, row["decomposition_error"])
check("real_vs_real_daily: on the CAGR scale a drag is NOT the cost itself (the planted calendar fund pays 3.00% of NAV "
      "and loses a different amount: the reason the table shows drags, not cost differences)",
      abs(row["cost_drag_calendar"] - (S_CAL + F_CAL)) > 1e-3, row["cost_drag_calendar"])

# A crash world: the ETF falls 45% inside a quarter, so the calendar fund resets early. The fit must model the same
# trigger, or it cannot give the planted cost back.
u2 = u.copy()
crash = (u2.index >= pd.Timestamp("2025-02-03")) & (u2.index <= pd.Timestamp("2025-02-14"))
u2[u2.index >= pd.Timestamp("2025-02-03")] *= np.exp(np.cumsum(np.where(crash, np.log(0.55) / crash.sum(), 0.0)))[
    u2.index >= pd.Timestamp("2025-02-03")]
cal2 = kernel.periodic_reset_series(u2, rate, reset="quarterly", L=2.0, spread_per_nav=S_CAL, fee=F_CAL, early_drop=spec.early_drop,
                                    early_mode="level", trigger=u2)
day2 = kernel.daily_reset_series(u2, rate, L=2.0, spread_per_nav=S_DAY, fee=F_DAY)
row2 = RV.real_vs_real_daily("SPYQ", spec, cal2.iloc[1:], pd.Series(F_CAL, index=ux), day2, pd.Series(F_DAY, index=ux), u2, u2, rate)
check("real_vs_real_daily CRASH: the planted calendar fund resets early, and the fit (with the same trigger) gives "
      "its cost back to 1e-5", len(cal2.attrs["early_resets"]) >= 1 and len(row2["model_early_resets"]) >= 1
      and abs(row2["residual_spread_calendar"] - S_CAL) < 1e-5, (cal2.attrs["early_resets"], row2["residual_spread_calendar"]))

# ---- B. the results file and the reference tables ----
res = json.loads((ROOT / "results" / "validate_live.json").read_text(encoding="utf-8"))["real_vs_real_daily"]
with open(ROOT / "reference" / "daily_etf_distributions.csv", newline="", encoding="utf-8") as f:
    DIST = list(csv.DictReader(f))
with open(ROOT / "reference" / "daily_etf_highlights.csv", newline="", encoding="utf-8") as f:
    HL = list(csv.DictReader(f))
check("results: the daily funds' hard test PASSES on all four fiscal years (SSO, QLD x FY2025, FY2026)",
      res["peer_hard_test"] == "PASS" and len(res["peer_checks"]) == 4 and all(c["passed"] for c in res["peer_checks"]))
indep = {}
for h in HL:
    e = h["fiscal_year_end"]
    s = f"{int(e[:4]) - 1}{e[4:]}"
    indep[(h["ticker"], e)] = (sum(float(d["amount_per_share"]) for d in DIST if d["ticker"] == h["ticker"] and s < d["ex_date"] <= e),
                               -float(h["dist_total"]))
check("reference: each fiscal year's payouts (csv reader) are within half a cent of the N-CSR per-share total",
      len(indep) == 4 and all(abs(a - b) <= 0.005 for a, b in indep.values()), indep)
check("reference: every highlights row cites the FY2026 ProShares Trust N-CSR accession",
      {h["accession"] for h in HL} == {"0001398344-26-013617"})
check("results: the rebuilt returns in the file equal the filed market returns to the printed 0.01",
      all(abs(c["total_return_rebuilt_pct"] - c["total_return_market_filed_pct"]) < 0.005 for c in res["peer_checks"]),
      [round(c["tr_error_pp"], 4) for c in res["peer_checks"]])
pairs = [(r["calendar_fund"], r["daily_fund"]) for r in res["rows"]]
check("results: three rows, SPYQ vs SSO, MQQQ vs QLD, QQQP vs QLD, each ending 2026-09-30",
      pairs == [("SPYQ", "AMEX:SSO"), ("MQQQ", "AMEX:QLD"), ("QQQP", "AMEX:QLD")] and {r["end"] for r in res["rows"]} == {"2026-09-30"},
      pairs)
check("results: every row's gap splits into model gap - calendar drag + daily drag (error < 1e-5)",
      all(abs(r["decomposition_error"]) < 1e-5 for r in res["rows"]), [r["decomposition_error"] for r in res["rows"]])
check("results: in every row the calendar fund's cost drag exceeds the model's design edge plus the daily fund's drag "
      "(why each real calendar fund trailed its daily peer)",
      all(r["cost_drag_calendar"] > r["model_gap"] + r["cost_drag_daily"] and r["gap"] < 0 for r in res["rows"]),
      [(round(r["cost_drag_calendar"], 4), round(r["model_gap"], 4), round(r["cost_drag_daily"], 4)) for r in res["rows"]])
check("results: no interval at two years; each row says so",
      all(r["interval"] is None and "too noisy" in r["interval_note"] for r in res["rows"]))
