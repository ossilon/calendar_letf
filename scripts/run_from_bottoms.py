"""B13: drawdown-conditioned entries (entries after major market drawdowns) for the calendar-reset 2x funds.

    py scripts\\run_from_bottoms.py        (from calendar_letf/, with CALENDAR_LETF_DATA / _RATES set)

What it does, in order (the math is in calendar_letf/bottoms.py):
  1. per index (S&P 500, Nasdaq-100): find every drawdown deeper than 19% in the PRICE index and compare with the brief's list;
  2. entries: A hindsight bottoms (major = the brief's list, shallow = the other 19-30% troughs), B rule entries (first close at least
     X below the all-time high, once per fall), C Guppy-confirmed entries after each A / B entry (daily and weekly slow ribbon);
  3. for every entry x calendar product x cost encoding: the fund's effective leverage on the entry day, and at 1 / 3 / 5 / 10 years the
     return, CAGR, max drawdown and early resets of the fund, its daily 2x twin, the 3x daily model (UPRO_MODEL / TQQQ_MODEL at the
     filed terms), the real UPRO / TQQQ price series (price only), the buy-once margin position and the 1x index;
  4. entry-timing sensitivity (+/- 1, 3, 6 months) and the cost-assumption swing next to it;
  5. charts and results/from_bottoms.md / .json (raw per-entry tables in results/raw/, git-ignored).
Every fund series is synthetic or a MODEL; the real UPRO / TQQQ are price-only overlays. Not investment advice.

Base case (R2 step 5): the early-reset trigger watches the ETF's daily low (SPY from 1993-01-29, QQQ from 1999-03-10; the index
price before), and the entry-day leverage is read from the kernel run with that same trigger and low. The ENTRIES (drawdowns,
falls from the high, Guppy signals) stay defined on the index price. One labeled sensitivity repeats the major-bottom entries
with the v1 trigger (index price, close only).
"""
import json
import sys
import time
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from calendar_letf import bottoms as B  # noqa: E402
from calendar_letf import costs, kernel, loader, products, provenance, study  # noqa: E402

OUT = ROOT / "results"
RAW = OUT / "raw"
CAPTION = ("Data: TradingView (via local export), FRED. The fund series are models; the UPRO and TQQQ columns are the real "
           "funds' market prices, price only. Not investment advice.")
ENC = study.ALL_ENCODINGS
BASE = study.BASE_ENCODING                                  # "fixed": the encoding the tables show; "rate" sits beside it
NAMES = {"SPX": "S&P 500", "NDX": "Nasdaq-100"}
LIVE = {"SPX": "SPYQ", "NDX": "MQQQ"}
REAL = {"SPX": ("AMEX:UPRO", "UPRO"), "NDX": ("NASDAQ:TQQQ", "TQQQ")}
SERIES_LABEL = {"fund": "fund", "twin": "2x daily twin", "m3x": "3x model", "real": "real 3x (price only)", "margin": "margin 2x", "idx": "1x index"}
COLORS = ["#00d1ff", "#ff9f1c", "#2ec4b6", "#ff4d6d", "#b388ff", "#ffd60a", "#80ed99", "#f78fb3", "#9bb1ff"]
GRAY = "#bbbbbb"


# ---------------------------------------------------------------- formatting
def pc(x, d=1):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.{d}f}%"


def sret(x):
    """A total return as a signed percentage ('+205%', '-34.2%'); big numbers with thousands separators."""
    if x is None or not np.isfinite(x):
        return "n/a"
    return f"{x * 100:+,.0f}%" if abs(x) >= 1 else f"{x * 100:+.1f}%"


def lev(x):
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.2f}x"


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def clean(o):
    """Make a nested result JSON-safe: numpy numbers to Python, NaN to null, Timestamps to text."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return str(o.date())
    return o


def med(xs):
    v = np.array([np.nan if x is None else x for x in xs], dtype=float)
    v = v[np.isfinite(v)]
    return float(np.median(v)) if len(v) else float("nan")


def cell(res, h, key, field="ret"):
    """res = one Evaluator.evaluate output; the number at horizon h for a series, or None."""
    x = res["horizons"][h][key]
    return None if x is None else x[field]


def rc(res, h, key):
    """'+205% (+45.2%/yr)' for horizons over one year, plain return at one year; 'n/a' if missing."""
    x = res["horizons"][h][key]
    if x is None:
        return "n/a"
    return sret(x["ret"]) if h == 1 else f"{sret(x['ret'])} ({sret(x['cagr'])}/yr)"


# ---------------------------------------------------------------- entries
class Entry(dict):
    pass


def build_entries(world, ev):
    """All entries for one underlying: A hindsight (major, shallow), B rule. Returns (entries, info for the report)."""
    n = world.name
    price = ev.price
    dates = world.dates
    cummax = np.maximum.accumulate(price)
    tr = B.drawdown_troughs(dates, price)
    major, shallow, cmp_rows, unmatched = B.tier_troughs(tr, B.HINDSIGHT_LIST[n], B.LIST_EXTRA_YEARS[n])
    entries = []

    def add(eid, family, row, **kw):
        entries.append(Entry(id=eid, family=family, row=int(row), date=str(dates[row].date()),
                             fall_from_ath=float(1.0 - price[row] / cummax[row]), **kw))

    for t in major:
        add(f"H {t['trough_date']}", "hindsight_major", t["trough_row"], depth=t["depth"], peak_date=t["peak_date"], level=t["level"],
            listed_only=False, note="")
    for r in cmp_rows:                                       # listed dates the data do not show as a trough: keep them as entries
        if r["found_date"] is None:
            row = world.row_on_or_before(r["listed"])
            near = [t for t in tr if abs((pd.Timestamp(t["trough_date"]) - pd.Timestamp(r["listed"])).days) <= 400]
            peak_row = near[0]["peak_row"] if near else int(np.argmax(price[:row + 1]))        # same peak as the nearest trough, else the ATH
            add(f"H {dates[row].date()}", "hindsight_major", row, depth=float(price[row] / price[peak_row] - 1.0), peak_date=str(dates[peak_row].date()), level=None,
                listed_only=True,
                note="listed in the brief, NOT the data's trough" + (f" (nearest trough in the data: {near[0]['trough_date']})" if near else ""))
    for t in shallow:
        add(f"S {t['trough_date']}", "hindsight_shallow", t["trough_row"], depth=t["depth"], peak_date=t["peak_date"], level=t["level"],
            listed_only=False, note="")
    lv, worst = B.level_entries(dates, price, B.LEVELS[n])
    for x, lst in lv.items():
        for e in lst:
            add(f"R {int(x * 100)}% {e['date']}", "rule", e["row"], level_x=x, ath_date=e["ath_date"], fall=e["fall"])
    order = {"hindsight_major": 0, "hindsight_shallow": 1, "rule": 2}
    entries.sort(key=lambda e: (order[e["family"]], e.get("level_x", 0), e["row"]))
    info = dict(troughs=tr, compare=cmp_rows, unmatched=unmatched, deepest=worst, levels=lv,
                n_major=len(major), n_shallow=len(shallow))
    return entries, info


def add_guppy(world, ev, book, parents):
    """Guppy-confirmed entries after each parent entry. Returns (child entries, per-parent confirmation records)."""
    dates = world.dates
    nrows = len(dates)
    kids, recs = [], []
    for p in parents:
        s = p["row"]
        end = B.horizon_row(dates, s, B.CONFIRM_YEARS)
        complete = end is not None
        last = end if complete else nrows - 1
        conf = book.confirmations(s, last)
        rec = dict(parent=p["id"], state_at_entry=book.state_on(s), window_end=str(dates[last].date()), window_complete=complete, signals={})
        for key in B.CONFIRM_KEYS:
            c = conf[key]
            if c is None:
                rec["signals"][key] = None
                continue
            f = B.fill_row(c["signal_row"], nrows)
            if f is None:
                rec["signals"][key] = dict(c, fill_row=None, fill_date=None)
                continue
            kid = Entry(id=f"G {key} after {p['id']}", family="guppy", row=int(f), date=str(dates[f].date()), parent=p["id"], key=key,
                        signal_date=c["signal_date"], days_to_signal=int(c["signal_row"] - s), days_waited=int(f - s),
                        index_move=float(ev.price[f] / ev.price[s] - 1.0), fall_from_ath=float(1.0 - ev.price[f] / np.maximum.accumulate(ev.price)[f]))
            kids.append(kid)
            rec["signals"][key] = dict(c, fill_row=int(f), fill_date=kid["date"], days_waited=kid["days_waited"], index_move=kid["index_move"])
        recs.append(rec)
    return kids, recs


def evaluate_entries(ev, entries, specs, encs):
    """entry['res'][encoding][product] = Evaluator.evaluate output, for every entry."""
    for e in entries:
        e["res"] = {en: {sp.name: ev.evaluate(e["row"], sp, ENC[en]) for sp in specs} for en in encs}


# ---------------------------------------------------------------- timing sensitivity
def timing_study(world, ev, major, specs, encs):
    """Per hindsight bottom and offset: the 1- and 3-year total returns of the fund, twin, 3x model and index; and the cost
    swing (range of the fund's 3-year return over all six cost assumptions of F5) at the bottom itself."""
    out = []
    for e in major:
        item = dict(id=e["id"], date=e["date"], offsets={}, cost_swing={})
        trows = B.timing_rows(world, e["row"])
        for sp in specs:
            for en in encs:
                rows_ = []
                for k, r in trows:
                    q = ev.quick(r, sp, ENC[en], (1, 3))
                    rows_.append(dict(months=k, date=str(world.dates[r].date()), row=r, **{f"{h}y": q[h] for h in (1, 3)}))
                item["offsets"][f"{sp.name}|{en}"] = rows_
            rets = {en: cell(ev.evaluate(e["row"], sp, ENC[en], (3,)), 3, "fund") for en in B.COST_ENCODINGS}
            v = [x for x in rets.values() if x is not None]
            item["cost_swing"][sp.name] = dict(by_encoding=rets, range=(max(v) - min(v)) if v else None)
        out.append(item)
    return out


def trigger_sensitivity(ev_v1, major, specs):
    """The major-bottom entries again with the v1 trigger (index price, close only): per bottom and calendar product, the
    entry leverage and the 3-year return of the fund under the base case (from the entries' own results) and under the v1
    trigger (`ev_v1`, an Evaluator on a world built with the v1 trigger; fixed encoding)."""
    out = []
    for e in major:
        item = dict(date=e["date"], listed_only=bool(e.get("listed_only")), products={})
        for sp in specs:
            b = e["res"][BASE][sp.name]
            v = ev_v1.evaluate(e["row"], sp, ENC[BASE], (3,))
            item["products"][sp.name] = dict(base_leverage=b["leverage"], v1_leverage=v["leverage"], base_3y=cell(b, 3, "fund"),
                                             v1_3y=cell(v, 3, "fund"), base_early_resets_3y=cell(b, 3, "fund", "early_resets"),
                                             v1_early_resets_3y=cell(v, 3, "fund", "early_resets"))
        out.append(item)
    return out


def trigger_sensitivity_md(specs, rows):
    head = ["bottom"] + [f"{sp.name} entry leverage (base / v1)" for sp in specs] + [f"{sp.name} 3y return (base / v1)" for sp in specs]
    body = []
    for r in rows:
        p = r["products"]
        body.append([r["date"] + (" *" if r["listed_only"] else "")] + [f"{lev(p[sp.name]['base_leverage'])} / {lev(p[sp.name]['v1_leverage'])}" for sp in specs]
                    + [f"{sret(p[sp.name]['base_3y'])} / {sret(p[sp.name]['v1_3y'])}" for sp in specs])
    return md_table(head, body)


# ---------------------------------------------------------------- charts
def style_axes(ax):
    ax.set_facecolor("black")
    ax.tick_params(colors="white")
    for s in ax.spines.values():
        s.set_color("#444444")
    ax.grid(color="#222222", lw=0.5)


def plot_overlay(world, ev, live, major, path):
    enc = ENC[BASE]
    fund = world.nav(live.name, enc).to_numpy()
    twin = world.nav(world.twin_name(live.name), enc).to_numpy()
    fig, ax = plt.subplots(figsize=(13, 7.5), facecolor="black")
    style_axes(ax)
    for i, e in enumerate(major):
        s = e["row"]
        end = B.horizon_row(world.dates, s, 3)
        if end is None:
            end = len(world.dates) - 1
        x = np.arange(end - s + 1) / 252.0
        c = COLORS[i % len(COLORS)]
        ax.plot(x, fund[s:end + 1] / fund[s], color=c, lw=1.9)
        ax.plot(x, twin[s:end + 1] / twin[s], color=c, lw=1.2, ls="--")
        ax.plot(x, ev.nav3[s:end + 1] / ev.nav3[s], color=c, lw=1.4, ls=":")
    ax.set_yscale("log")
    lo, hi = ax.get_ylim()
    ticks = [t for t in (0.1, 0.2, 0.3, 0.5, 1, 2, 3, 5, 10, 20, 30, 50) if lo <= t <= hi]
    ax.set_yticks(ticks)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
    ax.set_xlabel("years after the bottom (252 trading days each)", color="white")
    ax.set_ylabel("growth of 1 (log scale)", color="white")
    ax.axhline(1.0, color="#555555", lw=0.8)
    cols = [Line2D([0], [0], color=COLORS[i % len(COLORS)], lw=2.5, label=f"bottom {e['date']}" + (" (listed, not the data's low)" if e.get("listed_only") else ""))
            for i, e in enumerate(major)]
    sty = [Line2D([0], [0], color=GRAY, lw=1.9, label=f"{live.name} (calendar-reset, modeled)"),
           Line2D([0], [0], color=GRAY, lw=1.2, ls="--", label="its 2x daily twin"),
           Line2D([0], [0], color=GRAY, lw=1.4, ls=":", label=f"3x daily model ({ev.model_3x.name})")]
    ax.legend(handles=cols + sty, facecolor="black", labelcolor="white", edgecolor="#444444", fontsize=9, loc="upper left")
    ax.set_title(f"{NAMES[world.name]}: growth of 1 over the 3 years after each major bottom  [MODELED / MODEL series]\n"
                 f"encoding: {ENC[BASE].label}; early-reset mode: level; total-return underlying", color="white", fontsize=11, loc="left")
    fig.text(0.01, 0.005, CAPTION, fontsize=8, color="#999999")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path, dpi=120, facecolor="black")
    plt.close(fig)


def plot_leverage(worlds, evs, targets, path, ndays=90):
    """2 x 2: rows = index, columns = 2009 and 2020 bottoms. Effective leverage of each calendar fund after each close of the
    first `ndays` trading days after the bottom, beside the daily twin's constant 2 and the 3x model's constant 3."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 8.5), facecolor="black", sharey=False)
    enc = ENC[BASE]
    for r, name in enumerate(("SPX", "NDX")):
        w, ev = worlds[name], evs[name]
        for c, (label, date) in enumerate(targets[name]):
            ax = axes[r][c]
            style_axes(ax)
            s = w.row_on_or_before(date)
            for i, sp in enumerate(w.specs):
                path_ = ev.leverage_path(sp, enc, s, ndays)
                ax.step(np.arange(len(path_)), path_, where="post", color=COLORS[i], lw=1.7, label=f"{sp.name} ({sp.reset})")
            ax.axhline(2.0, color=GRAY, lw=1.1, ls="--", label="2x daily twin: always 2")
            ax.axhline(3.0, color="#ffffff", lw=1.4, ls=":", label=f"{ev.model_3x.name}: always 3")
            ax.set_title(f"{NAMES[name]}: first {ndays} trading days after the {w.dates[s].date()} close", color="white", fontsize=10, loc="left")
            ax.set_xlabel("trading days after the entry close", color="white")
            ax.set_ylabel("effective leverage (exposure / NAV)", color="white")
            if r == 0 and c == 0:
                ax.legend(facecolor="black", labelcolor="white", edgecolor="#444444", fontsize=8, loc="upper right")
    fig.suptitle("Effective leverage of the calendar-reset funds after a crash: it drifts away from 2 as the index moves and falls back to 2 only "
                 "at each reset  [MODEL series]", color="white", fontsize=11, x=0.01, ha="left")
    fig.text(0.01, 0.005, CAPTION, fontsize=8, color="#999999")
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    fig.savefig(path, dpi=120, facecolor="black")
    plt.close(fig)


# ---------------------------------------------------------------- raw tables
def raw_rows(entries, specs, en):
    rows = []
    for e in entries:
        for sp in specs:
            r = e["res"][en][sp.name]
            row = dict(entry=e["id"], family=e["family"], date=e["date"], parent=e.get("parent"), product=sp.name, encoding=en, leverage=r["leverage"])
            for h in B.HORIZONS_YEARS:
                for k in B.SERIES_KEYS:
                    for f in ("ret", "cagr", "maxdd"):
                        row[f"{k}_{h}y_{f}"] = cell(r, h, k, f)
                row[f"fund_{h}y_early_resets"] = cell(r, h, "fund", "early_resets")
            rows.append(row)
    return rows


# ---------------------------------------------------------------- markdown pieces
def hindsight_tables(name, world, live, major, ev, en):
    """One table per horizon for the live fund: entry leverage and the six series."""
    real_name = REAL[name][1]
    out = []
    for h in B.HORIZONS_YEARS:
        head = ["bottom", "fall", "entry leverage", f"{live.name}", "2x daily twin", f"{ev.model_3x.name} (3x)", f"{real_name} (price only)", "margin 2x (buy once)", "1x index (TR)"]
        rows = []
        for e in major:
            r = e["res"][en][live.name]
            rows.append([e["date"] + (" *" if e.get("listed_only") else ""), pc(e["depth"], 0), lev(r["leverage"]), rc(r, h, "fund"), rc(r, h, "twin"),
                         rc(r, h, "m3x"), rc(r, h, "real"), rc(r, h, "margin"), rc(r, h, "idx")])
        out.append(f"**{h}-year result after buying {live.name} at each bottom's close** (total return" + ("" if h == 1 else "; CAGR in brackets")
                   + f"; 'fall' = the drop into the bottom from its peak; n/a = the data end first, {real_name} did not exist yet, or its file ends earlier)\n")
        out.append(md_table(head, rows))
    return "\n".join(out)


DOLLAR_STEPS = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)       # calendar years after the bottom (0.5 = 6 months), the rule of every other table
START_DOLLARS = 10_000.0


def dollar_values(arr, dates, s):
    """$10,000 at row s -> its value at each DOLLAR_STEPS horizon (B.dollar_values: calendar-month rule, NaN past the data)."""
    return B.dollar_values(arr, dates, s, DOLLAR_STEPS, START_DOLLARS)


def dollar_matrix(world, ev, live, major):
    """What $10,000 bought at each bottom's close became at 0.5, 1, ..., 3 years, for the live calendar fund, its 2x
    daily twin, the 3x daily model and the 1x total-return index; plus key facts per bottom (entry leverage, 3-year CAGR,
    max drawdown inside the 3 years, early resets). Values are NAV ratios of the full-history runs x $10,000."""
    enc = ENC[BASE]
    series = {"fund": world.nav(live.name, enc).to_numpy(), "twin": world.nav(world.twin_name(live.name), enc).to_numpy(),
              "m3x": ev.nav3, "idx": world.u_arr}
    out = []
    for e in major:
        s = e["row"]
        r = e["res"][BASE][live.name]
        row = dict(date=e["date"], listed_only=bool(e.get("listed_only")), fall=float(e["depth"]), leverage=float(r["leverage"]))
        for key, arr in series.items():
            row[key] = dollar_values(arr, world.dates, s)
            row[f"{key}_cagr_3y"] = cell(r, 3, key, "cagr") if key != "idx" else cell(r, 3, "idx", "cagr")
            row[f"{key}_maxdd_3y"] = cell(r, 3, key, "maxdd") if key != "idx" else cell(r, 3, "idx", "maxdd")
        row["early_resets_3y"] = cell(r, 3, "fund", "early_resets")
        out.append(row)
    return out


def dollar_products(world, major):
    """The same $10,000 path for EVERY calendar product on the index (live and modeled), one block per product:
    entry leverage, values at the DOLLAR_STEPS, 3-year CAGR and max drawdown inside the 3 years, early resets."""
    enc = ENC[BASE]
    out = {}
    for sp in world.specs:
        arr = world.nav(sp.name, enc).to_numpy()
        rows = []
        for e in major:
            s = e["row"]
            r = e["res"][BASE][sp.name]
            vals = dollar_values(arr, world.dates, s)
            rows.append(dict(date=e["date"], listed_only=bool(e.get("listed_only")), leverage=float(r["leverage"]), values=vals,
                             cagr_3y=cell(r, 3, "fund", "cagr"), maxdd_3y=cell(r, 3, "fund", "maxdd"), early_resets_3y=cell(r, 3, "fund", "early_resets")))
        out[sp.name] = dict(kind=sp.kind, reset=sp.reset, rows=rows)
    return out


def dollar_products_md(world, per_product):
    head = ["bottom", "entry leverage"] + [f"{y:g}y" for y in DOLLAR_STEPS] + ["3y CAGR", "3y max DD", "early resets"]
    out = ["**Every calendar product on this index, $10,000 at each bottom's close** (fixed encoding; the daily twins differ "
           "from the live product's twin above only by fee, so they are not repeated). Products other than the live fund are "
           "MODELED designs (" + products.MODELED_NOTE + ").\n"]
    for sp in world.specs:
        d = per_product[sp.name]
        tag = "live product, modeled" if sp.kind == "LIVE" else "MODELED design"
        out.append(f"*{sp.name} ({sp.reset} reset; {tag})*\n")
        out.append(md_table(head, [[r["date"] + (" *" if r["listed_only"] else ""), lev(r["leverage"])] +
                                   [("n/a" if np.isnan(r["values"][f'{y:g}y']) else f"${r['values'][f'{y:g}y']:,.0f}") for y in DOLLAR_STEPS] +
                                   [pc(r["cagr_3y"]), pc(r["maxdd_3y"], 0), r["early_resets_3y"]] for r in d["rows"]]))
        med = [np.nanmedian([r["values"][f"{y:g}y"] for r in d["rows"]]) for y in DOLLAR_STEPS]
        out.append(md_table(["median"] + head[2:8], [[f"{sp.name}"] + [f"${v:,.0f}" for v in med]]))
    return "\n".join(out)


def dollar_md(name, live, ev, rows):
    """Markdown: one $10,000 matrix per series, then a key-facts table."""
    labels = {"fund": f"{live.name} (calendar-reset, modeled)", "twin": "2x daily twin", "m3x": f"{ev.model_3x.name} (3x daily model)",
              "idx": "1x index (total return)"}
    out = [f"**What $10,000 invested at each bottom's close became** (calendar years, the last close on or before the entry date plus 6 / 12 / ... / 36 months, as in every other table; "
           "fixed encoding; modeled series; n/a = the data end first).\n"]
    head = ["bottom"] + [f"{y:g}y" for y in DOLLAR_STEPS]
    for key, label in labels.items():
        out.append(f"*{label}*\n")
        out.append(md_table(head, [[r["date"] + (" *" if r["listed_only"] else "")] +
                                   [("n/a" if np.isnan(r[key][f'{y:g}y']) else f"${r[key][f'{y:g}y']:,.0f}") for y in DOLLAR_STEPS] for r in rows]))
    med = {key: [np.nanmedian([r[key][f"{y:g}y"] for r in rows]) for y in DOLLAR_STEPS] for key in labels}
    out.append("*Median across the bottoms*\n")
    out.append(md_table(["series"] + head[1:], [[labels[k]] + [f"${v:,.0f}" for v in med[k]] for k in labels]))
    out.append("**Key facts per bottom** (3-year CAGR and max drawdown inside the 3 years; CAGR is annualized, so +114% over 3 years is 28.9%/yr)\n")
    kf_head = ["bottom", "fall", "entry leverage", f"{live.name} CAGR / max DD", "twin CAGR / max DD", "3x CAGR / max DD", "1x CAGR / max DD", "early resets"]
    out.append(md_table(kf_head, [[r["date"] + (" *" if r["listed_only"] else ""), pc(r["fall"], 0), lev(r["leverage"]),
                                   f"{pc(r['fund_cagr_3y'])} / {pc(r['fund_maxdd_3y'], 0)}", f"{pc(r['twin_cagr_3y'])} / {pc(r['twin_maxdd_3y'], 0)}",
                                   f"{pc(r['m3x_cagr_3y'])} / {pc(r['m3x_maxdd_3y'], 0)}", f"{pc(r['idx_cagr_3y'])} / {pc(r['idx_maxdd_3y'], 0)}",
                                   r["early_resets_3y"]] for r in rows]))
    return "\n".join(out)


def risk_table(name, live, major, ev, en, h=3):
    head = ["bottom", f"{live.name} max DD", "twin max DD", "3x model max DD", "margin max DD", "1x max DD", f"early resets in {h}y"]
    rows = []
    for e in major:
        r = e["res"][en][live.name]
        rows.append([e["date"], pc(cell(r, h, "fund", "maxdd"), 0), pc(cell(r, h, "twin", "maxdd"), 0), pc(cell(r, h, "m3x", "maxdd"), 0),
                     pc(cell(r, h, "margin", "maxdd"), 0), pc(cell(r, h, "idx", "maxdd"), 0), cell(r, h, "fund", "early_resets")])
    return md_table(head, rows)


def all_products_table(world, entries, en, h, field="ret"):
    head = ["entry", "fall from ATH"] + [f"{sp.name} lev" for sp in world.specs] + [f"{sp.name} {h}y" for sp in world.specs] + [f"twin {h}y (of {world.specs[0].name})", f"1x {h}y"]
    rows = []
    for e in entries:
        rs = [e["res"][en][sp.name] for sp in world.specs]
        rows.append([e["date"], pc(e["fall_from_ath"], 0)] + [lev(r["leverage"]) for r in rs] + [sret(cell(r, h, "fund")) for r in rs]
                    + [sret(cell(rs[0], h, "twin")), sret(cell(rs[0], h, "idx"))])
    return md_table(head, rows)


def level_summary(name, world, live, ev, lv, deepest, entries, en):
    """Which levels triggered when, and the 1-/3-year outcome by level for the live fund."""
    rule = [e for e in entries if e["family"] == "rule"]
    lines = []
    never = [x for x in B.LEVELS[name] if not lv[x]]
    for x in B.LEVELS[name]:
        if not lv[x]:
            lines.append(f"- **{int(x * 100)}% never happened since {world.dates[0].date()}** (deepest fall {pc(deepest['fall'])}, "
                         f"{deepest['ath_date']} to {deepest['date']}).")
    srows = []
    for x in B.LEVELS[name]:
        es = [e for e in rule if e["level_x"] == x]
        rs = [e["res"][en][live.name] for e in es]
        if es:
            srows.append([f"{int(x * 100)}%", len(es), ", ".join(e["date"] for e in es), lev(med([r["leverage"] for r in rs])),
                          sret(med([cell(r, 1, "fund") for r in rs])), sret(med([cell(r, 3, "fund") for r in rs])), sret(med([cell(r, 3, "twin") for r in rs])),
                          sret(med([cell(r, 3, "m3x") for r in rs])), sret(med([cell(r, 3, "margin") for r in rs])), sret(med([cell(r, 3, "idx") for r in rs])),
                          f"{sum(1 for r in rs if (cell(r, 3, 'fund') or 0) > 0)} of {sum(1 for r in rs if cell(r, 3, 'fund') is not None)}"])
        else:
            srows.append([f"{int(x * 100)}%", 0, "never happened", "", "", "", "", "", "", "", ""])
    summ = md_table(["level", "episodes", "trigger dates", "median entry leverage", f"median {live.name} 1y", f"median {live.name} 3y", "median twin 3y",
                     "median 3x model 3y", "median margin 3y", "median 1x 3y", f"{live.name} 3y positive"], srows)
    detail_rows = []
    for x in B.LEVELS[name]:
        for e in [e for e in rule if e["level_x"] == x]:
            r = e["res"][en][live.name]
            detail_rows.append([f"{int(x * 100)}%", e["date"], e["ath_date"], pc(e["fall"], 1), lev(r["leverage"]), sret(cell(r, 1, "fund")),
                                sret(cell(r, 3, "fund")), sret(cell(r, 3, "twin")), sret(cell(r, 3, "m3x")), sret(cell(r, 3, "margin")), sret(cell(r, 3, "idx"))])
    detail = md_table(["level", "entry date", "prior high", "fall that day", "entry leverage", f"{live.name} 1y", f"{live.name} 3y", "twin 3y",
                       "3x model 3y", "margin 3y", "1x 3y"], detail_rows)
    return never, "\n".join(lines), summ, detail


def guppy_tables(name, live, entries_by_id, recs, parents_major, en):
    """Per major bottom: each confirmation as 'signal date (+days to fill, index move)'; and the summary over parents."""
    rows = []
    byparent = {r["parent"]: r for r in recs}
    for p in parents_major:
        rec = byparent[p["id"]]
        cells = []
        for key in B.CONFIRM_KEYS:
            c = rec["signals"][key]
            if c is None:
                cells.append("none within 2y" if rec["window_complete"] else "none yet (data end)")
            elif c.get("fill_date") is None:
                cells.append(f"{c['signal_date']} (no later close)")
            else:
                cells.append(f"{c['signal_date']} (+{c['days_waited']}d, {sret(c['index_move'])})")
        rows.append([p["date"], f"{rec['state_at_entry'][0]} / {rec['state_at_entry'][1]}"] + cells)
    per_bottom = md_table(["bottom", "ribbon at entry (daily / weekly)"] + [B.CONFIRM_LABELS[k] for k in B.CONFIRM_KEYS], rows)
    return per_bottom


def guppy_summary(world, live, entries, recs, en, group_name, parent_filter):
    """For each confirmation key over the parents in the group: possible, confirmed, median days waited, median index move,
    median 3-year fund return of the confirmed entry vs the parent's, share beating the parent (own 3-year window and same end date)."""
    byid = {e["id"]: e for e in entries}
    nav = world.nav(live.name, ENC[en]).to_numpy()
    rows = []
    for key in B.CONFIRM_KEYS:
        possible = confirmed = 0
        days, moves, kid3, par3, beat_own, n_own, beat_same, n_same, same_gap = [], [], [], [], 0, 0, 0, 0, []
        for rec in recs:
            p = byid[rec["parent"]]
            if not parent_filter(p):
                continue
            possible += 1
            sig = rec["signals"][key]
            if sig is None or sig.get("fill_row") is None:
                continue
            confirmed += 1
            days.append(sig["days_waited"])
            moves.append(sig["index_move"])
            kid = byid[f"G {key} after {p['id']}"]
            k3, p3 = cell(kid["res"][en][live.name], 3, "fund"), cell(p["res"][en][live.name], 3, "fund")
            if k3 is not None and p3 is not None:
                kid3.append(k3)
                par3.append(p3)
                n_own += 1
                beat_own += int(k3 > p3)
            end = B.horizon_row(world.dates, p["row"], 3)
            if end is not None and sig["fill_row"] < end:
                kr = nav[end] / nav[sig["fill_row"]] - 1.0
                pr = nav[end] / nav[p["row"]] - 1.0
                n_same += 1
                beat_same += int(kr > pr)
                same_gap.append(kr - pr)
        rows.append([B.CONFIRM_LABELS[key], possible, confirmed, f"{med(days):.0f}" if days else "n/a", sret(med(moves)) if moves else "n/a",
                     sret(med(kid3)) if kid3 else "n/a", sret(med(par3)) if par3 else "n/a", f"{beat_own} of {n_own}", f"{beat_same} of {n_same}",
                     sret(med(same_gap)) if same_gap else "n/a"])
    return md_table([f"confirmation ({group_name})", "entries", "confirmed in 2y", "median trading days waited (to the fill)", "median index move while waiting",
                     f"median {live.name} 3y return, confirmed entry", "median 3y return, parent entry", "confirmed beats parent (own 3y windows)",
                     "confirmed beats parent (same end date)", "median gap, same end date"], rows), rows


# ---------------------------------------------------------------- timing markdown
def timing_md(name, live, t_items, encs):
    res = []
    for sp_name in (live.name,):
        for en in encs:
            head = ["bottom", "series"] + [f"{k:+d}m" for k in B.TIMING_MONTHS]
            rows = []
            for it in t_items:
                offs = it["offsets"][f"{sp_name}|{en}"]
                for ser, lab in (("fund", sp_name), ("twin", "2x twin"), ("m3x", "3x model"), ("idx", "1x")):
                    rows.append([it["date"] if ser == "fund" else "", f"{lab} 3y"] + [sret(o["3y"][ser]) for o in offs])
                rows.append(["", f"{sp_name} 1y"] + [sret(o["1y"]["fund"]) for o in offs])
                rows.append(["", "entry date used"] + [o["date"][2:] for o in offs])
            res.append(f"**{sp_name}, encoding `{en}`: total return after buying at the month-end nearest to the bottom plus k months** (0m = the bottom close itself)\n")
            res.append(md_table(head, rows))
    return "\n".join(res)


def timing_summary(t_items, live_name, encs):
    """Headline numbers: the 3-year return change from being 3 months early / late, against the cost-assumption range."""
    rows, early_vs_cost = [], []
    for it in t_items:
        offs = {o["months"]: o for o in it["offsets"][f"{live_name}|{BASE}"]}
        base = offs[0]["3y"]["fund"]
        e3, l3 = offs[-3]["3y"]["fund"], offs[3]["3y"]["fund"]
        sw = it["cost_swing"][live_name]["range"]
        d_e = None if e3 is None or base is None else e3 - base
        d_l = None if l3 is None or base is None else l3 - base
        # compare in the same units: change in the 3-year total return, in percentage points of the starting capital
        rows.append([it["date"], sret(base), sret(e3), sret(l3), pc(None if d_e is None else d_e, 0), pc(None if d_l is None else d_l, 0),
                     pc(sw, 0), "yes" if (d_e is not None and sw is not None and abs(d_e) > sw) else ("no" if d_e is not None and sw is not None else "n/a")])
        if d_e is not None and sw is not None:
            early_vs_cost.append((abs(d_e), abs(d_l) if d_l is not None else np.nan, sw))
    md = md_table(["bottom", f"{live_name} 3y at the bottom", "3 months early (-3m)", "3 months late (+3m)", "change if early", "change if late",
                   "range over the 6 cost assumptions", "-3m change larger than cost range?"], rows)
    arr = np.array(early_vs_cost, dtype=float) if early_vs_cost else np.zeros((0, 3))
    stats = dict(n=int(len(arr)), median_abs_early=float(np.nanmedian(arr[:, 0])) if len(arr) else None,
                 median_abs_late=float(np.nanmedian(arr[:, 1])) if len(arr) else None, median_cost_range=float(np.nanmedian(arr[:, 2])) if len(arr) else None,
                 early_bigger_than_cost=int((arr[:, 0] > arr[:, 2]).sum()) if len(arr) else 0)
    return md, stats


# ---------------------------------------------------------------- the run
def main():
    wall0 = time.perf_counter()
    OUT.mkdir(exist_ok=True)
    RAW.mkdir(exist_ok=True)
    encs = ("fixed", "rate")
    R = dict(meta={}, worlds={})
    print("=" * 100 + "\nB13: entries from major bottoms (all fund series MODELED / MODEL; real UPRO / TQQQ are price-only overlays)")
    worlds, wprov, evs, books, idx_price = {}, {}, {}, {}, {}
    real_info = {}
    for name in ("SPX", "NDX"):
        # BASE CASE (R2 step 5): the trigger watches the ETF's daily low from the ETF's first bar, the index before.
        # v0.1.1: the data end is fixed at the v0.1.0 end (study.V010_END), so a library top-up moves nothing
        w, pv = study.build_world(name, intraday_trigger=True, trigger_basis="etf", end=study.V010_END[name])
        worlds[name], wprov[name] = w, pv
        idx_price[name] = study.TRIGGER_FOR[name]().loc[:study.V010_END[name]]   # the entries are defined on the INDEX price
        sym, rname = REAL[name]
        real = loader.close(sym).loc[:study.V010_END[name]]
        real_info[name] = dict(symbol=sym, name=rname, first=str(real.index[0].date()), last=str(real.index[-1].date()), rows=int(len(real)),
                               basis="price only, dividends NOT reinvested (distributions are not in the export)")
        evs[name] = B.Evaluator(w, products.MODELS_3X[products.MODEL_3X_FOR[name]], real, price=idx_price[name])
        books[name] = B.GuppyBook(w.dates, evs[name].price)
        print("\n" + pv["banner"])
        print(f"TRIGGER BASE CASE: {pv['trigger_text']}; entries and Guppy signals read the index price {pv['price_symbol']}.")
        print(f"rate: {pv['rate']}")
        print(products.banner(*w.specs, *w.twins.values(), overrides="spread_per_nav and the rate multiplier come from the cost encodings below"))
        print("3x MODEL (filed terms, plain reference rate, daily reset):")
        print("  " + costs.describe(products.MODELS_3X[products.MODEL_3X_FOR[name]].costs))
        for wn in products.MODELS_3X[products.MODEL_3X_FOR[name]].costs.warnings():
            print("  WARNING: " + wn)
        print(f"real overlay: {real_info[name]}")
    # Provenance: every price file the worlds read, plus the two real 3x funds loaded for the overlay.
    inputs = study.inputs_for(worlds, wprov, extra_symbols=[REAL[n][0] for n in REAL])
    banner = (provenance.banner_lines(inputs) + [ln for w_ in worlds.values() for ln in study.conventions_lines(w_)]
              + ["Entries (drawdowns, falls from the high, Guppy signals) read the INDEX price; the entry-day leverage reads the kernel "
                 "run with the base-case trigger and its daily low.", products.MODELED_NOTE])
    print("\nINPUTS AND CONVENTIONS:\n" + "\n".join(banner))
    print("\nCOST ENCODINGS (both ASSUMED; tables show `fixed`, `rate` sits beside it; the cost swing uses all six):")
    for en in B.COST_ENCODINGS:
        print("  " + ENC[en].describe())

    R["meta"] = dict(title="Entries from major market bottoms (B13)", run_date=str(pd.Timestamp.today().date()), base_encoding=BASE, encodings=list(encs),
                     code=provenance.code_fingerprint(__file__),
                     cost_swing_encodings=list(B.COST_ENCODINGS), horizons_years=list(B.HORIZONS_YEARS), timing_months=list(B.TIMING_MONTHS),
                     min_depth=B.MIN_DEPTH, hindsight_list={k: list(v) for k, v in B.HINDSIGHT_LIST.items()}, levels={k: list(v) for k, v in B.LEVELS.items()},
                     confirm_years=B.CONFIRM_YEARS, early_mode=study.BASE_MODE, caption=CAPTION, real_funds=real_info,
                     model_3x={k: dict(spread=v.costs.spread, turns=v.costs.turns, fee=v.costs.fee, fee_status=v.costs.fee_status,
                                       spread_status=v.costs.spread_status, turns_status=v.costs.turns_status, spread_source=v.costs.spread_source,
                                       fee_source=v.costs.fee_source) for k, v in products.MODELS_3X.items()},
                     underlyings={n: {k: v for k, v in wprov[n].items()} for n in wprov}, inputs=inputs, banner=banner,
                     trigger_base_case={n: wprov[n]["trigger_text"] for n in wprov})

    md_world = {}
    lev_checks = {}
    for name, w in worlds.items():
        t_w = time.perf_counter()
        ev, book = evs[name], books[name]
        live = products.PRODUCTS[LIVE[name]]
        entries, info = build_entries(w, ev)
        parents = list(entries)
        kids, recs = add_guppy(w, ev, book, parents)
        allentries = entries + kids
        evaluate_entries(ev, allentries, w.specs, encs)
        major = [e for e in entries if e["family"] == "hindsight_major"]
        shallow = [e for e in entries if e["family"] == "hindsight_shallow"]
        timing = timing_study(w, ev, major, w.specs, encs)
        # labeled sensitivity: the same major-bottom entries under the v1 trigger (index price, close only)
        w_v1, _ = study.build_world(name, end=study.V010_END[name])
        ev_v1 = B.Evaluator(w_v1, ev.model_3x, ev.real, price=idx_price[name])
        tsens = trigger_sensitivity(ev_v1, major, w.specs)

        # cross-check: the kernel-state leverage equals the NAV-ratio leverage wherever no early reset has happened since the last reset
        diffs = []
        for e in entries:
            for sp in w.specs:
                for en in encs:
                    fund = w.nav(sp.name, ENC[en])
                    r0 = ev.last_reset_row(sp, e["row"])
                    if e["row"] != r0 and not any(w.dates[r0] < pd.Timestamp(d) <= w.dates[e["row"]] for d in fund.attrs["early_resets"]):
                        diffs.append(abs(e["res"][en][sp.name]["leverage"] - B.effective_leverage_nav_ratio(w.u_arr, fund.to_numpy(), r0, e["row"], sp.L)))
        lev_checks[name] = dict(n=len(diffs), max_abs_diff=float(max(diffs)) if diffs else None)
        # cross-check: a margin position and the 3x model read from the shared run equal a direct run from the bottom date
        s0 = major[0]["row"] if major else entries[0]["row"]
        direct3 = kernel.run(ev.model_3x, w.u.iloc[s0:], w.rate.iloc[s0:])
        d3 = float(abs(direct3.iloc[-1] - ev.nav3[-1] / ev.nav3[s0]))
        print(f"{name}: entries {len(entries)} (+{len(kids)} Guppy-confirmed); leverage cross-check {lev_checks[name]}; "
              f"3x model: shared-run window vs direct run from {w.dates[s0].date()}, last-row difference {d3:.2e}")

        plot_overlay(w, ev, live, major, OUT / f"from_bottoms_{name}.png")
        pd.DataFrame(raw_rows(allentries, w.specs, "fixed") + raw_rows(allentries, w.specs, "rate")).to_csv(RAW / f"from_bottoms_{name}.csv", index=False)
        dollars = dollar_matrix(w, ev, live, major)
        dollars_products = dollar_products(w, major)

        # --- guppy summaries
        g_rows = {}
        gmd = {}
        for gname, flt in (("hindsight bottoms, major", lambda p: p["family"] == "hindsight_major"),
                           ("hindsight bottoms, shallow", lambda p: p["family"] == "hindsight_shallow"),
                           ("rule entries", lambda p: p["family"] == "rule")):
            gmd[gname], g_rows[gname] = guppy_summary(w, live, allentries, recs, BASE, gname, flt)

        md_world[name] = dict(entries=entries, kids=kids, recs=recs, major=major, shallow=shallow, info=info, timing=timing, gmd=gmd, grows=g_rows, live=live,
                              dollars=dollars, dollars_products=dollars_products, ev=ev, tsens=tsens)
        R["worlds"][name] = dict(
            dollars_10k=dollars, dollars_10k_all_products=dollars_products,
            troughs=info["troughs"], compare_with_list=info["compare"], unmatched_troughs=info["unmatched"], deepest_fall=info["deepest"],
            trigger_sensitivity_v1=tsens, level_entries=info["levels"], leverage_cross_check=lev_checks[name], real_fund=real_info[name], model_3x=products.MODEL_3X_FOR[name],
            entries=[{k: ({en: {live.name: v[en][live.name]} for en in v} if (k == "res" and e["family"] == "guppy") else v) for k, v in e.items()}
                     for e in allentries],
            guppy_records=recs, timing=timing, guppy_summary=g_rows)
        print(f"{name}: computed in {time.perf_counter() - t_w:.2f} s; kernel runs {w.kernel_runs} in {w.kernel_seconds:.2f} s")

    # --- leverage chart
    targets = {"SPX": [("2009", "2009-03-09"), ("2020", "2020-03-23")], "NDX": [("2009", "2009-03-09"), ("2020", "2020-03-20")]}
    plot_leverage(worlds, evs, targets, OUT / "from_bottoms_leverage.png")

    # ---------------------------------------------------------------- markdown
    md = []
    md.append("# Entries from major bottoms: what a calendar-reset 2x fund is after a crash (B13)\n")
    md.append(f"Run {R['meta']['run_date']}. Script `scripts/run_from_bottoms.py`, math in `calendar_letf/bottoms.py`; numbers in `from_bottoms.json`; per-entry tables in "
              "`results/raw/` (git-ignored). **Every fund series is synthetic or a model: SPYQ, MQQQ and QQQP are modeled, HYP_* are MODELED designs (" + products.MODELED_NOTE + "), the 3x series are MODELS of "
              "UPRO / TQQQ at their filed terms, and the real UPRO / TQQQ are price-only overlays. Research tooling, not investment advice.**\n")
    md.append("## Inputs and conventions\n")
    md.append("```text\n" + "\n".join(banner) + "\n```\n")
    md.append("## Headline numbers (all from this run; fixed encoding; live product = SPYQ on the S&P 500, MQQQ on the Nasdaq-100)\n")
    for name in ("SPX", "NDX"):
        d, live = md_world[name], md_world[name]["live"]
        maj = d["major"]
        rs = [e["res"][BASE][live.name] for e in maj]
        levs = [r["leverage"] for r in rs]
        f3, t3, m3, mg3, i3 = ([cell(r, 3, k) for r in rs] for k in ("fund", "twin", "m3x", "margin", "idx"))
        pairs = [(a, b) for a, b in zip(f3, t3) if a is not None and b is not None]
        pairs3 = [(a, b) for a, b in zip(f3, m3) if a is not None and b is not None]
        _, tstats = timing_summary(d["timing"], live.name, encs)
        d["timing_stats"] = tstats
        gm = d["grows"]["hindsight bottoms, major"]
        md.append(f"- **{NAMES[name]} ({live.name}), {len(maj)} major bottoms:** entry leverage {lev(min(levs))} to {lev(max(levs))} (median {lev(med(levs))}); twin exactly 2x, 3x model exactly 3x. "
                  f"Median 3-year total return: {live.name} {sret(med(f3))}, 2x twin {sret(med(t3))}, 3x model {sret(med(m3))}, margin 2x {sret(med(mg3))}, 1x index {sret(med(i3))}. "
                  f"The fund returned more than its twin at 3 years in {sum(a > b for a, b in pairs)} of {len(pairs)} bottoms and less than the 3x model in {sum(a < b for a, b in pairs3)} of {len(pairs3)}.")
        md.append(f"  Timing: median change in the {live.name} 3-year return from entering 3 months early {pc(tstats['median_abs_early'], 0)} (late {pc(tstats['median_abs_late'], 0)}), "
                  f"against a median range of {pc(tstats['median_cost_range'], 0)} over the six cost assumptions; early beat the cost range in {tstats['early_bigger_than_cost']} of {tstats['n']} bottoms.")
        md.append("  Guppy-confirmed entries after the major bottoms (median trading days waited / index rebound given up / confirmed entry beat the bottom entry at the same end date): "
                  + "; ".join(f"{r[0].split(' (')[0]} {r[3]} d / {r[4]} / {r[8]}" for r in gm) + ".")
    md.append("")
    md.append("## Method in brief\n")
    md.append("- **Question.** If you buy a calendar-reset 2x fund after a crash, what do you own (its leverage that day), and how does that compare with a daily-reset 2x "
              "twin, a daily 3x fund, a buy-once margin position and the plain index, at 1 / 3 / 5 / 10 years?")
    md.append("- **Comparators, all on the same total-return underlying and the same reference rate (DFF, lagged), early-reset mode `level`:** the calendar product; its daily 2x "
              "twin (same costs, `twin_of`); a synthetic 3x daily twin at the filed UPRO / TQQQ terms (below); the real UPRO (from 2009-06-25) and TQQQ (from 2010-02-11) price "
              "series where the entry is after their first bar (PRICE ONLY: distributions are not reinvested, so these are slightly below a total-return series); the buy-once "
              "2x margin position (`World.margin_slice`, same costs, never reset, finished at -50%; OPTIMISTIC: no margin call); and the 1x total-return index.")
    md.append("- **Cost encodings (ASSUMED, F5).** The 2x products are run under both: `fixed` (2.6% of NAV a year) and `rate` (1.4% + 1.3 x the reference rate). Tables show `fixed`; "
              "`rate` is in the JSON, the raw tables and the timing section. The 3x models use the plain rate and the filed costs (no residual encoding).")
    for name in ("SPX", "NDX"):
        m = products.MODELS_3X[products.MODEL_3X_FOR[name]]
        md.append(f"- **{m.name}** (L=3, daily reset, kernel convention: 2 turns of the reference rate): spread {m.costs.spread:.4%} over fed funds [{m.costs.spread_status}] on "
                  f"{m.costs.turns:g} swap turns [{m.costs.turns_status}, swaps basis] + fee {m.costs.fee:.2%} [{m.costs.fee_status}]. Source: {m.costs.spread_source}; fee: {m.costs.fee_source}.")
    for name in ("SPX", "NDX"):
        pv = wprov[name]
        md.append(f"- **{NAMES[name]}**: total return {pv['first']} to {pv['last']} ({pv['rows']} rows); entries on the price index `{pv['price_symbol']}`; "
                  f"early-reset trigger (base case): {pv['trigger_text']}, drop 35%, mode level. {pv['banner']} "
                  f"Rate: {pv['rate']['source']} (proxy rows {pv['rate']['proxy_rows']}, stale rows {pv['rate']['stale_rows']}).")
    md.append("- **Effective leverage** (entry day) is read from the kernel's own state: exactly L if the entry close is itself a reset close, otherwise the kernel is re-run from the last "
              "reset and the exposure is read from the NAV's slope in the index level (`bottoms.effective_leverage`); it equals 2 x (U_t/U_0) / (NAV_t/NAV_0) wherever the base is "
              f"the last reset's close (cross-check below: SPX {lev_checks['SPX']['n']} cases, max difference {lev_checks['SPX']['max_abs_diff']:.1e}; NDX {lev_checks['NDX']['n']} cases, "
              f"max difference {lev_checks['NDX']['max_abs_diff']:.1e}). Daily twins are exactly 2, the 3x models exactly 3.")
    md.append("- **Returns** are NAV ratios of full-history runs (DESIGN section 8), CAGR in calendar days / 365.25; the end is the last close on or before the entry date plus h years; "
              "n/a where the data end first. Max drawdown is measured from the entry level and any later high.\n")

    for name in ("SPX", "NDX"):
        w, ev, d = worlds[name], evs[name], md_world[name]
        live = d["live"]
        info = d["info"]
        md.append(f"## {NAMES[name]}\n")
        md.append(f"### A. Hindsight bottoms: troughs of every drawdown deeper than 19% in the price index, found from the data ({w.dates[0].date()} to {w.dates[-1].date()})\n")
        md.append("A drawdown starts at a new all-time-high close and ends at the next one; its trough is the lowest close in between. The search then repeats inside a drawdown that "
                  "never regained its old high (so the Nasdaq-100's 2008-09 low is found inside its 2000-2015 fall). The index data start in "
                  f"{w.dates[0].year}, so a fall from a high before that is invisible.\n")
        rows = []
        for r in info["compare"]:
            if r["found_date"] is None:
                near = [t for t in info["troughs"] if abs((pd.Timestamp(t["trough_date"]) - pd.Timestamp(r["listed"])).days) <= 400]
                rows.append([r["listed"], "NOT found as a trough", "", "", "nearest in the data: " + (f"{near[0]['trough_date']} ({pc(near[0]['depth'])})" if near else "none")])
            else:
                rows.append([r["listed"], r["found_date"], f"{r['days_apart']:+d} days" if r["days_apart"] else "same day", pc(r["depth"]), ""])
        md.append("**The brief's list against the data**\n")
        md.append(md_table(["listed date", "trough in the data", "difference", "fall from its peak", "note"], rows))
        major_ids = {e["date"] for e in d["major"]}
        extra_rows = []
        for t in info["unmatched"]:
            tier = "major (added)" if t["trough_date"] in major_ids else "shallow"
            extra_rows.append([t["trough_date"], t["peak_date"], pc(t["depth"]), "all-time-high fall" if t["level"] == 0 else f"inside a longer fall (level {t['level']})",
                               t["recovery_date"] or "not recovered", tier])
        md.append("**Troughs deeper than 19% that the list does not contain** (shallow = the brief's \"19-30%\" group, kept as separate entries; \"major (added)\" = deeper than 40% or, for the Nasdaq-100, the 1987 / 1990 lows the brief asks for)\n")
        md.append(md_table(["trough", "peak it fell from", "fall", "kind", "back at the peak", "tier here"], extra_rows))
        md.append(f"\n### A1. {live.name} bought at each major bottom's close (fixed-cost encoding)\n")
        md.append(f"Entry leverage = the fund's effective leverage after the entry close. A `*` marks a listed date that is not the data's trough. Real fund: {REAL[name][1]} price only.\n")
        md.append(hindsight_tables(name, w, live, d["major"], ev, BASE))
        md.append(f"**Worst fall inside the first 3 years after entry, and early (-35%) resets inside them**\n")
        md.append(risk_table(name, live, d["major"], ev, BASE))
        md.append(f"\n**Same entries, `rate` encoding: {live.name} and its twin**\n")
        rows = []
        for e in d["major"]:
            r = e["res"]["rate"][live.name]
            rows.append([e["date"], lev(r["leverage"])] + [rc(r, h, k) for h in B.HORIZONS_YEARS for k in ("fund", "twin")])
        md.append(md_table(["bottom", "entry leverage"] + [f"{h}y {k}" for h in B.HORIZONS_YEARS for k in (live.name, "twin")], rows))
        md.append(f"\n### A2. Every calendar product at each major bottom: 3-year return and entry leverage (fixed encoding)\n")
        md.append(all_products_table(w, d["major"], BASE, 3))
        md.append("\n### A3. Shallower bottoms (falls of 19-30%, and any other trough deeper than 19% not on the list)\n")
        md.append(md_table(["trough", "fall", f"{live.name} lev", f"{live.name} 1y", f"{live.name} 3y", "twin 3y", "3x model 3y", "margin 3y", "1x 3y"],
                           [[e["date"], pc(e["depth"], 0), lev(e["res"][BASE][live.name]["leverage"]), sret(cell(e["res"][BASE][live.name], 1, "fund")),
                             sret(cell(e["res"][BASE][live.name], 3, "fund")), sret(cell(e["res"][BASE][live.name], 3, "twin")),
                             sret(cell(e["res"][BASE][live.name], 3, "m3x")), sret(cell(e["res"][BASE][live.name], 3, "margin")),
                             sret(cell(e["res"][BASE][live.name], 3, "idx"))] for e in d["shallow"]]))
        md.append("(5- and 10-year numbers for these are in the JSON and `results/raw/`.)\n")
        md.append(f"\n### A4. Sensitivity: the v1 trigger (index price, close only) next to the base case\n")
        md.append(f"Same major bottoms, fixed encoding, every calendar product. Base case: {wprov[name]['trigger_text']}. v1 trigger: the {wprov[name]['price_symbol']} price index, "
                  "close only (the trigger of the v1 results). Entry leverage is the kernel's own state under each trigger: a fund whose early reset "
                  "fired between the last ordinary reset and the entry has a different base, so its leverage differs.\n")
        md.append(trigger_sensitivity_md(w.specs, d["tsens"]))

        # B: levels
        md.append(f"\n### B. Rule-based entries: the first close at least X below the prior all-time high of the price index, once per fall (re-armed by a new high)\n")
        never, never_txt, summ, detail = level_summary(name, w, live, ev, info["levels"], info["deepest"], d["entries"], BASE)
        md.append(f"The deepest close-to-high fall in the data is {pc(info['deepest']['fall'])} ({info['deepest']['ath_date']} to {info['deepest']['date']}).\n")
        md.append(never_txt + "\n" if never_txt else "Every level triggered at least once.\n")
        md.append(f"**By level ({live.name}, fixed encoding)**\n")
        md.append(summ)
        md.append(f"**Every rule entry ({live.name}, fixed encoding)**\n")
        md.append(detail)

        # C: Guppy
        md.append(f"\n### C. Guppy-confirmed entries after each entry (Clean Guppy v1 slow ribbon; fill at the next close)\n")
        md.append("A signal is the first bar after the entry on which the daily (or weekly, on week-end closes) slow ribbon changes state; the entry is the NEXT close (the repo's delay-1 "
                  "convention). `days waited` counts trading days from the bottom entry to that fill; the index move is the price index from the bottom to the fill (the price of waiting). "
                  "\"none within 2y\" = no such transition inside two years of the entry. The first transition after the entry is taken literally: if the ribbon was already gray at the "
                  "entry, a red->gray needs a later red phase.\n")
        md.append("**Major bottoms: each confirmation as signal date (trading days waited to the fill, index move while waiting)**\n")
        md.append(guppy_tables(name, live, {e["id"]: e for e in d["entries"] + d["kids"]}, d["recs"], d["major"], BASE))
        for gname, gt in d["gmd"].items():
            md.append(f"**Summary: {gname}, {live.name} fixed encoding**\n")
            md.append(gt)

        # timing
        md.append(f"\n### D. Entry-timing sensitivity around each major bottom\n")
        tmd, stats = timing_summary(d["timing"], live.name, encs)
        d["timing_stats"] = stats
        R["worlds"][name]["timing_stats"] = stats
        md.append(f"The entry moves to the month-end close nearest to the bottom date plus k months (so the dates used are listed). 'Range over the 6 cost assumptions' = max minus min of "
                  f"the {live.name} 3-year total return at the bottom itself over `fixed`, `rate` and the four F5 sensitivities (spread 1.4% / 3.5%, rate turns 1.0 / 1.5).\n")
        md.append(tmd)
        md.append(f"Over {stats['n']} bottoms with all three numbers: median |3-year return change| from entering 3 months early {pc(stats['median_abs_early'], 0)}, from entering 3 months late "
                  f"{pc(stats['median_abs_late'], 0)}, median range over the six cost assumptions {pc(stats['median_cost_range'], 0)}; the early shift is larger than the cost range in "
                  f"{stats['early_bigger_than_cost']} of {stats['n']} bottoms.\n")
        md.append(timing_md(name, live, d["timing"], encs))

    md.append("## Effective leverage after the 2009 and 2020 bottoms\n")
    md.append("![effective leverage](from_bottoms_leverage.png)\n")
    md.append("The first 90 trading days after the S&P 500 (2009-03-09, 2020-03-23) and Nasdaq-100 (2009-03-09, 2020-03-20) closes, fixed encoding, for every calendar product on that index.\n")
    for name in ("SPX", "NDX"):
        md.append(f"![{NAMES[name]} 3-year overlay](from_bottoms_{name}.png)\n")
        md.append(f"### {NAMES[name]}: the overlay chart in dollars\n")
        md.append(dollar_md(name, md_world[name]["live"], md_world[name]["ev"], md_world[name]["dollars"]))
        md.append(dollar_products_md(worlds[name], md_world[name]["dollars_products"]))

    md.append("## What could not be tested, and judgment calls\n")
    md.append("- No live calendar fund before 2024-08, so every calendar-fund number is a model with costs fitted on 2024-26 (F3-F5); the cost encodings diverge when rates move.\n"
              "- The -35% trigger is tested on the ETF's daily low (the index before the ETF existed); the fill price and a gap through the level are not known "
              "(mode `level` fills at the level), and the v1 close-only index trigger is table A4. The margin benchmark has no margin call (optimistic).\n"
              "- The real UPRO / TQQQ series are price only: they leave out distributions and are NAV-proxies, not NAVs; they exist only for the 2020 and later entries.\n"
              "- Hindsight bottoms are, by construction, not knowable at the time; the rule entries (B) and the Guppy-confirmed entries (C) are. There are few independent crashes "
              "(about 7 per index), so medians over them are descriptive, not evidence of a rule.\n"
              "- Index data start 1950 (S&P 500) and 1985 (Nasdaq-100), so earlier falls cannot be seen; the first drawdown in each file is measured from the first close, not a true earlier high.\n"
              "- Dividend yields before 1988 (S&P, Shiller measured) and before 2006 (Nasdaq-100: QQQ's measured yields 1999-2006, 0.3% ASSUMED before 1999) enter the total-return underlying (B7).\n"
              "- TQQQ_MODEL's 0.82% fee is as given in the brief; no TQQQ expense ratio is on file, so its status is ASSUMED. SOXL not used.\n"
              "- Judgment calls: tiering (major = the brief's list, plus NDX 1987 / 1990, plus any trough deeper than 40% the list omits; shallow = the rest); troughs are found inside "
              "long falls too; ties on the month-end for the timing shifts go to the earlier month-end; Guppy fills are at the next close; the 3x and margin comparators use "
              "the same entry close as the fund.\n")

    (OUT / "from_bottoms.md").write_text("\n".join(md), encoding="utf-8")
    R["meta"]["wall_seconds"] = time.perf_counter() - wall0
    (OUT / "from_bottoms.json").write_text(json.dumps(clean(R), separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT / 'from_bottoms.md'}, {OUT / 'from_bottoms.json'}, 3 charts, raw tables")
    for name in ("SPX", "NDX"):
        print(name, "timing stats:", md_world[name]["timing_stats"])
    print(f"done in {time.perf_counter() - wall0:.2f} s")


if __name__ == "__main__":
    main()
