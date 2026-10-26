"""Prose pins: check that the numbers printed in FINDINGS.md and ASSUMPTIONS.md equal the numbers in results/*.json.

Plain-English summary
  * A "pin" ties a place in a prose file to a value in a results file. The pin names the file, an ANCHOR (a short text
    that occurs exactly once and sits just before the numbers), and the items that should follow: for each item the JSON
    file, the key path, and the print format (scale, decimals, sign). The checker finds the anchor, reads the numbers
    printed after it, formats the true values the same way and compares the TEXT exactly ("+0.66" is not "0.66").
  * tests/prose_pins.json holds the pins; tests/test_prose_pins.py runs them. A mismatch is a failing check that prints
    the quoted prose, the true value and the file. When the prose is reworded, fix the prose or the anchor, never the
    format to match a wrong number.

How numbers are read (documented per pin through "mode" and "kind")
  * mode "after": the file text with every run of whitespace collapsed to one space (a hard-wrapped sentence reads as
    one line). The numbers are the tokens that follow the END of the anchor, in order.
  * mode "cell": the table row is the single line that contains the anchor, plus "row_offset" lines; the cell is the
    text between the pipes at index "col" (the text before the first pipe is index 0, so the first real column is 1).
    The numbers are the tokens of that cell.
  * kind "decimal" (default): a token is an optional sign and digits with a decimal point (0.66, -0.09, 12.50). A sign
    counts only when no letter, digit or point stands directly before it, so "0.88-0.92" reads as 0.88 and 0.92 and
    "2025-09-30" gives nothing. kind "signed": only tokens with an explicit + or - (for a chain of pp changes between
    unsigned words). kind "int": whole numbers such as 12 in "12-73%". kind "mult": a decimal followed directly by x
    (2.04x reads 2.04). kind "money": the digits after a dollar sign with thousands separators ($27,323 reads
    27,323); its items set "comma": true, so the true value prints with separators.
  * an item {"skip": n} drops the next n tokens (a distractor between two numbers that are pinned).
  * an item {"path": [...]} is one value ("len": true makes it the length of the list at the path, a count);
    {"of": [path, ...], "fn": "min"|"max"|"median", "abs": true|false} is the
    smallest, largest or middle of several values (the printed range "0.88-0.92" is min and max over the three funds).
  * format: "scale" (100 for a fraction printed as a percent or pp), "decimals", "sign" ("always" prints +0.66; "minus"
    prints 0.66 and -0.66 only).
  * key paths are lists: a string is a dict key (a key may hold dots), an integer is a list position, and
    {"where": {"start": "...", "end": "..."}} picks the one list row whose fields match.

Not in this module: running the pins (test_prose_pins.py does).
"""
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN = {
    "decimal": re.compile(r"(?<![\w.])[+-]?\d+\.\d+(?![\w])"),
    "signed": re.compile(r"(?<![\w.])[+-]\d+\.\d+(?![\w])"),
    "int": re.compile(r"(?<![\w.])[+-]?\d+(?![\w.])"),
    "mult": re.compile(r"(?<![\w.])\d+\.\d+(?=x(?!\w))"),
    "money": re.compile(r"(?<=\$)\d{1,3}(?:,\d{3})+(?!\w)"),
}
FUNCS = {"min": min, "max": max, "median": statistics.median}


class PinError(Exception):
    """A pin that cannot be evaluated (anchor missing or not unique, too few numbers, bad path)."""


def squash(text):
    """Every run of whitespace becomes one space."""
    return re.sub(r"\s+", " ", text)


def resolve(obj, path):
    """Walk `path` through nested dicts and lists (see the module docstring for the three kinds of step)."""
    cur = obj
    for step in path:
        try:
            if isinstance(step, dict):
                where = step["where"]
                hits = [r for r in cur if all(r.get(k) == v for k, v in where.items())]
                if len(hits) != 1:
                    raise PinError(f"{len(hits)} rows match {where} (need exactly 1)")
                cur = hits[0]
            else:
                cur = cur[step]
        except (KeyError, IndexError, TypeError) as err:
            raise PinError(f"key path {path} fails at {step!r}: {type(err).__name__}") from err
    return cur


def fmt(value, scale=1.0, decimals=2, sign="minus", comma=False):
    """The value as the prose prints it. A result that rounds to zero prints without a minus sign."""
    v = float(value) * scale
    sep = "," if comma else ""
    s = f"{v:+{sep}.{decimals}f}" if sign == "always" else f"{v:{sep}.{decimals}f}"
    if float(s.replace(",", "")) == 0.0:
        s = ("+" if sign == "always" else "") + f"{0.0:.{decimals}f}"
    return s


def item_value(item, results):
    """The number one item stands for: the value at its path, or min / max (of abs) over several paths."""
    if "path" in item:
        vals = [resolve(results, item["path"])]
        if item.get("len"):
            return len(vals[0])
    else:
        vals = [resolve(results, p) for p in item["of"]]
    if item.get("abs"):
        vals = [abs(v) for v in vals]
    if "path" in item:
        return vals[0]
    return FUNCS[item["fn"]](vals)


def locate(pin, text):
    """(start offset, text to read numbers from, quote start offset) for the pin's anchor."""
    if pin["mode"] == "cell":
        lines = text.split("\n")
        hits = [i for i, ln in enumerate(lines) if pin["anchor"] in ln]
        if len(hits) != 1:
            raise PinError(f"anchor {pin['anchor']!r} found on {len(hits)} lines (need exactly 1)")
        j = hits[0] + pin["cell"].get("row_offset", 0)
        if not 0 <= j < len(lines):
            raise PinError(f"row_offset {pin['cell'].get('row_offset')} leaves the file")
        cells = lines[j].split("|")
        col = pin["cell"]["col"]
        if col >= len(cells):
            raise PinError(f"row has {len(cells)} pipe-separated parts, no column {col}: {lines[j].strip()[:80]!r}")
        return 0, cells[col], 0
    sq = squash(text)
    anchor = squash(pin["anchor"])
    n = sq.count(anchor)
    if n != 1:
        raise PinError(f"anchor {anchor!r} occurs {n} times (need exactly 1)")
    at = sq.index(anchor)
    return at + len(anchor), sq, at


def read_numbers(pin, text, count):
    """[(token, end offset in the read text)] for the first `count` tokens after the anchor, plus the quoted prose."""
    start, body, qstart = locate(pin, text)
    toks = [(m.group(0), m.end()) for m in TOKEN[pin.get("kind", "decimal")].finditer(body, start)]
    if len(toks) < count:
        raise PinError(f"only {len(toks)} numbers follow the anchor, the pin needs {count}")
    end = toks[count - 1][1] if count else start
    quote = body[qstart:end].strip() if pin["mode"] == "after" else body.strip()
    return toks[:count], (quote if len(quote) <= 400 else quote[:400] + "...")


def evaluate(pin, text, results):
    """Check one pin against the prose `text` and the loaded `results` {json file name: parsed JSON}.

    Returns (ok, detail). detail names the prose (quoted), the numbers printed, the true values and the key paths.
    """
    items = pin["items"]
    need = sum(it["skip"] if "skip" in it else 1 for it in items)
    try:
        toks, quote = read_numbers(pin, text, need)
        src = results[pin.get("json", "results/validate_live.json")]
        pos, bad, shown = 0, [], []
        for it in items:
            if "skip" in it:
                pos += it["skip"]
                continue
            printed = toks[pos][0]
            pos += 1
            want = fmt(item_value(it, src), it.get("scale", 1.0), it.get("decimals", 2), it.get("sign", "minus"), it.get("comma", False))
            shown.append((printed, want))
            if printed != want:
                where = it["path"] if "path" in it else f"{it['fn']} of {len(it['of'])} paths, e.g. {it['of'][0]}"
                bad.append(f"prose {printed} but results hold {want} ({where})")
    except PinError as err:
        return False, f"{pin['file']}: {err}"
    if bad:
        return False, f"{pin['file']}: quoted prose: \"{quote}\" | " + "; ".join(bad)
    return True, ""


def load_pins(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
