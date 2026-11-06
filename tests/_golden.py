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
import os
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
GOLDEN = ROOT / "tests" / "golden"
STUDIES = ("calendar_vs_daily", "strategies", "from_bottoms", "validate_live", "coverage_sim", "gfc_oracle", "live_monthly", "sub2x",
           "montecarlo", "three_x", "semis", "reset_day", "compounding", "leap")
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
    # the GFC oracle entry: entry and end dates, every row's dollars, return, CAGR, drawdown and entry leverage
    "gfc_oracle": {"include": [r"worlds\..*"], "exclude": []},
    # B19, the real monthly-reset mutual funds: the hard test, every fit (cost, interval, coverage), every real-vs-real
    # row, the erratum, and each fund's counts. Not selected: the per-period and per-anchor check rows and the payout logs
    "live_monthly": {"include": [r"hard_test\..*", r"fits\..*", r"real_vs_real\..*", r"errata\..*",
                                 r"funds\.\w+\.(splits|ex_dates|payouts|undatable_payouts|unplaced_payouts_\w+|stale_closes_\w+|"
                                 r"window_start|periods_gated|periods_passed|anchors_gated|anchors_passed)(\..*)?"],
                     "exclude": []},
    # B17, sub-2x leverage: the index row, every optimum (best L, plateau, intervals), the named points, the 1.2x weekly
    # design, every break-even fee, out of sample, walk-forward, C10 / C13 / C14 and the wipeouts. Not selected: the
    # 4,920 curve rows (the chart's points; every published number above is read from them and pinned here) and the
    # coverage simulation details beyond the two coverages and the verdict.
    "sub2x": {"include": [r"worlds\.\w+\.(years|index|optimum|named|weeklypay|break_even|out_of_sample|walk_forward|c10|c13|c14|wipeouts_base|wipe_first_L)(\..*)?"],
              "exclude": [r"\.coverage\.(k|runs|phi|mc_se)$", r"\.rule$"]},
    # B11, the Monte Carlo paths: every bootstrap row, C5, the best-L distributions, the mechanism and its fit, every stress
    # case, the real decade's rank and the path calendar. Not selected: the fan chart's percentile arrays and the real
    # decade's monthly levels (chart data), the sample-path list and the run times.
    "montecarlo": {"include": [r"worlds\.\w+\.(calendar|history|bootstrap|c5|lstar|mechanism|mechanism_fit|stress_flat|stress_rate_shock|"
                               r"stress_1929)(\..*)?", r"worlds\.\w+\.real_decade\.\w*share\w*"],
                   "exclude": []},
    # B1, 3x calendar resets: every design row, the multi-start gaps, the fills, the costs, C13, the key periods, the real-fund
    # overlay, the simulated decades and the trigger checks. Not selected: the run time.
    "three_x": {"include": [r"worlds\.\w+\.(cost_cases|cost_effect|designs|multi_start|fills|cost_sensitivity|c13|key_periods|overlay|montecarlo|"
                            r"fixed35_never_fires|intraday_wipe_extra|history_none_equals_fixed35)(\..*)?"],
                "exclude": []},
    # B16, semiconductors: every named row, the multi-start gaps, the 0.05 curve and its plateaus, the break-even fees, C13,
    # the costs, the key periods, the SOXL overlay, the simulated decades, the validation status and the index basis.
    "semis": {"include": [r"world\.(index|named|multi_start|curve|plateau|break_even|c13|cost_sensitivity|key_periods|overlay|montecarlo|"
                          r"validation|soxx_index_basis)(\..*)?"],
              "exclude": []},
    # B12 + B10: every anchor's history row, the simulated anchors, entry on every trading day, the seam check, the summary.
    "reset_day": {"include": [r"worlds\.\w+\.(history|simulated|every_day|seam_alignment)(\..*)?", r"summary(\..*)?"], "exclude": []},
    # B14: every window row (ratio, gap, enhancement shares, formula fit, trend split), the planted paths, the worked example.
    "compounding": {"include": [r"worlds\.\w+\.windows(\..*)?", r"planted(\..*)?", r"worked_example(\..*)?", r"summary(\..*)?"], "exclude": []},
    # B15: the index, every LEAP and fund row, every episode.
    "leap": {"include": [r"index(\..*)?", r"rows(\..*)?", r"episodes(\..*)?"], "exclude": []},
}
NEVER = ("meta",)         # run dates and captions: not numbers to pin (the first path segment)


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
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()     # CR LF folded, as git checks out LF


def load_golden(study, golden_dir=GOLDEN):
    return json.loads((Path(golden_dir) / f"{study}.json").read_text(encoding="utf-8"))


def write_golden(path, rec):
    """One key per line so a diff of two golden files reads line by line. LF line endings."""
    text = json.dumps(rec, indent=1, ensure_ascii=True, allow_nan=True) + "\n"
    Path(path).write_bytes(text.encode("ascii"))


STRICT_ENV = "CALENDAR_LETF_GOLDEN_STRICT"     # set to 1: compare even when the inputs differ (the author's release check)


def input_fingerprints(doc):
    """{"<kind>/<file>": sha256} of every input a results file names in its manifest (price and rate files, reference
    tables). {} for a study with no manifest (a simulation that reads no data)."""
    inp = (doc.get("meta") or {}).get("inputs") or (doc.get("provenance") or {}).get("inputs") or {}
    out = {}
    for kind in ("files", "reference_files", "reference_json"):
        for rec in inp.get(kind, []) or []:
            out[f"{kind}/{rec['file']}"] = rec.get("sha256")
    return out


def inputs_differ(gold, doc):
    """Sorted names of the inputs whose fingerprint differs between the frozen run and this results file (added and
    removed ones too). An older golden file without an `inputs` record gives []: it is compared as before."""
    frozen = gold.get("inputs")
    if frozen is None:
        return []
    now = input_fingerprints(doc)
    return sorted(k.split("/", 1)[1] for k in set(frozen) | set(now) if frozen.get(k) != now.get(k))


def compare(gold, doc, strict=None):
    """("skip", message) when the results come from other inputs than the frozen run and strict mode is off;
    otherwise ("compare", differences). A stranger who re-runs a study on their own data gets the skip and its reason;
    the published results, read from the published inputs, stay pinned."""
    strict = os.environ.get(STRICT_ENV) == "1" if strict is None else strict
    diffs = differences(gold["keys"], flatten(doc))
    moved = inputs_differ(gold, doc)
    if moved and not strict:
        shown = ", ".join(moved[:4]) + (f" and {len(moved) - 4} more" if len(moved) > 4 else "")
        return "skip", (f"inputs differ from the frozen run ({shown}), so {len(diffs)} of {len(gold['keys'])} pinned "
                        f"numbers differ; the golden file pins the published inputs. Re-run the study on the published "
                        f"inputs to compare, or set {STRICT_ENV}=1")
    return "compare", diffs


class NothingChanged(ValueError):
    """A re-freeze that would change nothing (refused, so the history never carries a no-op entry)."""


def refreeze(study, reason, results_dir=RESULTS, golden_dir=GOLDEN, today=None):
    """Rewrite tests/golden/<study>.json from results/<study>.json. Returns (n_keys, keys_changed).

    Refuses an unknown study, an empty reason, a missing results file, and a re-freeze that would change nothing (so
    the `refrozen` history never carries a no-op entry; NothingChanged). An existing file keeps its `refrozen`
    history and gains {date, reason, keys_changed, added, removed, moved}: keys_changed = added + removed + moved, so a
    reason such as "no existing value moved" can be checked against `moved`.
    """
    if study not in STUDIES:
        raise ValueError(f"unknown study {study!r}; choose one of {', '.join(STUDIES)}")
    if not reason or not reason.strip():
        raise ValueError("a reason is required to re-freeze a golden file (say what changed and why)")
    src = Path(results_dir) / f"{study}.json"
    if not src.exists():
        raise FileNotFoundError(f"{src.name} not found; run the study first")
    doc = json.loads(src.read_text(encoding="utf-8"))
    keys = select(flatten(doc), study)
    inputs = input_fingerprints(doc)
    if not keys:
        raise ValueError(f"{study}: the selection matched no keys; the results layout changed, update SELECT")
    today = today or date.today().isoformat()
    target = Path(golden_dir) / f"{study}.json"
    history, changed = [], len(keys)
    if target.exists():
        old = json.loads(target.read_text(encoding="utf-8"))
        history = list(old.get("refrozen", []))
        old_keys = old.get("keys", {})
        added = sum(1 for k in keys if k not in old_keys)
        removed = sum(1 for k in old_keys if k not in keys)
        moved = sum(1 for k in keys if k in old_keys and not same(old_keys[k], keys[k]))
        changed = added + removed + moved
        n_inputs = len(inputs_differ(old, doc)) if "inputs" in old else len(inputs)
        if changed == 0 and n_inputs == 0:
            raise NothingChanged(f"{study}: nothing changed against the current golden file; a re-freeze would only add a no-op history entry")
        entry = {"date": today, "reason": reason.strip(), "keys_changed": changed, "added": added, "removed": removed, "moved": moved}
        if n_inputs:
            entry["inputs_changed"] = n_inputs     # B20: the inputs moved (a new manifest), whether or not a number did
        history.append(entry)
    rec = {"study": study, "frozen_on": today, "reason": reason.strip(), "source_json_sha256": sha256_file(src),
           "n_keys": len(keys), "inputs": inputs, "refrozen": history, "keys": keys}
    Path(golden_dir).mkdir(parents=True, exist_ok=True)
    write_golden(target, rec)
    return len(keys), changed


def refreeze_all(reason, results_dir=RESULTS, golden_dir=GOLDEN, today=None, studies=STUDIES):
    """Re-freeze every study that changed and skip the ones that did not (R4 review: the old loop stopped at the first
    unchanged study, after rewriting the ones before it). Returns [(study, "refrozen" | "unchanged", n_keys, changed)].
    Any other refusal (a missing results file, an empty selection) still raises, before nothing or after the earlier
    studies, with the study named."""
    out = []
    for study in studies:
        try:
            n, changed = refreeze(study, reason, results_dir, golden_dir, today)
            out.append((study, "refrozen", n, changed))
        except NothingChanged:
            out.append((study, "unchanged", None, 0))
    return out
