"""Publish guard: scripts/scan_identifiers.py must catch leaks, data files and pasted daily series.

Part 1 feeds the scan synthetic files (planted leaks must be caught, clean files must pass). Part 2 scans the real
repository: the categories that must be zero today are enforced; names of AI tools, British spellings and private
terms are reported as notes until the release pass cleans the prose (flip RELEASE_GATE to True then).
"""
import importlib.util
import tempfile
from collections import Counter
from pathlib import Path

from _harness import ROOT, check

RELEASE_GATE = True        # flipped in the R4 release pass (2026-10-26): every tier is now enforced

spec = importlib.util.spec_from_file_location("scan_identifiers", ROOT / "scripts" / "scan_identifiers.py")
scan_ids = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan_ids)

# 1. The real .gitignore keeps data, raw outputs and private notes out, and publishes the documents and aggregates.
pats = scan_ids.ignore_patterns()
for rel in ("data/SP_SPX_daily.csv", "data/rates/DFF.csv", "results/raw/run.csv", "PROMPT.md", "DESIGN.md", "BACKLOG.md",
            "identifiers_local.txt", "tests/crosscheck_local.py", "reference/clean_guppy_v1.pine",
            "calendar_letf/__pycache__/x.pyc", "calendar_letf.egg-info/PKG-INFO"):
    check(f".gitignore keeps {rel} private", scan_ids.ignored(rel, pats))
for rel in ("data/README.md", "README.md", "results/strategies.json", "results/strategies.md", "tests/golden/strategies.json",
            "scripts/scan_identifiers.py", "reference/nport_tradr_2026.json"):
    check(f".gitignore publishes {rel}", not scan_ids.ignored(rel, pats))

# 1b. The matcher follows git's rules: a slash anchors a pattern, '*' never crosses a folder, an ignored folder stays so.
rules = ["data/*", "!data/README.md", "forward/daily/", "tests/*_local.py", "*.egg-info/", "keep/", "!keep/x.md"]
for rel, want in (("data/README.md", False), ("data/raw/x.csv", True), ("a/forward/daily/x.csv", False),
                  ("forward/daily/x.md", True), ("tests/sub/x_local.py", False), ("tests/x_local.py", True),
                  ("pkg.egg-info/PKG-INFO", True), ("sub/pkg.egg-info/PKG-INFO", True), ("keep/x.md", True)):
    check(f"git rule: {rel} is {'ignored' if want else 'published'}", scan_ids.ignored(rel, rules) == want)

# 2. The daily-series detector: 5 or more dated numeric rows in a row, a few days apart, is a series.
daily = "\n".join(f"| 2026-10-{d:02d} | 26.{d:02d} | 778.{d:02d} |" for d in range(1, 13))
check("12 consecutive dated numeric rows make a run of 12", scan_ids.longest_dated_run(daily) == 12)
events = "\n".join(f"| {y}-03-09 | 0.{y % 90:02d} | 1.{y % 70:02d} |" for y in (1974, 1982, 1990, 2003, 2009, 2020))
check("event dates years apart are not a series", scan_ids.longest_dated_run(events) == 1, scan_ids.longest_dated_run(events))
four = "\n".join(daily.splitlines()[:4])
five = "\n".join(daily.splitlines()[:5])
check("4 consecutive rows pass, 5 are caught", scan_ids.longest_dated_run(four) <= scan_ids.MAX_DATED_RUN
      < scan_ids.longest_dated_run(five))
prose = "Review on 2027-04-14.\n2026-10-13: one note with 1.5 and 2.5 in it\n| 2026-10-13 | only 1.0 |"
check("dates in prose or rows with one number do not count", scan_ids.longest_dated_run(prose) == 0)
weekly = "\n".join(f"| {d} | 1.5 | 2.5 |" for d in ("2020-01-03", "2020-01-10", "2020-01-17", "2020-01-24", "2020-01-31", "2020-02-07"))
check("weekly rows 7 days apart are not flagged as a daily run", scan_ids.longest_dated_run(weekly) == 1)

import json  # noqa: E402

js_series = json.dumps({"x": [{"date": f"2026-10-{d:02d}", "close": 100 + d / 10} for d in range(1, 12)]})
js_events = json.dumps({"x": [{"date": d, "fall": -0.3} for d in ("1974-10-03", "1982-08-12", "1987-12-04", "1990-10-11", "2002-10-09", "2009-03-09")]})
check("a JSON list of 11 consecutive dated rows is a series", scan_ids.json_series_run(js_series) == 11, scan_ids.json_series_run(js_series))
check("a JSON list of event dates is not", scan_ids.json_series_run(js_events) == 1)
check("a JSON list of bare consecutive ISO date strings is a series",
      scan_ids.json_series_run(json.dumps([f"2026-10-{d:02d}" for d in range(1, 9)])) == 8)

# 3. Planted leaks in synthetic files. The leak texts are assembled from pieces so this file passes its own scan.
home = "C:" + "\\" + "Users" + "\\" + "someone" + "\\" + "x.csv"
home_json = "C:" + "\\\\" + "Users" + "\\\\" + "someone" + "\\\\" + "x.csv"
mail = "someone" + "@" + "example.org"
keyline = "api" + "_key" + " = " + chr(34) + "abcd1234efgh5678" + chr(34)
sk = "sk" + "-" + "A" * 24
gh = "gh" + "p_" + "B" * 36
model = "Cl" + "aude"
vendor = "Anthr" + "opic"
gpt = "GP" + "T-5"
british = ["behavio" + "ur", "colo" + "ur", "mode" + "lled", "analy" + "sed", "organi" + "se", "optimi" + "sed", "real" + "ised",
           "annuali" + "sation", "summari" + "ses"]
american = ["behavior", "color", "modeled", "analyzed", "analyses", "organize", "center",
            "optimistic", "realistic", "organism", "analysis", "emphasis"]      # -is- words that are not -ise verbs pass

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    def one(rel, text):
        p = tmp / rel.replace("/", "_")
        p.write_text(text, encoding="utf-8")
        return [(rel, p)]

    def hits(rel, text, personal=()):
        return scan_ids.scan(one(rel, text), personal=personal)

    check("a clean file passes", hits("notes.md", "Run the tests. The result is 0 failure(s).\n") == [])
    check("a Windows home path is caught", any("home directory path" in p for p in hits("notes.md", f"see {home}\n")))
    check("a JSON-escaped Windows home path is caught", any("home directory path" in p for p in hits("a.md", f'"{home_json}"\n')))
    check("a Unix home path is caught", any("home directory path" in p for p in hits("a.md", "/ho" + "me/someone/x\n")))
    check("an e-mail address is caught", any("email address" in p for p in hits("a.md", f"write to {mail}\n")))
    check("a key assignment is caught", any("possible secret" in p for p in hits("a.py", keyline + "\n")))
    check("an sk- style key is caught", any("API key pattern" in p for p in hits("a.py", f"k = '{sk}'\n")))
    check("a GitHub token is caught", any("API key pattern" in p for p in hits("a.py", f"t = '{gh}'\n")))
    for name in (model, vendor, gpt, "Op" + "us", "Son" + "net", "Hai" + "ku", "Fab" + "le"):
        check(f"AI model or vendor name '{name}' is caught", any("AI model or vendor name" in p for p in hits("a.md", f"Audited by {name} 5.\n")))
    check("lower-case plain words are not model names", hits("a.md", "a magnum opus, a fable and a haiku\n") == [])
    for w in british:
        check(f"British spelling '{w}' is caught", any("British spelling" in p for p in hits("a.md", f"the {w} here\n")))
    for w in american:
        check(f"American spelling '{w}' passes", hits("a.md", f"the {w} here\n") == [], w)

    p = hits("scripts/scan_identifiers.py", f"{model} {british[0]}\n")
    check("the scanner script and the guard tests are exempt for the names and spellings they list", p == [], p)
    p = hits("scripts/scan_identifiers.py", f"see {home}\n")
    check("the exemption does not cover a home path", any("home directory path" in x for x in p), p)

    fake = [scan_ids.re.compile("zzterm", scan_ids.re.IGNORECASE)]
    p = hits("notes.md", "line one\nmentions ZZTerm here\n", personal=fake)
    check("a private term is caught in contents, with file and line", p == ["notes.md:2: personal term /zzterm/"], p)
    check("a private term is caught in a file name", any("file name" in x for x in hits("zzterm_notes.md", "clean\n", personal=fake)))

    # data files, images, series
    check("a CSV outside the allowed folders is refused", any("data file" in x for x in hits("notes/prices.csv", "date,close\n2026-10-13,778.01\n")))
    check("a JSON file outside the allowed folders is refused", any("data file" in x for x in hits("notes/x.json", "{}")))
    check("an image outside results/ is refused", any("image file" in x for x in hits("docs/shot.png", "\x89PNG")))
    check("an image under results/ passes", hits("results/chart.png", "\x89PNG") == [])
    check("an aggregate JSON under results/ passes", hits("results/study.json", '{"gap": 0.012, "wins": 61}') == [])
    check("a golden JSON under tests/golden/ passes", hits("tests/golden/study.json", '{"keys": {"a": 1.5}}') == [])
    check("a price series saved as results JSON is refused", any("daily series" in x for x in hits("results/leak.json", js_series)))
    check("a pasted daily series in a markdown file is refused", any("daily series" in x for x in hits("results/leak.md", daily)))
    check("a small public reference table under reference/ passes", hits("reference/table.csv", "year,div\n1950,4.2\n1951,4.3\n") == [])
    check("a home path inside an allowed JSON file is still caught", any("home directory path" in x for x in hits("results/m.json", '{"in": "' + home_json + '"}')))

# 4. The real repository.
personal = scan_ids.personal_terms() or []
problems = scan_ids.scan(personal=personal)
kinds = Counter()
for line in problems:
    kinds[scan_ids.category(line)] += 1
enforced = scan_ids.ENFORCED_IN_SUITE        # the script prints the same two tiers in its summary
for k in enforced:
    check(f"the repository has no '{k}' hit", kinds[k] == 0, [p for p in problems if k in p][:3])
check("the repository has no hit of an unknown kind", kinds["other"] == 0, [p for p in problems][:3])
notes = {k: kinds[k] for k in scan_ids.REPORTED_ONLY if kinds[k]}
if RELEASE_GATE:
    check("every publishable file passes the full scan", not problems, "; ".join(problems[:5]))
elif notes:
    print(f"note: release-pass hits not yet enforced: {notes} ({'with' if personal else 'without'} the private term list)")
