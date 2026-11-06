"""Input provenance: which exact files a result came from.

Plain-English summary
  * `file_record(path)` describes one CSV: its SHA-256 fingerprint, size in bytes, number of data rows, and the first
    and last date. Two people with the same fingerprint hold the same bytes, so their results can be compared.
  * `inputs_manifest(symbols, rate_names)` finds the same files the loaders open (it calls the loaders' own folder
    and file-name helpers, so the rules live in one place) and describes each one.
  * `banner_lines(manifest)` turns the manifest into a few text lines for the top of a results table.

  * `code_fingerprint(script)` describes which CODE produced a result: one SHA-256 over the package's .py files and
    the producing script. Every results JSON carries it under meta.code; tests/test_provenance.py recomputes it from
    the current tree, so a results file rendered by older code (a "stale render") fails the suite until the script is
    re-run. Line endings are normalized before hashing, so a checkout with Windows or Unix line endings agrees.

Privacy rule: a manifest never holds an absolute path. Files appear by name only, and the two folders appear
relative to the repository (or as "<external>/<folder name>" when they sit elsewhere, as on a machine that points
CALENDAR_LETF_DATA at a shared price library).

The module reads files with the standard library only (csv, hashlib); it uses pandas only through the loader's
date parser, so a date in a file is read by the same strict rules the loaders use.
"""
import csv
import hashlib
from pathlib import Path

from . import loader

REPO = Path(__file__).resolve().parent.parent
PACKAGE = Path(__file__).resolve().parent                            # calendar_letf/calendar_letf: the code that computes
DATE_COLUMNS = ("date", "time", "observation_date", "ex_date", "first_day")   # ex_date: the payout tables; first_day: qqq_income_ratios.csv
TEXT_SUFFIXES = (".csv", ".json", ".jsonl", ".md", ".txt", ".py", ".toml", ".cff")  # hashed with CR LF folded to LF (see sha256_of)
CHUNK = 1 << 20


def json_safe(o):
    """A nested result made safe for strict JSON: numpy numbers to Python numbers, NaN and infinity to null, dates to
    ISO text. Write it with json.dumps(..., allow_nan=False), so a value this misses raises instead of becoming a
    bare NaN (which strict JSON readers reject) or a silent string."""
    import datetime as _dt
    import math

    if isinstance(o, dict):
        return {str(k): json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [json_safe(v) for v in o]
    if hasattr(o, "dtype") and hasattr(o, "item") and getattr(o, "ndim", 0) == 0:      # a numpy scalar
        o = o.item()
    if isinstance(o, bool) or o is None or isinstance(o, str):
        return o
    if isinstance(o, int):
        return o
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, (_dt.datetime, _dt.date)):                                       # pandas Timestamp included
        return o.date().isoformat() if isinstance(o, _dt.datetime) else o.isoformat()
    raise TypeError(f"json_safe: no JSON form for {type(o).__name__}: {o!r}")


def sha256_of(path):
    """SHA-256 of the file's bytes, as 64 hex characters. A text file (TEXT_SUFFIXES) is hashed with its Windows line
    endings (CR LF) turned into LF first, so the hash does not depend on how a checkout writes line endings: git stores
    and checks out LF (.gitattributes), while a Windows script may write CR LF (re-grade of 2026-11-06, finding T1).
    Any other file is hashed as its bytes."""
    if Path(path).suffix.lower() in TEXT_SUFFIXES:
        return hashlib.sha256(_normalized_bytes(path)).hexdigest()
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def byte_count(path):
    """The file's size in bytes, counted like sha256_of: a text file with CR LF folded to LF."""
    if Path(path).suffix.lower() in TEXT_SUFFIXES:
        return len(_normalized_bytes(path))
    return Path(path).stat().st_size


def _normalized_bytes(path):
    """The file's bytes with Windows line endings (CR LF) turned into Unix ones (LF), so the same source hashes the
    same on either system (git may convert line endings on checkout)."""
    return Path(path).read_bytes().replace(b"\r\n", b"\n")


def code_fingerprint(script=None, package_dir=None):
    """Which code produced a result: {"script": name or None, "files": count, "sha256": hex}.

    The hash runs over every .py file in the package folder (sorted by name; name and normalized bytes of each),
    then over the producing `script` (name and normalized bytes) when one is given. Two trees with the same
    fingerprint hold the same code; a results file whose meta.code differs from `code_fingerprint(<its script>)`
    on the current tree was rendered by other code and must be re-run.
    """
    folder = Path(package_dir) if package_dir is not None else PACKAGE
    files = sorted((p for p in folder.rglob("*.py") if p.is_file()), key=lambda p: p.relative_to(folder).as_posix())
    h = hashlib.sha256()
    for p in files:                                   # sub-packages (strategies/) included, by repository-relative name
        h.update(p.relative_to(folder).as_posix().encode("utf-8") + b"\0" + _normalized_bytes(p) + b"\0")
    name = None
    if script is not None:
        script = Path(script)
        name = script.name
        h.update(b"script:" + name.encode("utf-8") + b"\0" + _normalized_bytes(script) + b"\0")
    return {"script": name, "files": len(files), "sha256": h.hexdigest()}


def _date_text(value):
    """ISO date text for one date field, using the loader's strict parser; None if it cannot be read."""
    ts, _note = loader._parse_one(value, "America/New_York")
    return None if ts is None or ts != ts else str(ts.date())     # NaT != NaT


def _columns(header):
    """(index of the date column, index of the value column) from a header row.

    Date column: a column named date, time, observation_date, ex_date or first_day, else column 0.
    Value column: 'close' if present (price files), else column 1 (FRED files), else the date column itself.
    """
    low = [c.strip().lower() for c in header]
    d_idx = next((i for i, c in enumerate(low) if c in DATE_COLUMNS), 0)
    if "close" in low:
        v_idx = low.index("close")
    else:
        v_idx = 1 if len(low) > 1 else d_idx
    return d_idx, v_idx


def file_record(path):
    """Describe one CSV file: dict(file, sha256, bytes, rows, first_date, last_date).

    `rows` counts data rows that carry a date and a value (a blank value or FRED's "." marker is not a row, the same
    rows the loaders drop). `file` is the file name only, never the folder.
    """
    path = Path(path)
    rows, first, last = 0, None, None
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            raise ValueError(f"{path.name}: empty file")
        d_idx, v_idx = _columns(header)
        need = max(d_idx, v_idx)
        for row in reader:
            if len(row) <= need:
                continue
            date, val = row[d_idx].strip(), row[v_idx].strip()
            if not date or val in ("", ".") or val.lower() == "nan":
                continue
            rows += 1
            if first is None:
                first = date
            last = date
    return {"file": path.name, "sha256": sha256_of(path), "bytes": byte_count(path), "rows": rows,
            "first_date": None if first is None else _date_text(first),
            "last_date": None if last is None else _date_text(last)}


def manifest(paths):
    """A list of file records, one per path, in the order given."""
    return [file_record(p) for p in paths]


def _relative_name(folder):
    """The folder as repository-relative text with '/', or '<external>/<name>' if it lies outside the repository."""
    folder = Path(folder).resolve()
    try:
        return folder.relative_to(REPO).as_posix() or "."
    except ValueError:
        return f"<external>/{folder.name}"


def inputs_manifest(symbols, rate_names, data_dir=None, rates_dir=None):
    """The files a study reads, resolved exactly as `loader.load_prices` and `loader.load_fred` resolve them.

    symbols      e.g. ["SP:SPX", "NASDAQ:NDX"]       -> <data folder>/SP_SPX_daily.csv, ...
    rate_names   e.g. ["DFF", "DTB3"]                -> <rates folder>/DFF.csv, ...
    data_dir     as in the loaders (argument, else $CALENDAR_LETF_DATA, else <repo>/data)
    rates_dir    a folder for the rate files; default is what `loader.rates_path(data_dir)` gives
    Returns {"data_dir": text, "rates_dir": text, "files": [records]}. A missing file raises FileNotFoundError.
    """
    price_folder = loader.data_path(data_dir)
    rate_folder = Path(rates_dir) if rates_dir is not None else loader.rates_path(data_dir)
    paths = []
    for symbol in symbols:
        paths.append(price_folder / loader._file_name(symbol))
    for name in rate_names:
        paths.append(rate_folder / f"{name}.csv")
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError("input files not found: " + ", ".join(missing) + " (see data/README.md)")
    return {"data_dir": _relative_name(price_folder), "rates_dir": _relative_name(rate_folder),
            "files": manifest(paths)}


def banner_lines(manifest_or_records):
    """Short text lines for a results banner: the two folders, then one line per file.

    Accepts the dict from `inputs_manifest` or a plain list of records.
    """
    if isinstance(manifest_or_records, dict):
        records = manifest_or_records["files"]
        head = (f"Inputs: {len(records)} files; prices from {manifest_or_records['data_dir']}, "
                f"rates from {manifest_or_records['rates_dir']}")
    else:
        records = list(manifest_or_records)
        head = f"Inputs: {len(records)} files"
    lines = [head]
    for r in records:
        lines.append(f"  {r['file']}: {r['rows']} rows, {r['first_date']} to {r['last_date']}, "
                     f"sha256 {r['sha256'][:12]}")
    return lines
