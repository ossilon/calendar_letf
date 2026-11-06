#!/usr/bin/env python3
"""Fresh-clone check: does the repository work for a stranger who has none of the private data?

    py scripts\\fresh_clone_check.py            copy, run the tests there, report; exit code 0 only if all pass
    py scripts\\fresh_clone_check.py --keep     keep the temporary copy and print its folder

What it does
1. Copies every file the .gitignore would publish (the same rule scripts/scan_identifiers.py uses) into a new
   temporary folder. Price files, rate files, raw outputs and private notes are not copied.
2. Runs `tests/run_tests.py` in that folder with CALENDAR_LETF_DATA, CALENDAR_LETF_RATES and
   CALENDAR_LETF_IDENTIFIERS removed from the environment.
3. Reports, per test file, how many checks passed, how many failed and which lines announce a skip, then the total.
   A data-bound test must skip with a printed note; a failure without data is a defect.
"""
import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PRIVATE_ENV = ("CALENDAR_LETF_DATA", "CALENDAR_LETF_RATES", "CALENDAR_LETF_IDENTIFIERS")
MODULE = re.compile(r"^===== (\S+) =====$")
SKIP = re.compile(r"(?i)\bskip(?:ped)?\b")


def load_scanner():
    spec = importlib.util.spec_from_file_location("scan_identifiers", REPO / "scripts" / "scan_identifiers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BINARY_SUFFIXES = (".pdf", ".png")               # `binary` in .gitattributes; every other file is text=auto eol=lf


def as_checked_out(data, rel):
    """The bytes a git clone gives for a file under this repository's .gitattributes: `* text=auto eol=lf`, so a text
    file (no NUL byte in its first 8,000 bytes, git's own test, and not marked binary) comes out with LF line endings.
    The working tree may hold CR LF (a Windows script wrote it), and a check on the working-tree bytes would miss what a
    stranger gets (re-grade of 2026-11-06, finding T1)."""
    if Path(rel).suffix.lower() in BINARY_SUFFIXES or b"\0" in data[:8000]:
        return data
    return data.replace(b"\r\n", b"\n")


def copy_publishable(dest, repo=REPO):
    """Copy the publishable files into `dest` as a git checkout would write them (as_checked_out); return their
    relative paths."""
    files = load_scanner().published_files(repo)
    for rel, path in files:
        target = Path(dest) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(as_checked_out(Path(path).read_bytes(), rel))
        shutil.copystat(path, target)
    return [rel for rel, _ in files]


def summarize(output):
    """Parse run_tests output into {module: {'ok': n, 'fail': n, 'skips': [lines]}} plus the failure names."""
    modules, current, failed = {}, None, []
    for line in output.splitlines():
        m = MODULE.match(line.strip())
        if m:
            current = modules.setdefault(m.group(1), {"ok": 0, "fail": 0, "skips": []})
            continue
        if current is None:
            continue
        if line.startswith("ok   "):
            current["ok"] += 1
        elif line.startswith("FAIL "):
            current["fail"] += 1
            failed.append(f"{next(k for k, v in modules.items() if v is current)}: {line[5:].strip()}")
        elif SKIP.search(line) and not line.startswith(("ok   ", "FAIL ")):
            current["skips"].append(line.strip())
    return modules, failed


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run the test suite on a copy of the publishable files, with no private data")
    ap.add_argument("--keep", action="store_true", help="keep the temporary copy and print its folder")
    args = ap.parse_args(argv)

    tmp = Path(tempfile.mkdtemp(prefix="calendar_letf_clone_"))
    try:
        files = copy_publishable(tmp)
        leaked = [f for f in files if f.startswith("data/") and f != "data/README.md"]
        print(f"copied {len(files)} publishable files; price/rate files copied: {len(leaked)}")
        env = {k: v for k, v in os.environ.items() if k not in PRIVATE_ENV}
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run([sys.executable, "tests/run_tests.py"], cwd=tmp, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        modules, failed = summarize(proc.stdout)
        ran = sum(v["ok"] + v["fail"] for v in modules.values())
        skips = [(name, s) for name, v in modules.items() for s in v["skips"]]
        crashed = "Traceback" in proc.stdout or "Traceback" in proc.stderr
        print(f"\n{'test file':32s} {'ok':>5s} {'fail':>5s} {'skip notes':>11s}")
        for name, v in modules.items():
            print(f"{name:32s} {v['ok']:5d} {v['fail']:5d} {len(v['skips']):11d}")
        print(f"\nchecks run: {ran}; failed: {len(failed)}; skip notes: {len(skips)}; exit code {proc.returncode}")
        for name, s in skips:
            print(f"  skip  {name}: {s[:150]}")
        for f in failed:
            print(f"  FAIL  {f}")
        if crashed:
            print("  a traceback appeared in the output; see the last lines:")
            print("\n".join((proc.stdout + proc.stderr).splitlines()[-15:]))
        ok = proc.returncode == 0 and not failed and not leaked and not crashed
        print("\nfresh-clone check: " + ("PASS" if ok else "FAIL"))
        if args.keep:
            print(f"copy kept at {tmp}")
        return 0 if ok else 1
    finally:
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
