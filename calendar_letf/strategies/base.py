"""The strategy plugin contract (DESIGN.md section 7).

Plain-English summary
  * A "strategy" (plugin) looks at price history and says how much of the fund to hold on each day: a number
    between 0 (all cash) and 1 (all fund). That number is the "exposure".
  * A plugin NEVER touches wealth, costs or timing. It only returns the exposure array. The backtest
    (`backtest.py`) decides when a signal is acted on (the "delay") and charges the trading costs.
  * Exposure on row t may use data up to and including row t (the close). It must NOT look at row t+1 or later.
    `check_no_lookahead` below proves that: it computes the exposure on the full history and on the history cut
    short, and the early values must agree.
  * Adding a plugin: drop a new file into this folder, decorate the class with `@register("my_name")`, and give
    it `exposure(ctx)`. `discover()` imports every file in the folder, so nothing else needs editing; the study
    script and the look-ahead test pick the new plugin up by themselves.

The context given to a plugin (`SignalContext`)
    dates        trading days (pandas DatetimeIndex)
    close        the underlying PRICE index close, float64. Signals use this (long history), never the fund's own NAV,
                 except a rule that is about the fund's own drawdown (drawdown_stop)
    close_tr     the underlying total-return level, or None
    product_nav  the passive NAV of the product being traded (for rules about the fund itself)
    week_last    bool array: True on the last trading day of each calendar week. Calendar information (the exchange
                 calendar is known in advance), so a cut of the history keeps the flags of the full history.
"""
import importlib
import pkgutil
from dataclasses import dataclass

import numpy as np
import pandas as pd

registry = {}                        # key -> Strategy subclass, filled by @register at import time


@dataclass
class SignalContext:
    dates: pd.DatetimeIndex
    close: np.ndarray
    close_tr: np.ndarray | None
    product_nav: np.ndarray
    week_last: np.ndarray

    def __post_init__(self):
        n = len(self.dates)
        self.close = np.asarray(self.close, dtype=np.float64)
        self.product_nav = np.asarray(self.product_nav, dtype=np.float64)
        self.week_last = np.asarray(self.week_last, dtype=bool)
        if self.close_tr is not None:
            self.close_tr = np.asarray(self.close_tr, dtype=np.float64)
        for name in ("close", "product_nav", "week_last") + (("close_tr",) if self.close_tr is not None else ()):
            if len(getattr(self, name)) != n:
                raise ValueError(f"SignalContext: {name} has {len(getattr(self, name))} rows, dates has {n}")

    def __len__(self):
        return len(self.dates)

    def cut(self, rows):
        """The same context with only the first `rows` rows (what a trader would have seen on that day)."""
        return SignalContext(self.dates[:rows], self.close[:rows], None if self.close_tr is None else self.close_tr[:rows],
                             self.product_nav[:rows], self.week_last[:rows])

    def tail_from(self, row):
        """The context from `row` on (an investor who starts at `row`)."""
        return SignalContext(self.dates[row:], self.close[row:], None if self.close_tr is None else self.close_tr[row:],
                             self.product_nav[row:], self.week_last[row:])


class Strategy:
    """Base class. A subclass sets DEFAULTS (every tunable, with its default) and implements exposure(ctx).

    key              the registry name, set by @register
    DEFAULTS         dict of parameters; passing an unknown parameter raises, so a typo cannot silently do nothing
    VARIANTS         the parameter sets the study (and the look-ahead test) run, e.g. ({"kind": "sma"}, {"kind": "ema"})
    path_dependent   True if the exposure depends on WHERE the investor starts (a drawdown stop measures from its own
                     entry). Multi-start results for such a rule must come from one run per start, not from ratios of
                     one wealth path
    params           the parameters in force (DEFAULTS + overrides), so reports can list what was tried
    warmup           nominal number of leading rows with no signal (NaN); the engine uses the real first valid row
    """
    key = ""
    DEFAULTS = {}
    VARIANTS = ({},)
    path_dependent = False

    def __init__(self, **params):
        unknown = set(params) - set(self.DEFAULTS)
        if unknown:
            raise ValueError(f"{self.key}: unknown parameter(s) {sorted(unknown)}; known: {sorted(self.DEFAULTS)}")
        self.params = {**self.DEFAULTS, **params}

    @property
    def name(self):
        """Unique name of this variant (used in tables); subclasses add a suffix for the parameters that matter."""
        return self.key

    @property
    def warmup(self):
        return 0

    def exposure(self, ctx):
        raise NotImplementedError(f"{type(self).__name__}.exposure is not implemented")

    def __repr__(self):
        return f"{self.name}({', '.join(f'{k}={v}' for k, v in self.params.items())})"


def register(key):
    """Class decorator: `@register("trend_50d")` puts the class in the registry under that key."""
    def deco(cls):
        if key in registry:
            raise ValueError(f"strategy {key!r} is already registered ({registry[key].__name__})")
        cls.key = key
        registry[key] = cls
        return cls
    return deco


def discover():
    """Import every module in the strategies package, so every plugin file registers itself. Returns the registry."""
    pkg_path = importlib.import_module(__package__).__path__          # the folder this package lives in
    for mod in pkgutil.iter_modules(pkg_path):
        if mod.name != "base":
            importlib.import_module(f"{__package__}.{mod.name}")
    return registry


def make(name, **params):
    """A plugin instance by registry key: make("trend_200d", kind="ema")."""
    if name not in registry:
        raise KeyError(f"unknown strategy {name!r}; registered: {sorted(registry)}")
    return registry[name](**params)


def all_variants():
    """Every (key, params, instance) the study runs: one per entry in each registered plugin's VARIANTS."""
    return [(key, dict(p), registry[key](**p)) for key in registry for p in registry[key].VARIANTS]


def week_end_closes(ctx):
    """(rows, closes): the row numbers of the week-end rows and the underlying close on them (the weekly bars)."""
    rows = np.flatnonzero(ctx.week_last)
    return rows, ctx.close[rows]


def carry_forward(weekly_values, rows, n):
    """Spread a weekly signal over the daily rows: row t gets the value of the latest week-end row at or before t
    (NaN before the first week-end). The signal therefore changes only on week-end rows."""
    out = np.full(n, np.nan)
    if len(rows) == 0:
        return out
    k = np.searchsorted(rows, np.arange(n), side="right") - 1          # index of the latest week-end row <= t
    ok = k >= 0
    out[ok] = np.asarray(weekly_values, dtype=np.float64)[k[ok]]
    return out


def check_exposure(expo, n, name="strategy"):
    """Validate a plugin's output: float64, one value per row, NaN only at the start, then values in [0, 1]."""
    expo = np.asarray(expo, dtype=np.float64)
    if expo.shape != (n,):
        raise ValueError(f"{name}: exposure has shape {expo.shape}, expected ({n},)")
    fin = np.isfinite(expo)
    if fin.any():
        first = int(np.argmax(fin))
        if not fin[first:].all():
            raise ValueError(f"{name}: exposure is NaN after its first valid row ({first})")
        if (expo[first:] < 0.0).any() or (expo[first:] > 1.0).any():
            raise ValueError(f"{name}: exposure must stay in [0, 1]")
    return expo


def check_no_lookahead(strategy, ctx, cuts=(300, 1000, 2500)):
    """The generic look-ahead test. Compute the exposure on the full history, then on the history cut to its first t
    rows; the first t values must be identical (NaN equals NaN). Returns a list of (t, first_row_that_differs); an
    empty list means no look-ahead was detected. A plugin that peeks at row t+1 or later fails here.
    A cut at or beyond the history length is skipped."""
    full = check_exposure(strategy.exposure(ctx), len(ctx), strategy.name)
    bad = []
    for t in cuts:
        if t >= len(ctx):
            continue
        part = check_exposure(strategy.exposure(ctx.cut(t)), t, strategy.name)
        if not np.array_equal(full[:t], part, equal_nan=True):
            same = (full[:t] == part) | (np.isnan(full[:t]) & np.isnan(part))
            bad.append((t, int(np.argmin(same))))
    return bad
