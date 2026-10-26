"""NAV kernels for calendar-reset and daily-reset leveraged funds and the buy-once margin position (DESIGN.md
sections 4.1 and 4.2; R2 step 1 fixes E1-E5).

Two kinds of function live here:
- kernels (`periodic_reset_nav`, `daily_reset_nav`, `margin_position_nav`): plain loops over float64 numpy
  arrays, compiled to machine code by numba. `@njit` = "compile this function, no Python objects inside";
  `cache=True` = keep the compiled code on disk (in __pycache__) so the next run skips the few seconds of compiling.
- wrappers (`periodic_reset_series`, `daily_reset_series`, `run`): ordinary Python that checks the inputs, turns
  pandas Series into arrays, calls a kernel and turns the result back into a labeled Series.

Notation (the same in every kernel)
    u[t]            underlying level at close t (an index or a total-return index)
    trig[t]         calendar kernel only: the CLOSE of the level the -35% early trigger watches (the price index,
                    or u itself)
    trig_low[t]     calendar kernel only: the day's LOW of that level (pass trig itself when there is no intraday
                    information; the kernel uses min(trig_low[t], trig[t]))
    rate[t]         annual reference rate KNOWN BEFORE day t (the caller lags it; row 0 is never used)
    accrual_fin[t]  calendar days since the previous row / 360 (ACT/360, the financing legs; 0 on row 0)
    accrual_fee[t]  calendar days since the previous row / 365 (the expense ratio; 0 on row 0)
    L               leverage (2.0 for a 2x fund)
    spread_per_nav  annual swap spread as a fraction of NAV = spread per turn x turns (costs.spread_per_nav)
    fee[t]          annual expense ratio in force over the step from row t-1 to row t (a per-row array, so a fee
                    timeline can be modeled; a constant array for a single fee)
Each day the fund pays financing ((L - 1) x rate + spread_per_nav) x accrual_fin and its fee x accrual_fee.

NAV starts at 1.0 on row 0, and row 0 counts as a reset (the calendar fund's base is fixed at u[0]). So a calendar
run must either start on a reset date (the last trading day of a period), or be read as ratios nav[e] / nav[s] of
one run over the full history (DESIGN.md section 8). A series sliced to start mid-period resets on its first row,
which the real fund does not do. A NAV at or below zero means the fund is finished: it is set to 0 and stays there.

Arithmetic in the calendar and daily kernels is written in the same order as the author's earlier, tested
implementations (checked by a local cross-check that is not part of the repo), so that comparison matches on every
row. Do not "simplify" the formulas: (a + b) + c and a + (b + c) can differ in the last digit, and that would break
the bit-for-bit match. The R2 changes keep that order: the single accrual became accrual_fin (financing) and
accrual_fee (fee), and the scalar fee became fee[t]; with fin_day_count=365 and a constant fee the two accrual
arrays and the fee array hold exactly the old numbers, so the cross-check still matches at 0.00e+00. The trigger
test now reads min(trig_low[t], trig[t]), which is trig[t] itself when no low is given.
"""
import numpy as np
import pandas as pd
from numba import njit

from . import periods as cal      # period ids and accrual (named periods.py so it never shadows Python's own calendar module)

PERIODIC_RESETS = cal.ALL_RESETS      # ("weekly", "monthly", "quarterly", "never"): "never" = a buy-once position
                                      # that is never reset (the margin benchmark, study.py); row 0 is its purchase

# How the early (-35%) reset is carried out. The wrappers take the name; the kernel takes the number.
#   level       the fund resets intraday at exactly the trigger level (prospectus base case: "as soon as possible"
#               after the trigger level is reached)
#   close       the fund resets at the close of the day the trigger is breached
#   next_close  the fund resets at the next day's close (the prospectus's "final 30 minutes" clause)
EARLY_LEVEL, EARLY_CLOSE, EARLY_NEXT_CLOSE = 0, 1, 2
EARLY_MODES = {"level": EARLY_LEVEL, "close": EARLY_CLOSE, "next_close": EARLY_NEXT_CLOSE}

FIN_DAY_COUNT = 360                   # ACT/360 on the financing legs (rate and spread): money-market convention
FEE_DAY_COUNT = 365                   # the expense ratio accrues on a 365-day year


# ----------------------------------------------------------------------------------------------------------------
# Kernels
# ----------------------------------------------------------------------------------------------------------------
@njit(cache=True)
def financing_rate(L, rate_t, spread_per_nav):
    """Annual financing cost as a fraction of the notional it applies to: (L-1) x rate + spread_per_nav.

    Shared by the calendar and daily kernels so the only difference between them is WHICH notional it is charged on.
    """
    return (L - 1.0) * rate_t + spread_per_nav


@njit(cache=True)
def periodic_reset_nav(u, trig, trig_low, rate, accrual_fin, accrual_fee, period_end, L, spread_per_nav, fee,
                       early_drop, early_mode):
    """NAV of a fund that resets exposure to L x NAV at each period end, or early after a big in-period fall.

    u         the level the NAV is marked on (a price or total-return index)
    trig      the CLOSE of the level the early trigger watches. The prospectus trigger is on the PRICE of SPY /
              QQQ, so a total-return run passes the price index here. Pass u itself to trigger on the underlying.
    trig_low  the day's LOW of that same level. The breach test uses lo[t] = min(trig_low[t], trig[t]); pass trig
              itself for a close-only trigger (then lo = trig and nothing changes).

    Between resets the fund is a fixed levered position: with NAV0, U0 and T0 (nav0, u0, trig0 in the code) fixed
    at the last reset,
        carry  += financing_rate x accrual_fin[t]        financing on the amounts fixed at the reset (simple
                                                         interest inside the period: the swap's financing leg
                                                         accrues on the reset notional and settles at the reset)
        fees   += fee[t] x nav[t-1] x accrual_fee[t]     expense ratio on yesterday's NAV
        nav[t]  = NAV0 x (L x u[t]/U0 - (L-1)) - NAV0 x carry - fees
    Ordinary reset (NAV0 = nav[t], U0 = u[t], T0 = trig[t], carry = fees = 0) at the close when period_end[t] is
    True (the last NYSE session of the week / month / quarter; periods.period_end_flags).

    Early reset: the trigger is breached on day t when lo[t]/T0 - 1 <= -early_drop (e.g. -35%), lo[t] the day's low
    (or the close when there is no low). early_drop <= 0 turns it off. With a close-only trigger, a fall that
    touches -35% during the day and recovers by the close is missed; with the low it is caught. early_mode says
    what the fund does once the trigger is breached (the fill rules do not depend on whether the low is given):
      EARLY_LEVEL (0): it resets intraday at exactly the trigger level (the prospectus base case). The day's carry
          and fee are charged first; then, at the trigger moment,
              T_hit = T0 x (1 - early_drop)                       the trigger level
              U_hit = T_hit x (u_ref / trig_ref)                  the underlying at that moment (see below)
              NAV_hit = NAV0 x (L x U_hit/U0 - (L-1)) - NAV0 x carry - fees
          the base becomes NAV0 = NAV_hit, U0 = U_hit, T0 = T_hit, carry = fees = 0, and the rest of the day is
          marked on the new base. (u_ref, trig_ref) is the last point where both levels are known: yesterday's
          close, or the previous trigger moment on the same day. So the underlying is assumed to move in step
          with the trigger series since yesterday's close; for a total-return run on a price trigger that ignores
          only the day's own dividend, which is negligible. When trig is u, U_hit = U0 x (1 - early_drop) exactly.
          If the day's low is beyond the NEXT trigger level as well (a fall of 1 - 0.65^2 = 57.75% at 35%), the
          fund resets again at that level, as many times as needed: the stub after an early reset is a new period,
          so the trigger re-arms. The re-arm loop tests the LOW; the day is then marked at its CLOSE on the last
          base, so a close back above some of the levels rides the rebound on the new base. If NAV_hit <= 0 the
          fund is finished.
          This is the optimistic end: a gap through the level (a fall overnight, or a market too fast to trade)
          is still filled exactly at the level. Two consequences worth knowing: with the trigger on, a 2x fund
          can never be wiped out by one day's fall in this mode (each reset leaves 0.30 x the old base and the
          next level is 35% further down; "close" mode terminates at -50%); and the triggering day's whole carry
          and fee are charged on the OLD base before the reset, nothing after (slightly conservative, tiny).
      EARLY_CLOSE (1): it resets at the close of the triggering day.
      EARLY_NEXT_CLOSE (2): it resets at the NEXT trading day's close (the "final 30 minutes" clause: not enough
          time to rebalance that day). If that next day is a period end, it is an ordinary period reset.
          A trigger on the final row stays pending (the data ends before the reset).
    In EARLY_CLOSE and EARLY_NEXT_CLOSE, a trigger on a period-end close is just the period reset (nothing is
    pending, nothing is flagged). In EARLY_LEVEL, a trigger on a period-end day is two resets: the early one at
    the level (flagged) and the period one at the close (not flagged).
    Termination is tested on the close (and at each trigger level in EARLY_LEVEL); an intraday low that would take
    a close-mode fund through zero and recover by the close is not treated as a wipe-out.

    Returns
        nav               float64 array, nav[0] = 1.0
        early_reset_flag  int8 array, 1 on rows where an EARLY reset happened (not on ordinary period ends)
        terminated_index  int64 row where NAV first hit 0, or -1 if it never did
    """
    n = u.shape[0]
    if trig.shape[0] != n:
        raise ValueError("trig must have one value per row of u")
    if trig_low.shape[0] != n:
        raise ValueError("trig_low must have one value per row of u")
    if accrual_fin.shape[0] != n or accrual_fee.shape[0] != n or rate.shape[0] != n:
        raise ValueError("rate, accrual_fin and accrual_fee must have one value per row of u")
    if fee.shape[0] != n:
        raise ValueError("fee must have one value per row of u (a per-row array)")
    if early_mode != EARLY_LEVEL and early_mode != EARLY_CLOSE and early_mode != EARLY_NEXT_CLOSE:
        raise ValueError("early_mode must be 0 (level), 1 (close) or 2 (next_close)")
    nav = np.zeros(n)                          # rows after a wipeout simply stay 0
    early_reset_flag = np.zeros(n, dtype=np.int8)
    terminated_index = -1
    if n == 0:
        return nav, early_reset_flag, terminated_index
    nav[0] = 1.0
    nav0 = 1.0                                 # NAV at the last reset
    u0 = u[0]                                  # underlying level at the last reset
    trig0 = trig[0]                            # trigger level at the last reset
    carry = 0.0                                # financing accrued since the last reset, per unit of NAV0
    fees = 0.0                                 # fees accrued since the last reset, in NAV units
    pending = False                            # next_close mode: a trigger fired yesterday, reset at today's close
    for t in range(1, n):
        carry += financing_rate(L, rate[t], spread_per_nav) * accrual_fin[t]
        fees += fee[t] * nav[t - 1] * accrual_fee[t]
        lo = trig_low[t] if trig_low[t] < trig[t] else trig[t]      # the day's lowest trigger level

        # Level mode: reset intraday at the trigger level (again if the day's low passed the next level too).
        if early_mode == EARLY_LEVEL and early_drop > 0.0:
            u_ref = u[t - 1]                                 # last point where both levels are known
            trig_ref = trig[t - 1]
            dead = False
            while lo / trig0 - 1.0 <= -early_drop:
                trig_hit = trig0 * (1.0 - early_drop)        # the trigger level
                u_hit = trig_hit * (u_ref / trig_ref)        # the underlying at that moment
                v_hit = nav0 * (L * u_hit / u0 - (L - 1.0)) - nav0 * carry - fees
                if v_hit <= 0.0:
                    dead = True                              # finished before it could reset
                    break
                nav0 = v_hit                                 # the new base, fixed at the trigger moment
                u0 = u_hit
                trig0 = trig_hit
                carry = 0.0
                fees = 0.0
                u_ref = u_hit
                trig_ref = trig_hit
                early_reset_flag[t] = 1
            if dead:
                terminated_index = t                         # nav[t:] are already 0
                break

        gross = nav0 * (L * u[t] / u0 - (L - 1.0))        # the levered position marked to today's close
        v = gross - nav0 * carry - fees
        if v <= 0.0:
            terminated_index = t                         # the fund is finished; nav[t:] are already 0
            break
        nav[t] = v
        reset_now = False
        if period_end[t]:
            reset_now = True                             # ordinary reset at the period's last close
        elif pending:
            reset_now = True                             # delayed early reset (next_close mode)
            early_reset_flag[t] = 1
        elif early_mode != EARLY_LEVEL and early_drop > 0.0 and lo / trig0 - 1.0 <= -early_drop:
            if early_mode == EARLY_CLOSE:
                reset_now = True                         # early reset at the triggering close
                early_reset_flag[t] = 1
            else:
                pending = True                           # reset at tomorrow's close; tonight nothing changes
                continue
        if reset_now:
            nav0 = v
            u0 = u[t]
            trig0 = trig[t]
            carry = 0.0
            fees = 0.0
            pending = False
    return nav, early_reset_flag, terminated_index


@njit(cache=True)
def daily_reset_nav(u, rate, accrual_fin, accrual_fee, L, spread_per_nav, fee):
    """NAV of a fund that resets exposure to L x NAV at every close (the daily twin).

        d[t]   = L x (u[t]/u[t-1] - 1) - financing_rate x accrual_fin[t] - fee[t] x accrual_fee[t]
        nav[t] = nav[t-1] x (1 + d[t]), and 0 for good once it reaches 0
    Same cost expression as the calendar kernel, but charged on today's NAV (the position is re-set daily),
    not on the amounts fixed at the last reset.

    Returns nav (float64, nav[0] = 1.0) and terminated_index (int64, -1 if never).
    """
    n = u.shape[0]
    if accrual_fin.shape[0] != n or accrual_fee.shape[0] != n or rate.shape[0] != n or fee.shape[0] != n:
        raise ValueError("rate, accrual_fin, accrual_fee and fee must have one value per row of u")
    nav = np.zeros(n)
    terminated_index = -1
    if n == 0:
        return nav, terminated_index
    nav[0] = 1.0
    for t in range(1, n):
        d = (L * (u[t] / u[t - 1] - 1.0)
             - financing_rate(L, rate[t], spread_per_nav) * accrual_fin[t]
             - fee[t] * accrual_fee[t])
        v = nav[t - 1] * (1.0 + d)
        if v <= 0.0:
            terminated_index = t
            break
        nav[t] = v
    return nav, terminated_index


@njit(cache=True)
def margin_position_nav(u, rate, accrual_fin, accrual_fee, L, spread_per_nav, fee):
    """Equity of a buy-once L x position on margin, never reset (the margin benchmark; R1 memo E1).

    Bought at the close of row 0 with equity NAV0 = 1: exposure L x NAV0, loan (L-1) x NAV0. The loan is a
    balance that capitalizes daily (a margin loan charges interest on interest; Wang (2025) eq. 2 compounds the
    non-reset portfolio's financing as (n-1)[prod(1 + rf_t) - 1]):
        loan[0]   = (L - 1) x NAV0
        loan[t]   = loan[t-1] + loan[t-1] x rate[t] x accrual_fin[t]           interest on the whole balance
                              + NAV0 x spread_per_nav x accrual_fin[t]          the spread, paid by borrowing
                              + fee[t] x equity[t-1] x accrual_fee[t]           the fee, paid by borrowing
        equity[t] = L x NAV0 x u[t]/u[0] - loan[t]
    The spread and fee are added to the loan, so they bear interest from the next day on. The position is
    finished when equity <= 0 (set to 0, stays 0). With zero costs equity = 1 + L x (u[t]/u[0] - 1) exactly.
    The calendar kernel with no period end charges the same costs as SIMPLE interest on NAV0 instead; the gap
    is the interest on interest: about (rate x years)^2 / 2 of the loan, 8e-5 of NAV over one quarter at 5%,
    0.15 of NAV over ten years.

    Returns nav (float64, nav[0] = 1.0) and terminated_index (int64, -1 if never).
    """
    n = u.shape[0]
    if accrual_fin.shape[0] != n or accrual_fee.shape[0] != n or rate.shape[0] != n or fee.shape[0] != n:
        raise ValueError("rate, accrual_fin, accrual_fee and fee must have one value per row of u")
    nav = np.zeros(n)
    terminated_index = -1
    if n == 0:
        return nav, terminated_index
    nav[0] = 1.0
    nav0 = 1.0
    loan = (L - 1.0) * nav0
    for t in range(1, n):
        loan += (loan * rate[t] * accrual_fin[t] + nav0 * spread_per_nav * accrual_fin[t]
                 + fee[t] * nav[t - 1] * accrual_fee[t])
        v = L * nav0 * u[t] / u[0] - loan
        if v <= 0.0:
            terminated_index = t
            break
        nav[t] = v
    return nav, terminated_index


# ----------------------------------------------------------------------------------------------------------------
# pandas wrappers: check inputs, call a kernel, label the output
# ----------------------------------------------------------------------------------------------------------------
def _check_number(name, x, lo=None, hi=None):
    """Return float(x) after checking it is a finite number inside [lo, hi] (when given)."""
    if x is None or isinstance(x, bool):
        raise ValueError(f"{name} must be a number (no defaults for costs: pass it explicitly)")
    x = float(x)
    if not np.isfinite(x):
        raise ValueError(f"{name} must be finite, got {x}")
    if lo is not None and x < lo:
        raise ValueError(f"{name} = {x} is below the minimum {lo}")
    if hi is not None and x > hi:
        raise ValueError(f"{name} = {x} is above the maximum {hi}")
    return x


def _check_day_count(name, x):
    if isinstance(x, bool) or x not in cal.DAY_COUNTS:
        raise ValueError(f"{name} must be one of {cal.DAY_COUNTS} (ACT/360 or ACT/365), got {x!r}")
    return int(x)


def _prepare(u, rate, L, allow_gaps, max_gap_days, fin_day_count, fee_day_count):
    """Check the inputs shared by the wrappers; return (dates, u array, rate array, accrual_fin, accrual_fee, L)."""
    if not isinstance(u, pd.Series) or not isinstance(u.index, pd.DatetimeIndex):
        raise ValueError("u must be a pandas Series with a DatetimeIndex (underlying level per trading day)")
    if len(u) < 2:
        raise ValueError("u needs at least two rows")
    if not (u.index.is_monotonic_increasing and u.index.is_unique):
        raise ValueError("u's dates must be strictly increasing with no repeats (sort it first)")
    # copy=True gives a fresh, writable array (pandas may hand out read-only views, which numba would compile
    # a second version of the kernel for).
    u_arr = u.to_numpy(dtype=np.float64, copy=True)
    if not np.isfinite(u_arr).all() or (u_arr <= 0).any():
        raise ValueError("underlying levels must be finite and positive")
    L = _check_number("L", L, lo=1.0)                  # this model is for long funds with leverage >= 1
    fin_dc = _check_day_count("fin_day_count", fin_day_count)
    fee_dc = _check_day_count("fee_day_count", fee_day_count)

    gaps = cal.gap_days(u.index)
    if not allow_gaps and (gaps > max_gap_days).any():
        first = u.index[int(np.argmax(gaps > max_gap_days))]
        raise ValueError(f"gap of {int(gaps.max())} days (first at {first.date()}): reset math needs daily data, "
                         "and a missing row could hide a period end; pass allow_gaps=True only if the gaps are "
                         "market closures")

    # The rate: one value per row of u, already lagged by the caller (known before each day).
    if isinstance(rate, pd.Series):
        if not rate.index.equals(u.index):
            raise ValueError("rate must have exactly the same index as u (align and lag it before calling)")
        r_arr = rate.to_numpy(dtype=np.float64, copy=True)                    # a copy we may edit
    else:
        r_arr = np.full(len(u_arr), _check_number("rate", rate), dtype=np.float64)
    # Row 0 accrues nothing (accrual 0), so its rate is never used; a one-row lag leaves NaN there. Use 0 so
    # no NaN ever reaches the kernel.
    if not np.isfinite(r_arr[0]):
        r_arr[0] = 0.0
    if not np.isfinite(r_arr).all():
        bad = u.index[int(np.argmax(~np.isfinite(r_arr)))]
        raise ValueError(f"rate is missing or not finite on {bad.date()} (only the first row may be missing)")
    if (np.abs(r_arr) > 0.5).any():
        raise ValueError("rate above 50% a year: it looks like a percentage; pass decimals (0.05 = 5%)")

    accrual_fin = cal.accrual_fraction(u.index, fin_dc)
    accrual_fee = cal.accrual_fraction(u.index, fee_dc)
    return u.index, u_arr, r_arr, accrual_fin, accrual_fee, L


def _fee_array(fee, u):
    """The fee as a per-row float64 array and its label for attrs: a float is broadcast; a Series (a step series on
    u's exact index) is used row by row, value on row t = the annual fee over the step from row t-1 to row t."""
    if isinstance(fee, pd.Series):
        if not fee.index.equals(u.index):
            raise ValueError("a fee Series must have exactly the same index as u (a step series of annual fees)")
        f_arr = fee.to_numpy(dtype=np.float64, copy=True)
        if not np.isfinite(f_arr[1:]).all():
            raise ValueError("fee Series has missing or non-finite values (only the first row may be missing)")
        if not np.isfinite(f_arr[0]):
            f_arr[0] = 0.0                                 # row 0 accrues nothing
        if (f_arr < 0.0).any() or (f_arr > 0.5).any():
            raise ValueError("fee Series values must be annual decimals between 0 and 0.5 (0.01 = 1%)")
        change = np.flatnonzero(np.r_[True, f_arr[2:] != f_arr[1:-1]]) + 1 if len(f_arr) > 1 else np.array([], int)
        steps = [[str(u.index[i].date()), float(f_arr[i])] for i in change]
        return f_arr, "timeline", steps
    f = _check_number("fee", fee, 0.0, 0.5)
    return np.full(len(u), f, dtype=np.float64), f, None


def _iso(dates, rows):
    return [str(dates[i].date()) for i in rows]


def _trigger_levels(trigger, u, u_arr):
    """The trigger as a float64 array (u itself when trigger is None) and its label for attrs["model"]."""
    if trigger is None:
        return u_arr, "underlying"
    if not isinstance(trigger, pd.Series):
        raise ValueError("trigger must be a pandas Series with u's exact index (or None to trigger on u itself)")
    if not trigger.index.equals(u.index):
        raise ValueError("trigger must have exactly the same index as u (align it before calling)")
    t_arr = trigger.to_numpy(dtype=np.float64, copy=True)
    if not np.isfinite(t_arr).all() or (t_arr <= 0).any():
        raise ValueError("trigger levels must be finite and positive")
    return t_arr, (str(trigger.name) if trigger.name is not None else "unnamed trigger series")


def _trigger_lows(trigger_low, trig_arr, u):
    """The array the breach test reads, and a dict for attrs["trigger_low"] (None when no low is given).

    A row carries intraday information only when its low is BELOW its close. Rows where the low equals the close
    (the SPX export's placeholder bars before 1962, the NDX export's before 1985-10), or is missing, are treated as
    "no intraday information": the breach test reads the close there, exactly as a close-only run does. A real
    bar can also close at its low; reading the close there is the same number, so nothing is lost.
    A low ABOVE the close is impossible data and raises.
    """
    if trigger_low is None:
        return trig_arr, None
    if not isinstance(trigger_low, pd.Series):
        raise ValueError("trigger_low must be a pandas Series with u's exact index (the trigger series' daily lows)")
    if not trigger_low.index.equals(u.index):
        raise ValueError("trigger_low must have exactly the same index as u (align it before calling)")
    lo = trigger_low.to_numpy(dtype=np.float64, copy=True)
    finite = np.isfinite(lo)
    if (lo[finite] <= 0).any():
        raise ValueError("trigger_low levels must be positive")
    above = finite & (lo > trig_arr * (1.0 + 1e-12))
    if above.any():
        bad = u.index[int(np.argmax(above))]
        raise ValueError(f"trigger_low is above the trigger close on {bad.date()}: a low cannot exceed the close "
                         "(is it the low of a different series?)")
    real = finite & (lo < trig_arr)
    used = np.where(real, lo, trig_arr)
    info = dict(series=(str(trigger_low.name) if trigger_low.name is not None else "unnamed low series"),
                first_real_low=(str(u.index[int(np.argmax(real))].date()) if real.any() else None),
                placeholder_rows=int((~real).sum()), rows=int(len(lo)),
                rule="breach test on the day's low where low < close; on the close where low == close or missing")
    return used, info


def periodic_reset_series(u, rate, *, reset, L, spread_per_nav, fee, early_drop, early_mode="level", trigger=None,
                          trigger_low=None, calendar="nyse", fin_day_count=FIN_DAY_COUNT, fee_day_count=FEE_DAY_COUNT,
                          allow_gaps=False, max_gap_days=7):
    """Synthetic NAV (starts at 1.0) of an L-times fund that resets weekly, monthly or quarterly, or of the
    buy-once margin position (reset "never").

    u:              pandas Series of underlying levels (price or total-return index) on a DatetimeIndex.
    rate:           pandas Series of annual decimal rates with u's exact index, ALREADY LAGGED by the caller so
                    rate[t] was known before day t (a float is accepted for a constant rate).
    reset:          "weekly", "monthly" or "quarterly"; or "never" for the buy-once margin position (a loan that
                    compounds daily: kernel.margin_position_nav; no trigger allowed).
    spread_per_nav: annual spread as a fraction of NAV (costs.spread_per_nav(spec) = spread x turns).
    fee:            annual expense ratio (costs.annual_fee(spec)): a float, or a pandas Series on u's exact index
                    (a step series, e.g. a fee cap that ends on a date); value on row t applies from row t-1 to t.
    early_drop:     0.35 resets early after a 35% in-period fall; None or 0 turns the trigger off. Required, so
                    the trigger can never be switched off by forgetting it.
    early_mode:     what the fund does once the trigger is breached (details in periodic_reset_nav):
                    "level"      (base case) resets intraday at exactly the trigger level; the prospectus says
                                 "as soon as possible" after the trigger level is reached
                    "close"      resets at that day's close (sensitivity)
                    "next_close" resets at the next day's close (sensitivity: the "final 30 minutes" clause)
    trigger:        optional Series with u's exact index that the trigger watches instead of u. The prospectus
                    trigger is on the PRICE of SPY / QQQ, so a total-return run should pass the price index here.
                    NAV is still marked on u. In "level" mode the underlying at the trigger moment is taken to
                    have moved in step with the trigger since the previous close (only that day's dividend is
                    ignored, which is negligible).
    trigger_low:    optional Series with u's exact index: the daily LOW of the trigger series (of u when trigger is
                    None). The breach test then uses the low, so an intraday touch of -35% fires the trigger as it
                    does in the real fund (BACKLOG B4). Rows where low == close count as "no intraday information"
                    (the close is tested); attrs["trigger_low"] records the first real low and the placeholder count.
    calendar:       "nyse" (default): period ends are the last NYSE sessions (periods.period_end_flags; raises if
                    one is missing from the data). None: the old last-row rule (for the local cross-checks).
    fin_day_count:  360 (default, ACT/360 on the rate and spread legs) or 365.
    fee_day_count:  365 (default) or 360.
    Everything after the `*` must be passed by name, so a fee can never be mistaken for a spread.

    ROW 0 IS A RESET. The fund's base is fixed at u's first row. Either start u on a reset date (the last
    trading day of a period: then the run equals the full-history fund from that date), or run the full history
    once and read results as ratios nav[e] / nav[s] (DESIGN.md section 8). A series that starts mid-period resets
    on its first row, which the real fund does not do, so its numbers are not the fund's.

    Returns a Series named e.g. "synthetic_2x_monthly" with attrs:
        model         every parameter used (early_mode, trigger = "underlying" or the trigger Series' name,
                      trigger_low, calendar, day counts, fee or "timeline" plus fee_timeline)
        early_resets  ISO dates of early resets
        terminated    ISO date the NAV hit 0, or None
        trigger_low   None, or dict(series, first_real_low, placeholder_rows, rows, rule)
    """
    if reset not in PERIODIC_RESETS:
        raise ValueError(f"reset must be one of {PERIODIC_RESETS}, got {reset!r} (use daily_reset_series for daily)")
    dates, u_arr, r_arr, acc_fin, acc_fee, L = _prepare(u, rate, L, allow_gaps, max_gap_days, fin_day_count,
                                                         fee_day_count)
    s = _check_number("spread_per_nav", spread_per_nav, -0.5, 0.5)
    f_arr, f_label, f_steps = _fee_array(fee, u)
    drop = 0.0 if early_drop is None else _check_number("early_drop", early_drop, 0.0, 0.999)
    if not isinstance(early_mode, str) or early_mode not in EARLY_MODES:
        raise ValueError(f"early_mode must be one of {tuple(EARLY_MODES)}, got {early_mode!r}")
    common = dict(L=L, spread_per_nav=s, fee=f_label, fin_day_count=int(fin_day_count),
                  fee_day_count=int(fee_day_count), rate="supplied by caller, lagged by caller", allow_gaps=allow_gaps)
    if f_steps is not None:
        common["fee_timeline"] = f_steps

    if reset == cal.NEVER:
        if drop > 0.0 or trigger is not None or trigger_low is not None:
            raise ValueError("reset 'never' is the buy-once margin position: it has no early reset, so pass "
                             "early_drop=None and no trigger / trigger_low")
        nav, term = margin_position_nav(u_arr, r_arr, acc_fin, acc_fee, L, s, f_arr)
        out = pd.Series(nav, index=dates, name=f"synthetic_{L:g}x_never")
        out.attrs["model"] = dict(structure="buy_once_margin", reset=reset, early_drop=None,
                                  interest="loan balance compounds daily (spread and fee are borrowed too)", **common)
        out.attrs["early_resets"] = []
        out.attrs["terminated"] = None if term < 0 else str(dates[term].date())
        out.attrs["trigger_low"] = None
        return out

    trig_arr, trig_label = _trigger_levels(trigger, u, u_arr)
    low_arr, low_info = _trigger_lows(trigger_low, trig_arr, u)
    period_end = cal.period_end_flags(dates, reset, calendar=calendar)

    nav, flags, term = periodic_reset_nav(u_arr, trig_arr, low_arr, r_arr, acc_fin, acc_fee, period_end, L, s, f_arr,
                                          drop, EARLY_MODES[early_mode])

    out = pd.Series(nav, index=dates, name=f"synthetic_{L:g}x_{reset}")
    out.attrs["model"] = dict(structure="calendar_reset", reset=reset, early_drop=(drop if drop > 0 else None),
                              early_mode=early_mode, trigger=trig_label,
                              trigger_low=(None if low_info is None else low_info["series"]),
                              calendar=calendar, **common)
    out.attrs["early_resets"] = _iso(dates, np.flatnonzero(flags))
    out.attrs["terminated"] = None if term < 0 else str(dates[term].date())
    out.attrs["trigger_low"] = low_info
    return out


def run(spec, u, rate, *, trigger=None, trigger_low=None, early_mode="level", spread_per_nav=None, fee=None,
        calendar="nyse", fin_day_count=FIN_DAY_COUNT, fee_day_count=FEE_DAY_COUNT, allow_gaps=False, max_gap_days=7):
    """One entry point: the NAV of a product, with L, spread-per-NAV and fee taken from its ProductSpec.

    This is the way to run a product (audit S1c, finding 2): the bare wrappers accept any L / spread / fee
    combination, while a ProductSpec has already checked that its turns match its leverage. Daily products go to
    the daily kernel, calendar products to the calendar kernel with the spec's own early-reset trigger.
    `spread_per_nav` and `fee` may be overridden for a sensitivity run (`fee` may be a step Series on u's index,
    e.g. a fee timeline for a validation run); every override is written into attrs["product"]["overrides"] so a
    table can never show a sensitivity as the base case. `trigger_low` (the daily low of the trigger series) and
    `calendar` pass through to the calendar kernel; the day counts to both.
    The returned Series is named after the product and carries attrs["product"] (name, kind, underlying, reset,
    costs as text, overrides) next to the usual attrs["model"].
    """
    from . import costs as c                       # local import: costs never imports kernel, so no cycle
    overrides = {}
    s = c.spread_per_nav(spec.costs) if spread_per_nav is None else _check_number("spread_per_nav", spread_per_nav, -0.5, 0.5)
    if fee is None:
        f = c.annual_fee(spec.costs)
    elif isinstance(fee, pd.Series):
        f = fee                                    # checked by the wrapper (_fee_array)
    else:
        f = _check_number("fee", fee, 0.0, 0.5)
    if spread_per_nav is not None:
        overrides["spread_per_nav"] = s
    if fee is not None:
        overrides["fee"] = "timeline (see attrs['model']['fee_timeline'])" if isinstance(fee, pd.Series) else f
    if spec.reset == "daily":
        if trigger_low is not None:
            raise ValueError(f"{spec.name} resets daily: it has no trigger, so trigger_low does not apply")
        out = daily_reset_series(u, rate, L=spec.L, spread_per_nav=s, fee=f, fin_day_count=fin_day_count,
                                 fee_day_count=fee_day_count, allow_gaps=allow_gaps, max_gap_days=max_gap_days)
    else:
        out = periodic_reset_series(u, rate, reset=spec.reset, L=spec.L, spread_per_nav=s, fee=f,
                                    early_drop=spec.early_drop, early_mode=early_mode, trigger=trigger,
                                    trigger_low=trigger_low, calendar=calendar, fin_day_count=fin_day_count,
                                    fee_day_count=fee_day_count, allow_gaps=allow_gaps, max_gap_days=max_gap_days)
    out.name = spec.name
    out.attrs["product"] = dict(name=spec.name, kind=spec.kind, underlying=spec.underlying, reset=spec.reset,
                                L=spec.L, costs=c.describe(spec.costs), overrides=overrides)
    return out


def daily_reset_series(u, rate, *, L, spread_per_nav, fee, fin_day_count=FIN_DAY_COUNT, fee_day_count=FEE_DAY_COUNT,
                       allow_gaps=False, max_gap_days=7):
    """Synthetic NAV (starts at 1.0) of an L-times fund that resets every day (the daily twin).

    Same inputs and conventions as periodic_reset_series (rate ALREADY LAGGED by the caller; fee a float or a step
    Series; ACT/360 financing and a 365-day fee year by default). Row 0 is the start (NAV 1.0). Every close is a
    reset, so a run on u sliced from any date s equals nav[s:] / nav[s] of the full-history run; still read
    multi-start results as ratios nav[e] / nav[s] so the twin is handled exactly like the calendar fund (DESIGN.md
    section 8). Returns a Series named e.g. "synthetic_2x_daily" with attrs model, early_resets (always empty) and
    terminated.
    """
    dates, u_arr, r_arr, acc_fin, acc_fee, L = _prepare(u, rate, L, allow_gaps, max_gap_days, fin_day_count,
                                                         fee_day_count)
    s = _check_number("spread_per_nav", spread_per_nav, -0.5, 0.5)
    f_arr, f_label, f_steps = _fee_array(fee, u)

    nav, term = daily_reset_nav(u_arr, r_arr, acc_fin, acc_fee, L, s, f_arr)

    out = pd.Series(nav, index=dates, name=f"synthetic_{L:g}x_daily")
    out.attrs["model"] = dict(structure="daily_reset", L=L, reset="daily", spread_per_nav=s, fee=f_label,
                              fin_day_count=int(fin_day_count), fee_day_count=int(fee_day_count),
                              rate="supplied by caller, lagged by caller", allow_gaps=allow_gaps)
    if f_steps is not None:
        out.attrs["model"]["fee_timeline"] = f_steps
    out.attrs["early_resets"] = []
    out.attrs["terminated"] = None if term < 0 else str(dates[term].date())
    return out
