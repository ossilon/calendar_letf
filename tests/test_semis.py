"""BACKLOG B16: calendar-reset funds on semiconductors. study.clean_lows, the SOXX index-basis labels, the semiconductor
designs and their filed inputs, and the results file results/semis.json.

Part A, planted (made-up data or an independent reading of the reference files with the csv / json modules). Part B
checks what must hold in any correct run, and the qualitative claims of FINDINGS F26.
"""
import csv
import importlib.util
import json

import numpy as np
import pandas as pd

from _harness import ROOT, check
from calendar_letf import products, study

spec_ = importlib.util.spec_from_file_location("run_semis", ROOT / "scripts" / "run_semis.py")
RS = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(RS)

# ---- A1. bad daily lows of a single series ----
ix = pd.bdate_range("2024-01-01", periods=6)
close = pd.Series([100.0, 100.0, 100.0, 120.0, 80.0, 80.0], index=ix)
low = pd.Series([99.0, 48.0, 91.0, 100.5, 79.0, 75.0], index=ix)
clean, bad = study.clean_lows(close, low)
check("clean_lows: a low 52% below both closes is a bad print and becomes the close; a rally day's low near the previous close "
      "(17% below its own close) stays; a crash day's low near its close stays",
      bad == ["2024-01-02"] and clean.iloc[1] == 100.0 and clean.iloc[3] == 100.5 and clean.iloc[4] == 79.0, (bad, clean.tolist()))
check("clean_lows BREAK: a low exactly 10% below the lower close stays; a hair more is replaced (day 6: floor 72.0)",
      study.clean_lows(close, low.where(low.index != ix[5], 72.0))[1] == ["2024-01-02"]
      and study.clean_lows(close, low.where(low.index != ix[5], 71.99))[1] == ["2024-01-02", "2024-01-08"])

# ---- A2. the SOXX index basis (SECONDARY dates) ----
check("soxx_index_on: three indexes; the boundaries belong to the period that starts or ends there",
      RS.soxx_index_on("2010-10-14").startswith("S&P") and RS.soxx_index_on("2010-10-15").startswith("PHLX")
      and RS.soxx_index_on("2021-06-20").startswith("PHLX") and RS.soxx_index_on("2021-06-21").startswith("NYSE")
      and RS.soxx_index_on("2001-07-12") is None)

# ---- A3. the designs and their filed inputs, read independently ----
rows = [r for r in csv.DictReader(open(ROOT / "reference" / "nav_anchors.csv", encoding="utf-8")) if r["ticker"] in ("SOXM", "SOXW") and r["status"] == "PRIMARY"]
usd = json.loads((ROOT / "reference" / "nport_semis_2026.json").read_text(encoding="utf-8"))["USD"]
d2 = RS.base_design("monthly")
check("semis design: the fee is SOXM / SOXW's filed net expense ratio and the spread per turn is USD's N-PORT weighted spread",
      len(rows) == 2 and d2.fee == float(rows[0]["expense_ratio_net_pct"]) / 100 and d2.costs.spread == usd["weighted_spread_pct"] / 100
      and d2.underlying == "SOX" and d2.kind == "MODELED" and "HYPOTHETICAL" in d2.note)
p15 = RS.spec_at("weekly", 1.5, "scaled")
check("semis design at 1.5x: 1.5 swap turns (notional basis), trigger at 0.70 / 1.5, and its encoding pays 1.5 x the spread per turn",
      p15.costs.turns == 1.5 and abs(p15.early_drop - 0.7 / 1.5) < 1e-15 and abs(RS.enc_at(1.5).spread_per_nav - 1.5 * d2.costs.spread) < 1e-15)

# ---- A4. SOXX's own total return and its payouts' split basis ----
px = pd.Series([100.0, 98.0, 99.0], index=pd.bdate_range("2024-09-24", periods=3))
tr = RS.own_total_return(px, pd.Series([1.0], index=[pd.Timestamp("2024-09-25")]))
check("own_total_return: a $1 payout on a $98 ex-date close: day 2 is (98 + 1) / 100, day 3 adds 99 / 98",
      abs(tr.iloc[1] - 0.99) < 1e-15 and abs(tr.iloc[2] - 0.99 * 99 / 98) < 1e-15, tr.tolist())
splits = list(csv.DictReader(open(ROOT / "reference" / "soxx_splits.csv", encoding="utf-8")))
pay = list(csv.DictReader(open(ROOT / "reference" / "soxx_distributions.csv", encoding="utf-8")))
want = [3 if r["ex_date"] < splits[0]["first_split_adjusted_day"] else 1 for r in pay]
check("soxx payouts: every payout before the 3-for-1 split of 2026-11-05 (SEC 497, PRIMARY) is divided by 3, and the published "
      "amount is kept", splits[0]["ratio"] == "3" and splits[0]["status"] == "PRIMARY" and [int(r["split_factor"]) for r in pay] == want
      and all(abs(float(r["amount_per_share"]) * int(r["split_factor"]) - float(r["amount_as_published"])) < 1e-9 for r in pay))

# ================================================================ Part B: the results file
res = json.loads((ROOT / "results" / "semis.json").read_text(encoding="utf-8"))
m, W = res["meta"], res["world"]
check("results: the single bad low removed from NASDAQ:SOX is 1997-08-08", m["underlying"]["bad_low_days"] == ["1997-08-08"])
check("results: every row names the index basis (SOX price only)", all(r["basis"] == RS.BASIS_LABEL for r in W["named"]) and "price only" in m["basis"])
v = W["validation"]
check("results: the SOXM / SOXW check has run, with the filed anchors and SOXX's index in that month (NYSE, SECONDARY)",
      v["status"].startswith("RUN") and sorted(a["ticker"] for a in v["anchor_rows"]) == ["SOXM", "SOXW"]
      and all(abs(a["nav_return_pct"] - float(next(r for r in rows if r["ticker"] == a["ticker"])["total_return_nav_pct"])) < 1e-12 for a in v["anchor_rows"])
      and v["soxx_index_in_window"] == RS.soxx_index_on("2024-09-30") and v["soxx_index_in_window"].startswith("NYSE"))
check("results: 5 L x 3 trigger rules x 3 resets named rows; the 0.05 curve has 41 L x 4 designs",
      len(W["named"]) == 45 and len(W["curve"]) == 41 * 4)
G = {(c["reset"], c["L"]): c["growth"] for c in W["curve"]}
ok = all(p["L_best"] == max((L for (r, L), g in G.items() if r == p["reset"] and g is not None and (p["scope"] == "to3" or L <= 2.0)),
                            key=lambda L: (G[(p["reset"], L)], -L)) for p in W["plateau"])
check("results: each best L is the argmax of its curve's growth", ok)
cs = {(r["L"], r["cost"], r["product"]): r["cagr"] for r in W["cost_sensitivity"]}
check("results: costs only hurt (CAGR falls from no spread to USD's spread to twice it, at 2x and 3x)",
      all(cs[(L, "zero", p)] > cs[(L, "usd", p)] > cs[(L, "double", p)] for (L, _, p) in cs))
check("results: the check's model rows reread the c it quotes from the CURRENT results/validate_live.json",
      v["validate_live_sha256"] == __import__("calendar_letf.provenance", fromlist=["x"]).sha256_of(ROOT / "results" / "validate_live.json"))
# the qualitative claims of FINDINGS F26
check("F26: the one-month check passes: every model row is within 0.1 points of the filed return (F1b's standard)",
      v["max_abs_gap_pp"] < 0.1 and len(v["rows"]) == 2, v["max_abs_gap_pp"])
bw = {(b["reset"], b["L"]): b["gap_at_zero_fee_with_soxx_yield"] for b in W["break_even"]}
check("F26: with SOXX's mean yield added back, only the 1.5x weekly and monthly designs edge ahead with no fee, and none ahead "
      "at the 1.30% fee", sorted(k for k, g in bw.items() if g > 0) == [("monthly", 1.5), ("weekly", 1.5)]
      and all(g - m["fee"] < 0 for g in bw.values()))
check("F26: no fund at or under 2x dies on the history, under any trigger rule",
      all(r["terminated"] is None for r in W["named"] if r["L"] <= 2.0))
check("F26: at every L and reset the fund trails the price index even with no fee (no break-even fee exists)",
      all(b["fee"] is None and b["log_growth_gap_at_zero_fee"] < 0 for b in W["break_even"]))
check("F26: the best L is 1.00 in every design, and the plateau at or under 2x reaches 2.00",
      all(p["L_best"] == 1.0 for p in W["plateau"]) and all(p["plateau_hi"] == 2.0 for p in W["plateau"] if p["scope"] == "under2"))
wm = [r for r in W["named"] if r["trigger"] == "none" and r["reset"] in ("weekly", "monthly") and r["L"] in (1.2, 1.5, 1.7)]
check("F26: with no trigger the weekly and monthly designs at 1.2x, 1.5x and 1.7x lead their daily twins: every yearly interval "
      "excludes zero and passes the coverage check", len(wm) == 6 and all(r["gap_yearly"]["lo"] > 0 and r["gap_yearly"]["verdict"] == "valid" for r in wm))
term3 = {r["reset"]: r["terminated"] for r in W["named"] if r["L"] == 3.0 and r["trigger"] == "none"}
check("F26: at 3x with no trigger the monthly design dies on 2001-09-26 and the quarterly on 1997-12-12; the weekly survives",
      term3 == {"weekly": None, "monthly": "2001-09-26", "quarterly": "1997-12-12"}, term3)
