"""Draw candles with the Clean Guppy ribbons from the Python port, for any symbol in your data folder.

    py scripts\\plot_guppy.py AMEX:SPY --weekly --years 10
    py scripts\\plot_guppy.py NASDAQ:QQQ --daily --years 3 --out results/guppy_QQQ_daily.png

What you get: candles (green up, red down) on a black background; the fast ribbon (EMAs 3-21) cyan when both groups
stack up and orange when both stack down; the slow ribbon (EMAs 24-66) green when stacked up, red when stacked down,
gray otherwise; the 200 EMA in blue; and triangles where the FIXED rule in strategies/guppy.py buys (green, below the
bar) or sells (red, above the bar). Weekly bars are built from the daily file the way TradingView builds them: open of
the first session, high/low over the week, close of the last session. The EMAs are computed on the whole history the
file holds, so the ribbon is fully warmed up before the window you look at.
Data: your own TradingView export (never shipped with this repository). Illustration only; not investment advice.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from calendar_letf import indicators as ind  # noqa: E402
from calendar_letf import loader  # noqa: E402
from calendar_letf.strategies.guppy import hold_through_gray  # noqa: E402

CYAN, ORANGE, GRAY, GREEN, RED, BLUE = "#00FFFF", "#FFA500", "#808080", "#00FF00", "#FF0000", "#4d9fe6"
UP, DOWN = "#26a69a", "#ef5350"


def weekly_bars(daily):
    """Weekly OHLC from daily OHLC: one bar per calendar week, dated by its last trading day."""
    ends = ind.week_end_rows(daily.index)
    starts = np.r_[0, ends[:-1] + 1]
    return pd.DataFrame({
        "open": daily["open"].to_numpy()[starts],
        "high": [daily["high"].iloc[s:e + 1].max() for s, e in zip(starts, ends)],
        "low": [daily["low"].iloc[s:e + 1].min() for s, e in zip(starts, ends)],
        "close": daily["close"].to_numpy()[ends],
    }, index=daily.index[ends])


def plot(symbol, weekly=True, years=10, out=None, data_dir=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    daily = loader.load_prices(symbol, data_dir)
    if daily[["open", "high", "low"]].isna().any().any():
        raise ValueError(f"{symbol}: candles need open/high/low; this file has blanks (index files are often close-only)")
    bars = weekly_bars(daily) if weekly else daily[["open", "high", "low", "close"]]
    g = ind.guppy(bars["close"].to_numpy())                 # full history, so the window is warmed up
    expo = hold_through_gray(g["slow_state"])               # the fixed rule, on these bars
    m = bars.index >= bars.index[-1] - pd.DateOffset(years=years)
    w, x = bars[m], np.arange(int(m.sum()))
    fast_col = np.where((g["fast_state"][m] == 1) & (g["slow_state"][m] == 1), CYAN,
                        np.where((g["fast_state"][m] == -1) & (g["slow_state"][m] == -1), ORANGE, GRAY))
    slow_col = np.where(g["slow_state"][m] == 1, GREEN, np.where(g["slow_state"][m] == -1, RED, GRAY))

    fig, ax = plt.subplots(figsize=(16, 8), facecolor="black")
    ax.set_facecolor("black")

    def ribbon(emas, cols, lw):
        for e in emas:                                        # each segment takes the color of the bar it ends on
            y = e[m]
            for i in range(len(x) - 1):
                ax.plot(x[i:i + 2], y[i:i + 2], color=cols[i + 1], lw=lw, alpha=0.9, solid_capstyle="round")

    ribbon(g["fast_emas"], fast_col, 0.8)
    ribbon(g["slow_emas"], slow_col, 0.8)
    ax.plot(x, g["long_ema"][m], color=BLUE, lw=1.8, label=f"EMA 200 ({'weeks' if weekly else 'days'})")
    up = w["close"].to_numpy() >= w["open"].to_numpy()
    for i in range(len(x)):
        c = UP if up[i] else DOWN
        ax.plot([x[i], x[i]], [w["low"].iloc[i], w["high"].iloc[i]], color=c, lw=0.8)
        body = abs(w["close"].iloc[i] - w["open"].iloc[i]) or 0.01
        ax.add_patch(plt.Rectangle((x[i] - 0.35, min(w["open"].iloc[i], w["close"].iloc[i])), 0.7, body, color=c))
    e = expo[m]
    for i in np.flatnonzero(np.diff(e) != 0) + 1:
        buy = e[i] == 1.0
        ax.scatter(x[i], w["low"].iloc[i] * 0.97 if buy else w["high"].iloc[i] * 1.03, marker="^" if buy else "v",
                   s=90, color=GREEN if buy else RED, zorder=5)
    yrs = w.index.year.to_numpy()
    ticks = np.flatnonzero(yrs[1:] != yrs[:-1]) + 1
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(y) for y in yrs[ticks]], color="white")
    ax.tick_params(colors="white")
    for s in ax.spines.values():
        s.set_color("#444444")
    ax.set_xlim(-1, len(x))
    ax.set_ylim(w["low"].min() * 0.95, w["high"].max() * 1.05)
    ax.set_title(f"{symbol} {'weekly' if weekly else 'daily'}, {w.index[0].date()} to {w.index[-1].date()}: Clean Guppy ribbons "
                 "(Python port). Triangles = the fixed rule's buys / sells on the slow ribbon.\n"
                 "Data: TradingView (your own export). Illustration only; not investment advice.", color="white", fontsize=11)
    ax.legend(loc="upper left", facecolor="black", labelcolor="white", edgecolor="#444444")
    ax.grid(color="#222222", lw=0.5)
    out = Path(out) if out else ROOT / "results" / f"guppy_{symbol.split(':')[-1]}_{'weekly' if weekly else 'daily'}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110, bbox_inches="tight", facecolor="black")
    plt.close(fig)
    s = g["slow_state"][m]
    print(f"wrote {out}: {len(x)} bars; slow ribbon green {int((s == 1).sum())} / gray {int((s == 0).sum())} / red "
          f"{int((s == -1).sum())}; rule events in window {int((np.diff(e) != 0).sum())}")
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="Candles with the Clean Guppy ribbons (Python port)")
    p.add_argument("symbol", help="EXCHANGE:TICKER as the data file is named, e.g. AMEX:SPY")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--weekly", action="store_true", default=True, help="weekly bars (default)")
    g.add_argument("--daily", action="store_true", help="daily bars")
    p.add_argument("--years", type=float, default=10, help="how many years to show (default 10)")
    p.add_argument("--out", default=None, help="png path (default results/guppy_<TICKER>_<weekly|daily>.png)")
    a = p.parse_args(argv)
    plot(a.symbol, weekly=not a.daily, years=a.years, out=a.out)


if __name__ == "__main__":
    main()
