"""Input provenance: file records, manifests and banners (calendar_letf/provenance.py). Uses temp files only."""
import hashlib
import os
import tempfile
from pathlib import Path

from _harness import check, raises
from calendar_letf import loader, provenance

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    prices = tmp / "prices"
    rates = tmp / "rates"
    prices.mkdir()
    rates.mkdir()

    # a clean-format price file: 3 rows
    clean = prices / "SP_SPX_daily.csv"
    clean.write_text("date,open,high,low,close,volume\n2020-01-02,1,2,0.5,1.5,0\n2020-01-03,1,2,0.5,1.6,0\n"
                     "2020-01-06,1,2,0.5,1.7,0\n", encoding="utf-8")
    rec = provenance.file_record(clean)
    check("record holds the file name only, no folder", rec["file"] == "SP_SPX_daily.csv" and "\\" not in rec["file"]
          and "/" not in rec["file"], rec["file"])
    check("record counts data rows (header excluded)", rec["rows"] == 3, rec["rows"])
    check("record gives first and last date", (rec["first_date"], rec["last_date"]) == ("2020-01-02", "2020-01-06"), rec)
    _lf = clean.read_bytes().replace(b"\r\n", b"\n")
    check("record sha256 equals hashlib on the bytes with CR LF folded to LF", rec["sha256"] == hashlib.sha256(_lf).hexdigest())
    check("record bytes counts the same LF bytes", rec["bytes"] == len(_lf))
    # T1 (re-grade 2026-11-06): a Windows CR LF copy and a git LF checkout of the same text hash alike; a binary does not fold
    (tmp / "lf.json").write_bytes(b"{\n \"a\": 1\n}\n")
    (tmp / "crlf.json").write_bytes(b"{\r\n \"a\": 1\r\n}\r\n")
    (tmp / "blob.xls").write_bytes(b"x\r\ny")
    check("sha256_of: the CR LF and LF forms of a text file hash the same, and their byte counts agree",
          provenance.sha256_of(tmp / "lf.json") == provenance.sha256_of(tmp / "crlf.json")
          and provenance.byte_count(tmp / "lf.json") == provenance.byte_count(tmp / "crlf.json") == 12)
    check("sha256_of: a non-text file is hashed as its raw bytes (no folding)",
          provenance.sha256_of(tmp / "blob.xls") == hashlib.sha256(b"x\r\ny").hexdigest())
    check("sha256_of BREAK: one changed character in the text still changes the hash",
          provenance.sha256_of(tmp / "lf.json") != hashlib.sha256(b"{\n \"a\": 2\n}\n").hexdigest())
    check("record keys are exactly the contract", set(rec) == {"file", "sha256", "bytes", "rows", "first_date", "last_date"})

    # the fingerprint changes when one byte changes
    clean2 = prices / "copy.csv"
    clean2.write_text(clean.read_text(encoding="utf-8").replace("1.7", "1.8"), encoding="utf-8")
    check("one changed digit changes the sha256", provenance.file_record(clean2)["sha256"] != rec["sha256"])

    # a raw TradingView export with unix seconds (2020-01-02 14:30 UTC = 09:30 New York)
    raw = prices / "NASDAQ_NDX_daily.csv"
    raw.write_text("time,open,high,low,close\n1577975400,1,2,0.5,1.5\n1578061800,1,2,0.5,1.6\n", encoding="utf-8")
    r = provenance.file_record(raw)
    check("raw unix times become New York session dates", (r["first_date"], r["last_date"]) == ("2020-01-02", "2020-01-03"), r)

    # a FRED file: header observation_date, a '.' marker row and a trailing blank row are not counted
    dff = rates / "DFF.csv"
    dff.write_text("observation_date,DFF\n2020-01-01,1.55\n2020-01-02,.\n2020-01-03,1.56\n2020-01-04,\n", encoding="utf-8")
    f = provenance.file_record(dff)
    check("FRED rows skip '.' and blank values", f["rows"] == 2, f)
    check("FRED last date is the last row WITH a value", (f["first_date"], f["last_date"]) == ("2020-01-01", "2020-01-03"), f)

    old = tmp / "DTB3.csv"
    old.write_text("DATE,DTB3\n1954-01-04,1.2\n1954-01-05,1.3\n", encoding="utf-8")
    check("older FRED header 'DATE' works", provenance.file_record(old)["last_date"] == "1954-01-05")

    # a payout table from reference/: the date column is ex_date, not column 0 (the ticker)
    pay = tmp / "etf_distributions.csv"
    pay.write_text("ticker,ex_date,amount_per_share\nSPY,2024-06-21,1.75\nSPY,2024-09-20,1.74\n", encoding="utf-8")
    p = provenance.file_record(pay)
    check("an ex_date column is read as the date column", (p["rows"], p["first_date"], p["last_date"]) == (2, "2024-06-21", "2024-09-20"), p)

    empty = tmp / "empty.csv"
    empty.write_text("", encoding="utf-8")
    raises("an empty file is refused", lambda: provenance.file_record(empty), "empty file")

    m = provenance.manifest([clean, dff])
    check("manifest keeps the order given", [x["file"] for x in m] == ["SP_SPX_daily.csv", "DFF.csv"], m)

    # inputs_manifest resolves like the loaders do
    (rates / "DTB3.csv").write_text("observation_date,DTB3\n2020-01-02,1.5\n", encoding="utf-8")
    inp = provenance.inputs_manifest(["SP:SPX", "NASDAQ:NDX"], ["DFF", "DTB3"], data_dir=prices, rates_dir=rates)
    names = [x["file"] for x in inp["files"]]
    check("inputs_manifest names files by the loader's rule (':' -> '_', '_daily.csv', '<NAME>.csv')",
          names == ["SP_SPX_daily.csv", "NASDAQ_NDX_daily.csv", "DFF.csv", "DTB3.csv"], names)
    check("inputs_manifest folders are never absolute paths",
          not any(Path(inp[k].replace("<external>/", "")).is_absolute() for k in ("data_dir", "rates_dir"))
          and ":" not in inp["data_dir"] and "\\" not in inp["data_dir"] + inp["rates_dir"], inp)
    check("a folder outside the repository shows as <external>/<name>", inp["data_dir"] == "<external>/prices"
          and inp["rates_dir"] == "<external>/rates", inp)

    # rates folder follows the loader: default is <data_dir>/rates, the environment variable wins
    old_env = os.environ.pop(loader.ENV_RATES, None)
    try:
        (prices / "rates").mkdir()
        (prices / "rates" / "DFF.csv").write_text("observation_date,DFF\n2021-01-04,0.09\n", encoding="utf-8")
        d = provenance.inputs_manifest([], ["DFF"], data_dir=prices)
        check("without rates_dir the file is <data_dir>/rates/<NAME>.csv", d["files"][0]["first_date"] == "2021-01-04", d)
        os.environ[loader.ENV_RATES] = str(rates)
        d = provenance.inputs_manifest([], ["DFF"], data_dir=prices)
        check("$CALENDAR_LETF_RATES wins, as in loader.rates_path", d["files"][0]["first_date"] == "2020-01-01", d)
    finally:
        os.environ.pop(loader.ENV_RATES, None)
        if old_env is not None:
            os.environ[loader.ENV_RATES] = old_env

    raises("a missing input file is named in the error",
           lambda: provenance.inputs_manifest(["SP:SPXTR"], [], data_dir=prices, rates_dir=rates), "SP_SPXTR_daily.csv")

    lines = provenance.banner_lines(inp)
    check("banner has a header line and one line per file", len(lines) == 1 + 4, lines)
    check("banner shows rows, dates and the first 12 hash characters",
          "3 rows" in lines[1] and "2020-01-02 to 2020-01-06" in lines[1] and inp["files"][0]["sha256"][:12] in lines[1], lines[1])
    check("banner accepts a plain list of records", len(provenance.banner_lines(m)) == 3)
    check("banner holds no absolute path", all(str(tmp) not in x for x in lines))

# the repository's default folder is shown as plain 'data'
check("the repository data folder shows as 'data'", provenance._relative_name(provenance.REPO / "data") == "data")
check("a nested repository folder shows relative with '/'", provenance._relative_name(provenance.REPO / "data" / "rates") == "data/rates")

# ---- code fingerprint: which code produced a result ----
with tempfile.TemporaryDirectory() as tmp:
    pkg = Path(tmp) / "pkg"
    (pkg / "sub").mkdir(parents=True)
    (pkg / "a.py").write_bytes(b"x = 1\n")
    (pkg / "b.py").write_bytes(b"y = 2\n")
    (pkg / "sub" / "c.py").write_bytes(b"z = 3\n")
    (pkg / "notes.txt").write_bytes(b"not code\n")
    fp = provenance.code_fingerprint(package_dir=pkg)
    check("code fingerprint counts the .py files, sub-folders included, and no other files; no script by default",
          fp["files"] == 3 and fp["script"] is None and len(fp["sha256"]) == 64, fp)
    (pkg / "a.py").write_bytes(b"x = 1\r\n")
    check("CRLF and LF versions of the same source give the same fingerprint (git may convert line endings)",
          provenance.code_fingerprint(package_dir=pkg)["sha256"] == fp["sha256"])
    (pkg / "a.py").write_bytes(b"x = 2\n")
    check("one changed character in one package file changes the fingerprint", provenance.code_fingerprint(package_dir=pkg)["sha256"] != fp["sha256"])
    (pkg / "a.py").write_bytes(b"x = 1\n")
    (pkg / "sub" / "c.py").write_bytes(b"z = 4\n")
    check("a change in a sub-folder file changes the fingerprint too", provenance.code_fingerprint(package_dir=pkg)["sha256"] != fp["sha256"])
    (pkg / "sub" / "c.py").write_bytes(b"z = 3\n")
    check("restoring the bytes restores the fingerprint", provenance.code_fingerprint(package_dir=pkg)["sha256"] == fp["sha256"])
    script = Path(tmp) / "run_x.py"
    script.write_bytes(b"print(1)\n")
    fs = provenance.code_fingerprint(script, package_dir=pkg)
    check("the producing script enters the fingerprint by name and content", fs["script"] == "run_x.py" and fs["sha256"] != fp["sha256"], fs)
    script.write_bytes(b"print(2)\n")
    check("a changed script changes the fingerprint", provenance.code_fingerprint(script, package_dir=pkg)["sha256"] != fs["sha256"])

# ---- stale renders: every results JSON in the tree was produced by the code now in the tree ----
# A results file carries meta.code = code_fingerprint(<its script>) from the run that wrote it. If the package or the script
# changed since, the fingerprint recomputed here differs and the check fails with the script to re-run. (A green suite over a
# stale render is how this project lost a grade on 2026-10-24.)
import json  # noqa: E402

RESULTS, SCRIPTS = provenance.REPO / "results", provenance.REPO / "scripts"
_current = {}
_json_files = sorted(RESULTS.glob("*.json"))
check("stale-render check: results/*.json files are present to check", len(_json_files) >= 1, len(_json_files))
for _path in _json_files:
    _meta = json.loads(_path.read_text(encoding="utf-8")).get("meta") or {}
    _code = _meta.get("code") or {}
    _script_name = _code.get("script")
    if not _script_name or not _code.get("sha256"):
        check(f"{_path.name}: carries meta.code (script name and fingerprint); if not, re-run its script", False, f"meta.code = {_code!r}")
        continue
    _script = SCRIPTS / _script_name
    if not _script.exists():
        check(f"{_path.name}: its producing script scripts/{_script_name} exists", False, "missing")
        continue
    if _script_name not in _current:
        _current[_script_name] = provenance.code_fingerprint(_script)
    check(f"{_path.name}: rendered by the code now in the tree (package + scripts/{_script_name}); a mismatch is a stale render: re-run py scripts\\{_script_name}",
          _current[_script_name]["sha256"] == _code["sha256"], f"file {_code['sha256'][:12]} vs tree {_current[_script_name]['sha256'][:12]}")

# ---- stale inputs (R4 review): a file that SHIPS in the repository (reference/) must still be the file each result read.
# Price and rate files are not compared: a stranger's own export always differs from the author's, and the README tells
# them to expect a green suite. (The GFC second route compares them where they match; tests/test_gfc_oracle.py.)
def _inputs_of(doc):
    return (doc.get("meta") or {}).get("inputs") or (doc.get("provenance") or {}).get("inputs") or {}


def _reference_mismatches(inputs, repo):
    """[(file, reason)] for every reference record whose file is missing or whose sha256 differs now."""
    out = []
    for rec in list(inputs.get("reference_files", [])) + list(inputs.get("reference_json", [])):
        f = Path(repo) / "reference" / rec["file"]
        if not f.exists():
            out.append((rec["file"], "missing"))
        elif provenance.sha256_of(f) != rec["sha256"]:
            out.append((rec["file"], "sha256 differs"))
    return out


for _path in _json_files:
    _doc = json.loads(_path.read_text(encoding="utf-8"))
    _inp = _inputs_of(_doc)
    _script = ((_doc.get("meta") or {}).get("code") or {}).get("script", "the study")
    _bad = _reference_mismatches(_inp, provenance.REPO)
    check(f"{_path.name}: every reference/ file it read is unchanged (a mismatch is a stale result: re-run py scripts\\{_script})",
          not _bad, _bad)
    if any(r["file"] == "SP_SPX_daily.csv" for r in _inp.get("files", [])) and _path.name != "validate_live.json":
        check(f"{_path.name}: an S&P result names the Shiller yield file it read in its manifest",
              any(r["file"] == "shiller_sp500_monthly.csv" for r in _inp.get("reference_files", [])), _inp.get("reference_files"))
    # B7b: a Nasdaq-100 total return reads QQQ's income table for 1999-2006 (validate_live reads XNDX only as a fund benchmark)
    if any(r["file"] == "NASDAQ_XNDX_daily.csv" for r in _inp.get("files", [])) and _path.name != "validate_live.json":
        check(f"{_path.name}: a Nasdaq-100 result names the QQQ income file it read in its manifest",
              any(r["file"] == "qqq_income_ratios.csv" for r in _inp.get("reference_files", [])), _inp.get("reference_files"))
with tempfile.TemporaryDirectory() as _tmp:
    (Path(_tmp) / "reference").mkdir()
    (Path(_tmp) / "reference" / "t.csv").write_text("month,y\n2000-01,1\n", encoding="utf-8")
    _good = {"reference_files": [provenance.file_record(Path(_tmp) / "reference" / "t.csv")]}
    _wrong = {"reference_files": [dict(_good["reference_files"][0], sha256="0" * 64)]}
    check("stale inputs, planted: an unchanged reference file passes, a changed hash and a missing file are named",
          _reference_mismatches(_good, _tmp) == [] and _reference_mismatches(_wrong, _tmp) == [("t.csv", "sha256 differs")]
          and _reference_mismatches({"reference_json": [{"file": "gone.json", "sha256": "x"}]}, _tmp) == [("gone.json", "missing")])

# ---- strict JSON (R4 review): no results file may hold a bare NaN / Infinity, which strict JSON readers reject ----
import datetime as _dt  # noqa: E402

import numpy as _np  # noqa: E402
import pandas as _pd  # noqa: E402


def _no_constant(name):
    raise ValueError(f"non-standard JSON constant {name}")


for _path in _json_files:
    try:
        json.loads(_path.read_text(encoding="utf-8"), parse_constant=_no_constant)
        _ok = True
    except ValueError as _err:
        _ok = str(_err)
    check(f"{_path.name}: strict JSON (no bare NaN / Infinity)", _ok is True, _ok)
_js = provenance.json_safe({"a": float("nan"), "b": _np.int64(3), "c": [_np.float64(1.5), float("inf")], 4: _np.bool_(True),
                            "d": _pd.Timestamp("2000-01-03 12:00"), "e": _dt.date(2026, 1, 2), "f": "x", "g": None})
check("json_safe: NaN and infinity to null, numpy scalars to Python, dates to ISO text, keys to strings",
      _js == {"a": None, "b": 3, "c": [1.5, None], "4": True, "d": "2000-01-03", "e": "2026-01-02", "f": "x", "g": None}
      and type(_js["b"]) is int and type(_js["4"]) is bool, _js)
raises("json_safe: a value with no JSON form raises (no silent string)", lambda: provenance.json_safe({"x": object()}), "no JSON form")

# ---- the coverage simulation reads the passive study's per-start gaps: its raw-input hashes must match the files now in
# results/raw, and its seed-0 bootstrap bounds must equal the bounds the passive study published (same function, same seed)
_cov_path, _cvd_path = RESULTS / "coverage_sim.json", RESULTS / "calendar_vs_daily.json"
if _cov_path.exists() and _cvd_path.exists():
    _cov = json.loads(_cov_path.read_text(encoding="utf-8"))
    _cvd = json.loads(_cvd_path.read_text(encoding="utf-8"))
    _raw = {r["file"]: r["sha256"] for r in (_cov.get("meta") or {}).get("raw_inputs", [])}
    check("coverage_sim.json names the raw gap files it read (results/raw/multi_start_*_fixed.csv)", len(_raw) == 2, sorted(_raw))
    for _name, _sha in _raw.items():
        _p = RESULTS / "raw" / _name
        if not _p.exists():
            print(f"skip: results/raw/{_name} is absent (the per-start gaps are not shipped; run scripts/run_calendar_vs_daily.py to make them), so its hash is not checked")
            continue
        check(f"coverage_sim.json: {_name} in results/raw is the file it read (sha256); a mismatch means the passive study ran again: re-run py scripts\\run_coverage_sim.py",
              provenance.sha256_of(_p) == _sha, _sha[:12])
    _rows = {(r["world"], r["product"], r["horizon_years"]): r for r in _cov.get("bb_seed_spread", [])}
    check("coverage_sim.json: a seed-spread row for every (world, product, horizon) of the passive study", len(_rows) == 24, len(_rows))
    _bad = []
    for (_w, _p_, _h), _r in _rows.items():
        _pub = next((x for x in _cvd["worlds"][_w]["multi_start"]["fixed"] if x["product"] == _p_ and x["horizon_years"] == _h), None)
        if _pub is None or any(abs(_r[f"seed0_{k}"] - _pub[v]) > 1e-15 for k, v in (("mean_lo", "bb_lo"), ("mean_hi", "bb_hi"), ("median_lo", "bb_median_lo"), ("median_hi", "bb_median_hi"))):
            _bad.append((_w, _p_, _h))
    check("coverage_sim.json: seed 0 of every seed-spread row reproduces the published block-bootstrap bounds to 1e-15 (the published value is the seed-0 draw)", not _bad, _bad[:4])
else:
    print("skip: coverage_sim.json or calendar_vs_daily.json absent; the raw-input and seed-0 checks are not run")
