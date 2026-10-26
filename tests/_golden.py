"""Golden-file helpers: flatten a results JSON into named numbers, pick the published ones, compare, re-freeze.

Plain-English summary
  * A "golden file" (tests/golden/<study>.json) pins the numbers that results/*.md and FINDINGS.md quote. If a code
    change moves one of them, tests/test_golden.py fails and prints old and new. A change is then either a bug or a
    deliberate new result; only a deliberate one is re-frozen, with a written reason (scripts/refreeze_golden.py).
  * `flatten` turns the nested results into {path: value}. A row in a list gets a readable label made from its
    identifying fields (product, reset, rule, horizon ...), so a path reads like
    `worlds.SPX.multi_start.fixed[SPYQ/M/10].gap_median` and a reordered list does not look like a change.
  * `SELECT` says which paths are headline numbers per study. The golden file stores the chosen paths and values, so
    the test needs no selection logic: it compares exactly what the file holds.

Not in this module: reading results (test_golden.py does) or writing them (the study scripts do).
"""
import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
GOLDEN = ROOT / "tests" / "golden"
STUDIES = ("calendar_vs_daily", "strategies", "from_bottoms", "validate_live", "coverage_sim")
REL_TOL = 1e-9
ABS_TOL = 1e-12

# Fields that name a row (a product, a rule, a horizon, a date). Their text joins into the row's label.
ID_FIELDS = ("underlying", "world", "product", "reset", "encoding", "mode", "rule", "key", "delay", "scope", "decade", "scenario",
             "series", "horizon_years", "months", "family", "bar", "id", "date", "listed", "name", "kind", "phi", "share", "era")

# Headline numbers per study: regular expressions that must match the WHOLE label-free path (list rows add no text).
# A path is kept if any `include` matches and no `exclude` matches (search anywhere).
_BOTTOM_SECTIONS = ("dollars_10k|dollars_10k_all_products|troughs|compare_with_list|unmatched_troughs|deepest_fall|"
                    "level_entries|leverage_cross_check|real_fund|model_3x|timing_stats|guppy_summary")
SELECT = {
    # reset gaps, win shares, decades, horizon curve, rolling 10y, early-reset events, margin benchmark, key periods,
    # sensitivity, full-history CAGR/drawdown, episode split, independent phases: everything under "worlds"
    "calendar_vs_daily": {"include": [r"worlds\..*"], "exclude": []},
    # full-history table (CAGR, drawdown, edge), common-start table, multi-start medians and win counts, sub-period
    # and delay edges, Guppy summary. Not selected: per-trade lists and every secondary ratio.
    "strategies": {
        "include": [r"full\.\w+\.\w+\.(start|years|cagr|max_dd|edge|passive_cagr|passive_max_dd|trades_per_year)",
                    r"common\.\w+\.\w+\.(start|cagr|max_dd|edge|passive_cagr|passive_max_dd)",
                    r"multi_start\.\w+\.\w+\.(n|wins|ties|edge_median|edge_mean|indep_mean|indep_lo|indep_hi|indep_df|noisy|too_few_windows)",
                    r"subperiod\.\w+\.\w+\.(split|edge_in_sample|edge_out_of_sample)",
                    r"eras\.\w+\.\w+\.(edge|strat_cagr|passive_cagr|years)",
                    r"era_tests\.\w+\.\w+\.(eras\.(mean_pp|n|se_pp\.\d+)|z_last_two\.\d+|z_pre_post\.\d+)",
                    r"delay\.\w+\.\w+\.(edge_d1|edge_d2|edge_d3)",
                    r"guppy\..*"],
        "exclude": []},
    # dollar tables, trough and entry dates and depths, listed-bottom comparison, real-fund span, timing statistics.
    # Not selected: the 200-odd per-entry result trees and the per-offset timing trees.
    "from_bottoms": {"include": [rf"worlds\.\w+\.({_BOTTOM_SECTIONS})(\..*)?"], "exclude": []},
    # live-fit slopes, intercepts, fitted spreads, 2025 returns, sensitivity gaps; not the per-period tables
    "validate_live": {"include": [r".*"], "exclude": [r"(^|\.)table(\.|$)", r"(^|\.)early_resets(\.|$)"]},
    # the coverage simulation: every published coverage, SE ratio, multiplier, autocorrelation, p-value and seed spread
    "coverage_sim": {"include": [r"(summary|iid|mechanism|regime|measured_persistence|matched|bb_seed_spread|bb_seed_spread_summary)(\..*)?"],
                     "exclude": []},
}
NEVER = ("meta",)          # run dates and captions: not numbers to pin (the first path segment)


# ---------------------------------------------------------------- flatten

def _label(item, index):
    """Readable label for one dict row of a list: its identifying fields, else its position."""
    parts = [str(item[f]) for f in ID_FIELDS if f in item and isinstance(item[f], (str, int)) and not isinstance(item[f], bool)]
    return "/".join(parts) if parts else str(index)


def flatten(obj, path="", out=None):
    """{path: leaf value} for every leaf (str, int, float, bool, None). Returns (paths in order) as a dict."""
    out = {} if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(v, f"{path}.{k}" if path else str(k), out)
    elif isinstance(obj, list):
        labels = [_label(v, i) if isinstance(v, dict) else str(i) for i, v in enumerate(obj)]
        seen = {}
        for lab in labels:
            seen[lab] = seen.get(lab, 0) + 1
        for i, (v, lab) in enumerate(zip(obj, labels)):
            if seen[lab] > 1:
                lab = f"{lab}#{i}"                    # two rows with the same label: the position breaks the tie
            flatten(v, f"{path}[{lab}]", out)
    else:
        out[path] = obj
    return out


def shape(path):
    """The path without row labels: `a.b[x/y].c` -> `a.b.c`."""
    return re.sub(r"\[[^\]]*\]", "", path)


def select(flat, study):
    """The headline subset of a flattened results file."""
    rules = SELECT[study]
    inc = [re.compile(p) for p in rules["include"]]
    exc = [re.compile(p) for p in rules["exclude"]]
    out = {}
    for path, value in flat.items():
        s = shape(path)
        if s.split(".")[0] in NEVER:
            continue
        if any(r.fullmatch(s) for r in inc) and not any(r.search(s) for r in exc):
            out[path] = value
    return out


# ---------------------------------------------------------------- compare

def same(old, new):
    """Equal as the golden rule says: floats to 1e-9 relative, everything else (dates, counts, text, None) exactly."""
    if isinstance(old, bool) or isinstance(new, bool) or old is None or new is None:
        return old is new or (old == new and type(old) is type(new))
    if isinstance(old, float) or isinstance(new, float):
        if not (isinstance(old, (int, float)) and isinstance(new, (int, float))):
            return False
        if isinstance(old, int) or isinstance(new, int):
            return False                               # a count that turned into a float (or the reverse) is a change
        if math.isnan(old) and math.isnan(new):
            return True
        return math.isclose(old, new, rel_tol=REL_TOL, abs_tol=ABS_TOL)
    return old == new and type(old) is type(new)


MISSING = object()


def differences(golden_keys, current_flat):
    """[(path, old, new)] for each golden key whose current value differs or is absent (new = MISSING)."""
    out = []
    for path, old in golden_keys.items():
        new = current_flat.get(path, MISSING)
        if new is MISSING or not same(old, new):
            out.append((path, old, new))
    return out


# ---------------------------------------------------------------- files

def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_golden(study, golden_dir=GOLDEN):
    return json.loads((Path(golden_dir) / f"{study}.json").read_text(encoding="utf-8"))


def write_golden(path, rec):
    """One key per line so a diff of two golden files reads line by line. LF line endings."""
    text = json.dumps(rec, indent=1, ensure_ascii=True, allow_nan=True) + "\n"
    Path(path).write_bytes(text.encode("ascii"))


def refreeze(study, reason, results_dir=RESULTS, golden_dir=GOLDEN, today=None):
    """Rewrite tests/golden/<study>.json from results/<study>.json. Returns (n_keys, keys_changed).

    Refuses an unknown study, an empty reason, a missing results file, and a re-freeze that would change nothing (so
    the `refrozen` history never carries a no-op entry). An existing file keeps its `refrozen` history and gains
    {date, reason, keys_changed}; keys_changed counts keys added, removed or different in value.
    """
    if study not in STUDIES:
        raise ValueError(f"unknown study {study!r}; choose one of {', '.join(STUDIES)}")
    if not reason or not reason.strip():
        raise ValueError("a reason is required to re-freeze a golden file (say what changed and why)")
    src = Path(results_dir) / f"{study}.json"
    if not src.exists():
        raise FileNotFoundError(f"{src.name} not found; run the study first")
    keys = select(flatten(json.loads(src.read_text(encoding="utf-8"))), study)
    if not keys:
        raise ValueError(f"{study}: the selection matched no keys; the results layout changed, update SELECT")
    today = today or date.today().isoformat()
    target = Path(golden_dir) / f"{study}.json"
    history, changed = [], len(keys)
    if target.exists():
        old = json.loads(target.read_text(encoding="utf-8"))
        history = list(old.get("refrozen", []))
        old_keys = old.get("keys", {})
        changed = sum(1 for k in set(old_keys) | set(keys)
                      if k not in old_keys or k not in keys or not same(old_keys[k], keys[k]))
        if changed == 0:
            raise ValueError(f"{study}: nothing changed against the current golden file; a re-freeze would only add a no-op history entry")
        history.append({"date": today, "reason": reason.strip(), "keys_changed": changed})
    rec = {"study": study, "frozen_on": today, "reason": reason.strip(), "source_json_sha256": sha256_file(src),
           "n_keys": len(keys), "refrozen": history, "keys": keys}
    Path(golden_dir).mkdir(parents=True, exist_ok=True)
    write_golden(target, rec)
    return len(keys), changed
