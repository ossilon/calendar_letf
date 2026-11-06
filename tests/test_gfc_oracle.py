"""Tests for scripts/run_gfc_oracle.py (the GFC oracle entry): planted answers for its date rules, its dollar
arithmetic and its sensitivity helpers; checks that every claim F21 prints holds in the published
results/gfc_oracle.json; the entry leverage against results/from_bottoms.json (another script, same dates); and a
second route that reads the raw files with the csv module and rebuilds the index and the 3x models with plain loops,
not the package loaders or kernel. The second route runs on the files the published run read (their sha256 is in the
results manifest) and skips, naming the file and the reason, on any other data (a fresh clone, a later top-up).
The script is imported as a module; its main() does not run.
"""
import bisect
import csv
import hashlib
import importlib.util
import json
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd

from _harness import ROOT, check, raises
from calendar_letf import loader, products, provenance, series

spec = importlib.util.spec_from_file_location("run_gfc_oracle", ROOT / "scripts" / "run_gfc_oracle.py")
go = importlib.util.module_from_spec(spec)
spec.loader.exec_module(go)

# ---- oracle_low: the lowest close inside the window; a lower close outside it does not count; a tie keeps the first ----
ix = pd.bdate_range("2006-12-01", "2010-03-31")
px = pd.Series(100.0, index=ix)
px.loc["2006-12-15"] = 10.0                      # lower, but before the window
px.loc["2010-02-01"] = 5.0                       # lower, but after the window
px.loc["2008-11-20"] = 40.0
px.loc["2009-03-09"] = 40.0                      # the same low again: the first day wins
check("oracle_low: the lowest close inside GFC_FROM..GFC_TO, not a lower one outside it, and the first day of a tie",
      ix[go.oracle_low(px)] == pd.Timestamp("2008-11-20"), ix[go.oracle_low(px)])
check("oracle_low: the window bounds are inclusive (a low on GFC_TO itself is found)",
      ix[go.oracle_low(px.where(px.index != pd.Timestamp("2009-12-31"), 1.0))] == pd.Timestamp("2009-12-31"))
raises("oracle_low: an empty window raises", lambda: go.oracle_low(px, "2011-01-01", "2011-12-31"), "no rows")

# ---- fall_from_window_high: the low against the highest close since GFC_FROM (not an older high before it) ----
fx = pd.Series([200.0, 120.0, 150.0, 90.0], index=pd.to_datetime(["2006-06-01", "2007-02-01", "2007-10-09", "2009-03-09"]))
check("fall_from_window_high: 90 against the window high 150 is -40% (the 2006 high of 200 is outside the window)",
      abs(go.fall_from_window_high(fx, 3) - (-0.4)) < 1e-15, go.fall_from_window_high(fx, 3))

# ---- common_end and exact_row ----
a = pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-09"])
b = pd.to_datetime(["2026-10-01", "2026-10-02"])
check("common_end: the earliest last date of the series", go.common_end(a, b) == pd.Timestamp("2026-10-02"))
raises("common_end: raises when that date is not a row of every series",
       lambda: go.common_end(a, pd.to_datetime(["2026-10-01", "2026-10-03"])), "not a row of every series")
check("exact_row: finds a present date", go.exact_row(a, "2026-10-05") == 2)
raises("exact_row: an absent date raises (no nearest-date fill)", lambda: go.exact_row(a, "2026-10-06"), "is not a row of the series")

# ---- numbers: $10,000 x the level ratio; CAGR and drawdown from bottoms.window_numbers ----
dates = pd.to_datetime(["2000-01-03", "2001-01-03", "2002-01-03"])
lvl = np.array([2.0, 1.0, 4.0])
n = go.numbers(lvl, dates, 0, 2)
yrs = (dates[2] - dates[0]).days / 365.25
check("numbers: dollars = 10,000 x level[e] / level[s] (2 -> 4 is $20,000)", abs(n["dollars"] - 20_000.0) < 1e-9, n)
check("numbers: CAGR over calendar days / 365.25 and the -50% fall on the way", abs(n["cagr"] - (2.0 ** (1 / yrs) - 1)) < 1e-12
      and abs(n["max_dd"] - (-0.5)) < 1e-12, n)

# ---- drawdown_ranges on a planted results dict: the index row is left out, 3x model rows are separate ----
R = dict(worlds=dict(X=dict(rows=[dict(series="A", kind="MODELED calendar", max_dd=-0.61), dict(series="B", kind="REAL 2x fund (price only)", max_dd=-0.59),
                                  dict(series="M", kind="MODEL 3x daily (filed terms)", max_dd=-0.77), dict(series=go.INDEX_ROW, kind="1x", max_dd=-0.34)]),
                     Y=dict(rows=[dict(series="M", kind="MODEL 3x daily (filed terms)", max_dd=-0.82), dict(series="C", kind="MODELED calendar", max_dd=-0.64)])))
check("drawdown_ranges: 2x rows -0.64..-0.59, 3x rows -0.82..-0.77, the index row excluded",
      go.drawdown_ranges(R) == ((-0.64, -0.59), (-0.82, -0.77)), go.drawdown_ranges(R))

raises("numbers: a terminated series (level 0 at the entry) raises, no silent NaN",
       lambda: go.numbers(np.array([0.0, 1.0]), dates[:2], 0, 1), "not positive")

# ---- early_resets: strictly after the entry close, on or before the end ----
nav = pd.Series([1.0, 1.0, 1.0])
nav.attrs["early_resets"] = ["2020-01-02", "2020-01-05"]
check("early_resets: a reset ON the entry day and one after the end are both left out",
      go.early_resets(nav, pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-04")) == [])
check("early_resets: a reset after the entry and on the end day is counted",
      go.early_resets(nav, pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-05")) == ["2020-01-02", "2020-01-05"])

# ---- shift_rows on a planted world: fund doubles each row, twin flat, so the lead from row k to the end is 2^(e-k) ----
class FakeWorld:
    dates = pd.bdate_range("2020-01-01", periods=5)
    specs = [SimpleNamespace(name="A", reset="monthly")]

    def nav(self, name, enc):
        return pd.Series([1.0, 2.0, 4.0, 8.0, 16.0] if name == "A" else [1.0] * 5, index=self.dates)

    def twin_name(self, name):
        return "TWIN_" + name


sr = [r for r in go.shift_rows(FakeWorld(), 2, 4, shifts=(-1, 0, 1)) if r["encoding"] == "fixed"]
check("shift_rows: entries one row early, on the row and one row late give leads 8, 4 and 2 (closed form 2^(e-k))",
      [(r["shift"], r["lead"]) for r in sr] == [(-1, 8.0), (0, 4.0), (1, 2.0)], sr)
check("shift_rows: each row carries the entry date of its shift", [r["date"] for r in sr] == [str(d.date()) for d in FakeWorld.dates[1:4]])
raises("shift_rows: a shift before row 0 raises (a negative row would wrap to the end)", lambda: go.shift_rows(FakeWorld(), 2, 4, shifts=(-3,)), "leave the rows")
raises("shift_rows: a shift onto the end row raises (no hold left)", lambda: go.shift_rows(FakeWorld(), 2, 4, shifts=(2,)), "leave the rows")

# ---- shift_summary on planted grid rows: range, lowest and highest lead with their shifts, the shifts below 1 ----
grid = [dict(series="A", encoding="fixed", shift=k, date="", lead=v) for k, v in ((-2, 0.9), (-1, 0.95), (0, 1.3), (1, 1.1))]
grid += [dict(series="A", encoding="rate", shift=k, date="", lead=v) for k, v in ((-2, 1.2), (-1, 1.0), (0, 1.4), (1, 1.1))]
ss = {r["encoding"]: r for r in go.shift_summary(grid)}
check("ranges_text: shifts print as runs ('-5 to -3, +7'), a single shift alone, and an empty list as 'none'",
      go.ranges_text([-3, -5, -4, 7]) == "-5 to -3, +7" and go.ranges_text([2]) == "+2" and go.ranges_text([]) == "none")
check("shift_summary: fixed: range -2..+1 over 4 shifts, lowest 0.9 at -2, highest 1.3 at 0, below 1 at -2 and -1",
      (ss["fixed"]["shift_first"], ss["fixed"]["shift_last"], ss["fixed"]["n_shifts"], ss["fixed"]["lead_min"], ss["fixed"]["lead_min_shift"],
       ss["fixed"]["lead_max"], ss["fixed"]["lead_max_shift"], ss["fixed"]["below_one"]) == (-2, 1, 4, 0.9, -2, 1.3, 0, [-2, -1]), ss["fixed"])
check("shift_summary: rate: a lead of exactly 1.0 is not below 1 (the break case of the strict test)", ss["rate"]["below_one"] == [], ss["rate"])
check("shift_summary: publishes no per-session lead or date (a daily series must stay unpublished)",
      all("lead" not in r and "date" not in r for r in ss.values()))

# ---- shift_losers and twin_vs_real_range on planted results ----
Rp = dict(worlds=dict(X=dict(shift=[dict(series="A", encoding="fixed", below_one=[-3]), dict(series="A", encoding="rate", below_one=[5]),
                                    dict(series="B", encoding="fixed", below_one=[])],
                             rows=[dict(kind="MODELED 2x daily twin (same costs)", vs_real_2x=0.7), dict(kind="MODELED calendar", vs_real_2x=1.4),
                                   dict(kind="MODELED 2x daily twin (same costs)", vs_real_2x=0.9)])))
check("shift_losers: fixed-encoding shifts below 1 only (the rate row and product B, with none, are left out)",
      go.shift_losers(Rp) == [("X", "A", [-3])], go.shift_losers(Rp))
check("twin_vs_real_range: min and max over the twin rows only (the calendar row's 1.4 is left out)",
      go.twin_vs_real_range(Rp) == (0.7, 0.9), go.twin_vs_real_range(Rp))

# ---- the published results file ----
path = ROOT / "results" / "gfc_oracle.json"
res = json.loads(path.read_text(encoding="utf-8"))
for name, W in res["worlds"].items():
    real_dollars = next(r for r in W["rows"] if r["kind"].startswith("REAL 2x"))["dollars"]
    check(f"gfc_oracle.json {name}: each modeled row's vs_real_2x is its dollars / the real 2x fund's dollars",
          all(abs(r["vs_real_2x"] - r["dollars"] / real_dollars) < 1e-12 for r in W["rows"] if "vs_real_2x" in r))
    calendar = [r for r in W["rows"] if r["kind"] == "MODELED calendar"]
    check(f"gfc_oracle.json {name}: 3 calendar products x 2 cost encodings, each with its twin, plus the 3x model, the real 2x fund and the index",
          len(calendar) == 6 and len(W["rows"]) == 15, len(W["rows"]))
    check(f"gfc_oracle.json {name}: a calendar fund bought at the low holds at least 2x (a fall inside its period only raises it)",
          all(r["leverage"] >= 2.0 - 1e-9 for r in calendar), [r["leverage"] for r in calendar])
    check(f"gfc_oracle.json {name}: the entry is inside the GFC window and the end is after the real 3x fund's launch",
          go.GFC_FROM <= W["entry"]["date"] <= go.GFC_TO and W["launch"]["date"] < W["end"])
    # F21's claims, read from the results (a change that breaks one fails here, not only in the prose)
    for en in go.ENCODINGS:
        cal = {r["series"]: r for r in calendar if r["encoding"] == en}
        twins = {r["series"]: r for r in W["rows"] if r["kind"].startswith("MODELED 2x") and r["encoding"] == en}
        check(f"F21 claim {name}/{en}: every calendar design ends above its daily twin at the headline entry",
              all(c["dollars"] > twins["TWIN_" + s]["dollars"] for s, c in cal.items()))
        check(f"F21 claim {name}/{en}: every daily twin ends below the real 2x fund", all(t["vs_real_2x"] < 1 for t in twins.values()),
              {s: round(t["vs_real_2x"], 3) for s, t in twins.items()})
        summ = {r["series"]: r for r in W["shift"] if r["encoding"] == en}
        _grid = (min(go.ENTRY_SHIFTS), max(go.ENTRY_SHIFTS), len(go.ENTRY_SHIFTS))
        check(f"F21 claim {name}/{en}: the entry-shift grid held every session of ENTRY_SHIFTS {_grid} for each design",
              set(summ) == set(cal) and all((r["shift_first"], r["shift_last"], r["n_shifts"]) == _grid for r in summ.values())
              and _grid[2] == _grid[1] - _grid[0] + 1)
        for s_, ks_ in {s: summ[s]["below_one"] for s in cal}.items():
            if cal[s_]["reset"] == "quarterly":
                check(f"F21 claim {name}/{en}: {s_} (quarterly) trails its twin only in one unbroken run of shifts that ends before the low "
                      "(F21 states each run, with 'at least' where it reaches the grid's edge; checked below)",
                      not ks_ or (ks_ == list(range(min(ks_), max(ks_) + 1)) and max(ks_) < 0), (min(ks_, default=None), max(ks_, default=None)))
            else:
                check(f"F21 claim {name}/{en}: {s_} ({cal[s_]['reset']}) never ends below its twin at any entry shift", not ks_, ks_)
    by = {(r["series"], r["encoding"]): r for r in W["rows"]}
    mono = "HYP_SPX_M" if name == "SPX" else "MQQQ"
    check(f"F21 claim {name}: under the rate encoding the monthly design ends above the real 2x fund",
          by[(mono, "rate")]["vs_real_2x"] > 1, by[(mono, "rate")]["vs_real_2x"])
check("F21 claim: under the fixed encoding the S&P monthly design ends below SSO",
      next(r for r in res["worlds"]["SPX"]["rows"] if r["series"] == "HYP_SPX_M" and r["encoding"] == "fixed")["vs_real_2x"] < 1)

# ---- the entry leverage against results/from_bottoms.json: another script reads it at the same dates ----
fb = json.loads((ROOT / "results" / "from_bottoms.json").read_text(encoding="utf-8"))
for name, W in res["worlds"].items():
    for r in [r for r in W["rows"] if r["kind"] == "MODELED calendar" and r["encoding"] == "fixed"]:
        hit = [x for x in fb["worlds"][name]["dollars_10k_all_products"][r["series"]]["rows"] if x["date"] == W["entry"]["date"]]
        check(f"leverage {name}/{r['series']}: equals from_bottoms.json at {W['entry']['date']} (fixed encoding)",
              len(hit) == 1 and abs(hit[0]["leverage"] - r["leverage"]) < 1e-9, (r["leverage"], [x["leverage"] for x in hit]))

# ---- what FINDINGS F21 prints that the prose pins cannot read (dates, session counts) ----
f21 = (ROOT / "FINDINGS.md").read_text(encoding="utf-8")
f21 = f21[f21.index("**F21."):f21.index("Could not test (B13):")]
spx, ndx = res["worlds"]["SPX"], res["worlds"]["NDX"]
qqqp = next(r for r in ndx["rows"] if r["series"] == "QQQP" and r["encoding"] == "fixed")
quarter_runs = []                       # "QQQP from at least 400 up to 2": each quarterly design's losing run, as F21 prints it
for W_ in (ndx, spx):
    resets_ = {r["series"]: r["reset"] for r in W_["rows"] if r["kind"] == "MODELED calendar"}
    for r in W_["shift"]:
        if r["encoding"] == "fixed" and r["below_one"] and resets_[r["series"]] == "quarterly":
            ks_ = r["below_one"]
            quarter_runs.append(f"{r['series']} from {'at least ' if min(ks_) == min(go.ENTRY_SHIFTS) else ''}{-min(ks_)} up to {-max(ks_)}")
for text in (f"{spx['entry']['date']} on the S&P 500", f"{ndx['entry']['date']} on the Nasdaq-100",
             f"S&P 500 (to {spx['end']})", f"Nasdaq-100 (to {ndx['end']})",
             f"its 35% early reset fired on the next session, {qqqp['first_early_reset']}",
             *quarter_runs,
             f"The monthly and weekly designs end above their twins at every entry shift from {min(go.ENTRY_SHIFTS)} to "
             f"+{max(go.ENTRY_SHIFTS)} sessions"):
    check(f"FINDINGS F21 prints the published value: {text!r}", " ".join(text.split()) in " ".join(f21.split()))


# ---- a second route: the raw files read with the csv module and plain loops, not the package loaders or kernel ----
# The route runs only on the files the published run read (sha256 in its manifest). Other files (a later top-up, your
# own export) skip with the reason: the published numbers cannot be expected to match them until the study is re-run.
PUBLISHED = {f["file"]: f["sha256"] for f in res["meta"]["inputs"]["files"]}


def _published_file(path):
    """None if `path` is the file the published run read, else the reason it is not."""
    if not path.exists():
        return f"{path.name} is absent"
    if provenance.sha256_of(path) != PUBLISHED.get(path.name):          # line endings folded, as the manifest does
        return f"{path.name} differs from the file the published run read (sha256); re-run py scripts\\run_gfc_oracle.py on your data"
    return None


def raw(symbol):
    """({date: {"close", "low"}}, None) from a price file, or (None, reason)."""
    p = loader.data_path() / (symbol.replace(":", "_") + "_daily.csv")
    why = _published_file(p)
    if why:
        return None, why
    with open(p, newline="", encoding="utf-8") as f:
        rd = csv.reader(f)
        head = next(rd)
        if head[0] != "date":
            return None, f"{p.name} is not in the library layout (date, open, high, low, close)"
        kc, kl = head.index("close"), head.index("low")
        return {row[0]: dict(close=float(row[kc]), low=float(row[kl])) for row in rd}, None


def raw_rate(name):
    """([dates], [decimal rates]) from a FRED file (date, value in percent; '.' and blanks skipped), or (None, reason)."""
    p = loader.rates_path() / f"{name}.csv"
    why = _published_file(p)
    if why:
        return None, why
    out_d, out_v = [], []
    with open(p, newline="", encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            try:
                v = float(row[1])
            except ValueError:
                continue
            out_d.append(row[0][:10])
            out_v.append(v / 100.0)
    return (out_d, out_v), None


def need(*items):
    """Load each ("price", symbol) or ("rate", name); None (with a printed skip naming every reason) if any is unusable."""
    got = [raw(x) if kind == "price" else raw_rate(x) for kind, x in items]
    why = [r for _, r in got if r]
    if why:
        print(f"skip: the second route for {', '.join(x for _, x in items)} is not run: {'; '.join(why)}")
        return None
    return [d for d, _ in got]


def spliced_levels(price, published, first, last, splice=None, pre_yield=0.0):
    """The package's total-return rule, written again: up to `splice` the price move plus `pre_yield` a year accrued by
    calendar days / 365; from `splice` on, the published series scaled to meet it; a day the published file lacks is
    carried by the price move, and the next published day re-syncs. Returns (dates, {date: level}) on the price calendar."""
    ds = sorted(d for d in price if first <= d <= last)
    lvl = {ds[0]: 1.0}
    scale = None if splice and splice > ds[0] else 1.0 / published[ds[0]]["close"]
    for a, b in zip(ds, ds[1:]):
        if scale is None:
            days = (date.fromisoformat(b) - date.fromisoformat(a)).days
            lvl[b] = lvl[a] * price[b]["close"] / price[a]["close"] * (1.0 + pre_yield * days / 365.0)
            if b == splice:
                scale = lvl[b] / published[b]["close"]
        else:
            lvl[b] = published[b]["close"] * scale if b in published else lvl[a] * price[b]["close"] / price[a]["close"]
    return ds, lvl


def daily_route(ds, lvl, rate, L, spread_per_nav, fee):
    """The daily-reset NAV over dates ds, written again as a plain loop of the kernel's documented rule: each step pays
    L x the level move, financing ((L - 1) x rate + spread_per_nav) x days / 360 at the rate dated on or before the
    previous close, and fee x days / 365. Returns the end NAV per 1 at ds[0]."""
    rd, rv = rate
    nav = 1.0
    for a, b in zip(ds, ds[1:]):
        days = (date.fromisoformat(b) - date.fromisoformat(a)).days
        r = rv[bisect.bisect_right(rd, a) - 1]
        nav *= 1.0 + L * (lvl[b] / lvl[a] - 1.0) - ((L - 1.0) * r + spread_per_nav) * days / 360.0 - fee * days / 365.0
    return nav


def close_to(got, want, label):
    check(label, abs(got - want) <= 1e-9 * abs(want), (got, want))


checks = dict(SPX=("SP:SPX", "AMEX:SSO", "AMEX:UPRO", "SP:SPXTR"), NDX=("NASDAQ:NDX", "AMEX:QLD", "NASDAQ:TQQQ", "NASDAQ:XNDX"))
for name, (idx_sym, real_sym, real3_sym, tr_sym) in checks.items():
    W = res["worlds"][name]
    files = need(("price", idx_sym), ("price", real_sym), ("price", real3_sym), ("price", tr_sym), ("rate", "DFF"))
    if files is None:
        continue
    idx, real, real3, tr, dff = files
    inside = {d: v["close"] for d, v in idx.items() if go.GFC_FROM <= d <= go.GFC_TO}
    low = min(inside, key=lambda d: (inside[d], d))
    check(f"second route {name}: the lowest {idx_sym} close in the window, read from the raw file, is the published entry date",
          low == W["entry"]["date"], (low, W["entry"]["date"]))
    # v0.1.1: the study also stops at its fixed v0.1.0 end (study.V010_END), whatever the files hold after it
    _fixed = go.study.V010_END[name]
    check(f"second route {name}: the end is the earliest of the three raw files' last dates and the fixed end {_fixed}",
          min(max(idx), max(real), max(real3), _fixed) == W["end"], (max(idx), max(real), max(real3), _fixed, W["end"]))
    row = {r["series"]: r for r in W["rows"] if r["encoding"] in ("price", "filed", "tr")}
    lrow = {r["series"]: r for r in W["launch"]["rows"]}
    close_to(row[real_sym.split(":")[1]]["dollars"], 10_000 * real[W["end"]]["close"] / real[W["entry"]["date"]]["close"],
             f"second route {name}: {real_sym} $10,000 from the raw file's closes equals the published row")
    first = min(real3)
    check(f"second route {name}: {real3_sym}'s first raw close ({first}) is the published launch date", first == W["launch"]["date"])
    close_to(lrow[real3_sym.split(":")[1]]["dollars"], 10_000 * real3[W["end"]]["close"] / real3[first]["close"],
             f"second route {name}: {real3_sym} from its first raw close equals the published launch row")
    # the 1x total-return index and the 3x model, from the entry and from the launch, rebuilt from the raw files
    m3 = products.MODELS_3X[products.MODEL_3X_FOR[name]]
    splice = series.XNDX_TRUST_FROM if name == "NDX" else None
    if splice:
        check("second route NDX: the entry falls in the measured-yield block (XNDX_LEVEL_FROM to the splice)",
              series.XNDX_LEVEL_FROM <= W["entry"]["date"] < splice)
    for start, rows_, what in ((W["entry"]["date"], row, "entry"), (W["launch"]["date"], lrow, "launch")):
        ds, lvl = spliced_levels(idx, tr, start, W["end"], splice=splice, pre_yield=series.MID_YIELD if splice else 0.0)
        close_to(rows_[go.INDEX_ROW]["dollars"], 10_000 * lvl[W["end"]],
                 f"second route {name}: the 1x total-return index from the {what}, rebuilt from {idx_sym} + {tr_sym}, equals the published row")
        nav = daily_route(ds, lvl, dff, m3.L, m3.costs.spread * m3.costs.turns, m3.costs.fee)
        close_to(rows_[m3.name]["dollars"], 10_000 * nav,
                 f"second route {name}: {m3.name} from the {what}, a plain loop on the rebuilt index and raw DFF, equals the published row")

# ---- a second route to QQQP's early-reset day: the first QQQ daily low at least 35% below the quarter-end close ----
q = need(("price", "NASDAQ:QQQ"))
if q is not None:
    q = q[0]
    entry = ndx["entry"]["date"]
    qstart = f"{entry[:4]}-{(int(entry[5:7]) - 1) // 3 * 3 + 1:02d}-01"            # first day of the entry's quarter
    base_day = max(d for d in q if d < qstart)                                     # the last reset: the prior quarter's last close
    drop = products.PRODUCTS["QQQP"].early_drop
    hit = next(d for d in sorted(q) if d > base_day and q[d]["low"] / q[base_day]["close"] - 1.0 <= -drop)
    check(f"second route: QQQ's first daily low {drop:.0%} below its {base_day} close is the published QQQP early reset",
          hit == qqqp["first_early_reset"], (hit, qqqp["first_early_reset"]))
    check("second route: that day is the session after the entry in the raw QQQ file (F21: 'the next session')",
          min(d for d in q if d > entry) == qqqp["first_early_reset"], (min(d for d in q if d > entry), qqqp["first_early_reset"]))
