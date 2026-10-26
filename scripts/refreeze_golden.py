#!/usr/bin/env python3
"""Re-freeze a golden file from the current results.

    py scripts\\refreeze_golden.py --study strategies --reason "R2 kernel exactness"
    py scripts\\refreeze_golden.py --study all --reason "..."

When to use it: tests/test_golden.py failed because a published number moved, you checked WHY, and the new number is
the intended one. Never use it just to make a failure go away. The reason goes into the golden file (a `refrozen`
list holds date, reason and how many keys changed), so the history of every deliberate change stays in the file.
The script refuses to run without a reason.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tests"))
import _golden  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rewrite tests/golden/<study>.json from results/<study>.json")
    ap.add_argument("--study", required=True, help="one of: " + ", ".join(_golden.STUDIES) + ", or all")
    ap.add_argument("--reason", default="", help="why the numbers changed (required)")
    args = ap.parse_args(argv)
    if not args.reason.strip():
        print("refused: --reason is required (say what changed and why)")
        return 2
    studies = _golden.STUDIES if args.study == "all" else (args.study,)
    for study in studies:
        try:
            n, changed = _golden.refreeze(study, args.reason)
        except (ValueError, FileNotFoundError) as err:
            print(f"refused: {err}")
            return 2
        print(f"{study}: {n} keys written, {changed} changed against the previous golden file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
