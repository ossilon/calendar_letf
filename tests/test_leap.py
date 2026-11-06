"""The LEAP roll loop of scripts/run_leap.py (re-grade 2026-11-06, finding P1: no test covered `leap_path`).

  1. A planted flat index (no volatility, no rate, no yield): a call deep in the money is worth S - K, so the wealth
     moves only by the trading cost, ((1 - c/2) / (1 + c/2)) per round trip, a closed form.
  2. A second implementation of the whole loop, written here from the textbook formulas (its own Black-Scholes-Merton
     call and delta, its own strike search by bisection on K, its own skew and term structure), on a planted path where
     the index, the rate, the yield and VIX all move. It must give the same wealth on every row and the same strikes.
  3. The published LEAP-minus-fund intervals (results/leap.json, when present) carry a coverage verdict, and the
     covers-zero flag agrees with the interval.
"""
import importlib.util
import json
import math
import sys

import numpy as np
import pandas as pd

from _harness import ROOT, check
from calendar_letf import periods

sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("run_leap", ROOT / "scripts" / "run_leap.py")
RL = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RL)


# ---------------------------------------------------------------- 1. the flat index
ix = pd.bdate_range("2001-01-02", "2003-12-31")
flat = pd.DataFrame(dict(S=100.0, u=100.0, q=0.0, r=0.0, rc=0.0, vix=1e-4, theta=1e-8), index=ix)
for c in (0.0, 0.01, 0.02):
    W, lev, rolls = RL.leap_path(flat, 2.0, "quarterly", "flat", c)
    n = len(rolls)
    # A roll day records the wealth after the sale and before the purchase. The planted index ends on a quarter end (a
    # roll), so the last mark holds n - 1 round trips; a mark between rolls also carries the last purchase's 1 / (1 + c/2).
    want_roll = ((1 - c / 2) / (1 + c / 2)) ** (n - 1)
    mid = flat.index.get_loc(pd.Timestamp("2003-11-14"))
    want_mid = ((1 - c / 2) / (1 + c / 2)) ** (n - 2) / (1 + c / 2)       # 11 rolls before 2003-11-14
    check(f"leap_path, flat index, cost {c:.0%}: wealth on the last roll day is ((1 - c/2)/(1 + c/2))^(n-1), n = {n}; "
          "between rolls it also carries 1 / (1 + c/2)",
          abs(W.iloc[-1] - want_roll) < 1e-12 and abs(W.iloc[mid] - want_mid) < 1e-12, (W.iloc[-1], want_roll, W.iloc[mid], want_mid))
check("leap_path, flat index: the strike gives exactly 2x (K = S / 2 when the call is worth S - K)",
      all(abs(r_["strike_over_spot"] - 0.5) < 1e-6 for r_ in rolls), [r_["strike_over_spot"] for r_ in rolls][:3])
check("leap_path, flat index: one roll per quarter end of 2001-2003 (12)", n == 12, n)


# ---------------------------------------------------------------- 2. a second implementation
def N(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def call2(S, K, T, r, q, s):
    v = s * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q) * T) / v + v / 2.0
    return S * math.exp(-q * T) * N(d1) - K * math.exp(-r * T) * N(d1 - v), math.exp(-q * T) * N(d1)


def vol2(vix, theta, kappa, T, S, slope, K):
    w = (1.0 - math.exp(-kappa * T)) / (kappa * T)
    atm = math.sqrt(max(theta + (vix * vix - theta) * w, 1e-8))
    return atm * max(1.0, 1.0 + slope * math.log(S / K))


def strike2(L, S, T, r, q, vol_of_k):
    lo, hi = S * 1e-5, 4.0 * S                     # leverage rises with K: bisection on K itself (the engine bisects log K)
    for _ in range(200):
        K = 0.5 * (lo + hi)
        c, dl = call2(S, K, T, r, q, vol_of_k(K))
        if dl * S / c < L:
            lo = K
        else:
            hi = K
    return 0.5 * (lo + hi)


def leap2(df, L, roll, slope, cost, kappa=RL.TERM_KAPPA, T=RL.T_YEARS):
    d = df.index
    q_ends = periods.period_end_flags(d, "quarterly")
    rf = q_ends if roll == "quarterly" else q_ends & (d.month == 12)
    W = np.full(len(d), np.nan)
    units = K = t0 = None
    first = int(np.flatnonzero(rf)[0])
    strikes = []
    for t in range(first, len(d)):
        S, r, q, vix, th = (float(df[c_].iloc[t]) for c_ in ("S", "rc", "q", "vix", "theta"))
        if units is not None:
            tau = T - (d[t] - d[t0]).days / 365.25
            W[t] = units * call2(S, K, tau, r, q, vol2(vix, th, kappa, tau, S, slope, K))[0]
        if t == first or rf[t]:
            wealth = 1.0 if units is None else W[t] * (1.0 - cost / 2.0)
            K = strike2(L, S, T, r, q, lambda k: vol2(vix, th, kappa, T, S, slope, k))
            units = wealth / (call2(S, K, T, r, q, vol2(vix, th, kappa, T, S, slope, K))[0] * (1.0 + cost / 2.0))
            t0 = t
            W[t] = wealth
            strikes.append(K / S)
    return W, strikes


rng = np.random.default_rng(2026)
ix2 = pd.bdate_range("2004-01-02", "2007-12-31")
n2 = len(ix2)
S = 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.011, n2)))
vix = np.clip(0.18 + np.cumsum(rng.normal(0, 0.004, n2)), 0.10, 0.45)
df2 = pd.DataFrame(dict(S=S, u=S, q=0.015 + 0.005 * np.sin(np.arange(n2) / 90.0),
                        rc=0.02 + 0.02 * np.arange(n2) / n2, vix=vix), index=ix2)
df2["theta"] = np.cumsum(vix ** 2) / np.arange(1, n2 + 1)
worst, worst_k = 0.0, 0.0
for L, roll, skew, cost in ((1.5, "quarterly", "base", 0.005), (2.0, "yearly", "steep", 0.01), (1.2, "quarterly", "flat", 0.0)):
    W1, _, rl = RL.leap_path(df2, L, roll, skew, cost)
    W2, ks = leap2(df2, L, roll, RL.SKEWS[skew], cost)
    same_nan = np.array_equal(np.isnan(W1.to_numpy()), np.isnan(W2))
    m = ~np.isnan(W2)
    worst = max(worst, float(np.max(np.abs(W1.to_numpy()[m] / W2[m] - 1.0))) if same_nan else float("inf"))
    worst_k = max(worst_k, max(abs(a - b) for a, b in zip([x["strike_over_spot"] for x in rl], ks)))
check("leap_path equals a second implementation (own BSM, strike search, skew, term structure, roll loop) on every row of a "
      "planted path, three settings, to 1e-9 relative", worst < 1e-9, worst)
check("leap_path: the strikes equal the second implementation's to 1e-8 of the index", worst_k < 1e-8, worst_k)

# ---------------------------------------------------------------- 3. the published intervals
path = ROOT / "results" / "leap.json"
if path.exists():
    res = json.loads(path.read_text(encoding="utf-8"))
    vf = res.get("vs_fund", [])
    check("leap.json: LEAP minus fund intervals exist for every L, roll and cost run at the base skew (4 L x 6)",
          len(vf) == len(RL.LS) * len(RL.ROLLS) * len(RL.ROLL_COSTS), len(vf))
    check("leap.json: every interval has a coverage verdict and at least 30 paired years",
          all(x["verdict"] in ("valid", "too narrow") and x["k"] >= 30 for x in vf))
    check("leap.json: the covers-zero flag agrees with each interval", all(x["covers_zero"] == (x["lo"] <= 0.0 <= x["hi"]) for x in vf))
else:
    print("skip: results/leap.json is absent (run py scripts\\run_leap.py)")


# ---------------------------------------------------------------- 4. the derived inputs are causal (re-check 2026-11-06)
_ix = pd.bdate_range("2010-01-04", periods=40)
_raw = pd.DataFrame(dict(r=np.linspace(0.0, 0.06, 40), vix=np.linspace(0.12, 0.40, 40)), index=_ix)
_d1 = RL.derived(_raw.copy())
check("derived inputs: theta on each day is the mean of VIX^2 from the first row up to that day (written out as a loop)",
      all(abs(_d1["theta"].iloc[t] - sum(_raw["vix"].iloc[i] ** 2 for i in range(t + 1)) / (t + 1)) < 1e-15 for t in range(40)))
_late = _raw.copy()
_late.iloc[25:, _late.columns.get_loc("vix")] = 0.90                     # a different future
_d2 = RL.derived(_late)
check("derived inputs BREAK: changing VIX after day 24 leaves theta up to day 24 unchanged (no later data); a full-sample "
      "mean would move it", np.array_equal(_d1["theta"].iloc[:25].to_numpy(), _d2["theta"].iloc[:25].to_numpy())
      and not np.array_equal(_d1["theta"].to_numpy(), _d2["theta"].to_numpy()))
check("derived inputs: the rate passed to the option formula is 365 ln(1 + r / 360); at 6% it sits within 1e-5 of the "
      "first-order value 6% x 365 / 360, and a raw rate (no conversion) would miss by more than 8e-4",
      abs(_d1["rc"].iloc[-1] - 365 * math.log1p(0.06 / 360)) < 1e-14 and abs(_d1["rc"].iloc[-1] - 0.06 * 365 / 360) < 1e-5
      and abs(_d1["rc"].iloc[-1] - 0.06) > 8e-4 and _d1["rc"].iloc[0] == 0.0)
