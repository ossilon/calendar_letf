"""European options on an index with a continuous dividend yield (Black-Scholes-Merton), for the LEAP comparator (BACKLOG
B15). `scripts/run_leap.py` runs the study.

Plain-English map
  * A call is the right to buy the index at the strike K on the expiry date. A deep in-the-money call (K far below
    today's index S) moves almost one for one with the index, but costs only part of S: it is a levered position. Its
    leverage is delta x S / C (how far the call moves, in percent, per 1% index move).
  * Put-call parity: C - P = S e^(-qT) - K e^(-rT). So a call = the index (less the dividends it will not receive) + a
    loan of K e^(-rT) + a put. Below 2x the strike is low, the put is far out of the money and cheap, and the call is
    mostly "index plus a loan": its cost of leverage is the loan rate r plus the put's premium.
  * The dividend yield q matters: the call holder does not receive the index's dividends, while a fund's swap earns the
    total return. Leaving q out makes the call look cheaper by about L x q a year.
Every function takes annual decimals (r, q, sigma) and T in years.
"""
import math

import numpy as np

SQRT2 = math.sqrt(2.0)


def norm_cdf(x):
    """The standard normal distribution function, from the complementary error function: 0.5 erfc(-x / sqrt 2). It keeps
    full relative precision in the lower tail, where 0.5 (1 + erf(x / sqrt 2)) cancels to 0 (x below about -6), so a far
    out-of-the-money call and its leverage stay finite and positive (fix 2026-11-06: the old form gave 0, negative or
    NaN leverage at a strike of 4 x the index under a 10% volatility, and the strike search then refused its bracket)."""
    return 0.5 * math.erfc(-x / SQRT2)


def d1d2(S, K, T, r, q, sigma):
    v = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / v
    return d1, d1 - v


def call(S, K, T, r, q, sigma):
    """Black-Scholes-Merton call value."""
    if K <= 0.0:
        return S * math.exp(-q * T) - K * math.exp(-r * T)        # a call with no strike is the forward position
    d1, d2 = d1d2(S, K, T, r, q, sigma)
    return S * math.exp(-q * T) * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)


def put(S, K, T, r, q, sigma):
    """Black-Scholes-Merton put value (written out on its own, not from parity, so parity is a test)."""
    if K <= 0.0:
        return 0.0
    d1, d2 = d1d2(S, K, T, r, q, sigma)
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * math.exp(-q * T) * norm_cdf(-d1)


def call_delta(S, K, T, r, q, sigma):
    if K <= 0.0:
        return math.exp(-q * T)
    return math.exp(-q * T) * norm_cdf(d1d2(S, K, T, r, q, sigma)[0])


def leverage(S, K, T, r, q, sigma):
    """The call's leverage: delta x S / C. A call worth nothing to machine precision (far out of the money at a tiny
    volatility) has unbounded leverage: +inf, not the 0 / 0 of the formula."""
    c = call(S, K, T, r, q, sigma)
    if c <= 0.0:
        return float("inf")
    return call_delta(S, K, T, r, q, sigma) * S / c


def strike_for_leverage(target, S, T, r, q, vol_of_k, tol=1e-10, max_iter=200):
    """The strike K at which the call's leverage equals `target` (> 1). vol_of_k(K) gives the implied volatility at K
    (the skew). The leverage rises with K, so the search bisects on log K between S e^-12 and 4 S. Raises when the
    target is out of that range."""
    if target <= 1.0:
        raise ValueError("strike_for_leverage: the target leverage must be above 1 (a call at K -> 0 is 1x the index)")
    lo, hi = math.log(S) - 12.0, math.log(4.0 * S)
    f = lambda x: leverage(S, math.exp(x), T, r, q, vol_of_k(math.exp(x))) - target       # noqa: E731
    if f(lo) > 0 or f(hi) < 0:
        raise ValueError(f"strike_for_leverage: target {target} is outside the reachable range")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            break
    return math.exp(0.5 * (lo + hi))


def skewed_vol(atm, S, slope):
    """Implied volatility at strike K: atm x (1 + slope x ln(S / K)), floored at atm (a strike below spot carries a higher
    implied volatility; slope 0 is a flat smile). Returns a function of K."""
    return lambda K: atm * max(1.0, 1.0 + slope * math.log(S / K))


def term_vol(vix, theta, kappa, T):
    """Implied volatility for maturity T from the 30-day VIX level, by mean reversion of variance toward theta (an
    average of v^2 over T, Heston's expected variance): sqrt(theta + (vix^2 - theta) x (1 - e^(-kT)) / (kT))."""
    w = (1.0 - math.exp(-kappa * T)) / (kappa * T)
    return math.sqrt(max(theta + (vix * vix - theta) * w, 1e-8))


def call_by_integration(S, K, T, r, q, sigma, n=20001):
    """A second implementation for the tests: the discounted expected payoff under the lognormal law, by the trapezoid
    rule over the standard normal variable z in [-10, 10]."""
    z = np.linspace(-10.0, 10.0, n)
    ST = S * np.exp((r - q - 0.5 * sigma * sigma) * T + sigma * math.sqrt(T) * z)
    dens = np.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    return math.exp(-r * T) * float(np.trapezoid(np.maximum(ST - K, 0.0) * dens, z))
