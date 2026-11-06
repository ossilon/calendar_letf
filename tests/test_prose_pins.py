"""Prose pins: the numbers printed in FINDINGS.md and ASSUMPTIONS.md equal the numbers in results/*.json.

Part 1 tests the checker on a small made-up document and results file (no files needed). Part 2 runs every pin in
tests/prose_pins.json against the real prose and the real results; a results file that is absent is skipped with one
line (the test needs no data, only the aggregates that ship with the repository). One check per pin: a failure prints
the file, the quoted sentence or table cell, the number the prose prints and the number the results hold.

A failure here is a lead, not a verdict: either the prose is stale (fix the prose) or the pin points at the wrong place
(fix tests/prose_pins.json). The format is never changed to match a number that is wrong. How a pin reads numbers is in
tests/_prose_pins.py.
"""
import json

import _prose_pins as P
from _harness import ROOT, check, raises

# ---------------------------------------------------------------- 1. the checker on made-up data
toks = lambda kind, s: [m.group(0) for m in P.TOKEN[kind].finditer(s)]                                   # noqa: E731
check("decimal tokens: a range 0.88-0.92 is two unsigned numbers; a date gives none; a lone minus sign stays",
      toks("decimal", "c = 0.88-0.92 on 2025-09-30, gap -0.06 to 0.23") == ["0.88", "0.92", "-0.06", "0.23"], toks("decimal", "c = 0.88-0.92 on 2025-09-30"))
check("decimal tokens: an arrow is not a sign; a dollar sign is not a letter; 12 and 1.5x are not decimals read as 1.5",
      toks("decimal", "1.00 -> 1.30% costs $3.66 or 1.5x or 12") == ["1.00", "1.30", "3.66"], toks("decimal", "1.00 -> 1.30% costs $3.66 or 1.5x or 12"))
check("signed tokens: only numbers with an explicit sign (a chain of pp changes between unsigned words)",
      toks("signed", "closes +0.38 pp, turns 1.5 -> 2.0 at 0.92% +0.57, total -1.61") == ["+0.38", "+0.57", "-1.61"])
check("int tokens: 12-73% is 12 and 73; 2.5 gives none", toks("int", "yield is 12-73% of 2.5") == ["12", "73"], toks("int", "yield is 12-73% of 2.5"))
check("mult tokens: 2.04x reads 2.04 and 1.5x reads 1.5; 12x (no decimal) and a bare 2.04 give none",
      toks("mult", "swaps 2.04x of NAV, 1.5x and 12x, or 2.04 alone") == ["2.04", "1.5"], toks("mult", "swaps 2.04x of NAV, 1.5x and 12x, or 2.04 alone"))
check("money tokens: $27,323 and $1,000,000 read with their separators; $500 (no separator) and 27,323 (no dollar sign) give none",
      toks("money", "$27,323 then $1,000,000 but $500 and 27,323") == ["27,323", "1,000,000"], toks("money", "$27,323 then $1,000,000 but $500 and 27,323"))
check("fmt: comma prints thousands separators (27323.4 at 0 decimals is 27,323; a signed negative keeps them)",
      P.fmt(27323.4, 1, 0, "minus", True) == "27,323" and P.fmt(-1234.5, 1, 1, "always", True) == "-1,234.5", P.fmt(27323.4, 1, 0, "minus", True))
check("squash: a hard-wrapped sentence reads as one line", P.squash("the invariant\n  is   the\tall-in") == "the invariant is the all-in")
check("fmt: scale, decimals and sign; always prints +; zero loses its minus sign",
      P.fmt(0.0066, 100, 2, "always") == "+0.66" and P.fmt(-0.0066, 100, 2, "always") == "-0.66" and P.fmt(0.879, 1, 3) == "0.879"
      and P.fmt(-0.00001, 100, 2, "always") == "+0.00" and P.fmt(-0.00001, 100, 2) == "0.00", P.fmt(-0.00001, 100, 2, "always"))

doc = """# Title
Intro. The cash yield c = 0.88-0.92 in window 1 and the gaps were
-0.43 / +0.66 (pp) before.
Unique start: the fee cap closes +0.38 pp, spread turns 1.5 -> 2.0 at 0.92% +0.57, total +0.95.
Twice twice 1.0
Twice twice 2.0
| row | SPYQ | MQQQ |
|---|---|---|
| gap at c = 0.8 | +0.40 / +0.95 | -0.74 / +0.57 |
| rate turns | 1.21 | 1.30 |
Final value $27,323 on 2.04x swaps over 2 rows.
"""
res = {"a": {"rows": [{"start": "2024-01-01", "end": "2024-06-30", "x": 0.0066}, {"start": "2024-07-01", "end": "2024-12-31", "x": -0.0043}],
             "c": {"0.3": 0.88, "0.4": 0.92}}, "pp": [0.0038, 0.0057], "dollars": 27323.4, "turns": 2.0412}
store = {"results/validate_live.json": res}
mk = lambda **kw: dict(dict(id="t", file="DOC.md", mode="after", items=[]), **kw)                            # noqa: E731
check("item_value: len counts the rows at a path (2); median picks the middle of three paths (0.88 of 0.0038, 0.88, 0.92)",
      P.item_value({"path": ["a", "rows"], "len": True}, res) == 2
      and P.item_value({"of": [["a", "c", "0.3"], ["a", "c", "0.4"], ["pp", 0]], "fn": "median"}, res) == 0.88)
money_pin = mk(anchor="Final value", kind="money", items=[{"path": ["dollars"], "decimals": 0, "comma": True}])
mult_pin = mk(anchor="Final value", kind="mult", items=[{"path": ["turns"], "decimals": 2}])
len_pin = mk(anchor="swaps over", kind="int", items=[{"path": ["a", "rows"], "len": True, "decimals": 0}])
check("pin: kind money reads $27,323 and compares with separators; kind mult reads 2.04x; a len item compares a count",
      P.evaluate(money_pin, doc, store)[0] and P.evaluate(mult_pin, doc, store)[0] and P.evaluate(len_pin, doc, store)[0],
      (P.evaluate(money_pin, doc, store), P.evaluate(mult_pin, doc, store), P.evaluate(len_pin, doc, store)))
check("pin: kind money fails on a stale dollar figure and quotes it",
      not P.evaluate(mk(anchor="Final value", kind="money", items=[{"path": ["pp", 0], "scale": 1e7, "decimals": 0, "comma": True}]), doc, store)[0])
good = mk(anchor="The cash yield c =", items=[{"of": [["a", "c", "0.3"], ["a", "c", "0.4"]], "fn": "min", "decimals": 2},
                                               {"of": [["a", "c", "0.3"], ["a", "c", "0.4"]], "fn": "max", "decimals": 2}])
check("pin: a range printed as min-max over several paths passes", P.evaluate(good, doc, store)[0], P.evaluate(good, doc, store))
check("pin: the anchor matches across a line break; a where-selected row and the sign mode work",
      P.evaluate(mk(anchor="and the gaps were", kind="signed",
                    items=[{"path": ["a", "rows", {"where": {"start": "2024-07-01", "end": "2024-12-31"}}, "x"], "scale": 100, "sign": "always"},
                           {"path": ["a", "rows", {"where": {"start": "2024-01-01", "end": "2024-06-30"}}, "x"], "scale": 100, "sign": "always"}]), doc, store)[0])
chain = mk(anchor="the fee cap closes", kind="signed", items=[{"path": ["pp", 0], "scale": 100, "sign": "always"},
                                                              {"path": ["pp", 1], "scale": 100, "sign": "always"}])
check("pin: a signed chain skips the unsigned 1.5, 2.0 and 0.92 between the two pp numbers", P.evaluate(chain, doc, store)[0], P.evaluate(chain, doc, store))
skipper = mk(anchor="the fee cap closes", items=[{"path": ["pp", 0], "scale": 100, "sign": "always"}, {"skip": 3},
                                                 {"of": [["pp", 1], ["a", "rows", 1, "x"]], "fn": "max", "abs": True, "scale": 100, "sign": "always"}])
check("pin: skip drops the next tokens (1.5, 2.0, 0.92); abs takes the larger size before the max (+0.57 beats -0.43)",
      P.evaluate(skipper, doc, store)[0], P.evaluate(skipper, doc, store))
res["g"] = {"spyq": [0.0040, 0.0095], "mqqq": [-0.0074, 0.0057], "rate_turns_mqqq": 1.2972}
gap = lambda col, key, **kw: mk(mode="cell", anchor="| gap at c = 0.8", cell={"col": col},                                  # noqa: E731
                                items=[{"path": ["g", key, i], "scale": 100, "sign": "always", **kw} for i in (0, 1)])
check("pin cell mode: column 2 reads +0.40 / +0.95 and column 3 reads -0.74 / +0.57 (two numbers each, in order)",
      P.evaluate(gap(2, "spyq"), doc, store)[0] and P.evaluate(gap(3, "mqqq"), doc, store)[0], (P.evaluate(gap(2, "spyq"), doc, store), P.evaluate(gap(3, "mqqq"), doc, store)))
wrong_col = P.evaluate(gap(3, "spyq"), doc, store)
check("pin cell mode: a value from the wrong column fails and the detail quotes the cell", not wrong_col[0] and "-0.74 / +0.57" in wrong_col[1], wrong_col)
off = mk(mode="cell", anchor="| gap at c = 0.8", cell={"col": 3, "row_offset": 1}, items=[{"path": ["g", "rate_turns_mqqq"], "decimals": 2}])
check("pin cell mode: row_offset 1 reads the row below the anchor row (rate turns 1.30)", P.evaluate(off, doc, store)[0], P.evaluate(off, doc, store))
check("pin cell mode: an anchor on two lines, or a column that is not there, fails",
      not P.evaluate(mk(mode="cell", anchor="Twice twice", cell={"col": 1}, items=[{"path": ["pp", 0]}]), doc, store)[0]
      and not P.evaluate(mk(mode="cell", anchor="| gap at c = 0.8", cell={"col": 9}, items=[{"path": ["pp", 0]}]), doc, store)[0])
bad =mk(anchor="The cash yield c =", items=[{"path": ["a", "c", "0.3"], "decimals": 2}, {"path": ["a", "c", "0.3"], "decimals": 2}])
ok, why = P.evaluate(bad, doc, store)
check("pin: a wrong value fails and the detail names the file, the quoted prose, the printed and the true number",
      not ok and "DOC.md" in why and "0.88-0.92" in why and "prose 0.92 but results hold 0.88" in why, why)
nudge = mk(anchor="The cash yield c =", items=[{"of": [["a", "c", "0.3"]], "fn": "min", "decimals": 2}, {"path": ["a", "c", "0.4"], "decimals": 3}])
check("pin: a format that prints a different number of decimals is a mismatch, not a rounding pass", not P.evaluate(nudge, doc, store)[0])
check("pin: an anchor that is not in the file fails", not P.evaluate(mk(anchor="no such text", items=[{"path": ["pp", 0]}]), doc, store)[0]
      and "occurs 0 times" in P.evaluate(mk(anchor="no such text", items=[{"path": ["pp", 0]}]), doc, store)[1])
check("pin: an anchor that occurs twice fails", "occurs 2 times" in P.evaluate(mk(anchor="Twice twice", items=[{"path": ["pp", 0]}]), doc, store)[1])
check("pin: too few numbers after the anchor fails with the count",
      "only 2 numbers follow" in P.evaluate(mk(anchor="| rate turns |", items=[{"path": ["pp", 0]}] * 3), doc, store)[1],
      P.evaluate(mk(anchor="| rate turns |", items=[{"path": ["pp", 0]}] * 3), doc, store)[1])
check("pin: a key path that does not exist fails with the path",
      not P.evaluate(mk(anchor="The cash yield c =", items=[{"path": ["a", "nope"]}]), doc, store)[0])
raises("resolve: a where-selector that matches two rows is refused", lambda: P.resolve({"r": [{"k": 1}, {"k": 1}]}, ["r", {"where": {"k": 1}}]), "exactly 1")

# ---------------------------------------------------------------- 2. the real pins
spec = P.load_pins(ROOT / "tests" / "prose_pins.json")
pins = spec["pins"]
ids = [p["id"] for p in pins]
PROSE_FILES = ("FINDINGS.md", "ASSUMPTIONS.md", "README.md", "THEORY.md")      # THEORY.md since B18 (docs/theory_examples.json)
check("prose pins: ids are unique and every pin has a file, an anchor, a mode and items",
      len(ids) == len(set(ids)) and all(p.get("file") in PROSE_FILES and p.get("anchor") and p.get("mode") in ("after", "cell")
                                        and p.get("items") for p in pins), [i for i in ids if ids.count(i) > 1][:3])
check("prose pins: the pin list covers all four prose files (FINDINGS, ASSUMPTIONS, README, THEORY)", {p["file"] for p in pins} == set(PROSE_FILES))
texts, results, skipped = {}, {}, set()
for p in pins:
    texts.setdefault(p["file"], (ROOT / p["file"]).read_text(encoding="utf-8"))
    name = p.get("json", "results/validate_live.json")
    if name not in results and name not in skipped:
        path = ROOT / name
        if path.exists():
            results[name] = json.loads(path.read_text(encoding="utf-8"))
        else:
            skipped.add(name)
            print(f"skip: {name} is absent, the prose pins that read it are not run")
n_run = 0
for p in pins:
    if p.get("json", "results/validate_live.json") in skipped:
        continue
    ok, why = P.evaluate(p, texts[p["file"]], results)
    n_run += 1
    check(f"prose pin {p['id']} ({p['file']})", ok, why)
print(f"prose pins run: {n_run} of {len(pins)}")
