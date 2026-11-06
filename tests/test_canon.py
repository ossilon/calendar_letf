"""Tests from the canon (R1 depth review, sections 1 and 4.2): exact identities and planted answers that tie the two
kernels to each other and to the published formulas. Made-up data, except three real S&P 500 quarters in P1
(skipped with a printed note when the price file is not available).

    P1  Bessembinder's exact identity: calendar minus daily period return = sum_{k>=2} (beta - beta^k) e_k
    P2  Avellaneda-Zhang / Leung-Santoli log formula for the daily twin on a GBM path, and its convergence
    P3  planted serial correlation (the design of Bessembinder's Figure 1 caption): the sign of the mean calendar-minus-daily gap
    P4  properties: finite outputs, monotone in each cost, scale invariance, calendar = margin inside a period
    P5  a second, vectorized implementation of the calendar NAV, equal to the numba kernel

Each check says in plain words what would be wrong if it failed; numbers are worked out in the comments.
Terms: e_k = the k-th elementary symmetric sum of the period's daily returns r_1..r_T (the sum of all products of
k different returns), i.e. the coefficient of z^k in prod(1 + r_t z). VR_T = the variance ratio
Var(r_1 + ... + r_T) / (T Var(r_t)): 1 with no autocorrelation, below 1 when daily returns tend to reverse.
"""
import math
from datetime import date

import numpy as np
import pandas as pd

from _harness import check, worst_of  # noqa: I001  (must come first: puts the repo root on sys.path)
from calendar_letf import kernel as k
from calendar_letf import loader, nyse
from calendar_letf import periods as cal


def esym(r):
    """e_0 .. e_T of the returns r: multiply out prod(1 + r_t z) one factor at a time (c_k += r_t x c_{k-1})."""
    c = np.zeros(len(r) + 1)
    c[0] = 1.0
    for x in r:
        c[1:] = c[1:] + x * c[:-1]          # the right side uses the old c, so this is (1 + x z) times the old poly
    return c


def zeros(n):
    return np.zeros(n)


def one_period(u, beta):
    """(calendar return, daily return, True if either fund hit zero) over rows 0..n-1 of level u at zero costs,
    one period (no reset inside)."""
    n = len(u)
    z = zeros(n)
    c_nav, _, c_term = k.periodic_reset_nav(u, u, u, z, z, z, np.zeros(n, dtype=np.bool_), beta, 0.0, z, 0.0,
                                            k.EARLY_LEVEL)
    d_nav, d_term = k.daily_reset_nav(u, z, z, z, beta, 0.0, z)
    return c_nav[-1] - 1.0, d_nav[-1] - 1.0, (c_term >= 0 or d_term >= 0)


def identity_error(u, beta):
    """(|(calendar - daily) - sum_{k=2}^{T} (beta - beta^k) e_k|, calendar - daily, terminated) for one period.

    The identity is about the unfloored payoffs; once a fund hits zero the kernel keeps it at zero (a finished fund
    cannot go negative), so a terminated period is reported, not compared."""
    r = u[1:] / u[:-1] - 1.0
    e = esym(r)
    kk = np.arange(len(e))
    rhs = float(np.sum((beta - beta ** kk[2:]) * e[2:]))
    c_ret, d_ret, dead = one_period(u, beta)
    return abs((c_ret - d_ret) - rhs), c_ret - d_ret, dead


# =================================================================================================================
# P1. Bessembinder (2026, SSRN 7376118 eq. 6), exact for any T at zero cost:
#     calendar = beta x (prod(1 + r) - 1) = beta x sum_{k>=1} e_k;  daily = prod(1 + beta r) - 1 = sum_{k>=1} beta^k e_k
#     so calendar - daily = sum_{k>=2} (beta - beta^k) e_k (the k = 1 terms cancel).
#     Two-day example by hand: r = (+10%, +10%), beta = 2: e_2 = 0.01, so the gap is (2 - 4) x 0.01 = -0.02, which is
#     1.42 - 1.44 from test_kernel (b).
# =================================================================================================================
err_hand, gap_hand, _ = identity_error(np.array([100.0, 110.0, 121.0]), 2.0)
check("P1: two days of +10% at 2x: calendar - daily = (2 - 4) x e_2 = -2 x 0.01 = -0.02 (1.42 - 1.44)",
      err_hand < 1e-14 and abs(gap_hand + 0.02) < 1e-14, (err_hand, gap_hand))
rng = np.random.default_rng(76118)
worst_p1, n_p1, dead_p1 = 0.0, 0, 0
for T in (5, 21, 63):
    for beta in (2.0, 3.0):
        for _ in range(25):
            r = rng.normal(0.0004, 0.015, T)
            u = 100.0 * np.concatenate(([1.0], np.cumprod(1.0 + r)))
            err, _, dead = identity_error(u, beta)
            worst_p1, n_p1, dead_p1 = worst_of(worst_p1, err), n_p1 + 1, dead_p1 + dead
check(f"P1: on {n_p1} random periods (T = 5, 21, 63 days; beta = 2 and 3; none terminated) the kernels' calendar - "
      f"daily gap equals sum_k (beta - beta^k) e_k to 1e-12 (worst {worst_p1:.1e})", worst_p1 < 1e-12 and dead_p1 == 0,
      (worst_p1, dead_p1))
try:
    spx = loader.close("SP:SPX")
except FileNotFoundError as exc:                               # no price library on this machine
    spx = None
    print(f"     P1 real SPX quarters: skipped ({exc})")
except ValueError as exc:                                      # the file exists but fails the loader's checks: a failure
    spx = None
    check("P1 real SPX quarters: the SP:SPX file passes the loader's data checks", False, exc)
if spx is not None:
    # 2008 Q4 at 3x is a planted wipe-out: SPX closed at 752.44 on 2008-11-20, 35.5% below its 2008-09-30 close of
    # 1166.36, and a 3x calendar fund is finished once 3 x u/u0 - 2 <= 0, i.e. at -33.3%. The identity is about the
    # unfloored payoff, so that case is checked as a termination instead.
    real = []
    for q_start, q_end in (("2008-09-30", "2008-12-31"), ("2020-03-31", "2020-06-30"), ("2022-03-31", "2022-06-30")):
        seg = spx.loc[q_start:q_end].to_numpy(dtype=np.float64, copy=True)   # previous quarter end .. this quarter end
        for beta in (2.0, 3.0):
            err, gap, dead = identity_error(seg, beta)
            real.append((q_end, beta, len(seg) - 1, err, gap, dead))
    print("     P1 real SPX quarters (end, beta, sessions, identity error, calendar - daily, terminated):",
          [(q, b_, n_, f"{e_:.1e}", f"{g_:+.4f}", d_) for q, b_, n_, e_, g_, d_ in real])
    alive = [x for x in real if not x[5]]
    check("P1: on three real S&P 500 quarters (2008 Q4, 2020 Q2, 2022 Q2; beta 2 and 3) the identity holds to 1e-12 "
          "wherever neither fund terminated (5 of 6 cases)",
          len(alive) == 5 and max(x[3] for x in alive) < 1e-12 and all(x[2] >= 60 for x in real), real)
    check("P1: the one terminated case is 2008 Q4 at 3x (the -35.5% close of 2008-11-20 finishes a 3x calendar fund)",
          [(x[0], x[1]) for x in real if x[5]] == [("2008-12-31", 3.0)])

# =================================================================================================================
# P2. Avellaneda-Zhang (2010) eqs. (4)-(6), p. 591 = Leung-Santoli (2016) eq. (2.8), p. 14 (R0 read 2026-11-06; both
#     write V_T demeaned, while the raw sum is the true second-order term: THEORY.md section 5): a daily LETF with return
#     beta R_i - ((beta-1) r + f) dt has
#         ln(L_T/L_0) ~ beta ln(S_T/S_0) - ((beta-1) r + f) T + 0.5 beta (1 - beta) V_T,   V_T = sum (R_i - Rbar)^2.
#     GBM: mu 8%, sigma 25%, r 4%, f 1%, beta 2, T = 1 year, accrual exactly dt per row (so the kernel's cost per row
#     is ((2-1) x 4% + 1%) x dt, the formula's own). The stated error bound is O(T sqrt(dt)); we check the error
#     is below 3 sigma sqrt(dt) T = 3 x 0.25 x 0.0630 x 1 = 0.0472 on every path, and simulate the SAME Brownian path
#     at dt = 1/252 and dt = 1/2520 (each coarse increment is the sum of 10 fine ones). The bound would allow the
#     error to fall by sqrt(10) = 3.16; it falls by about 10: on a path the cubic Taylor terms (beta^3 - beta)/3 x
#     sum R^3 and the n Rbar^2 term are O(dt) each, so the formula is first-order accurate in dt (the O(sqrt dt) bound
#     is a worst case from |R| <= C sqrt(dt)). 300 paths, fixed seed.
# =================================================================================================================
MU, SIG, RR, FF, BETA, TT = 0.08, 0.25, 0.04, 0.01, 2.0, 1.0


def az_error(dw, n):
    dt = TT / n
    s = np.exp(np.concatenate(([0.0], np.cumsum((MU - 0.5 * SIG ** 2) * dt + SIG * dw))))
    ret = s[1:] / s[:-1] - 1.0
    acc = np.full(n + 1, dt)
    acc[0] = 0.0
    nav, term = k.daily_reset_nav(s, np.full(n + 1, RR), acc, acc, BETA, 0.0, np.full(n + 1, FF))
    v = float(np.sum((ret - ret.mean()) ** 2))
    formula = BETA * math.log(s[-1] / s[0]) - ((BETA - 1.0) * RR + FF) * TT + 0.5 * BETA * (1.0 - BETA) * v
    return math.log(nav[-1]) - formula if term < 0 else float("nan")


rng2 = np.random.default_rng(2010)
err_c, err_f = [], []
for _ in range(300):
    dw_f = rng2.normal(0.0, math.sqrt(TT / 2520), 2520)
    err_c.append(az_error(dw_f.reshape(252, 10).sum(axis=1), 252))
    err_f.append(az_error(dw_f, 2520))
err_c, err_f = np.abs(np.array(err_c)), np.abs(np.array(err_f))
ratio_p2 = float(err_c.mean() / err_f.mean())
print(f"     P2: mean |error| {err_c.mean():.2e} at dt = 1/252, {err_f.mean():.2e} at dt = 1/2520 (ratio {ratio_p2:.2f}); "
      f"max {err_c.max():.2e} and {err_f.max():.2e}; stated bound 3 sigma sqrt(dt) T = {3 * SIG * math.sqrt(1 / 252) * TT:.4f}")
check("P2: the daily kernel satisfies the Avellaneda-Zhang log formula within the stated O(T sqrt dt) bound "
      "(|error| < 3 sigma sqrt(1/252) T = 0.047 on all 300 paths)",
      np.isfinite(err_c).all() and err_c.max() < 3 * SIG * math.sqrt(1 / 252) * TT, err_c.max())
check(f"P2: on the same Brownian paths the error falls at least sqrt(10) = 3.16 times when dt is cut tenfold "
      f"(observed {ratio_p2:.2f}: between 7 and 14, i.e. first order in dt)", 7.0 < ratio_p2 < 14.0, ratio_p2)

# =================================================================================================================
# P3. Planted serial correlation in the design of Bessembinder (2026) Figure 1's caption (an independent check of his
#     eq. (13) at this project's settings, not a replication of his plotted values): r_t = mu + e_t + 0.75 MA e_{t-1} + 0.50 MA e_{t-2}
#     + 0.25 MA e_{t-3}, e_t iid normal sd 1%, mu = 0.04%, T = 21, zero costs, 20,000 paths per MA value (fixed seed;
#     three extra e's before each path so every path is stationary). His eq. (13), second order, beta = 2:
#         E[calendar - daily] = (beta - beta^2) [C(T,2) mu^2 + T sigma^2/2 (VR_T - 1)] = -2 [210 mu^2 + 10.5 sigma^2 (VR - 1)]
#     With MA = 0 (VR = 1) the daily fund leads by 2 x C(21,2) x mu^2 = 2 x 210 x 1.6e-7 = 6.72e-5 per period (the exact
#     iid value, all orders, is 2((1+mu)^21 - 1) - ((1+2mu)^21 - 1) = -6.771e-5). The calendar fund wins when
#     VR < 1 - (T-1) mu^2/sigma^2 = 1 - 20 x 1.6e-7 / 1e-4 = 0.968. Population VR for MA = -0.1: the MA(3) weights
#     (-0.075, -0.05, -0.025) give autocorrelations (-0.069, -0.048, -0.025), VR = 1 + 2 sum (1 - j/21) rho_j = 0.74,
#     so the calendar fund wins by about +4.8e-4 per month; for MA = +0.3, VR = 1.88 and it loses about 2.1e-3.
#     The paths are chained into one long series with a reset after every 21 days, so each kernel runs once.
# =================================================================================================================
T3, N3, MU3, SD3 = 21, 20000, 0.0004, 0.01
p3 = {}
for ma in (-0.3, -0.1, 0.0, 0.1, 0.3):
    rg = np.random.default_rng(1)                                     # the same shocks for every MA value
    e = rg.normal(0.0, SD3, (N3, T3 + 3))
    rr = MU3 + e[:, 3:] + 0.75 * ma * e[:, 2:-1] + 0.50 * ma * e[:, 1:-2] + 0.25 * ma * e[:, :-3]
    u3 = np.concatenate(([1.0], np.cumprod(1.0 + rr.ravel())))
    n3 = len(u3)
    z3 = zeros(n3)
    pe3 = np.zeros(n3, dtype=np.bool_)
    pe3[T3::T3] = True                                                # reset at the end of every path
    c_nav, _, c_term = k.periodic_reset_nav(u3, u3, u3, z3, z3, z3, pe3, 2.0, 0.0, z3, 0.0, k.EARLY_LEVEL)
    d_nav, d_term = k.daily_reset_nav(u3, z3, z3, z3, 2.0, 0.0, z3)
    ends = np.arange(0, n3, T3)
    c_ret = c_nav[ends[1:]] / c_nav[ends[:-1]] - 1.0
    d_ret = d_nav[ends[1:]] / d_nav[ends[:-1]] - 1.0
    direct = 2.0 * (np.prod(1.0 + rr, axis=1) - 1.0) - (np.prod(1.0 + 2.0 * rr, axis=1) - 1.0)
    gap = c_ret - d_ret
    s2 = float(rr.var(ddof=1))
    vr = float(rr.sum(axis=1).var(ddof=1) / (T3 * s2))
    pred = -2.0 * (T3 * (T3 - 1) / 2 * MU3 ** 2 + T3 * s2 / 2 * (vr - 1.0))
    # third-order term of eq. (13): (beta - beta^3) [C(T,3) mu^3 + mu (T-2) T sigma^2/2 (VR - 1)], beta - beta^3 = -6
    pred3 = pred - 6.0 * (math.comb(T3, 3) * MU3 ** 3 + MU3 * (T3 - 2) * T3 * s2 / 2 * (vr - 1.0))
    p3[ma] = dict(vr=vr, sigma2=s2, gap=float(gap.mean()), se=float(gap.std(ddof=1) / math.sqrt(N3)), pred=pred, pred3=pred3,
                  crossover=1.0 - (T3 - 1) * MU3 ** 2 / s2, kernel_vs_direct=float(np.abs(gap - direct).max()),
                  terms=(c_term, d_term))
for ma, v in p3.items():
    print(f"     P3 MA {ma:+.1f}: VR_21 {v['vr']:.4f} (calendar wins below {v['crossover']:.4f}); mean gap {v['gap']:+.3e} "
          f"(se {v['se']:.1e}); eq. 13 second order {v['pred']:+.3e}, with third order {v['pred3']:+.3e}")
iid_exact = 2.0 * ((1 + MU3) ** 21 - 1) - ((1 + 2 * MU3) ** 21 - 1)
check("P3: the chained kernel runs give each path's calendar and daily return exactly as the direct products (1e-12), "
      "with no wipe-out", max(v["kernel_vs_direct"] for v in p3.values()) < 1e-12
      and all(v["terms"] == (-1, -1) for v in p3.values()))
check(f"P3: with MA = 0 the daily fund leads by 2 x C(21,2) x mu^2 = 6.72e-5 a period (all orders -6.77e-5) within 3 "
      f"standard errors (mean gap {p3[0.0]['gap']:+.2e}, se {p3[0.0]['se']:.1e})",
      abs(p3[0.0]["gap"] - (-2 * 210 * MU3 ** 2)) < 3 * p3[0.0]["se"] and abs(p3[0.0]["gap"] - iid_exact) < 3 * p3[0.0]["se"])
check("P3: for every MA the sign of the mean gap is the sign of -(C(21,2) mu^2 + 21 sigma^2/2 (VR - 1)): the calendar "
      "fund wins exactly when VR is below 1 - 20 mu^2/sigma^2 (about 0.968)",
      all(np.sign(v["gap"]) == np.sign(v["pred"]) and (v["gap"] > 0) == (v["vr"] < v["crossover"]) for v in p3.values()),
      {m_: (round(v["vr"], 3), f"{v['gap']:+.2e}") for m_, v in p3.items()})
gaps3 = [p3[m_]["gap"] for m_ in (-0.3, -0.1, 0.0, 0.1, 0.3)]
check("P3: the mean gap falls as MA rises (reversals help the calendar fund, continuations the daily one)",
      all(a_ > b_ for a_, b_ in zip(gaps3[:-1], gaps3[1:])), gaps3)
check("P3: eq. (13) to third order, with each path set's own VR and sigma^2, matches the mean gap within 4 standard "
      "errors for every MA (the second-order part alone is off by 2-3% of the gap at |MA| = 0.3)",
      all(abs(v["gap"] - v["pred3"]) < 4 * v["se"] for v in p3.values()),
      {m_: (f"{v['gap']:+.3e}", f"{v['pred3']:+.3e}", f"{v['se']:.1e}") for m_, v in p3.items()})

# =================================================================================================================
# P4. Properties on random paths, trigger on and off, with real-looking lows.
# =================================================================================================================
s_p4 = pd.DatetimeIndex(nyse.sessions(date(2000, 1, 3), date(2011, 12, 30)))          # 12 years of NYSE sessions
n4 = len(s_p4)
rng4 = np.random.default_rng(44)
paths4 = []
for vol in (0.010, 0.025):
    lv = 100.0 * np.exp(np.cumsum(rng4.normal(0.0003, vol, n4)))
    paths4.append(pd.Series(lv, index=s_p4))
crash4 = paths4[1].to_numpy(copy=True)
crash4[2000:] *= 0.62                                                 # a -38% day: the trigger fires in every mode
paths4.append(pd.Series(crash4, index=s_p4))
rate4 = pd.Series(np.clip(0.03 + np.cumsum(rng4.normal(0.0, 0.0004, n4)), 0.0, 0.12), index=s_p4)
base4 = dict(rate=rate4, spread_per_nav=0.02, fee=0.01)


def runs4(u, low, costs):
    """Every structure on one path: {label: NAV array}."""
    out = {}
    for reset in cal.RESETS:
        for mode in ("level", "close", "next_close"):
            for drop in (None, 0.35):
                out[(reset, mode, drop)] = k.periodic_reset_series(
                    u, costs["rate"], reset=reset, L=2.0, spread_per_nav=costs["spread_per_nav"], fee=costs["fee"],
                    early_drop=drop, early_mode=mode, trigger_low=low).to_numpy()
    out["daily"] = k.daily_reset_series(u, costs["rate"], L=2.0, spread_per_nav=costs["spread_per_nav"],
                                        fee=costs["fee"]).to_numpy()
    out["never"] = k.periodic_reset_series(u, costs["rate"], reset="never", L=2.0, spread_per_nav=costs["spread_per_nav"],
                                           fee=costs["fee"], early_drop=None).to_numpy()
    return out


finite_ok, mono_bad, scale_worst, n_runs = True, [], 0.0, 0
for pi, u in enumerate(paths4):
    low = pd.Series(u.to_numpy() * np.exp(-np.abs(rng4.normal(0.0, 0.012, n4))), index=s_p4)
    for low_used in (None, low):
        base = runs4(u, low_used, base4)
        n_runs += len(base)
        finite_ok &= all(np.isfinite(v).all() and (v >= 0).all() for v in base.values())
        for bump in ("rate", "spread_per_nav", "fee"):
            more = dict(base4)
            more[bump] = base4[bump] + 0.01
            hi = runs4(u, low_used, more)
            for key, v in base.items():
                if (hi[key] > v * (1 + 1e-12) + 1e-15).any():
                    mono_bad.append((pi, low_used is not None, bump, key))
        sc_low = None if low_used is None else low_used * 7.0
        scaled = runs4(u * 7.0, sc_low, base4)
        for key, v in base.items():
            both = np.maximum(np.abs(v), 1e-300)
            scale_worst = worst_of(scale_worst, float(np.max(np.abs(scaled[key] - v) / both)))
check(f"P4: no NaN, inf or negative NAV in any of {n_runs} runs (3 paths incl. a -38% day, close-only and with lows, "
      "3 resets x 3 modes x trigger on/off, daily, never)", finite_ok)
check("P4: NAV is non-increasing in the rate, the spread and the fee, row by row on the same path (+1 pt each)",
      not mono_bad, mono_bad[:5])
check(f"P4: scale invariance: the index (and its lows) x 7 gives the same NAV in every structure (worst rel diff "
      f"{scale_worst:.1e}, limit 1e-12)", scale_worst < 1e-12, scale_worst)
# The calendar fund with the trigger off equals the margin position inside its first period, up to the interest on
# interest the margin loan adds. Bound (derived in the R2 notes): with tau_t = sum of a_fin up to t, rates <= r_max,
# fee <= f_max, equity <= E_max = 2 max(u/u0), K = r_max + spread + f_max E_max:
#     0 <= calendar - margin <= K r_max tau_t^2 exp(r_max tau_t)
# (the gap grows by A_{t-1} r_t a_t a day, A the loan's excess over its start, A_t <= K tau_t exp(r_max tau_t)).
# For a quarter at 4%, 2% spread, 1% fee: K = 0.04 + 0.02 + 0.025 = 0.085, tau = 0.25: bound 2.2e-4.
first_ok, worst_ratio = True, 0.0
for u in paths4:
    for reset in cal.RESETS:
        pe = cal.period_end_flags(u.index, reset)
        e0 = int(np.flatnonzero(pe[1:])[0]) + 1                     # the first period end after row 0
        seg = u.iloc[:e0 + 1]
        cal_nav = k.periodic_reset_series(seg, rate4.iloc[:e0 + 1], reset=reset, L=2.0, spread_per_nav=0.02, fee=0.01,
                                          early_drop=None).to_numpy()
        mg_nav = k.periodic_reset_series(seg, rate4.iloc[:e0 + 1], reset="never", L=2.0, spread_per_nav=0.02, fee=0.01,
                                         early_drop=None).to_numpy()
        tau = np.cumsum(cal.accrual_fraction(seg.index, 360))
        r_max, e_max = float(rate4.iloc[:e0 + 1].max()), 2.0 * float((seg / seg.iloc[0]).max())
        bound = (r_max + 0.02 + 0.01 * e_max) * r_max * tau ** 2 * np.exp(r_max * tau)
        diff = cal_nav - mg_nav
        first_ok &= bool((diff >= -1e-15).all() and (diff <= bound + 1e-15).all())
        worst_ratio = worst_of(worst_ratio, float(np.max(diff[1:] / bound[1:])))
check(f"P4: inside the first period the calendar fund (trigger off) equals the margin position up to the "
      f"interest-on-interest bound, on every row, all resets and paths (largest gap / bound {worst_ratio:.2f})",
      first_ok and worst_ratio <= 1.0)

# =================================================================================================================
# P5. A second implementation: the calendar NAV with zero fee and the trigger off, written in closed form per period
#     and vectorized (no loop over rows):  nav[t] = NAV0 x (L u[t]/U0 - (L-1) - (F[t] - F[b])), where b is the last
#     reset row before t, U0 = u[b], F = cumsum of ((L-1) rate + spread) x a_fin, and NAV0 at each reset row is the
#     running product of the previous periods' end values.
# =================================================================================================================


def calendar_closed_form(u, rate, a_fin, pe, L, spread):
    n = len(u)
    F = np.cumsum(((L - 1.0) * rate + spread) * a_fin)
    resets = np.r_[0, np.flatnonzero(pe[1:]) + 1]                     # row 0 is a reset, then every flagged row
    t = np.arange(n)
    which = np.searchsorted(resets, t, side="left") - 1               # index of the last reset STRICTLY before t
    which[0] = 0
    b = resets[which]
    growth = L * u / u[b] - (L - 1.0) - (F - F[b])                    # value per unit of NAV0 within the period
    growth[0] = 1.0
    nav0_at = np.cumprod(np.r_[1.0, growth[resets[1:]]])              # NAV0 of each period = product of earlier ends
    out = nav0_at[which] * growth
    out[0] = 1.0
    return out


rng5 = np.random.default_rng(55)
worst_p5, n_p5 = 0.0, 0
for seed_vol in (0.008, 0.015):
    lv = pd.Series(100.0 * np.exp(np.cumsum(rng5.normal(0.0003, seed_vol, n4))), index=s_p4)
    rt = np.clip(0.03 + np.cumsum(rng5.normal(0.0, 0.0004, n4)), 0.0, 0.12)
    a_fin = cal.accrual_fraction(s_p4, 360)
    for reset in cal.RESETS:
        pe = cal.period_end_flags(s_p4, reset)
        kern = k.periodic_reset_series(lv, pd.Series(rt, index=s_p4), reset=reset, L=2.0, spread_per_nav=0.022, fee=0.0,
                                       early_drop=None).to_numpy()
        closed = calendar_closed_form(lv.to_numpy(), rt, a_fin, pe, 2.0, 0.022)
        worst_p5 = worst_of(worst_p5, float(np.max(np.abs(closed - kern) / kern)))
        n_p5 += 1
check(f"P5: the vectorized closed form equals the numba calendar kernel on every row ({n_p5} runs: 2 paths x weekly, "
      f"monthly, quarterly; worst rel diff {worst_p5:.1e}, limit 1e-12)", worst_p5 < 1e-12, worst_p5)
