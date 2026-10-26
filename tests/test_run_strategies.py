"""Planted-answer tests for the statistics that scripts/run_strategies.py adds to the timing-rule study (R2 steps 12d-12e):
summarize_windows (the phase-pooled interval and the too-few-windows flag), era_rows (the full-run edge by sub-era) and
era_tests (the era-difference z). The script is imported as a module; its main() does not run. A small fake "underlying"
object with piecewise-exponential wealth and NAV paths gives exact per-era CAGRs, so the edges are known to rounding.
"""
import importlib.util
import math

import numpy as np
import pandas as pd

from _harness import ROOT, check
from calendar_letf import metrics, stats

spec = importlib.util.spec_from_file_location("run_strategies", ROOT / "scripts" / "run_strategies.py")
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)

# ---- summarize_windows: the interval equals stats.phase_pooled_mean on the edges IN START ORDER, NaN kept in place ----
n = 400
rng = np.random.default_rng(21)
edge = rng.normal(0.002, 0.03, n)
edge[:7] = np.nan                                 # a rule with no signal for the first starts: NaN edges at the front
edge[100:107] = np.nan                            # and a gap inside: dropping it would shift every later start into another phase
arr = dict(edge=edge, cagr_s=rng.normal(0.1, 0.05, n), cagr_p=rng.normal(0.1, 0.05, n), mdd_s=-rng.uniform(0.2, 0.9, n), mdd_p=-rng.uniform(0.2, 0.9, n))
mask = np.ones(n, dtype=bool)
s = rs.summarize_windows(arr, mask)
want = stats.phase_pooled_mean(edge, rs.HORIZON_MONTHS)
check("summarize_windows: indep_mean / lo / hi / df equal stats.phase_pooled_mean on the edges in start order with the NaN kept in place",
      all(abs(s[f"indep_{k}"] - want[k]) < 1e-15 for k in ("mean", "lo", "hi")) and s["indep_df"] == want["df"] and s["indep_k_min"] == want["k_min"], (s["indep_mean"], want["mean"]))
dropped = stats.phase_pooled_mean(edge[np.isfinite(edge)], rs.HORIZON_MONTHS)
check("summarize_windows: dropping the NaN first would move every start after the gap into another phase and give a different interval (the break case the code avoids; a uniform shift at the front alone would not)",
      abs(dropped["mean"] - want["mean"]) > 1e-9 or abs(dropped["se"] - want["se"]) > 1e-9, (dropped["mean"], want["mean"], dropped["se"], want["se"]))
fin = edge[np.isfinite(edge)]
check("summarize_windows: mean, median, n, wins agree with the finite edges", s["n"] == n - 14 and abs(s["edge_mean"] - fin.mean()) < 1e-15
      and abs(s["edge_median"] - np.median(fin)) < 1e-15 and abs(s["wins"] - (fin > rs.TIE).mean()) < 1e-15)
check("summarize_windows: the too-few flag is k_min < MIN_WINDOWS (the NaN gap here empties two phases down to 2 windows) and noisy follows it",
      s["indep_k_min"] == want["k_min"] and s["too_few_windows"] == (want["k_min"] < rs.MIN_WINDOWS) and s["noisy"] == (s["too_few_windows"] or stats.covers_zero(s["indep_lo"], s["indep_hi"])),
      (s["indep_k_min"], s["too_few_windows"]))
arr_clean = dict(arr, edge=rng.normal(0.002, 0.03, n))
sc = rs.summarize_windows(arr_clean, mask)
check("summarize_windows: 400 complete starts at 120 months give phases of 3-4 windows: not too few, and noisy = the interval covers zero",
      sc["indep_k_min"] == 3 and sc["too_few_windows"] is False and sc["noisy"] == stats.covers_zero(sc["indep_lo"], sc["indep_hi"]), (sc["indep_k_min"], sc["noisy"]))
s2 = rs.summarize_windows(arr, np.arange(n) < 250)
check("summarize_windows: 250 starts give a smallest phase of 2 windows: too_few_windows and noisy are both True whatever the interval",
      s2["too_few_windows"] is True and s2["noisy"] is True and s2["indep_k_min"] == 2, (s2["indep_k_min"], s2["indep_lo"], s2["indep_hi"]))
_holed = np.ones(n, dtype=bool)
_holed[150:160] = False
try:
    rs.summarize_windows(arr, _holed)
    _refused = False
except ValueError as _err:
    _refused = "contiguous" in str(_err)
check("summarize_windows: a mask with a hole (which would mix phases) is refused, not silently pooled", _refused)
s0 = rs.summarize_windows(arr, np.zeros(n, dtype=bool))
check("summarize_windows: an empty mask gives n 0, NaN statistics and noisy True", s0["n"] == 0 and math.isnan(s0["indep_mean"]) and s0["noisy"] is True)


# ---- a fake underlying with exact piecewise-exponential paths ----
class _Run:
    def __init__(self, start, wealth):
        self.start, self.wealth = start, wealth


class _World:
    def __init__(self, dates):
        self.dates = dates

    def row_before(self, date):
        """Row of the last session strictly before `date` (what study.World.row_before gives)."""
        return int(np.searchsorted(self.dates.values, np.datetime64(pd.Timestamp(date)), side="left")) - 1


class _Strat:
    def __init__(self, name):
        self.name = name


class _Und:
    """name, world, dates, n, series, nav(enc, series), run(strat, enc, series, delay): the surface era_rows / era_tests use."""

    def __init__(self, name, dates, nav, wealth, start):
        self.name, self.world, self.dates, self.n = name, _World(dates), dates, len(dates)
        self.series = ["SPYQ"]
        self._nav, self._wealth, self._start = nav, wealth, start

    def nav(self, enc, series):
        return self._nav

    def run(self, strat, enc, series, delay, first_signal=None, cost_mult=1.0):
        return _Run(self._start, self._wealth)


def _exp_path(dates, rates_by_row, start_row=0):
    """exp(sum of rho x days / 365.25) from start_row with the continuous rate rho = ln(1 + R) switching at the rows given in
    rates_by_row = [(first row of the segment, annual R), ...]; NaN before start_row. Its CAGR over any sub-period that starts
    and ends inside one segment is exactly R."""
    days = dates.values.astype("datetime64[D]").astype(np.int64)
    out = np.full(len(dates), np.nan)
    out[start_row] = 1.0
    for t in range(start_row + 1, len(dates)):
        R = next(r for a, r in reversed(rates_by_row) if t - 1 >= a)          # the rate that applies over the step into row t
        out[t] = out[t - 1] * math.exp(math.log(1.0 + R) * (days[t] - days[t - 1]) / 365.25)
    return out


dates = pd.bdate_range("1985-01-02", "2012-12-31")
und = _Und("SPX", dates, None, None, 0)
b1, b2 = und.world.row_before("1990-01-01"), und.world.row_before("2009-01-01")
check("fake world: row_before lands on the last session before the boundary", str(dates[b1].date()) == "1989-12-29" and str(dates[b2].date()) == "2008-12-31")
nav = _exp_path(dates, [(0, 0.05)])                                          # passive 5% a year throughout
wealth = _exp_path(dates, [(0, 0.10), (b1, 0.20), (b2, 0.02)])               # the rule: 10%, 20%, 2% a year by era
und = _Und("SPX", dates, nav, wealth, 0)
variants = [("k", {}, _Strat("rule"))]
rows = rs.era_rows(und, "fixed", variants)
check("era_rows: three eras with the planted edges 10 - 5 = +5, 20 - 5 = +15, 2 - 5 = -3 pp a year, exact to 1e-12",
      len(rows) == 3 and all(abs(r["edge"] - w) < 1e-12 for r, w in zip(rows, (0.05, 0.15, -0.03))), [r["edge"] for r in rows])
check("era_rows: the eras start at the rule's first row and at the boundary rows, and are labeled 'start to end'",
      rows[0]["start"] == "1985-01-02" and rows[0]["end"] == "1989-12-29" and rows[1]["start"] == "1989-12-29" and rows[1]["end"] == "2008-12-31"
      and rows[2]["end"] == "2012-12-31" and rows[1]["era"] == "1989-12-29 to 2008-12-31", rows)
# the per-era CAGRs compound to the full-run growth: prod (1 + cagr_k)^years_k = W_end / W_start, to 1e-12 (rule and passive)
grow_s = math.prod((1.0 + r["strat_cagr"]) ** r["years"] for r in rows)
grow_p = math.prod((1.0 + r["passive_cagr"]) ** r["years"] for r in rows)
check("era_rows: the era CAGRs compound to the full-run growth of the rule and of the passive fund (1e-12)",
      abs(grow_s - wealth[-1] / wealth[0]) < 1e-12 * wealth[-1] and abs(grow_p - nav[-1] / nav[0]) < 1e-12 * nav[-1], (grow_s, wealth[-1]))
# break case: a boundary one row off gives a different edge in the eras it touches (the rates differ across the boundary)
wealth_off = _exp_path(dates, [(0, 0.10), (b1 + 1, 0.20), (b2, 0.02)])
rows_off = rs.era_rows(_Und("SPX", dates, nav, wealth_off, 0), "fixed", variants)
check("era_rows: a path whose rate switches one row after the boundary no longer gives +5 / +15 exactly (an off-by-one boundary is visible)",
      abs(rows_off[0]["edge"] - 0.05) > 1e-6 or abs(rows_off[1]["edge"] - 0.15) > 1e-6, [r["edge"] for r in rows_off])
# a rule whose first valid row falls after the first boundary: the first era is dropped, two rows remain
late = b1 + 500
wealth_late = _exp_path(dates, [(late, 0.20), (b2, 0.02)], start_row=late)
rows_late = rs.era_rows(_Und("SPX", dates, nav, wealth_late, late), "fixed", variants)
check("era_rows: a rule that starts after the first boundary gets two eras (its start to the second boundary, then to the end)",
      len(rows_late) == 2 and rows_late[0]["start"] == str(dates[late].date()) and abs(rows_late[0]["edge"] - 0.15) < 1e-12 and abs(rows_late[1]["edge"] + 0.03) < 1e-12, rows_late)

# ---- era_tests on the same planted paths ----
et = rs.era_tests(und, "fixed", variants)[0]
# the mean daily log edge x 252 equals the planted log edge x (252 / sessions a year of this calendar): bdate_range has about 261
_days_all = dates.values.astype("datetime64[D]").astype(np.int64)
_scale = 252.0 / (len(dates) / ((_days_all[-1] - _days_all[0]) / 365.25))
check("era_tests: three eras whose means x 252 equal the planted log edges ln(1.10/1.05), ln(1.20/1.05), ln(1.02/1.05) scaled by 252 / sessions-per-year (within 0.05 pp)",
      len(et["eras"]) == 3 and all(abs(e["mean_pp"] - math.log((1 + R) / 1.05) * 100 * _scale) < 0.05 for e, R in zip(et["eras"], (0.10, 0.20, 0.02))),
      ([e["mean_pp"] for e in et["eras"]], _scale))
check("era_tests: a 20% era against a 2% era gives a large positive z at every lag; all-earlier against last is positive too",
      all(et["z_last_two"][str(L)] > 10 for L in rs.NW_LAGS) and all(et["z_pre_post"][str(L)] > 10 for L in rs.NW_LAGS), et["z_last_two"])
# wiring, exactly: era_tests' z equals stats.era_difference_z on the daily log edges sliced by hand at the boundary rows
with np.errstate(divide="ignore", invalid="ignore"):
    _d = np.diff(np.log(wealth)) - np.diff(np.log(nav))
_cuts = [0, b1, b2, len(dates) - 1]
_sl = [_d[i:j][np.isfinite(_d[i:j])] for i, j in zip(_cuts[:-1], _cuts[1:])]
check("era_tests: z for the last two eras and for all earlier against the last equal stats.era_difference_z on hand-sliced daily log edges (1e-12)",
      all(abs(et["z_last_two"][str(L)] - stats.era_difference_z(_sl[1], _sl[2], L)) < 1e-12 for L in rs.NW_LAGS)
      and all(abs(et["z_pre_post"][str(L)] - stats.era_difference_z(np.concatenate(_sl[:2]), _sl[2], L)) < 1e-12 for L in rs.NW_LAGS),
      (et["z_last_two"], {L: stats.era_difference_z(_sl[1], _sl[2], L) for L in rs.NW_LAGS}))
# a noisy planted case where z is moderate, so a wrong scale would show: the rule's daily log edge is the passive's plus iid noise
_rng = np.random.default_rng(77)
_noise = np.concatenate([[0.0], _rng.normal(0.0, 0.01, len(dates) - 1)])
wealth_n = nav * np.exp(np.cumsum(_noise))
et_n = rs.era_tests(_Und("SPX", dates, nav, wealth_n, 0), "fixed", variants)[0]
_dn = np.diff(np.log(wealth_n)) - np.diff(np.log(nav))
_sn = [_dn[i:j] for i, j in zip(_cuts[:-1], _cuts[1:])]
check("era_tests: on a pure-noise edge the z equals the hand computation to 1e-12 and is small (|z| < 3) at every lag",
      all(abs(et_n["z_last_two"][str(L)] - stats.era_difference_z(_sn[1], _sn[2], L)) < 1e-12 and abs(et_n["z_last_two"][str(L)]) < 3 for L in rs.NW_LAGS),
      et_n["z_last_two"])
check("era_tests: Newey-West SEs are positive and finite at lags 21 / 63 / 252 in every era", all(e["se_pp"][str(L)] > 0 and math.isfinite(e["se_pp"][str(L)]) for e in et["eras"] for L in rs.NW_LAGS))
same = _Und("SPX", dates, nav, _exp_path(dates, [(0, 0.05)]), 0)
et0 = rs.era_tests(same, "fixed", variants)[0]
check("era_tests: a rule identical to the passive fund has zero edge in every era and NaN z (zero variance), not a crash",
      all(abs(e["mean_pp"]) < 1e-9 for e in et0["eras"]) and all(math.isnan(v) for v in et0["z_last_two"].values()))
