"""The backtest overlay (step 4): turn a plugin's exposure signal into a wealth path, with a delay and trading costs.

Plain-English map
  * A strategy plugin (strategies/) returns, for every trading day, how much of the PRODUCT to hold: 1.0 = all in the
    fund, 0.0 = all in cash, NaN = no signal yet. It knows nothing about money.
  * This module is the only place that decides WHEN a signal is acted on and what trading costs.
        exposure[t] is decided on the close of row t.
        With delay d the trade is made at the close of row t+d and the position is held over the return from the
        close of row t+d to the close of row t+d+1.   Base delay d = 1 (signal on today's close, fill at the next
        close); delays 2 and 3 are also run.
  * Wealth, with w the position held over the return into row t and w_prev the position before it:
        W[t] = W[t-1] x (1 + w x r_prod[t] + (1 - w) x r_cash[t]) - |w - w_prev| x half_spread x W[t-1]
    r_prod is the product's NAV return, r_cash what cash earns (3-month T-bill, FRED DTB3, known the day before; DTB3 is
    a bank-discount rate and is converted to an investment yield before it accrues, see `cash_returns`).
    Buying mid-period gets the product's floated leverage automatically: the investor holds NAV units.
  * The trading cost is `half_spread` per unit of position changed. A full round trip (buy, then sell) changes the
    position by 1 twice, so it costs exactly 2 half-spreads. (DESIGN section 7 writes the cost as |dw| x 2 x half_spread
    and also says "a round trip costs two half-spreads"; both cannot hold. The round-trip sentence is the economic
    meaning of a half-spread, so that is what is implemented. `cost_mult=2.0` gives the literal formula as a
    sensitivity, and the study script reports it.)
  * The run starts at the strategy's first valid signal (no trade before it) with wealth 1.0 on the first fill close,
    already holding the first position: the first purchase is not charged, for the strategy AND the passive
    benchmark alike, so an "always 1.0" strategy equals the passive product exactly.
  * The wealth loop is a numba @njit function (compiled to machine code); tests/test_strategies.py checks it against
    a plain-Python loop to 1e-12.

Nothing here is a result; scripts/run_strategies.py records results with their provenance.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from numba import njit

from . import indicators, loader, periods
from .strategies.base import SignalContext, check_exposure

# ---------------------------------------------------------------- trading cost assumptions

HALF_SPREADS = {
    "tradr_live": dict(value=0.0010, status="ASSUMED",
                       source="DESIGN section 7 / PROMPT.md STRATEGIES: thin Tradr funds (QQQP ~4k shares a day, SPYQ ~4.5k); "
                              "not measured from quotes. Sensitivity: the study also reports twice this cost"),
    "modeled_or_twin": dict(value=0.0002, status="ASSUMED",
                             source="DESIGN section 7: a liquid SPY/QQQ-like product; modeled products (no live fund of the design "
                                    "trades today) and daily twins do not trade, so this is a stand-in"),
}
LIVE_PRODUCTS = ("SPYQ", "MQQQ", "QQQP")


def half_spread_key(product_name):
    """Which row of HALF_SPREADS a product uses: the three live Tradr funds, else the modeled / twin value."""
    return "tradr_live" if product_name in LIVE_PRODUCTS else "modeled_or_twin"


def half_spread_for(product_name):
    return HALF_SPREADS[half_spread_key(product_name)]["value"]


# ---------------------------------------------------------------- the wealth loop

@njit(cache=True)
def wealth_loop(r_prod, r_cash, w, half_spread, w_init):
    """Wealth path (starting at 1.0 on row 0) for position w[t] held over the return into row t (w[0] is unused).

    cost on row t = |w[t] - w[t-1]| x half_spread x wealth[t-1], with w[0] taken as w_init (so w_init = w[1] means no
    charge for the first position). Returns the wealth array."""
    n = r_prod.shape[0]
    wealth = np.empty(n)
    wealth[0] = 1.0
    prev = w_init
    for t in range(1, n):
        wt = w[t]
        cost = abs(wt - prev) * half_spread
        wealth[t] = wealth[t - 1] * (1.0 + wt * r_prod[t] + (1.0 - wt) * r_cash[t]) - cost * wealth[t - 1]
        prev = wt
    return wealth


def held_weights(exposure, delay):
    """The position held over the return INTO each row: held[s] = exposure[s - 1 - delay] (NaN where there is none).

    A signal decided on the close of row t is filled at the close of row t+delay and earns the return into row
    t+delay+1."""
    if delay < 0:
        raise ValueError("delay must be >= 0 (0 would trade on the close that made the signal)")
    n = len(exposure)
    held = np.full(n, np.nan)
    if delay + 1 < n:
        held[delay + 1:] = exposure[:n - delay - 1]
    return held


@dataclass
class OverlayRun:
    first_signal: int       # row of the first valid signal
    start: int              # row of the first fill close (= first_signal + delay): wealth is 1.0 here
    delay: int
    half_spread: float      # cost per unit of position changed, as used (after cost_mult)
    wealth: np.ndarray      # length n, NaN before `start`
    held: np.ndarray        # length n, the position held over the return into each row, NaN up to and including `start`


def run_overlay(r_prod, r_cash, exposure, delay, half_spread, cost_mult=1.0, first_signal=None):
    """Wealth path of an exposure signal. r_prod / r_cash: simple returns into each row (row 0 unused), same length as
    exposure. first_signal: start no earlier than this row (default: the first valid signal)."""
    r_prod = np.ascontiguousarray(r_prod, dtype=np.float64)
    r_cash = np.ascontiguousarray(r_cash, dtype=np.float64)
    n = len(r_prod)
    if len(r_cash) != n or len(exposure) != n:
        raise ValueError("r_prod, r_cash and exposure must have the same length")
    exposure = check_exposure(exposure, n)
    fin = np.isfinite(exposure)
    if not fin.any():
        raise ValueError("the strategy never gives a valid signal on this history")
    v = int(np.argmax(fin))
    if first_signal is not None:
        if first_signal < v:
            raise ValueError(f"first_signal {first_signal} is before the first valid signal ({v})")
        v = int(first_signal)
    a = v + delay
    if a + 2 > n:
        raise ValueError("not enough rows after the first signal to hold a position")
    held = held_weights(exposure, delay)
    w_local = held[a:].copy()
    w_local[0] = w_local[1]                       # row `a` has no return of its own; keep the array free of NaN
    cost = half_spread * cost_mult
    wealth_local = wealth_loop(r_prod[a:], r_cash[a:], w_local, cost, float(w_local[1]))
    wealth = np.full(n, np.nan)
    wealth[a:] = wealth_local
    held[:a + 1] = np.nan
    return OverlayRun(first_signal=v, start=a, delay=delay, half_spread=cost, wealth=wealth, held=held)


# ---------------------------------------------------------------- inputs: returns, cash, signal context

def returns_from_level(level):
    """Simple returns into each row of a level array; 0.0 on row 0 and wherever the previous level is not positive."""
    v = np.asarray(level, dtype=np.float64)
    out = np.zeros(len(v))
    prev = v[:-1]
    ok = prev > 0
    out[1:][ok] = v[1:][ok] / prev[ok] - 1.0
    return out


def cash_rate_with_proxy(index):
    """What cash earns in strategy tests, for each row of `index`: FRED DTB3 (3-month T-bill) known the day before.

    DTB3 starts 1954-01-04. Rows before that use TB3MS (monthly average, shifted forward one month so a month's average
    is never used inside its own month) as a PROXY, as the financing rate does (loader.reference_rate). The result
    carries attrs proxy_rows / proxy_until / source so tables can flag those years."""
    index = pd.DatetimeIndex(index)
    dtb = loader.load_fred("DTB3")
    proxy_rows = 0
    spliced = dtb
    if index[0] <= dtb.index[0]:
        tb = loader.tb3ms_prior_month(loader.load_fred("TB3MS"))
        spliced = pd.concat([tb[tb.index < dtb.index[0]], dtb])
        proxy_rows = int((index <= dtb.index[0]).sum())
    loader.check_rate_holes(dtb, index[index > dtb.index[0]], 10, "DTB3")          # the daily part only; TB3MS is monthly
    out = loader.rate_known_before(index, spliced, "DTB3", max_stale_rows=15, max_hole_days=None)
    out.name = "cash_rate"
    out.attrs["proxy_rows"] = proxy_rows
    out.attrs["proxy_until"] = str(index[index <= dtb.index[0]][-1].date()) if proxy_rows else None
    out.attrs["source"] = ("FRED DTB3 (3-month T-bill), lagged one row; TB3MS prior-month average as a proxy before "
                           f"{dtb.index[0].date()}")
    out.attrs["basis"] = "bank discount, 360-day year (convert with discount_to_investment_yield; cash_returns does)"
    return out


BILL_DAYS = 91          # days to maturity of the 3-month bill in the discount-to-yield formula


def discount_to_investment_yield(discount, days=BILL_DAYS):
    """Investment (bond-equivalent) yield of a Treasury bill quoted on a bank-discount basis.

        yield = 365 d / (360 - days x d)        d = the discount rate as a decimal, days = days to maturity

    FRED DTB3 is the bill's discount rate: price = 100 x (1 - d x days / 360). An investor who pays that price and
    receives 100 earns 100 / price - 1 = d x days / (360 - days x d) over `days` days, i.e. 365 d / (360 - days x d) a year
    on a 365-day basis, which is the basis the cash leg accrues on. At d = 5% the yield is 5.134% (+0.134 pp); at
    d = 1% it is 1.016% (+0.016 pp). Works on a number or an array."""
    d = np.asarray(discount, dtype=np.float64)
    out = 365.0 * d / (360.0 - days * d)
    return float(out) if out.ndim == 0 else out


def cash_returns(index, cash_rate, discount_basis=True):
    """Cash return into each row: annual rate x calendar days since the previous row / 365 (the kernel's accrual rule).

    cash_rate is FRED DTB3 (or the TB3MS proxy before 1954), both quoted as a bank-discount rate on a 360-day year.
    With discount_basis=True (the default) it is converted to the investment yield first
    (discount_to_investment_yield; R2 step 3, audit F4). discount_basis=False reproduces the earlier runs, which accrued
    the discount rate as if it were a yield (about 0.13 pp a year too little at 5%)."""
    rate = np.asarray(cash_rate, dtype=np.float64)
    if discount_basis:
        rate = discount_to_investment_yield(rate)
    return rate * periods.accrual_fraction(index)


def make_context(dates, close, product_nav, close_tr=None):
    """SignalContext from arrays; week_last from indicators.week_end_rows (the final row counts as a week end)."""
    dates = pd.DatetimeIndex(dates)
    week_last = np.zeros(len(dates), dtype=bool)
    week_last[indicators.week_end_rows(dates)] = True
    return SignalContext(dates=dates, close=np.asarray(close, dtype=np.float64), close_tr=close_tr,
                         product_nav=np.asarray(product_nav, dtype=np.float64), week_last=week_last)


def signal_from(strategy, ctx, row=0):
    """The exposure array for an investor who starts at `row`. A path-dependent rule (drawdown stop) is given only the
    history from `row` on, so its running peak starts there; any other rule is computed on the full history (it only
    looks backwards, so the value at row t is the same either way) and set to NaN before `row`."""
    n = len(ctx)
    if row == 0:
        return check_exposure(strategy.exposure(ctx), n, strategy.name)
    out = np.full(n, np.nan)
    if strategy.path_dependent:
        out[row:] = check_exposure(strategy.exposure(ctx.tail_from(row)), n - row, strategy.name)
    else:
        out[row:] = check_exposure(strategy.exposure(ctx), n, strategy.name)[row:]
    return out


# ---------------------------------------------------------------- statistics of a held-position path

def trade_stats(held, min_spell=10):
    """Trade counts from the positions held over a window (no NaN). A trade is any change of position.

    entries / exits   0 -> invested and invested -> 0 (invested = position above 0.5)
    whipsaws_in       complete in-market spells (entry then exit, both inside the window) shorter than `min_spell` rows
    whipsaws_cash     complete cash spells (exit then entry) shorter than `min_spell` rows
    invested_share    average position over the window (time-weighted)
    The spell at each end of the window is cut off by the window, so it is never counted as a whipsaw."""
    x = np.asarray(held, dtype=np.float64)
    if len(x) == 0:
        return dict(trades=0, entries=0, exits=0, whipsaws_in=0, whipsaws_cash=0, invested_share=float("nan"))
    trades = int((np.abs(np.diff(x)) > 1e-12).sum())
    inv = (x > 0.5).astype(np.int8)
    d = np.diff(inv)
    entries, exits = int((d == 1).sum()), int((d == -1).sum())
    cuts = np.flatnonzero(d != 0) + 1
    starts = np.r_[0, cuts]
    lens = np.r_[cuts, len(inv)] - starts
    state = inv[starts].astype(bool)
    complete = np.ones(len(lens), dtype=bool)
    complete[0] = False
    complete[-1] = False
    short = lens < min_spell
    return dict(trades=trades, entries=entries, exits=exits, whipsaws_in=int((short & state & complete).sum()),
                whipsaws_cash=int((short & ~state & complete).sum()), invested_share=float(x.mean()))
