"""Step 2 (R2 re-fit): validate the model against the live Tradr funds (SPYQ, MQQQ, QQQP) and the issuer's own
NAV figures.

    py scripts\\run_validate_live.py            (from calendar_letf/, with CALENDAR_LETF_DATA / _RATES set)

What it does, in order, for each live fund:
  1. Builds the fund's total-return series: library closing price + distributions added back on ex-date.
  2. Builds the ETF it tracks (SPY / QQQ) as a total return on two bases: (a) the ETF's own price plus its own
     dividends reinvested on their ex-dates (`reference/etf_distributions.csv`), which is exactly what the swaps
     receive and the direct holding earns; (b) the ETF price times the index's total-return / price ratio, less the
     ETF fee (the v1 construction). Basis (a) is the model's input; (b) is kept as a cross-check. They differ only
     in dividend TIMING inside a quarter, which matters for the one-month anchors (section 5).
  3. Runs the model from the fund's inception close with the FEE TIMELINE the filings show (FILED ratios read from
     reference/nav_anchors.csv: the N-CSR FY2025 ratio from inception to 2025-03-31 (MQQQ carries 0.01% excise tax),
     the N-CSRS ratio from 2025-04-01 to 2025-09-30; DERIVED second half of fiscal 2026 from 2025-10-01 to 2026-03-31,
     worked out as 2 x the FY2026 N-CSR realized ratio less the first-half ratio; the 2026 prospectus figure
     1.00 / 1.03 / 1.00% from 2026-04-01, an ASSUMED start date; sensitivity: the FY2026 average held to 2026-07-31)
     and the BALANCE-SHEET STRUCTURE the N-PORTs show, in two windows:
        window 1  inception to 2025-09-30:  all cash plus swaps, no ETF held directly
        window 2  2025-10-01 to the end:    about 0.4 x NAV in the ETF itself, swaps and cash for the rest
     Two readings of each window's balance sheet are run. BASE, "at a reset": direct holding d, swaps s = 2 - d and
     cash k = 1 - d (d = 0 then 0.4), the identity the kernel already assumes (it fixes the notional at each reset and
     lets it drift inside the period). SNAPSHOT: the N-PORT period-end notionals as printed (swaps 2.21 then 1.32 x
     NAV, cash 1.11 then 0.41), which include the drift at the snapshot date. The one number nobody files, c = the
     fraction of OBFR the fund's cash earns, is fitted per fund per window by bisection on the CAGR gap. The gaps at
     c = 0.8 (the estimate derived from the N-CSR income ratios) and c = 1.0 are the residual that remains without a
     fit. The v1 encodings (fixed 2.6% of NAV; filed 1.4% + 1.3 rate turns; the filed 1.5-turn structure, all at the
     prospectus fee 1.00 / 1.03%) run on the same windows for the before/after.
     Two further tables follow the per-fund sections. Window 2: c refitted at d = 0.3 / 0.4 / 0.5 / 0.6, with the all-in
     financing per NAV a year, which does not move with d (c is a residual conditional on d). Window 1: the CAGR gap
     between the v1 filed structure and the fitted one, split into the fee step, the spread-turns step and the
     rate-turns step (validate.gap_decomposition).
  4. Compares the model with every PRIMARY NAV anchor in reference/nav_anchors.csv (inception to 2025-03-31,
     2025-03-31 to 2026-03-31, calendar 2025, one month to 2024-09-30), model and fund-price figures side by side.
  5. Models the three liquidated SPY / QQQ calendar funds (SPYM monthly, SPYB weekly, QQQW weekly: the designs the
     registry carries as MODELED) over their only published month, 2024-08-30 to 2024-09-30, at the live funds'
     terms, as an out-of-sample check (nothing was fitted on them).
  6. Measures the realized multiple: fund return / ETF return over every full calendar period (unchanged, F4).
  7. REAL vs REAL (BACKLOG B19): each live calendar fund against the real 2x DAILY fund on the same index over the
     same dates (SPYQ vs SSO; MQQQ and QQQP vs QLD), both on market prices plus payouts, split into the fee difference
     and the rest, next to the model's design gap at equal costs. The daily funds' total returns must first pass a
     HARD TEST against their own N-CSR (reference/daily_etf_highlights.csv): each fiscal year's market-price total
     return within PEER_TR_TOL_PP and each year's payouts within PEER_DIST_TOL of the filed per-share total; a
     failure exits 1.
Writes results/validate_live.json and results/validate_live.md. Prints provenance banners first.
Model series are never presented as the funds; the funds' PRICES stand in for their NAVs except where an anchor is
the issuer's own NAV figure (then the table says so).
"""
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from calendar_letf import kernel, loader, periods, products, provenance, validate  # noqa: E402
from calendar_letf.study import ENCODINGS  # noqa: E402  (the v1 encodings, for the before/after only)
from calendar_letf.validate import Structure  # noqa: E402

OUT = ROOT / "results"
REFERENCE = ROOT / "reference"

# Where each fund's ETF and index live, and the fund's first reset (its inception date).
FUNDS = {
    "SPYQ": dict(symbol="NASDAQ:SPYQ", etf="AMEX:SPY", index_px="SP:SPX", index_tr="SP:SPXTR", reset_date="2024-09-30"),
    "MQQQ": dict(symbol="NASDAQ:MQQQ", etf="NASDAQ:QQQ", index_px="NASDAQ:NDX", index_tr="NASDAQ:XNDX", reset_date="2024-08-30"),
    "QQQP": dict(symbol="NASDAQ:QQQP", etf="NASDAQ:QQQ", index_px="NASDAQ:NDX", index_tr="NASDAQ:XNDX", reset_date="2024-09-30"),
}
# The ETFs' own expense ratios, used only by the index-ratio cross-check basis (the ETFs pay them out of dividends,
# so that construction must take them off; audit S2 finding 1). VERIFIED from the issuer pages on 2026-10-12: SPY
# 0.0945% gross (SSGA fund page, "Fund Information as of Oct 12 2026"); QQQ 0.18% total (Invesco product page).
ETF_FEE = {"AMEX:SPY": 0.000945, "NASDAQ:QQQ": 0.0018}
# Filed swap terms, notional-weighted at 2026-06-30, READ from the filing extract (ASSUMPTIONS section 6,
# reference/nport_tradr_2026.json) by validate.filed_spread: SPYQ 0.9175%, MQQQ 0.9930%, QQQP 0.9296%. (Until R2 step
# 12e these were typed, and MQQQ's read 0.97%: a review caught it.) A 10 bp spread difference moves the fitted c by
# 0.001 x s / (k x OBFR) = 0.001 x 2.0 / (1.0 x 0.044) = 0.05.
# Window 1 (inception to 2025-09-30) is fitted at the 2026-06-30 mix, the LATEST snapshot in the extract. Window 1's own
# mix changed inside the window (SPYQ: Cowen and Clear Street at 2025-03-31, Wells Fargo added by 2025-06-30; ASSUMPTIONS
# section 6 structure timeline; those N-PORTs were read for notionals in R2 step 2, not for spreads, and are not in the
# extract), so window 1's c is BOUNDED instead: re-fitted at the smallest and the largest spread any filed swap carries
# (validate.filed_spread_range: 75 and 100 bp). The premise that window 1's swaps carried those same two terms has its own
# source: the N-CSR for the fiscal year to 2025-03-31 (EDGAR fp0093842) lists Cowen at OBFR01 + 75 bp and Clear Street and
# Wells Fargo at OBFR01 + 100 bp (R2 step 12g; a typed 2025-03-31 mix used in step 12f is gone).
NPORT_PERIOD = "2026-06-30"
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference", "nport_tradr_2026.json"), encoding="utf-8") as _f:
    _NPORT = json.load(_f)
FILED_SPREAD = {f: validate.filed_spread(_NPORT, f, NPORT_PERIOD) for f in ("SPYQ", "MQQQ", "QQQP")}
SPREAD_BOUNDS = validate.filed_spread_range(_NPORT)          # (0.0075, 0.0100): the bounds for window 1's unknown mix
SPREAD_STATUS = "VERIFIED_NPORT_2026-06-30"
SPREAD_SOURCE = "N-PORT 2026-06-30, notional-weighted 75/100 bp over OBFR, read from reference/nport_tradr_2026.json by validate.filed_spread"

# ---- fee timeline (ASSUMPTIONS section 2) ----
# Four segments per fund (annual decimals). A date below is the LAST day at the old fee (validate.fee_timeline), so the
# new fee starts on the next trading day. SINGLE SOURCE: every filed ratio is read from reference/nav_anchors.csv
# (column expense_ratio_net_pct, PRIMARY rows only) by the row's fund and dates; the script holds no copy of them. Only
# the prospectus fee (products.py) and the derived second half (computed below) come from elsewhere.
#   inception to 2025-03-31   FILED  N-CSR FY2025 financial highlights (row: inception to 2025-03-31); MQQQ 1.31% with excise tax
#   2025-04-01 to 2025-09-30  FILED  N-CSRS to 2025-09-30 (row: 2025-04-01 to 2025-09-30); 1.30% for all three funds
#   2025-10-01 to 2026-03-31  DERIVED  2 x FY2026 ratio - first-half ratio (FY2026 row: 2025-03-31 to 2026-03-31, N-CSR FY2026)
#   2026-04-01 on             prospectus fee, start date ASSUMED
FEE_STEP_0 = "2025-03-31"             # last day of the N-CSR FY2025 period; the N-CSRS first-half ratio starts 2025-04-01
FEE_STEP_1 = "2025-09-30"             # last day of the first-half fee; the DERIVED fee runs 2025-10-01 to 2026-03-31
FEE_STEP_2 = "2026-03-31"             # last day of the DERIVED fee; the prospectus fee starts 2026-04-01
FEE_H1_START = "2025-04-01"           # first day of the N-CSRS period (nav_anchors.csv start_date of the first-half rows)
FEE_SENS_END = "2026-07-31"           # sensitivity: the FY2026 average is held to this date (the prospectus date), then the prospectus fee
FEE_MIN_PCT, FEE_MAX_PCT = 0.05, 5.0  # a filed ratio outside this range (percent) is a typo or a unit slip: refused
FEE_ROW_WHAT = {"fy2025": "N-CSR FY2025, inception to 2025-03-31", "h1": "N-CSRS, 2025-04-01 to 2025-09-30",
                "fy2026": "N-CSR FY2026, 2025-03-31 to 2026-03-31"}


def anchors_table(path=None):
    """reference/nav_anchors.csv: every published NAV figure with its source and status."""
    a = pd.read_csv(path or REFERENCE / "nav_anchors.csv", dtype=str).fillna("")
    for col in ("total_return_nav_pct", "total_return_market_pct", "expense_ratio_net_pct"):
        a[col] = pd.to_numeric(a[col], errors="coerce")
    return a


def filed_fee(anchors, ticker, start, end, what):
    """(annual decimal fee, file line) of the ONE PRIMARY row of `anchors` for `ticker` over `start`..`end`.
    Raises ValueError naming the row (file line number, header = line 1) when the row is absent or duplicated, not
    PRIMARY, has no expense ratio, or has a ratio outside FEE_MIN_PCT..FEE_MAX_PCT percent."""
    sel = anchors[(anchors["ticker"] == ticker) & (anchors["start_date"] == start) & (anchors["end_date"] == end)]
    where = f"nav_anchors.csv {ticker} {start} to {end} ({what})"
    if len(sel) != 1:
        raise ValueError(f"{where}: expected exactly one row, found {len(sel)}"
                         + (f" (file lines {', '.join(str(int(i) + 2) for i in sel.index)})" if len(sel) else ""))
    line, row = int(sel.index[0]) + 2, sel.iloc[0]
    where = f"nav_anchors.csv row {line} ({ticker} {start} to {end}, {what})"
    if row["status"] != "PRIMARY":
        raise ValueError(f"{where}: status is {row['status']!r}, a filed ratio needs a PRIMARY row")
    pct = row["expense_ratio_net_pct"]
    if not np.isfinite(pct):
        raise ValueError(f"{where}: expense_ratio_net_pct is missing")
    if not FEE_MIN_PCT <= pct <= FEE_MAX_PCT:
        raise ValueError(f"{where}: expense_ratio_net_pct {pct} is outside {FEE_MIN_PCT}..{FEE_MAX_PCT} percent (a unit slip?)")
    return round(float(pct) / 100.0, 8), line


def load_filed_fees(path=None):
    """The filed ratios of the three live funds, read from nav_anchors.csv, and the second half of fiscal 2026 derived
    from them: {"fy2025": {fund: fee}, "h1": ..., "fy2026": ..., "derived": ..., "rows": {key: {fund: file line}}}.
    The derived fee is 2 x FY2026 - first half (the fiscal year averages two halves of six months); it must be positive."""
    anchors = anchors_table(path)
    windows = {"fy2025": lambda f: (FUNDS[f]["reset_date"], FEE_STEP_0), "h1": lambda f: (FEE_H1_START, FEE_STEP_1),
               "fy2026": lambda f: (FEE_STEP_0, FEE_STEP_2)}
    out = {k: {} for k in windows}
    rows = {k: {} for k in windows}
    for key, win in windows.items():
        for f in FUNDS:
            out[key][f], rows[key][f] = filed_fee(anchors, f, *win(f), FEE_ROW_WHAT[key])
    out["derived"] = {}
    for f in FUNDS:
        out["derived"][f] = round(2.0 * out["fy2026"][f] - out["h1"][f], 6)
        if not 0.0 < out["derived"][f] <= FEE_MAX_PCT / 100.0:
            raise ValueError(f"derived second-half fee {out['derived'][f]:.4%} for {f} is not a plausible ratio: check "
                             f"nav_anchors.csv rows {rows['fy2026'][f]} (FY2026) and {rows['h1'][f]} (first half)")
    out["rows"] = rows
    return out


_FEES = load_filed_fees()
FEE_FY2025, FEE_FIRST_HALF, FEE_FY2026, FEE_DERIVED = _FEES["fy2025"], _FEES["h1"], _FEES["fy2026"], _FEES["derived"]
FEE_ROWS = _FEES["rows"]              # file lines of nav_anchors.csv behind each figure (shown in the banner and the JSON)


def pct3(d):
    """'1.30 / 1.31 / 1.30%' for a {fund: fee} dict in the order SPYQ / MQQQ / QQQP."""
    return " / ".join(f"{d[f] * 100:.2f}" for f in ("SPYQ", "MQQQ", "QQQP")) + "%"


REGISTRY_FEES = {f: products.PRODUCTS[f].fee for f in ("SPYQ", "MQQQ", "QQQP")}      # the prospectus fees, read from products.py
FEE_STATUS = {
    "inception to 2025-03-31": "FILED: N-CSR FY2025 financial highlights (MQQQ includes 0.01% excise tax)",
    "2025-04-01 to 2025-09-30": "FILED: N-CSRS to 2025-09-30, expense ratio annualized",
    "2025-10-01 to 2026-03-31": "DERIVED from two filed figures: 2 x FY2026 realized ratio - first-half ratio, "
                                "that is (12 x FY2026 - 6 x first half) / 6",
    "2026-04-01 on": f"ASSUMED start date (the first document that shows the {pct3(REGISTRY_FEES)} is the 2026-07-31 prospectus)",
}


def row_text(key):
    """'rows 19-21' (consecutive file lines) or 'rows 10, 12, 13' for the nav_anchors.csv lines behind FEE_ROWS[key]."""
    ls = sorted(FEE_ROWS[key].values())
    return "rows " + (f"{ls[0]}-{ls[-1]}" if ls == list(range(ls[0], ls[-1] + 1)) else ", ".join(str(x) for x in ls))


def fee_source():
    """One line naming the document and the nav_anchors.csv rows behind each fee figure."""
    return (f"inception to {FEE_STEP_0}: N-CSR FY2025 (reference/nav_anchors.csv {row_text('fy2025')}); {FEE_H1_START} to "
            f"{FEE_STEP_1}: N-CSRS (reference/nav_anchors.csv {row_text('h1')}); fiscal year 2026 realized ratio "
            f"{pct3(FEE_FY2026)}: N-CSR EDGAR 0001398344-26-010562 R2 (reference/nav_anchors.csv {row_text('fy2026')}); 2026 ratio "
            f"{pct3({f: products.PRODUCTS[f].fee for f in FUNDS})}: prospectus 2026-07-31")


def fee_series(fund, index, sensitivity=False):
    """The fund's fee timeline on `index`. Base: the FY2025 ratio, then the first-half ratio, then the DERIVED fee, then
    the prospectus fee (registry spec.fee). Sensitivity: the same to 2025-09-30, then the FY2026 average held to
    FEE_SENS_END, then the prospectus fee. A step to the same fee leaves no trace in the series (validate.fee_timeline)."""
    prospectus = products.PRODUCTS[fund].fee
    steps = {FEE_STEP_0: FEE_FIRST_HALF[fund]}
    if sensitivity:
        steps.update({FEE_STEP_1: FEE_FY2026[fund], FEE_SENS_END: prospectus})
    else:
        steps.update({FEE_STEP_1: FEE_DERIVED[fund], FEE_STEP_2: prospectus})
    return validate.fee_timeline(index, FEE_FY2025[fund], steps)


def fee_banner_lines():
    """The fee timeline for the banner: each segment with its value, status and, for a filed figure, its source row."""
    pros = {f: products.PRODUCTS[f].fee for f in FUNDS}
    return [
        "Fee timeline (annual expense ratio, ACT/365; SPYQ / MQQQ / QQQP):",
        f"  inception to {FEE_STEP_0}: {pct3(FEE_FY2025)}  [{FEE_STATUS['inception to 2025-03-31']}; "
        f"reference/nav_anchors.csv {row_text('fy2025')}]",
        f"  {FEE_H1_START} to {FEE_STEP_1}: {pct3(FEE_FIRST_HALF)}  [{FEE_STATUS['2025-04-01 to 2025-09-30']}; "
        f"reference/nav_anchors.csv {row_text('h1')}]",
        f"  2025-10-01 to {FEE_STEP_2}: {pct3(FEE_DERIVED)}  [{FEE_STATUS['2025-10-01 to 2026-03-31']}; "
        f"fiscal year 2026 {pct3(FEE_FY2026)} (reference/nav_anchors.csv {row_text('fy2026')}), first half {pct3(FEE_FIRST_HALF)}]",
        f"  from 2026-04-01: {pct3(pros)}  [{FEE_STATUS['2026-04-01 on']}]",
        f"  sensitivity: the fiscal-year 2026 average {pct3(FEE_FY2026)} held from 2025-10-01 to {FEE_SENS_END}, then {pct3(pros)}.",
    ]

# ---- balance-sheet structure (ASSUMPTIONS section 6; N-PORT quarters) ----
STRUCTURE_SPLIT = "2025-09-30"        # last day of window 1 (a quarter end and month end: a reset for all three funds)
DIRECT_1, DIRECT_2 = 0.0, 0.4         # ETF held directly, as a fraction of NAV: none (to 2025-06-30), 39.6% (2025-09-30)
BASE_1 = dict(swap_turns=2.0 - DIRECT_1, cash_nav=1.0 - DIRECT_1)   # at a reset: s = 2 - d, k = 1 - d
BASE_2 = dict(swap_turns=2.0 - DIRECT_2, cash_nav=1.0 - DIRECT_2)
SNAP_1 = dict(swap_turns=2.21, cash_nav=1.11)     # N-PORT 2025-03-31 as printed: swaps 2.21x NAV, cash 111%, no direct ETF
SNAP_2 = dict(swap_turns=1.32, cash_nav=0.41)     # N-PORT 2025-09-30 as printed: direct ETF 40%, swaps 1.32x, cash 41%
D_SENSITIVITY = (0.3, 0.4, 0.5, 0.6)  # window 2: the direct ETF holding d is only known to 40-62% of NAV in the filings
CASH_YIELD_PRIOR = 0.8                # derived from the N-CSR income ratios (ASSUMPTIONS section 6): an estimate, not a fact
CASH_YIELD_FULL = 1.0

# ---- the liquidated SPY / QQQ calendar funds: the only live record of the MODELED designs ----
LIQUIDATED = {"SPYM": "HYP_SPX_M", "SPYB": "HYP_SPX_W", "QQQW": "HYP_NDX_W"}
LIQUIDATED_WINDOW = ("2024-08-30", "2024-09-30")
MQQQ_SPLIT_FACTOR = 5.0             # 1-for-5 reverse split, effective 2025-06-03 (issuer page). The library is
MQQQ_SPLIT_CUTOFF = "2025-06-01"    # split-adjusted; the only pre-split payout is Dec 2024.
PRICE_VS_NAV_BOUND = ("N-CSR FY to 2025-03-31: market-price total returns -8.12 / -7.94 / -12.12% against NAV "
                      "-8.08 / -7.90 / -12.04% (SPYQ / MQQQ / QQQP), so price and NAV differed by 0.04-0.08 pp over "
                      "six to seven months")


# The last day of every fit and table: the common data end of the three funds at v0.1.0. Without it the windows would
# follow whatever the library holds (in v0.1.1 the MQQQ and QQQP files ran 20 sessions further than SPYQ's, which
# moved the published window-2 figures), and a stranger with newer data could not reproduce them.
VALIDATE_END = "2026-10-09"

# ---- real vs real (section 7, BACKLOG B19) ----
DAILY_PEER = {"SPYQ": "AMEX:SSO", "MQQQ": "AMEX:QLD", "QQQP": "AMEX:QLD"}   # the real 2x daily fund on the same index
RVR_END = "2026-09-30"        # a quarter end (a reset for all three funds) inside every data file on hand
PEER_TR_TOL_PP = 0.02         # the N-CSR prints total returns to 0.01 points: rounding plus one more
PEER_DIST_TOL = 0.005         # the N-CSR prints per-share distributions to the cent: half a cent per fiscal year
PEER_FEE_NOTE = ("the N-CSR net expense ratio of each fiscal year (to May 31); the FY2026 ratio held after 2026-05-31 "
                 "(ASSUMED: no later filing yet)")

REFERENCE_FILES = ("distributions.csv", "etf_distributions.csv", "nav_anchors.csv",      # the CSV tables main() reads
                   "daily_etf_distributions.csv", "daily_etf_highlights.csv")


def build_inputs():
    """The input manifest: every price file and FRED file this script loads (fund, ETF, index price and total-return
    index for each fund; OBFR and DFF), plus the CSV tables in reference/ (fingerprints only; no absolute paths)."""
    symbols = list(dict.fromkeys([s for cfg in FUNDS.values() for s in (cfg["symbol"], cfg["etf"], cfg["index_px"], cfg["index_tr"])]
                                 + list(DAILY_PEER.values())))
    m = provenance.inputs_manifest(symbols, ["OBFR", "DFF"])
    m["reference_dir"] = REFERENCE.name
    m["reference_files"] = provenance.manifest([REFERENCE / n for n in REFERENCE_FILES])
    # the N-PORT extract (JSON, not a CSV table): the source of FILED_SPREAD and SPREAD_BOUNDS, fingerprinted by its bytes
    nport = REFERENCE / "nport_tradr_2026.json"
    m["reference_json"] = [{"file": nport.name, "sha256": provenance.sha256_of(nport), "bytes": provenance.byte_count(nport)}]
    return m


def banner_lines(inputs):
    """Console and markdown banner: the inputs with fingerprints, then the conventions behind every number."""
    spec = products.PRODUCTS["SPYQ"]
    lines = provenance.banner_lines(inputs)
    lines += [f"Reference tables ({inputs['reference_dir']}/): " + str(len(inputs["reference_files"])) + " files"]
    lines += provenance.banner_lines(inputs["reference_files"])[1:]
    lines += fee_banner_lines()
    lines += [
        f"Early-reset trigger: the ETF price close (AMEX:SPY / NASDAQ:QQQ), mode level, drop {spec.early_drop:.0%} from the fund's base; "
        "close-only here because the deepest in-period fall stays far above it (tables below).",
        f"Day counts: financing (OBFR and swap spread) ACT/{kernel.FIN_DAY_COUNT}; expense ratio ACT/{kernel.FEE_DAY_COUNT}.",
        f"Reset dates: last NYSE session of the week / month / quarter (calendar_letf/nyse.py, from {periods.NYSE_FROM.date()}).",
        products.MODELED_NOTE + " (applies to the liquidated-fund section).",
    ]
    return lines


def distributions(fund):
    """Per-share payouts by ex-date, on the same (split-adjusted) basis as the library price."""
    d = pd.read_csv(REFERENCE / "distributions.csv", parse_dates=["ex_date"])
    d = d[(d["ticker"] == fund) & d["ex_date"].notna() & (d["amount_per_share"] > 0)]
    amt = d["amount_per_share"].astype(float).copy()
    note = []
    if fund == "MQQQ":
        pre = d["ex_date"] < pd.Timestamp(MQQQ_SPLIT_CUTOFF)
        amt[pre] = amt[pre] * MQQQ_SPLIT_FACTOR            # pre-split payout quoted per OLD share (ASSUMED x5)
        if pre.any():
            note.append(f"pre-split payout(s) scaled x{MQQQ_SPLIT_FACTOR:g} (ASSUMED; ~0.1% either way)")
    return pd.Series(amt.values, index=pd.DatetimeIndex(d["ex_date"].values)), note


def etf_dividends(ticker, start):
    """The ETF's own cash dividends by ex-date from `start` on (reference/etf_distributions.csv, SECONDARY)."""
    d = pd.read_csv(REFERENCE / "etf_distributions.csv", parse_dates=["ex_date"])
    d = d[(d["ticker"] == ticker) & (d["ex_date"] >= pd.Timestamp(start))]
    return pd.Series(d["amount_per_share"].astype(float).values, index=pd.DatetimeIndex(d["ex_date"].values))


def etf_inputs(etf_symbol, index_px, index_tr, start):
    """ETF price, ETF daily low, ETF total return on its own dividends (the model input) and on the index ratio
    (cross-check), all from `start` (a reset date) on."""
    px_all = loader.load_prices(etf_symbol)
    name = etf_symbol.split(":")[1]
    if pd.Timestamp(start) not in px_all.index:
        raise ValueError(f"{etf_symbol}: {start} is not a trading day in the library")
    etf_px = px_all["close"].astype(float).rename(name).loc[start:]
    etf_low = px_all["low"].astype(float).rename(name + "_low").loc[start:]
    own = validate.fund_total_return(etf_px, etf_dividends(name, start)).rename(name + "_TR")
    idx = validate.etf_total_return(etf_px, loader.close(index_px), loader.close(index_tr), etf_fee=ETF_FEE[etf_symbol])
    return etf_px, etf_low, own, idx


def peer_dividends(ticker):
    """A daily fund's cash payouts by ex-date (reference/daily_etf_distributions.csv, SECONDARY, split-adjusted)."""
    d = pd.read_csv(REFERENCE / "daily_etf_distributions.csv", parse_dates=["ex_date"])
    d = d[d["ticker"] == ticker]
    return pd.Series(d["amount_per_share"].astype(float).values, index=pd.DatetimeIndex(d["ex_date"].values))


def peer_highlights(ticker):
    h = pd.read_csv(REFERENCE / "daily_etf_highlights.csv", parse_dates=["fiscal_year_end"])
    return h[h["ticker"] == ticker].sort_values("fiscal_year_end")


def peer_checks(symbol, px, divs, hl):
    """The daily fund's HARD TEST, one row per N-CSR fiscal year: the market-price total return rebuilt from the
    library closes plus the payouts (reinvested on the ex-date close) against the filed one, and the payouts inside
    the year against the filed per-share total. A fiscal year runs from the last close on or before the previous
    May 31 to the last close on or before this one."""
    tr = validate.fund_total_return(px, divs)
    rows = []
    for _, r in hl.iterrows():
        e = r["fiscal_year_end"]
        s = pd.Timestamp(year=e.year - 1, month=e.month, day=e.day)
        s_row, e_row = px.index[px.index <= s][-1], px.index[px.index <= e][-1]
        got = float(tr.loc[e_row] / tr.loc[s_row] - 1.0) * 100.0
        paid = float(divs[(divs.index > s) & (divs.index <= e)].sum())
        filed_paid = -float(r["dist_total"])                     # the N-CSR prints distributions as negatives
        rows.append(dict(fund=symbol, fiscal_year_end=str(e.date()), start_row=str(s_row.date()), end_row=str(e_row.date()),
                         total_return_rebuilt_pct=got, total_return_market_filed_pct=float(r["total_return_market_pct"]),
                         total_return_nav_filed_pct=float(r["total_return_nav_pct"]), payouts=paid, payouts_filed=filed_paid,
                         tr_error_pp=got - float(r["total_return_market_pct"]), payout_error=paid - filed_paid,
                         passed=bool(abs(got - float(r["total_return_market_pct"])) <= PEER_TR_TOL_PP
                                     and abs(paid - filed_paid) <= PEER_DIST_TOL)))
    return rows


def peer_fee_series(hl, index):
    """The daily fund's filed net expense ratio (annual decimal) on each row: each fiscal year's N-CSR ratio over that
    year (to May 31), the last one held after its end (PEER_FEE_NOTE)."""
    fee = pd.Series(np.nan, index=index)
    for _, r in hl.iterrows():
        e = r["fiscal_year_end"]
        s = pd.Timestamp(year=e.year - 1, month=e.month, day=e.day)
        fee[(index > s) & (index <= e)] = float(r["expense_ratio_net_pct"]) / 100.0
    if fee.isna().all():
        raise ValueError("no filed expense ratio covers the window")
    return fee.ffill().bfill()


def real_vs_real_daily(fund, spec, fund_tr, fee_cal, peer_tr, fee_peer, u_tr, u_px, rate):
    """The realized gap between the real calendar fund and the real daily fund over their shared dates from the
    calendar fund's inception close to RVR_END, split into the filed fee difference and the rest, next to the model's
    design gap: the calendar kernel (the fund's reset and its -35% trigger on the ETF price) less the daily kernel, both
    at L, zero fee and zero spread, financing (L - 1) x DFF, on the ETF's own total return."""
    end = u_tr.index[u_tr.index <= pd.Timestamp(RVR_END)][-1]
    reset = u_tr.index[0]                                       # the inception close: the model's first reset
    first = fund_tr.index[0]                                    # the calendar fund's first price bar (one session later)
    shared = u_tr.loc[first:end].index.intersection(fund_tr.index).intersection(peer_tr.index)
    if shared[0] != first or shared[-1] != end:
        raise ValueError(f"{fund}: both funds need a close on {first.date()} and {end.date()}")
    a, d = fund_tr.loc[shared], peer_tr.loc[shared]
    c_a, c_d = validate.cagr(a / a.iloc[0]), validate.cagr(d / d.iloc[0])
    u, px, r = u_tr.loc[reset:end], u_px.loc[reset:end], rate.loc[reset:end]
    m_cal = kernel.periodic_reset_series(u, r, reset=spec.reset, L=spec.L, spread_per_nav=0.0, fee=0.0,
                                         early_drop=spec.early_drop, early_mode="level", trigger=px)
    m_day = kernel.daily_reset_series(u, r, L=spec.L, spread_per_nav=0.0, fee=0.0)
    m_cal, m_day = m_cal.loc[shared], m_day.loc[shared]         # the resets stay on the fund's schedule; growth on the shared dates
    fa, fd = float(fee_cal.loc[first:end].iloc[1:].mean()), float(fee_peer.loc[first:end].iloc[1:].mean())
    gap = c_a - c_d
    model_gap = validate.cagr(m_cal / m_cal.iloc[0]) - validate.cagr(m_day / m_day.iloc[0])
    # Each fund's own residual cost on the same footing: the spread per NAV a year, on top of (L - 1) x DFF and its
    # filed fee, that makes its kernel grow as the fund did over the shared dates (validate.fit_spread). Its COST DRAG
    # is the CAGR its kernel loses to fee + residual against the same kernel at zero cost. Because each fit reproduces
    # its fund's growth, gap = model gap - calendar drag + daily drag holds to the fit's tolerance: the realized gap
    # splits exactly into the design and the two funds' costs (decomposition_error is the check).
    fee_c, fee_p = fee_cal.loc[reset:end], fee_peer.reindex(u.index).ffill().bfill()

    def cal_at(x):
        return kernel.periodic_reset_series(u, r, reset=spec.reset, L=spec.L, spread_per_nav=x, fee=fee_c,
                                            early_drop=spec.early_drop, early_mode="level", trigger=px)

    def day_at(x):
        return kernel.daily_reset_series(u, r, L=spec.L, spread_per_nav=x, fee=fee_p)

    s_cal = validate.fit_spread(cal_at, a, -0.10, 0.20)["spread_per_nav"]
    s_day = validate.fit_spread(day_at, d, -0.10, 0.20)["spread_per_nav"]

    def growth(nav):
        nav = nav.loc[shared]
        return validate.cagr(nav / nav.iloc[0])

    drag_cal = growth(m_cal) - growth(cal_at(s_cal))
    drag_day = growth(m_day) - growth(day_at(s_day))
    return dict(calendar_fund=fund, daily_fund=DAILY_PEER[fund], reset=spec.reset, L=spec.L, inception=str(reset.date()),
                start=str(first.date()), end=str(end.date()), years=round((end - first).days / 365.25, 4), rows=int(len(shared)),
                cagr_calendar=c_a, cagr_daily=c_d, gap=gap, log_gap=float(np.log1p(c_a) - np.log1p(c_d)),
                fee_calendar=fa, fee_daily=fd, fee_difference=fa - fd, gap_fee_adjusted=gap + (fa - fd),
                model_gap=model_gap, residual_vs_model=gap + (fa - fd) - model_gap,
                model_early_resets=m_cal.attrs["early_resets"], residual_spread_calendar=s_cal, residual_spread_daily=s_day,
                residual_spread_difference=s_day - s_cal, cost_drag_calendar=drag_cal, cost_drag_daily=drag_day,
                decomposition_error=gap - (model_gap - drag_cal + drag_day),
                interval=None, interval_note="two years: too few independent years for an interval (too noisy to test)")


def structural_spec(spec, fund):
    """The product with the filed spread on the 'swaps' basis and OBFR named; turns are carried by the Structure."""
    return replace(spec, costs=replace(
        spec.costs, spread=FILED_SPREAD[fund], spread_status=SPREAD_STATUS, spread_source=SPREAD_SOURCE,
        turns=BASE_2["swap_turns"], turns_status="ASSUMED",
        turns_source="at a reset: swaps = 2 - direct holding (0.4 of NAV from 2025-09-30, N-PORT; 0 before); carried "
                     "per window by validate.Structure, not by this field", spread_basis="swaps", rate_name="OBFR",
        label=f"{fund} filed structure"))


def run_structural(spec, u_tr, u_px, rate, spread, structures, fee):
    """One kernel run with the whole financing in the rate series (validate.structural_rate) and a fee timeline."""
    r = validate.structural_rate(rate, spread, structures)
    return kernel.run(spec, u_tr, r, trigger=u_px, early_mode="level", spread_per_nav=0.0, fee=fee)


def gap_of(nav, real):
    return validate.compare(nav, real)["cagr_gap"]


def fmt_pp(x):
    return "-" if x is None or not np.isfinite(x) else f"{x * 100:+.2f}"


def fmt_c(x):
    return "-" if x is None or not np.isfinite(x) else f"{x:.3f}"


def two_windows(bs1, bs2, c1, c2):
    return [(STRUCTURE_SPLIT, Structure(bs1["swap_turns"], bs1["cash_nav"], c1, "window 1")),
            (None, Structure(bs2["swap_turns"], bs2["cash_nav"], c2, "window 2"))]


def main():
    OUT.mkdir(exist_ok=True)
    inputs = build_inputs()
    banner = banner_lines(inputs)
    print("=" * 100 + "\nSTEP 2: model vs the live funds and the issuer's NAV figures (R2 re-fit)")
    print("\n".join(banner))
    obfr, dff = loader.load_fred("OBFR"), loader.load_fred("DFF")
    anchors = anchors_table()
    results = dict(meta=dict(title="Live-fund validation (step 2, R2 refit)", run_date=str(pd.Timestamp.today().date()),
                             code=provenance.code_fingerprint(__file__)), provenance=dict(
        inputs=inputs, banner=banner,
        fee_fy2025=FEE_FY2025, fee_first_half=FEE_FIRST_HALF, fee_fy2026=FEE_FY2026, fee_derived=FEE_DERIVED,
        fee_prospectus={f: products.PRODUCTS[f].fee for f in FUNDS}, fee_step_dates=[FEE_STEP_0, FEE_STEP_1, FEE_STEP_2],
        fee_anchor_rows=FEE_ROWS, fee_status=FEE_STATUS, fee_source=fee_source(), fee_sensitivity_end=FEE_SENS_END,
        structure_split=STRUCTURE_SPLIT, direct_holding=[DIRECT_1, DIRECT_2], base_1=BASE_1, base_2=BASE_2,
        snapshot_1=SNAP_1, snapshot_2=SNAP_2, cash_yield_prior=CASH_YIELD_PRIOR, filed_spread=FILED_SPREAD,
        spread_bounds=list(SPREAD_BOUNDS), nport_period=NPORT_PERIOD,
        spread_source=SPREAD_SOURCE, etf_fee_crosscheck_basis=ETF_FEE, etf_dividends="reference/etf_distributions.csv (SECONDARY)",
        obfr_to=str(obfr.index[-1].date()), dff_to=str(dff.index[-1].date()), price_vs_nav_bound=PRICE_VS_NAV_BOUND,
        anchors_file="reference/nav_anchors.csv", anchors_rows=int(len(anchors))), funds={}, liquidated={})
    md = ["# Step 2: model vs the live funds and the issuer's NAV figures (R2 re-fit)\n"]
    md.append("**Inputs and conventions.**\n\n```text\n" + "\n".join(banner) + "\n```\n")
    md.append(f"Script `scripts/run_validate_live.py`. Data: TradingView exports via the local library (fund and ETF "
              f"closes and lows, split-adjusted, no distributions); FRED OBFR to {obfr.index[-1].date()} and DFF to "
              f"{dff.index[-1].date()}; fund payouts `reference/distributions.csv`; SPY / QQQ dividends "
              f"`reference/etf_distributions.csv` (SECONDARY: vendor history, latest row cross-checked against a second "
              f"vendor); NAV anchors `reference/nav_anchors.csv` ({len(anchors)} rows, each with its filing); swap terms "
              f"`reference/nport_tradr_2026.json`.\n")
    md.append("**Provenance of the model inputs.**\n"
              f"- Fee timeline (SPYQ / MQQQ / QQQP): {fee_source()}. Inception to {FEE_STEP_0}: {pct3(FEE_FY2025)} "
              f"({FEE_STATUS['inception to 2025-03-31']}). {FEE_H1_START} to {FEE_STEP_1}: {pct3(FEE_FIRST_HALF)} "
              f"({FEE_STATUS['2025-04-01 to 2025-09-30']}). 2025-10-01 to {FEE_STEP_2}: {pct3(FEE_DERIVED)} "
              f"({FEE_STATUS['2025-10-01 to 2026-03-31']}; the N-CSR reports {pct3(FEE_FY2026)} for the whole fiscal year). "
              f"From 2026-04-01: the prospectus {pct3({f: products.PRODUCTS[f].fee for f in FUNDS})} "
              f"({FEE_STATUS['2026-04-01 on']}). Sensitivity: the FY2026 average {pct3(FEE_FY2026)} held from 2025-10-01 to "
              f"{FEE_SENS_END}, then the prospectus fee.\n"
              f"- Balance sheet, window 1 (inception to {STRUCTURE_SPLIT}): no ETF held directly (semi-annual report "
              f"2024-09-30: 100% cash, swaps 1.90-2.01x; N-PORT 2025-03-31: swaps 2.21x, cash 111%; N-PORT 2025-06-30: "
              f"swaps 1.75x, cash 88%). Window 2 ({STRUCTURE_SPLIT} on): ETF held directly about 0.4 x NAV (N-PORT "
              f"2025-09-30: 39.6%, swaps 1.32x, cash 41%; N-CSRS holdings SPYQ 48 / 20 / 32; 40-62% in the 2026 "
              f"snapshots). The switch date is taken as {STRUCTURE_SPLIT}, the first snapshot with a direct holding.\n"
              f"- BASE reading ('at a reset'): swaps s = 2 - d, cash k = 1 - d: {BASE_1['swap_turns']:g} / {BASE_1['cash_nav']:g} "
              f"then {BASE_2['swap_turns']:g} / {BASE_2['cash_nav']:g} x NAV. This is the identity the kernel already "
              f"assumes: it fixes the swap notional at each reset and lets it drift inside the period, so a period-end "
              f"snapshot's notional / NAV (2.21x after a down quarter) must not be fed in again. SNAPSHOT reading (the "
              f"N-PORT notionals as printed): {SNAP_1['swap_turns']:g} / {SNAP_1['cash_nav']:g} then {SNAP_2['swap_turns']:g} / "
              f"{SNAP_2['cash_nav']:g}, shown as the sensitivity. Note that at 2025-09-30, a reset date, printed notional "
              f"1.32 + direct 0.40 = 1.72 < 2: the swaps' unrealized appreciation carries the rest of the exposure, and "
              f"whether the financing leg accrues on the printed notional or on the exposure is OPEN.\n"
              f"- Swap spread per turn: {', '.join(f'{k} {v:.2%}' for k, v in FILED_SPREAD.items())} ({SPREAD_SOURCE}); "
              f"reference rate OBFR (lagged one row: the rate set on t-1 accrues over t-1 to t); financing legs ACT/360, "
              f"fee ACT/365; underlying = the ETF's own total return (price + its dividends reinvested on ex-date, which is "
              f"what the swaps receive); trigger on the ETF price close, level mode.\n"
              f"- Cash yield c (fraction of OBFR the fund's cash earns): FITTED per fund per window; prior "
              f"{CASH_YIELD_PRIOR:g} derived from the N-CSR income ratios (net investment income after waivers 2.38 / "
              f"2.39 / 2.27% plus expenses {pct3(FEE_FY2025)} on a 100%-cash balance sheet while OBFR averaged about 4.5%).\n"
              f"- Price vs NAV: {PRICE_VS_NAV_BOUND}. Fund PRICES stand in for NAVs in every fit; bid-ask noise "
              f"inflates tracking error on thin funds.\n")

    c_fit_w1, dsens_all, decomp_all, rvr_in = {}, {}, {}, {}
    for fund, cfg in FUNDS.items():
        spec = products.PRODUCTS[fund]
        spec_s = structural_spec(spec, fund)
        print("\n" + "=" * 100 + f"\n{fund}\n" + products.banner(spec_s))
        fund_px = loader.close(cfg["symbol"])
        dist, dist_note = distributions(fund)
        fund_tr = validate.fund_total_return(fund_px, dist)
        start, end = pd.Timestamp(cfg["reset_date"]), fund_tr.index[fund_tr.index <= pd.Timestamp(VALIDATE_END)][-1]
        if end != pd.Timestamp(VALIDATE_END):
            raise ValueError(f"{fund}: no close on {VALIDATE_END} (the data ends {fund_tr.index[-1].date()})")
        etf_px, etf_low, etf_own, etf_idx = etf_inputs(cfg["etf"], cfg["index_px"], cfg["index_tr"], cfg["reset_date"])
        u_px, u_low, u_tr, u_idx = etf_px.loc[:end], etf_low.loc[:end], etf_own.loc[:end], etf_idx.loc[:end]
        r_obfr = loader.rate_known_before(u_px.index, obfr, "OBFR", max_hole_days=10)
        r_dff = loader.rate_known_before(u_px.index, dff, "DFF", max_hole_days=10)
        real = fund_tr.loc[:end]
        first_fund_day = real.index[0]
        spread = FILED_SPREAD[fund]
        print(f"fund TR: {fund_tr.attrs['basis']}; payouts {fund_tr.attrs['distributions']} "
              f"({fund_tr.attrs['distribution_total_pct_of_price']:.2f}% of price) {'; '.join(dist_note)}")
        print(f"ETF TR (model input): {etf_own.attrs['basis']}; dividends {len(etf_own.attrs['distributions'])} ex-dates, "
              f"{etf_own.attrs['distribution_total_pct_of_price']:.2f}% of price in total. Cross-check basis: {etf_idx.attrs['basis']}; "
              f"ETF fee {etf_idx.attrs['etf_fee']:.4%}; implied index yield {etf_idx.attrs['implied_dividend_yield_pct']:.2f}%/yr; "
              f"end levels own {u_tr.iloc[-1]:.5f} vs index-ratio {u_idx.iloc[-1]:.5f}")

        fee_tl = fee_series(fund, u_px.index)
        fee_sens = fee_series(fund, u_px.index, sensitivity=True)
        fall = validate.worst_in_period_fall(u_px, spec.reset, low=u_low)
        rvr_in[fund] = dict(spec=spec, fund_tr=real, fee=fee_tl, u_tr=u_tr, u_px=u_px, rate=r_dff)   # for section 7
        fr = results["funds"][fund] = dict(
            inception=cfg["reset_date"], first_fund_bar=str(first_fund_day.date()), end=str(end.date()),
            fund_payouts=fund_tr.attrs["distributions"], etf_dividends=etf_own.attrs["distributions"],
            etf_tr_end_level_own=float(u_tr.iloc[-1]), etf_tr_end_level_index_ratio=float(u_idx.iloc[-1]),
            fee_timeline=fee_tl.attrs["steps"], worst_in_period_fall_of_etf=fall, windows={}, anchors=[])
        md.append(f"\n## {fund}  (inception {cfg['reset_date']}, first price bar {first_fund_day.date()}, data to {end.date()})\n")
        md.append(f"Fee timeline used: {', '.join(f'{d}: {f:.2%}' for d, f in fee_tl.attrs['steps'])}. Fund payouts added back: "
                  f"{fund_tr.attrs['distributions'] or 'none'}. ETF total return on its own dividends ends at "
                  f"{u_tr.iloc[-1]:.4f} vs {u_idx.iloc[-1]:.4f} on the index-ratio basis ({(u_tr.iloc[-1] / u_idx.iloc[-1] - 1) * 100:+.2f}% "
                  f"over the life). Deepest in-period fall of {u_px.name} since the last reset: "
                  f"{fall['close']:.1%} on the close ({fall['close_date']}), {fall['low']:.1%} on the day's low "
                  f"({fall['low_date']}), against the -35% trigger: the early reset never came near, so the three "
                  f"early-reset modes give identical numbers and only level mode is shown.\n")

        # ---- 1. the two windows: structural fit of c, residual at the prior, the v1 encodings ----
        windows = {"w1": (start, pd.Timestamp(STRUCTURE_SPLIT), BASE_1, SNAP_1),
                   "w2": (pd.Timestamp(STRUCTURE_SPLIT), end, BASE_2, SNAP_2),
                   "all": (start, end, None, None)}
        md.append("| window | c, BASE (at-reset s, k) | rate turns s - k c | BASE gap at c = 0.8 | BASE gap at c = 1.0 | "
                  "c, BASE, FY2026 fee to 2026-07-31 | c, SNAPSHOT (s, k as printed) | SNAPSHOT gap at c = 0.8 | "
                  f"v1 filed (1.5 turns, registry fee {pct3(REGISTRY_FEES)}) | v1 fixed 2.6% | v1 rate 1.4% + 1.3 turns | DFF - OBFR (bp) | "
                  "gap with DFF | ETF TR own - index basis (pp) |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        w1_bound_note = None
        for wname, (w_start, w_end, base_bs, snap_bs) in windows.items():
            uw_tr, uw_px, uw_idx = u_tr.loc[w_start:w_end], u_px.loc[w_start:w_end], u_idx.loc[w_start:w_end]
            rw, rw_dff = r_obfr.loc[w_start:w_end], r_dff.loc[w_start:w_end]
            real_w = real.loc[:w_end]
            fee_w, fee_w_sens = fee_tl.loc[w_start:w_end], fee_sens.loc[w_start:w_end]
            basis_diff = float((uw_tr.iloc[-1] / uw_tr.iloc[0]) - (uw_idx.iloc[-1] / uw_idx.iloc[0]))
            row = dict(first=str(w_start.date()), last=str(w_end.date()), etf_tr_own_minus_index_basis=basis_diff)
            if base_bs is None:                                   # whole life: two structures, c from each window's fit
                c1, c2 = fr["windows"]["w1"]["cash_yield"], fr["windows"]["w2"]["cash_yield"]
                structs = two_windows(BASE_1, BASE_2, c1, c2)
                nav_fit = run_structural(spec_s, uw_tr, uw_px, rw, spread, structs, fee_w)
                row.update(cash_yield=None, structures=[st_.describe(spread) for _, st_ in structs],
                           cagr_gap_whole_life=gap_of(nav_fit, real_w))
                fit_c = {"cash_yield": float("nan")}
                turns_txt = f"{c1:.3f} / {c2:.3f} per window"
                gap_prior = gap_full = c_cap = c_snap = gap_snap = float("nan")
                c_bounds = None
            else:
                def build(c, bs=base_bs, fee_s=fee_w, uw_tr=uw_tr, uw_px=uw_px, rw=rw):
                    return run_structural(spec_s, uw_tr, uw_px, rw, spread, [(None, Structure(bs["swap_turns"], bs["cash_nav"], c))], fee_s)
                fit_c = validate.fit_cash_yield(build, real_w)
                st = Structure(base_bs["swap_turns"], base_bs["cash_nav"], fit_c["cash_yield"])
                gap_prior = gap_of(build(CASH_YIELD_PRIOR), real_w)
                gap_full = gap_of(build(CASH_YIELD_FULL), real_w)
                c_cap = validate.fit_cash_yield(lambda c: build(c, fee_s=fee_w_sens), real_w)["cash_yield"]
                c_snap = validate.fit_cash_yield(lambda c: build(c, bs=snap_bs), real_w)["cash_yield"]
                gap_snap = gap_of(build(CASH_YIELD_PRIOR, bs=snap_bs), real_w)
                c_bounds = None
                if wname == "w1":                                      # window 1's c at the two filed spread extremes
                    def build_at(s, bs=base_bs, fee_s=fee_w, uw_tr=uw_tr, uw_px=uw_px, rw=rw):
                        return lambda c: run_structural(spec_s, uw_tr, uw_px, rw, s, [(None, Structure(bs["swap_turns"], bs["cash_nav"], c))], fee_s)
                    cb = validate.cash_yield_at_spreads(build_at, real_w, SPREAD_BOUNDS)
                    c_bounds = dict(spread_lo=SPREAD_BOUNDS[0], spread_hi=SPREAD_BOUNDS[1], cash_yield_at_spread_lo=cb[SPREAD_BOUNDS[0]],
                                    cash_yield_at_spread_hi=cb[SPREAD_BOUNDS[1]],
                                    source=("every filed swap in reference/nport_tradr_2026.json is at 75 or 100 bp (validate.filed_spread_range); "
                                            "window 1's terms: N-CSR fiscal year to 2025-03-31 (EDGAR fp0093842), Cowen OBFR01 + 75 bp, "
                                            "Clear Street and Wells Fargo OBFR01 + 100 bp"))
                nav_fit = build(fit_c["cash_yield"])
                structs = [(None, st)]
                row.update(cash_yield=fit_c["cash_yield"], rate_turns=st.rate_turns, spread_per_nav=st.spread_turns * spread,
                           structure=st.describe(spread), cagr_gap_at_fit=fit_c["cagr_gap_at_fit"],
                           gap_at_prior_0_8=gap_prior, gap_at_full_1_0=gap_full, cash_yield_fy2026_fee_sensitivity=c_cap,
                           cash_yield_bounds_at_filed_spread_extremes=c_bounds,
                           snapshot=dict(**snap_bs, cash_yield=c_snap, gap_at_prior_0_8=gap_snap,
                                         rate_turns=snap_bs["swap_turns"] - snap_bs["cash_nav"] * c_snap))
                turns_txt = f"{st.rate_turns:.3f}"
            nav_dff = run_structural(spec_s, uw_tr, uw_px, rw_dff, spread, structs, fee_w)
            diff_bp = float((rw_dff - rw).iloc[1:].mean() * 1e4)
            row["dff_minus_obfr_bp_mean"] = diff_bp
            row["gap_with_dff"] = gap_of(nav_dff, real_w)
            # the v1 encodings on the same window (each fund's registry fee from products.py, OBFR on 1 turn unless scaled)
            spec_b = replace(spec_s, costs=replace(spec_s.costs, turns=1.5, turns_status="ASSUMED",
                                                   turns_source="v1: ~1.5 swap turns at a reset"))
            v1 = {
                "v1_filed_1p5_turns": kernel.run(spec_b, uw_tr, rw, trigger=uw_px, early_mode="level"),
                "v1_fixed_2p6": kernel.run(spec, uw_tr, rw, trigger=uw_px, early_mode="level",
                                           spread_per_nav=ENCODINGS["fixed"].spread_per_nav),
                "v1_rate_1p3_turns": kernel.run(spec, uw_tr, rw * ENCODINGS["rate"].rate_turns, trigger=uw_px,
                                                early_mode="level", spread_per_nav=ENCODINGS["rate"].spread_per_nav),
            }
            for k_, nav in v1.items():
                row[f"gap_{k_}"] = gap_of(nav, real_w)
            if c_bounds is not None:                          # kept for below the table (a line between rows would break it)
                w1_bound_note = (f"Window 1's cash yield at the filed spread extremes (window 1's own counterparty mix is not in the extract): "
                                 f"c = {c_bounds['cash_yield_at_spread_lo']:.3f} at {c_bounds['spread_lo']:.2%} and {c_bounds['cash_yield_at_spread_hi']:.3f} "
                                 f"at {c_bounds['spread_hi']:.2%}, against {row['cash_yield']:.3f} at the 2026-06-30 mix ({spread:.2%}).")
            if base_bs is not None and wname == "w2":
                # c is a residual that depends on the direct holding d: refit c for each d. The all-in financing per NAV a
                # year, (s - k c) x mean rate + s x spread with s = 2 - d and k = 1 - d, should not move with d.
                gap_days = pd.Series(rw.index, index=rw.index).diff().dt.days.fillna(0).to_numpy(dtype=float)   # days each row's rate accrues
                mean_rate = float((rw.to_numpy() * gap_days).sum() / gap_days.sum())                           # day-weighted mean lagged OBFR
                ds = {}
                for d in D_SENSITIVITY:
                    bs_d = dict(swap_turns=2.0 - d, cash_nav=1.0 - d)
                    c_d = validate.fit_cash_yield(lambda c, bs_d=bs_d: build(c, bs=bs_d), real_w)["cash_yield"]
                    st_d = Structure(bs_d["swap_turns"], bs_d["cash_nav"], c_d)
                    ds[f"{d:g}"] = dict(direct_holding=d, cash_yield=c_d, rate_turns=st_d.rate_turns,
                                        all_in_financing_per_nav=st_d.rate_turns * mean_rate + st_d.spread_turns * spread)
                row["d_sensitivity"] = dict(mean_lagged_obfr=mean_rate, spread=spread, by_d=ds)
                dsens_all[fund] = row["d_sensitivity"]
            if base_bs is not None and wname == "w1":
                # CAGR gap closed by each step from the v1 filed structure to the fitted one, in this order
                fee_v1 = validate.fee_timeline(uw_px.index, spec.fee)
                fee_new = float(fee_w.iloc[1])
                steps = [("v1 filed", v1["v1_filed_1p5_turns"]),
                         (f"fee {spec.fee:.2%} -> {fee_new:.2%}",
                          run_structural(spec_s, uw_tr, uw_px, rw, spread, [(None, validate.fixed_turns_structure(1.5, 1.0))], fee_w)),
                         ("spread turns 1.5 -> 2.0",
                          run_structural(spec_s, uw_tr, uw_px, rw, spread, [(None, validate.fixed_turns_structure(2.0, 1.0))], fee_w)),
                         (f"rate turns 1.0 -> {st.rate_turns:.3f}", nav_fit)]
                dec = validate.gap_decomposition(real_w, steps)
                recon = run_structural(spec_s, uw_tr, uw_px, rw, spread, [(None, validate.fixed_turns_structure(1.5, 1.0))], fee_v1)
                dec["start_reconstruction_error"] = abs(gap_of(recon, real_w) - dec["start_gap"])    # the stepped start equals the v1 run
                row["gap_decomposition"] = decomp_all[fund] = dec
            cmp_fit = validate.compare(nav_fit, real_w)
            row.update(cagr_model=cmp_fit["cagr_model"], cagr_fund=cmp_fit["cagr_real"],
                       tracking_error_ann=cmp_fit["tracking_error_ann"], daily_corr=cmp_fit["daily_corr"],
                       overlap_rows=cmp_fit["overlap_rows"], early_resets=nav_fit.attrs["early_resets"])
            fr["windows"][wname] = row
            label = {"w1": f"1: {w_start.date()} to {w_end.date()}", "w2": f"2: {w_start.date()} to {w_end.date()}",
                     "all": "whole life (c per window)"}[wname]
            md.append(f"| {label} | {fmt_c(fit_c['cash_yield'])} | {turns_txt} | {fmt_pp(gap_prior)} | {fmt_pp(gap_full)} | "
                      f"{fmt_c(c_cap)} | {fmt_c(c_snap)} | {fmt_pp(gap_snap)} | {fmt_pp(row['gap_v1_filed_1p5_turns'])} | "
                      f"{fmt_pp(row['gap_v1_fixed_2p6'])} | {fmt_pp(row['gap_v1_rate_1p3_turns'])} | {diff_bp:+.1f} | "
                      f"{fmt_pp(row['gap_with_dff'])} | {basis_diff * 100:+.2f} |")
            print(f"{fund} {wname:4} {w_start.date()}..{w_end.date()} c {fmt_c(fit_c['cash_yield'])} turns {turns_txt} "
                  f"gap@0.8 {fmt_pp(gap_prior)} gap@1.0 {fmt_pp(gap_full)} c(cap) {fmt_c(c_cap)} | snapshot c {fmt_c(c_snap)} "
                  f"gap@0.8 {fmt_pp(gap_snap)} | v1 filed {row['gap_v1_filed_1p5_turns']:+.2%} fixed {row['gap_v1_fixed_2p6']:+.2%} "
                  f"rate {row['gap_v1_rate_1p3_turns']:+.2%} | DFF-OBFR {diff_bp:+.1f} bp gap(DFF) {row['gap_with_dff']:+.2%} | "
                  f"basis diff {basis_diff * 100:+.2f} pp | TE {cmp_fit['tracking_error_ann']:.2%} corr {cmp_fit['daily_corr']:.3f} "
                  f"rows {cmp_fit['overlap_rows']}")
        if w1_bound_note:
            md.append("\n" + w1_bound_note + "\n")
        c_fit_w1[fund] = fr["windows"]["w1"]["cash_yield"]
        w_all = fr["windows"]["all"]
        md.append(f"\nGaps are model CAGR minus fund CAGR in pp/yr over the window (fund prices + payouts; the fit zeroes "
                  f"the gap by construction, so the fitted c has no gap column). Whole life with the BASE structural model: "
                  f"TE {w_all['tracking_error_ann']:.2%}/yr, daily correlation {w_all['daily_corr']:.3f}, "
                  f"{w_all['overlap_rows']} rows; price vs NAV bound from the N-CSR: 0.04-0.08 pp over the first six to "
                  f"seven months. The last column is the ETF total return on its own dividends minus the index-ratio "
                  f"construction over the window (return units): the two agree over whole quarters.\n")

        # ---- 2. NAV anchors: the structural whole-life model and the v1 encodings against every published figure ----
        c1, c2 = fr["windows"]["w1"]["cash_yield"], fr["windows"]["w2"]["cash_yield"]
        life = {
            "structural_base_fitted_c": run_structural(spec_s, u_tr, u_px, r_obfr, spread, two_windows(BASE_1, BASE_2, c1, c2), fee_tl),
            "structural_base_c_0_8": run_structural(spec_s, u_tr, u_px, r_obfr, spread,
                                                    two_windows(BASE_1, BASE_2, CASH_YIELD_PRIOR, CASH_YIELD_PRIOR), fee_tl),
            "v1_fixed_2p6": kernel.run(spec, u_tr, r_obfr, trigger=u_px, early_mode="level", spread_per_nav=ENCODINGS["fixed"].spread_per_nav),
            "v1_rate_1p3_turns": kernel.run(spec, u_tr, r_obfr * ENCODINGS["rate"].rate_turns, trigger=u_px, early_mode="level",
                                            spread_per_nav=ENCODINGS["rate"].spread_per_nav),
        }
        rows = anchors[(anchors["ticker"] == fund) & anchors["total_return_nav_pct"].notna()]
        md.append("| anchor window | source | status | anchor NAV return | fund price + payouts | 2 x ETF TR | BASE, fitted c | gap pp | "
                  "BASE, c = 0.8 | gap pp | v1 fixed 2.6% | gap pp | v1 rate 1.3 turns | gap pp |\n"
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for _, a in rows.iterrows():
            s_, e_ = a["start_date"], a["end_date"]
            anchor = float(a["total_return_nav_pct"]) / 100.0
            rec = dict(start=s_, end=e_, anchor_nav_return=anchor, source=a["source"], status=a["status"], note=a["note"],
                       anchor_market_return=(None if pd.isna(a["total_return_market_pct"]) else float(a["total_return_market_pct"]) / 100.0),
                       used_as_check=(a["status"] == "PRIMARY"), models={})
            if pd.Timestamp(e_) > u_tr.index[-1] or pd.Timestamp(s_) < u_tr.index[0]:
                rec["skipped"] = "outside the data"
                fr["anchors"].append(rec)
                continue
            fund_ret = (validate.window_return(real, s_, e_) if pd.Timestamp(s_) in real.index and pd.Timestamp(e_) in real.index
                        else None)
            rec["fund_price_return"] = fund_ret
            rec["two_x_etf_tr"] = 2.0 * validate.window_return(u_tr, s_, e_)
            cells = []
            for k_, nav in life.items():
                m = validate.window_return(nav, s_, e_)
                rec["models"][k_] = dict(model_return=m, gap_pp=(m - anchor) * 100)
                cells.append(f"{m:.2%} | {fmt_pp(m - anchor)}")
            fr["anchors"].append(rec)
            src_short = a["source"].split("(")[0].strip()[:60]
            md.append(f"| {s_} to {e_} | {src_short} | {a['status']} | {anchor:.2%} | "
                      f"{'n/a (no price bar on the start date)' if fund_ret is None else f'{fund_ret:.2%}'} | "
                      f"{rec['two_x_etf_tr']:.2%} | " + " | ".join(cells) + " |")
            print(f"{fund} anchor {s_}..{e_} [{a['status']}] NAV {anchor:+.2%} price {fund_ret if fund_ret is None else f'{fund_ret:+.2%}'} "
                  f"2xETF {rec['two_x_etf_tr']:+.2%} " + " ".join(f"{k_} {v['model_return']:+.2%} ({v['gap_pp']:+.2f} pp)" for k_, v in rec["models"].items()))
        md.append("\nAnchor NAV returns are the issuer's own figures (filing in the source column); the model is run from the "
                  "inception close, so the inception-dated anchors need no fund price at all. The fitted-c model used the "
                  "whole fund price path of each window, so anchors inside a window test how evenly the cost is spread "
                  "and how close price is to NAV, not the level (which the fit sets); the c = 0.8 column is the prior with "
                  "nothing fitted. '2 x ETF TR' is the gross promise before any cost.\n")

        # ---- 3. the product's promise: fund return vs ETF return per full period (F4, unchanged) ----
        for basis, lvl in (("price", etf_px), ("total_return", etf_own)):
            pm = validate.period_multiple(real, lvl.loc[real.index[0]:], spec.reset)
            reg = validate.period_regression(pm)
            fr[f"period_multiple_{basis}"] = dict(
                periods=int(len(pm)), regression=reg,
                multiple_mean=float(pm["multiple"].mean()), multiple_median=float(pm["multiple"].median()),
                multiple_min=float(pm["multiple"].min()), multiple_max=float(pm["multiple"].max()),
                ratio_filter_min_abs_etf_return=validate.DEFAULT_MIN_ABS_ETF_RETURN[spec.reset],
                fund_minus_2x_etf_mean_pct=float(pm["fund_minus_2x_etf"].mean() * 100),
                fund_minus_2x_etf_sum_pct=float(pm["fund_minus_2x_etf"].sum() * 100),
                table=[{k_: (str(v) if hasattr(v, "isoformat") else v) for k_, v in r_.items()} for r_ in pm.to_dict("records")])
            s = fr[f"period_multiple_{basis}"]
            md.append(f"Fund vs ETF {basis}, {s['periods']} full {spec.reset[:-2]}s: regression slope **{reg['slope']:.3f}** "
                      f"(the delivered multiple), intercept **{reg['intercept_pct_per_period']:+.2f} pp per period** "
                      f"(the cost), R² {reg['r2']:.3f}. Ratio fund/ETF where |ETF| >= "
                      f"{s['ratio_filter_min_abs_etf_return']:.1%}: median {s['multiple_median']:.2f}, range "
                      f"{s['multiple_min']:.2f} to {s['multiple_max']:.2f}. Fund minus 2x ETF: mean "
                      f"{s['fund_minus_2x_etf_mean_pct']:+.2f} pp per period.\n")
            print(f"{fund} vs ETF {basis}: n={s['periods']} slope {reg['slope']:.3f} intercept {reg['intercept_pct_per_period']:+.2f} "
                  f"pp/period R2 {reg['r2']:.3f}; ratio median {s['multiple_median']:.2f} [{s['multiple_min']:.2f}, {s['multiple_max']:.2f}]")

    # ---- 3b. window 2: the fitted cash yield c at other direct holdings d; window 1: the v1 gap, step by step ----
    md.append("\n## Window 2: the fitted cash yield c depends on the assumed direct holding d\n")
    md.append(f"Window 2 starts {STRUCTURE_SPLIT}. The filings put the direct ETF holding at 40-62% of NAV, so each fund is refitted "
              f"at d = {' / '.join(f'{d:g}' for d in D_SENSITIVITY)} (swaps s = 2 - d, cash k = 1 - d; the fit sets the CAGR gap to zero in "
              "every column). **c is a residual conditional on the assumed direct holding d; the invariant is the all-in financing.** "
              "The all-in financing per NAV a year is (s - k c) x the day-weighted mean lagged OBFR of the window + s x the filed spread; "
              "it does not move with d, because each fit must reproduce the same fund growth.\n")
    head_d = ([f"c at d = {d:g}" for d in D_SENSITIVITY] + [f"all-in financing, d = {d:g}" for d in D_SENSITIVITY]
              + ["mean lagged OBFR (day-weighted)"])
    rows_d = []
    for fund_, ds_ in dsens_all.items():
        rows_d.append([fund_] + [fmt_c(ds_["by_d"][f"{d:g}"]["cash_yield"]) for d in D_SENSITIVITY]
                      + [f"{ds_['by_d'][f'{d:g}']['all_in_financing_per_nav'] * 100:.2f}%" for d in D_SENSITIVITY]
                      + [f"{ds_['mean_lagged_obfr'] * 100:.2f}%"])
    md.append("| fund | " + " | ".join(head_d) + " |\n|" + "---|" * (len(head_d) + 1))
    md.extend("| " + " | ".join(r_) + " |" for r_ in rows_d)
    print("\nWindow 2 d-sensitivity (c; all-in financing % of NAV a year; mean lagged OBFR)")
    for r_ in rows_d:
        print("  " + " | ".join(r_))
    md.append("\n## Window 1: which input closes how much of the v1 CAGR gap\n")
    md.append(f"Start: the v1 filed structure (fee {pct3(REGISTRY_FEES)} for SPYQ / MQQQ / QQQP; 1.5 swap turns; 1.0 rate turn). Each step changes one input of the "
              "step before and shows how many percentage points a year of the CAGR gap (model minus fund) it closes: first the fee to "
              f"the filed ratio ({pct3(FEE_FY2025)} to {FEE_STEP_0}, then {pct3(FEE_FIRST_HALF)} to {FEE_STEP_1}), then the swap turns to 2.0, "
              "then the rate turns to the fitted s - k c. The "
              "pieces add up to the v1 gap, because the last model is the fitted one (gap zero).\n")
    md.append("| fund | v1 filed gap (pp a year) | fee step | spread-turns step | rate-turns step | sum of steps | fitted rate turns |\n"
              "|---|---|---|---|---|---|---|")
    for fund_, dc in decomp_all.items():
        md.append(f"| {fund_} | {dc['start_gap'] * 100:+.3f} | " + " | ".join(f"{x * 100:+.3f}" for x in dc["closed"])
                  + f" | {sum(dc['closed']) * 100:+.3f} | " + dc["labels"][3].split("-> ")[1] + " |")
        print(f"{fund_} window 1 v1 gap {dc['start_gap'] * 100:+.3f} pp = " + " + ".join(f"{x * 100:+.3f}" for x in dc["closed"])
              + f" = {sum(dc['closed']) * 100:+.3f}; stepped start vs v1 run: {dc['start_reconstruction_error']:.1e}")
    md.append("")

    # ---- 4. the liquidated SPY / QQQ calendar funds over their one published month (out of sample) ----
    # the one-month report ratio of each liquidated fund, from the same CSV (nav_anchors.csv, the semi-annual report rows)
    liq_fee = {t: filed_fee(anchors, t, *LIQUIDATED_WINDOW, "semi-annual report to 2024-09-30") for t in LIQUIDATED}
    if len({v[0] for v in liq_fee.values()}) != 1:
        raise ValueError(f"the liquidated funds' filed ratios differ: {liq_fee}; the text below assumes one value")
    liq_fee_txt = f"{next(iter(liq_fee.values()))[0]:.2%}"
    c_live =float(np.mean(list(c_fit_w1.values())))
    results["provenance"]["liquidated_cash_yield_used"] = dict(value=c_live, rule="mean of the three live funds' window-1 BASE fits")
    md.append("\n## Liquidated calendar funds, one month 2024-08-30 to 2024-09-30 (out of sample)\n")
    md.append(f"SPYM (2x SPY monthly), SPYB (2x SPY weekly) and QQQW (2x QQQ weekly) launched 2024-08-30 and were liquidated "
              f"2025-02-28; their only published NAV figures are the one-month total returns in the semi-annual report to "
              f"2024-09-30 (PRIMARY). The registry carries these designs as MODELED (HYP_SPX_M, HYP_SPX_W, HYP_NDX_W). Each is "
              f"modeled here from the 2024-08-30 close at the live funds' window-1 terms: fee {liq_fee_txt} (their filed ratio), BASE balance sheet (swaps "
              f"{BASE_1['swap_turns']:g} x NAV at the filed spread of the live fund on the same ETF, cash {BASE_1['cash_nav']:g} x NAV) "
              f"earning c = {c_live:.3f} x OBFR (the mean of the three live funds' window-1 fits; c = {CASH_YIELD_PRIOR:g} and "
              f"{CASH_YIELD_FULL:g} shown too). Nothing was fitted on these funds. The semi-annual report's swap notionals at "
              f"2024-09-30 were SPYM 1.97x, SPYB 1.96x, QQQW 1.98x. The last model column repeats the fitted-c model on the v1 "
              f"ETF total-return construction (index-ratio basis), which mistimes the ETF's September ex-dividend inside this "
              f"month. Liquidation values (SECONDARY) are listed, not used.\n")
    v1_fees = " / ".join(f"{f * 100:.2f}" for f in sorted({products.PRODUCTS[p].fee for p in LIQUIDATED.values()})) + "%"
    md.append("| fund | design | anchor NAV return | market return | 2 x ETF TR | model c fitted | gap pp | model c = 0.8 | gap pp | "
              f"model c = 1.0 | gap pp | v1 fixed 2.6% (registry fee {v1_fees}) | gap pp | fitted c on the index-ratio ETF basis | gap pp | "
              "resets in the month |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    s0, e0 = LIQUIDATED_WINDOW
    for tkr, pname in LIQUIDATED.items():
        spec = products.PRODUCTS[pname]
        live_on_same_etf = "SPYQ" if spec.underlying == "SPX" else "MQQQ"
        spread = FILED_SPREAD[live_on_same_etf]
        spec_s = structural_spec(spec, live_on_same_etf)
        cfg = FUNDS[live_on_same_etf]
        etf_px, etf_low, etf_own, etf_idx = etf_inputs(cfg["etf"], cfg["index_px"], cfg["index_tr"], s0)
        u_px, u_tr, u_idx = etf_px.loc[s0:e0], etf_own.loc[s0:e0], etf_idx.loc[s0:e0]
        r_obfr = loader.rate_known_before(u_px.index, obfr, "OBFR", max_hole_days=10)
        a = anchors[(anchors["ticker"] == tkr) & (anchors["start_date"] == s0) & (anchors["end_date"] == e0)].iloc[0]
        anchor = float(a["total_return_nav_pct"]) / 100.0
        liq = anchors[(anchors["ticker"] == tkr) & (anchors["status"] == "SECONDARY")]
        fee_liq = liq_fee[tkr][0]
        fee_flat = validate.fee_timeline(u_px.index, fee_liq)
        rec = dict(product=pname, underlying=spec.underlying, reset=spec.reset, start=s0, end=e0, anchor_nav_return=anchor,
                   anchor_market_return=float(a["total_return_market_pct"]) / 100.0, source=a["source"], status=a["status"],
                   fee=fee_liq, spread=spread, structure=BASE_1, two_x_etf_tr=2.0 * validate.window_return(u_tr, s0, e0), models={},
                   liquidation_secondary=(None if liq.empty else dict(end=liq.iloc[0]["end_date"], nav_end=liq.iloc[0]["nav_end"],
                                                                      total_return_pct=float(liq.iloc[0]["total_return_nav_pct"]),
                                                                      source=liq.iloc[0]["source"])))
        cells = []
        for k_, c, uu in (("c_fitted_live_mean", c_live, u_tr), ("c_prior_0_8", CASH_YIELD_PRIOR, u_tr), ("c_full_1_0", CASH_YIELD_FULL, u_tr)):
            nav = run_structural(spec_s, uu, u_px, r_obfr, spread, [(None, Structure(BASE_1["swap_turns"], BASE_1["cash_nav"], c))], fee_flat)
            m = validate.window_return(nav, s0, e0)
            rec["models"][k_] = dict(cash_yield=c, model_return=m, gap_pp=(m - anchor) * 100)
            cells.append(f"{m:.2%} | {fmt_pp(m - anchor)}")
        nav_v1 = kernel.run(spec, u_tr, r_obfr, trigger=u_px, early_mode="level", spread_per_nav=ENCODINGS["fixed"].spread_per_nav)
        m_v1 = validate.window_return(nav_v1, s0, e0)
        rec["models"]["v1_fixed_2p6"] = dict(model_return=m_v1, gap_pp=(m_v1 - anchor) * 100)
        nav_idx = run_structural(spec_s, u_idx, u_px, r_obfr, spread, [(None, Structure(BASE_1["swap_turns"], BASE_1["cash_nav"], c_live))], fee_flat)
        m_idx = validate.window_return(nav_idx, s0, e0)
        rec["models"]["c_fitted_on_index_ratio_etf_basis"] = dict(cash_yield=c_live, model_return=m_idx, gap_pp=(m_idx - anchor) * 100)
        n_resets = int(np.count_nonzero(np.asarray(periods.period_end_flags(u_px.index, spec.reset))[1:-1]))
        rec["period_resets_inside_month"] = n_resets
        results["liquidated"][tkr] = rec
        md.append(f"| {tkr} | {pname} ({spec.underlying} {spec.reset}) | {anchor:.2%} | {rec['anchor_market_return']:.2%} | "
                  f"{rec['two_x_etf_tr']:.2%} | " + " | ".join(cells) + f" | {m_v1:.2%} | {fmt_pp(m_v1 - anchor)} | {m_idx:.2%} | "
                  f"{fmt_pp(m_idx - anchor)} | {n_resets} |")
        print(f"{tkr} ({pname}) anchor {anchor:+.2%} 2xETF {rec['two_x_etf_tr']:+.2%} "
              + " ".join(f"{k_} {v['model_return']:+.2%} ({v['gap_pp']:+.2f} pp)" for k_, v in rec["models"].items()))
    secondary = anchors[anchors["status"] == "SECONDARY"]
    md.append("\nSECONDARY liquidation values (brokerage corporate-actions record, not a filing; shown, not used): "
              + "; ".join(f"{r.ticker} {r.end_date} {r.nav_end} per share from 25.00 ({float(r.total_return_nav_pct):+.2f}%)"
                          for r in secondary.itertuples()) + ".\n")
    md.append("Out of scope (underlying not in this kit): SOXM, SOXW (SOXX), NVDW (NVDA, 1.75x), TSLW (TSLA, 1.5x), TLTM, TLTQ (TLT); "
              "their one-month anchors are in `reference/nav_anchors.csv`.\n")

    # ---- 7. real vs real: each live calendar fund against the real 2x daily fund on the same index (B19) ----
    peer_tr, peer_fee, checks = {}, {}, []
    for sym in dict.fromkeys(DAILY_PEER.values()):
        tkr = sym.split(":")[1]
        px, divs, hl = loader.close(sym), peer_dividends(tkr), peer_highlights(tkr)
        checks += peer_checks(tkr, px, divs, hl)
        first = pd.Timestamp(min(c["reset_date"] for c in FUNDS.values()))
        tr = validate.fund_total_return(px.loc[first:], divs[divs.index > first])
        peer_tr[sym], peer_fee[sym] = tr, peer_fee_series(hl, tr.index)
    peer_ok = all(c["passed"] for c in checks)
    rvr = [real_vs_real_daily(f, x["spec"], x["fund_tr"], x["fee"], peer_tr[DAILY_PEER[f]], peer_fee[DAILY_PEER[f]],
                              x["u_tr"], x["u_px"], x["rate"]) for f, x in rvr_in.items()]
    results["real_vs_real_daily"] = dict(peer_hard_test="PASS" if peer_ok else "FAIL", peer_checks=checks, rows=rvr,
                                         peer_tr_tol_pp=PEER_TR_TOL_PP, peer_dist_tol=PEER_DIST_TOL, end=RVR_END,
                                         peer_fee_note=PEER_FEE_NOTE,
                                         peer_payouts="reference/daily_etf_distributions.csv (SECONDARY; fiscal-year sums checked)",
                                         peer_filing="reference/daily_etf_highlights.csv (N-CSR, accession on every row)")
    md.append("\n## Real calendar fund vs real daily fund, inception to " + RVR_END + " (BACKLOG B19)\n")
    md.append(f"The real 2x DAILY fund on the same index: SSO (S&P 500) and QLD (Nasdaq-100), on market prices plus payouts "
              f"reinvested on the ex-date close, like the calendar funds. Hard test first: each daily fund's total return "
              f"rebuilt this way against its own N-CSR market-price total return per fiscal year (within {PEER_TR_TOL_PP} "
              f"points), and its payouts against the filed per-share total (within {PEER_DIST_TOL}): "
              f"**{results['real_vs_real_daily']['peer_hard_test']}**.\n")
    md.append("| daily fund | fiscal year to | rebuilt % | N-CSR market % | N-CSR NAV % | payouts | filed | passed |\n"
              "|---|---|---|---|---|---|---|---|")
    for c in checks:
        md.append(f"| {c['fund']} | {c['fiscal_year_end']} | {c['total_return_rebuilt_pct']:.2f} | {c['total_return_market_filed_pct']:.2f} | "
                  f"{c['total_return_nav_filed_pct']:.2f} | {c['payouts']:.5f} | {c['payouts_filed']:.2f} | {c['passed']} |")
    md.append(f"\nFees: the calendar funds' fee timeline above; the daily funds' {PEER_FEE_NOTE}. The model gap runs both "
              "kernels at equal costs (zero fee, zero spread, (L - 1) x DFF) on the ETF's own total return; the calendar "
              "kernel keeps the fund's -35% trigger. Gaps are CAGR differences in pp a year; 'rest' = fee-adjusted gap "
              "minus model gap: everything else (cash yield, swap terms, price vs NAV at the ends).\n")
    md.append("| calendar | daily | reset | window | years | CAGR calendar % | CAGR daily % | gap | log gap | fee difference | "
              "gap fee-adjusted | model gap (equal costs) | rest | residual cost calendar / daily, % of NAV a year | "
              "cost drag calendar / daily, pp a year | interval |\n"
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for p in rvr:
        md.append(f"| {p['calendar_fund']} | {p['daily_fund']} | {p['reset']} | {p['start']} to {p['end']} | {p['years']:.2f} | "
                  f"{p['cagr_calendar'] * 100:+.2f} | {p['cagr_daily'] * 100:+.2f} | {fmt_pp(p['gap'])} | {fmt_pp(p['log_gap'])} | "
                  f"{fmt_pp(p['fee_difference'])} | {fmt_pp(p['gap_fee_adjusted'])} | {fmt_pp(p['model_gap'])} | "
                  f"{fmt_pp(p['residual_vs_model'])} | "
                  f"{fmt_pp(p['residual_spread_calendar'])} / {fmt_pp(p['residual_spread_daily'])} | "
                  f"{fmt_pp(p['cost_drag_calendar'])} / {fmt_pp(p['cost_drag_daily'])} | {p['interval_note']} |")
        print(f"real vs real {p['calendar_fund']} - {p['daily_fund']} {p['start']}..{p['end']}: gap {p['gap']:+.2%}, "
              f"fee-adjusted {p['gap_fee_adjusted']:+.2%}, model {p['model_gap']:+.2%}, rest {p['residual_vs_model']:+.2%}; "
              f"residual cost {p['residual_spread_calendar']:+.2%} / {p['residual_spread_daily']:+.2%}; cost drag "
              f"{p['cost_drag_calendar']:+.2%} / {p['cost_drag_daily']:+.2%}; decomposition error {p['decomposition_error']:.1e}")
    md.append("\nResidual cost: the spread per NAV a year, on top of (L - 1) x DFF and the filed fee, that makes each fund's own "
              "kernel grow as the fund did on the shared dates (validate.fit_spread), on the ETF's own total return for both "
              "funds (the daily funds track the index itself, so theirs also absorbs the ETF's fee). It is a residual: cash "
              "yield, swap terms and price vs NAV, not a filed term. Cost drag: the CAGR each fund's kernel loses to its fee "
              "plus its residual cost, against the same kernel at zero cost. Because each fit reproduces its fund, the gap "
              "splits exactly: gap = model gap - calendar drag + daily drag (to the fit's tolerance).\n")
    for c in checks:
        print(f"peer check {c['fund']} FY to {c['fiscal_year_end']}: TR {c['total_return_rebuilt_pct']:.2f} vs "
              f"{c['total_return_market_filed_pct']:.2f}; payouts {c['payouts']:.5f} vs {c['payouts_filed']:.2f}: {c['passed']}")
    md.append("")

    (OUT / "validate_live.json").write_text(json.dumps(provenance.json_safe(results), indent=2, allow_nan=False), encoding="utf-8")
    (OUT / "validate_live.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nwrote {OUT / 'validate_live.json'} and validate_live.md")
    if not peer_ok:
        print("DAILY-FUND HARD TEST FAILED on:\n  " + "\n  ".join(str(c) for c in checks if not c["passed"]))
        sys.exit(1)


if __name__ == "__main__":
    main()
