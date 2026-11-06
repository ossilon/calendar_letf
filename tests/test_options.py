"""BACKLOG B15: calendar_letf/options.py (Black-Scholes-Merton with a dividend yield) and results/leap.json.

Part A, planted: put-call parity WITH the dividend yield (the call and the put are written out separately), the call
against a second implementation (numerical integration of the lognormal payoff), the strike search, the limit as the
target leverage falls to 1 (the call becomes the index less its dividends), and the volatility helpers' limits.
Part B checks the results file and the qualitative claims of FINDINGS F29.
"""
import json
import math

from _harness import ROOT, check, raises, worst_of
from calendar_letf import options as opt

grid = [(S, K, T, r, q, s) for S in (100.0, 3000.0) for K in (20.0, 50.0, 90.0, 100.0, 130.0) for T in (0.25, 2.0)
        for r in (0.0, 0.05) for q in (0.0, 0.02) for s in (0.1, 0.35)]
err = 0.0
for S, K, T, r, q, s in grid:
    lhs = opt.call(S, K, T, r, q, s) - opt.put(S, K, T, r, q, s)
    err = worst_of(err, abs(lhs - (S * math.exp(-q * T) - K * math.exp(-r * T))) / S)
check("put-call parity WITH the dividend yield: C - P = S e^(-qT) - K e^(-rT) to 1e-10 of S on 160 cases", err < 1e-10, err)
err = 0.0
for S, K, T, r, q, s in grid[:40]:
    err = worst_of(err, abs(opt.call(S, K, T, r, q, s) - opt.call_by_integration(S, K, T, r, q, s)) / S)
check("the call equals the discounted expected payoff by numerical integration (a second implementation) to 1e-6 of S", err < 1e-6, err)
vk = opt.skewed_vol(0.2, 100.0, 0.25)
for target in (1.2, 1.5, 2.0, 3.0):
    K = opt.strike_for_leverage(target, 100.0, 2.0, 0.04, 0.015, vk)
    check(f"strike_for_leverage: target {target} -> the call's leverage at that strike is {target} to 1e-8",
          abs(opt.leverage(100.0, K, 2.0, 0.04, 0.015, vk(K)) - target) < 1e-8)
Ks = [opt.strike_for_leverage(t, 100.0, 2.0, 0.04, 0.015, vk) for t in (1.2, 1.5, 2.0)]
check("strike_for_leverage: a higher target leverage needs a higher strike", Ks[0] < Ks[1] < Ks[2], Ks)
Kz = opt.strike_for_leverage(1.0001, 100.0, 2.0, 0.04, 0.015, lambda K: 0.2)
check("limit: as the target leverage falls to 1, the strike goes to 0 and the call to the index less its dividends, S e^(-qT)",
      Kz < 0.5 and abs(opt.call(100.0, Kz, 2.0, 0.04, 0.015, 0.2) - 100.0 * math.exp(-0.03)) < 0.5, Kz)
raises("strike_for_leverage refuses a target of 1 or less", lambda: opt.strike_for_leverage(1.0, 100.0, 2.0, 0.0, 0.0, lambda K: 0.2), "above 1")
check("term_vol: at T -> 0 it is the VIX level; at T -> infinity the long-run level sqrt(theta)",
      abs(opt.term_vol(0.3, 0.04, 2.0, 1e-9) - 0.3) < 1e-6 and abs(opt.term_vol(0.3, 0.04, 2.0, 1e6) - 0.2) < 1e-4)
check("term_vol at T = 1, kappa = 2: the averaged-variance weight (1 - e^-2) / 2 = 0.4323 (Heston's expected variance), not e^-2",
      abs(opt.term_vol(0.3, 0.04, 2.0, 1.0) - math.sqrt(0.04 + 0.05 * (1 - math.exp(-2.0)) / 2.0)) < 1e-15)
check("skewed_vol: a strike below the index gets atm x (1 + slope x ln(S/K)); a strike above it keeps atm",
      abs(opt.skewed_vol(0.2, 100.0, 0.25)(50.0) - 0.2 * (1 + 0.25 * math.log(2))) < 1e-15 and opt.skewed_vol(0.2, 100.0, 0.25)(150.0) == 0.2)

# ================================================================ Part B: the results file
res = json.loads((ROOT / "results" / "leap.json").read_text(encoding="utf-8"))
rows = res["rows"]


def leap(L, roll, cost, skew="base"):
    return next(r for r in rows if r["series"] == "LEAP" and r["L"] == L and r["roll_freq"] == roll and r["cost"] == cost and r["skew"] == skew)


def fund(L, c="b19"):
    return next(r for r in rows if r["series"] == f"fund ({c} cost)" and r["L"] == L)


check("results: 4 leverages x (8 LEAP variants + 2 funds) rows (quarterly: 3 skews and 3 costs; yearly: 3 costs)", len(rows) == 4 * 10)
# the claims of FINDINGS F29, read from the paired yearly intervals (re-grade 2026-11-06, finding U2)
vf = {(x["L"], x["roll_freq"], x["cost"]): x for x in res["vs_fund"]}
check("F29: with no roll cost the quarterly LEAP leads the fund at every L, every interval excludes zero, and only the 2x "
      "interval passes the coverage check",
      all(vf[(L, "quarterly", 0.0)]["lo"] > 0 for L in (1.2, 1.5, 1.7, 2.0))
      and [vf[(L, "quarterly", 0.0)]["verdict"] for L in (1.2, 1.5, 1.7, 2.0)] == ["too narrow"] * 3 + ["valid"])
check("F29: at a 0.5% cost per quarterly roll no interval below 2x clears zero with a valid verdict (none separates the two)",
      all(vf[(L, "quarterly", 0.005)]["covers_zero"] or vf[(L, "quarterly", 0.005)]["verdict"] != "valid" for L in (1.2, 1.5, 1.7)))
check("F29: rolled yearly at 0.5%, the 2x lead is a valid interval above zero; at 1.5x and 1.7x the intervals cover zero",
      vf[(2.0, "yearly", 0.005)]["lo"] > 0 and vf[(2.0, "yearly", 0.005)]["verdict"] == "valid"
      and vf[(1.5, "yearly", 0.005)]["covers_zero"] and vf[(1.7, "yearly", 0.005)]["covers_zero"])
check("F29: rolled yearly at 0.5%, the 1.2x lead excludes zero but its interval fails the coverage check (too narrow)",
      vf[(1.2, "yearly", 0.005)]["lo"] > 0 and vf[(1.2, "yearly", 0.005)]["verdict"] == "too narrow")
check("F29: at 0.5% per quarterly roll the 1.2x interval only just excludes zero (upper end within 0.01 points of it) and "
      "is too narrow; the 1.5x and 1.7x intervals cover zero",
      -1e-4 < vf[(1.2, "quarterly", 0.005)]["hi"] < 0 and vf[(1.2, "quarterly", 0.005)]["verdict"] == "too narrow"
      and vf[(1.5, "quarterly", 0.005)]["covers_zero"] and vf[(1.7, "quarterly", 0.005)]["covers_zero"])
check("F29: the embedded put costs under 0.5% of the position a year at every L and skew; below 2x the strikes are UNTRADED",
      all(r["put_cost_per_year"] < 0.005 for r in rows if r["series"] == "LEAP")
      and all(r["untraded"] == (r["L"] < 2.0) for r in rows if r["series"] == "LEAP"))


# ---- the normal distribution in the deep lower tail (fix 2026-11-06) ----
# Independent route: the asymptotic series Phi(-x) = phi(x) / x (1 - 1/x^2 + 3/x^4 - 15/x^6 + 105/x^8 ...), whose error at x = 10
# is below the next term (945 / x^10 = 1e-7 relative).
def _tail(x):
    return math.exp(-x * x / 2) / math.sqrt(2 * math.pi) / x * (1 - 1 / x ** 2 + 3 / x ** 4 - 15 / x ** 6 + 105 / x ** 8)


check("norm_cdf keeps relative precision in the deep lower tail: Phi(-10) and Phi(-20) match the asymptotic series to 1e-6",
      all(abs(opt.norm_cdf(-x) / _tail(x) - 1) < 1e-6 for x in (10.0, 20.0)), [opt.norm_cdf(-x) for x in (10.0, 20.0)])
check("norm_cdf BREAK: the old form 0.5 (1 + erf) gives exactly 0 at -10, so the test above can tell the two apart",
      0.5 * (1 + math.erf(-10 / math.sqrt(2))) == 0.0)
check("a far out-of-the-money call (K = 4 S, two years, 10% volatility) is positive and its leverage finite and above 20",
      opt.call(100, 400, 2, 0.04, 0.02, 0.10) > 0 and 20 < opt.leverage(100, 400, 2, 0.04, 0.02, 0.10) < 1e6)
check("strike_for_leverage works at a 10% volatility (the bracket top at 4 S is now a valid upper end)",
      abs(opt.leverage(100, opt.strike_for_leverage(1.5, 100, 2, 0.04, 0.02, lambda k: 0.10), 2, 0.04, 0.02, 0.10) - 1.5) < 1e-8)
check("leverage: a call worth nothing (K = 4 S at a 0.01% volatility) has leverage +inf, not NaN",
      opt.leverage(100, 400, 2, 0.0, 0.0, 1e-4) == float("inf"))
