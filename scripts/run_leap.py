"""B15: is a calendar fund a "better LEAP"? A rolling two-year call on the S&P 500 with its leverage set to L at each
roll, against the calendar fund at the same L.

    py scripts\\run_leap.py        (from calendar_letf/, with CALENDAR_LETF_DATA / _RATES set; about a minute)

The LEAP position holds only calls (calendar_letf/options.py, Black-Scholes-Merton WITH the index's dividend yield). At
each roll it sells its call and buys a new two-year call whose leverage delta x S / C equals the target L. Inputs, all
read from data or labeled:
  index      the S&P 500 price index (the call is on the price; the fund's swap earns the total return)
  q          the trailing one-year dividend yield, from the total-return and price series (log difference)
  r          effective fed funds known the day before (the fund's own reference rate), an ACT/360 overnight rate, turned into
             the continuous rate that the option formula needs: 365 x ln(1 + r / 360) (daily compounding on a 365-day year)
  volatility CBOE VIX (from 1990): the two-year implied volatility by mean reversion of variance toward theta, the mean
             of VIX^2 from 1990 up to the day (an expanding mean: causal, no later data), with TERM_KAPPA (ASSUMED), times a
             skew for strikes below the index (SKEWS flat / base / steep, ASSUMED)
  costs      a round-trip cost per roll as a share of the option's value (ROLL_COSTS, ASSUMED: deep in-the-money LEAPs
             trade wide)
The comparator is the calendar fund at the same L and reset (the B17 designs at the B19 and Tradr cost anchors, trigger
at 0.70 / L). Strikes under STRIKE_TRADED x the index are flagged UNTRADED: such strikes are not listed, so those rows
compare financing rates, not tradeable positions. The Nasdaq-100 is out of scope: no implied-volatility series of it
(VXN) is in the price library.
Writes results/leap.json and results/leap.md.
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import run_sub2x as sub2x  # noqa: E402
from calendar_letf import bottoms as B  # noqa: E402
from calendar_letf import kernel, leverage, loader, metrics, options as opt, periods, provenance, series, study  # noqa: E402

OUT = ROOT / "results"
CAPTION = "Data: TradingView (via local export), FRED. Model option prices and HYPOTHETICAL funds; no real option quotes. Not investment advice."
NAME = "SPX"
VIX = "CBOE:VIX"
LS = (1.2, 1.5, 1.7, 2.0)
T_YEARS = 2.0
ROLLS = ("quarterly", "yearly")
SKEWS = {"flat": 0.0, "base": 0.25, "steep": 0.5}
BASE_SKEW = "base"
ROLL_COSTS = (0.0, 0.005, 0.01)
BASE_ROLL_COST = 0.005
TERM_KAPPA = 2.0             # mean reversion of variance a year (half-life about four months), ASSUMED
STRIKE_TRADED = 0.5          # strikes below half the index are not listed (BACKLOG B15), ASSUMED
FUND_RESET = "quarterly"
HOLD_YEARS_AFTER_BOTTOM = 3


def inputs(w):
    """Aligned daily arrays from the first VIX close: price S, total return u, yield q, rate r, VIX (decimal), dates."""
    px = series.spx_price().loc[:sub2x.STUDY_END].reindex(w.dates)
    vix = loader.close(VIX).loc[:sub2x.STUDY_END].reindex(w.dates).ffill()
    tr = w.u
    q = (np.log(tr / tr.shift(252)) - np.log(px / px.shift(252)))      # trailing one-year dividend yield (continuous)
    df = pd.DataFrame(dict(S=px, u=tr, q=q, r=w.rate, vix=vix / 100.0)).dropna()
    first = df.index[df.index >= loader.close(VIX).index[0]][0]
    return derived(df.loc[first:].copy())


def derived(df):
    """Add the two derived inputs, each known on its own day: rc, the continuous equivalent of the ACT/360 rate
    (365 ln(1 + r / 360), daily compounding on a 365-day year), and theta, the mean of VIX^2 from the first row up to
    and including the day (an expanding mean: no later data). tests/test_leap.py plants both."""
    df["rc"] = 365.0 * np.log1p(df["r"] / 360.0)
    v2 = df["vix"].to_numpy() ** 2
    df["theta"] = np.cumsum(v2) / np.arange(1, len(v2) + 1)
    return df


def roll_flags(dates, roll):
    if roll == "quarterly":
        return periods.period_end_flags(dates, "quarterly")
    q = periods.period_end_flags(dates, "quarterly")
    return q & (pd.DatetimeIndex(dates).month == 12)


def leap_path(df, L, roll, skew, cost):
    """Wealth of the all-calls position (1.0 at the first roll) and its daily leverage; the strikes and put costs at
    each roll. The call is priced each day at that day's rate (continuous), yield, VIX and theta (all known that day)."""
    S, r, q, v, theta = (df[c].to_numpy() for c in ("S", "rc", "q", "vix", "theta"))
    dates = df.index
    rf = roll_flags(dates, roll)
    first = int(np.flatnonzero(rf)[0])
    W = np.full(len(dates), np.nan)
    lev = np.full(len(dates), np.nan)
    rolls = []
    units = K = t0 = None
    for t in range(first, len(dates)):
        if units is not None:
            tau = T_YEARS - (dates[t] - dates[t0]).days / 365.25
            vk = opt.skewed_vol(opt.term_vol(v[t], theta[t], TERM_KAPPA, tau), S[t], SKEWS[skew])(K)
            c = opt.call(S[t], K, tau, r[t], q[t], vk)
            W[t] = units * c
            lev[t] = opt.leverage(S[t], K, tau, r[t], q[t], vk)
        if t == first or rf[t]:
            wealth = 1.0 if units is None else W[t] * (1.0 - cost / 2.0)          # sell at the bid
            atm = opt.term_vol(v[t], theta[t], TERM_KAPPA, T_YEARS)
            volk = opt.skewed_vol(atm, S[t], SKEWS[skew])
            K = opt.strike_for_leverage(L, S[t], T_YEARS, r[t], q[t], volk)
            c0 = opt.call(S[t], K, T_YEARS, r[t], q[t], volk(K))
            units = wealth / (c0 * (1.0 + cost / 2.0))                          # buy at the ask
            t0 = t
            W[t] = wealth
            lev[t] = L
            p0 = opt.put(S[t], K, T_YEARS, r[t], q[t], volk(K))
            rolls.append(dict(date=str(dates[t].date()), strike_over_spot=K / S[t], put_cost_per_year=p0 / c0 / T_YEARS,
                              vol=volk(K), q=q[t], r=r[t]))
    return pd.Series(W, index=dates), pd.Series(lev, index=dates), rolls


def fund_path(w, df, L, cname, costs):
    spec = sub2x.spec_at(NAME, FUND_RESET, L, sub2x.HEADLINE_TRIGGER, sub2x.BASE_BASIS)
    enc = study.encoding_at(costs[cname], L, sub2x.BASE_BASIS)
    nav = kernel.run(spec, w.u, study.scaled_rate(w.rate, enc), trigger=w.trigger, trigger_low=w.trigger_low,
                     early_mode=study.BASE_MODE, **study.kernel_kwargs(spec, enc))
    return nav.reindex(df.index), spec


def stats_of(level, df):
    x = level.dropna()
    s, e = x.index[0], x.index[-1]
    yrs = (e - s).days / 365.25
    me = periods.period_end_flags(x.index, "monthly")
    rows = np.flatnonzero(me)
    pairs = [(a, b) for a, b in zip(rows[:-120], rows[120:])]
    c10 = [(x.iloc[b] / x.iloc[a]) ** (1 / ((x.index[b] - x.index[a]).days / 365.25)) - 1 if x.iloc[a] > 0 else np.nan for a, b in pairs]
    return dict(first=str(s.date()), last=str(e.date()), cagr=float((x.iloc[-1] / x.iloc[0]) ** (1 / yrs) - 1) if x.iloc[-1] > 0 else -1.0,
                max_dd=metrics.max_drawdown(x.to_numpy()), cagr10_median=float(np.nanmedian(c10)) if c10 else None, n10=len(c10))


def episodes(df, series_):
    """$10,000 through each covered key period, and from the index's lowest close inside it for HOLD_YEARS_AFTER_BOTTOM
    years (the bottom is read from the data, a hindsight entry)."""
    out = []
    S = df["S"]
    for label, d0, d1 in study.KEY_PERIODS:
        if pd.Timestamp(d0) < df.index[0] + pd.Timedelta(days=400):
            continue
        a = S.index[S.index < pd.Timestamp(d0)][-1]
        b = S.loc[:d1].index[-1]
        bottom = S.loc[d0:d1].idxmin()
        end = S.loc[:bottom + pd.DateOffset(years=HOLD_YEARS_AFTER_BOTTOM)].index[-1]
        row = dict(period=label, first_close=str(a.date()), last_close=str(b.date()), bottom=str(bottom.date()), bottom_end=str(end.date()))
        for k, s_ in series_.items():
            row[k] = dict(period=10000.0 * float(s_.loc[b] / s_.loc[a]), from_bottom=10000.0 * float(s_.loc[end] / s_.loc[bottom]))
        out.append(row)
    return out


def pc(x, d=1):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.{d}f}%"


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]) + "\n"


def markdown(res):
    m = res["meta"]
    md = [f"# {m['title']}\n", f"*{m['caption']}*\n", "```", *m["banner"], "```\n",
          f"Window {m['window'][0]} to {m['window'][1]} (VIX starts 1990). Two-year calls, leverage set to L at each roll; theta = "
          f"{m['theta_rule']} ({m['theta_last']:.4f} at the end), kappa {TERM_KAPPA}; rate {m['rate_rule']}; skews {SKEWS}; base roll cost {BASE_ROLL_COST:.1%} round trip. Index total return: "
          f"CAGR {pc(res['index']['cagr'], 2)}, max DD {pc(res['index']['max_dd'])}.\n",
          "## Full window\n",
          md_table(["L", "series", "roll / cost", "skew", "CAGR", "max DD", "10y median CAGR", "strike / spot (median)", "embedded put a year (median)",
                    "leverage p5 / median / p95", "untraded"],
                   [[f"{r['L']:g}", r["series"], r["roll"], r.get("skew", "-"), pc(r["cagr"], 2), pc(r["max_dd"]), pc(r["cagr10_median"], 2),
                     "-" if r.get("strike_over_spot") is None else f"{r['strike_over_spot']:.2f}",
                     "-" if r.get("put_cost_per_year") is None else pc(r["put_cost_per_year"], 2),
                     "-" if r.get("lev_p5") is None else f"{r['lev_p5']:.2f} / {r['lev_median']:.2f} / {r['lev_p95']:.2f}",
                     "UNTRADED" if r.get("untraded") else "-"] for r in res["rows"]]),
          "## LEAP minus fund (B19 cost), yearly paired log differences, pp a year [95%] and coverage verdict\n",
          md_table(["L", "roll", "cost per roll", "years", "mean", "95% interval", "verdict"],
                   [[f"{x['L']:g}", x["roll_freq"], f"{x['cost']:.1%}", f"{x['first_year']}-{x['last_year']} ({x['k']})", f"{x['mean'] * 100:+.2f}",
                     f"[{x['lo'] * 100:+.2f}, {x['hi'] * 100:+.2f}]", x["verdict"] + ("; covers zero" if x["covers_zero"] else "")]
                    for x in res["vs_fund"]]),
          "## Key periods and bottoms ($10,000; base skew, base roll cost, quarterly roll)\n"]
    keys = [k for k in res["episodes"][0] if isinstance(res["episodes"][0][k], dict)]
    md.append(md_table(["period", "bottom"] + [f"{k}: period / 3y from bottom" for k in keys],
                       [[e["period"], e["bottom"]] + [f"${e[k]['period']:,.0f} / ${e[k]['from_bottom']:,.0f}" for k in keys] for e in res["episodes"]]))
    return "\n".join(md)


def main():
    wall0 = time.perf_counter()
    print("=" * 100 + "\nB15: a rolling two-year call against the calendar fund (S&P 500; model option prices)")
    worlds, wprov = sub2x.build_worlds()
    w = worlds[NAME]
    costs = sub2x.cost_cases(sub2x.b19_anchor())
    df = inputs(w)
    theta_last = float(df["theta"].iloc[-1])
    inputs_m = study.inputs_for({NAME: w}, {NAME: wprov[NAME]}, extra_symbols=[VIX])
    banner = provenance.banner_lines(inputs_m) + study.conventions_lines(w) + [
        f"Option model: Black-Scholes-Merton with the trailing dividend yield; implied volatility from {VIX}; study end {sub2x.STUDY_END}."]
    print("\n".join(banner))
    rows, series_, vs_fund = [], {}, []
    idx = (df["u"] / df["u"].iloc[0])
    for L in LS:
        base_W = {}                                    # (roll, cost) -> LEAP wealth at the base skew, for the paired test
        for roll in ROLLS:
            for skew in SKEWS:
                for cost in ROLL_COSTS:
                    if skew != BASE_SKEW and cost != BASE_ROLL_COST:
                        continue
                    if roll != "quarterly" and skew != BASE_SKEW:
                        continue
                    W, lev, rl = leap_path(df, L, roll, skew, cost)
                    if skew == BASE_SKEW:
                        base_W[(roll, cost)] = W
                    st = stats_of(W, df)
                    ks = np.array([x["strike_over_spot"] for x in rl])
                    rows.append(dict(L=L, series="LEAP", roll=f"{roll} / {cost:.1%}", roll_freq=roll, cost=cost, skew=skew, **st,
                                     strike_over_spot=float(np.median(ks)), strike_over_spot_min=float(ks.min()),
                                     put_cost_per_year=float(np.median([x["put_cost_per_year"] for x in rl])),
                                     lev_p5=float(np.nanpercentile(lev, 5)), lev_median=float(np.nanmedian(lev)), lev_p95=float(np.nanpercentile(lev, 95)),
                                     n_rolls=len(rl), untraded=bool(np.median(ks) < STRIKE_TRADED)))
                    if skew == BASE_SKEW and cost == BASE_ROLL_COST and roll == "quarterly":
                        series_[f"LEAP {L:g}x"] = W
        for cname in sub2x.HEADLINE_COSTS:
            nav, spec = fund_path(w, df, L, cname, costs)
            first = W.dropna().index[0]
            early = [d for d in nav.attrs.get("early_resets", []) if pd.Timestamp(d) >= first]
            nav = nav.loc[first:] / nav.loc[first]
            st = stats_of(nav, df)
            # the fund's own leverage drift, read from the kernel's state with this run's costs (an early reset re-bases at
            # the trigger level, not at the close): bottoms.leverage_series
            enc = study.encoding_at(costs[cname], L, sub2x.BASE_BASIS)
            lev = B.leverage_series(w, spec, enc, rows=range(w.dates.get_loc(first), len(w.dates)))
            if cname == "b19":
                # LEAP minus fund, yearly paired log differences over the full NYSE years both cover (the project's
                # interval convention: t(k-1) x SE, with its simulated coverage; re-grade 2026-11-06, finding U2)
                yf = leverage.yearly_log_returns(nav)
                for (roll, cost), W in base_W.items():
                    yl = leverage.yearly_log_returns(W.dropna())
                    yrs = sorted(set(yl) & set(yf))
                    d = np.array([yl[y] - yf[y] for y in yrs])
                    iv = sub2x.interval_with_coverage(d, f"leap {L:g} {roll} {cost} vs fund")
                    vs_fund.append(dict(L=L, roll_freq=roll, cost=cost, skew=BASE_SKEW, fund_cost=cname, first_year=yrs[0],
                                        last_year=yrs[-1], k=iv["k"], mean=iv["mean"], se=iv["se"], lo=iv["lo"], hi=iv["hi"],
                                        verdict=iv["verdict"], covers_zero=bool(iv["lo"] <= 0.0 <= iv["hi"])))
            rows.append(dict(L=L, series=f"fund ({cname} cost)", roll=FUND_RESET, cost_case=cname, **st,
                             annual_cost=spec.fee + study.encoding_at(costs[cname], L, sub2x.BASE_BASIS).spread_per_nav,
                             early_resets=len(early), lev_p5=float(np.nanpercentile(lev, 5)), lev_median=float(np.nanmedian(lev)),
                             lev_p95=float(np.nanpercentile(lev, 95))))
            if cname == "b19":
                series_[f"fund {L:g}x"] = nav
        print(f"  L {L:g}: {time.perf_counter() - wall0:.0f} s")
    first = min(s_.dropna().index[0] for s_ in series_.values())
    series_["index"] = idx.loc[first:] / idx.loc[first]
    res = dict(meta=dict(title="B15: a rolling LEAP against the calendar fund", run_date=str(pd.Timestamp.today().date()), caption=CAPTION,
                         study_end=sub2x.STUDY_END, window=[str(df.index[0].date()), str(df.index[-1].date())], ls=list(LS), t_years=T_YEARS,
                         rolls=list(ROLLS), skews=SKEWS, base_skew=BASE_SKEW, roll_costs=list(ROLL_COSTS), base_roll_cost=BASE_ROLL_COST,
                         term_kappa=TERM_KAPPA, theta_rule="expanding mean of VIX^2 from 1990 to the day (causal)",
                         theta_last=theta_last, rate_rule="continuous 365 x ln(1 + r / 360) from ACT/360 fed funds", strike_traded=STRIKE_TRADED, fund_reset=FUND_RESET,
                         hold_years_after_bottom=HOLD_YEARS_AFTER_BOTTOM, inputs=inputs_m, banner=banner,
                         underlying=wprov[NAME], code=provenance.code_fingerprint(__file__)),
               index=stats_of(series_["index"], df), rows=rows, vs_fund=vs_fund, episodes=episodes(df, {k: v.dropna() for k, v in series_.items()}))
    res["meta"]["timing"] = dict(total_wall_seconds=time.perf_counter() - wall0)
    (OUT / "leap.json").write_text(json.dumps(provenance.json_safe(res), indent=1, allow_nan=False) + "\n", encoding="utf-8")
    (OUT / "leap.md").write_text(markdown(res), encoding="utf-8")
    print(f"wrote results/leap.json and results/leap.md in {time.perf_counter() - wall0:.0f} s")


if __name__ == "__main__":
    main()
