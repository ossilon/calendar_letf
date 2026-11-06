"""BACKLOG B19: tests for scripts/run_live_monthly.py and its published result.

Part A uses made-up data only: each helper the study relies on against a hand-computed or planted answer, plus the
kernel at the Direxion leverages (1.75x, 1.25x) on a planted month. Part B reads the committed results file and the
reference tables (SEC filing data) and re-derives the HARD TEST from them, so the suite FAILS (it never skips) if the
published result claims a pass the numbers do not support, or if a label appears that nobody has explained.
"""
import csv
import json
import sys

import numpy as np
import pandas as pd

from _harness import ROOT, check, raises  # noqa: I001  (must come first: puts the repo root on sys.path)
from calendar_letf import kernel as k
from calendar_letf import navtr, periods

sys.path.insert(0, str(ROOT / "scripts"))
import run_live_monthly as R  # noqa: E402

# ================================================================ part A: planted answers

# ---- the kernel at the B19 leverages: one full month at zero cost returns exactly 1 + L R ----
ix = pd.bdate_range("2021-01-29", "2021-03-31")
rng = np.random.default_rng(1925)
u = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.012, len(ix)))), index=ix)
feb_end = ix[ix.month == 2][-1]
R_feb = float(u.loc[feb_end] / u.iloc[0] - 1.0)
worst = 0.0
for L in (1.75, 1.25, 2.0):
    nav = k.periodic_reset_series(u, 0.0, reset="monthly", L=L, spread_per_nav=0.0, fee=0.0, early_drop=None)
    worst = max(worst, abs(float(nav.loc[feb_end]) - (1.0 + L * R_feb)))
check("kernel: a full calendar month at zero cost returns exactly 1 + L R at L = 1.75, 1.25 and 2 (to 1e-13)", worst < 1e-13, worst)

# ---- residual(): the regime split must sit on the filed date (planted) ----
ix2 = pd.bdate_range("2022-01-03", "2022-12-30")
u2 = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.011, len(ix2)))), index=ix2)
split = pd.Timestamp("2022-08-01")
a = k.periodic_reset_series(u2.loc[:"2022-07-29"], 0.0, reset="monthly", L=2.0, spread_per_nav=0.0, fee=0.0, early_drop=None)
b = k.periodic_reset_series(u2.loc["2022-07-29":], 0.0, reset="monthly", L=1.75, spread_per_nav=0.0, fee=0.0, early_drop=None)
fund = pd.concat([a, b.iloc[1:] * float(a.iloc[-1])])           # 2x monthly to July, then 1.75x from 2022-08-01
idx_ret = u2.pct_change().fillna(0.0).to_numpy()
right = R.residual(fund, idx_ret, [("2022-01-03", "2022-07-31", 2.0, "monthly", "SPX"), ("2022-08-01", None, 1.75, "monthly", "SPX")])
wrong = R.residual(fund, idx_ret, [("2022-01-03", "2022-08-31", 2.0, "monthly", "SPX"), ("2022-09-01", None, 1.75, "monthly", "SPX")])
check("residual: with the regime split on the filed date (2022-08-01) a planted 2x-then-1.75x fund leaves 0 on every day (to 1e-12)",
      float(right.abs().max()) < 1e-12, float(right.abs().max()))
check("residual (break case): the same fund with the split a month late leaves a visible residual in August (> 1e-4)",
      float(wrong.loc["2022-08"].abs().max()) > 1e-4, float(wrong.loc["2022-08"].abs().max()))

# ---- anchor_dates ----
s1, e1, n1 = R.anchor_dates(dict(as_of="2019-12-31", period="5y", start=""))
s2, e2, n2 = R.anchor_dates(dict(as_of="2013-06-30", period="ytd", start=""))
s3, e3, n3 = R.anchor_dates(dict(as_of="2015-12-31", period="since_inception", start="2014-11-28"))
s4, e4, n4 = R.anchor_dates(dict(as_of="2014-12-31", period="since_inception", start="2014-11-28"))
check("anchor_dates: 5y to 2019-12-31 runs from 2014-12-31, annualized over 5 years",
      (s1, e1, n1) == (pd.Timestamp("2014-12-31"), pd.Timestamp("2019-12-31"), 5.0))
check("anchor_dates: a year-to-date figure to 2013-06-30 runs from the 2012-12-31 close and is not annualized",
      (s2, n2) == (pd.Timestamp("2012-12-31"), None))
check("anchor_dates: since inception over 1.09 years is annualized over (end - start) / 365.25; under a year it is not",
      abs(n3 - 398 / 365.25) < 1e-12 and n4 is None, (n3, n4))

# ---- t_interval: hand-computed ----
mean, med, iv, kk = R.t_interval([0.01, 0.02, 0.03])
check("t_interval: values 1, 2, 3 % give mean 2 %, SE 0.577 %, half-width t(2) x SE = 4.303 x 0.577 = 2.484 %",
      abs(mean - 0.02) < 1e-15 and abs((iv[1] - iv[0]) / 2 - 4.302652729911275 * 0.01 / np.sqrt(3)) < 1e-6 and kk == 3, iv)
check("t_interval: one value gives no interval", R.t_interval([0.01])[2] is None)

# ---- yearly_log_gaps: one planted gap per year; a bad year-end close is stepped over ----
ix3 = pd.bdate_range("2018-12-24", "2021-12-31")
base = pd.Series(np.exp(np.linspace(0.0, 0.3, len(ix3))), index=ix3)
years = (ix3 - ix3[0]).days / 365.25
lead = base * np.exp(0.01 * years)                              # grows 1 % (log) a year faster
gaps = R.yearly_log_gaps(lead, base, pd.DatetimeIndex([]))
check("yearly_log_gaps: a series growing 1 % a year faster gives about 0.01 in each full year 2019-2021",
      sorted(gaps) == [2019, 2020, 2021] and all(abs(v - 0.01) < 2e-4 for v in gaps.values()), gaps)
glitched = base.copy()
glitched.loc["2020-12-31"] *= 1.05                              # a bad vendor close on a year end
plain = R.yearly_log_gaps(lead, glitched, pd.DatetimeIndex([]))
clean = R.yearly_log_gaps(lead, glitched, pd.DatetimeIndex(["2020-12-31"]))
check("yearly_log_gaps: a 5 % bad close on 2020-12-31 moves 5 points from 2020 into 2021, unless that day is marked bad",
      plain[2020] < -0.03 and plain[2021] > 0.05 and abs(clean[2020] - 0.01) < 2e-4 and abs(clean[2021] - 0.01) < 2e-4, (plain, clean))

# ---- glitch_days and stale_days ----
dd = pd.Series([0.0, 0.0, 0.10, -0.10, 0.0, 0.02, 0.0, 0.0], index=pd.bdate_range("2020-03-09", periods=8))
days, n_pairs, _ = R.glitch_days(dd)
check("glitch_days: a +10 % day undone the next day is one pair (both days); a 2 % move that stays is not a glitch",
      n_pairs == 1 and list(days) == list(dd.index[2:4]), (n_pairs, list(days)))
nav_s = pd.Series([10.0, 10.2, 10.2, 10.3, 10.3], index=pd.bdate_range("2012-12-26", periods=5))
ir_s = pd.Series([0.0, 0.01, 0.021, 0.004, 0.001], index=nav_s.index)
check("stale_days: a repeated close on a 2.1 % index day is stale; a repeat on a 0.1 % day is not",
      list(R.stale_days(nav_s, ir_s, nav_s.index)) == [nav_s.index[2]])

# ---- first_reset ----
idx_rows = pd.bdate_range("2014-11-20", "2014-12-10")
fund_rows = pd.bdate_range("2014-11-28", "2014-12-10")
check("first_reset: a regime that starts at inception starts at the fund's first close (no close before it)",
      R.first_reset(idx_rows, fund_rows, "2014-11-28") == pd.Timestamp("2014-11-28"))
check("first_reset: a later regime starts at the close before its first day (the reset that starts it)",
      R.first_reset(idx_rows, fund_rows, "2014-12-01") == pd.Timestamp("2014-11-28"))
gappy = idx_rows.delete(idx_rows.get_loc(pd.Timestamp("2014-11-28")))   # earlier rows, but no 2014-11-28 close
raises("first_reset refuses a start whose previous close the fund lacks although it has earlier rows",
       lambda: R.first_reset(idx_rows, gappy, "2014-12-01"), "although the fund has earlier rows")

# ================================================================ part B: the published result

with open(ROOT / "results" / "live_monthly.json", encoding="utf-8") as f:
    RES = json.load(f)


def ref(name):
    with open(ROOT / "reference" / "mutual_funds" / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


HL = {(r["fund"], r["period_start"], r["period_end"], r["report_type"]): r for r in ref("highlights.csv")}
AN = {(r["fund"], r["as_of"], r["period"], r["tax"]): r for r in ref("anchors.csv")}

check("live_monthly: the published hard test is a PASS", RES["hard_test"]["result"] == "PASS", RES["hard_test"])

gp = [p for p in RES["period_checks"] if p["gated"]]
bad_p = [p for p in gp if abs(p["rebuilt_pct"] - float(HL[(p["fund"], p["start"], p["end"], p["kind"])]["total_return_pct"]))
         > RES["hard_test"]["period_tol_pp"]]
check(f"live_monthly: every gated report period ({len(gp)}) is within {RES['hard_test']['period_tol_pp']} points of the "
      "figure in reference/mutual_funds/highlights.csv (re-derived from the table, not from the result's own error)",
      len(gp) >= 200 and not bad_p, bad_p[:3])

ga = [a for a in RES["anchor_checks"] if a["gated"]]
bad_a = [a for a in ga if abs(a["rebuilt_pct"] - float(AN[(a["fund"], a["as_of"], a["period"], a["tax"])]["return_pct"]))
         > a["tolerance_pp"]]
check(f"live_monthly: every gated 497K anchor ({len(ga)}) is within its tolerance of the figure in anchors.csv",
      len(ga) >= 250 and not bad_a, bad_a[:3])
def stated_tolerance(a):
    """0.05 + (1 + g) / n x (bound + cents) x 100: the annualizing of a level error C x (bound + cents), since
    d[C^(1/n)] = C^(1/n) / n x dC / C (n = 1 when the figure is not annualized)."""
    _s, _e, n = R.anchor_dates(AN[(a["fund"], a["as_of"], a["period"], a["tax"])])
    n = n or 1.0
    return R.ANCHOR_PRINT_PP + (1 + a["rebuilt_pct"] / 100) / n * (a["undatable_bound"] + a["cent_rounding"]) * 100


off = [a for a in ga if abs(a["tolerance_pp"] - stated_tolerance(a)) > 2e-3]
check("live_monthly: every anchor tolerance equals its stated parts recomputed here (0.05 base + cents + undatable "
      "bound, annualized; to 0.002 for the result's rounding)", not off, [(a["fund"], a["as_of"], a["tolerance_pp"], stated_tolerance(a)) for a in off[:3]])

rule_rows = sorted((p["fund"], p["start"], p["status"]) for p in RES["period_checks"] if p["in_window"] and p["status"] != "ok")
check("live_monthly: the only in-window report rows set aside are the three explained ones (RMQHX 2015 half-year REPORT "
      "INCONSISTENT; RYVYX 2012 and 2013 short year VENDOR NAV DIFFERS, the stale 2012-12-31 close)",
      rule_rows == [("RMQHX", "2015-04-01", "REPORT INCONSISTENT"), ("RYVYX", "2012-01-01", "VENDOR NAV DIFFERS"),
                    ("RYVYX", "2013-01-01", "VENDOR NAV DIFFERS")], rule_rows)
rmq = HL[("RMQHX", "2015-04-01", "2015-09-30", "semiannual")]
check("live_monthly: the RMQHX 2015 half-year really is inconsistent in the filing (no payout; TR -2.40 vs NAV change "
      "-5.37), re-derived from the table", not navtr.report_self_consistent(rmq), rmq["total_return_pct"])
stale_a = [a for a in RES["anchor_checks"] if a["in_window"] and a["status"] == "VENDOR CLOSE STALE"]
touch = all(a["fund"] == "RYVYX" and "2012-12-31" in (str(R.anchor_dates(AN[(a["fund"], a["as_of"], a["period"], a["tax"])])[0].date()),
                                                      str(R.anchor_dates(AN[(a["fund"], a["as_of"], a["period"], a["tax"])])[1].date()))
            for a in stale_a)
check("live_monthly: every anchor labeled VENDOR CLOSE STALE is a RYVYX figure that starts or ends on the stale "
      "2012-12-31 close", bool(stale_a) and touch, [(a["as_of"], a["period"]) for a in stale_a])

err = RES["errata"]
check("live_monthly: exactly one filing erratum (Nova 2011 1y), and its after-tax twin (-0.57) is reproduced",
      len(err) == 1 and err[0]["fund"] == "RYNVX" and err[0]["as_of"] == "2011-12-31" and err[0]["twin_reproduced"]
      and AN[("RYNVX", "2011-12-31", "1y", "after_distributions")]["return_pct"] == "-0.57", err)
check("live_monthly: no payout inside a check window is left unplaced", RES["hard_test"]["unplaced_payouts_in_window"] == 0)

# ---- the reference tables against their own evidence ----
evid = ref("regime_evidence.csv")
ok_reg = []
for r in ref("regimes.csv"):
    e = [x for x in evid if x["fund"] == r["fund"] and x["date"] == r["evidence_date"]]
    ok_reg.append(bool(e) and float(e[0]["leverage"]) == float(r["leverage"])
                  and (("month" in e[0]["reset"]) == (r["reset"] == "monthly")) and r["first_day"] >= r["evidence_date"])
check("regimes.csv: every regime's L and reset match its evidence row, and its first day is on or after the evidence date",
      len(ok_reg) == 11 and all(ok_reg), ok_reg)
dx = [(r["first_day"], r["leverage"], r["reset"]) for r in ref("regimes.csv") if r["fund"] == "DXSLX"]
check("regimes.csv: DXSLX is 2.5x daily from 2006-05-01, 2x monthly from 2009-10-01, 1.75x monthly from 2022-08-01",
      dx == [("2006-05-01", "2.5", "daily"), ("2009-10-01", "2", "monthly"), ("2022-08-01", "1.75", "monthly")], dx)
bad_split = []
for s in ref("splits.csv"):
    q, ratio = s["quote"].lower(), float(s["ratio"])
    if ("reverse" in q) != (ratio < 1.0):
        bad_split.append(s["fund"] + " " + s["date"])
check("splits.csv: every reverse split has a ratio below 1 and every forward split above 1 (read against the quote)",
      not bad_split and len(ref("splits.csv")) == 11, bad_split)
check("splits.csv: the vendor series needed the Direxion forward splits applied (3 applied in the result: DXSLX 2018, "
      "DXQLX 2014 and 2018), and no other split", sorted((f, d) for f, x in RES["funds"].items() for d, _r, st in x["splits"]
                                                         if st == "applied")
      == [("DXQLX", "2014-03-17"), ("DXQLX", "2018-04-09"), ("DXSLX", "2018-04-09")])
check("live_monthly: the monthly reset rows the study uses are the NYSE month ends (periods.period_end_flags)",
      R.periods is periods)

# ---- interval coverage (coverage.yearly_t_coverage at each row's own k): present, labeled, reproducible ----
from calendar_letf import coverage as cov  # noqa: E402
ivs = ([("fit", f["coverage"], f["interval"], f["yearly"].values(), f"fit {f['fund']} {f['first_day']} {f['label']}") for f in RES["fits"]]
       + [(kind, p[f"coverage_{kind}"], p[f"yearly_{kind}_interval"],
           (p["yearly_gap"].values() if kind == "gap" else
            [p["yearly_gap"][y] + p["fee_difference"] - p["yearly_model_gap"][y] for y in p["yearly_gap"]]),
           f"{kind} {p['calendar_fund']} {p['daily_fund']} {p['start']} {p['label']}")
          for p in RES["real_vs_real"] for kind in ("gap", "rest")])
check("coverage: every published yearly interval (k >= 3) carries a simulated coverage and a verdict that follows the floor",
      all((c is not None) == (iv is not None and len(list(v)) >= 3) for _k, c, iv, v, _s in ivs)
      and all(c["verdict"] == ("valid" if min(c["coverage_bootstrap"], c["coverage_ar1"]) >= R.COVERAGE_FLOOR else "too narrow")
              for _k, c, _iv, _v, _s in ivs if c), [(s, c and c["verdict"]) for _k, c, _iv, _v, s in ivs])
again = [(s, cov.yearly_t_coverage(list(v), seed=__import__("zlib").crc32(s.encode("utf-8")), runs=R.COVERAGE_RUNS) == {
    x: y for x, y in c.items() if x != "verdict"}) for _k, c, _iv, v, s in ivs if c]
check("coverage: each published coverage is re-derived exactly from the yearly values in the file and its seed key",
      again and all(ok for _s, ok in again), [s for s, ok in again if not ok])
rest_valid = sorted(p["calendar_fund"] + ("*" if p["label"] != "primary" else "") for p in RES["real_vs_real"]
                    if p["coverage_rest"] and p["coverage_rest"]["verdict"] == "valid")
check("coverage: the model-explains-the-funds claim rests on VALID rest intervals: DXSLX, DXQLX and RMQHX after its launch year",
      rest_valid == ["DXQLX", "DXSLX", "RMQHX*"], rest_valid)
check("coverage: no real-vs-real GAP interval of a primary row is valid (the edge's uncertainty is wider than printed)",
      all(p["coverage_gap"]["verdict"] == "too narrow" for p in RES["real_vs_real"] if p["label"] == "primary"),
      [(p["calendar_fund"], p["coverage_gap"]["verdict"]) for p in RES["real_vs_real"] if p["label"] == "primary"])
