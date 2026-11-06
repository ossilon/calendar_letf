"""Product registry: the live calendar funds, modeled calendar funds whose live counterparts were liquidated, and
their daily-reset twins.

kind tells you what a series IS, so a model can never be read as a real fund:
    LIVE          a fund that trades today (its model is still a model; validate it against the real NAV)
    MODELED      no live fund of this design exists today. A live fund of each MODELED design traded from
                  2024-08-30 to 2025-02-28 (SPYM = 2x SPY monthly, SPYB = 2x SPY weekly, QQQW = 2x QQQ weekly) and
                  was liquidated; its one published month is an out-of-sample check (validate.py, step 2). Every
                  banner says so. (Before R2 step 2 this kind was named HYPOTHETICAL and the README said weekly
                  products did not exist; the issuer's filings show they did.)
    DAILY_TWIN    a synthetic daily-reset 2x fund on the same index with the SAME fee, rate and spread as the
                  calendar funds, so the reset rule is the only difference
    REAL_FUND     a real daily fund used as an overlay (e.g. SSO, QLD), with its own costs (none registered yet)

    from calendar_letf.products import PRODUCTS, banner, twin_of
    spec = PRODUCTS["MQQQ"]
    twin = twin_of(spec)          # the daily twin to compare MQQQ with: same index, L, fee, spread and turns
    print(banner(spec, twin))

The registry twins TWIN_SPX_D and TWIN_NDX_D carry the modeled funds' ASSUMED 1.00% fee. To compare a
specific fund (e.g. MQQQ at 1.03%) with its daily twin, use twin_of(spec), so the two never differ in fee or costs.

Sources: Tradr calendar-reset ETFs prospectus dated 2026-07-31. Page numbers are PDF page numbers (the printed page
number is 3 lower on these pages), re-read on 2026-10-12: total annual fund operating expenses on pp.17 (SPYQ),
31 (MQQQ), 60 (QQQP); the -35% intra-period performance trigger on pp.19, 33, 62. The fee table excludes the
cost of the swaps, so the spread is charged on top of the fee. The liquidated funds: Investment Managers Series
Trust II semi-annual financial report for the period ended 2024-09-30 (note 1: commencement 2024-08-30, 200% of
the weekly or monthly return of SPY / QQQ; one-month NAV returns on pp.47, 50, 51) and the 497 supplements of
2025-01-27 (SPYB, QQQW) and 2025-01-31 (SPYM): trading through 2025-02-21, liquidation on or about 2025-02-28.
"""
from dataclasses import dataclass, replace

from .costs import (SPREAD_BASE, SPREAD_BASE_SOURCE, SPREAD_BASE_STATUS, SPREAD_SENSITIVITY, TURNS_2X,
                    TURNS_SOURCE, TURNS_STATUS, CostSpec, check_status, check_turns, describe, expected_turns)

KINDS = ("LIVE", "MODELED", "DAILY_TWIN", "REAL_FUND")
MODELED_NOTE = "MODELED: a live fund of this design traded 2024-08-30 to 2025-02-28; no live fund exists today"
LIQUIDATED_SOURCE = ("semi-annual financial report to 2024-09-30 (Investment Managers Series Trust II), note 1 and "
                     "financial highlights; 497 supplements 2025-01-27 / 2025-01-31: last trade 2025-02-21, "
                     "liquidation on or about 2025-02-28")
UNDERLYINGS = ("SPX", "NDX", "SOX")          # SOX: the PHLX Semiconductor Sector Index (BACKLOG B16; price only)
RESETS = ("daily", "weekly", "monthly", "quarterly")

PROSPECTUS = "Tradr calendar-reset ETFs prospectus dated 2026-07-31"
PROSPECTUS_STATUS = "VERIFIED_prospectus_2026-07-31"


@dataclass(frozen=True)
class ProductSpec:
    """One product. The fee lives in `costs` (with its status and source); `spec.fee` reads it from there."""
    name: str                     # "SPYQ", "HYP_SPX_W", "TWIN_NDX_D" ...
    kind: str                     # one of KINDS
    underlying: str               # "SPX" or "NDX"
    reset: str                    # one of RESETS
    costs: CostSpec
    early_drop: float | None      # 0.35 = reset early after a 35% in-period fall; None for daily funds
    early_drop_status: str        # VERIFIED_... / ASSUMED / OPEN; NOT_APPLICABLE for daily-reset funds
    early_drop_source: str
    L: float = 2.0
    inception: str | None = None  # live funds only, ISO date
    note: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: kind must be one of {KINDS}")
        if self.underlying not in UNDERLYINGS:
            raise ValueError(f"{self.name}: underlying must be one of {UNDERLYINGS}")
        if self.reset not in RESETS:
            raise ValueError(f"{self.name}: reset must be one of {RESETS}")
        if not self.L >= 1.0:
            raise ValueError(f"{self.name}: L must be >= 1 (long funds only)")
        check_turns(self.costs, self.L)       # turns must match L (notional basis: turns = L), or this raises
        if self.reset == "daily":
            if self.early_drop is not None or self.early_drop_status != "NOT_APPLICABLE":
                raise ValueError(f"{self.name}: a daily-reset fund has no in-period trigger; use early_drop=None "
                                 "and early_drop_status='NOT_APPLICABLE'")
        else:
            check_status(self.early_drop_status, f"{self.name} early_drop")
            if self.early_drop is not None and not 0.0 < self.early_drop < 1.0:
                raise ValueError(f"{self.name}: early_drop must be between 0 and 1 (0.35 = 35%) or None")
        if self.kind == "DAILY_TWIN" and self.reset != "daily":
            raise ValueError(f"{self.name}: a DAILY_TWIN must have reset 'daily'")
        if self.kind == "LIVE" and not self.inception:
            raise ValueError(f"{self.name}: a LIVE product needs its inception date")

    @property
    def fee(self):
        return self.costs.fee

    def warnings(self):
        out = list(self.costs.warnings())
        if self.reset != "daily" and not self.early_drop_status.startswith("VERIFIED"):
            out.append(f"{self.name}: early-reset trigger {self.early_drop} is {self.early_drop_status} "
                       f"({self.early_drop_source})")
        return out


def _costs(label, fee, fee_status, fee_source):
    """Cost spec for a 2x product: the shared base spread (ASSUMED) on 2 turns (notional basis, L = 2)."""
    return CostSpec(fee=fee, fee_status=fee_status, fee_source=fee_source,
                    spread=SPREAD_BASE, spread_status=SPREAD_BASE_STATUS, spread_source=SPREAD_BASE_SOURCE,
                    turns=TURNS_2X, turns_status=TURNS_STATUS, turns_source=TURNS_SOURCE, spread_basis="notional",
                    label=label)


def _live(name, underlying, reset, fee, fee_page, trigger_page, inception, note):
    return ProductSpec(
        name=name, kind="LIVE", underlying=underlying, reset=reset,
        costs=_costs(name, fee, PROSPECTUS_STATUS,
                     f"{PROSPECTUS}, p.{fee_page}: total annual fund operating expenses (excludes swap costs)"),
        early_drop=0.35, early_drop_status=PROSPECTUS_STATUS,
        early_drop_source=f"{PROSPECTUS}, p.{trigger_page}: intra-period performance trigger -35%",
        inception=inception, note=note)


_MOD_FEE_SOURCE = ("same as the live funds today (1.00% for SPYQ and QQQP); the liquidated fund of this design paid "
                   "the 1.30% expense cap while it traded")
_MOD_TRIGGER_SOURCE = "same -35% trigger as the live funds; the liquidated fund of this design had the same trigger"


def _modeled(name, underlying, reset, live_ticker, live_name, note):
    """A design with no live fund today. `live_ticker` / `live_name` record the fund that traded 2024-08-30 to
    2025-02-28 under this design, with the filing that says so, so the note can never read as "never existed"."""
    return ProductSpec(
        name=name, kind="MODELED", underlying=underlying, reset=reset,
        costs=_costs(name, 0.0100, "ASSUMED", _MOD_FEE_SOURCE),
        early_drop=0.35, early_drop_status="ASSUMED", early_drop_source=_MOD_TRIGGER_SOURCE,
        note=f"{note}. Live counterpart: {live_ticker} ({live_name}), traded 2024-08-30 to 2025-02-28, liquidated; "
             f"source: {LIQUIDATED_SOURCE}")


def _twin(name, underlying, note):
    return ProductSpec(
        name=name, kind="DAILY_TWIN", underlying=underlying, reset="daily",
        costs=_costs(name, 0.0100, "ASSUMED",
                     "same fee as the calendar funds so the reset rule is the only difference"),
        early_drop=None, early_drop_status="NOT_APPLICABLE", early_drop_source="resets every day",
        note=note)


PRODUCTS = {
    "SPYQ": _live("SPYQ", "SPX", "quarterly", 0.0100, 17, 19, "2024-09-30",
                  "Tradr 2X Long SPY Quarterly ETF: 2x the calendar-quarter return of SPY via swaps"),
    "MQQQ": _live("MQQQ", "NDX", "monthly", 0.0103, 31, 33, "2024-08-30",
                  "Tradr 2X Long Innovation 100 Monthly ETF: 2x the calendar-month return of QQQ via swaps"),
    "QQQP": _live("QQQP", "NDX", "quarterly", 0.0100, 60, 62, "2024-09-30",
                  "Tradr 2X Long Innovation 100 Quarterly ETF: 2x the calendar-quarter return of QQQ via swaps"),
    "HYP_SPX_M": _modeled("HYP_SPX_M", "SPX", "monthly", "SPYM", "Tradr 2X Long SPY Monthly ETF", "2x S&P 500, monthly reset"),
    "HYP_SPX_W": _modeled("HYP_SPX_W", "SPX", "weekly", "SPYB", "Tradr 2X Long SPY Weekly ETF", "2x S&P 500, weekly reset"),
    "HYP_NDX_W": _modeled("HYP_NDX_W", "NDX", "weekly", "QQQW", "Tradr 2X Long Triple Q Weekly ETF", "2x Nasdaq-100, weekly reset"),
    "TWIN_SPX_D": _twin("TWIN_SPX_D", "SPX", "2x S&P 500, daily reset, calendar-fund costs"),
    "TWIN_NDX_D": _twin("TWIN_NDX_D", "NDX", "2x Nasdaq-100, daily reset, calendar-fund costs"),
}


def twin_of(spec):
    """The DAILY_TWIN of a calendar product: same underlying, L, fee, spread, turns and rate; resets daily.

    The costs are copied from `spec` (only the label changes, and the fee source says where it was copied from),
    so a twin can never carry a different fee or spread from the fund it is compared with. This also holds for a
    sensitivity copy made with dataclasses.replace: its changed costs are copied too.
    """
    if spec.reset == "daily":
        raise ValueError(f"{spec.name} already resets daily; twin_of() is for calendar-reset products")
    name = f"TWIN_{spec.name}"
    twin_costs = replace(spec.costs, label=name, fee_source=f"copied from {spec.name}: {spec.costs.fee_source}")
    return ProductSpec(
        name=name, kind="DAILY_TWIN", underlying=spec.underlying, reset="daily", costs=twin_costs,
        early_drop=None, early_drop_status="NOT_APPLICABLE", early_drop_source="resets every day", L=spec.L,
        note=f"daily-reset twin of {spec.name}: same index, L and costs; only the reset rule differs")


# ---------------------------------------------------------------- the same design at another leverage (BACKLOG B17)
TRIGGER_RULES = ("none", "scaled", "fixed35")
SCALED_FUND_LOSS = 0.70       # "scaled": reset early at the index fall that costs the fund 70%, as 35% does at 2x


def trigger_for(L, rule):
    """(early_drop, source) for a calendar fund at leverage L under one of TRIGGER_RULES.

    none     no intra-period reset, so an in-period index fall of 1/L wipes the fund out (-83.3% at 1.2x, -33.3% at 3x)
    scaled   early reset at an index fall of 0.70 / L: the same 70% fund loss as the 35% trigger at 2x (23.3% at 3x)
    fixed35  the 35% trigger of the live 2x funds at any L; at L >= 1 / 0.35 = 2.857 a 35% fall has already wiped the
             fund out, so this rule can never fire first (the 3x case, BACKLOG B1)
    """
    if rule == "none":
        return None, "no intra-period reset: an in-period index fall of 1/L wipes the fund out"
    if rule == "scaled":
        drop = SCALED_FUND_LOSS / float(L)
        return drop, f"early reset at a {drop:.2%} index fall: the same {SCALED_FUND_LOSS:.0%} fund loss as 35% at 2x"
    if rule == "fixed35":
        return 0.35, "the -35% trigger of the live 2x funds, kept at this L"
    raise ValueError(f"trigger rule must be one of {TRIGGER_RULES}, got {rule!r}")


def at_leverage(base, L, trigger="scaled", basis="notional"):
    """The design of the calendar product `base` (underlying, reset, fee) at leverage L: a HYPOTHETICAL product.

    trigger  one of TRIGGER_RULES (trigger_for). basis: the balance-sheet structure that sets the swap turns that pay
    the spread: "notional" (all swap, turns = L) or "borrowed" (the index held directly, a swap for the excess,
    turns = L - 1). Both are modeling choices (ASSUMED). The fee is base's; a caller sets another with
    dataclasses.replace. The daily twin at the same L and costs is twin_of(at_leverage(...)).
    """
    if base.kind == "REAL_FUND":
        raise ValueError(f"{base.name} models a real fund at its filed terms; it cannot be moved to another leverage")
    if base.reset == "daily":
        raise ValueError(f"{base.name} resets daily; build the calendar design at L, then take twin_of() of it")
    L = float(L)
    turns = expected_turns(L, basis)
    if turns is None:
        raise ValueError("basis 'swaps' has no rule for turns at another leverage; use 'notional' or 'borrowed'")
    drop, drop_source = trigger_for(L, trigger)
    name = f"{base.name}_L{L:.2f}_{trigger}" + ("" if basis == "notional" else f"_{basis}")
    costs_at_L = replace(base.costs, turns=turns, spread_basis=basis, turns_status="ASSUMED", label=name,
                         turns_source=f"{basis} basis at L = {L:g}: the balance-sheet structure is a modeling choice (B17)")
    return ProductSpec(
        name=name, kind="MODELED", underlying=base.underlying, reset=base.reset, costs=costs_at_L,
        early_drop=drop, early_drop_status="ASSUMED", early_drop_source=drop_source, L=L,
        note=f"HYPOTHETICAL: the {base.reset} design of {base.name} at L = {L:g}; trigger rule '{trigger}'; "
             f"spread on the {basis} basis")


def at_leverage_filed(base, L, model, drop, drop_source, name):
    """The calendar design of `base` (underlying, reset, fee) at leverage L with the swap terms of `model`, a model of a
    real fund at its FILED terms (spread per turn and swap turns from SEC N-PORT, "swaps" basis; MODELS_3X). A
    HYPOTHETICAL product (BACKLOG B1: no 3x calendar fund exists). drop is the early-reset index fall (None: no early
    reset; at L = 3 a fall of 1/3 wipes the fund out, so a drop at or above 1/3 can never fire first)."""
    if base.reset == "daily":
        raise ValueError(f"{base.name} resets daily; build the calendar design, then take twin_of() of it")
    if model.kind != "REAL_FUND" or model.costs.spread_basis != "swaps":
        raise ValueError(f"{model.name} is not a model of a real fund at its filed swap terms")
    if model.underlying != base.underlying:
        raise ValueError(f"{model.name} is on {model.underlying}, the design on {base.underlying}")
    c = model.costs
    costs = replace(base.costs, spread=c.spread, spread_status=c.spread_status, spread_source=f"{model.name}: {c.spread_source}",
                    turns=c.turns, turns_status=c.turns_status, turns_source=f"{model.name}: {c.turns_source}",
                    spread_basis="swaps", label=name)
    return ProductSpec(
        name=name, kind="MODELED", underlying=base.underlying, reset=base.reset, costs=costs, early_drop=drop,
        early_drop_status="ASSUMED", early_drop_source=drop_source, L=float(L),
        note=f"HYPOTHETICAL: the {base.reset} design of {base.name} at L = {L:g} with {model.name}'s filed swap terms")


# ---------------------------------------------------------------- 3x daily MODELS of real funds (BACKLOG B13)
# A separate dict, NOT part of PRODUCTS: PRODUCTS is the list of calendar funds and their 2x twins (the step-1 tests
# pin its exact contents). These two are models of real 3x daily funds at their FILED terms, used by the
# "entries from bottoms" study (bottoms.py) as a comparator. They are models, not the funds' NAVs.
#
# Terms copied from a private financing kit (SEC N-PORT filings, period end 2026-05-31, read 2026-10-03 in the
# author's earlier work; UPRO accession 0002071691-26-017443, TQQQ 0002071691-26-017348). Spread = notional-weighted over
# the fund's swaps, quoted over effective fed funds; turns = swap notional / NAV ("swaps" basis, so check_turns does
# not tie it to L). The kernel charges (L - 1) x rate = 2 turns of the reference rate for L = 3: this is the letf
# convention (a 3x fund borrows 2 NAVs), plus spread x turns plus the fee, all as fractions of NAV.
_NPORT_STATUS = "VERIFIED_NPORT_2026-05-31"


def _model_3x(name, underlying, spread, turns, fee, fee_status, fee_source, accession):
    costs = CostSpec(
        fee=fee, fee_status=fee_status, fee_source=fee_source,
        spread=spread, spread_status=_NPORT_STATUS, spread_source=f"SEC N-PORT {accession} (period end 2026-05-31), over fed funds",
        turns=turns, turns_status=_NPORT_STATUS, turns_source=f"SEC N-PORT {accession}: swap notional / NAV",
        spread_basis="swaps", label=name)
    return ProductSpec(
        name=name, kind="REAL_FUND", underlying=underlying, reset="daily", costs=costs,
        early_drop=None, early_drop_status="NOT_APPLICABLE", early_drop_source="resets every day", L=3.0,
        note=f"MODEL of the real 3x daily fund on {underlying} at its filed terms, not the fund's NAV; run at the plain "
             "reference rate (these costs are filed, not fitted, so no residual encoding)")


MODELS_3X = {
    "UPRO_MODEL": _model_3x("UPRO_MODEL", "SPX", 0.009218, 2.4215, 0.0089, "VERIFIED_issuer_page_2026-09-25_RECHECK",
                            "UPRO issuer page 2026-09-25 (re-check)", "0002071691-26-017443"),
    "TQQQ_MODEL": _model_3x("TQQQ_MODEL", "NDX", 0.010576, 2.5630, 0.0082, "ASSUMED",
                            "0.82% as given in the B13 brief (issuer page); no TQQQ expense ratio is on file, so not "
                            "re-verified here", "0002071691-26-017348"),
}
MODEL_3X_FOR = {"SPX": "UPRO_MODEL", "NDX": "TQQQ_MODEL"}


def banner(*specs, overrides=""):
    """Provenance paragraph for one or more products: kind, reset, L, costs with statuses, and labels that stop a
    modeled or synthetic series being read as a real fund."""
    lines = []
    for p in specs:
        trigger = (f"early reset at -{p.early_drop:.0%} [{p.early_drop_status}]" if p.early_drop
                   else "no early reset")
        lines.append(f"PRODUCT {p.name}: kind={p.kind} underlying={p.underlying} reset={p.reset} L={p.L:g} "
                     f"{trigger}" + (f" inception={p.inception}" if p.inception else ""))
        lines.append("  costs: " + describe(p.costs))
        if p.kind == "MODELED":
            lines.append("  " + MODELED_NOTE)
        if p.kind == "DAILY_TWIN":
            lines.append("  DAILY TWIN: synthetic comparison series")
    lines.append(f"SPREAD SENSITIVITY: the registry spread ({SPREAD_BASE:.2%} per turn) is a default that every published table "
                 f"overrides (the two historical encodings or the filed spread); sensitivity range {SPREAD_SENSITIVITY[0]:.2%} to "
                 f"{SPREAD_SENSITIVITY[1]:.2%} per turn; no calendar fund publishes its swap spread")
    if overrides:
        lines.append("OVERRIDES: " + overrides)
    w = [x for p in specs for x in p.warnings()]
    lines += ["WARNING: " + x for x in w] if w else ["all product inputs verified"]
    return "\n".join(lines)
