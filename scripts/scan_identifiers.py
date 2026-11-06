#!/usr/bin/env python3
"""Refuse to publish personal identifiers, secrets, AI-tool names or licensed data.  Run before every push:

    py -I scripts\\scan_identifiers.py          (must print "0 problem(s)"; exit code 1 on any hit)

It checks every file git would publish (everything .gitignore does not exclude, matched the way git matches):
1. personal terms from a PRIVATE list, `identifiers_local.txt` (one regular expression per line, # for comments),
   in file contents and file names. The list never sits in this repository: the script looks for it in
   $CALENDAR_LETF_IDENTIFIERS, then the repository root (git-ignored), then the sibling folder calendar_letf_private.
   Without a list only the generic checks run, and the script says so;
2. generic leaks: Windows and Unix home-directory paths, e-mail addresses, API-key and token patterns, the names of
   AI models and vendors (public text says "an independent audit", never who did it), and British spellings (the
   public style rule is plain American English);
3. data files that must not ship: CSV/JSON/XLS/PDF/Parquet outside the folders that hold published aggregates,
   images outside results/, and any file with a run of 5 or more dated numeric rows whose dates follow each other
   within 5 days (a pasted daily series).

Edit the lists below to change what the scan catches. tests/test_scan_identifiers.py runs the same scan inside the
test suite, with two tiers:
- ENFORCED_IN_SUITE: data files, images, daily series, home-directory paths, e-mail addresses, secrets and API-key
  patterns. One hit fails the suite.
- REPORTED_ONLY: AI model or vendor names, British spellings and private terms. The suite prints them as a note until
  the release pass sets RELEASE_GATE = True in the test file.
This script is the release gate: it exits 1 on a hit in EITHER tier, so it can fail while the suite passes. Its summary
line prints the hit count of each tier. The test file reads the two lists below, so the script and the suite agree.
"""
import functools
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".toml", ".cfg", ".ini", ".yml", ".yaml", ".html", ".js", ".css",
                 ".csv", ".gitignore", ".cff", ".svg", ".pine", ".sha256", ""}

# ---------------------------------------------------------------- configurable lists
GENERIC = {
    # one or two backslashes: JSON doubles every backslash in a Windows path
    "home directory path": re.compile(r"[A-Za-z]:\\{1,2}Users\\{1,2}[^\\\s]+|/home/[a-z0-9_-]+|/Users/[A-Za-z0-9_-]+"),
    "email address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "possible secret": re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}"),
    "API key pattern": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}|\bghp_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}|\bAKIA[0-9A-Z]{16}\b"
                                  r"|\bxox[abp]-[A-Za-z0-9-]{10,}|\bAIza[0-9A-Za-z_-]{35}\b"),
    # public rule: no model or vendor names. Case-sensitive on purpose: "opus" or "fable" in lower case are plain words.
    "AI model or vendor name": re.compile(r"\b(Claude|Anthropic|Opus|Sonnet|Haiku|Fable|ChatGPT|OpenAI|GPT-?\d\w*|Gemini|Copilot"
                                          r"|Codex|Llama|Mistral|DeepSeek|Grok)\b"),
    # public style rule: plain American English. "analyses" passes (it is also the American plural of "analysis");
    # the verb forms analyse, analysed, analysing and analyser still fail.
    # The -is- verbs count only with a verb or -ation ending, so "optimistic", "realistic", "organism" and "analysis" pass.
    # "cancell" counts only as cancelled / cancelling: "cancellation" is American too (R4 review).
    "British spelling": re.compile(r"(?i)\b\w*(behaviour|licence|centre|neighbour|favour|colour|honour|programme|labell|modell"
                                   r"|cancell(?:ed|ing)|catalogue|whilst|towards|artefact|judgement|\bmaths\b"
                                   r"|(?:organis|recognis|summaris|realis|vectoris|itemis|minimis|maximis|optimis|prioritis"
                                   r"|parallelis|normalis|standardis|annualis|initialis|characteris|utilis|generalis"
                                   r"|categoris|visualis|emphasis)(?:e|ed|es|er|ers|ing|ation|ations|able)(?![a-z])"
                                   r"|analys(?:e\b|ed|ing|er))\w*"),
}
ALLOWED_EMAILS = set()                                       # public contacts that docs may cite
# These files list the spellings and names they look for, so they cannot pass the check on themselves.
SELF_LISTS = {"scripts/scan_identifiers.py", "scripts/ste_check.py", "tests/test_scan_identifiers.py",
              "tests/test_ste_check.py"}
DATA_SUFFIXES = {".csv", ".json", ".jsonl", ".xls", ".xlsx", ".pdf", ".parquet"}
# Published aggregates and small public reference tables. Their contents are still scanned like any text file.
ALLOWED_DATA_DIRS = ("results/", "tests/golden/", "reference/")
ALLOWED_DATA_FILES = {"tests/prose_pins.json",              # single files allowed outside those folders: the prose-pin list (text anchors and key paths, no data)
                      "docs/theory_examples.json"}          # and the THEORY.md worked examples (planted inputs only, no market data; B18)
DAILY_EXEMPT = {"reference/shiller_sp500_monthly.csv"}       # monthly public series (Shiller), not exchange data
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
ALLOWED_IMAGE_DIRS = ("results/",)                           # charts the study scripts draw, aggregates only
ALLOWED_IMAGE_FILES = ("docs/banner.png",)                   # the README banner: artwork (a synthetic ribbon), no data
MAX_DATED_RUN = 4
MAX_GAP_DAYS = 5

# The two tiers (see the module docstring). tests/test_scan_identifiers.py enforces the first and only reports the second.
ENFORCED_IN_SUITE = ("data file", "image file", "daily series", "home directory path", "email address", "possible secret",
                     "API key pattern")
REPORTED_ONLY = ("AI model or vendor name", "British spelling", "personal term")


def category(problem):
    """The tier-list name a problem line belongs to ('other' if it matches none of them)."""
    return next((k for k in ENFORCED_IN_SUITE + REPORTED_ONLY if k in problem), "other")


# ---------------------------------------------------------------- .gitignore matching (git's rules)

def ignore_patterns(repo=REPO):
    pats = []
    for line in (Path(repo) / ".gitignore").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            pats.append(line)
    return pats


@functools.lru_cache(maxsize=None)
def _rule(pattern):
    """(regex, negated, directory_only) for one .gitignore line, following gitignore(5).

    A slash at the start or in the middle anchors the pattern to the repository root; otherwise it matches at any
    depth. A trailing slash matches directories only. '*' and '?' never cross a '/'; '**' does.
    """
    negated = pattern.startswith("!")
    pat = pattern[1:] if negated else pattern
    dir_only = pat.endswith("/")
    pat = pat.rstrip("/")
    anchored = "/" in pat
    pat = pat.lstrip("/")
    out, i = "", 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pat.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pat[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pat[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pat[i]), i + 1
    return re.compile(("" if anchored else "(?:.*/)?") + out + r"\Z"), negated, dir_only


def ignored(rel, pats):
    """True if git would ignore the file at `rel` (a path relative to the repository, with '/').

    Like git: each parent folder is checked first, and a file inside an ignored folder stays ignored even if a later
    '!' pattern names it. For the file itself, the last matching pattern wins.
    """
    rules = [_rule(p) for p in pats]
    parts = rel.split("/")
    for depth in range(1, len(parts) + 1):
        sub, is_dir = "/".join(parts[:depth]), depth < len(parts)
        state = None
        for rx, negated, dir_only in rules:
            if dir_only and not is_dir:
                continue
            if rx.match(sub):
                state = not negated
        if is_dir and state:
            return True
        if not is_dir:
            return bool(state)
    return False


def published_files(repo=REPO):
    """[(relative path with '/', Path)] of every file the .gitignore does not exclude."""
    repo = Path(repo)
    pats = ignore_patterns(repo)
    out = []
    for path in sorted(repo.rglob("*")):
        rel_parts = path.relative_to(repo).parts
        if path.is_dir() or ".git" in rel_parts:
            continue
        rel = path.relative_to(repo).as_posix()
        if not ignored(rel, pats):
            out.append((rel, path))
    return out


# ---------------------------------------------------------------- daily-series detector

DATED_ROW = re.compile(r"^\s*\|?\s*((?:19|20)\d\d-\d\d-\d\d)\s*[|,;\t]")
DECIMAL = re.compile(r"-?\d+\.\d+")


def _day(text):
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def longest_dated_run(text):
    """Longest run of consecutive dated numeric rows whose dates rise by 1 to MAX_GAP_DAYS days each.

    A dated numeric row is a line that starts with an ISO date and holds at least two decimal numbers. A daily or
    weekly price series makes a long run. A list of event dates (crash bottoms years apart) does not.
    """
    best = run = 0
    prev = None
    for line in text.splitlines():
        m = DATED_ROW.match(line)
        if not (m and len(DECIMAL.findall(line)) >= 2):
            continue
        d = _day(m.group(1))
        if d is not None and prev is not None and 0 < (d - prev).days <= MAX_GAP_DAYS:
            run += 1
        else:
            run = 1
        prev = d
        best = max(best, run)
    return best


def _walk_dates(obj, found):
    """Collect, for every list in a JSON value, the dates of items that are ISO strings or dicts with a date field."""
    if isinstance(obj, dict):
        for v in obj.values():
            _walk_dates(v, found)
    elif isinstance(obj, list):
        days = []
        for item in obj:
            if isinstance(item, str):
                d = _day(item[:10]) if re.match(r"\d{4}-\d{2}-\d{2}", item) else None
            elif isinstance(item, dict):
                d = next((_day(item[k][:10]) for k in ("date", "day", "time") if isinstance(item.get(k), str)), None)
            else:
                d = None
            if d is not None:
                days.append(d)
        found.append(days)
        for item in obj:
            _walk_dates(item, found)


def json_series_run(text):
    """Longest run of consecutive dates (1 to MAX_GAP_DAYS days apart) inside any one JSON list."""
    try:
        obj = json.loads(text)
    except ValueError:
        return 0
    lists = []
    _walk_dates(obj, lists)
    best = 0
    for days in lists:
        run = 1 if days else 0
        for a, b in zip(days, days[1:]):
            run = run + 1 if 0 < (b - a).days <= MAX_GAP_DAYS else 1
            best = max(best, run)
        best = max(best, run)
    return best


# ---------------------------------------------------------------- personal terms (private list)

def personal_list_path(repo=REPO):
    """First existing identifiers_local.txt among the documented places, or None."""
    repo = Path(repo)
    env = os.environ.get("CALENDAR_LETF_IDENTIFIERS")
    candidates = ([Path(env)] if env else []) + [repo / "identifiers_local.txt",
                                                   repo.parent / "calendar_letf_private" / "identifiers_local.txt"]
    return next((p for p in candidates if p.exists()), None)


def personal_terms(repo=REPO):
    path = personal_list_path(repo)
    if path is None:
        return None
    out = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(re.compile(line, re.IGNORECASE))
    return out


# ---------------------------------------------------------------- the scan

def scan(files=None, personal=(), repo=REPO):
    """Problems (list of 'file:line: kind: text' strings) in the files git would publish."""
    files = published_files(repo) if files is None else files
    problems = []
    for rel, path in files:
        for rx in personal:
            if rx.search(rel):
                problems.append(f"{rel}: personal term /{rx.pattern}/ in the file name")
        suffix = Path(rel).suffix.lower()
        allowed_file = rel in ALLOWED_DATA_FILES or (rel.startswith(ALLOWED_DATA_DIRS) and suffix in DATA_SUFFIXES)
        if suffix in DATA_SUFFIXES and not allowed_file:
            problems.append(f"{rel}: data file; git would publish it")
            continue
        if suffix in IMAGE_SUFFIXES and not rel.startswith(ALLOWED_IMAGE_DIRS) and rel not in ALLOWED_IMAGE_FILES:
            problems.append(f"{rel}: image file; publish only images this code draws, under results/")
            continue
        if suffix in IMAGE_SUFFIXES:
            continue
        if suffix not in TEXT_SUFFIXES and not allowed_file:
            continue
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        if rel not in DAILY_EXEMPT:
            run = json_series_run(text) if suffix == ".json" else longest_dated_run(text)
            if run > MAX_DATED_RUN:
                problems.append(f"{rel}: run of {run} consecutive dated numeric rows; looks like a daily series")
        for n, line in enumerate(text.splitlines(), 1):
            for rx in personal:
                if rx.search(line):
                    problems.append(f"{rel}:{n}: personal term /{rx.pattern}/")
            for name, rx in GENERIC.items():
                if rel in SELF_LISTS and name in ("British spelling", "AI model or vendor name"):
                    continue                                   # these files list what they look for
                for m in rx.finditer(line):
                    if name == "email address" and m.group(0).lower() in ALLOWED_EMAILS:
                        continue
                    problems.append(f"{rel}:{n}: {name}: {m.group(0)[:40]}")
    return problems


def main():
    personal = personal_terms()
    if personal is None:
        print("WARNING: identifiers_local.txt not found; only generic checks run")
        personal = []
    files = published_files()
    problems = scan(files, personal)
    for p in problems:
        print(p)
    print(f"\nscanned {len(files)} publishable files; {len(problems)} problem(s)")
    counts = {}
    for p in problems:
        counts[category(p)] = counts.get(category(p), 0) + 1
    enforced = sum(counts.get(k, 0) for k in ENFORCED_IN_SUITE) + counts.get("other", 0)
    reported = sum(counts.get(k, 0) for k in REPORTED_ONLY)
    print(f"enforced in the test suite ({enforced} hit(s); one hit fails the suite): " + ", ".join(ENFORCED_IN_SUITE))
    print(f"release tier, enforced in the suite since the R4 release pass (RELEASE_GATE in tests/test_scan_identifiers.py) "
          f"({reported} hit(s)): " + ", ".join(REPORTED_ONLY))
    if problems and not enforced:
        print("the suite passes today, but this script exits 1: it is the release gate and counts both tiers")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
