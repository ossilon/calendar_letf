"""THEORY.md (BACKLOG B18): the theory document stays true to the code, the tests and its own rules.

  * Vendor-neutral: THEORY.md names no fund sponsor and no fund ticker. It names designs ("2x SPY monthly") and the
    underlyings (SPY, QQQ, SOXX, the S&P 500, the Nasdaq-100, the PHLX semiconductor index) only.
  * Every code reference (`module.function`, `module.Class.attribute`, a file path) resolves to something real.
  * Every numbered equation (\\tag{n}) has a row in the formula -> code -> test map; the row's function resolves; its
    test file exists and holds the named check. A check that exists is run by the suite, so a failing one fails here too.
  * Every number in the text comes from docs/theory_examples.json (prose pins in tests/prose_pins.json); this file checks
    that the JSON is fresh: written by the code now in the tree, and equal to a new run of docs/theory_examples.compute().
  * The references each carry a status (PRIMARY, ABSTRACT, SECONDARY or NOT READ) and the date read; the README links
    the document; the figures it shows exist.
"""
import csv
import importlib
import importlib.util
import json
import math
import re

from _harness import ROOT, check
from calendar_letf import provenance

THEORY = ROOT / "THEORY.md"
EXAMPLES_PY = ROOT / "docs" / "theory_examples.py"
EXAMPLES_JSON = ROOT / "docs" / "theory_examples.json"

# ---------------------------------------------------------------- 1. names THEORY.md must not carry
SPONSORS = ("Tradr", "AXS", "Direxion", "Rydex", "Guggenheim", "ProFunds", "ProShares", "Roundhill", "GraniteShares",
            "iShares", "BlackRock", "Invesco", "SPDR", "State Street", "SSGA", "WeeklyPay")
FUND_TICKERS = ("SPYQ", "MQQQ", "QQQP", "SPYM", "SPYB", "QQQW", "SOXM", "SOXW", "NVDW", "TSLW", "TLTQ", "MSPY", "DQQQ",
                "UPRO", "TQQQ", "SSO", "QLD", "SOXL", "SOXS", "USD", "SQQQ", "SPXU", "SDS", "QID", "DKNW", "TOPW",
                "DXSLX", "DXQLX", "RMQHX", "ULPIX", "UOPIX", "RYVYX", "RYNVX")
UNDERLYINGS = {"SPY", "QQQ", "SOXX"}                        # the index ETFs the designs track: allowed


def reference_tickers(root=ROOT):
    """Every fund ticker the reference tables carry (column 'ticker'), so a fund added later is banned without a list edit."""
    out = set()
    for path in (root / "reference").rglob("*.csv"):
        with open(path, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            if r.fieldnames and "ticker" in r.fieldnames:
                out |= {row["ticker"].strip() for row in r if row["ticker"].strip()}
    return out


def banned_hits(text, names):
    """[(name, line number)] for each banned name that occurs as a whole word."""
    hits = []
    for name in names:
        for m in re.finditer(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text):
            hits.append((name, text.count("\n", 0, m.start()) + 1))
    return hits


BANNED = sorted((set(FUND_TICKERS) | reference_tickers()) - UNDERLYINGS) + list(SPONSORS)
check("banned list: the reference tables add their tickers, the underlyings stay allowed",
      {"SPYQ", "SOXM", "DXSLX"} <= set(BANNED) and not UNDERLYINGS & set(BANNED), sorted(set(BANNED))[:8])
check("banned names, planted: 'MQQQ' and 'Tradr' are caught; 'QQQ', 'SPY' and 'USDA' are not",
      [h[0] for h in banned_hits("2x QQQ monthly (MQQQ) by Tradr; SPY; USDA", BANNED)] == ["MQQQ", "Tradr"])

if not THEORY.exists():
    check("THEORY.md exists", False, "missing")
else:
    text = THEORY.read_text(encoding="utf-8")
    hits = banned_hits(text, BANNED)
    check("THEORY.md names no fund sponsor and no fund ticker (vendor-neutral)", not hits, hits[:10])

    # ------------------------------------------------------------ 2. code references resolve
    MODULES = ("kernel", "periods", "nyse", "costs", "products", "series", "loader", "study", "stats", "coverage",
               "leverage", "montecarlo", "options", "validate", "navtr", "backtest", "metrics", "bottoms", "provenance")
    REF = re.compile(r"`(?:calendar_letf\.)?(" + "|".join(MODULES) + r")\.([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)(?:\(\))?`")

    def resolves(module, attr):
        try:
            obj = importlib.import_module(f"calendar_letf.{module}")
            for part in attr.split("."):
                obj = getattr(obj, part)
            return True
        except (ImportError, AttributeError):
            return False

    refs = sorted(set(REF.findall(text)))
    bad = [f"{m}.{a}" for m, a in refs if not resolves(m, a)]
    check("THEORY.md: it references the package's code (at least 30 module.name references)", len(refs) >= 30, len(refs))
    check("THEORY.md: every `module.name` reference resolves to a real object in the package", not bad, bad)
    check("code references, planted: a made-up name does not resolve", not resolves("kernel", "no_such_function")
          and resolves("kernel", "periodic_reset_nav"))
    paths = sorted(set(re.findall(r"`((?:scripts|tests|docs|reference|calendar_letf|results)/[A-Za-z0-9_/-]+"
                                  r"\.(?:py|json|csv|md|png))`", text)))
    missing = [p for p in paths if "*" not in p and not (ROOT / p).exists()]
    check("THEORY.md: every file path it names exists", paths and not missing, missing)

    # ------------------------------------------------------------ 3. the formula -> code -> test map
    tags = re.findall(r"\\tag\{(\d+)\}", text)
    check("THEORY.md: the equations are numbered 1, 2, 3, ... in order, each once",
          tags and [int(t) for t in tags] == list(range(1, len(tags) + 1)), tags)
    MAP_ROW = re.compile(r"^\|\s*\((\d+)\)\s*\|[^|]*\|\s*`([^`]+)`\s*\|\s*`(tests/[A-Za-z0-9_]+\.py)`\s*\|\s*\"([^\"]+)\"\s*\|", re.M)
    rows = {}
    for n, func, tfile, label in MAP_ROW.findall(text):
        rows.setdefault(int(n), []).append((func, tfile, label))
    unmapped = [int(t) for t in tags if int(t) not in rows]
    check("map: every numbered equation has a row (equation, function, test file, check label)", not unmapped, unmapped)
    stray = sorted(n for n in rows if str(n) not in tags)
    check("map: every row names an equation that exists", not stray, stray)

    def func_ok(ref):
        if ref.startswith("docs/theory_examples."):
            spec = importlib.util.spec_from_file_location("theory_examples_ref", EXAMPLES_PY)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return hasattr(mod, ref.split(".", 1)[1].split(".")[-1].split("/")[-1])
        m = re.fullmatch(r"(?:calendar_letf\.)?(\w+)\.([\w.]+)", ref)
        return bool(m) and resolves(m.group(1), m.group(2))

    bad_rows = []
    for n, entries in sorted(rows.items()):
        for func, tfile, label in entries:
            tpath = ROOT / tfile
            if not func_ok(func):
                bad_rows.append((n, func, "function does not resolve"))
            elif not tpath.exists():
                bad_rows.append((n, tfile, "test file missing"))
            elif label not in tpath.read_text(encoding="utf-8"):
                bad_rows.append((n, label[:50], f"label not in {tfile}"))
    check("map: every row's function resolves, its test file exists and holds the named check", not bad_rows, bad_rows[:6])

    # ------------------------------------------------------------ 4. README, references, figures
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    check("README links THEORY.md", "](THEORY.md)" in readme)
    refs_part = text[text.find("## 16."):] if "## 16." in text else ""
    entries = []                                   # one entry = a "- " line plus its indented continuation lines
    for ln in refs_part.splitlines():
        if ln.startswith("- "):
            entries.append(ln)
        elif ln.startswith("  ") and entries:
            entries[-1] += " " + ln.strip()
    status = re.compile(r"\b(PRIMARY|ABSTRACT|SECONDARY|NOT READ)\b")
    undated = [e[:60] for e in entries if not status.search(e) or not (re.search(r"\d{4}-\d{2}-\d{2}", e) or "NOT READ" in e)]
    check("references: each entry carries PRIMARY / ABSTRACT / SECONDARY / NOT READ and the date read", entries and not undated,
          undated[:5])
    figs = re.findall(r"\]\((results/[A-Za-z0-9_]+\.png)\)", text)
    check("THEORY.md: the figures it shows exist under results/", figs and all((ROOT / f).exists() for f in figs), figs)

# ---------------------------------------------------------------- 5. the worked examples are fresh
doc = json.loads(EXAMPLES_JSON.read_text(encoding="utf-8")) if EXAMPLES_JSON.exists() else None
check("docs/theory_examples.json exists (run py docs\\theory_examples.py)", doc is not None)
if doc is not None:
    want = provenance.code_fingerprint(EXAMPLES_PY)
    check("docs/theory_examples.json was written by the code now in the tree (package + docs/theory_examples.py); "
          "else re-run py docs\\theory_examples.py", doc["meta"]["code"]["sha256"] == want["sha256"],
          f"file {doc['meta']['code']['sha256'][:12]} vs tree {want['sha256'][:12]}")
    spec = importlib.util.spec_from_file_location("theory_examples", EXAMPLES_PY)
    tex = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tex)
    fresh = json.loads(json.dumps(provenance.json_safe(tex.compute()), allow_nan=False))

    def diff(a, b, path=""):
        if isinstance(a, dict) and isinstance(b, dict):
            if set(a) != set(b):
                return [f"{path}: keys {sorted(set(a) ^ set(b))[:4]}"]
            return [d for k in a for d in diff(a[k], b[k], f"{path}.{k}")]
        if isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                return [f"{path}: length {len(a)} vs {len(b)}"]
            return [d for i, (x, y) in enumerate(zip(a, b)) for d in diff(x, y, f"{path}[{i}]")]
        if isinstance(a, float) and isinstance(b, float):
            return [] if math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-15) else [f"{path}: {a!r} vs {b!r}"]
        return [] if a == b else [f"{path}: {a!r} vs {b!r}"]

    d = diff(doc["examples"], fresh)
    check("docs/theory_examples.json equals a new run of docs/theory_examples.compute() (1e-12 relative)", not d, d[:5])
    ex = fresh
    check("examples: two days of +10% at 2x give 1.42 calendar and 1.44 daily; the reversal (+10%, -10%) gives 0.98 and 0.96",
          [round(ex["two_day"][k][s], 12) for k in ("trend", "reversal") for s in ("calendar", "daily")] == [1.42, 1.44, 0.98, 0.96])
    check("examples: the kernels' 21-day gap equals Bessembinder's exact sum (1e-12); the second order is within 5%",
          abs(ex["gap_orders"]["kernel_gap"] - ex["gap_orders"]["exact_sum"]) < 1e-12 and ex["gap_orders"]["rel_error_second"] < 0.05
          and abs(ex["gap_orders"]["ss_form"] - ex["gap_orders"]["second_order"]) < 1e-15)
    check("examples: the effective leverage read off the kernel equals L (1 + R) / (1 + L R) (1e-6)",
          all(abs(r["kernel"] - r["closed"]) < 1e-6 for r in ex["effective_leverage"]["rows"]))
    check("examples: a daily fund's rebalancing trade equals L (L - 1) r x NAV",
          all(abs(r["trade"] - r["closed"]) < 1e-9 for r in ex["rebalance"]["rows"]))
    check("examples: on the alternating path the daily 2x fund's log loss equals L (L - 1) / 2 x sum r^2 within 1%",
          abs(-ex["drag"]["path"]["fund_log"] / ex["drag"]["path"]["sum_r2"] - 1.0) < 0.01)
    check("examples: Kelly sample form equals the kernel's grid optimum within one grid step (0.01)",
          abs(ex["kelly"]["sample"]["kelly_closed"] - ex["kelly"]["sample"]["grid_best"]) <= 0.01 + 1e-12)
    check("examples: the kernel's break-even fee and the second-order form agree within 0.01 points",
          abs(ex["break_even"]["sample"]["kernel"] - ex["break_even"]["sample"]["second_order"]) < 1e-4)
    check("examples: put-call parity with the dividend yield holds to 1e-10", abs(ex["option"]["parity_gap"]) < 1e-10)
    check("examples: at a reset the balance sheet has exposure L and holdings 1; with d = 0 and full-rate cash it pays "
          "L - 1 rate turns and L spread turns",
          all(abs(r["exposure"] - r["L"]) < 1e-12 and abs(r["holdings"] - 1.0) < 1e-12 for r in ex["structure"]["at_reset"])
          and all(abs(r["rate_turns"] - (r["L"] - 1.0)) < 1e-12 and abs(r["spread_turns"] - r["L"]) < 1e-12
                  for r in ex["structure"]["at_reset"] if r["d"] == 0.0))
    check("examples: on a 63-day +30% trend at 3x the raw-sum log formula beats the demeaned one, and the gap between "
          "them is the dropped term L (L - 1) / 2 x T x mean(r)^2",
          abs(ex["log_formula"]["raw_error"]) < abs(ex["log_formula"]["demeaned_error"])
          and abs((ex["log_formula"]["demeaned_error"] - ex["log_formula"]["raw_error"]) - ex["log_formula"]["dropped_term"]) < 1e-12)
    check("examples: for iid returns the terms k >= 3 add 1.92% to the second-order expected gap; (1 + L)(T - 2) mu / 3 "
          "approximates it within 0.05 points",
          abs(ex["crossover"]["higher_order_iid"]["share"] - ex["crossover"]["higher_order_iid"]["approx"]) < 5e-4)
    # ---- direct checks of single equations (strengthened after the re-grade of 2026-11-06) ----
    check("eq. 4: the calendar kernel ends a fund whose index falls just past 1/L in one period, at 1.2x, 1.5x, 2x and 3x",
          all(r_["kernel_terminates_past_it"] for r_ in ex["wipeout"]["rows"]))
    rt = ex["log_formula"]["order_ratios"]
    check("eq. 10 is second order: halving every daily return cuts its error by 6.5 to 9.5 times, twice (a cubic error: 8)",
          all(6.5 < x_ < 9.5 for x_ in rt), rt)
    gr = ex["kelly"]["sample"]["growth"]
    check("eq. 17 in sample form: the second-order log growth matches the daily kernel's log wealth over 20 planted years "
          "within 0.002 at L = 1, 2 and 3", all(abs(g_["kernel"] - g_["second_order"]) < 2e-3 for g_ in gr), gr)
    kc = ex["kelly"]["cases"]["s0"]
    ls_ = kc["L_star"]
    sig2 = ex["kelly"]["sigma"] ** 2
    check("eq. 19: g(L*) - g(L) = sigma^2 / 2 (L - L*)^2 on the growth values of the example, at L = 1, 1.5, 2 and 3 (1e-12)",
          all(abs((kc["growth"][f"{ls_:.4f}".rstrip("0").rstrip(".")] - kc["growth"][k_]) - sig2 / 2 * (float(k_) - ls_) ** 2) < 1e-12
              for k_ in ("1", "1.5", "2", "3")))
    check("eq. 24: the call's leverage from the formula equals a central difference of the price in S (1e-8)",
          abs(ex["option"]["leverage"] - ex["option"]["leverage_fd"]) < 1e-8)
    pt = ex["price_trigger"]
    check("eq. 30: with the total return 1% above the price, the level fill keeps 1 + L((1 - delta)(1.01) - 1) = 0.313, not "
          "0.30, and the kernel's close equals the hand value (1e-12)",
          pt["early_reset"] and abs(pt["v_hit"] - 0.313) < 1e-12 and abs(pt["kernel_close"] - pt["hand_close"]) < 1e-12, pt)
    mi = ex["median_interval"]["rows"]
    check("eq. 41: the median interval's exact binomial coverage is at least 0.95 at 400 and 5,000 draws, with the ranks of "
          "the normal approximation rounded outward",
          all(m_["coverage"] >= 0.95 and m_["rank_lo"] == math.floor(m_["N"] / 2 - 1.959963984540054 * math.sqrt(m_["N"]) / 2)
              and m_["rank_hi"] == math.ceil(m_["N"] / 2 + 1.959963984540054 * math.sqrt(m_["N"]) / 2) for m_ in mi), mi)

# ---------------------------------------------------------------- 6. the kernel equations 29, 31, 32, written out again
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from calendar_letf import kernel, periods  # noqa: E402

_rng = np.random.default_rng(29)
_r = _rng.normal(0.0003, 0.015, 252)
_u = np.r_[1.0, np.cumprod(1 + _r)]
_d = pd.bdate_range("2020-01-02", periods=253)
_af, _ae = periods.accrual_fraction(_d, 360), periods.accrual_fraction(_d, 365)
_rate = np.r_[0.0, np.full(252, 0.045)]
_fee = np.full(253, 0.0095)
_v0, _C, _F, _cal = 1.0, 0.0, 0.0, [1.0]
for _t in range(1, 253):                                   # equation 29: one period, financing as simple interest on V_0
    _C += ((2.0 - 1) * _rate[_t] + 0.02) * _af[_t]
    _F += _fee[_t] * _cal[-1] * _ae[_t]
    _cal.append(_v0 * (2.0 * _u[_t] / _u[0] - 1.0) - _v0 * _C - _F)
_k29 = kernel.periodic_reset_nav(_u, _u, _u, _rate, _af, _ae, np.zeros(253, bool), 2.0, 0.02, _fee, 0.0, 0)[0]
check("eq. 29: the calendar kernel equals the recursion written out again (one period, rate, spread and fee) to 1e-13",
      float(np.max(np.abs(_k29 - np.array(_cal)))) < 1e-13)
_day = [1.0]
for _t in range(1, 253):                                   # equation 31
    _day.append(_day[-1] * (1 + 2.0 * _r[_t - 1] - ((2.0 - 1) * _rate[_t] + 0.02) * _af[_t] - _fee[_t] * _ae[_t]))
_k31 = kernel.daily_reset_nav(_u, _rate, _af, _ae, 2.0, 0.02, _fee)[0]
check("eq. 31: the daily kernel equals the recursion written out again (rate, spread and fee) to 1e-12 relative",
      float(np.max(np.abs(_k31 / np.array(_day) - 1))) < 1e-12)
_D, _mg = 1.0, [1.0]
for _t in range(1, 253):                                   # equation 32
    _D = _D * (1 + _rate[_t] * _af[_t]) + 0.02 * _af[_t] + _fee[_t] * _mg[-1] * _ae[_t]
    _mg.append(2.0 * _u[_t] / _u[0] - _D)
_k32 = kernel.margin_position_nav(_u, _rate, _af, _ae, 2.0, 0.02, _fee)[0]
check("eq. 32: the margin kernel equals the recursion written out again (compounding loan, borrowed spread and fee) to 1e-12",
      float(np.max(np.abs(_k32 - np.array(_mg)))) < 1e-12)
if doc is not None:                                       # two example checks that belong with section 5
    check("examples: over ten years at 5% the never-reset simple-interest NAV exceeds the margin equity by exactly the "
          "interest on interest prod(1 + i a) - 1 - sum(i a) (1e-12)",
          abs(ex["margin"]["gap"] - ex["margin"]["interest_on_interest"]) < 1e-12)
    check("examples: the AR(1) variance ratio from stats.variance_ratio is within 3 standard errors of the closed form",
          abs(ex["variance_ratio"]["vr"] - ex["variance_ratio"]["closed"])
          < 3 * math.sqrt(2 * (2 * 21 - 1) * (21 - 1) / (3 * 21 * ex["variance_ratio"]["n"])))
