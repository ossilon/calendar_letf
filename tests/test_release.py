"""Final-release maintenance (BACKLOG B20): the release must stay usable after its author stops maintaining it.

  * The tested versions sit in constraints.txt and in the README, and they agree. Every dependency in pyproject.toml
    has a pinned version there.
  * The README's no-affiliation paragraph names every fund sponsor that any published file names.
  * The README's "What this cannot tell you" section names the cuts (B2: the short funds).
The golden-file skip on other inputs is tested in tests/test_golden.py.
"""
import importlib.util
import re
import sys
from importlib import metadata

from _harness import ROOT, check

spec = importlib.util.spec_from_file_location("scan_identifiers", ROOT / "scripts" / "scan_identifiers.py")
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)

README = (ROOT / "README.md").read_text(encoding="utf-8")

# ---------------------------------------------------------------- 1. tested versions
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([0-9][0-9A-Za-z.]*)\s*$")


def pins(text):
    """{package: version} of every `name==version` line (comments and blank lines skipped)."""
    out = {}
    for line in text.splitlines():
        m = PIN.match(line.split("#", 1)[0].strip()) if line.strip() and not line.lstrip().startswith("#") else None
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def dependencies(pyproject_text):
    """Package names in pyproject.toml's dependencies list."""
    block = pyproject_text[pyproject_text.index("dependencies = ["):]
    block = block[:block.index("]")]
    return sorted(m.group(1).lower() for m in re.finditer(r'"([A-Za-z0-9_.-]+)\s*[<>=!~]', block))


check("pins: parses name==version, skips comments", pins("# x\nnumpy==2.5.3\n  # y==1\npandas==3.0.6  # note\n")
      == {"numpy": "2.5.3", "pandas": "3.0.6"})
_pins = pins((ROOT / "constraints.txt").read_text(encoding="utf-8"))
_deps = dependencies((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
check("constraints.txt pins every dependency in pyproject.toml", _deps and all(d in _pins for d in _deps), (_deps, _pins))
_flat = " ".join(README.split())
_named = [f"{name} {ver}" for name, ver in _pins.items()]
check("the README names the same tested versions as constraints.txt", all(n in _flat for n in _named),
      [n for n in _named if n not in _flat])
_py = re.search(r"tested versions are Python (\d+\.\d+)\.\d+", _flat)
check("the README names the tested Python version", _py is not None)
_installed = {}
for _name in _pins:
    try:
        _installed[_name] = metadata.version(_name)
    except metadata.PackageNotFoundError:
        _installed[_name] = None
_off = {n: (_pins[n], v) for n, v in _installed.items() if v != _pins[n]}
_pyv = f"{sys.version_info.major}.{sys.version_info.minor}"
if _off or (_py and _py.group(1) != _pyv):
    print(f"note: this environment differs from the tested versions (pinned, installed): {_off}; Python {_pyv}. "
          "If a test fails here, try `pip install -c constraints.txt -e .`")

# ---------------------------------------------------------------- 2. sponsors in the disclaimer
# Every fund sponsor whose name a published file may carry. A new sponsor in the tree must join this list and the README.
SPONSORS = ("Tradr", "AXS", "Direxion", "Rydex", "Guggenheim", "ProFunds", "ProShares", "Roundhill", "GraniteShares",
            "iShares", "BlackRock", "Invesco", "SPDR", "State Street", "SSGA")
TEXT_SUFFIXES = {".md", ".py", ".json", ".csv", ".toml", ".txt"}


def disclaimer(readme):
    """The README paragraph that starts 'This project has no affiliation'."""
    i = readme.index("This project has no affiliation")
    j = readme.find("\n\n", i)
    return " ".join(readme[i:j if j > 0 else None].split())


def sponsors_missing(text, found):
    return [s for s in found if s not in text]


_disc = disclaimer(README)
_found = set()
for _rel, _path in scan.published_files(ROOT):
    if _path.suffix.lower() in TEXT_SUFFIXES and _rel != "tests/test_release.py":
        _t = _path.read_text(encoding="utf-8", errors="replace")
        _found |= {s for s in SPONSORS if re.search(rf"\b{re.escape(s)}\b", _t)}
check("the published tree names the sponsors it models (at least Tradr, Direxion, ProShares)",
      {"Tradr", "Direxion", "ProShares"} <= _found, sorted(_found))
check("the README disclaimer names every sponsor that a published file names", not sponsors_missing(_disc, sorted(_found)),
      sponsors_missing(_disc, sorted(_found)))
check("the README disclaimer also names the sponsors the backlog lists (GraniteShares, Guggenheim)",
      not sponsors_missing(_disc, ["GraniteShares", "Guggenheim"]))
check("planted: a disclaimer without Roundhill is caught", sponsors_missing(_disc.replace("Roundhill", "R."), ["Roundhill"]) == ["Roundhill"])
check("the disclaimer says no affiliation and no endorsement", "no affiliation" in _disc and "endorsement" in _disc)

# ---------------------------------------------------------------- 3. the cuts
_limits = README[README.index("## What this cannot tell you"):]
_limits = _limits[:_limits.index("\n## ", 5)]
check("'What this cannot tell you' names the B2 cut (the short funds MSPY and DQQQ)",
      "MSPY" in _limits and "DQQQ" in _limits and "out of scope" in _limits)


# ---------------------------------------------------------------- 4. the fresh-clone check sees what a git clone gives (T1)
_fspec = importlib.util.spec_from_file_location("fresh_clone_check", ROOT / "scripts" / "fresh_clone_check.py")
fcc = importlib.util.module_from_spec(_fspec)
_fspec.loader.exec_module(fcc)
check("fresh-clone copy: a text file comes out with LF line endings, as .gitattributes (text=auto eol=lf) checks it out",
      fcc.as_checked_out(b"{\r\n \"a\": 1\r\n}\r\n", "results/x.json") == b"{\n \"a\": 1\n}\n"
      and fcc.as_checked_out(b"a\r\nb\r\n", "README.md") == b"a\nb\n")
check("fresh-clone copy: a binary (.png, .pdf, or bytes with a NUL) keeps its bytes",
      fcc.as_checked_out(b"x\r\ny", "results/a.png") == b"x\r\ny" and fcc.as_checked_out(b"x\r\n\0y", "data.bin") == b"x\r\n\0y")
_attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
check("fresh-clone copy: .gitattributes still says text=auto eol=lf and marks exactly .pdf and .png binary",
      "* text=auto eol=lf" in _attrs and sorted(l.split()[0] for l in _attrs.splitlines() if l.strip().endswith(" binary"))
      == sorted("*" + s for s in fcc.BINARY_SUFFIXES))


# ---------------------------------------------------------------- 5. one version everywhere (re-grade 2026-11-06: CITATION.cff said 0.1.0)
import calendar_letf as _pkg  # noqa: E402

_v_py = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
_v_cff = re.search(r"^version: (\S+)", (ROOT / "CITATION.cff").read_text(encoding="utf-8"), re.M).group(1)
check("one version: pyproject.toml, CITATION.cff and calendar_letf.__version__ agree", _v_py == _v_cff == _pkg.__version__,
      (_v_py, _v_cff, _pkg.__version__))
check("the CHANGELOG has an entry for that version", f"## {_v_py} (" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
