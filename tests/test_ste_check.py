"""Style guard: scripts/ste_check.py (Simplified Technical English, American spelling) flags what it promises to.

Part 1 feeds it single sentences and small Markdown files. Part 2 runs it on the real public documents and reports
the count as a note; the release pass brings that count to zero (flip RELEASE_GATE to True then).
"""
import importlib.util
import tempfile
from pathlib import Path

from _harness import ROOT, check

RELEASE_GATE = True        # flipped in the R4 review fix pass (2026-10-29): the public documents lint at 0, now enforced

spec = importlib.util.spec_from_file_location("ste_check", ROOT / "scripts" / "ste_check.py")
ste = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ste)


def kinds(sentence):
    return " | ".join(ste.check_sentence(sentence))


clean = "The kernel resets the fund on the last trading day of each month."
check("a short active sentence passes", ste.check_sentence(clean) == [], kinds(clean))

long_sentence = " ".join(["word"] * 26) + "."
check("a 26-word sentence is flagged (limit 25)", "26 words" in kinds(long_sentence), kinds(long_sentence))
check("a 25-word sentence passes the length rule", "words (limit" not in kinds(" ".join(["word"] * 25) + "."))
instruction = "Run " + " ".join(["word"] * 20) + "."
check("an instruction of 21 words is flagged (limit 20)", "limit 20" in kinds(instruction), kinds(instruction))

check("passive voice is flagged", "passive voice" in kinds("The file is loaded by the script."))
check("an adjective participle is not passive voice", "passive" not in kinds("The data are split-adjusted."))
check("a progressive tense is flagged", "progressive" in kinds("The script is running the model."))
check("an -ing noun is flagged", "-ing form" in kinds("Avoid overfitting the rule."))
check("an allowed -ing word passes", "-ing" not in kinds("The financing cost is 1.5%."))
for word, fix in (("e.g.", "for example"), ("basically", "delete"), ("utilize", "use"), ("via", "through")):
    check(f"banned word '{word}' is flagged with its fix", any(word in x and fix in x for x in ste.check_sentence(f"We {word} test it.")),
          kinds(f"We {word} test it."))
for w in ("behavio" + "ur", "colo" + "ur", "mode" + "lling", "centre"):
    check(f"British spelling '{w}' is flagged", "British spelling" in kinds(f"The {w} is stable."))
for w in ("behavior", "color", "modeling", "center"):
    check(f"American spelling '{w}' passes", "British" not in kinds(f"The {w} is stable."))

stripped = ste.strip_markup("Use `a very long code span that is not prose` and [a link](https://example.org/x) here.")
check("code spans and link targets are stripped before the check", "very long" not in stripped and "example.org" not in stripped, stripped)
check("a short quoted phrase is skipped, a long one is kept",
      "QUOTE" in ste.strip_markup('He wrote "a short title" there.')
      and "QUOTE" not in ste.strip_markup('He wrote "' + " ".join(["word"] * 16) + '" there.'))

md = ["# Title that is long enough to pass without any length rule being applied at all here", "", "```", "e.g. code is skipped",
      "```", "", "Good sentence one. Good sentence two.", "", "This is basically wrong.", "",
      "| Col | Cell with via |", "|---|---|", "| a | b |"]
got = [(n, k) for n, k, _t in ste.blocks(md)]
check("fenced code is skipped, headings, paragraphs and table cells are yielded",
      [k for _n, k in got] == ["heading", "para", "para", "cell", "cell", "cell", "cell"], got)

with tempfile.TemporaryDirectory() as tmp:
    good, bad = Path(tmp) / "good.md", Path(tmp) / "bad.md"
    good.write_text("# Notes\n\nRun the tests. The kernel resets each month.\n", encoding="utf-8")
    bad.write_text("# Notes\n\nThis is basically broken. " + " ".join(["word"] * 30) + ".\n\n" + "A sentence. " * 7 + "\n", encoding="utf-8")
    check("a clean file has no problems", ste.check_file(good) == [], ste.check_file(good))
    why = " ".join(w for _l, w, _s in ste.check_file(bad))
    check("a bad file reports a banned word, a long sentence and a long paragraph",
          "banned word" in why and "words (limit" in why and "paragraph of 7 sentences" in why, why)
    check("main returns 0 for a clean file and 1 for a bad one", ste.main([str(good)]) == 0 and ste.main([str(bad)]) == 1)

# Math (B18, THEORY.md): display blocks and inline math are not prose; a dollar amount still is.
check("inline math is skipped: $L(L-1)\\sigma^2/2$ and $L$ become MATH",
      "sigma" not in ste.strip_markup("The drag $L(L-1)\\sigma^2/2$ grows with $L$.")
      and ste.strip_markup("The drag $L(L-1)\\sigma^2/2$ grows with $L$.").count("MATH") == 2)
check("a dollar amount is not math: '$4,522 of $10,000' stays prose",
      ste.strip_markup("The fund kept $4,522 of $10,000.") == "The fund kept $4,522 of $10,000.")
_m = ["Prose before.", "", "$$", "x = \\frac{a}{b} \\text{ is computed by the kernel and it is long}", "\\tag{1}", "$$", "",
      "$$ y = 2 $$", "Prose after."]
_b = [t for _l, _k, t in ste.blocks(_m)]
check("display math between $$ lines and a one-line $$ ... $$ block are skipped; the prose around them is kept",
      _b == ["Prose before.", "Prose after."], _b)
check("THEORY.md is on the public list", "THEORY.md" in ste.PUBLIC)

# Real documents: reported, not yet enforced.
files = ste.public_files()
check("the public document list names files that exist", len(files) >= 3, [f.name for f in files])
total = sum(len(ste.check_file(f)) for f in files)
if RELEASE_GATE:
    check("the public documents pass the style check", total == 0, f"{total} problem(s)")
else:
    print(f"note: style problems in the public documents, not yet enforced: {total} in {len(files)} files")
