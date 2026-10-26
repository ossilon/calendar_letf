"""Cost inputs for the synthetic funds. Every number carries a status and a source; nothing is silently assumed.

A 2x fund costs its holder three things a year, each a fraction of NAV (net asset value: what the fund is worth):

  1. carry   = (L - 1) x reference rate     interest on the borrowed turn. L is the leverage (2 for a 2x fund),
                                             so a 2x fund borrows 1 turn (one extra NAV's worth of exposure).
  2. spread  = spread per turn x turns       what the swap counterparty charges ABOVE the reference rate, on the
                                             swap notional (the size of the swap). This package's default is the
                                             "notional basis": turns = L (2 for a 2x fund), the convention the
                                             an earlier private kit's spreads were fitted under. `turns` has no default,
                                             and check_turns() refuses a turns that does not match the basis and L.
                                             CAVEAT (ASSUMPTIONS section 6): the funds' own N-PORT filings show a
                                             different structure: ~40-60% of NAV held directly in the ETF plus
                                             swaps for the rest, so the spread is paid on roughly 1.5 turns, not
                                             2, at 0.75-1.00% over OBFR. The step-2 refit (ASSUMPTIONS section 6)
                                             superseded this default: every published table overrides it with one
                                             of the two cost encodings; the default stays ASSUMED and unused.
  3. fee     = expense ratio                 the manager's fee. The prospectus fee table excludes swap costs, so
                                             the fund pays the spread AND the fee.

The reference rate (FRED DFF, effective fed funds) is a PROXY: the filings name OBFR, the overnight bank funding
rate, which runs a few basis points below fed funds and exists on FRED only from 2016. The rate goes to the kernels
as a series that the caller has already lagged, so each day uses the rate known before it.

Status strings
    VERIFIED_<source>_<date>   read from a primary document on that date (e.g. VERIFIED_prospectus_2026-07-31)
    ASSUMED                    a modeling choice; results must show a sensitivity to it
    OPEN                       unknown: the value is None, and code that needs it raises until one is supplied

To run a sensitivity, make a changed copy rather than editing the original:
    from dataclasses import replace
    low = replace(spec, spread=SPREAD_SENSITIVITY[0], spread_source="sensitivity: low end of the F8 fit range")
"""
import math
from dataclasses import dataclass

# ---- spread: the one cost no calendar fund publishes ----
SPREAD_BASE = 0.011
SPREAD_BASE_STATUS = "ASSUMED"
SPREAD_BASE_SOURCE = ("an earlier private kit's calibration 2026-10-11, midpoint of MQQQ 1.43% and QQQP 0.77% "
                      "fitted on price return")
SPREAD_SENSITIVITY = (0.008, 0.014)      # low and high spread per turn: registry default; every published table overrides it

# ---- turns: how many NAVs of swap notional pay the spread ----
# Basis = the rule that ties turns to the leverage L (the same names as a private financing kit):
#   notional  turns = L        the spread is paid on the whole swap notional, L x NAV (this package's convention)
#   borrowed  turns = L - 1    only on the borrowed part
#   swaps     turns = the fund's real swap notional / NAV, read from its filing (no rule; must be sourced)
# An unlevered fund (L = 1) holds the index itself, needs no swap, and pays no spread: turns = 0 on every basis.
SPREAD_BASES = ("notional", "borrowed", "swaps")
TURNS_2X = 2.0                           # for the 2x products on the notional basis (L = 2)
TURNS_STATUS = "ASSUMED"
TURNS_SOURCE = ("notional basis, turns = L: the 2x convention an earlier private kit's spreads were fitted under "
                "(DESIGN 4.1). Contradicted by the N-PORT structure in ASSUMPTIONS section 6 (~1.5 swap turns plus a "
                "direct ETF holding); superseded by the step-2 refit and overridden in every published table")


def check_status(status, what):
    """Raise unless `status` is ASSUMED, OPEN, or VERIFIED_<something>."""
    ok = status in ("ASSUMED", "OPEN") or (isinstance(status, str) and status.startswith("VERIFIED_")
                                           and len(status) > len("VERIFIED_"))
    if not ok:
        raise ValueError(f"{what}: status must be VERIFIED_<source>_<date>, ASSUMED or OPEN, got {status!r}")


def _check_value(what, value, status, source):
    """A value and its status must agree: OPEN means unknown (None); anything else needs a decimal number."""
    check_status(status, what)
    if not (isinstance(source, str) and source.strip()):
        raise ValueError(f"{what}: give a source (for an OPEN value, say why it is unknown)")
    if status == "OPEN":
        if value is not None:
            raise ValueError(f"{what}: status OPEN means the value is unknown, so it must be None (got {value})")
        return
    if value is None:
        raise ValueError(f"{what}: value is None but status is {status}; use status OPEN for an unknown value")
    if not math.isfinite(value) or abs(value) >= 0.5:
        raise ValueError(f"{what}: {value} is not a sensible annual decimal (0.01 means 1%); is it a percentage?")


@dataclass(frozen=True)
class CostSpec:
    """The cost inputs of one product, each with its status and source. frozen=True: a spec cannot be edited in
    place, so a sensitivity run always makes a labeled copy (see the module docstring)."""
    fee: float | None             # annual expense ratio, decimal (0.01 = 1%)
    fee_status: str
    fee_source: str
    spread: float | None          # annual spread per turn over the reference rate, decimal
    spread_status: str
    spread_source: str
    turns: float                  # swap notional / NAV that pays the spread. No default: it depends on L
    turns_status: str
    turns_source: str
    spread_basis: str = "notional"    # the rule tying turns to L (SPREAD_BASES); check_turns() enforces it
    rate_name: str = "DFF"        # the reference rate the spread is quoted over
    label: str = ""               # short name used in banners, e.g. "MQQQ"

    def __post_init__(self):
        _check_value("fee", self.fee, self.fee_status, self.fee_source)
        _check_value("spread", self.spread, self.spread_status, self.spread_source)
        check_status(self.turns_status, "turns")
        if not (isinstance(self.turns_source, str) and self.turns_source.strip()):
            raise ValueError("turns: give a source")
        if (self.turns is None or isinstance(self.turns, bool) or self.turns_status == "OPEN"
                or not math.isfinite(self.turns) or self.turns < 0):
            raise ValueError(f"turns must be a known number >= 0, got {self.turns} ({self.turns_status})")
        if self.spread_basis not in SPREAD_BASES:
            raise ValueError(f"spread_basis must be one of {SPREAD_BASES}, got {self.spread_basis!r}")

    def warnings(self):
        """One line per input that is not VERIFIED, so tables can never hide an assumption."""
        name = self.label or "costs"
        out = []
        for what, value, status, source in (("fee", self.fee, self.fee_status, self.fee_source),
                                            ("spread", self.spread, self.spread_status, self.spread_source),
                                            ("turns", self.turns, self.turns_status, self.turns_source)):
            if not status.startswith("VERIFIED"):
                out.append(f"{name}: {what} {value} is {status} ({source})")
        return out


def expected_turns(L, basis):
    """Turns the basis implies at leverage L, or None for 'swaps' (read from a filing, so there is no rule)."""
    if basis not in SPREAD_BASES:
        raise ValueError(f"spread_basis must be one of {SPREAD_BASES}, got {basis!r}")
    if L <= 1.0:
        return 0.0                    # an unlevered fund holds the index itself: no swap, no spread
    if basis == "notional":
        return float(L)
    if basis == "borrowed":
        return L - 1.0
    return None


def check_turns(spec, L):
    """Raise unless spec.turns is what spec.spread_basis implies at leverage L (notional basis: turns = L;
    0 when L = 1). Called by products.ProductSpec, so no product can carry a 2x turns at another leverage."""
    want = expected_turns(L, spec.spread_basis)
    if want is not None and abs(spec.turns - want) > 1e-12:
        raise ValueError(f"{spec.label or 'costs'}: turns {spec.turns:g} does not match L = {L:g} on the "
                         f"{spec.spread_basis} basis (expected {want:g}); a wrong turns would mis-charge the spread")


def annual_fee(spec):
    """The expense ratio as a number; raises if it is OPEN (no silent defaults)."""
    if spec.fee is None:
        raise ValueError(f"{spec.label or 'costs'}: fee is OPEN ({spec.fee_source}); "
                         "supply one with dataclasses.replace(spec, fee=..., fee_status=..., fee_source=...)")
    return spec.fee


def spread_per_nav(spec):
    """Annual spread cost as a fraction of NAV = spread per turn x turns. Raises if the spread is OPEN."""
    if spec.spread is None:
        raise ValueError(f"{spec.label or 'costs'}: spread is OPEN ({spec.spread_source}); "
                         "supply one with dataclasses.replace(spec, spread=..., spread_status=..., spread_source=...)")
    return spec.spread * spec.turns


def _pct(x):
    return "OPEN" if x is None else f"{x:.2%}"


def describe(spec):
    """One line: fee, spread x turns, and the status of each."""
    name = (spec.label + ": ") if spec.label else ""
    spread_total = "OPEN" if spec.spread is None else f"{spec.spread * spec.turns:.2%}"
    return (f"{name}fee {_pct(spec.fee)} [{spec.fee_status}]; "
            f"spread {_pct(spec.spread)} per turn over {spec.rate_name} [{spec.spread_status}] "
            f"x {spec.turns:g} turns [{spec.turns_status}, {spec.spread_basis} basis] = {spread_total} of NAV a year")


def banner(*specs, overrides=""):
    """Provenance paragraph to print above any table that uses these costs (style of letf's financing.banner)."""
    lines = ["COST INPUTS (annual, decimal; rate " + ", ".join(sorted({s.rate_name for s in specs}))
             + " lagged by the caller so each day uses the rate known before it):"]
    lines += ["  " + describe(s) for s in specs]
    lines.append(f"SPREAD SENSITIVITY: the registry spread ({SPREAD_BASE:.2%} per turn) is a default that every published table "
                 f"overrides (the two historical encodings or the filed spread); sensitivity range {SPREAD_SENSITIVITY[0]:.2%} to "
                 f"{SPREAD_SENSITIVITY[1]:.2%} per turn; no calendar fund publishes its swap spread")
    if overrides:
        lines.append("OVERRIDES: " + overrides)
    w = [x for s in specs for x in s.warnings()]
    lines += ["WARNING: " + x for x in w] if w else ["all cost inputs verified"]
    return "\n".join(lines)
