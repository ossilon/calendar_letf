"""Planted-answer tests for leverage other than 2x (BACKLOG B17; reused by B1 and B16): products.trigger_for,
products.at_leverage, study.encoding_at and its guard, and the kernel's closed forms at L = 1.2, 1.5, 1.7 and 3.

Made-up data only. Each expected value comes from an independent route: a hand-computed number, a closed form
(1 + L R over one period, the product of (1 + L r) for a daily fund), or the second-order expansion of the
calendar-vs-daily gap, L(L-1)/2 x (sum r^2 - (sum r)^2) per period, which the kernel never uses.
"""
import math
from dataclasses import replace

import numpy as np
import pandas as pd

from _harness import check, raises, worst_of  # noqa: I001  (must come first: puts the repo root on sys.path)
from calendar_letf import kernel as k
from calendar_letf import products, study

LS = (1.2, 1.5, 1.7, 3.0)
BASE = products.PRODUCTS["HYP_SPX_M"]                 # a 2x monthly design


def periodic(u, reset, L, early_drop=None, spread=0.0, fee=0.0):
    return k.periodic_reset_series(u, 0.0, reset=reset, L=L, spread_per_nav=spread, fee=fee, early_drop=early_drop)


def daily(u, L, spread=0.0, fee=0.0):
    return k.daily_reset_series(u, 0.0, L=L, spread_per_nav=spread, fee=fee)


def walk(start, n, seed, vol, drift=0.0003):
    ix = pd.bdate_range(start, periods=n)
    rng = np.random.default_rng(seed)
    return pd.Series(100.0 * np.exp(np.cumsum(rng.normal(drift, vol, n))), index=ix)


# ---- trigger rules ----
check("trigger_for: 'none' has no early reset; 'fixed35' is 35% at any L; 'scaled' is 0.70 / L (35% at 2x, 58.33% at 1.2x, 23.33% at 3x)",
      products.trigger_for(1.2, "none")[0] is None and products.trigger_for(3.0, "fixed35")[0] == 0.35
      and products.trigger_for(2.0, "scaled")[0] == 0.35 and abs(products.trigger_for(1.2, "scaled")[0] - 0.7 / 1.2) < 1e-15
      and abs(products.trigger_for(3.0, "scaled")[0] - 0.7 / 3) < 1e-15)
raises("trigger_for refuses an unknown rule", lambda: products.trigger_for(2.0, "sometimes"), "trigger rule")

# ---- the same design at another leverage ----
p15 = products.at_leverage(BASE, 1.5, "scaled", "notional")
p15b = products.at_leverage(BASE, 1.5, "none", "borrowed")
check("at_leverage: L = 1.5 keeps the underlying, reset and fee; notional basis pays the spread on 1.5 turns, borrowed on 0.5",
      p15.L == 1.5 and p15.reset == "monthly" and p15.underlying == "SPX" and p15.fee == BASE.fee
      and p15.costs.turns == 1.5 and p15b.costs.turns == 0.5 and p15b.costs.spread_basis == "borrowed", (p15.costs.turns, p15b.costs.turns))
check("at_leverage: a HYPOTHETICAL (MODELED) product with an ASSUMED trigger: scaled -> 0.70 / 1.5, none -> no early reset",
      p15.kind == "MODELED" and p15.early_drop_status == "ASSUMED" and abs(p15.early_drop - 0.7 / 1.5) < 1e-15
      and p15b.early_drop is None and "HYPOTHETICAL" in p15.note)
check("at_leverage: L = 1 pays no spread on either basis (no swap); names differ by L, rule and basis",
      products.at_leverage(BASE, 1.0, "none").costs.turns == 0.0 and products.at_leverage(BASE, 1.0, "none", "borrowed").costs.turns == 0.0
      and len({p15.name, p15b.name, products.at_leverage(BASE, 1.7).name}) == 3)
tw = products.twin_of(p15)
check("twin_of(at_leverage(...)): the daily twin carries the same L, fee, spread and turns",
      tw.L == 1.5 and tw.reset == "daily" and tw.costs.turns == p15.costs.turns and tw.fee == p15.fee and tw.costs.spread == p15.costs.spread)
raises("at_leverage refuses a daily-reset base (build the calendar design, then take its twin)",
       lambda: products.at_leverage(products.PRODUCTS["TWIN_SPX_D"], 1.5), "resets daily")
raises("at_leverage refuses a model of a real fund at its filed terms", lambda: products.at_leverage(products.MODELS_3X["UPRO_MODEL"], 2.0), "real fund")
raises("at_leverage refuses the 'swaps' basis (no rule for turns)", lambda: products.at_leverage(BASE, 1.5, "none", "swaps"), "swaps")

# ---- the fitted 2x encodings carried to L ----
fixed, rate = study.ENCODINGS["fixed"], study.ENCODINGS["rate"]
same_at_2 = all(study.encoding_at(e, 2.0, b).spread_per_nav == e.spread_per_nav and study.encoding_at(e, 2.0, b).rate_turns == e.rate_turns
                for e in (fixed, rate) for b in ("notional", "borrowed"))
check("encoding_at: at L = 2 both encodings come back unchanged on both bases (the published 2x anchor)", same_at_2)
check("encoding_at: at 1.5x the fixed 2.6% becomes 1.95% on the notional basis (x 1.5/2) and 1.30% on the borrowed basis (x 0.5/1); rate turns kept",
      abs(study.encoding_at(fixed, 1.5, "notional").spread_per_nav - 0.0195) < 1e-15
      and abs(study.encoding_at(fixed, 1.5, "borrowed").spread_per_nav - 0.013) < 1e-15
      and study.encoding_at(rate, 1.5, "borrowed").rate_turns == 1.3)
check("encoding_at: at L = 1 there is no spread on either basis; at 3x the notional spread is 3/2 of the 2x one, the borrowed 2/1",
      study.encoding_at(fixed, 1.0, "notional").spread_per_nav == 0.0 and study.encoding_at(fixed, 1.0, "borrowed").spread_per_nav == 0.0
      and abs(study.encoding_at(rate, 3.0, "notional").spread_per_nav - 0.021) < 1e-15
      and abs(study.encoding_at(rate, 3.0, "borrowed").spread_per_nav - 0.028) < 1e-15)
check("encoding_at: an ASSUMED label that names the L and the basis; definitions (zero costs) pass through at any L",
      study.encoding_at(fixed, 1.7).status == "ASSUMED" and "1.7" in study.encoding_at(fixed, 1.7).label
      and study.encoding_at(study.ZERO_COSTS, 1.7).spread_per_nav == 0.0 and study.encoding_at(study.ZERO_COSTS, 1.7).L == 1.7)
raises("encoding_at refuses to carry an encoding that is not set for 2x", lambda: study.encoding_at(study.encoding_at(fixed, 1.5), 1.7), "2x encoding")
raises("encoding_at refuses the 'swaps' basis", lambda: study.encoding_at(fixed, 1.5, "swaps"), "swaps")
raises("kernel_kwargs refuses a 2x encoding on a 1.5x product (the guard)", lambda: study.kernel_kwargs(p15, fixed), "set for L = 2")
check("kernel_kwargs accepts the encoding carried to the product's L, and a definition at any L",
      study.kernel_kwargs(p15, study.encoding_at(fixed, 1.5))["spread_per_nav"] == study.encoding_at(fixed, 1.5).spread_per_nav
      and study.kernel_kwargs(p15, study.ZERO_COSTS)["fee"] == 0.0)

# ---- kernel closed forms at other L (zero costs) ----
u = walk("2024-01-01", 60, seed=5, vol=0.01)
jan_end, feb_end = u[:"2024-01-31"].index[-1], u[:"2024-02-29"].index[-1]
R_feb = u[feb_end] / u[jan_end] - 1.0
err = 0.0
for L in LS:
    nav = periodic(u, "monthly", L)
    err = worst_of(err, abs(nav[feb_end] / nav[jan_end] - (1.0 + L * R_feb)))
check("kernel: one full calendar month at zero cost returns exactly 1 + L R at L = 1.2, 1.5, 1.7, 3 (to 1e-13)", err < 1e-13, err)

err = 0.0
for reset in ("weekly", "monthly", "quarterly"):
    err = worst_of(err, float(np.max(np.abs(periodic(u, reset, 1.0).values - (u / u.iloc[0]).values))))
err = worst_of(err, float(np.max(np.abs(daily(u, 1.0).values - (u / u.iloc[0]).values))))
check("kernel: L = 1 at zero cost is the index itself for every reset, daily included (to 1e-12)", err < 1e-12, err)

err = 0.0
r = u.pct_change().fillna(0.0).values
for L in LS:
    err = worst_of(err, float(np.max(np.abs(daily(u, L).values - np.cumprod(1.0 + L * r)))))
check("kernel: the daily fund at L = 1.2, 1.5, 1.7, 3 equals the product of (1 + L r_t) (to 1e-12)", err < 1e-11, err)

# Wipeout with no trigger: an in-period fall of exactly 1/L ends the fund; one a hair smaller does not.
# 1.25x: 1/L = 0.8 is exact in binary, so the index at 20 from 100 gives L R = -1 exactly.
days = pd.bdate_range("2024-01-29", "2024-02-09")       # Jan 31 is the period end, then February
def crash(level):
    vals = np.full(len(days), 100.0)
    vals[days > pd.Timestamp("2024-02-02")] = level
    return pd.Series(vals, index=days)
wiped = periodic(crash(20.0), "monthly", 1.25)
alive = periodic(crash(100.0 * (1.0 - 0.8 + 1e-9)), "monthly", 1.25)
check("kernel: 1.25x with no trigger: an in-period fall of exactly 1/L = 80% wipes the fund out and it stays at 0; 80% - 1e-9 does not",
      wiped.iloc[-1] == 0.0 and (wiped[wiped.index > pd.Timestamp("2024-02-02")] == 0.0).all() and alive.iloc[-1] > 0.0, (wiped.iloc[-1], alive.iloc[-1]))
alive_ok = all(periodic(crash(100.0 * (1.0 - 1.0 / L + 1e-6)), "monthly", L).iloc[-1] > 0.0 for L in LS)
check("kernel: at 1.2, 1.5, 1.7 and 3 a fall just short of 1/L (by 1e-6) leaves the fund alive", alive_ok)

# ---- C13: the calendar-vs-daily gap scales with L(L-1), against the second-order expansion ----
rng = np.random.default_rng(13)
n, phi = 2520, -0.3
e = rng.normal(0.0, 0.002, n)
r_ar = np.empty(n)
r_ar[0] = e[0]
for i in range(1, n):
    r_ar[i] = phi * r_ar[i - 1] + e[i]                  # small daily returns that tend to reverse
ix = pd.bdate_range("2010-01-01", periods=n + 1)
u_ar = pd.Series(100.0 * np.concatenate(([1.0], np.cumprod(1.0 + r_ar))), index=ix)
month = pd.Series(ix[1:].to_period("M"), index=ix[1:])
periods_r = [g.values for _, g in pd.Series(r_ar, index=ix[1:]).groupby(month)]
term = sum(np.sum(p ** 2) - np.sum(p) ** 2 for p in periods_r)          # per-period (sum r^2 - (sum r)^2), summed
worst_rel = 0.0
for L in (1.2, 1.5, 1.7, 2.0, 3.0):
    gap = math.log(periodic(u_ar, "monthly", L).iloc[-1]) - math.log(daily(u_ar, L).iloc[-1])
    want = L * (L - 1.0) / 2.0 * term
    worst_rel = worst_of(worst_rel, abs(gap / want - 1.0))
check("C13: on planted reversing returns the kernel's calendar-vs-daily log gap matches L(L-1)/2 x sum (sum r^2 - (sum r)^2) "
      "within 5% at L = 1.2, 1.5, 1.7, 2 and 3 (the second-order expansion, an independent route)",
      worst_rel < 0.05 and term > 0, (worst_rel, term))
g12 = math.log(periodic(u_ar, "monthly", 1.2).iloc[-1]) - math.log(daily(u_ar, 1.2).iloc[-1])
g2 = math.log(periodic(u_ar, "monthly", 2.0).iloc[-1]) - math.log(daily(u_ar, 2.0).iloc[-1])
check("C13: the 1.2x gap is about 0.12 of the 2x gap (L(L-1) = 0.24 vs 2), within 0.01", abs(g12 / g2 - 0.12) < 0.01, g12 / g2)

# ---- C14: the growth-optimal daily leverage, against the closed form on the same sample ----
r_iid = np.random.default_rng(14).normal(0.0002, 0.01, 20000)
u_iid = pd.Series(100.0 * np.concatenate(([1.0], np.cumprod(1.0 + r_iid))), index=pd.bdate_range("1950-01-02", periods=20001))
grid = np.round(np.arange(1.0, 4.001, 0.01), 2)
growth = [math.log(daily(u_iid, L).iloc[-1]) for L in grid]
L_best = float(grid[int(np.argmax(growth))])
L_closed = float(np.sum(r_iid) / np.sum(r_iid ** 2))      # argmax of sum(L r - L^2 r^2 / 2): the Kelly fraction on this sample
check("C14: the daily fund's growth-optimal L on planted iid returns lands within 0.05 of sum(r) / sum(r^2) (Kelly, second order)",
      1.0 < L_closed < 4.0 and abs(L_best - L_closed) < 0.05, (L_best, L_closed))

# ---- property: costs only hurt ----
uu = walk("2000-01-03", 1500, seed=9, vol=0.012)
ends = [periodic(uu, "monthly", 1.5, spread=s).iloc[-1] for s in (0.0, 0.01, 0.02, 0.04)]
ends_fee = [periodic(uu, "monthly", 1.5, fee=f).iloc[-1] for f in (0.0, 0.0099, 0.02)]
check("property: at 1.5x the final NAV falls strictly as the spread or the fee rises", all(a > b for a, b in zip(ends, ends[1:]))
      and all(a > b for a, b in zip(ends_fee, ends_fee[1:])), (ends, ends_fee))
