#!/usr/bin/env python3
"""Worked examples for THEORY.md (BACKLOG B18): every number THEORY.md quotes is computed here, never typed.

    py docs\\theory_examples.py        writes docs/theory_examples.json and results/theory_payoff.png,
                                       results/theory_leverage.png

Every example uses planted inputs (made-up returns, rates and volatilities), so it needs no market data and a stranger
reproduces it exactly. Each example calls the package's own functions (the kernels, leverage.py, stats.py, options.py,
backtest.py), and where the theory gives a closed form, it computes the closed form on its own next to the kernel's
answer. tests/test_theory.py recomputes `compute()` and compares it with the JSON, and the prose pins read the JSON.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from calendar_letf import backtest, kernel, leverage, montecarlo, options, periods, products, provenance, stats  # noqa: E402

OUT_JSON = ROOT / "docs" / "theory_examples.json"
FIG_PAYOFF = ROOT / "results" / "theory_payoff.png"
FIG_LEVERAGE = ROOT / "results" / "theory_leverage.png"
SEED = 20261106


def one_period(u, L, early_drop=0.0, mode=kernel.EARLY_LEVEL, rate=0.0, fee=0.0, spread=0.0, dates=None):
    """Calendar-kernel NAV over ONE reset period (no period end inside), zero costs unless given, trigger on u."""
    u = np.asarray(u, dtype=np.float64)
    n = len(u)
    acc = np.zeros(n) if dates is None else periods.accrual_fraction(dates, 360)
    acc_fee = np.zeros(n) if dates is None else periods.accrual_fraction(dates, 365)
    nav, flags, term = kernel.periodic_reset_nav(u, u.copy(), u.copy(), np.full(n, rate), acc, acc_fee, np.zeros(n, dtype=np.bool_),
                                                 float(L), float(spread), np.full(n, fee), float(early_drop), mode)
    return nav, flags, term


def daily(u, L, rate=0.0, fee=0.0, spread=0.0, dates=None):
    u = np.asarray(u, dtype=np.float64)
    n = len(u)
    acc = np.zeros(n) if dates is None else periods.accrual_fraction(dates, 360)
    acc_fee = np.zeros(n) if dates is None else periods.accrual_fraction(dates, 365)
    nav, term = kernel.daily_reset_nav(u, np.full(n, rate), acc, acc_fee, float(L), float(spread), np.full(n, fee))
    return nav, term


def planted_daily(seed, n, mu, sigma):
    """n daily returns whose sample mean and SD are EXACTLY mu / 252 and sigma / sqrt(252) (standardized normal draws),
    so a sample statistic can be set next to the closed form of the planted law without sampling noise in the drift."""
    z = np.random.default_rng(seed).standard_normal(n)
    return mu / 252.0 + sigma / math.sqrt(252.0) * (z - z.mean()) / z.std()


def level_from_returns(r):
    return np.concatenate(([1.0], np.cumprod(1.0 + np.asarray(r, dtype=np.float64))))


def elementary_symmetric(r):
    """e_0 .. e_T of the returns r (the coefficients of prod (1 + x r_t) in x)."""
    e = np.zeros(len(r) + 1)
    e[0] = 1.0
    for x in r:
        e[1:] = e[1:] + x * e[:-1]
    return e


# ---------------------------------------------------------------- Part I and II examples

def ex_two_day():
    """Two days at 2x with no costs: a trend (+10%, +10%) and a reversal (+10%, -10%)."""
    out = {}
    for name, r in (("trend", (0.10, 0.10)), ("reversal", (0.10, -0.10))):
        u = level_from_returns(r)
        cal = float(one_period(u, 2.0)[0][-1])
        dly = float(daily(u, 2.0)[0][-1])
        e2 = float(elementary_symmetric(r)[2])
        out[name] = dict(r=list(r), index=float(u[-1]), calendar=cal, daily=dly, gap=cal - dly, e2=e2,
                         second_order=(2.0 - 4.0) * e2)
    return out


def ex_effective_leverage():
    """L_t = L (1 + R) / (1 + L R) after an index return R since the reset; read off the kernel by a nudge as well."""
    rows = []
    for R in (0.10, -0.10, -0.20, -0.30, -0.35):
        closed = 2.0 * (1.0 + R) / (1.0 + 2.0 * R)
        u = np.array([1.0, 1.0 + R, (1.0 + R) * (1.0 + 1e-7)])
        nav = one_period(u, 2.0)[0]
        kern = (nav[2] / nav[1] - 1.0) / 1e-7
        rows.append(dict(R=R, closed=closed, kernel=float(kern)))
    return dict(L=2.0, rows=rows)


def ex_wipeout():
    """The in-period index fall that takes NAV to zero (1/L), the fund value left at a level-fill early reset (1 - L d),
    and the scaled trigger 0.70 / L."""
    rows = []
    for L in (1.2, 1.5, 2.0, 3.0):
        u = np.array([1.0, 1.0 - 1.0 / L + 1e-9, 1.0 - 1.0 / L - 1e-9])
        nav, _, term = one_period(u, L)
        rows.append(dict(L=L, wipe_fall=1.0 / L, kernel_terminates_past_it=bool(term == 2),
                         scaled_drop=products.trigger_for(L, "scaled")[0]))
    u = np.array([1.0, 0.60])                                  # a gap far below the 35% line in one day
    lvl = one_period(u, 2.0, early_drop=0.35, mode=kernel.EARLY_LEVEL)
    cls = one_period(u, 2.0, early_drop=0.35, mode=kernel.EARLY_CLOSE)
    return dict(rows=rows, trigger=dict(drop=0.35, left_at_level=1.0 - 2.0 * 0.35,
                                        level_fill_nav=float(lvl[0][-1]), close_fill_nav=float(cls[0][-1]),
                                        index_close=0.60))


def ex_price_trigger():
    """A level fill when the trigger watches the PRICE and the fund holds the TOTAL return: dividends since the reset make
    the total return fall less than the price, so the fund keeps more than 1 - L delta at the trigger moment. Planted: the
    total return stands 1% above the price since the reset (U_ref / X_ref = 1.01 U_0 / X_0), and the day's low touches -40%."""
    wedge, L, d = 0.01, 2.0, 0.35
    X = np.array([100.0, 100.0, 61.0])
    XL = np.array([100.0, 100.0, 60.0])
    U = np.array([100.0, 100.0 * (1 + wedge), 61.0 * (1 + wedge)])
    nav, flags, _ = kernel.periodic_reset_nav(U, X, XL, np.zeros(3), np.zeros(3), np.zeros(3), np.zeros(3, dtype=np.bool_),
                                              L, 0.0, np.zeros(3), d, kernel.EARLY_LEVEL)
    v_hit = 1.0 + L * ((1.0 - d) * (1.0 + wedge) - 1.0)       # equation 30 by hand: U_hit = X_hit U_ref / X_ref
    close = v_hit * (1.0 + L * ((61.0 * (1 + wedge)) / ((1.0 - d) * 100.0 * (1 + wedge)) - 1.0))
    return dict(wedge=wedge, drop=d, plain=1.0 - L * d, v_hit=v_hit, kernel_close=float(nav[-1]), hand_close=close,
                early_reset=bool(flags[-1]))


def ex_rebalance():
    """A daily fund's end-of-day trade after an index move r: L (L - 1) r per unit of NAV (buy after a rise)."""
    rows = []
    for L, r in ((2.0, 0.01), (2.0, -0.01), (3.0, 0.01)):
        nav0 = 100.0
        exposure = L * nav0 * (1.0 + r)                       # the exposure drifts with the index
        nav1 = nav0 * (1.0 + L * r)
        trade = L * nav1 - exposure                           # what restores exposure = L x NAV
        rows.append(dict(L=L, r=r, nav=nav0, trade=trade, closed=L * (L - 1.0) * r * nav0))
    return dict(rows=rows)


def ex_drag():
    """Volatility drag of a daily fund against L times the index's log return: L (L - 1) sigma^2 / 2 a year."""
    sigma = 0.20
    rows = [dict(L=L, drag=L * (L - 1.0) * sigma * sigma / 2.0) for L in (1.5, 2.0, 3.0)]
    # the same on a planted path: 252 days of +/- sigma/sqrt(252), alternating, so the index ends flat in log terms
    d = sigma / math.sqrt(252.0)
    r = np.array([math.exp(d) - 1.0 if i % 2 == 0 else math.exp(-d) - 1.0 for i in range(252)])
    u = level_from_returns(r)
    nav = daily(u, 2.0)[0]
    path = dict(index_log=float(math.log(u[-1])), fund_log=float(math.log(nav[-1])), sum_r2=float(np.sum(r * r)))
    return dict(sigma=sigma, rows=rows, path=path)


def ex_log_formula():
    """The daily log formula on a planted 63-day trend (+30% at 3x): the raw sum of squared returns against the demeaned
    sum that Avellaneda-Zhang eq. (5) and Leung-Santoli eq. (2.8) write. Demeaning drops L (L - 1) / 2 x T x mean(r)^2."""
    rng = np.random.default_rng(SEED + 4)
    T, L = 63, 3.0
    z = rng.standard_normal(T)
    r = math.log(1.30) / T + 0.01 * (z - z.mean()) / z.std()
    r = np.exp(r) - 1.0                                        # simple returns whose index ends exactly 30% up
    u = level_from_returns(r)
    exact = float(math.log(daily(u, L)[0][-1]))
    base = L * math.log(u[-1])
    raw = base - L * (L - 1.0) / 2.0 * float(np.sum(r * r))
    demeaned = base - L * (L - 1.0) / 2.0 * float(np.sum((r - r.mean()) ** 2))
    # the order of the error: with no costs the raw form misses by sum (L^3 - L) r^3 / 3 + ..., so halving every daily
    # return cuts the error about 8 times (third order); planted zero-mean path, 3x, 63 days
    z0 = np.random.default_rng(SEED + 5).normal(0.0, 0.02, T)
    errs = []
    for scale in (1.0, 0.5, 0.25):
        q = scale * z0
        lv = math.log(daily(level_from_returns(q), L)[0][-1])
        errs.append(lv - (L * float(np.sum(np.log1p(q))) - L * (L - 1.0) / 2.0 * float(np.sum(q * q))))
    return dict(T=T, L=L, index_return=float(u[-1] - 1.0), kernel_log=exact, raw_error=raw - exact,
                demeaned_error=demeaned - exact, dropped_term=L * (L - 1.0) / 2.0 * T * float(r.mean()) ** 2,
                order_ratios=[errs[0] / errs[1], errs[1] / errs[2]])


def ex_gap_orders():
    """Calendar minus daily over one 21-day period at 2x: the kernels, Bessembinder's exact sum, and its second order."""
    rng = np.random.default_rng(SEED)
    r = rng.normal(0.0004, 0.012, 21)
    u = level_from_returns(r)
    cal, dly = float(one_period(u, 2.0)[0][-1]), float(daily(u, 2.0)[0][-1])
    e = elementary_symmetric(r)
    beta = 2.0
    exact = float(sum((beta - beta ** k) * e[k] for k in range(2, len(e))))
    second = float((beta - beta ** 2) * e[2])
    ss = float(np.sum(r * r))
    s2 = float(np.sum(r) ** 2)
    return dict(T=21, kernel_gap=cal - dly, exact_sum=exact, second_order=second,
                ss_form=beta * (beta - 1.0) / 2.0 * (ss - s2), rel_error_second=abs(second - exact) / abs(exact))


def ex_crossover():
    """Bessembinder's expected gap per 21-day period and the variance ratio where its sign flips (beta = 2)."""
    mu, sigma, T = 0.0004, 0.01, 21
    rows = []
    for vr in (0.90, 0.95, 1.00, 1.05):
        p = stats.predicted_reset_gap(mu, sigma, vr, T, 2.0)
        rows.append(dict(vr=vr, gap=p["gap_per_period"], sign=p["sign"]))
    cross = stats.predicted_reset_gap(mu, sigma, 1.0, T, 2.0)["crossover_vr"]
    phi = -0.05
    # iid returns: E[e_k] = C(T, k) mu^k exactly, so the share of the terms k >= 3 in the expected gap is exact here
    m3, beta = 0.001, 2.0
    terms = {k: (beta - beta ** k) * math.comb(T, k) * m3 ** k for k in range(2, T + 1)}
    third = dict(mu=m3, share=sum(v for k, v in terms.items() if k >= 3) / terms[2], approx=(1 + beta) * (T - 2) * m3 / 3)
    return dict(mu=mu, sigma=sigma, T=T, rows=rows, crossover_vr=cross,
                ar1=dict(phi=phi, vr=montecarlo.ar1_variance_ratio(phi, T)), higher_order_iid=third)


def ex_kelly():
    """Growth g(L) = r + L (mu - r - s) - f - L^2 sigma^2 / 2 a year, its optimum (mu - r - s) / sigma^2 and the plateau."""
    r, mu, sigma = 0.04, 0.10, 0.16
    out = {}
    for s in (0.0, 0.01):
        Ls = (mu - r - s) / sigma ** 2
        g = {L: r + L * (mu - r - s) - L * L * sigma ** 2 / 2.0 for L in (1.0, 1.5, 2.0, 3.0)}
        g[round(Ls, 4)] = r + Ls * (mu - r - s) - Ls * Ls * sigma ** 2 / 2.0
        width = math.sqrt(2.0 * 0.0025) / sigma                # |L - L*| that costs 0.25% a year
        out[f"s{s:g}"] = dict(spread=s, L_star=Ls, growth={f"{k:g}": v for k, v in g.items()}, half_width_25bp=width)
    # the sample form on a planted daily series: leverage.kelly_daily against a grid search of the kernel
    n = 252 * 20
    rd = planted_daily(SEED + 1, n, mu, sigma)
    u = level_from_returns(rd)
    import pandas as pd
    dates = pd.bdate_range("2000-01-03", periods=n + 1)
    a = periods.accrual_fraction(dates, 360)
    k_closed = leverage.kelly_daily(rd, np.full(n, r), a[1:])
    grid = np.round(np.arange(1.0, 4.001, 0.01), 2)
    logw = [float(math.log(daily(u, L, rate=r, dates=dates)[0][-1])) for L in grid]
    # equation 17 in sample form, G(L) = L sum r - (L - 1) sum rho a - L^2 sum r^2 / 2, against the kernel's log wealth
    Sr, Sr2, Sra = float(rd.sum()), float(np.sum(rd * rd)), float(r * a[1:].sum())
    growth = [dict(L=L, kernel=float(math.log(daily(u, L, rate=r, dates=dates)[0][-1])),
                   second_order=L * Sr - (L - 1.0) * Sra - L * L * Sr2 / 2.0) for L in (1.0, 2.0, 3.0)]
    return dict(r=r, mu=mu, sigma=sigma, cases=out,
                sample=dict(years=20, rate_years=float(a[1:].sum()), kelly_closed=k_closed,
                            grid_best=float(grid[int(np.argmax(logw))]), growth=growth))


def ex_break_even():
    """The fee at which a fund at L grows as fast as the index: closed form a year, and kernel against second order."""
    r, mu, sigma, s = 0.04, 0.10, 0.16, 0.005
    closed = {f"{L:g}": (L - 1.0) * (mu - r) - L * s - (L * L - 1.0) * sigma ** 2 / 2.0 for L in (1.2, 1.5, 2.0)}
    import pandas as pd
    n = 252 * 20
    rd = planted_daily(SEED + 2, n, mu, sigma)
    u = level_from_returns(rd)
    dates = pd.bdate_range("2000-01-03", periods=n + 1)
    a_fin = periods.accrual_fraction(dates, 360)
    a_fee = periods.accrual_fraction(dates, 365)
    L = 1.5
    target = float(math.log(u[-1]))
    res = leverage.break_even_fee(lambda f: float(math.log(daily(u, L, rate=r, fee=f, spread=s * L, dates=dates)[0][-1])), target)
    k = ((L - 1.0) * r + s * L) * a_fin[1:]
    second = leverage.break_even_fee_second_order(rd, k, a_fee[1:], L)
    return dict(r=r, mu=mu, sigma=sigma, spread_per_turn=s, closed=closed,
                sample=dict(L=L, years=20, rate_years=float(a_fin[1:].sum()), fee_years=float(a_fee[1:].sum()),
                            kernel=res["fee"], second_order=second))


# ---------------------------------------------------------------- Part III examples

def ex_accrual():
    """A Friday-to-Monday step: financing on ACT/360, the fee on ACT/365, at a 5% rate on one borrowed turn and a 1% fee."""
    import pandas as pd
    d = pd.DatetimeIndex(["2026-10-02", "2026-10-05"])
    a_fin = float(periods.accrual_fraction(d, 360)[1])
    a_fee = float(periods.accrual_fraction(d, 365)[1])
    return dict(days=3, a_fin=a_fin, a_fee=a_fee, financing_5pct=0.05 * a_fin, fee_1pct=0.01 * a_fee,
                financing_on_365=0.05 * 3 / 365)


def ex_margin():
    """Ten years of a flat index at a 5% rate: the buy-once margin loan compounds, the never-reset calendar kernel
    charges simple interest; the gap is about (rate x years)^2 / 2 of the loan."""
    import pandas as pd
    dates = pd.bdate_range("2010-01-04", "2020-01-03")
    u = pd.Series(1.0, index=dates)
    rate = pd.Series(0.05, index=dates)
    marg = kernel.periodic_reset_series(u, rate, reset="never", L=2.0, spread_per_nav=0.0, fee=0.0, early_drop=None)
    n = len(dates)
    acc = periods.accrual_fraction(dates, 360)
    simple, _, _ = kernel.periodic_reset_nav(np.ones(n), np.ones(n), np.ones(n), np.full(n, 0.05), acc, np.zeros(n),
                                             np.zeros(n, dtype=np.bool_), 2.0, 0.0, np.zeros(n), 0.0, kernel.EARLY_LEVEL)
    years = float(acc.sum() * 360 / 365.25)
    x = 0.05 * acc
    return dict(years=years, margin_nav=float(marg.iloc[-1]), simple_nav=float(simple[-1]),
                gap=float(simple[-1] - marg.iloc[-1]), interest_on_interest=float(np.prod(1.0 + x) - 1.0 - x.sum()),
                second_order=float(x.sum() ** 2 / 2.0))


def ex_cash_yield():
    """A bank-discount rate turned into the investment yield the cash leg accrues: 365 d / (360 - 91 d)."""
    return dict(rows=[dict(discount=d, yield_=backtest.discount_to_investment_yield(d)) for d in (0.01, 0.05)])


def ex_structure():
    """A balance sheet of swaps on s turns, an ETF holding of 2 - s and cash k earning c x the rate (validate.Structure)."""
    from calendar_letf import validate
    st = validate.Structure(1.5, 0.5, 0.9)
    # equation 1 at a reset: d + s = L and d + k = 1, for a few direct holdings d; with d = 0 and c = 1 the balance sheet
    # pays the kernels' cost: (L - 1) rate turns and L spread turns
    rows = []
    for L in (1.5, 2.0, 3.0):
        for d in (0.0, 0.4):
            s, k = L - d, 1.0 - d
            b = validate.Structure(s, k, 1.0)
            rows.append(dict(L=L, d=d, swap_turns=s, cash_nav=k, exposure=d + s, holdings=d + k,
                             rate_turns=b.rate_turns, spread_turns=b.spread_turns))
    return dict(swap_turns=1.5, cash_nav=0.5, cash_yield=0.9, rate_turns=st.rate_turns, spread_turns=st.spread_turns,
                rate=0.04, spread=0.01, financing=st.rate_turns * 0.04 + st.spread_turns * 0.01, at_reset=rows)


def ex_option():
    """A two-year call at 2x leverage on an index at 100 (planted r, q, sigma): its strike, put and loan."""
    S, T, r, q, vol = 100.0, 2.0, 0.04, 0.015, 0.18
    flat = options.skewed_vol(vol, S, 0.0)
    K = options.strike_for_leverage(2.0, S, T, r, q, flat)
    C = options.call(S, K, T, r, q, vol)
    P = options.put(S, K, T, r, q, vol)
    loan = K * math.exp(-r * T)
    tv = options.term_vol(0.30, 0.18 ** 2, 2.0, 2.0)
    h = 1e-4                                                      # the leverage of equation 24 by a central difference in S
    lev_fd = (options.call(S + h, K, T, r, q, vol) - options.call(S - h, K, T, r, q, vol)) / (2 * h) * S / C
    return dict(S=S, T=T, r=r, q=q, sigma=vol, K=K, call=C, put=P, loan=loan, put_share=P / C,
                leverage=options.leverage(S, K, T, r, q, vol), leverage_fd=lev_fd,
                parity_gap=C - P - (S * math.exp(-q * T) - loan), term_vol=dict(vix=0.30, theta_vol=0.18, kappa=2.0, T=2.0, vol=tv))


def ex_variance_ratio():
    """stats.variance_ratio on a planted AR(1) series against the AR(1) closed form."""
    rng = np.random.default_rng(SEED + 3)
    phi, n, q = -0.10, 1_000_000, 21
    x = np.empty(n)
    z = rng.standard_normal(n)
    x[0] = z[0]
    for t in range(1, n):
        x[t] = phi * x[t - 1] + math.sqrt(1 - phi * phi) * z[t]
    v = stats.variance_ratio(0.01 * x, q)
    return dict(phi=phi, n=n, q=q, vr=v["vr"], z_robust=v["z_robust"], closed=montecarlo.ar1_variance_ratio(phi, q))


def ex_median_interval():
    """The distribution-free interval of a median over N draws (coverage.quantile_interval): its ranks and its exact
    coverage P(r <= B <= s - 1), B ~ Binomial(N, 1/2), by an exact sum of binomial terms (no scipy)."""
    from calendar_letf import coverage
    out = []
    for N in (400, 5000):
        x = np.arange(1.0, N + 1.0)
        lo, hi = coverage.quantile_interval(x, 0.5)
        r_, s_ = int(lo), int(hi)                                 # x is 1..N, so the values are the ranks
        logp = [math.lgamma(N + 1) - math.lgamma(k + 1) - math.lgamma(N - k + 1) - N * math.log(2.0) for k in range(r_, s_)]
        out.append(dict(N=N, rank_lo=r_, rank_hi=s_, coverage=float(sum(math.exp(v) for v in logp))))
    return dict(rows=out)


def compute():
    return dict(two_day=ex_two_day(), effective_leverage=ex_effective_leverage(), wipeout=ex_wipeout(),
                rebalance=ex_rebalance(), drag=ex_drag(), log_formula=ex_log_formula(), gap_orders=ex_gap_orders(), crossover=ex_crossover(),
                kelly=ex_kelly(), break_even=ex_break_even(), accrual=ex_accrual(), margin=ex_margin(),
                cash_yield=ex_cash_yield(), structure=ex_structure(), option=ex_option(), variance_ratio=ex_variance_ratio(),
                price_trigger=ex_price_trigger(), median_interval=ex_median_interval())


# ---------------------------------------------------------------- figures

def figures(ex):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    R = np.linspace(-0.45, 0.30, 301)
    cal = np.where(R > -0.35, 1 + 2 * R, (1 - 0.70) * (1 + 2 * ((1 + R) / 0.65 - 1)))
    cal_none = np.maximum(1 + 2 * R, 0.0)
    dly = (1 + 2 * ((1 + R) ** (1 / 21) - 1)) ** 21                # 21 equal daily moves
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=120)
    ax.plot(R * 100, cal_none, color="#9aa4b1", lw=1.2, ls="--", label="calendar 2x, no early reset")
    ax.plot(R * 100, cal, color="#1f5fa8", lw=2.0, label="calendar 2x, early reset at -35% (level fill)")
    ax.plot(R * 100, dly, color="#c2571a", lw=1.6, label="daily 2x, 21 equal daily moves")
    ax.axvline(-35, color="#666", lw=0.8, ls=":")
    ax.set_xlabel("index return since the last reset (%)")
    ax.set_ylabel("fund NAV / NAV at the reset")
    ax.set_title("One period, no costs: the calendar payoff is a straight line in the index return", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_PAYOFF)
    plt.close(fig)
    R = np.linspace(-0.36, 0.40, 300)
    fig, ax = plt.subplots(figsize=(7.2, 4.0), dpi=120)
    for L, c in ((1.5, "#6b8e23"), (2.0, "#1f5fa8"), (3.0, "#a83232")):
        RR = R[1 + L * R > 0.05]
        ax.plot(RR * 100, L * (1 + RR) / (1 + L * RR), color=c, lw=1.8, label=f"{L:g}x")
    ax.set_xlabel("index return since the last reset (%)")
    ax.set_ylabel("effective leverage")
    ax.set_ylim(0.8, 8)
    ax.set_title("Leverage drifts inside a period: L(1 + R) / (1 + L R)", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_LEVERAGE)
    plt.close(fig)


def main():
    ex = compute()
    doc = dict(meta=dict(title="Worked examples for THEORY.md", code=provenance.code_fingerprint(Path(__file__)),
                         seed=SEED, figures=[FIG_PAYOFF.name, FIG_LEVERAGE.name],
                         note="planted inputs only; no market data"),
               examples=ex)
    OUT_JSON.write_text(json.dumps(provenance.json_safe(doc), indent=1, allow_nan=False) + "\n", encoding="utf-8")
    figures(ex)
    print(f"wrote {OUT_JSON.relative_to(ROOT).as_posix()}, {FIG_PAYOFF.relative_to(ROOT).as_posix()}, "
          f"{FIG_LEVERAGE.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
