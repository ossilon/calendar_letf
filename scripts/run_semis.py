"""B16: calendar-reset funds on semiconductors (the PHLX Semiconductor Sector Index, SOX) at 1.2x, 1.5x, 1.7x, 2x and
3x, each against a daily twin at the same leverage and costs. Every fund is HYPOTHETICAL; Tradr ran a 2x SOXX monthly
(SOXM) and a 2x SOXX weekly (SOXW) fund from 2024-08-30 to 2025-02-28.

    py scripts\\run_semis.py        (from calendar_letf/, with CALENDAR_LETF_DATA / _RATES set; about 2 minutes)

Index basis. The long history is ONE index, the PHLX Semiconductor Sector Index (NASDAQ:SOX), PRICE ONLY: no total-return
series of it is on hand, so every return here leaves out its dividends (the fund, its twin and the index alike). The
SOXX ETF tracked three indexes over its life (SOXX_INDEX_BASIS, SECONDARY dates), so SOXX's own history is not used for
the long run. The early-reset trigger watches SOX itself (close and daily low).
Costs. The fee of SOXM / SOXW (their filed net expense ratio, reference/nav_anchors.csv). The swap spread per turn of
the real 2x daily semiconductor fund (ProShares USD, SEC N-PORT, reference/nport_semis_2026.json) on L turns (all swap,
ASSUMED), with no spread and twice it as sensitivities; fed funds on the L - 1 borrowed turns.
What it reports: per L, reset and trigger rule the full-history CAGR, drawdown, wipeouts and early resets with their
eras, the yearly gap against the twin with its interval and coverage, the 10-year multi-start gap; the 0.05 curve with
the best L as a plateau and the break-even fee; C13 on semiconductors; $10,000 through the key periods; the real SOXL
(price only, another index since 2021) next to the 3x twin; wipeout and early-reset rates on 5000 simulated decades.
The SOXM / SOXW one-month check needs SOXX's daily prices and its 2024 payouts, which are not in the price library yet:
the results file says so (validation.status).
Writes results/semis.json and results/semis.md.
"""
import csv
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import run_montecarlo as rmc  # noqa: E402
import run_sub2x as sub2x  # noqa: E402
from calendar_letf import costs as cst, leverage, loader, metrics, montecarlo as mc, products, provenance, study  # noqa: E402

OUT = ROOT / "results"
REFERENCE = ROOT / "reference"
CAPTION = ("Data: TradingView (via local export), FRED, SEC N-PORT. Every fund is HYPOTHETICAL; the index is PRICE ONLY; "
           "SOXL is a price-only overlay on another index since 2021. Not investment advice.")
STUDY_END = sub2x.STUDY_END
SYMBOL = "NASDAQ:SOX"
NAME = "SOX"
BASIS_LABEL = "PHLX Semiconductor Sector Index (NASDAQ:SOX), price only: dividends left out"
LS = (1.2, 1.5, 1.7, 2.0, 3.0)
TRIGGERS = products.TRIGGER_RULES
BASE_TRIGGER = "scaled"
COST_FACTORS = {"zero": 0.0, "usd": 1.0, "double": 2.0}
BASE_COST = "usd"
REAL = "AMEX:SOXL"
N_MC = 5000
MC_BLOCK = 252
DESIGN_NAME = {"weekly": "HYP_SOX_W", "monthly": "HYP_SOX_M", "quarterly": "HYP_SOX_Q"}
# The indexes SOXX tracked (SECONDARY: the dates come from a secondary source and TradingView; verify in iShares' filings).
SOXX_INDEX_BASIS = (("2001-07-13", "2010-10-14", "S&P North American Technology Semiconductors Index"),
                    ("2010-10-15", "2021-06-20", "PHLX Semiconductor Sector Index (SOX)"),
                    ("2021-06-21", None, "NYSE Semiconductor Index"))
VALIDATION_FUNDS = ("SOXM", "SOXW")
SOXX, USD = "NASDAQ:SOXX", "AMEX:USD"
YIELD_YEARS = (2022, 2025)        # full calendar years the saved SOXX payout history covers (it starts 2021-09)


def soxx_index_on(date):
    """The index SOXX tracked on `date` (SOXX_INDEX_BASIS, SECONDARY)."""
    d = pd.Timestamp(date)
    for a, b, label in SOXX_INDEX_BASIS:
        if pd.Timestamp(a) <= d and (b is None or d <= pd.Timestamp(b)):
            return label
    return None


# ---------------------------------------------------------------- inputs read from files, never typed
def filed_fee():
    rows = [r for r in csv.DictReader(open(REFERENCE / "nav_anchors.csv", encoding="utf-8"))
            if r["ticker"] in VALIDATION_FUNDS and r["status"] == "PRIMARY"]
    fees = {float(r["expense_ratio_net_pct"]) / 100.0 for r in rows}
    if len(rows) != 2 or len(fees) != 1:
        raise ValueError(f"nav_anchors.csv: expected one PRIMARY row each for {VALIDATION_FUNDS} with one fee, got {rows}")
    return fees.pop(), rows


def filed_spread():
    doc = json.loads((REFERENCE / "nport_semis_2026.json").read_text(encoding="utf-8"))
    u = doc["USD"]
    if u["spread_units"] != "percent" or u["reference"] != "FEDL01":
        raise ValueError("nport_semis_2026.json: USD's spread must be in percent over FEDL01")
    return u["weighted_spread_pct"] / 100.0, u


FEE, ANCHOR_ROWS = filed_fee()
SPREAD, USD_NPORT = filed_spread()


def base_design(reset):
    """The 2x SOX design of a reset: the base that products.at_leverage moves to L (HYPOTHETICAL)."""
    name = DESIGN_NAME[reset]
    c = cst.CostSpec(fee=FEE, fee_status="VERIFIED_semiannual_2024-09-30",
                     fee_source="SOXM / SOXW net expense ratio, semi-annual report to 2024-09-30 (reference/nav_anchors.csv)",
                     spread=SPREAD, spread_status="VERIFIED_NPORT_2026-05-31",
                     spread_source=("USD (ProShares Ultra Semiconductors, 2x daily) N-PORT 2026-05-31 weighted spread over fed funds "
                                    "(reference/nport_semis_2026.json); carried to a calendar design (ASSUMED)"),
                     turns=2.0, turns_status="ASSUMED", turns_source="notional basis: swaps on the whole exposure (ASSUMED)",
                     spread_basis="notional", label=name)
    return products.ProductSpec(
        name=name, kind="MODELED", underlying=NAME, reset=reset, costs=c, early_drop=0.35, early_drop_status="ASSUMED",
        early_drop_source="the Tradr -35% intra-period trigger (SOXM / SOXW had it)",
        note=f"HYPOTHETICAL 2x {reset} design on the SOX price index; SOXM / SOXW traded 2024-08-30 to 2025-02-28 on SOXX")


def spec_at(reset, L, trig, basis="notional"):
    if reset == "daily":
        return products.twin_of(products.at_leverage(base_design("monthly"), L, "none", basis))
    return products.at_leverage(base_design(reset), L, trig, basis)


def enc_at(L, factor=1.0):
    e2 = study.CostEncoding(f"sox_{factor:g}", SPREAD * 2.0 * factor, 1.0, status="ASSUMED",
                            source=f"{factor:g} x USD's filed spread per turn on L turns", label=f"{factor:g} x USD spread")
    return study.encoding_at(e2, L, "notional")


def build_world():
    px = loader.load_prices(SYMBOL).loc[:STUDY_END]
    if px.index[-1] != pd.Timestamp(STUDY_END):
        raise ValueError(f"{SYMBOL}: no close on {STUDY_END}")
    u = px["close"].astype("float64").rename(NAME)
    u.attrs = dict(symbols=[SYMBOL], basis=BASIS_LABEL)
    low, bad = study.clean_lows(u, px["low"])
    low = low.rename(f"{NAME}_low")
    rate = loader.reference_rate(u.index)
    specs = [base_design(r) for r in sub2x.CAL_RESETS]
    info = dict(basis="index", symbol=SYMBOL, intraday=True, bad_low_days=bad,
                bad_low_rule=f"a low more than {study.BAD_LOW_TOL:.0%} below both the previous close and the close is replaced by the close")
    w = study.World(NAME, u, u.copy(), rate, specs, {}, trigger_low=low, trigger_basis="index", trigger_info=info)
    prov = dict(banner=f"[{NAME}] {BASIS_LABEL}", first=str(u.index[0].date()), last=str(u.index[-1].date()), rows=int(len(u)),
                rate=dict(source=rate.attrs["source"], proxy_rows=rate.attrs["proxy_rows"], proxy_until=rate.attrs["proxy_until"],
                          rate_last_date=rate.attrs["rate_last_date"], stale_rows=rate.attrs["stale_rows"]),
                trigger_text=f"the {SYMBOL} price index, daily low", bad_low_days=bad, bad_low_rule=info["bad_low_rule"])
    return w, prov


def world_with(w, specs):
    return study.World(w.name, w.u, w.trigger, w.rate, specs, {s.name: products.twin_of(s) for s in specs},
                       trigger_low=w.trigger_low, trigger_basis=w.trigger_basis, trigger_info=w.trigger_info)


def era(d):
    return leverage.era_of(d, study.KEY_PERIODS)


# ---------------------------------------------------------------- the study
def named_rows(w):
    rows, ms = [], []
    for L in LS:
        enc = enc_at(L)
        for trig in TRIGGERS:
            W = world_with(w, [spec_at(r, L, trig) for r in sub2x.CAL_RESETS])
            for p in W.specs:
                nav, tw = W.nav(p.name, enc), W.nav(W.twin_name(p.name), enc)
                yc, yt = leverage.yearly_log_returns(nav), leverage.yearly_log_returns(tw)
                d = np.array([yc[y] - yt[y] for y in sorted(yc)])
                rows.append(dict(L=L, trigger=trig, drop=p.early_drop, product=p.name, reset=p.reset, basis=BASIS_LABEL,
                                 cagr=metrics.cagr(nav), max_dd=metrics.max_drawdown(nav), terminated=nav.attrs["terminated"],
                                 terminated_era=era(nav.attrs["terminated"]) if nav.attrs["terminated"] else None,
                                 n_early_resets=len(nav.attrs["early_resets"]), early_resets=list(nav.attrs["early_resets"]),
                                 early_eras=sorted({era(x) or "other" for x in nav.attrs["early_resets"]}),
                                 twin_cagr=metrics.cagr(tw), twin_max_dd=metrics.max_drawdown(tw), twin_terminated=tw.attrs["terminated"],
                                 gap_yearly=sub2x.interval_with_coverage(d, f"semis {p.name} {L} {trig} yearly gap")))
            hz = study.HORIZONS_YEARS if trig == BASE_TRIGGER else (10,)
            for r in study.multi_start(W, enc, horizons_years=hz)[0]:
                ms.append(dict(L=L, trigger=trig, **{k: r[k] for k in ("product", "reset", "horizon_years", "n_starts", "gap_median", "gap_p10",
                                                                         "gap_p90", "calendar_wins", "indep_mean", "indep_lo", "indep_hi",
                                                                         "indep_df", "noisy", "cal_cagr_median", "twin_cagr_median",
                                                                         "cal_maxdd_median")}))
    return rows, ms


def curve(w):
    """The 0.05 grid at the base cost: yearly log returns per (reset, L), the best L as a plateau, the break-even fee."""
    idx_growth = math.log(w.u.iloc[-1] / w.u.iloc[0])
    out_curve, plateaus, be = [], [], []
    for reset in sub2x.RESETS:
        trig = "-" if reset == "daily" else BASE_TRIGGER
        yearly = {}
        for L in leverage.GRID:
            spec = spec_at(reset, L, None if reset == "daily" else BASE_TRIGGER)
            enc = enc_at(L)
            W = world_with(w, [spec]) if reset != "daily" else None
            nav = W.nav(spec.name, enc) if W else kernel_run(w, spec, enc)
            y = leverage.yearly_log_returns(nav)
            yearly[L] = np.array([y[k] for k in sorted(y)])
            out_curve.append(dict(reset=reset, trigger=trig, L=L, cagr=metrics.cagr(nav), terminated=nav.attrs["terminated"],
                                  growth=float(np.mean(yearly[L])) if np.isfinite(yearly[L]).all() else None))
            if L in LS:
                def g(f, spec=spec, enc=enc):
                    v = kernel_run(w, spec, enc, fee=f).iloc[-1]
                    return math.log(v) if v > 0 else -math.inf
                yrs = (w.dates[-1] - w.dates[0]).days / 365.25
                be.append(dict(reset=reset, trigger=trig, L=L, **leverage.break_even_fee(g, idx_growth),
                               log_growth_gap_at_zero_fee=(g(0.0) - idx_growth) / yrs))   # how far behind the index with no fee
        for scope, top in (("under2", leverage.HEADLINE_MAX_L), ("to3", None)):
            p = leverage.plateau(yearly, max_L=top)
            plateaus.append(dict(reset=reset, trigger=trig, scope=scope, L_best=p["L_best"], plateau_lo=p["lo"], plateau_hi=p["hi"],
                                 contiguous=p["contiguous"], wiped=p["wiped"], rising_at_top=p["rising_at_top"],
                                 growth_best=p["growth"][p["L_best"]]))
    return out_curve, plateaus, be


def kernel_run(w, spec, enc, fee=None):
    from calendar_letf import kernel
    kw = study.kernel_kwargs(spec, enc)
    if fee is not None:
        kw["fee"] = fee
    daily = spec.reset == "daily"
    return kernel.run(spec, w.u, study.scaled_rate(w.rate, enc), trigger=None if daily else w.trigger,
                      trigger_low=None if daily else w.trigger_low, early_mode=study.BASE_MODE, **kw)


def c13(w):
    out = []
    z = study.ZERO_COSTS
    for reset in sub2x.CAL_RESETS:
        gap = {}
        for L in LS:
            e = study.encoding_at(z, L)
            c = kernel_run(w, spec_at(reset, L, "none"), e).iloc[-1]
            d = kernel_run(w, spec_at("daily", L, None), e).iloc[-1]
            gap[L] = math.log(c / d) if c > 0 else None
        out.append(dict(reset=reset, gap_2x_log=gap[2.0], rows=[dict(L=L, gap_log=gap[L], predicted=L * (L - 1.0) / 2.0,
                                                                       ratio=None if gap[L] is None or not gap[2.0] else gap[L] / gap[2.0])
                                                                  for L in LS if L != 2.0]))
    return out


def cost_sensitivity(w):
    out = []
    for L in (2.0, 3.0):
        for k, f in COST_FACTORS.items():
            enc = enc_at(L, f)
            W = world_with(w, [spec_at(r, L, BASE_TRIGGER) for r in sub2x.CAL_RESETS])
            ms = {r["product"]: r for r in study.multi_start(W, enc, horizons_years=(10,))[0]}
            for p in W.specs:
                out.append(dict(L=L, cost=k, product=p.name, reset=p.reset, cagr=metrics.cagr(W.nav(p.name, enc)),
                                twin_cagr=metrics.cagr(W.nav(W.twin_name(p.name), enc)), gap10_median=ms[p.name]["gap_median"]))
    return out


def key_periods(w):
    out = []
    for label, d0, d1 in study.KEY_PERIODS:
        s, e = w.row_before(d0), w.row_on_or_before(d1)
        if s < 0 or e <= s:
            out.append(dict(period=label, covered=False))
            continue
        row = dict(period=label, covered=True, first_close=str(w.dates[s].date()), last_close=str(w.dates[e].date()),
                   index=10000.0 * float(w.u.iloc[e] / w.u.iloc[s]), funds={})
        for L in (2.0, 3.0):
            enc = enc_at(L)
            W = world_with(w, [spec_at(r, L, BASE_TRIGGER) for r in sub2x.CAL_RESETS])
            for p in W.specs:
                nav = W.nav(p.name, enc)
                row["funds"][p.name] = 10000.0 * float(nav.iloc[e] / nav.iloc[s]) if nav.iloc[s] > 0 else 0.0
            tw = W.nav(W.twin_name(W.specs[0].name), enc)
            row["funds"][f"TWIN_L{L:g}"] = 10000.0 * float(tw.iloc[e] / tw.iloc[s])
        out.append(row)
    return out


def overlay(w):
    real = loader.close(REAL).loc[:STUDY_END]
    s = int(np.searchsorted(w.dates.values, np.datetime64(real.index[0])))
    yrs = (w.dates[-1] - w.dates[s]).days / 365.25
    g = lambda a: (a[-1] / a[s]) ** (1.0 / yrs) - 1.0 if a[s] > 0 and a[-1] > 0 else -1.0     # noqa: E731
    enc = enc_at(3.0)
    rr = real.loc[w.dates[s]:]
    designs = {r: g(kernel_run(w, spec_at(r, 3.0, BASE_TRIGGER), enc).to_numpy()) for r in sub2x.CAL_RESETS}
    return dict(real=REAL, first=str(w.dates[s].date()), last=str(w.dates[-1].date()), years=yrs,
                real_cagr=float((rr.iloc[-1] / rr.iloc[0]) ** (1.0 / yrs) - 1.0), real_max_dd=metrics.max_drawdown(rr.to_numpy()),
                twin_cagr=float(g(kernel_run(w, spec_at("daily", 3.0, None), enc).to_numpy())), designs=designs,
                index_cagr=float(g(w.u.to_numpy())),
                note=("SOXL: price only; it tracked SOX until 2021-08-25 and another semiconductor index since (SECONDARY); its "
                      "filed swap spread is not resolved, so the 3x twin pays USD's spread per turn on 3 turns and the SOXM fee"))


def soxx_payouts():
    d = pd.read_csv(REFERENCE / "soxx_distributions.csv", parse_dates=["ex_date"])
    return pd.Series(d["amount_per_share"].astype(float).values, index=pd.DatetimeIndex(d["ex_date"]))


def own_total_return(close, payouts):
    """The ETF's own total return: each payout reinvested at its ex-date close, TR_t / TR_t-1 = (P_t + D_t) / P_t-1."""
    d = payouts.reindex(close.index).fillna(0.0)
    r = (close + d) / close.shift(1)
    r.iloc[0] = 1.0
    return r.cumprod()


def soxx_yield():
    """SOXX's payouts in each full calendar year of the saved history as a share of its mean close that year (SECONDARY)."""
    px, pay = loader.close(SOXX), soxx_payouts()
    out = {}
    for y in range(YIELD_YEARS[0], YIELD_YEARS[1] + 1):
        out[y] = float(pay[pay.index.year == y].sum() / px[px.index.year == y].mean())
    return dict(by_year={str(k): v for k, v in out.items()}, mean=float(np.mean(list(out.values()))),
                lo=min(out.values()), hi=max(out.values()), source="reference/soxx_distributions.csv (SECONDARY) and NASDAQ:SOXX closes")


def validation():
    """SOXM (2x SOXX monthly) and SOXW (2x SOXX weekly) over their one published month, on SOXX's OWN total return, in the
    way of FINDINGS F1b: swaps on 2 x NAV at the filed spread over OBFR, cash of 1 x NAV earning c x OBFR (c from the live
    funds' fits, results/validate_live.json), the filed fee. Nothing is fitted on these funds."""
    from calendar_letf import kernel, validate
    rows = {r["ticker"]: r for r in ANCHOR_ROWS}
    s0, e0 = {r["start_date"] for r in ANCHOR_ROWS}, {r["end_date"] for r in ANCHOR_ROWS}
    if len(s0) != 1 or len(e0) != 1:
        raise ValueError("SOXM / SOXW anchors must share one window")
    s0, e0 = s0.pop(), e0.pop()
    px = loader.load_prices(SOXX).loc[s0:e0]
    if str(px.index[0].date()) != s0 or str(px.index[-1].date()) != e0:
        raise ValueError(f"{SOXX}: no close on {s0} or {e0}")
    pay = soxx_payouts()
    pay = pay[(pay.index > pd.Timestamp(s0)) & (pay.index <= pd.Timestamp(e0))]
    tr = own_total_return(px["close"].astype(float), pay)
    low, _ = study.clean_lows(px["close"].astype(float), px["low"])
    obfr = loader.rate_known_before(px.index, loader.load_fred("OBFR"), "OBFR", max_hole_days=10)
    vl = json.loads((OUT / "validate_live.json").read_text(encoding="utf-8"))
    c = vl["provenance"]["liquidated_cash_yield_used"]["value"]
    lo, hi = validate.filed_spread_range(json.loads((REFERENCE / "nport_tradr_2026.json").read_text(encoding="utf-8")))
    out = []
    for fund in VALIDATION_FUNDS:
        r = rows[fund]
        spec = base_design(r["reset"])
        anchor = float(r["total_return_nav_pct"]) / 100.0
        models = {}
        for label, s in (("tradr_spread_low", lo), ("tradr_spread_high", hi), ("usd_spread", SPREAD)):
            nav = kernel.run(spec, tr, obfr * (2.0 - c), trigger=px["close"].astype(float), trigger_low=low, spread_per_nav=2.0 * s,
                             fee=float(r["expense_ratio_net_pct"]) / 100.0)
            m = float(nav.iloc[-1] / nav.iloc[0] - 1.0)
            models[label] = dict(spread=s, model_return=m, gap_pp=(m - anchor) * 100.0)
        out.append(dict(fund=fund, reset=r["reset"], start=s0, end=e0, anchor_nav_return=anchor, models=models,
                        two_x_etf_tr=2.0 * float(tr.iloc[-1] / tr.iloc[0] - 1.0), payouts_in_window=[str(d.date()) for d in pay.index],
                        soxx_index=soxx_index_on(e0), cash_yield_c=c, source=r["source"]))
    return dict(status="RUN: on SOXX's own total return (price plus payouts at their ex-dates)", rows=out,
                max_abs_gap_pp=max(abs(x["gap_pp"]) for v in out for x in v["models"].values()),
                validate_live_sha256=provenance.sha256_of(OUT / "validate_live.json"))


def usd_overlay(w):
    """The real 2x daily semiconductor fund USD (price only; it tracks its own semiconductor index, not SOX) from its first
    bar, next to the 2x daily twin and the 2x calendar designs on SOX."""
    real = loader.close(USD).loc[:STUDY_END]
    s = int(np.searchsorted(w.dates.values, np.datetime64(real.index[0])))
    yrs = (w.dates[-1] - w.dates[s]).days / 365.25
    g = lambda a: (a[-1] / a[s]) ** (1.0 / yrs) - 1.0 if a[s] > 0 and a[-1] > 0 else -1.0     # noqa: E731
    enc = enc_at(2.0)
    rr = real.loc[w.dates[s]:]
    return dict(real=USD, first=str(w.dates[s].date()), last=str(w.dates[-1].date()), years=yrs,
                real_cagr=float((rr.iloc[-1] / rr.iloc[0]) ** (1.0 / yrs) - 1.0), real_max_dd=metrics.max_drawdown(rr.to_numpy()),
                twin_cagr=float(g(kernel_run(w, spec_at("daily", 2.0, None), enc).to_numpy())),
                designs={r: g(kernel_run(w, spec_at(r, 2.0, BASE_TRIGGER), enc).to_numpy()) for r in sub2x.CAL_RESETS},
                index_cagr=float(g(w.u.to_numpy())),
                note="USD: price only, its own semiconductor index (not SOX); its fee and filed spread differ from the twin's")


def montecarlo(w):
    S = rmc.Setup(NAME, w)
    S.idx = 20
    items = []
    for L in LS:
        enc = enc_at(L)
        for trig in ("none", BASE_TRIGGER):
            items += [((L, trig, r), spec_at(r, L, trig), enc) for r in sub2x.CAL_RESETS]
        items.append(((L, "twin"), spec_at("daily", L, None), enc))
    starts = mc.block_starts(len(S.h["lr_u"]), MC_BLOCK)
    res = rmc.run_batches(S, items, lambda rng, P: mc.build_paths(S.h, mc.block_pick(rng, starts, MC_BLOCK, S.n, P)), N_MC, (9, 20))
    yrs = S.years[10]
    out = []
    for L in LS:
        kt = res["labels"].index((L, "twin"))
        tw = mc.cagr_between(res["navc"][:, kt, :], 0, S.col[10], yrs)
        for trig in ("none", BASE_TRIGGER):
            for r in sub2x.CAL_RESETS:
                k = res["labels"].index((L, trig, r))
                g = mc.cagr_between(res["navc"][:, k, :], 0, S.col[10], yrs) - tw
                out.append(dict(L=L, trigger=trig, reset=r, paths=N_MC, wiped=float((res["term"][:, k] >= 0).mean()),
                                wiped_twin=float((res["term"][:, kt] >= 0).mean()), early=float((res["early"][:, k] > 0).mean()),
                                gap=rmc.tails(g), wealth=rmc.tails(res["navc"][:, k, -1]), twin_wealth=rmc.tails(res["navc"][:, kt, -1]),
                                index_wealth=rmc.tails(res["index"][:, -1])))
    return out


# ---------------------------------------------------------------- report
def pp(x, d=2):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:+.{d}f}"


def pc(x, d=1):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.{d}f}%"


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]) + "\n"


def iv(x):
    return "n/a" if not x or x.get("lo") is None or not np.isfinite(x["lo"]) else f"[{pp(x['lo'])}, {pp(x['hi'])}] {x['verdict']}"


def markdown(res):
    m, W = res["meta"], res["world"]
    md = [f"# {m['title']}\n", f"*{m['caption']}*\n", "```", *m["banner"], "```\n",
          f"Index: {BASIS_LABEL}. Fee {pc(FEE, 2)} (SOXM / SOXW, filed); spread {pc(SPREAD, 4)} per turn over fed funds (USD, N-PORT) on L "
          f"turns; trigger rules none / scaled (0.70 / L) / fixed 35%. Every fund is HYPOTHETICAL.\n",
          f"## SOXM / SOXW one-month check ({W['validation']['status']})\n",
          md_table(["fund", "reset", "window", "anchor NAV return", "2 x SOXX TR", "model, Tradr spread low", "gap pp", "model, Tradr spread high",
                    "gap pp", "model, USD spread", "gap pp", "SOXX index (SECONDARY)"],
                   [[v["fund"], v["reset"], f"{v['start']} to {v['end']}", pc(v["anchor_nav_return"], 2), pc(v["two_x_etf_tr"], 2)]
                    + [x for k in ("tradr_spread_low", "tradr_spread_high", "usd_spread")
                       for x in (pc(v["models"][k]["model_return"], 2), f"{v['models'][k]['gap_pp']:+.2f}")] + [v["soxx_index"]]
                    for v in W["validation"]["rows"]]),
          f"Cash yield c = {W['validation']['rows'][0]['cash_yield_c']:.3f} x OBFR (from results/validate_live.json); payouts in the window: "
          f"{', '.join(W['validation']['rows'][0]['payouts_in_window']) or 'none'}. SOXX payouts {YIELD_YEARS[0]}-{YIELD_YEARS[1]}: "
          f"{pc(W['soxx_yield']['lo'], 2)}-{pc(W['soxx_yield']['hi'], 2)} of the mean price a year (SECONDARY).\n",
          "## Per leverage, trigger rule and reset (full history, base cost, level fill)\n",
          md_table(["L", "trigger", "design", "CAGR", "max DD", "twin CAGR", "wiped", "early resets", "eras", "yearly gap vs twin (95%)"],
                   [[f"{r['L']:g}", r["trigger"], r["product"], pc(r["cagr"], 2), pc(r["max_dd"]), pc(r["twin_cagr"], 2),
                     f"{r['terminated']} ({r['terminated_era'] or 'other'})" if r["terminated"] else "-", r["n_early_resets"],
                     ", ".join(r["early_eras"]) or "-", iv(r["gap_yearly"])] for r in W["named"]]),
          "## Multi-start gap against the daily twin (phase-pooled 95% interval)\n",
          md_table(["L", "trigger", "design", "years", "starts", "median gap", "calendar wins", "mean [95%]", "noisy"],
                   [[f"{r['L']:g}", r["trigger"], r["product"], r["horizon_years"], r["n_starts"], pp(r["gap_median"]), f"{r['calendar_wins']:.0%}",
                     f"{pp(r['indep_mean'])} [{pp(r['indep_lo'])}, {pp(r['indep_hi'])}]", "yes" if r["noisy"] else "no"] for r in W["multi_start"]]),
          "## The best L (0.05 grid, base cost; plateau = within one SE of the best)\n",
          md_table(["reset", "range", "best L", "plateau", "rising at top", "growth %/yr", "wiped L"],
                   [[p["reset"], p["scope"], f"{p['L_best']:.2f}", f"{p['plateau_lo']:.2f}-{p['plateau_hi']:.2f}", "yes" if p["rising_at_top"] else "no",
                     pp(p["growth_best"]), ", ".join(f"{x:.2f}" for x in p["wiped"][:6]) + ("..." if len(p["wiped"]) > 6 else "")] for p in W["plateau"]]),
          "## Break-even fee (against the price index, no fee)\n",
          md_table(["reset", "L", "fee", "status"], [[b["reset"], f"{b['L']:g}", pc(b["fee"], 2) if b["fee"] is not None else "loses", b["status"]] for b in W["break_even"]]),
          "## C13 on semiconductors (zero cost, no trigger; ratio of the full-history log gap to the 2x one)\n",
          md_table(["reset", "2x gap (log)"] + [f"{L:g}x ratio (pred {L * (L - 1) / 2:g})" for L in LS if L != 2.0],
                   [[c["reset"], f"{c['gap_2x_log']:+.4f}"] + ["n/a" if x["ratio"] is None else f"{x['ratio']:.3f}" for x in c["rows"]] for c in W["c13"]]),
          "## Costs (trigger scaled)\n",
          md_table(["L", "cost", "design", "CAGR", "twin CAGR", "10y median gap"],
                   [[f"{r['L']:g}", r["cost"], r["product"], pc(r["cagr"], 2), pc(r["twin_cagr"], 2), pp(r["gap10_median"])] for r in W["cost_sensitivity"]]),
          "## $10,000 through the key periods (trigger scaled, base cost)\n"]
    names = list(next(k for k in W["key_periods"] if k["covered"])["funds"])
    md.append(md_table(["period", "index"] + names, [[k["period"], f"${k['index']:,.0f}"] + [f"${k['funds'][n]:,.0f}" for n in names]
                                                   for k in W["key_periods"] if k["covered"]]))
    o = W["overlay"]
    md.append(f"## Real {o['real']} (price only) from {o['first']} to {o['last']}\n")
    md.append(md_table(["series", "CAGR"], [[f"real {o['real']}", pc(o["real_cagr"], 2)], ["3x daily twin", pc(o["twin_cagr"], 2)]]
                       + [[f"3x {r} (scaled)", pc(v, 2)] for r, v in o["designs"].items()] + [["SOX price index", pc(o["index_cagr"], 2)]]))
    md.append(o["note"] + "\n")
    u = W["usd_overlay"]
    md.append(f"## Real {u['real']} (price only) from {u['first']} to {u['last']}\n")
    md.append(md_table(["series", "CAGR"], [[f"real {u['real']}", pc(u["real_cagr"], 2)], ["2x daily twin", pc(u["twin_cagr"], 2)]]
                       + [[f"2x {r} (scaled)", pc(v, 2)] for r, v in u["designs"].items()] + [["SOX price index", pc(u["index_cagr"], 2)]]))
    md.append(u["note"] + "\n")
    md.append(f"## {N_MC} simulated decades ({MC_BLOCK}-day blocks of SOX history, base cost)\n")
    md.append(md_table(["L", "trigger", "reset", "wiped", "twin wiped", "early reset", "gap median (10y)", "median wealth", "p5 wealth"],
                       [[f"{r['L']:g}", r["trigger"], r["reset"], f"{r['wiped']:.1%}", f"{r['wiped_twin']:.1%}", f"{r['early']:.1%}", pp(r["gap"]["median"]),
                         f"{r['wealth']['median']:.2f}", f"{r['wealth']['p5']:.3f}"] for r in W["montecarlo"]]))
    return "\n".join(md)


def main():
    wall0 = time.perf_counter()
    print("=" * 100 + "\nB16: calendar-reset funds on semiconductors (all HYPOTHETICAL; SOX price only)")
    w, prov = build_world()
    inputs = study.inputs_for({NAME: w}, {NAME: prov}, extra_symbols=[REAL, SOXX, USD], extra_rates=["OBFR"])
    inputs["reference_dir"] = "reference"
    inputs.setdefault("reference_files", [])
    inputs["reference_files"] = list(inputs["reference_files"]) + provenance.manifest(
        [REFERENCE / n for n in ("nav_anchors.csv", "nport_semis_2026.json", "nport_tradr_2026.json", "soxx_distributions.csv")])
    banner = (provenance.banner_lines(inputs) + study.conventions_lines(w)
              + ["B16 trigger rules replace the 35% drop above: none, scaled (0.70 / L), fixed 35%.",
                 f"Index basis: {BASIS_LABEL}. Study end fixed at {STUDY_END}; Monte Carlo seed {rmc.SEED}."])
    print("\n".join(banner))
    t0 = time.perf_counter()
    named, ms = named_rows(w)
    print(f"  named points: {time.perf_counter() - t0:.0f} s")
    crv, plat, be = curve(w)
    print(f"  curve and break-even: {time.perf_counter() - t0:.0f} s")
    W = dict(index=dict(cagr=metrics.cagr(w.u), max_dd=metrics.max_drawdown(w.u), first=prov["first"], last=prov["last"], basis=BASIS_LABEL),
             named=named, multi_start=ms, curve=crv, plateau=plat, break_even=be, c13=c13(w), cost_sensitivity=cost_sensitivity(w),
             key_periods=key_periods(w), overlay=overlay(w), usd_overlay=usd_overlay(w),
             validation=dict(validation(), funds=list(VALIDATION_FUNDS),
                             anchor_rows=[dict(ticker=r["ticker"], start=r["start_date"], end=r["end_date"],
                                               nav_return_pct=float(r["total_return_nav_pct"])) for r in ANCHOR_ROWS],
                             soxx_index_in_window=soxx_index_on(ANCHOR_ROWS[0]["end_date"])),
             soxx_index_basis=[dict(first=a, last=b, index=c, status="SECONDARY") for a, b, c in SOXX_INDEX_BASIS])
    sy = soxx_yield()
    W["soxx_yield"] = sy
    for b in W["break_even"]:                      # the zero-fee shortfall with SOXX's recent mean yield added back (L - 1) times
        b["gap_at_zero_fee_with_soxx_yield"] = b["log_growth_gap_at_zero_fee"] + (b["L"] - 1.0) * sy["mean"]
    W["montecarlo"] = montecarlo(w)
    print(f"  Monte Carlo: {time.perf_counter() - t0:.0f} s")
    res = dict(meta=dict(title="B16: calendar-reset funds on semiconductors", run_date=str(pd.Timestamp.today().date()), caption=CAPTION,
                         study_end=STUDY_END, symbol=SYMBOL, basis=BASIS_LABEL, ls=list(LS), triggers=list(TRIGGERS), base_trigger=BASE_TRIGGER,
                         fee=FEE, spread_per_turn=SPREAD, usd_nport=dict(accession=USD_NPORT["accession"], period_end=USD_NPORT["period_end"],
                                                                          turns=USD_NPORT["swap_notional_over_nav"]),
                         cost_factors=COST_FACTORS, base_cost=BASE_COST, n_mc=N_MC, mc_block=MC_BLOCK, seed=rmc.SEED,
                         underlying=prov, inputs=inputs, banner=banner, code=provenance.code_fingerprint(__file__)), world=W)
    res["meta"]["timing"] = dict(total_wall_seconds=time.perf_counter() - wall0)
    (OUT / "semis.json").write_text(json.dumps(provenance.json_safe(res), indent=1, allow_nan=False) + "\n", encoding="utf-8")
    (OUT / "semis.md").write_text(markdown(res), encoding="utf-8")
    print(f"wrote results/semis.json and results/semis.md in {time.perf_counter() - wall0:.0f} s")


if __name__ == "__main__":
    main()
