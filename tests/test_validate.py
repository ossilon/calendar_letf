"""Known-answer tests for validate.py, kernel.run() and the December rule of check_missing_weekdays (step 2).
Made-up data only; no files needed. Expected numbers are worked out by hand in the comments.
"""
from dataclasses import replace

import numpy as np
import pandas as pd

from _harness import check, raises  # noqa: I001
from calendar_letf import costs, loader, products, validate
from calendar_letf import kernel as k


def walk(start, n, seed, vol=0.012, drift=0.0003):
    ix = pd.bdate_range(start, periods=n)
    rng = np.random.default_rng(seed)
    return pd.Series(100.0 * np.exp(np.cumsum(rng.normal(drift, vol, n))), index=ix, name="walk")


# ---- 1. fund_total_return: a payout is added back on its ex-date ----
days = pd.bdate_range("2025-01-06", periods=4)
px = pd.Series([100.0, 100.0, 100.0, 100.0], index=days, name="F")
dist = pd.Series([1.0], index=[days[2]])                                  # $1 goes ex on day 3
tr = validate.fund_total_return(px, dist)
check("fund TR: $1 payout on a flat $100 price adds exactly 1% on the ex-date and stays",
      np.allclose(tr.values, [1.0, 1.0, 1.01, 1.01]), tr.values)
check("fund TR: attrs list the payout and its size (1% of the prior close)",
      tr.attrs["distributions"] == {"2025-01-08": 1.0} and abs(tr.attrs["distribution_total_pct_of_price"] - 1.0) < 1e-12)
check("fund TR: no payouts -> price / first price", np.allclose(validate.fund_total_return(px * 2).values, 1.0))
raises("fund TR: a payout on a non-trading day is refused, not dropped",
       lambda: validate.fund_total_return(px, pd.Series([1.0], index=[pd.Timestamp("2025-01-11")])), "not in the price")
raises("fund TR: a negative payout is refused", lambda: validate.fund_total_return(px, pd.Series([-1.0], index=[days[1]])), ">= 0")

# ---- 2. etf_total_return: the index's dividend accrual rides on the ETF's own price path ----
idx = walk("2024-01-02", 300, 1)
yld = pd.Series(0.02, index=idx.index)
days_frac = pd.Series(idx.index, index=idx.index).diff().dt.days.fillna(0) / 365.0
idx_tr = idx * np.cumprod(1.0 + 0.02 * days_frac)                        # index + 2%/yr accrued daily
etf = (idx * 0.5).rename("ETF")                                           # the ETF is half the index level
etf_tr = validate.etf_total_return(etf, idx, idx_tr)
check("ETF TR: ETF price x index TR/price ratio = ETF with the index's 2% yield reinvested (1e-12)",
      np.allclose(etf_tr.values, (etf_tr.iloc[0] * np.cumprod(1.0 + 0.02 * days_frac) * idx / idx.iloc[0]).values, rtol=1e-12),
      )
check("ETF TR: implied dividend yield is about 2%/yr", abs(etf_tr.attrs["implied_dividend_yield_pct"] - 2.0) < 0.05,
      etf_tr.attrs["implied_dividend_yield_pct"])
short_tr = idx_tr.iloc[:-5]                                               # the TR index stops 5 days early
etf_tr2 = validate.etf_total_return(etf, idx, short_tr)
check("ETF TR: days the TR index lacks are carried by the ETF's price (ratio forward-filled) and listed",
      etf_tr2.attrs["ratio_carried_days"] == [str(d.date()) for d in idx.index[-5:]]
      and np.allclose(etf_tr2.iloc[-5:].values / etf_tr2.iloc[-6], etf.iloc[-5:].values / etf.iloc[-6]))
raises("ETF TR: refuses an ETF that starts before the TR index exists",
       lambda: validate.etf_total_return(etf, idx.iloc[10:], idx_tr.iloc[10:]), "on or before")

etf_tr_fee = validate.etf_total_return(etf, idx, idx_tr, etf_fee=0.002)
years = (etf.index[-1] - etf.index[0]).days / 365.25
check("ETF TR: a 0.2% ETF fee lowers the end level by about exp(-0.002 x years) (the fee is paid from dividends)",
      abs(etf_tr_fee.iloc[-1] / etf_tr.iloc[-1] / np.exp(-0.002 * years) - 1) < 1e-4 and etf_tr_fee.attrs["etf_fee"] == 0.002,
      etf_tr_fee.iloc[-1] / etf_tr.iloc[-1])
raises("ETF TR: a fee given in percent (0.2) is refused", lambda: validate.etf_total_return(etf, idx, idx_tr, etf_fee=0.2), "decimal")

# ---- 3. compare: identical series fit perfectly; a known gap is reported ----
same = validate.compare(idx, idx * 3.0)
check("compare: a series against a scaled copy of itself: gap 0, correlation 1, tracking error 0",
      abs(same["cagr_gap"]) < 1e-12 and abs(same["daily_corr"] - 1) < 1e-12 and same["tracking_error_ann"] < 1e-12)
worse = idx * np.exp(-0.01 * np.arange(len(idx)) / 252)                   # loses 1%/yr steadily
cmp2 = validate.compare(worse, idx)
check("compare: a model losing 1%/yr against the real series reports a CAGR gap of about -1 pt",
      abs(cmp2["cagr_gap"] + 0.0099) < 0.002, cmp2["cagr_gap"])
raises("compare: too little overlap is refused", lambda: validate.compare(idx.iloc[:30], idx), "overlapping")

# ---- 4. fit_spread recovers a known spread ----
u = walk("2015-01-02", 1500, 7)
rate = pd.Series(0.03, index=u.index)
real = k.daily_reset_series(u, rate, L=2.0, spread_per_nav=0.015, fee=0.01)
fit = validate.fit_spread(lambda s: k.daily_reset_series(u, rate, L=2.0, spread_per_nav=s, fee=0.01), real)
check("fit_spread: recovers the spread (1.5% of NAV) that generated the 'real' series to 1e-5",
      abs(fit["spread_per_nav"] - 0.015) < 1e-5, fit)
def _fit_flat():
    """The break case feeds a constant 'real' series, whose correlation is undefined; numpy's warning about that is
    expected and silenced here so the test fails only on the wrong error, never on the warning."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return validate.fit_spread(lambda s: k.daily_reset_series(u, rate, L=2.0, spread_per_nav=s, fee=0.01), real * 0 + 1.0, lo=0.0, hi=0.001)


raises("fit_spread: refuses when no spread in range explains the fund", _fit_flat, "no root")

# ---- 4b. fit_rate_turns recovers a known rate multiplier ----
real_rt = k.daily_reset_series(u, rate * 1.4, L=2.0, spread_per_nav=0.015, fee=0.01)
fit_rt = validate.fit_rate_turns(lambda m: k.daily_reset_series(u, rate * m, L=2.0, spread_per_nav=0.015, fee=0.01), real_rt)
check("fit_rate_turns: recovers 1.4 rate turns that generated the 'real' series to 1e-5",
      abs(fit_rt["rate_turns"] - 1.4) < 1e-5, fit_rt)

# ---- 4c. R2 step 2: fee timeline, balance-sheet structure, cash-yield fit, window return, in-period fall ----
ix = u.index
ft = validate.fee_timeline(ix, 0.013, {"2016-06-30": 0.010})
after = ix > pd.Timestamp("2016-06-30")
check("fee_timeline: 1.30% through the change date, 1.00% on every row dated after it; steps recorded",
      np.allclose(ft[~after], 0.013) and np.allclose(ft[after], 0.010) and ft.loc["2016-06-30"] == 0.013
      and ft.attrs["steps"] == [[str(ix[0].date()), 0.013], [str(ix[after][0].date()), 0.010]], ft.attrs["steps"])
check("fee_timeline: no changes -> a constant series; a change before the first row replaces the initial fee",
      np.allclose(validate.fee_timeline(ix, 0.013), 0.013)
      and np.allclose(validate.fee_timeline(ix, 0.013, {"2000-01-01": 0.02}), 0.02))
raises("fee_timeline: a fee in percent is refused", lambda: validate.fee_timeline(ix, 1.3), "annual decimals")
ft2 = validate.fee_timeline(ix, 0.013, {"2016-12-30": 0.012, "2016-06-30": 0.010})            # two changes, given out of order
seg1, seg2, seg3 = ix <= pd.Timestamp("2016-06-30"), (ix > pd.Timestamp("2016-06-30")) & (ix <= pd.Timestamp("2016-12-30")), ix > pd.Timestamp("2016-12-30")
check("fee_timeline: two changes make three segments (the dates sort; each date is the last day at the old fee)",
      np.allclose(ft2[seg1], 0.013) and np.allclose(ft2[seg2], 0.010) and np.allclose(ft2[seg3], 0.012)
      and [s[1] for s in ft2.attrs["steps"]] == [0.013, 0.010, 0.012], ft2.attrs["steps"])

# ---- 4c-bis. the live-fund fee path of scripts/run_validate_live.py: four segments, their dates, their status, and ONE source ----
# Every filed ratio is read by an independent csv-module reader from reference/nav_anchors.csv here, so the test
# compares the script with the file, not with a second copy of the numbers.
import csv  # noqa: E402
import importlib.util  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from _harness import ROOT  # noqa: E402
_spec = importlib.util.spec_from_file_location("run_validate_live", ROOT / "scripts" / "run_validate_live.py")
RV = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RV)
with open(ROOT / "reference" / "nav_anchors.csv", newline="", encoding="utf-8") as _fh:
    CSV_ROWS = list(csv.DictReader(_fh))


def csv_fee(ticker, start, end):
    """(fee as a decimal, file line) of the one PRIMARY nav_anchors.csv row for this fund and window (header = line 1)."""
    hits = [(i + 2, r) for i, r in enumerate(CSV_ROWS) if r["ticker"] == ticker and r["start_date"] == start and r["end_date"] == end]
    assert len(hits) == 1 and hits[0][1]["status"] == "PRIMARY", (ticker, start, end, len(hits))
    return float(hits[0][1]["expense_ratio_net_pct"]) / 100.0, hits[0][0]


fx = pd.bdate_range("2024-08-30", "2026-10-08")
for _f in ("SPYQ", "MQQQ", "QQQP"):
    _inc = RV.FUNDS[_f]["reset_date"]
    _fy25, _l25 = csv_fee(_f, _inc, "2025-03-31")                # N-CSR FY2025: inception to 2025-03-31
    _h1, _lh1 = csv_fee(_f, "2025-04-01", "2025-09-30")          # N-CSRS: first half of fiscal 2026
    _fy26, _l26 = csv_fee(_f, "2025-03-31", "2026-03-31")        # N-CSR FY2026: the whole fiscal year
    _dv = 2.0 * _fy26 - _h1                                       # the derivation, restated from the CSV figures
    _pr = products.PRODUCTS[_f].fee
    _s = RV.fee_series(_f, fx[fx >= pd.Timestamp(_inc)])
    _at = lambda d, _s=_s: float(_s.loc[d])                                                                    # noqa: E731
    _want_steps = [str(_s.index[0].date())] + (["2025-04-01"] if abs(_h1 - _fy25) > 1e-12 else []) + ["2025-10-01", "2026-04-01"]
    check(f"live fee path {_f}: the CSV ratios {_fy25:.2%} to 2025-03-31, {_h1:.2%} to 2025-09-30, derived {_dv:.2%} to 2026-03-31, then {_pr:.2%}",
          abs(_s.iloc[1] - _fy25) < 1e-12 and abs(_at("2025-03-31") - _fy25) < 1e-12 and abs(_at("2025-04-01") - _h1) < 1e-12
          and abs(_at("2025-09-30") - _h1) < 1e-12 and abs(_at("2025-10-01") - _dv) < 1e-12
          and abs(_at("2026-03-31") - _dv) < 1e-12 and abs(_at("2026-04-01") - _pr) < 1e-12 and abs(_s.iloc[-1] - _pr) < 1e-12
          and [x[0] for x in _s.attrs["steps"]] == _want_steps, _s.attrs["steps"])
    check(f"live fee path {_f}: the script's figures equal the CSV rows (FY2025 row {_l25}, first-half row {_lh1}, FY2026 row {_l26}) and record those lines",
          abs(RV.FEE_FY2025[_f] - _fy25) < 1e-12 and abs(RV.FEE_FIRST_HALF[_f] - _h1) < 1e-12 and abs(RV.FEE_FY2026[_f] - _fy26) < 1e-12
          and RV.FEE_ROWS["fy2025"][_f] == _l25 and RV.FEE_ROWS["h1"][_f] == _lh1 and RV.FEE_ROWS["fy2026"][_f] == _l26)
    check(f"live fee path {_f}: the derived fee is the second half of the fiscal year: (6 x first half + 6 x derived) / 12 = FY2026 ratio",
          abs((6 * _h1 + 6 * _dv) / 12 - _fy26) < 1e-12 and abs(RV.FEE_DERIVED[_f] - _dv) < 1e-12
          and abs(products.PRODUCTS[_f].fee - _pr) < 1e-12)
    _t = RV.fee_series(_f, fx[fx >= pd.Timestamp(_inc)], sensitivity=True)
    check(f"live fee path {_f} sensitivity: filed ratios to 2025-09-30, then the FY2026 average {_fy26:.2%} from 2025-10-01 to 2026-07-31, then the prospectus fee",
          abs(float(_t.loc["2025-03-31"]) - _fy25) < 1e-12 and abs(float(_t.loc["2025-04-01"]) - _h1) < 1e-12
          and abs(float(_t.loc["2025-09-30"]) - _h1) < 1e-12 and abs(float(_t.loc["2025-10-01"]) - _fy26) < 1e-12
          and abs(float(_t.loc["2026-04-01"]) - _fy26) < 1e-12 and abs(float(_t.loc["2026-07-31"]) - _fy26) < 1e-12
          and abs(float(_t.loc["2026-08-03"]) - _pr) < 1e-12, _t.attrs["steps"])
# the slip that this section fixes: MQQQ's N-CSR FY2025 ratio is 1.31% (excise tax), its N-CSRS ratio is 1.30%, and the path steps down on 2025-04-01
_mq = RV.fee_series("MQQQ", fx)
check("live fee path MQQQ: the fiscal-2025 ratio (with excise tax) ends on 2025-03-31 and the N-CSRS ratio applies from 2025-04-01 (no 1.31% beyond)",
      csv_fee("MQQQ", "2024-08-30", "2025-03-31")[0] > csv_fee("MQQQ", "2025-04-01", "2025-09-30")[0]
      and float(_mq.loc["2025-03-31"]) > float(_mq.loc["2025-04-01"]) and np.allclose(_mq.loc["2025-04-01":"2025-09-30"], csv_fee("MQQQ", "2025-04-01", "2025-09-30")[0], rtol=0, atol=1e-12),
      _mq.attrs["steps"])
_bn = RV.banner_lines(dict(files=[], data_dir="data", rates_dir="rates", reference_dir="reference", reference_files=[]))
_derived = [x for x in _bn if "DERIVED" in x]
_assumed = [x for x in _bn if "ASSUMED" in x and "2026-04-01" in x]
_pct3 = lambda key: " / ".join(f"{RV.FEE_FIRST_HALF[f] * 100:.2f}" if key == "h1" else f"{RV.FEE_DERIVED[f] * 100:.2f}" for f in ("SPYQ", "MQQQ", "QQQP")) + "%"   # noqa: E731
_h1_line = [x for x in _bn if "2025-04-01 to 2025-09-30" in x]
_h1_lines = sorted(csv_fee(f, "2025-04-01", "2025-09-30")[1] for f in ("SPYQ", "MQQQ", "QQQP"))
check("live fee path banner: names the DERIVED segment with its dates and values, the ASSUMED start date of the 2026 fee, and the FILED first half",
      len(_derived) == 1 and "2025-10-01 to 2026-03-31" in _derived[0] and _pct3("derived") in _derived[0]
      and len(_assumed) == 1 and "1.00 / 1.03 / 1.00%" in _assumed[0] and any("FILED" in x and "N-CSR FY2025" in x for x in _bn)
      and any("sensitivity" in x and "1.26 / 1.21 / 1.24%" in x and "2026-07-31" in x for x in _bn), _bn)
check("live fee path banner: the first-half segment (2025-04-01 to 2025-09-30) is labeled FILED with its values and its nav_anchors.csv rows",
      len(_h1_line) == 1 and "FILED" in _h1_line[0] and "DERIVED" not in _h1_line[0] and _pct3("h1") in _h1_line[0]
      and f"rows {_h1_lines[0]}-{_h1_lines[-1]}" in _h1_line[0] and "N-CSRS" in _h1_line[0], _h1_line)
# the loader refuses a CSV whose fee column is missing, mistyped, duplicated, absent or not PRIMARY, and names the row
_hdr = list(CSV_ROWS[0].keys())


def _csv_with(edit):
    """Write a copy of nav_anchors.csv in which edit(rows) changed the rows; return the loader's call on it."""
    rows = [dict(r) for r in CSV_ROWS]
    rows = edit(rows) or rows
    tmp = tempfile.TemporaryDirectory()
    p = Path(tmp.name) / "nav_anchors.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_hdr)
        w.writeheader()
        w.writerows(rows)
    return lambda: RV.load_filed_fees(p), tmp


_l_h1_mq = csv_fee("MQQQ", "2025-04-01", "2025-09-30")[1]
_l_fy_sp = csv_fee("SPYQ", "2025-03-31", "2026-03-31")[1]
_l_fy25_qq = csv_fee("QQQP", "2024-09-30", "2025-03-31")[1]
check("load_filed_fees: the real CSV loads and the derived fee equals 2 x FY2026 - first half for every fund",
      all(abs(RV.load_filed_fees()["derived"][f] - (2 * csv_fee(f, "2025-03-31", "2026-03-31")[0] - csv_fee(f, "2025-04-01", "2025-09-30")[0])) < 1e-9
          for f in ("SPYQ", "MQQQ", "QQQP")))


def _blank_h1(rows):
    rows[_l_h1_mq - 2]["expense_ratio_net_pct"] = ""


def _percent_slip(rows):
    rows[_l_fy_sp - 2]["expense_ratio_net_pct"] = "0.0126"


def _secondary(rows):
    rows[_l_fy25_qq - 2]["status"] = "SECONDARY"


def _duplicate(rows):
    rows.append(dict(rows[_l_h1_mq - 2]))


def _drop(rows):
    del rows[_l_fy_sp - 2]


def _negative_derived(rows):
    rows[_l_fy_sp - 2]["expense_ratio_net_pct"] = "0.30"          # 2 x 0.30 - 1.30 < 0


for _name, _edit, _msg in (
        ("a blank first-half ratio", _blank_h1, f"row {_l_h1_mq}"),
        ("a ratio in the wrong unit", _percent_slip, f"row {_l_fy_sp}"),
        ("a row that is not PRIMARY", _secondary, f"row {_l_fy25_qq}"),
        ("a duplicated row", _duplicate, "found 2"),
        ("a missing row", _drop, "found 0"),
        ("a FY2026 ratio that makes the derived second half negative", _negative_derived, f"rows {_l_fy_sp}")):
    _call, _tmp = _csv_with(_edit)
    raises(f"load_filed_fees refuses {_name} and names it", _call, _msg)
    _tmp.cleanup()
# the kernel charges a step fee exactly: a flat index, zero financing -> NAV falls by the fee accrual only
flat = pd.Series(100.0, index=ix, name="flat")
nav_step = k.daily_reset_series(flat, 0.0, L=2.0, spread_per_nav=0.0, fee=ft)
acc = pd.Series(ix, index=ix).diff().dt.days.fillna(0).values / 365.0
check("fee_timeline through the kernel: a flat index at zero financing loses exactly prod(1 - fee_t x days/365) with the step fee",
      np.allclose(nav_step.values, np.cumprod(1.0 - ft.values * acc), rtol=1e-12))

st1 = validate.Structure(swap_turns=2.0, cash_nav=1.0, cash_yield=0.8, label="w1")
check("Structure: rate turns = s - k c = 2.0 - 0.8 = 1.2; spread turns = s = 2.0; describe names both",
      abs(st1.rate_turns - 1.2) < 1e-12 and st1.spread_turns == 2.0 and "rate turns 1.200" in st1.describe(0.0092)
      and "1.84%" in st1.describe(0.0092), st1.describe(0.0092))
raises("Structure: swap turns above 3 NAV are refused", lambda: validate.Structure(4.0, 1.0, 0.8), "between 0 and 3")
r_const = pd.Series(0.04, index=ix)
sr = validate.structural_rate(r_const, 0.01, [("2017-12-29", st1), (None, validate.Structure(1.0, 0.4, 0.5, "w2"))])
w2 = ix > pd.Timestamp("2017-12-29")
# Two windows with DIFFERENT rates (R4 review: the earlier pair both gave 6.8%, so a window mix-up could not show).
check("structural_rate: row = rate x (s - k c) + s x spread per window: 0.04 x 1.2 + 0.02 = 6.8% then 0.04 x 0.8 + 0.01 = 4.2% "
      "(window 2: 1.0 - 0.2 = 0.8 turns), each on its own rows, and the windows are recorded",
      np.allclose(sr[~w2], 0.04 * 1.2 + 0.02) and np.allclose(sr[w2], 0.04 * 0.8 + 0.01) and w2.any() and (~w2).any()
      and [w["last"] for w in sr.attrs["windows"]] == ["2017-12-29", str(ix[-1].date())]
      and sr.attrs["windows"][0]["rate_turns"] == 1.2 and abs(sr.attrs["windows"][1]["rate_turns"] - 0.8) < 1e-12, sr.attrs["windows"])
raises("structural_rate: a row no window covers is refused", lambda: validate.structural_rate(r_const, 0.01, [("2016-01-01", st1)]), "no Structure covers")
raises("structural_rate: window ends must ascend", lambda: validate.structural_rate(r_const, 0.01, [("2017-12-29", st1), ("2016-12-30", st1), (None, st1)]), "ascending")
raises("structural_rate: an open-ended window must be last", lambda: validate.structural_rate(r_const, 0.01, [(None, st1), ("2017-12-29", st1)]), "last window")
raises("structural_rate: a spread in percent is refused", lambda: validate.structural_rate(r_const, 0.92, [(None, st1)]), "decimal per turn")
# the kernel run on the folded rate with spread_per_nav=0 equals the plain run with rate x turns and the spread passed separately
nav_fold = k.daily_reset_series(u, validate.structural_rate(r_const, 0.01, [(None, st1)]), L=2.0, spread_per_nav=0.0, fee=0.01)
nav_plain = k.daily_reset_series(u, r_const * 1.2, L=2.0, spread_per_nav=0.02, fee=0.01)
check("structural_rate through the kernel: folding s x spread into the rate equals passing spread_per_nav = s x spread (1e-12)",
      np.allclose(nav_fold.values, nav_plain.values, rtol=1e-12))
# fit_cash_yield recovers a planted c (a higher c means a cheaper fund, the opposite direction to fit_spread)
real_c = k.daily_reset_series(u, validate.structural_rate(rate, 0.0092, [(None, validate.Structure(2.0, 1.0, 0.75))]), L=2.0, spread_per_nav=0.0, fee=0.013)
fit_c = validate.fit_cash_yield(lambda c: k.daily_reset_series(u, validate.structural_rate(rate, 0.0092, [(None, validate.Structure(2.0, 1.0, c))]),
                                                                L=2.0, spread_per_nav=0.0, fee=0.013), real_c)
check("fit_cash_yield: recovers the planted c = 0.75 to 1e-5 with a zero CAGR gap at the fit",
      abs(fit_c["cash_yield"] - 0.75) < 1e-5 and abs(fit_c["cagr_gap_at_fit"]) < 1e-6, fit_c)
# cash_yield_at_spreads: identity at the planted spread, and the bound direction (a costlier spread needs a higher c)
_build_at = lambda s: (lambda c: k.daily_reset_series(u, validate.structural_rate(rate, s, [(None, validate.Structure(2.0, 1.0, c))]),  # noqa: E731
                                                      L=2.0, spread_per_nav=0.0, fee=0.013))
_cs = validate.cash_yield_at_spreads(_build_at, real_c, (0.0075, 0.0092, 0.0100))
check("cash_yield_at_spreads: at the spread that built the 'fund' (0.92%) it returns the planted c = 0.75 (identity, 1e-5)", abs(_cs[0.0092] - 0.75) < 1e-5, _cs)
check("cash_yield_at_spreads: c rises with the spread (75 bp < 92 bp < 100 bp gives c below 0.75 < c above), so the two filed extremes bound c",
      _cs[0.0075] < _cs[0.0092] < _cs[0.0100], _cs)
# closed form for the size: with 2 swap turns and 1 cash turn, a spread change ds moves the charge by 2 ds, which c x rate must
# offset: dc = 2 ds / rate. The planted rate here is the test's constant 'rate' series' mean.
_rmean = float(np.mean(np.asarray(rate)))
check("cash_yield_at_spreads: the move per spread step is about 2 x ds / rate (2 swap turns, 1 cash turn), within 10%",
      abs((_cs[0.0100] - _cs[0.0075]) - 2 * 0.0025 / _rmean) < 0.1 * 2 * 0.0025 / _rmean, (_cs[0.0100] - _cs[0.0075], 2 * 0.0025 / _rmean))
# gap_decomposition: the planted 'fund' is the fitted structure (fee 1.30%, 2.0 swap turns, rate turns 2.0 - 0.75 = 1.25). The
# starting model is the v1 filed one (fee 1.00%, 1.5 swap turns, 1.0 rate turn). Three steps: fee, spread turns, rate turns.
def dec_nav(fee, swap_turns, rate_turns):
    st_ = validate.fixed_turns_structure(swap_turns, rate_turns)
    return k.daily_reset_series(u, validate.structural_rate(rate, 0.0092, [(None, st_)]), L=2.0, spread_per_nav=0.0, fee=fee)


check("fixed_turns_structure: asks for 1.5 swap turns and 1.0 rate turns -> Structure with exactly those turns",
      abs(validate.fixed_turns_structure(1.5, 1.0).rate_turns - 1.0) < 1e-12 and validate.fixed_turns_structure(1.5, 1.0).spread_turns == 1.5)
steps_dec = [("v1 filed", dec_nav(0.010, 1.5, 1.0)), ("fee 1.30%", dec_nav(0.013, 1.5, 1.0)),
             ("2.0 spread turns", dec_nav(0.013, 2.0, 1.0)), ("fitted rate turns", dec_nav(0.013, 2.0, 1.25))]
dec = validate.gap_decomposition(dec_nav(0.013, 2.0, 1.25), steps_dec)
check("gap_decomposition: the three pieces (fee, spread turns, rate turns) add up to the total gap within 1e-6, and the fitted end is 0",
      abs(sum(dec["closed"]) - dec["total_closed"]) < 1e-6 and abs(dec["end_gap"]) < 1e-12 and abs(sum(dec["closed"]) - dec["start_gap"]) < 1e-6
      and len(dec["closed"]) == 3, dec)
# A cost of x a year lowers log growth by x; CAGR moves by (1 + CAGR) x, here about 0.75 x because this synthetic fund loses
# value (volatility drag). So each piece is the planted cost times one common factor in (0.5, 1.0): same factor for all three.
planted = np.array([0.003, 0.5 * 0.0092, 0.25 * 0.03])
fac = np.array(dec["closed"]) / planted
check("gap_decomposition: each piece is the planted cost (fee +0.30 pt; 0.5 turns x 0.92% = +0.46 pt; 0.25 rate turns x 3% = +0.75 pt) "
      "times one common factor between 0.5 and 1 (spread of the factors under 5%)",
      ((fac > 0.5) & (fac < 1.0)).all() and (fac.max() / fac.min() - 1) < 0.05, fac)
raises("gap_decomposition: one model alone is refused", lambda: validate.gap_decomposition(real, steps_dec[:1]), "at least one step")
check("window_return: level[end]/level[start] - 1 on exact rows",
      abs(validate.window_return(u, ix[10], ix[50]) - (u.iloc[50] / u.iloc[10] - 1)) < 1e-15)
raises("window_return: a date that is not a row raises (an anchor is close-to-close, never a nearest match)",
       lambda: validate.window_return(u, "2015-01-03", ix[50]), "not a row")
# worst_in_period_fall: a planted 20% intraday low inside one month, closes never below -5% of the reset
px_m = pd.Series(100.0, index=pd.bdate_range("2024-01-02", "2024-03-29"), name="px")
px_m.loc["2024-02-01":"2024-02-29"] = 96.0                      # February closes 4% under the January-end reset
low_m = px_m.copy(); low_m.loc["2024-02-14"] = 80.0           # one intraday low 20% under it
fall = validate.worst_in_period_fall(px_m, "monthly", low=low_m)
check("worst_in_period_fall: close -4.0% in February, low -20.0% on 2024-02-14, both measured from the January-end close",
      abs(fall["close"] + 0.04) < 1e-12 and abs(fall["low"] + 0.20) < 1e-12 and fall["low_date"] == "2024-02-14", fall)
check("worst_in_period_fall: without lows the low fields are None and a flat series reports 0",
      validate.worst_in_period_fall(pd.Series(100.0, index=px_m.index), "monthly") == dict(close=0.0, close_date=None, low=None, low_date=None))

# ---- 5. period_multiple: a zero-cost 2x calendar fund delivers exactly 2x per full period ----
fund = k.periodic_reset_series(u, 0.0, reset="monthly", L=2.0, spread_per_nav=0.0, fee=0.0, early_drop=None)
pm = validate.period_multiple(fund, u, "monthly")
check("period_multiple: zero-cost 2x monthly fund shows multiple 2.0 and difference 0 in every full month",
      np.allclose(pm["multiple"].dropna(), 2.0, atol=1e-9) and np.allclose(pm["fund_minus_2x_etf"], 0.0, atol=1e-12)
      and len(pm) >= 60, (pm["multiple"].min(), pm["multiple"].max(), len(pm)))
check("period_multiple: a near-flat ETF month (|move| < 1%, the monthly default) gives NaN multiple",
      pm["multiple"].isna().sum() == (pm["etf_return"].abs() < 0.01).sum())
reg0 = validate.period_regression(pm)
check("period_regression: zero-cost 2x fund -> slope 2.000, intercept 0.00 pp, R2 1",
      abs(reg0["slope"] - 2.0) < 1e-9 and abs(reg0["intercept"]) < 1e-12 and abs(reg0["r2"] - 1.0) < 1e-12, reg0)
# a fund that returns 2x the ETF minus a constant 1% per month: slope 2, intercept -1 pp, whatever the ETF did
pm_c = pm.copy(); pm_c["fund_return"] = 2.0 * pm_c["etf_return"] - 0.01
reg_c = validate.period_regression(pm_c)
check("period_regression: 2x ETF minus 1% per month -> slope 2, intercept -1.00 pp (the cost), where the plain ratio would swing",
      abs(reg_c["slope"] - 2.0) < 1e-9 and abs(reg_c["intercept_pct_per_period"] + 1.0) < 1e-9, reg_c)
check("period_multiple: periods run from one period-end close to the next",
      (pm["period_start"].iloc[1:].values == pm["period_end"].iloc[:-1].values).all())

# ---- 6. calendar_year_return ----
cy = pd.Series([1.0, 1.1, 1.21, 1.331], index=pd.to_datetime(["2023-12-29", "2024-06-28", "2024-12-31", "2025-12-31"]))
check("calendar_year_return: 2024 = 1.21/1.0 - 1 = 21%; 2025 = 10%; 2023 is not covered",
      abs(validate.calendar_year_return(cy, 2024) - 0.21) < 1e-12 and abs(validate.calendar_year_return(cy, 2025) - 0.10) < 1e-12
      and np.isnan(validate.calendar_year_return(cy, 2023)))

# ---- 7. kernel.run: one entry point driven by a ProductSpec ----
spec = products.PRODUCTS["MQQQ"]
by_spec = k.run(spec, u, rate)
by_hand = k.periodic_reset_series(u, rate, reset="monthly", L=2.0, spread_per_nav=costs.spread_per_nav(spec.costs),
                                  fee=spec.fee, early_drop=0.35, early_mode="level")
check("run: MQQQ via its spec equals the bare wrapper with the spec's own costs (bit-exact)",
      np.array_equal(by_spec.values, by_hand.values) and by_spec.name == "MQQQ" and by_spec.attrs["product"]["overrides"] == {})
twin = products.twin_of(spec)
check("run: the twin goes to the daily kernel with the fund's fee (1.03%) and costs",
      np.array_equal(k.run(twin, u, rate).values,
                     k.daily_reset_series(u, rate, L=2.0, spread_per_nav=costs.spread_per_nav(spec.costs), fee=0.0103).values)
      and k.run(twin, u, rate).attrs["model"]["structure"] == "daily_reset")
sens = k.run(spec, u, rate, spread_per_nav=0.008)
check("run: an override is applied AND recorded in attrs so it cannot pass as the base case",
      sens.attrs["product"]["overrides"] == {"spread_per_nav": 0.008} and sens.iloc[-1] > by_spec.iloc[-1])
open_fee = replace(spec, costs=replace(spec.costs, fee=None, fee_status="OPEN", fee_source="test: unknown"))
raises("run: a spec with an OPEN fee refuses to run (no silent default)", lambda: k.run(open_fee, u, rate), "OPEN")
check("run: early_mode and a price trigger pass through to the calendar kernel",
      k.run(spec, u, rate, early_mode="close", trigger=u.rename("PX")).attrs["model"]["trigger"] == "PX")

# ---- 7b. reset "never": the buy-once margin position, via the public wrapper (step 3, judgment call 1) ----
nv = k.periodic_reset_series(u, rate, reset="never", L=2.0, spread_per_nav=0.02, fee=0.0, early_drop=None)
# R2 E1 + E2: the loan (1 at the purchase) compounds daily on ACT/360 and the spread is borrowed too, so with a
# constant 3% rate and day gaps g_t: loan_t = prod(1 + 0.03 g/360) + (0.02/0.03) x (prod(1 + 0.03 g/360) - 1) when
# every gap is one day; in general loan_t = loan_{t-1} x (1 + 0.03 g_t/360) + 0.02 g_t/360 (re-stated here).
g = np.r_[0.0, np.diff(u.index.values).astype("timedelta64[D]").astype(float)]
loan_v = np.ones(len(u))
for t in range(1, len(u)):
    loan_v[t] = loan_v[t - 1] * (1.0 + 0.03 * g[t] / 360.0) + 0.02 * g[t] / 360.0
check("never: with no reset the NAV is 2 x u/u0 - 1 minus the compounding loan's growth (ACT/360, 1e-9), no resets listed",
      np.allclose(nv.values[:50], 2.0 * u.values[:50] / u.values[0] - loan_v[:50], atol=1e-9)
      and nv.attrs["early_resets"] == [] and nv.attrs["model"]["reset"] == "never"
      and nv.attrs["model"]["structure"] == "buy_once_margin", nv.values[:3])
raises("never: the buy-once position has no early reset (an early_drop is refused, not silently ignored)",
       lambda: k.periodic_reset_series(u, rate, reset="never", L=2.0, spread_per_nav=0.02, fee=0.0, early_drop=0.35),
       "no early reset")
crash = pd.Series([100.0, 80.0, 49.0, 60.0], index=pd.bdate_range("2024-01-02", periods=4))
dead = k.periodic_reset_series(crash, 0.0, reset="never", L=2.0, spread_per_nav=0.0, fee=0.0, early_drop=None)
check("never: a 51% fall finishes a buy-once 2x position (equity 0) and it never recovers",
      dead.iloc[2] == 0.0 and dead.iloc[-1] == 0.0 and dead.attrs["terminated"] == "2024-01-04")

# ---- 7c. Shiller dividend yields (B7): the measured series replaces the assumed map before 1988 ----
from calendar_letf import series as ser  # noqa: E402
tbl = pd.read_csv(ser.SHILLER_FILE)
check("shiller file: monthly rows 1871-01 to at least 1987-12 with yields between 1% and 15%",
      tbl["month"].iloc[0] == "1871-01" and tbl["month"].iloc[-1] >= "1987-12" and tbl["dividend_yield"].between(0.01, 0.15).all())
cal_days = pd.bdate_range("1950-01-02", "1987-12-31")
sy = ser.shiller_yield_series(cal_days)
check("shiller yield on 1950-1987 trading days: mean about 4.1%/yr (the decade map had 3.8%); every row filled",
      abs(sy.mean() - 0.041) < 0.002 and sy.notna().all(), sy.mean())
check("shiller yield: a day takes its own month's value (1950-06-15 = the 1950-06 row)",
      abs(sy.loc["1950-06-15"] - float(tbl.set_index("month").loc["1950-06", "dividend_yield"])) < 1e-12)
raises("shiller yield: a month outside the file raises (no silent zero)",
       lambda: ser.shiller_yield_series(pd.bdate_range("2030-01-01", "2030-01-10")), "no value")

# ---- 8. check_missing_weekdays: the last year is judged only when the data end on its final weekday ----
full = pd.bdate_range("2025-01-01", "2025-12-31")                          # 261 weekdays, ends Wed 31 Dec
check("weekday guard: a complete year of weekdays passes", loader.check_missing_weekdays(full) is None)
raises("weekday guard: 20 missing weekdays in a complete year raise",
       lambda: loader.check_missing_weekdays(full.delete(list(range(50, 70)))), "weekdays look missing")
to_24th = pd.bdate_range("2025-01-01", "2025-12-24")                       # 256 rows, would pass anyway
to_24th_holed = to_24th.delete(list(range(50, 70)))                        # 236 rows: not judged, year incomplete
check("weekday guard: a file ending 24 Dec is NOT judged for that year (more weekdays follow), audit S1c item 5",
      loader.check_missing_weekdays(to_24th_holed) is None)
two_years = pd.bdate_range("2024-01-01", "2025-12-24").delete(list(range(50, 70)))   # the hole is in 2024
raises("weekday guard: the hole in the COMPLETE earlier year is still caught when the file ends mid-December",
       lambda: loader.check_missing_weekdays(two_years), "year 2024")

# ---- filed_spread: the swap spread read from the N-PORT extract, never typed (R2 step 12e) ----
import json as _json  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_planted = {"X": {"snapshots": [{"period": "2026-06-30", "swaps": [{"cp": "A", "pay": "OBFR01 + 100bps (Spread)", "notional": 300.0},
                                                                   {"cp": "B", "pay": "OBFR01 + 75bps (Spread)", "notional": 100.0}]},
                                {"period": "2026-03-31", "swaps": []}]}}
check("filed_spread: notional-weighted 100 bp x 300 and 75 bp x 100 = 93.75 bp = 0.009375", abs(validate.filed_spread(_planted, "X", "2026-06-30") - 0.009375) < 1e-15)
raises("filed_spread refuses a period with no swaps", lambda: validate.filed_spread(_planted, "X", "2026-03-31"), "no swaps")
raises("filed_spread refuses an unknown fund", lambda: validate.filed_spread(_planted, "Y", "2026-06-30"), "no snapshots")
raises("filed_spread refuses a pay leg that does not state its spread",
       lambda: validate.filed_spread({"X": {"snapshots": [{"period": "p", "swaps": [{"pay": "OBFR01 flat", "notional": 1.0}]}]}}, "X", "p"), "cannot read")
_nport = _json.loads((_Path(__file__).resolve().parents[1] / "reference" / "nport_tradr_2026.json").read_text(encoding="utf-8"))
_fs = {f: validate.filed_spread(_nport, f, "2026-06-30") for f in ("SPYQ", "MQQQ", "QQQP")}
# hand-weighted from the extract: SPYQ (4,667,259 x 100 + 5,485,187 x 75 + 6,472,811 x 100) / 16,625,257 = 91.75 bp;
# MQQQ (78,073,192 x 100 + 10,121,715 x 75 + 274,802,244 x 100) / 362,997,151 = 99.30 bp; QQQP 92.96 bp.
check("filed_spread on the shipped extract at 2026-06-30: SPYQ 0.9175%, MQQQ 0.9930%, QQQP 0.9296% (hand-weighted from the three swaps each)",
      abs(_fs["SPYQ"] - 0.0091752) < 2e-6 and abs(_fs["MQQQ"] - 0.0099302) < 2e-6 and abs(_fs["QQQP"] - 0.0092957) < 2e-6, _fs)
check("filed_spread: MQQQ at 2026-03-31 reads 98.37 bp (the typed 0.97% matched neither period)",
      abs(validate.filed_spread(_nport, "MQQQ", "2026-03-31") - 0.009837) < 2e-6, validate.filed_spread(_nport, "MQQQ", "2026-03-31"))
check("filed_spread_range: every swap in the shipped extract is at 75 or 100 bp, so the bounds are (0.0075, 0.0100)",
      validate.filed_spread_range(_nport) == (0.0075, 0.0100), validate.filed_spread_range(_nport))
check("filed_spread_range: the planted extract (100 and 75 bp) gives (0.0075, 0.0100); a metadata key starting with '_' is ignored",
      validate.filed_spread_range(dict(_planted, _what="note")) == (0.0075, 0.0100))
raises("filed_spread_range refuses an extract with no swaps", lambda: validate.filed_spread_range({"X": {"snapshots": [{"period": "p", "swaps": []}]}}), "no swaps")
# the extremes sit in a LATER snapshot of the first fund (50 bp) and in a SECOND fund (125 bp): a version that reads only the first
# snapshot, only the first fund, or returns a constant gives a different answer
_wide = {"_what": "metadata",
         "A": {"snapshots": [{"period": "p1", "swaps": [{"pay": "OBFR01 + 100bps (Spread)", "notional": 1.0}, {"pay": "OBFR01 + 75bps (Spread)", "notional": 1.0}]},
                             {"period": "p2", "swaps": [{"pay": "OBFR01 + 50bps (Spread)", "notional": 1.0}]},
                             {"period": "p3", "swaps": [{"pay": "OBFR01 + 90bps (Spread)", "notional": 1.0}]}]},     # 50 bp sits in a MIDDLE snapshot
         "B": {"snapshots": [{"period": "p1", "swaps": [{"pay": "OBFR01 + 125bps (Spread)", "notional": 1.0}]}]}}
raises("filed_spread refuses a pay leg on another reference rate (the model charges OBFR)",
       lambda: validate.filed_spread({"X": {"snapshots": [{"period": "p", "swaps": [{"pay": "SOFR + 90bps (Spread)", "notional": 1.0}]}]}}, "X", "p"), "OBFR01")
raises("filed_spread_range refuses a pay leg on another reference rate",
       lambda: validate.filed_spread_range({"X": {"snapshots": [{"period": "p", "swaps": [{"pay": "SOFR + 90bps (Spread)", "notional": 1.0}]}]}}), "OBFR01")
check("filed_spread_range: extremes in a middle snapshot of the first fund (50 bp) and in a second fund (125 bp) give (0.0050, 0.0125)",
      validate.filed_spread_range(_wide) == (0.0050, 0.0125), validate.filed_spread_range(_wide))
raises("filed_spread_range refuses a pay leg that does not state its spread",
       lambda: validate.filed_spread_range({"X": {"snapshots": [{"period": "p", "swaps": [{"pay": "OBFR01 flat", "notional": 1.0}]}]}}), "cannot read")
