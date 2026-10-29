"""Golden files: the published headline numbers are pinned (tests/golden/<study>.json).

Part 1 tests the machinery on small synthetic data. Part 2 compares each golden file with the current
results/<study>.json: every key that moved (beyond 1e-9 relative for floats, exactly for dates, counts and text)
fails as its own check and prints old and new. If a results file is absent, the study is skipped with one line.

A failure here is a lead, not a verdict: find out why the number moved. If the new number is intended, re-freeze with
   py scripts\\refreeze_golden.py --study <name> --reason "<why>"
"""
import importlib.util
import json
import tempfile
from pathlib import Path

import _golden as G
from _harness import ROOT, check, raises

# ---------------------------------------------------------------- 1. machinery

sample = {"meta": {"run_date": "2026-01-01"},
          "worlds": {"SPX": {"rows": [{"product": "A", "reset": "M", "horizon_years": 1, "gap": 0.01, "n": 5},
                                      {"product": "A", "reset": "W", "horizon_years": 1, "gap": 0.02, "n": 6}],
                             "twins": [{"x": 1.0}, {"x": 1.0}],
                             "dup": [{"product": "B", "gap": 1.5}, {"product": "B", "gap": 2.5}],
                             "levels": {"0.2": [{"date": "2000-01-03", "fall": -0.2}]}}}}
flat = G.flatten(sample)
check("flatten labels a row by its identifying fields", "worlds.SPX.rows[A/M/1].gap" in flat, list(flat)[:6])
check("flatten falls back to the position when a row has no identifying field", "worlds.SPX.twins[1].x" in flat)
check("flatten breaks a label tie with the position", "worlds.SPX.dup[B#0].gap" in flat and "worlds.SPX.dup[B#1].gap" in flat)
check("flatten keeps dotted keys and dated labels", flat.get("worlds.SPX.levels.0.2[2000-01-03].fall") == -0.2)
check("shape drops the row labels", G.shape("worlds.SPX.rows[A/M/1].gap") == "worlds.SPX.rows.gap")
sel = G.select(flat, "calendar_vs_daily")
check("select skips meta and keeps worlds", all(k.startswith("worlds") for k in sel) and len(sel) == len(flat) - 1, len(sel))
check("a reordered list gives the same labeled numbers",
      G.flatten({"worlds": {"SPX": {"rows": list(reversed(sample["worlds"]["SPX"]["rows"]))}}})["worlds.SPX.rows[A/M/1].gap"] == 0.01)

check("floats within 1e-9 relative are the same", G.same(1.0, 1.0 + 5e-10) and G.same(1e6, 1e6 * (1 + 5e-10)))
check("floats beyond 1e-9 relative differ", not G.same(1.0, 1.0 + 2e-9) and not G.same(0.5, 0.5001))
check("zero and tiny values compare on the absolute floor", G.same(0.0, 1e-13) and not G.same(0.0, 1e-9))
check("dates and text compare exactly", G.same("2000-01-03", "2000-01-03") and not G.same("2000-01-03", "2000-01-04"))
check("a count never equals a float, and bool is not int", not G.same(5, 5.0) and not G.same(1, True) and G.same(5, 5))
check("None equals only None", G.same(None, None) and not G.same(None, 0.0))
check("NaN equals NaN", G.same(float("nan"), float("nan")))

diff = G.differences({"a": 1.0, "b": "x", "c": 3, "d": 2.0}, {"a": 1.0, "b": "y", "c": 3})
check("differences lists changed and missing keys with old and new",
      sorted(d[0] for d in diff) == ["b", "d"] and dict((d[0], d[1:]) for d in diff)["b"] == ("x", "y")
      and dict((d[0], d[2]) for d in diff)["d"] is G.MISSING, diff)

with tempfile.TemporaryDirectory() as tmp:
    res, gold = Path(tmp) / "results", Path(tmp) / "golden"
    res.mkdir()
    raises("re-freeze refuses without a reason", lambda: G.refreeze("strategies", "  ", res, gold), "reason is required")
    raises("re-freeze refuses an unknown study", lambda: G.refreeze("nope", "why", res, gold), "unknown study")
    raises("re-freeze refuses when the results file is absent", lambda: G.refreeze("validate_live", "why", res, gold), "not found")
    (res / "validate_live.json").write_text(json.dumps({"A": {"slope": 1.99, "end": "2026-10-09", "table": [1, 2]}}), encoding="utf-8")
    n, ch = G.refreeze("validate_live", "first", res, gold, today="2026-10-24")
    rec = json.loads((gold / "validate_live.json").read_text(encoding="utf-8"))
    check("first freeze writes header, keys and an empty history",
          n == 2 and rec["frozen_on"] == "2026-10-24" and rec["reason"] == "first" and rec["refrozen"] == []
          and rec["n_keys"] == 2 and set(rec["keys"]) == {"A.slope", "A.end"} and len(rec["source_json_sha256"]) == 64, rec)
    check("the golden file uses LF line endings", b"\r" not in (gold / "validate_live.json").read_bytes())
    (res / "validate_live.json").write_text(json.dumps({"A": {"slope": 2.01, "new": 7}}), encoding="utf-8")
    n, ch = G.refreeze("validate_live", "slope refit", res, gold, today="2026-11-24")
    rec = json.loads((gold / "validate_live.json").read_text(encoding="utf-8"))
    check("re-freeze counts keys changed (one value moved, one key added, one removed)", ch == 3, ch)
    check("re-freeze appends {date, reason, keys_changed} and the split added / removed / moved to refrozen",
          rec["refrozen"] == [{"date": "2026-11-24", "reason": "slope refit", "keys_changed": 3, "added": 1, "removed": 1, "moved": 1}],
          rec["refrozen"])
    raises("re-freeze refuses when nothing changed (no no-op entry in the history)",
           lambda: G.refreeze("validate_live", "no change", res, gold, today="2026-12-01"), "nothing changed")
    rec = json.loads((gold / "validate_live.json").read_text(encoding="utf-8"))
    check("a refused re-freeze leaves the golden file and its history as they were",
          len(rec["refrozen"]) == 1 and rec["refrozen"][0]["keys_changed"] == 3 and rec["frozen_on"] == "2026-11-24", rec["refrozen"])
    # refreeze_all (R4 review): an unchanged study is skipped and the run goes on to the changed one after it
    (res / "coverage_sim.json").write_text(json.dumps({"summary": {"pooled_min": 0.94}}), encoding="utf-8")
    G.refreeze("coverage_sim", "first", res, gold, today="2026-10-24")
    (res / "coverage_sim.json").write_text(json.dumps({"summary": {"pooled_min": 0.95}}), encoding="utf-8")
    out_all = G.refreeze_all("coverage moved", res, gold, today="2026-12-02", studies=("validate_live", "coverage_sim"))
    rec_c = json.loads((gold / "coverage_sim.json").read_text(encoding="utf-8"))
    check("refreeze_all: the unchanged study (validate_live) is skipped and the changed one after it (coverage_sim) is re-frozen",
          [(s, st) for s, st, _n, _c in out_all] == [("validate_live", "unchanged"), ("coverage_sim", "refrozen")]
          and rec_c["refrozen"][-1]["moved"] == 1 and rec_c["keys"]["summary.pooled_min"] == 0.95, out_all)

    spec = importlib.util.spec_from_file_location("refreeze_golden", ROOT / "scripts" / "refreeze_golden.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    check("the command line refuses an empty reason (exit code 2)", cli.main(["--study", "strategies", "--reason", ""]) == 2)

# The guard catches a nudge: shift one real pinned number by 1e-6 relative and it must show up.
_g = G.load_golden("validate_live")
_cur = G.flatten(json.loads((G.RESULTS / "validate_live.json").read_text(encoding="utf-8"))) \
    if (G.RESULTS / "validate_live.json").exists() else None
if _cur is not None:
    _key = next((k for k, v in _g["keys"].items() if isinstance(v, float) and v != 0.0 and isinstance(_cur.get(k), float)), None)
    if _key is not None:                               # none if the results moved on from the frozen layout
        _moved = dict(_cur)
        _moved[_key] = _cur[_key] * (1 + 1e-6)
        _d = [d[0] for d in G.differences({_key: _cur[_key]}, _moved)]
        _same = [d[0] for d in G.differences({_key: _cur[_key]}, _cur)]
        check("a 1e-6 relative shift of one pinned number is detected; the unshifted number is not",
              _d == [_key] and _same == [], (_d[:3], _same[:3]))

# ---------------------------------------------------------------- 2. the real golden files

for study in G.STUDIES:
    gpath = G.GOLDEN / f"{study}.json"
    check(f"golden file for {study} exists", gpath.exists(), gpath.name)
    if not gpath.exists():
        continue
    gold = G.load_golden(study)
    check(f"{study}: golden header is complete",
          all(k in gold for k in ("study", "frozen_on", "reason", "source_json_sha256", "n_keys", "refrozen", "keys"))
          and gold["study"] == study and gold["reason"].strip() != "" and len(gold["source_json_sha256"]) == 64,
          list(gold)[:8])
    check(f"{study}: n_keys matches the keys held", gold["n_keys"] == len(gold["keys"]), (gold["n_keys"], len(gold["keys"])))
    # Entries before the R4 review carry {date, reason, keys_changed}; later ones add the split, which must sum to it.
    _base, _split = {"date", "reason", "keys_changed"}, {"added", "removed", "moved"}
    check(f"{study}: every re-freeze entry has date, reason and keys_changed (and, where present, added + removed + moved = keys_changed)",
          all(e["reason"].strip() and (set(e) == _base or (set(e) == _base | _split and e["added"] + e["removed"] + e["moved"] == e["keys_changed"]))
              for e in gold["refrozen"]), [sorted(e) for e in gold["refrozen"]][-1:])
    src = G.RESULTS / f"{study}.json"
    if not src.exists():
        print(f"skip {study}: results/{study}.json is absent, golden comparison not run")
        continue
    current = G.flatten(json.loads(src.read_text(encoding="utf-8")))
    diffs = G.differences(gold["keys"], current)
    LIMIT = 50                  # one failing check per difference up to here; the rest are counted in one check
    for path, old, new in diffs[:LIMIT]:
        shown = "absent from the results" if new is G.MISSING else repr(new)
        check(f"golden {study}: {path}", False, f"golden {old!r} -> now {shown}")
    if len(diffs) > LIMIT:
        check(f"golden {study}: {len(diffs) - LIMIT} further differences not listed", False,
              f"{sum(1 for d in diffs if d[2] is G.MISSING)} of all {len(diffs)} are absent from the results (layout "
              "change?); compare the golden file with the results, then re-freeze with a reason")
    check(f"golden {study}: all {len(gold['keys'])} pinned numbers match results/{study}.json", not diffs, f"{len(diffs)} differ")
    if G.sha256_file(src) != gold["source_json_sha256"] and not diffs:
        print(f"note {study}: results file differs from the frozen one in unpinned keys only (sha256 changed)")
