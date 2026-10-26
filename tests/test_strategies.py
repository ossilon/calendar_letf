"""Known-answer tests for the strategy plugins and the backtest overlay (step 4). Made-up data only; no files needed.
Expected numbers are worked out by hand in the comments. The generic look-ahead test runs on EVERY registered plugin.
"""
import time

import numpy as np
import pandas as pd

from _harness import check, raises  # noqa: I001
from calendar_letf import backtest as bt
from calendar_letf import indicators as ind
from calendar_letf import strategies
from calendar_letf.strategies import base, drawdown_stop, guppy, trend, vol_threshold


def synth(n=4000, seed=1, start="2000-01-03"):
    """A made-up index with slow cycles (so trend and ribbon rules switch), noise, and a more volatile 'product' NAV.
    Returns a SignalContext. 2000-01-03 is a Monday, so rows 4, 9, 14, ... are Fridays."""
    idx = pd.bdate_range(start, periods=n)
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    sigma = np.where(np.sin(2 * np.pi * t / 700.0) > 0.5, 0.02, 0.007)       # calm and stormy spells (about 11% and 32% a year)
    logp = 0.0002 * t + 0.45 * np.sin(2 * np.pi * t / 900.0) + np.cumsum(rng.normal(0.0, 1.0, n) * sigma)
    close = 100.0 * np.exp(logp)
    nav = 100.0 * np.exp(np.cumsum(rng.normal(4e-4, 0.02, n)))
    return bt.make_context(idx, close, nav, close)


def py_wealth(r_prod, r_cash, w, hs, w_init):
    """Plain-Python version of the wealth loop, written the way DESIGN section 7 writes it."""
    out = [1.0]
    prev = w_init
    for t in range(1, len(r_prod)):
        old = out[-1]
        out.append(old * (1.0 + w[t] * r_prod[t] + (1.0 - w[t]) * r_cash[t]) - abs(w[t] - prev) * hs * old)
        prev = w[t]
    return np.array(out)


# ---- the wealth loop against a Python loop ----
rng = np.random.default_rng(5)
n = 500
rp, rc = rng.normal(0.0005, 0.02, n), np.full(n, 0.0001)
w = np.where(rng.random(n) < 0.3, 1.0, 0.0)
w[::7] = rng.random(len(w[::7]))                                # some fractional positions too
fast = bt.wealth_loop(rp, rc, w, 0.001, 0.0)
slow = py_wealth(rp, rc, w, 0.001, 0.0)
check("wealth loop (numba) equals the pure-Python loop to 1e-12 on 500 random days with fractional positions",
      np.max(np.abs(fast / slow - 1.0)) < 1e-12, np.max(np.abs(fast / slow - 1.0)))

# ---- costs: a round trip costs exactly two half-spreads ----
hs = 0.001
expo = np.zeros(50)
expo[10:20] = 1.0                                               # flat, in for 10 rows, flat again: one buy and one sell
run = bt.run_overlay(np.zeros(50), np.zeros(50), expo, 1, hs)
check("round trip: one buy and one sell with zero returns leave exactly (1 - hs)^2 of wealth", abs(run.wealth[-1] - (1 - hs) ** 2) < 1e-15, run.wealth[-1])
check("round trip: the loss is 2 half-spreads (0.20%) up to hs^2 (second-order term of the two multiplicative charges)",
      abs((1 - run.wealth[-1]) - 2 * hs) <= hs ** 2 + 1e-15)
run2 = bt.run_overlay(np.zeros(50), np.zeros(50), expo, 1, hs, cost_mult=2.0)
check("cost_mult=2 gives the literal DESIGN formula (|dw| x 2 x half_spread): a round trip costs 4 half-spreads", abs(run2.wealth[-1] - (1 - 2 * hs) ** 2) < 1e-15)
check("zero half-spread: no trading cost at all", bt.run_overlay(np.zeros(50), np.zeros(50), expo, 1, 0.0).wealth[-1] == 1.0)

# ---- always in = the passive product; always out = cash ----
rp = np.r_[0.0, rng.normal(0.0008, 0.02, 399)]
rc = np.r_[0.0, np.full(399, 0.0002)]
for d in (1, 2, 3):
    nan_prefix = np.r_[np.full(30, np.nan), np.ones(370)]       # the first valid signal is on row 30
    run = bt.run_overlay(rp, rc, nan_prefix, d, 0.001)
    a = 30 + d
    passive = np.cumprod(1.0 + rp[a + 1:])
    check(f"always 1.0 at delay {d}: wealth equals the passive product from the first fill close to 1e-12 (no charge for the first purchase)",
          run.start == a and run.wealth[a] == 1.0 and np.max(np.abs(run.wealth[a + 1:] / passive - 1.0)) < 1e-12 and np.isnan(run.wealth[:a]).all())
    zero = bt.run_overlay(rp, rc, np.zeros(400), d, 0.001)
    cash = np.cumprod(1.0 + rc[d + 1:])
    check(f"always 0.0 at delay {d}: wealth equals cash compounding to 1e-12", np.max(np.abs(zero.wealth[d + 1:] / cash - 1.0)) < 1e-12)

# ---- the delay shift: a signal on row t affects the return from row t+delay to t+delay+1 ----
rp = np.r_[0.0, rng.normal(0.0, 0.02, 59)]
for d in (1, 2, 3):
    k = 10
    expo = np.zeros(60)
    expo[k] = 1.0                                               # the only 1.0 is decided on the close of row k
    run = bt.run_overlay(rp, np.zeros(60), expo, d, 0.0)
    ratio = run.wealth[1 + d:] / np.r_[run.wealth[d:-1]]        # growth into each row after the start
    hit = k + d + 1                                             # the return into this row is the only one earned
    rows = np.arange(d + 1, 60)
    ok = all(abs(run.wealth[s] / run.wealth[s - 1] - (1 + rp[hit] if s == hit else 1.0)) < 1e-15 for s in rows)
    check(f"delay {d}: a signal on row {k} earns exactly the return into row {k + d + 1} and no other", ok)
    check(f"delay {d}: held positions line up (held[t+delay+1] = exposure[t])", bt.held_weights(expo, d)[k + d + 1] == 1.0 and np.nansum(bt.held_weights(expo, d)) == 1.0)
raises("delay must not be negative", lambda: bt.held_weights(np.zeros(5), -1), "delay")
raises("a strategy with no valid signal is refused", lambda: bt.run_overlay(np.zeros(5), np.zeros(5), np.full(5, np.nan), 1, 0.0), "never gives")
raises("exposure above 1 is refused", lambda: bt.run_overlay(np.zeros(5), np.zeros(5), np.array([0.5, 1.5, 0, 0, 0]), 1, 0.0), "[0, 1]")
raises("NaN after the first valid signal is refused", lambda: bt.run_overlay(np.zeros(6), np.zeros(6), np.array([0, 1, np.nan, 1, 1, 1.0]), 1, 0.0), "NaN after")

# ---- independent pandas check of the whole chain for trend_200d (zero costs, zero cash) ----
ctx = synth()
close = pd.Series(ctx.close)
sig = (close > close.rolling(200).mean()).astype(float).where(close.rolling(200).mean().notna())
r1 = close.pct_change().fillna(0.0).to_numpy()
for d in (1, 2, 3):
    run = bt.run_overlay(r1, np.zeros(len(r1)), strategies.make("trend_200d", kind="sma").exposure(ctx), d, 0.0)
    held = sig.shift(d + 1)                                     # independent route: signal row t earns the return into row t+d+1
    a = run.start
    pd_wealth = (1.0 + held * pd.Series(r1)).iloc[a + 1:].cumprod().to_numpy()
    check(f"trend_200d sma, delay {d}: engine wealth equals an independent pandas rolling/shift/cumprod calculation to 1e-12",
          held.iloc[a + 1:].notna().all() and np.max(np.abs(run.wealth[a + 1:] / pd_wealth - 1.0)) < 1e-12 and a == 199 + d)

# ---- multi-start ratio = a direct run from the start (stateless rule, zero cost) ----
strat = strategies.make("trend_200d", kind="ema")
run = bt.run_overlay(r1, np.full(len(r1), 0.0001), strat.exposure(ctx), 1, 0.0)
s, e = 1500, 2300
direct = bt.wealth_loop(r1[s:e + 1].copy(), np.full(e - s + 1, 0.0001), run.held[s:e + 1].copy(), 0.0, float(run.held[s + 1]))
check("a window of a stateless rule read as W[e]/W[s] equals a direct run over the window (zero cost) to 1e-12",
      abs(direct[-1] - run.wealth[e] / run.wealth[s]) < 1e-12, (direct[-1], run.wealth[e] / run.wealth[s]))

# ---- trade statistics by hand ----
ts = bt.trade_stats(np.array([1, 1, 0, 0, 1, 0, 1, 1.0]))
check("trade_stats: [1,1,0,0,1,0,1,1] -> 4 trades (2 entries, 2 exits), 1 complete short in-market spell, 2 complete short cash spells, 62.5% invested",
      (ts["trades"], ts["entries"], ts["exits"], ts["whipsaws_in"], ts["whipsaws_cash"]) == (4, 2, 2, 1, 2) and abs(ts["invested_share"] - 0.625) < 1e-15, ts)
ts2 = bt.trade_stats(np.r_[np.ones(5), np.zeros(30), np.ones(5)])
check("trade_stats: spells cut off by the window ends never count as whipsaws; a 30-row cash spell is not short",
      ts2["whipsaws_in"] == 0 and ts2["whipsaws_cash"] == 0 and ts2["trades"] == 2)

# ---- half-spread register ----
check("half-spreads: 0.10% for SPYQ / MQQQ / QQQP, 0.02% for modeled products and twins, each ASSUMED with a source",
      bt.half_spread_for("SPYQ") == 0.001 and bt.half_spread_for("MQQQ") == 0.001 and bt.half_spread_for("QQQP") == 0.001
      and bt.half_spread_for("HYP_SPX_M") == 0.0002 and bt.half_spread_for("TWIN_SPYQ") == 0.0002
      and all(v["status"] == "ASSUMED" and v["source"] for v in bt.HALF_SPREADS.values()))

# ---- trend rules ----
line = np.linspace(100.0, 200.0, 300)
dates = pd.bdate_range("2020-01-01", periods=300)
lc = bt.make_context(dates, line, line, line)
for kind in ("sma", "ema"):
    ex = strategies.make("trend_50d", kind=kind).exposure(lc)
    check(f"trend_50d ({kind}) on a straight rising line: NaN for the first 49 rows, then 1.0 on every row",
          np.isnan(ex[:49]).all() and (ex[49:] == 1.0).all())
fall = bt.make_context(dates, line[::-1].copy(), line, line)
check("trend_50d (sma) on a straight falling line: 0.0 after warm-up", (strategies.make("trend_50d").exposure(fall)[49:] == 0.0).all())
check("trend_200d on 150 rows: all NaN (the average does not exist yet), no error", np.isnan(strategies.make("trend_200d").exposure(base.SignalContext(
    dates[:150], line[:150], None, line[:150], lc.week_last[:150])) ).all())
raises("trend: kind must be sma or ema", lambda: strategies.make("trend_50d", kind="wma"), "kind")
raises("unknown parameter is refused", lambda: strategies.make("trend_50d", length=3), "unknown parameter")
raises("unknown strategy name is refused", lambda: strategies.make("no_such_rule"), "unknown strategy")
check("trend_50d known answer: close above the 3-day average? (SMA 3 on 1,2,3,2,1 -> NaN,NaN,2,2.33,2 vs close 3,2,1 -> 1,0,0)",
      np.array_equal(trend.above_average(np.array([1.0, 2.0, 3.0, 2.0, 1.0]), 3, "sma"), np.array([np.nan, np.nan, 1.0, 0.0, 0.0]), equal_nan=True))

# trend_200w only changes on week-end rows
for kind in ("sma", "ema"):
    st = strategies.make("trend_200w", kind=kind)
    ex = st.exposure(ctx)
    both = np.isfinite(ex[1:]) & np.isfinite(ex[:-1])
    change_rows = np.flatnonzero(both & (ex[1:] != ex[:-1])) + 1
    check(f"trend_200w ({kind}): the signal changes only on week-end rows ({len(change_rows)} changes found, all on last-trading-day-of-week rows)",
          len(change_rows) >= 2 and lc is not None and ctx.week_last[change_rows].all())
    first = int(np.argmax(np.isfinite(ex)))
    check(f"trend_200w ({kind}): first signal on a week-end row after about 200 weeks (row {first})", ctx.week_last[first] and 990 <= first <= 1010, first)

# weekly average known answer: closes 1..5 weekly, SMA 2 -> signal on week ends only, carried forward
wd = pd.bdate_range("2024-01-01", periods=15)                   # three Mon-Fri weeks
wc = np.repeat([10.0, 12.0, 9.0], 5) + np.tile([0.0, 0.1, 0.2, 0.3, 0.4], 3)
wctx = bt.make_context(wd, wc, wc, wc)
class _W2(trend._Trend):                                        # a 2-week toy version
    N, WEEKLY = 2, True
wex = _W2(kind="sma").exposure(wctx)
# week-end closes: 10.4, 12.4, 9.4; SMA2: NaN, 11.4, 10.9; signals: NaN, 1 (12.4>11.4), 0 (9.4<10.9)
check("weekly trend known answer: weeks close 10.4, 12.4, 9.4; SMA 2 -> signal NaN, 1, 0 carried forward over the following days",
      np.isnan(wex[:9]).all() and (wex[9:14] == 1.0).all() and wex[14] == 0.0, wex)

# ---- volatility threshold ----
c = 100.0 * np.exp(np.cumsum(np.random.default_rng(9).normal(0, 0.01, 200)))
v = vol_threshold.realized_vol(c, 21)
direct = np.std(np.diff(np.log(c))[100 - 21 + 0:100], ddof=1) * np.sqrt(252)      # returns into rows 80..100 -> window ending on row 100
check("vol_threshold: 21-day annualized volatility at row 100 equals std(ddof=1) of the 21 log returns into rows 80..100 x sqrt(252)",
      abs(v[100] - direct) < 1e-14 and np.isnan(v[:21]).all() and np.isfinite(v[21:]).all(), (v[100], direct))
flat = bt.make_context(pd.bdate_range("2020-01-01", periods=100), np.full(100, 100.0), np.full(100, 100.0), None)
check("vol_threshold: a flat price has zero volatility -> hold (1.0) from row 21", (strategies.make("vol_threshold").exposure(flat)[21:] == 1.0).all())
zig = np.where(np.arange(100) % 2 == 0, 100.0, 110.0)
check("vol_threshold: a price alternating by 10% is far above 25% a year -> cash (0.0)",
      (strategies.make("vol_threshold").exposure(bt.make_context(pd.bdate_range("2020-01-01", periods=100), zig, zig, None))[21:] == 0.0).all())

# ---- Guppy ----
state = np.array([0, 0, 1, 0, 0, -1, 0, 1])
check("guppy: hold-through-gray on states [0,0,1,0,0,-1,0,1] gives exposure [0,0,1,1,1,0,0,1] (starts flat, buys on +1, sells on -1, holds on gray)",
      np.array_equal(guppy.hold_through_gray(state), np.array([0, 0, 1, 1, 1, 0, 0, 1.0])))
check("guppy: a direct red->green->... jump sequence [-1,1,1,-1,0,1,-1,0] has 1 up-jump and 2 down-jumps (gray bars between do not count)",
      guppy.count_direct_jumps(np.array([-1, 1, 1, -1, 0, 1, -1, 0])) == (1, 2))
check("guppy: a sell straight from green to red works from ANY prior state ([1,-1] -> exposure [1,0])", np.array_equal(guppy.hold_through_gray(np.array([1, -1])), [1.0, 0.0]))
up = np.exp(np.linspace(0, 1, 400)) * 100.0
uctx = bt.make_context(pd.bdate_range("2020-01-01", periods=400), up, up, up)
g = strategies.make("guppy")
ex = g.exposure(uctx)
dg = g.diagnostics(uctx)
check("guppy on a rising line: NaN for 65 rows, then 1.0 on every row (enters once, never sells)",
      np.isnan(ex[:65]).all() and (ex[65:] == 1.0).all() and dg["buy_events"] == 1 and dg["sell_events"] == 0 and dg["jumps_total"] == 0, dg)
exf = strategies.make("guppy", filter_200=True).exposure(uctx)
check("guppy with the 200 EMA filter on a rising line: NaN for 199 rows, then 1.0 (close above the 200 EMA throughout)", np.isnan(exf[:199]).all() and (exf[199:] == 1.0).all())
dn = bt.make_context(pd.bdate_range("2020-01-01", periods=400), up[::-1].copy(), up, up)
check("guppy on a falling line: never buys (0.0 after warm-up)", (g.exposure(dn)[65:] == 0.0).all())
# weekly guppy: same as running the daily rule on the week-end closes (independent route) and carried forward
gw = strategies.make("guppy_weekly")
rows = np.flatnonzero(ctx.week_last)
sw = ind.guppy(ctx.close[rows])["slow_state"]
ew = guppy.hold_through_gray(sw)
ew[:65] = np.nan
exw = gw.exposure(ctx)
manual = np.full(len(ctx), np.nan)
for i, r in enumerate(rows):
    nxt = rows[i + 1] if i + 1 < len(rows) else len(ctx)
    manual[r:nxt] = ew[i]
check("guppy_weekly equals the daily rule applied to week-end closes and held over the following days", np.array_equal(exw, manual, equal_nan=True))
check("guppy_weekly: changes only on week-end rows", ctx.week_last[np.flatnonzero((exw[1:] != exw[:-1]) & np.isfinite(exw[1:]) & np.isfinite(exw[:-1])) + 1].all())
gdx = strategies.make("guppy").diagnostics(ctx)
check("guppy diagnostics on the synthetic cycle: some trades and green+red+gray shares sum to 1",
      gdx["buy_events"] >= 1 and abs(gdx["green_share"] + gdx["red_share"] + gdx["gray_share"] - 1.0) < 1e-12, gdx)

# ---- drawdown stop ----
nav = np.array([1.0, 1.2, 1.1, 0.83, 0.9, 1.1, 1.2, 1.25, 1.3])
dctx = base.SignalContext(pd.bdate_range("2020-01-01", periods=9), nav, None, nav, np.zeros(9, bool))
check("drawdown_stop: peak 1.2, exit when NAV 0.83 is more than 30% below it, stay out through 1.1 and a tie at 1.2, re-enter on the new peak 1.25",
      np.array_equal(strategies.make("drawdown_stop").exposure(dctx), [1, 1, 1, 0, 0, 0, 0, 1, 1.0]))
n3 = np.array([1.0, 0.71, 0.69])
check("drawdown_stop: 0.71 is 29% below the peak (stay in), 0.69 is 31% below (exit)",
      np.array_equal(drawdown_stop.stop_exposure(n3, 0.30), [1.0, 1.0, 0.0]))
n4 = np.array([1.0, 0.95, 0.89, 0.92, 1.01])
check("drawdown_stop with drop 10%: [1, .95, .89, .92, 1.01] -> in, in, out, out, back in on the new peak",
      np.array_equal(drawdown_stop.stop_exposure(n4, 0.10), [1, 1, 0, 0, 1.0]))
raises("drawdown_stop: drop must be between 0 and 1", lambda: strategies.make("drawdown_stop", drop=1.5), "between 0 and 1")
sf = bt.signal_from(strategies.make("drawdown_stop"), ctx, 1000)
check("signal_from for a path-dependent rule: NaN before the start row, and the peak starts AT the start row",
      np.isnan(sf[:1000]).all() and np.array_equal(sf[1000:], strategies.make("drawdown_stop").exposure(ctx.tail_from(1000))))
check("signal_from for a stateless rule: the full-history signal, NaN before the start row",
      np.array_equal(bt.signal_from(strategies.make("trend_50d"), ctx, 700)[700:], strategies.make("trend_50d").exposure(ctx)[700:]) and np.isnan(bt.signal_from(strategies.make("trend_50d"), ctx, 700)[:700]).all())

# ---- the registry ----
reg = base.discover()
need = {"trend_50d", "trend_200d", "trend_200w", "guppy", "guppy_weekly", "vol_threshold", "drawdown_stop"}
check("discover() finds all six example plugins (guppy in a daily and a weekly class): " + ", ".join(sorted(need)), need <= set(reg) and reg is base.registry, sorted(reg))
check("discover() is repeatable: a second call changes nothing", base.discover() is reg and set(reg) >= need)
check("make() builds each registered plugin with its defaults and the key is set", all(strategies.make(k).key == k for k in reg))
check("all_variants: 12 variants (6 trend, 4 guppy, vol, drawdown) with unique names", len(base.all_variants()) == 12 and len({s.name for _, _, s in base.all_variants()}) == 12,
      [s.name for _, _, s in base.all_variants()])
raises("registering a name twice is refused", lambda: base.register("trend_50d")(type("Dup", (base.Strategy,), {})), "already registered")
check("the cut of a context keeps the week-end flags of the full history (calendar information)",
      np.array_equal(ctx.cut(1003).week_last, ctx.week_last[:1003]) and len(ctx.cut(1003)) == 1003)

# ---- the GENERIC LOOK-AHEAD TEST: every registered plugin, every variant ----
CUTS = (300, 1000, 2500, 301, 1003, 2502)                       # the first three are week-ends (Fridays); the others are mid-week
for key, params, st in base.all_variants():
    bad = base.check_no_lookahead(st, ctx, cuts=CUTS)
    ex = st.exposure(ctx)
    live = ex[np.isfinite(ex)]
    check(f"look-ahead: {st.name} gives the same first t signals on the full history and on the history cut at t in {CUTS}", not bad, bad)
    check(f"look-ahead: {st.name} output is float64, in [0,1], NaN only before the first signal, and not constant (the test is not vacuous)",
          ex.dtype == np.float64 and len(live) > 0 and live.min() >= 0 and live.max() <= 1 and np.isfinite(ex[int(np.argmax(np.isfinite(ex))):]).all() and live.std() > 0)
    check(f"look-ahead: {st.name} nominal warmup is a non-negative number", st.warmup >= 0)


# Audit S4 finding 4: fixed cuts miss a rule that peeks only late in the sample. Cut at (almost) every row on a
# shorter random walk, so a peek anywhere after warm-up is caught.
_rng = np.random.default_rng(11)
_n = 1400
_walk = 100.0 * np.exp(np.cumsum(_rng.normal(0.0003, 0.012, _n)))
_ctx_walk = bt.make_context(pd.bdate_range("2015-01-01", periods=_n), _walk, _walk * 1.001, None)
_every = tuple(range(230, _n, 5))
for key, params, st in base.all_variants():
    bad = base.check_no_lookahead(st, _ctx_walk, cuts=_every)
    check(f"look-ahead (every 5th row, {len(_every)} cuts on a 1,400-row walk): {st.name} never changes an earlier signal", not bad, bad[:3])


class _LatePeeker(base.Strategy):
    """Peeks at tomorrow's close only from row 1005 on: invisible to fixed cuts at 300 and 1000, visible to the
    every-row test."""
    name, params, warmup = "late_peeker", {}, 1

    def exposure(self, ctx):
        c = np.asarray(ctx.close, dtype=float)
        out = np.ones(len(c))
        if len(c) > 1006:
            out[1005:-1] = (c[1006:] > c[1005:-1]).astype(float)
        return out


check("look-ahead (every 5th row) CATCHES a rule that peeks only after row 1005",
      len(base.check_no_lookahead(_LatePeeker(), _ctx_walk, cuts=_every)) > 0)
check("look-ahead (fixed cuts 300/1000) MISSES that late peeker: the every-row test is needed",
      len(base.check_no_lookahead(_LatePeeker(), _ctx_walk, cuts=(300, 1000))) == 0)


class _Peeker(base.Strategy):
    """A deliberately broken rule: 'hold if tomorrow's close is higher'. The generic test must catch it."""
    key = "peeker"

    def exposure(self, ctx):
        tomorrow = np.append(ctx.close[1:], ctx.close[-1])
        return (tomorrow > ctx.close).astype(np.float64)


rise = bt.make_context(pd.bdate_range("2020-01-01", periods=3000), np.linspace(100, 300, 3000), np.linspace(100, 300, 3000), None)
bad = base.check_no_lookahead(_Peeker(), rise)
check("look-ahead test CATCHES a rule that peeks at tomorrow's close (fails at every cut)", len(bad) == 3, bad)

# ---- speed: 36 wealth runs on 20,000 rows ----
big = 20000
rpb = np.r_[0.0, np.random.default_rng(2).normal(0.0004, 0.02, big - 1)]
eb = np.where(np.random.default_rng(3).random(big) < 0.5, 1.0, 0.0)
t0 = time.perf_counter()
for _ in range(36):
    bt.run_overlay(rpb, np.zeros(big), eb, 1, 0.001)
dt = time.perf_counter() - t0
check(f"timing: 36 overlay runs on 20,000 rows take {dt:.2f} s (< 2 s)", dt < 2.0, dt)

# ---- cash accrues at the investment yield, not the bank-discount rate (R2 step 3, audit F4) ----
# DTB3 quotes a bill's discount rate d on a 360-day year: price = 100 (1 - d x 91 / 360). Paying that price for 100 at
# maturity earns 100 / price - 1 over 91 days; scaled to a 365-day year that is 365 d / (360 - 91 d).
# d = 5%:  365 x 0.05 / (360 - 4.55) = 18.25 / 355.45 = 5.13433%   (+0.134 pp)
# d = 1%:  365 x 0.01 / (360 - 0.91) =  3.65 / 359.09 = 1.01644%   (+0.016 pp)
y5, y1 = bt.discount_to_investment_yield(0.05), bt.discount_to_investment_yield(0.01)
check("discount to yield at 5%: 18.25 / 355.45 = 5.1343% (hand computation)", abs(y5 - 18.25 / 355.45) < 1e-15 and abs(y5 - 0.051343) < 1e-6, y5)
check("discount to yield at 1%: 3.65 / 359.09 = 1.0164% (hand computation)", abs(y1 - 3.65 / 359.09) < 1e-15 and abs(y1 - 0.010164) < 1e-6, y1)
check("discount to yield: the effect is +0.134 pp at 5% and +0.016 pp at 1%", abs((y5 - 0.05) - 0.001343) < 1e-6 and abs((y1 - 0.01) - 0.000164) < 1e-6, (y5 - 0.05, y1 - 0.01))
for d_ in (0.0, 0.01, 0.05, 0.15):
    price = 100.0 * (1.0 - d_ * 91.0 / 360.0)
    via_price = (100.0 / price - 1.0) * 365.0 / 91.0                  # the investor's own arithmetic, independent of the closed form
    check(f"discount to yield at {d_:.0%}: equals the investor's return (100 / price - 1) x 365 / 91 from the bill's price to 1e-14",
          abs(bt.discount_to_investment_yield(d_) - via_price) < 1e-14, (bt.discount_to_investment_yield(d_), via_price))
arr_ = bt.discount_to_investment_yield(np.array([0.0, 0.01, 0.05]))
check("discount to yield: works on arrays (0 stays 0)", arr_.shape == (3,) and arr_[0] == 0.0 and abs(arr_[2] - y5) < 1e-15)
idx_ = pd.DatetimeIndex(["2020-01-03", "2020-01-06", "2020-01-07"])        # Friday, Monday (3 calendar days), Tuesday
rc_ = bt.cash_returns(idx_, np.array([0.05, 0.05, 0.05]))
rc_raw = bt.cash_returns(idx_, np.array([0.05, 0.05, 0.05]), discount_basis=False)
check("cash_returns: accrues the yield x calendar days / 365 (the Monday row carries 3 days); row 0 earns nothing",
      rc_[0] == 0.0 and abs(rc_[1] - y5 * 3 / 365) < 1e-15 and abs(rc_[2] - y5 / 365) < 1e-15, rc_)
check("cash_returns: discount_basis=False reproduces the earlier raw accrual (0.05 x 3 / 365)", abs(rc_raw[1] - 0.05 * 3 / 365) < 1e-15)
yr = bt.cash_returns(pd.date_range("2020-01-01", periods=366, freq="D"), np.full(366, 0.05))
check("cash_returns: a year of calendar days at a 5% discount rate grows by 5.134% (simple accrual), 0.134 pp above the raw 5.000%",
      abs(yr.sum() - y5 * 365 / 365) < 1e-12, yr.sum())
