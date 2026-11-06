"""The GFC oracle entry: $10,000 bought at the close of the lowest index close of the 2007-2009 crash (a HINDSIGHT entry
nobody could know on the day), held to the last date common to every price input.

    py scripts\\run_gfc_oracle.py        (from calendar_letf/, with CALENDAR_LETF_DATA / _RATES set)

What it does, in order (the engine is calendar_letf/study.py, bottoms.py and kernel.py; nothing here re-implements it):
  1. per index (S&P 500, Nasdaq-100): the oracle low = the lowest close of the PRICE index from GFC_FROM to GFC_TO;
  2. the end = the last date that the index, the real 2x fund and the real 3x fund all have;
  3. from that low to that end: every calendar product (MODELED; its exposure on the entry day comes from the kernel,
     and its early resets inside the hold are counted), its daily 2x twin (MODELED, same costs), the 3x daily model at
     the filed UPRO / TQQQ terms, the real 2x fund (SSO / QLD, PRICE ONLY) and the 1x total-return index; both cost
     encodings for the 2x products, and each modeled end value divided by the real 2x fund's;
  4. the real 3x funds launched after the low, so a second table starts at each launch close and sets the real fund
     next to its own model (a check of the model, not a result);
  5. sensitivities: the entry moved by ENTRY_SHIFTS sessions around the low (calendar end value / twin end value), and
     each index from the OTHER index's low date;
  6. results/gfc_oracle.json and results/gfc_oracle.md.
One path from one hindsight date: no interval exists for it; it is an illustration, not a statistic. Not investment advice.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from calendar_letf import bottoms as B  # noqa: E402
from calendar_letf import costs, loader, products, provenance, study  # noqa: E402

OUT = ROOT / "results"
CAPTION = ("Data: TradingView (via local export), FRED. The calendar funds, daily twins and 3x rows are models; the SSO, QLD, "
           "UPRO and TQQQ rows are real funds' market prices, price only. Not investment advice.")
START_DOLLARS = 10_000.0
GFC_FROM, GFC_TO = "2007-01-01", "2009-12-31"     # the window searched for the crash low (a definition, ASSUMED)
ENTRY_SHIFTS = tuple(range(-400, 22))              # every session from 400 before (-) to 21 after (+) the low
ENCODINGS = ("fixed", "rate")
NAMES = {"SPX": "S&P 500", "NDX": "Nasdaq-100"}
REAL_2X = {"SPX": ("AMEX:SSO", "SSO"), "NDX": ("AMEX:QLD", "QLD")}
REAL_3X = {"SPX": ("AMEX:UPRO", "UPRO"), "NDX": ("NASDAQ:TQQQ", "TQQQ")}
INDEX_ROW = "INDEX_1X"
REAL_BASIS = "price only, distributions NOT reinvested (the export holds prices only), so the real funds' total return is higher"


# ---------------------------------------------------------------- the two date rules

def oracle_low(price, start=GFC_FROM, end=GFC_TO):
    """Row of the lowest close of `price` (a Series on a DatetimeIndex) from `start` to `end`, both inclusive.
    A tie keeps the first such day. Raises if the window holds no rows."""
    inside = np.flatnonzero((price.index >= pd.Timestamp(start)) & (price.index <= pd.Timestamp(end)))
    if not len(inside):
        raise ValueError(f"oracle_low: no rows from {start} to {end}")
    return int(inside[np.argmin(price.to_numpy(dtype=np.float64)[inside])])


def fall_from_window_high(price, row, start=GFC_FROM):
    """The close at `row` against the highest close from `start` to `row` (the fall into the low), as a fraction."""
    seg = price.to_numpy(dtype=np.float64)[np.flatnonzero(price.index >= pd.Timestamp(start))[0]:row + 1]
    return float(seg[-1] / seg.max() - 1.0)


def common_end(*indexes):
    """The last date that every DatetimeIndex in `indexes` holds: the earliest of their last dates, which must itself
    be a row of every index (otherwise one series would end on a date the others skip, and it raises)."""
    end = min(ix[-1] for ix in indexes)
    for ix in indexes:
        if end not in ix:
            raise ValueError(f"common_end: {end.date()} is not a row of every series")
    return end


def exact_row(index, d):
    """Row of date `d` in `index`; raises if the date is absent (no silent nearest-date fill)."""
    d = pd.Timestamp(d)
    if d not in index:
        raise ValueError(f"{d.date()} is not a row of the series ({index[0].date()} to {index[-1].date()})")
    return int(index.get_loc(d))


# ---------------------------------------------------------------- one table

def numbers(level, dates, s, e):
    """$10,000 at row s -> row e, with the return, CAGR and max drawdown of bottoms.window_numbers."""
    wn = B.window_numbers(level, dates, s, e)
    if wn is None:
        raise ValueError(f"numbers: the level on {dates[s].date()} is not positive (a terminated series); no return exists")
    return dict(dollars=START_DOLLARS * float(level[e]) / float(level[s]), ret=wn["ret"], cagr=wn["cagr"], max_dd=wn["maxdd"])


def early_resets(nav, d0, d1):
    """The early resets of a calendar NAV (its kernel attrs) after the entry close d0 and on or before d1."""
    return [str(pd.Timestamp(d).date()) for d in nav.attrs["early_resets"] if d0 < pd.Timestamp(d) <= d1]


def entry_rows(w, ev, real2, s, e):
    """Every comparator from the close of world row s to world row e (see the module docstring, step 3)."""
    d0, d1 = w.dates[s], w.dates[e]
    rs, re_ = exact_row(real2.index, d0), exact_row(real2.index, d1)
    real = numbers(real2.to_numpy(), real2.index, rs, re_)
    rows = []
    for en in ENCODINGS:
        enc = study.ALL_ENCODINGS[en]
        for sp in w.specs:
            nav = w.nav(sp.name, enc)
            er = early_resets(nav, d0, d1)
            x = numbers(nav.to_numpy(), w.dates, s, e)
            rows.append(dict(series=sp.name, kind="MODELED calendar", reset=sp.reset, encoding=en, leverage=float(ev.leverage(sp, enc, s)),
                             early_resets=len(er), first_early_reset=(er[0] if er else None),
                             vs_real_2x=x["dollars"] / real["dollars"], **x))
            tw = w.twin_name(sp.name)
            x = numbers(w.nav(tw, enc).to_numpy(), w.dates, s, e)
            rows.append(dict(series=tw, kind="MODELED 2x daily twin (same costs)", reset="daily", encoding=en, leverage=2.0,
                             vs_real_2x=x["dollars"] / real["dollars"], **x))
    m3 = ev.model_3x
    rows.append(dict(series=m3.name, kind="MODEL 3x daily (filed terms)", reset="daily", encoding="filed", leverage=float(m3.L),
                     **numbers(ev.nav3, w.dates, s, e)))
    rows.append(dict(series=real2.name, kind="REAL 2x fund (price only)", reset="daily", encoding="price", leverage=None, **real))
    rows.append(dict(series=INDEX_ROW, kind="1x total-return index", reset="none", encoding="tr", leverage=1.0,
                     **numbers(w.u_arr, w.dates, s, e)))
    return rows


def launch_rows(w, ev, real2, real3, e):
    """From the real 3x fund's first close to world row e: the real fund, its model, the real 2x fund and the index."""
    first = real3.index[0]
    s = exact_row(w.dates, first)
    d1 = w.dates[e]
    m3 = ev.model_3x
    rows = [dict(series=real3.name, kind="REAL 3x fund (price only)", encoding="price",
                 **numbers(real3.to_numpy(), real3.index, 0, exact_row(real3.index, d1))),
            dict(series=m3.name, kind="MODEL 3x daily (filed terms)", encoding="filed", **numbers(ev.nav3, w.dates, s, e)),
            dict(series=real2.name, kind="REAL 2x fund (price only)", encoding="price",
                 **numbers(real2.to_numpy(), real2.index, exact_row(real2.index, first), exact_row(real2.index, d1))),
            dict(series=INDEX_ROW, kind="1x total-return index", encoding="tr", **numbers(w.u_arr, w.dates, s, e))]
    return dict(fund=real3.name, date=str(first.date()), years=float((d1 - first).days / 365.25), rows=rows)


def shift_rows(w, s, e, shifts=ENTRY_SHIFTS):
    """For each calendar product, encoding and entry shift k (sessions from the low row s): the calendar fund's end value
    divided by its twin's, both bought at the close of row s + k and held to row e. Raises if s + k leaves 0..e-1
    (a negative row would silently wrap to the end of the series)."""
    bad = [k for k in shifts if not 0 <= s + k < e]
    if bad:
        raise ValueError(f"shift_rows: shifts {bad} leave the rows 0..{e - 1}")
    rows = []
    for en in ENCODINGS:
        enc = study.ALL_ENCODINGS[en]
        for sp in w.specs:
            fund, twin = w.nav(sp.name, enc).to_numpy(), w.nav(w.twin_name(sp.name), enc).to_numpy()
            for k in shifts:
                s2 = s + k
                rows.append(dict(series=sp.name, encoding=en, shift=int(k), date=str(w.dates[s2].date()),
                                 lead=float((fund[e] / fund[s2]) / (twin[e] / twin[s2]))))
    return rows


def shift_summary(rows):
    """What the results publish from the shift grid: per product and encoding, the shift range, the lowest and highest
    lead with their shifts, and the shifts where the lead is below 1. The full grid stays unpublished: one lead per
    session is a daily series, and its steps give back the index's daily moves (data/README, licensing)."""
    out = []
    for series_, en in dict.fromkeys((r["series"], r["encoding"]) for r in rows):
        rs = [r for r in rows if r["series"] == series_ and r["encoding"] == en]
        lo, hi = min(rs, key=lambda r: r["lead"]), max(rs, key=lambda r: r["lead"])
        out.append(dict(series=series_, encoding=en, shift_first=min(r["shift"] for r in rs), shift_last=max(r["shift"] for r in rs),
                        n_shifts=len(rs), lead_min=lo["lead"], lead_min_shift=lo["shift"], lead_max=hi["lead"], lead_max_shift=hi["shift"],
                        below_one=[r["shift"] for r in rs if r["lead"] < 1]))
    return out


# ---------------------------------------------------------------- rendering

def money(x):
    return f"${x:,.0f}"


def pct(x, d=1):
    return f"{x:+.{d}%}"


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def by(rows, series, encoding=None):
    hits = [r for r in rows if r["series"] == series and (encoding is None or r["encoding"] == encoding)]
    if len(hits) != 1:
        raise ValueError(f"{len(hits)} rows for {series}/{encoding}")
    return hits[0]


def entry_md(w, rows, real2_name, m3_name):
    head = ["product", "kind", "leverage at entry", "$10,000 became (fixed)", "CAGR (fixed)", "worst fall after entry (fixed)",
            "early resets", "$10,000 became (rate)", f"end value / {real2_name} (fixed / rate)"]
    out = []
    for sp in w.specs:
        f, r = by(rows, sp.name, "fixed"), by(rows, sp.name, "rate")
        er = f"{f['early_resets']} (first {f['first_early_reset']})" if f["early_resets"] else "0"
        out.append([f"{sp.name} ({sp.reset})", "MODELED calendar" + (" (live design)" if sp.kind == "LIVE" else ""),
                    f"{f['leverage']:.2f}x", money(f["dollars"]), pct(f["cagr"]), pct(f["max_dd"], 0), er, money(r["dollars"]),
                    f"{f['vs_real_2x']:.2f} / {r['vs_real_2x']:.2f}"])
        tf, tr = by(rows, w.twin_name(sp.name), "fixed"), by(rows, w.twin_name(sp.name), "rate")
        out.append(["its 2x daily twin", "MODELED, same costs", "2.00x", money(tf["dollars"]), pct(tf["cagr"]), pct(tf["max_dd"], 0), "",
                    money(tr["dollars"]), f"{tf['vs_real_2x']:.2f} / {tr['vs_real_2x']:.2f}"])
    for name, kind, levtxt in ((m3_name, "MODEL, filed terms", "3.00x"), (real2_name, "REAL, price only", "2x daily"),
                               (INDEX_ROW, "1x total-return index", "1.00x")):
        x = by(rows, name)
        out.append([name if name != INDEX_ROW else "1x index", kind, levtxt, money(x["dollars"]), pct(x["cagr"]), pct(x["max_dd"], 0),
                    "", "", ""])
    return md_table(head, out)


def launch_md(L):
    head = ["series", "kind", "$10,000 became", "CAGR", "worst fall"]
    return md_table(head, [[r["series"] if r["series"] != INDEX_ROW else "1x index", r["kind"], money(r["dollars"]), pct(r["cagr"]),
                            pct(r["max_dd"], 0)] for r in L["rows"]])


def ranges_text(ks):
    """Sorted integer shifts as runs, e.g. [-5, -4, -3, 7] -> '-5 to -3, +7'; 'none' when empty."""
    if not ks:
        return "none"
    ks = sorted(ks)
    runs, start, prev = [], ks[0], ks[0]
    for k in ks[1:] + [None]:
        if k is not None and k == prev + 1:
            prev = k
            continue
        runs.append(f"{start:+d}" if start == prev else f"{start:+d} to {prev:+d}")
        if k is not None:
            start = prev = k
    return ", ".join(runs)


def shift_md(w, summary):
    """One row per calendar product: the lowest and highest lead over the shift range, and the shifts below 1."""
    shifts = ranges_text
    head = ["product", "lowest lead (shift)", "highest lead (shift)", "shifts below 1 (fixed)", "shifts below 1 (rate)"]
    out = []
    for sp in w.specs:
        f, r = by(summary, sp.name, "fixed"), by(summary, sp.name, "rate")
        out.append([f"{sp.name} ({sp.reset})", f"{f['lead_min']:.3f} ({f['lead_min_shift']:+d})", f"{f['lead_max']:.3f} ({f['lead_max_shift']:+d})",
                    shifts(f["below_one"]), shifts(r["below_one"])])
    return md_table(head, out)


def drawdown_ranges(R):
    """(deepest, shallowest) worst fall after the headline entry over every 2x row, and over the 3x model rows."""
    dd2, dd3 = [], []
    for W in R["worlds"].values():
        for r in W["rows"]:
            if r["series"] == INDEX_ROW:
                continue
            (dd3 if r["kind"].startswith("MODEL 3x") else dd2).append(r["max_dd"])
    return (min(dd2), max(dd2)), (min(dd3), max(dd3))


def shift_losers(R):
    """[(index, product, [shifts])]: the calendar products whose end value falls below their twin's (lead < 1, fixed
    encoding) at one or more entry shifts, read from the published shift summary."""
    return [(name, r["series"], r["below_one"]) for name, W in R["worlds"].items() for r in W["shift"]
            if r["encoding"] == "fixed" and r["below_one"]]


def twin_vs_real_range(R):
    """(min, max) of the daily twins' end value / the real 2x fund's, over both indexes and both encodings."""
    v = [r["vs_real_2x"] for W in R["worlds"].values() for r in W["rows"] if r["kind"].startswith("MODELED 2x daily twin")]
    return min(v), max(v)


def render(R, banner, worlds):
    lines = ["# The GFC oracle entry: $10,000 at the crash low, held to the end of the data", "",
             "A HINDSIGHT entry: the close of the lowest index close from " + GFC_FROM + " to " + GFC_TO + ". Nobody knew that "
             "day on the day. One path from one date, so no interval exists; read it as an illustration, not a statistic. "
             "The calendar products and the daily twins are MODELED (no calendar fund existed before 2024-08-30); the real "
             f"2x and 3x funds are {REAL_BASIS}. Not investment advice.", "", "## Inputs, costs and conventions", "", "```text",
             *banner, "```", ""]
    for name, W in R["worlds"].items():
        w = worlds[name]
        lines += [f"## {NAMES[name]}", "",
                  f"Entry: the close of {W['entry']['date']}, after a fall of {abs(W['entry']['fall']):.1%} from the highest close "
                  f"since {GFC_FROM}. End: {W['end']}, the last date common to the index, {W['real_2x']} and {W['real_3x']}; "
                  f"{W['years']:.1f} years. Leverage at entry: the calendar fund's exposure after the entry close. It is above 2x "
                  "while the index stays below the level of the fund's last reset and below 2x once the index climbs above it; an "
                  "early reset sets it back to 2x.", "",
                  entry_md(w, W["rows"], W["real_2x"], W["model_3x"]),
                  f"**{W['real_3x']} launched after the low.** From its first close ({W['launch']['date']}, "
                  f"{W['launch']['years']:.1f} years), the real fund next to its model (a check of the model):", "",
                  launch_md(W["launch"]),
                  f"**Sensitivity: the entry moved around the low**, every session from {min(ENTRY_SHIFTS):+d} to "
                  f"{max(ENTRY_SHIFTS):+d}. The lead is the calendar fund's end value divided by its daily twin's, both bought at "
                  "the close of that session and held to the end; above 1 the calendar fund ends ahead. The table gives the "
                  "summary only: one lead per session would be a daily series (data/README, licensing).", "",
                  shift_md(w, W["shift"]),
                  f"**Sensitivity: the other index's low date ({W['alt']['date']}), fixed encoding.**", ""]
        lines.append(md_table(["series", "kind", "$10,000 became", "CAGR"],
                              [[r["series"] if r["series"] != INDEX_ROW else "1x index", r["kind"], money(r["dollars"]), pct(r["cagr"])]
                               for r in W["alt"]["rows"] if r["encoding"] in ("fixed", "filed", "price", "tr")]))
    dd2, dd3 = drawdown_ranges(R)
    tv = twin_vs_real_range(R)
    losers = shift_losers(R)
    loser_txt = ("; ".join(f"{p} ({NAMES[n]}) at shifts {ranges_text(ks)}"
                           + (" (the run reaches the grid's edge, so it may go on further)" if min(ks) == min(ENTRY_SHIFTS) else "")
                           for n, p, ks in losers) if losers else "none")
    lines += ["## How to read it", "",
              "- A calendar fund bought at the low partway through its period holds more than 2x until the index regains the "
              "level of its last reset (see the leverage note above), so its start into the rebound carries extra exposure. "
              "This study does not split each lead into its causes.",
              f"- Each daily twin is a daily-reset fund like the real 2x fund, with the costs fitted to the live calendar funds "
              f"(ASSUMPTIONS section 2, two ASSUMED encodings). The twins end at {tv[0]:.2f} to {tv[1]:.2f} times the real 2x "
              "fund's value (price only), so whether a calendar design ends above the real fund depends on the assumed costs: "
              "see the last column of each table.",
              f"- Calendar products whose end value falls below their twin's at some entry shift (fixed encoding): {loser_txt}.",
              f"- After the entry every 2x path fell {pct(dd2[1], 0)} to {pct(dd2[0], 0)} and the 3x models {pct(dd3[1], 0)} to "
              f"{pct(dd3[0], 0)} from a high; the dollar figures assume a holder kept the position through those falls.",
              "- An entry three months early or late moves a 3-year result far more than the reset design does "
              "(results/from_bottoms.md, section D), so the exact low matters more than the design.", "",
              CAPTION, ""]
    return "\n".join(lines)


def banner_lines(worlds, inputs):
    """Inputs (hashed), conventions, every product's costs, both cost encodings and the 3x model terms."""
    out = provenance.banner_lines(inputs) + [ln for w_ in worlds.values() for ln in study.conventions_lines(w_)]
    for w in worlds.values():
        out += products.banner(*w.specs, *w.twins.values(),
                               overrides="spread_per_nav and the rate multiplier come from the cost encodings below").splitlines()
        m3 = products.MODELS_3X[products.MODEL_3X_FOR[w.name]]
        out.append(f"3x MODEL {m3.name} (filed terms, plain reference rate, daily reset): {costs.describe(m3.costs)}")
        out += [f"  WARNING: {wn}" for wn in m3.costs.warnings()]
    out += [f"COST ENCODING {en} (ASSUMED): {study.ALL_ENCODINGS[en].describe()}" for en in ENCODINGS]
    out += [f"Real funds: {REAL_BASIS}.", products.MODELED_NOTE]
    return out


# ---------------------------------------------------------------- main

def main():
    worlds, provs, evs, reals, prices = {}, {}, {}, {}, {}
    for name in NAMES:
        # the base-case trigger (R2 step 5); v0.1.1 fixes the data end at the v0.1.0 end (study.V010_END)
        end = study.V010_END[name]
        w, pv = study.build_world(name, intraday_trigger=True, trigger_basis="etf", end=end)
        worlds[name], provs[name] = w, pv
        prices[name] = study.TRIGGER_FOR[name]().loc[:end]                         # the low is a low of the INDEX price
        real2 = loader.close(REAL_2X[name][0]).loc[:end].rename(REAL_2X[name][1])
        real3 = loader.close(REAL_3X[name][0]).loc[:end].rename(REAL_3X[name][1])
        reals[name] = (real2, real3)
        evs[name] = B.Evaluator(w, products.MODELS_3X[products.MODEL_3X_FOR[name]], real3, price=prices[name])
    lows = {name: oracle_low(prices[name]) for name in NAMES}
    inputs = study.inputs_for(worlds, provs, extra_symbols=[s for n in NAMES for s in (REAL_2X[n][0], REAL_3X[n][0])])
    banner = banner_lines(worlds, inputs)
    R = dict(meta=dict(title="The GFC oracle entry", run_date=str(pd.Timestamp.today().date()), code=provenance.code_fingerprint(__file__),
                       gfc_window=[GFC_FROM, GFC_TO], entry_shifts=list(ENTRY_SHIFTS), start_dollars=START_DOLLARS,
                       encodings=list(ENCODINGS), real_basis=REAL_BASIS, caption=CAPTION, inputs=inputs, banner=banner), worlds={})
    for name, w in worlds.items():
        ev, (real2, real3) = evs[name], reals[name]
        end = common_end(w.dates, real2.index, real3.index)
        e = exact_row(w.dates, end)
        s = lows[name]
        other = next(n for n in NAMES if n != name)
        s_alt = exact_row(w.dates, worlds[other].dates[lows[other]])
        R["worlds"][name] = dict(
            entry=dict(date=str(w.dates[s].date()), close=float(prices[name].iloc[s]), fall=fall_from_window_high(prices[name], s)),
            end=str(end.date()), years=float((end - w.dates[s]).days / 365.25), real_2x=real2.name, real_3x=real3.name,
            model_3x=ev.model_3x.name, rows=entry_rows(w, ev, real2, s, e), launch=launch_rows(w, ev, real2, real3, e),
            shift=shift_summary(shift_rows(w, s, e)), alt=dict(date=str(w.dates[s_alt].date()), rows=entry_rows(w, ev, real2, s_alt, e)))
    OUT.mkdir(exist_ok=True)
    (OUT / "gfc_oracle.json").write_text(json.dumps(provenance.json_safe(R), indent=1, allow_nan=False), encoding="utf-8", newline="\n")
    (OUT / "gfc_oracle.md").write_text(render(R, banner, worlds), encoding="utf-8", newline="\n")
    for name, W in R["worlds"].items():
        print(f"{name}: entry {W['entry']['date']} ({pct(W['entry']['fall'])}), end {W['end']}, {W['years']:.1f} years")
        for r in W["rows"]:
            if r["encoding"] in ("fixed", "filed", "price", "tr"):
                extra = f"  lev {r['leverage']:.2f}x  early {r['early_resets']} {r['first_early_reset'] or ''}" if "early_resets" in r else ""
                print(f"  {r['series']:<16} {r['kind']:<36} {money(r['dollars']):>13} {pct(r['cagr'])}/yr{extra}")
        for n_, p_, ks in shift_losers(dict(worlds={name: W})):
            print(f"  {p_} ends below its twin (fixed) at shifts {ranges_text(ks)}")
    print("wrote results/gfc_oracle.json and results/gfc_oracle.md")


if __name__ == "__main__":
    main()
