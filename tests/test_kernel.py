"""Known-answer tests for periods.py, kernel.py, costs.py and products.py. Made-up data only; no files needed.

Each check says in plain words what would be wrong if it failed. Expected numbers are worked out by hand in the
comments, so a reader can verify them with a calculator.
"""
import datetime as dt
import math
import time
from dataclasses import replace

import numpy as np
import pandas as pd

from _harness import check, raises  # noqa: I001  (must come first: puts the repo root on sys.path)
from calendar_letf import periods as cal
from calendar_letf import costs, nyse, products
from calendar_letf import kernel as k


def periodic(u, reset, L=2.0, rate=0.0, spread_per_nav=0.0, fee=0.0, early_drop=None, early_mode="level",
             trigger=None, trigger_low=None, **kw):
    """Calendar-reset NAV with zero costs unless given (the package itself has no cost defaults)."""
    return k.periodic_reset_series(u, rate, reset=reset, L=L, spread_per_nav=spread_per_nav, fee=fee,
                                   early_drop=early_drop, early_mode=early_mode, trigger=trigger,
                                   trigger_low=trigger_low, **kw)


def daily(u, L=2.0, rate=0.0, spread_per_nav=0.0, fee=0.0, **kw):
    return k.daily_reset_series(u, rate, L=L, spread_per_nav=spread_per_nav, fee=fee, **kw)


def arrays(index, fee=0.0):
    """(accrual_fin, accrual_fee, fee array) for a raw kernel call: the wrappers' defaults, ACT/360 and 365."""
    return cal.accrual_fraction(index, 360), cal.accrual_fraction(index), np.full(len(index), float(fee))


def max_rel_diff(a, b):
    """Largest |a - b| / |b| over all rows; rows where both are 0 count as equal."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return float(np.max(np.abs(a - b) / np.maximum(np.abs(b), 1e-300))) if len(a) else 0.0


def walk(start, n, seed, vol, drift=0.0003):
    """A made-up index: n business days of random daily moves (log-normal, so always positive)."""
    ix = pd.bdate_range(start, periods=n)
    rng = np.random.default_rng(seed)
    return pd.Series(100.0 * np.exp(np.cumsum(rng.normal(drift, vol, n))), index=ix)


# =================================================================================================================
# 1. periods.py: period ids, period ends, accrual
# =================================================================================================================
days = pd.bdate_range("2024-01-01", "2024-06-28").drop(pd.Timestamp("2024-03-29"))   # Good Friday: NYSE closed

wk = cal.period_ids(days, "weekly")
id_changes = np.flatnonzero(np.diff(wk) != 0) + 1
mondays = np.flatnonzero(days.dayofweek == 0)
check("calendar: weekly ids change exactly on Mondays (weekday calendar)",
      np.array_equal(id_changes, mondays[mondays > 0]))

sample = pd.DatetimeIndex(["1950-01-03", "1969-12-31", "1970-01-01", "1970-01-04", "2024-06-15", "2024-12-31"])
expected = [(d.date() - dt.timedelta(days=d.weekday())).toordinal() for d in sample]
check("calendar: weekly id = Python ordinal of that week's Monday, also before 1970 and on weekends",
      list(cal.period_ids(sample, "weekly")) == expected, f"{list(cal.period_ids(sample, 'weekly'))} vs {expected}")

ny = pd.DatetimeIndex(["2024-12-30", "2024-12-31", "2025-01-02", "2025-01-03", "2025-01-06"])
ny_ids = cal.period_ids(ny, "weekly")
check("calendar: a week spanning New Year is one weekly period; the next Monday starts a new one",
      len(set(ny_ids[:4])) == 1 and ny_ids[4] != ny_ids[3])

mlk = pd.bdate_range("2024-01-08", "2024-01-26").drop(pd.Timestamp("2024-01-15"))     # Monday holiday
f_mlk = cal.period_end_flags(mlk, "weekly", calendar=None)
check("calendar (last-row rule): with a Monday holiday the week still ends on Friday and the next starts on Tuesday",
      list(mlk[f_mlk].strftime("%Y-%m-%d")) == ["2024-01-12", "2024-01-19"])
f_mlk_n = cal.period_end_flags(mlk, "weekly")
check("calendar (NYSE): the same weeks end on 01-12 and 01-19, and the final row 01-26 is flagged too: it is the last "
      "session of its week, so that week is complete",
      list(mlk[f_mlk_n].strftime("%Y-%m-%d")) == ["2024-01-12", "2024-01-19", "2024-01-26"])

f_week = cal.period_end_flags(days, "weekly", calendar=None)
check("calendar (last-row rule): weekly ends are Fridays, Thursday 2024-03-28 in Good Friday week, final row not flagged",
      days[f_week].dayofweek.isin([4]).sum() == f_week.sum() - 1 and pd.Timestamp("2024-03-28") in days[f_week]
      and not f_week[-1])
f_week_n = cal.period_end_flags(days, "weekly")
check("calendar (NYSE): weekly ends are the same Fridays and Thursday 03-28, plus the final row Friday 06-28 (26 weeks)",
      np.array_equal(f_week_n[:-1], f_week[:-1]) and f_week_n[-1] and f_week_n.sum() == 26, int(f_week_n.sum()))

f_month = cal.period_end_flags(days, "monthly", calendar=None)
check("calendar (last-row rule): monthly ends land on the last trading day of each month (03-28 because of Good "
      "Friday); the final row 06-28 is not flagged",
      list(days[f_month].strftime("%Y-%m-%d")) == ["2024-01-31", "2024-02-29", "2024-03-28", "2024-04-30", "2024-05-31"],
      list(days[f_month].strftime("%Y-%m-%d")))
f_month_n = cal.period_end_flags(days, "monthly")
check("calendar (NYSE): monthly ends are the last NYSE sessions 01-31, 02-29, 03-28, 04-30, 05-31 and 06-28 (the final "
      "row, the last session of June 2024)",
      list(days[f_month_n].strftime("%Y-%m-%d")) == ["2024-01-31", "2024-02-29", "2024-03-28", "2024-04-30", "2024-05-31",
                                                     "2024-06-28"], list(days[f_month_n].strftime("%Y-%m-%d")))
f_q = cal.period_end_flags(days, "quarterly", calendar=None)
check("calendar (last-row rule): quarterly end lands on 2024-03-28 only (final row not flagged)",
      list(days[f_q].strftime("%Y-%m-%d")) == ["2024-03-28"])
check("calendar (NYSE): quarterly ends 2024-03-28 and the final row 2024-06-28",
      list(days[cal.period_end_flags(days, "quarterly")].strftime("%Y-%m-%d")) == ["2024-03-28", "2024-06-28"])
raises("calendar: period ids passed instead of dates are refused (they would be read as nanoseconds)",
       lambda: cal.period_end_flags(wk, "weekly"), "not period ids")
check("calendar: monthly id = year*100+month, quarterly id = year*10+quarter index",
      cal.period_ids(days, "monthly")[0] == 202401 and cal.period_ids(days, "quarterly")[-1] == 20241)
check("calendar: ids are int64", cal.period_ids(days, "weekly").dtype == np.int64
      and cal.period_ids(days, "monthly").dtype == np.int64 and cal.period_ids(days, "quarterly").dtype == np.int64)
raises("calendar: unknown reset raises", lambda: cal.period_ids(days, "daily"), "reset must be")
raises("calendar: dates out of order raise", lambda: cal.period_ids(days[::-1], "monthly"), "strictly increasing")

thu_fri_mon = pd.DatetimeIndex(["2024-01-04", "2024-01-05", "2024-01-08"])
a = cal.accrual_fraction(thu_fri_mon)
check("calendar: accrual is 0 on the first row, 1/365 Thu->Fri, 3/365 Fri->Mon (weekend accrues)",
      a[0] == 0.0 and a[1] == 1 / 365 and a[2] == 3 / 365 and a.dtype == np.float64, list(a))
a360 = cal.accrual_fraction(thu_fri_mon, 360)
check("calendar: ACT/360 accrual is 0, 1/360, 3/360 (the financing legs' day count, R2 E2)",
      a360[0] == 0.0 and a360[1] == 1 / 360 and a360[2] == 3 / 360, list(a360))
raises("calendar: a day count other than 360 or 365 is refused", lambda: cal.accrual_fraction(thu_fri_mon, 252), "days_in_year")
same_as_letf = pd.Series(days, index=days).diff().dt.days.fillna(0.0).values / 365.0       # letf's formula
check("calendar: accrual equals letf's data_io.accrual_fraction formula exactly",
      np.array_equal(cal.accrual_fraction(days), same_as_letf))

# -----------------------------------------------------------------------------------------------------------------
# 1b. the NYSE session calendar (nyse.py) and period ends from it (R2 E3)
# -----------------------------------------------------------------------------------------------------------------
D = dt.date
h2024 = sorted(nyse.holidays(2024))
check("nyse: 2024 holidays are New Year 01-01, MLK 01-15, Washington 02-19, Good Friday 03-29, Memorial 05-27, "
      "Juneteenth 06-19, Independence 07-04, Labor 09-02, Thanksgiving 11-28, Christmas 12-25",
      h2024 == [D(2024, 1, 1), D(2024, 1, 15), D(2024, 2, 19), D(2024, 3, 29), D(2024, 5, 27), D(2024, 6, 19),
                D(2024, 7, 4), D(2024, 9, 2), D(2024, 11, 28), D(2024, 12, 25)], h2024)
check("nyse: Easter Sunday 2024-03-31, 2001-04-15, 1970-03-29 (so Good Friday 03-29, 04-13, 03-27)",
      nyse.easter(2024) == D(2024, 3, 31) and nyse.easter(2001) == D(2001, 4, 15) and nyse.easter(1970) == D(1970, 3, 29))
check("nyse: Saturday holidays close the Friday before (2021-12-24, Christmas; 2020-07-03, Independence Day), a Sunday "
      "one the Monday after (2022-06-20 Juneteenth, 2017-01-02 New Year), and a Saturday New Year closes nothing "
      "(2021-12-31 and 1999-12-31 are sessions)",
      not nyse.is_session(D(2021, 12, 24)) and not nyse.is_session(D(2020, 7, 3)) and not nyse.is_session(D(2022, 6, 20))
      and not nyse.is_session(D(2017, 1, 2)) and nyse.is_session(D(2021, 12, 31)) and nyse.is_session(D(1999, 12, 31))
      and D(2022, 1, 1) not in nyse.holidays(2022) and len(nyse.holidays(2022)) == 9)
check("nyse: rule changes: MLK Day closed from 1998 (1998-01-19 closed, 1997-01-20 open); Juneteenth from 2022 "
      "(2021-06-18 open); Washington's Birthday on Feb 22 in 1970 (observed Monday 1970-02-23) and the 3rd Monday from "
      "1971 (1971-02-15); Memorial Day on the last Monday of May from 1971 (1971-05-31)",
      not nyse.is_session(D(1998, 1, 19)) and nyse.is_session(D(1997, 1, 20)) and nyse.is_session(D(2021, 6, 18))
      and not nyse.is_session(D(1970, 2, 23)) and not nyse.is_session(D(1971, 2, 15)) and not nyse.is_session(D(1971, 5, 31)))
check("nyse: Memorial Day 1970 fell on Saturday 05-30 and Friday 05-29 was the last business day of May, so the exchange "
      "stayed open (Saturday-holiday rule; the SPX file has a full bar that day)", nyse.is_session(D(1970, 5, 29)))
check("nyse: presidential Election Day closures 1972-11-07, 1976-11-02, 1980-11-04; open on 1984-11-06",
      not any(nyse.is_session(d_) for d_ in (D(1972, 11, 7), D(1976, 11, 2), D(1980, 11, 4))) and nyse.is_session(D(1984, 11, 6)))
check("nyse: one-off closures are not sessions (2001-09-11..14, 2012-10-29/30, 2025-01-09) and every listed date is a weekday",
      all(not nyse.is_session(d_) for d_ in nyse.SPECIAL_CLOSURES) and all(d_.weekday() < 5 for d_ in nyse.SPECIAL_CLOSURES)
      and len(nyse.SPECIAL_CLOSURES) >= 15)
check("nyse: 2024 has 252 sessions (366 days - 104 weekend days - 10 holidays); the fast array agrees with sessions()",
      len(nyse.sessions(D(2024, 1, 1), D(2024, 12, 31))) == 252
      and np.array_equal(pd.DatetimeIndex(nyse.sessions(D(1990, 1, 1), D(1990, 12, 31))).values.astype("datetime64[D]").astype(np.int64),
                         nyse.session_day_numbers()[(nyse.session_day_numbers() >= 7305) & (nyse.session_day_numbers() <= 7669)]))
raises("nyse: dates before 1970 are refused (no rule set here)", lambda: nyse.holidays(1969), "covers 1970")

s2024 = pd.DatetimeIndex(nyse.sessions(D(2024, 1, 2), D(2024, 12, 31)))     # every 2024 session, nothing else
exp_m = cal.expected_period_ends(s2024, "monthly")
check("period ends 2024: the last sessions of each month are 01-31, 02-29, 03-28 (Good Friday 03-29 closed), 04-30, "
      "05-31, 06-28, 07-31, 08-30, 09-30, 10-31, 11-29, 12-31",
      list(exp_m.strftime("%m-%d")) == ["01-31", "02-29", "03-28", "04-30", "05-31", "06-28", "07-31", "08-30", "09-30",
                                       "10-31", "11-29", "12-31"], list(exp_m.strftime("%m-%d")))
exp_w = cal.expected_period_ends(s2024, "weekly")
check("period ends 2024: Juneteenth (Wed 06-19) does not move the week's end (Fri 06-21); Good Friday week ends Thu 03-28; "
      "Independence Day week ends Fri 07-05; Christmas week ends Fri 12-27",
      all(pd.Timestamp(x) in exp_w for x in ("2024-06-21", "2024-03-28", "2024-07-05", "2024-12-27"))
      and pd.Timestamp("2024-03-29") not in exp_w)
f24 = cal.period_end_flags(s2024, "quarterly")
check("period ends 2024: quarterly flags on 03-28, 06-28, 09-30 and the FINAL row 2024-12-31 (the last session of Q4)",
      list(s2024[f24].strftime("%Y-%m-%d")) == ["2024-03-28", "2024-06-28", "2024-09-30", "2024-12-31"]
      and f24[-1] and not cal.period_end_flags(s2024, "quarterly", calendar=None)[-1])
s2001 = pd.DatetimeIndex(nyse.sessions(D(2001, 8, 27), D(2001, 9, 28)))
w2001 = s2001[cal.period_end_flags(s2001, "weekly")]
check("period ends 2001-09: the week of the attacks ends on its last session, Monday 09-10 (09-11..14 closed); the "
      "next week ends Friday 09-21",
      pd.Timestamp("2001-09-10") in w2001 and pd.Timestamp("2001-09-21") in w2001 and len(w2001) == 5
      and not any(pd.Timestamp(f"2001-09-{d_}") in s2001 for d_ in (11, 12, 13, 14)), list(w2001.strftime("%m-%d")))
s2012 = pd.DatetimeIndex(nyse.sessions(D(2012, 10, 1), D(2012, 11, 30)))
m2012 = s2012[cal.period_end_flags(s2012, "monthly")]
check("period ends 2012-10: October's last session is Wednesday 10-31 (Sandy closed 10-29 and 10-30); November's is 11-30",
      list(m2012.strftime("%Y-%m-%d")) == ["2012-10-31", "2012-11-30"])
holed = s2024.drop(pd.Timestamp("2024-05-31"))
raises("period ends: a deleted month-end row (2024-05-31) raises, naming the date, instead of moving the reset to 05-30",
       lambda: cal.period_end_flags(holed, "monthly"), "2024-05-31")
check("period ends: the same deleted row under calendar=None silently moves May's reset to 05-30 (why the NYSE rule exists)",
      pd.Timestamp("2024-05-30") in holed[cal.period_end_flags(holed, "monthly", calendar=None)])
raises("period ends: the wrapper refuses the holed series too (the reset cannot be placed)",
       lambda: periodic(pd.Series(100.0, index=holed), "monthly"), "missing from the data")
ext = pd.DatetimeIndex(sorted(set(s2024) | {pd.Timestamp("2024-03-29"), pd.Timestamp("2024-07-04")}))
check("period ends: rows on non-session days (Good Friday 03-29, a stale bar) are allowed and never flagged; March still "
      "resets on 03-28", pd.Timestamp("2024-03-28") in ext[cal.period_end_flags(ext, "monthly")]
      and not cal.period_end_flags(ext, "monthly")[ext.get_loc(pd.Timestamp("2024-03-29"))])
pre = pd.bdate_range("1969-11-20", "1970-02-10")
f_pre = cal.period_end_flags(pre, "monthly")
check("period ends across 1970-01-01: Nov and Dec 1969 use the last-row rule (11-28, 12-31), Jan 1970 the NYSE rule "
      "(01-30); the weekday guard of the loader is the only protection before 1970",
      list(pre[f_pre].strftime("%Y-%m-%d")) == ["1969-11-28", "1969-12-31", "1970-01-30"], list(pre[f_pre].strftime("%Y-%m-%d")))
mm = cal.session_mismatches(ext)
check("session_mismatches lists rows that are not sessions and sessions with no row",
      mm["extra"] == ["2024-03-29", "2024-07-04"] and mm["missing"] == []
      and cal.session_mismatches(holed)["missing"] == ["2024-05-31"])

# =================================================================================================================
# 2. kernels: known answers
# =================================================================================================================
# a) L = 1 with zero costs is the index itself, for every reset
idx = walk("2023-01-02", 750, seed=1, vol=0.012)
for reset in cal.RESETS:
    s = periodic(idx, reset, L=1.0)
    check(f"kernel: L=1, zero costs, {reset} reset reproduces the index (1e-12)",
          max_rel_diff(s.values, idx.values / idx.iloc[0]) < 1e-12)
check("kernel: L=1, zero costs, daily reset reproduces the index (1e-12)",
      max_rel_diff(daily(idx, L=1.0).values, idx.values / idx.iloc[0]) < 1e-12)

# b) +10%, +10% inside one week/month/quarter: calendar = 1 + 2 x 21% = 1.42; daily = 1.2 x 1.2 = 1.44
two = pd.Series([100.0, 110.0, 121.0], index=pd.bdate_range("2024-01-02", periods=3))
for reset in cal.RESETS:
    v = periodic(two, reset).iloc[-1]
    check(f"kernel: 2x {reset} after +10%,+10% in one period = 1.42 (no in-period compounding)", abs(v - 1.42) < 1e-12, v)
v = daily(two).iloc[-1]
check("kernel: 2x daily after +10%,+10% = 1.44 (compounds daily)", abs(v - 1.44) < 1e-12, v)

# c) each full period at zero cost returns exactly 1 + 2 x the underlying's return over that period
for reset in cal.RESETS:
    nav = periodic(idx, reset).values
    ends = np.flatnonzero(cal.period_end_flags(idx.index, reset))
    errs = [abs(nav[e] / nav[s] - (1 + 2 * (idx.iloc[e] / idx.iloc[s] - 1))) for s, e in zip(ends[:-1], ends[1:])]
    check(f"kernel: every full {reset} period ({len(errs)} of them) returns 1 + 2 x underlying return (1e-12)",
          len(errs) > 5 and max(errs) < 1e-12, f"max error {max(errs):.1e}")

# d) the 35% trigger, "close" mode (test d of an earlier private kit): -36% then +10%.
#    Day 1: NAV = 2 x 0.64 - 1 = 0.28 and the fall of 36% triggers a reset at the close (new base 64).
#    Day 2: +10% on the new base -> 0.28 x (1 + 2 x 10%) = 0.336.  Without the trigger: 1 + 2 x (70.4/100 - 1) = 0.408.
dip = pd.Series([100.0, 64.0, 70.4], index=pd.bdate_range("2024-01-02", periods=3))
early = periodic(dip, "monthly", early_drop=0.35, early_mode="close")
noearly = periodic(dip, "monthly", early_drop=None)
check("kernel: close mode: -36% in-month resets at the close; +10% next day earns 2 x 10% on the new base (0.28 x 1.2)",
      early.attrs["early_resets"] == ["2024-01-03"] and abs(early.iloc[-1] - 0.28 * 1.2) < 1e-12
      and abs(noearly.iloc[-1] - 0.408) < 1e-12 and noearly.attrs["early_resets"] == [],
      (early.iloc[-1], noearly.iloc[-1], early.attrs["early_resets"]))

# e) "next_close": the reset happens at the NEXT close. Index 100, 64 (-36%), 70.4, 77.44 (+10% twice).
#    close:      reset at 64 with NAV 0.28 -> 77.44/64 = 1.21 -> 0.28 x (2 x 1.21 - 1) = 0.28 x 1.42 = 0.3976
#    next_close: day 2 still on the old base: 2 x 0.704 - 1 = 0.408, reset there at 70.4 -> day 3: 0.408 x 1.2 = 0.4896
#    no trigger: 2 x 0.7744 - 1 = 0.5488
four = pd.Series([100.0, 64.0, 70.4, 77.44], index=pd.bdate_range("2024-01-02", periods=4))
d0 = periodic(four, "monthly", early_drop=0.35, early_mode="close")
d1 = periodic(four, "monthly", early_drop=0.35, early_mode="next_close")
dn = periodic(four, "monthly", early_drop=None)
check("kernel: close mode resets at the triggering close: final NAV 0.3976, reset dated 2024-01-03",
      abs(d0.iloc[-1] - 0.3976) < 1e-12 and d0.attrs["early_resets"] == ["2024-01-03"], (d0.iloc[-1], d0.attrs["early_resets"]))
check("kernel: next_close mode resets one close later: NAV 0.408 on the reset day, final 0.4896, reset dated 2024-01-04",
      abs(d1.iloc[2] - 0.408) < 1e-12 and abs(d1.iloc[-1] - 0.4896) < 1e-12 and d1.attrs["early_resets"] == ["2024-01-04"],
      (d1.iloc[2], d1.iloc[-1], d1.attrs["early_resets"]))
check("kernel: with no trigger the same path ends at 0.5488", abs(dn.iloc[-1] - 0.5488) < 1e-12, dn.iloc[-1])

# f) next_close when the next day is a month end: the reset there is an ordinary period reset (not 'early')
edge = pd.Series([100.0, 64.0, 70.4, 77.44], index=pd.DatetimeIndex(["2024-01-29", "2024-01-30", "2024-01-31", "2024-02-01"]))
e1 = periodic(edge, "monthly", early_drop=0.35, early_mode="next_close")
check("kernel: next_close trigger on 01-30 with 01-31 a month end: reset on 01-31 as a period reset, final 0.4896, "
      "no early reset listed", abs(e1.iloc[-1] - 0.4896) < 1e-12 and e1.attrs["early_resets"] == [],
      (e1.iloc[-1], e1.attrs["early_resets"]))
# g) the trigger fires ON a month end: in close / next_close mode the period reset happens there, nothing is left
#    pending and nothing is flagged
onend = pd.Series([100.0, 64.0, 70.4], index=pd.DatetimeIndex(["2024-01-30", "2024-01-31", "2024-02-01"]))
g0 = periodic(onend, "monthly", early_drop=0.35, early_mode="close")
g1 = periodic(onend, "monthly", early_drop=0.35, early_mode="next_close")
check("kernel: close/next_close: a trigger on a period-end close is just the period reset (0.28 x 1.2, no early reset)",
      abs(g0.iloc[-1] - 0.336) < 1e-12 and abs(g1.iloc[-1] - 0.336) < 1e-12
      and g0.attrs["early_resets"] == [] and g1.attrs["early_resets"] == [])

# h) a fall of 1/L (50%) inside the period finishes a 2x calendar fund; it stays at zero
crash = pd.Series([100.0, 80.0, 49.0, 60.0, 70.0], index=pd.bdate_range("2024-01-02", periods=5))
dead = periodic(crash, "monthly", early_drop=None)
_, _, term = k.periodic_reset_nav(crash.values.copy(), crash.values.copy(), crash.values.copy(), np.zeros(5),
                                  *arrays(crash.index)[:2], cal.period_end_flags(crash.index, "monthly"), 2.0, 0.0,
                                  np.zeros(5), 0.0, k.EARLY_LEVEL)
check("kernel: 2x monthly hits 0 when the index halves in-month, stays 0, terminated_index = 2 (2024-01-04)",
      dead.iloc[2] == 0 and dead.iloc[-1] == 0 and (dead.iloc[2:] == 0).all() and dead.attrs["terminated"] == "2024-01-04"
      and term == 2 and abs(dead.iloc[1] - 0.6) < 1e-12)
halve = pd.Series([100.0, 50.0, 60.0], index=pd.bdate_range("2024-01-02", periods=3))
dd = daily(halve)
check("kernel: 2x daily is finished by a -50% day and stays 0",
      dd.iloc[1] == 0 and dd.iloc[2] == 0 and dd.attrs["terminated"] == "2024-01-03")

# i) flat index, rate 5%, spread 1% per turn on 2 turns, fee 1%, one calendar year (2024-01-01 to 2024-12-31: 365
#    days, so the fee accruals sum to 365/365 and the ACT/360 financing accruals to 365/360):
#    costs are (5% + 2%) x 365/360 + 1% = 7.0972% + 1% = 8.0972% a year. They are charged on a shrinking NAV, so the
#    SIMPLE loss is a little under that; the LOG loss, -ln(NAV), is 8.0972% plus a small in-period term.
flat = pd.Series(100.0, index=pd.bdate_range("2024-01-01", "2024-12-31"))
check("kernel: test year accrues exactly one year", abs(cal.accrual_fraction(flat.index).sum() - 1.0) < 1e-12)
cost = dict(rate=0.05, spread_per_nav=0.01 * 2, fee=0.01)
for reset in cal.RESETS + ("daily",):
    nav_end = (daily(flat, **cost) if reset == "daily" else periodic(flat, reset, **cost)).iloc[-1]
    log_loss = -math.log(nav_end)
    check(f"kernel: flat index, {reset}: costs take ~8.10%/yr (log loss {log_loss:.4%}, simple {1 - nav_end:.4%}) "
          "within 0.3 pt", abs(log_loss - (0.07 * 365 / 360 + 0.01)) < 0.003, f"log loss {log_loss:.4%}")

# i2) R2 E2, the day counts. Same flat 2024 year (262 weekday rows: 209 one-day steps and 52 three-day weekend steps,
#     209 + 3 x 52 = 365 days).
#     Financing leg alone (rate 5%, no spread, no fee): ACT/360 charges 5% x 365/360 = 5.0694% a year. The daily fund's
#     log loss is sum of -ln(1 - x) with x = 0.05 g/360, = 5.0694% + sum x^2/2 = 5.0694% + 209 x (0.05/360)^2/2
#     + 52 x (0.15/360)^2/2 = 5.0694% + 0.0007% (6.5e-6): check within 1e-5. On calendar days / 365 it would be
#     5.0000%, 0.07 pt away. The calendar funds pay simple interest inside each period, so their log loss adds
#     sum over periods of x_p^2/2 with x_p = 0.05 x days/360: about 2e-5 weekly, 1.1e-4 monthly, 3.2e-4 quarterly;
#     check within 5e-4 of 5.0694% (and more than 5e-4 above the /365 value 5.0000%).
#     Fee leg alone (fee 1%, rate 0): the fee is charged on yesterday's NAV in every structure, so NAV_t = NAV_{t-1}
#     x (1 - 0.01 g/365) and the log loss is 1% + sum x^2/2 = 1% + 2.5e-7: check within 1e-6 for every reset.
fin_only = dict(rate=0.05, spread_per_nav=0.0, fee=0.0)
fee_only = dict(rate=0.0, spread_per_nav=0.0, fee=0.01)
ll_fin = {r_: -math.log((daily(flat, **fin_only) if r_ == "daily" else periodic(flat, r_, **fin_only)).iloc[-1])
          for r_ in cal.RESETS + ("daily",)}
ll_fee = {r_: -math.log((daily(flat, **fee_only) if r_ == "daily" else periodic(flat, r_, **fee_only)).iloc[-1])
          for r_ in cal.RESETS + ("daily",)}
check(f"day count: the daily fund's financing log loss is 5% x 365/360 = 5.0694% (got {ll_fin['daily']:.5%}, 1e-5)",
      abs(ll_fin["daily"] - 0.05 * 365 / 360) < 1e-5, ll_fin["daily"])
check("day count: every calendar fund's financing log loss is 5.0694% plus its in-period simple-interest term (< 5e-4), "
      "and clearly above the calendar/365 value of 5.0000%",
      all(0 <= ll_fin[r_] - 0.05 * 365 / 360 < 5e-4 and ll_fin[r_] - 0.05 > 5e-4 for r_ in cal.RESETS),
      {r_: f"{v:.5%}" for r_, v in ll_fin.items()})
check("day count: the fee leg costs exactly 1% of a 365-day year in every structure (log loss within 1e-6)",
      all(abs(v - 0.01) < 1e-6 for v in ll_fee.values()), {r_: f"{v:.6%}" for r_, v in ll_fee.items()})
old_dc = daily(flat, **fin_only, fin_day_count=365).iloc[-1]
check("day count: fin_day_count=365 restores the old calendar/365 financing (log loss 5.0000% + 6.3e-6, 1e-5)",
      abs(-math.log(old_dc) - 0.05) < 1e-5, -math.log(old_dc))
raises("day count: a financing day count other than 360 or 365 is refused",
       lambda: daily(flat, **fin_only, fin_day_count=252), "fin_day_count")

# i3) R2 E5, the fee as a timeline. Fee 2% a year on the steps up to 2024-07-01 and 0% after, flat 2024 index, no
#     other costs. Days from 2024-01-01 to 2024-07-01: 31 + 29 + 31 + 30 + 31 + 30 = 182, so the fee charged is
#     2% x 182/365 = 0.99726%, i.e. 1% of a year to within half a day (0.0027 pt); log loss = 0.99726% + sum x^2/2
#     with x = 0.02 g/365 on 130 steps (about 6e-7): check within 2e-6 of 2% x 182/365, and within 3e-5 of 1%.
step_fee = pd.Series(np.where(flat.index <= "2024-07-01", 0.02, 0.0), index=flat.index)
ll_step = {r_: -math.log((daily(flat, fee=step_fee) if r_ == "daily" else periodic(flat, r_, fee=step_fee)).iloc[-1])
           for r_ in cal.RESETS + ("daily",)}
check("fee timeline: 2% for the first half of a flat year and 0% after costs 2% x 182/365 = 0.99726% (about 1% of a year) "
      "in every structure",
      all(abs(v - 0.02 * 182 / 365) < 2e-6 and abs(v - 0.01) < 3e-5 for v in ll_step.values()),
      {r_: f"{v:.6%}" for r_, v in ll_step.items()})
const_fee = pd.Series(0.0103, index=idx.index)
check("fee timeline: a float fee and a constant fee Series give bit-identical NAVs (calendar and daily)",
      np.array_equal(periodic(idx, "monthly", rate=0.04, spread_per_nav=0.022, fee=0.0103, early_drop=0.35).values,
                     periodic(idx, "monthly", rate=0.04, spread_per_nav=0.022, fee=const_fee, early_drop=0.35).values)
      and np.array_equal(daily(idx, rate=0.04, fee=0.0103).values, daily(idx, rate=0.04, fee=const_fee).values))
tl = periodic(flat, "monthly", fee=step_fee).attrs["model"]
check("fee timeline: attrs record 'timeline' and the steps (2% from the first step, 0% from 2024-07-02)",
      tl["fee"] == "timeline" and tl["fee_timeline"] == [["2024-01-02", 0.02], ["2024-07-02", 0.0]], tl.get("fee_timeline"))
raises("fee timeline: a fee Series on another index is refused",
       lambda: periodic(flat, "monthly", fee=step_fee.iloc[1:]), "same index")
raises("fee timeline: a fee Series in percent is refused",
       lambda: periodic(flat, "monthly", fee=step_fee * 100), "annual decimals")

# j) the two kernels agree when L = 1 and costs are 0
for reset in cal.RESETS:
    check(f"kernel: L=1 zero costs, {reset} kernel == daily kernel (1e-12)",
          max_rel_diff(periodic(idx, reset, L=1.0).values, daily(idx, L=1.0).values) < 1e-12)

# k) structural check: a calendar fund that resets EVERY day is a daily fund (same costs, L = 2), with the two
#    accrual arrays (ACT/360 financing, 365-day fee) and a fee that steps from 1.30% to 1.00% halfway
u_k = walk("2010-01-01", 2000, seed=3, vol=0.015)
r_k = 0.02 + 0.015 * np.sin(np.arange(2000) / 200.0)
af_k, ae_k, _ = arrays(u_k.index)
fee_k = np.where(np.arange(2000) < 1000, 0.013, 0.010)
nav_p, _, _ = k.periodic_reset_nav(u_k.values.copy(), u_k.values.copy(), u_k.values.copy(), r_k, af_k, ae_k,
                                   np.ones(2000, dtype=np.bool_), 2.0, 0.022, fee_k, 0.0, k.EARLY_LEVEL)
nav_d, _ = k.daily_reset_nav(u_k.values.copy(), r_k, af_k, ae_k, 2.0, 0.022, fee_k)
diff_k = max_rel_diff(nav_p, nav_d)
check(f"kernel: calendar kernel with a reset on every row == daily kernel, with costs, two day counts and a fee step "
      f"(max rel diff {diff_k:.1e})", diff_k < 1e-11)


# l) numba kernels == a plain-Python loop written here (guards against a numba typing slip, e.g. integer maths)
LEVEL, CLOSE, NEXT_CLOSE = k.EARLY_LEVEL, k.EARLY_CLOSE, k.EARLY_NEXT_CLOSE


def ref_periodic(u, tr, lw, r, a, a2, pe, L, s, f, drop, mode):
    """Plain-Python calendar fund: a = financing accrual, a2 = fee accrual, f = fee per row, lw = the trigger's low."""
    u, tr, lw, r, a, a2, pe, f = (x.tolist() for x in (u, tr, lw, r, a, a2, pe, f))
    n = len(u)
    nav, flags, term = [1.0] + [0.0] * (n - 1), [0] * n, -1
    nav0, u0, g0, carry, fees, pending = 1.0, u[0], tr[0], 0.0, 0.0, False
    for t in range(1, n):
        carry += ((L - 1.0) * r[t] + s) * a[t]
        fees += f[t] * nav[t - 1] * a2[t]
        low = min(lw[t], tr[t])                           # the day's lowest trigger level
        if mode == LEVEL and drop > 0:
            u_ref, g_ref = u[t - 1], tr[t - 1]           # last point where both levels are known
            while low / g0 - 1.0 <= -drop:                # reset at the level, as many times as the day's low needs
                g_hit = g0 * (1.0 - drop)
                u_hit = g_hit * (u_ref / g_ref)
                v_hit = nav0 * (L * u_hit / u0 - (L - 1.0)) - nav0 * carry - fees
                if v_hit <= 0:
                    term = t
                    break
                nav0, u0, g0, carry, fees, u_ref, g_ref, flags[t] = v_hit, u_hit, g_hit, 0.0, 0.0, u_hit, g_hit, 1
            if term >= 0:
                break
        v = nav0 * (L * u[t] / u0 - (L - 1.0)) - nav0 * carry - fees
        if v <= 0:
            term = t
            break
        nav[t] = v
        fell = mode != LEVEL and drop > 0 and low / g0 - 1.0 <= -drop
        if pe[t]:
            do_reset = True
        elif pending or (fell and mode == CLOSE):
            do_reset, flags[t] = True, 1
        else:
            do_reset, pending = False, (pending or fell)
        if do_reset:
            nav0, u0, g0, carry, fees, pending = v, u[t], tr[t], 0.0, 0.0, False
    return np.array(nav), np.array(flags), term


def ref_daily(u, r, a, a2, L, s, f):
    u, r, a, a2, f = u.tolist(), r.tolist(), a.tolist(), a2.tolist(), f.tolist()
    nav, term = [1.0], -1
    for t in range(1, len(u)):
        if term >= 0:
            nav.append(0.0)
            continue
        d = L * (u[t] / u[t - 1] - 1.0) - ((L - 1.0) * r[t] + s) * a[t] - f[t] * a2[t]    # same order as the kernel
        v = nav[-1] * (1.0 + d)
        if v <= 0:
            term, v = t, 0.0
        nav.append(v)
    return np.array(nav), term


calm = walk("1990-01-01", 3000, seed=11, vol=0.012)
wild_vals = walk("1990-01-01", 3000, seed=12, vol=0.03).to_numpy(copy=True)    # a copy we may edit
for row in (1000, 1001, 1002):                 # rows 1000-1002 are Mon-Wed: three -15% days = -38.6% in one week,
    wild_vals[row:] *= 0.85                    # so the 35% trigger fires mid-week for every reset type
wild_vals[2600:] *= 0.45                       # and a one-day -55% crash near the end finishes every fund
wild = pd.Series(wild_vals, index=calm.index)
rate_l = 0.03 + 0.02 * np.sin(np.arange(3000) / 300.0)
acc_l, acc2_l, _ = arrays(calm.index)                       # ACT/360 financing, 365-day fee
fee_l = np.where(np.arange(3000) < 1500, 0.0131, 0.0103)   # a fee step halfway (1.31% -> 1.03%)
# A separate trigger: a "price index" that trails the path (a total-return index) by a 3%/yr dividend yield, so
# the trigger and the NAV level differ by the dividends earned since the last reset.
div_drag = np.exp(-0.03 * np.arange(3000) / 252.0)
# Intraday lows (R2 E4): each day's low is below its close by |N(0, 1.5%)|, and on one row in four it equals the close
# (a placeholder bar). The "wild" path's -15% days then breach -35% on the low a day before the close does.
dip_rng = np.random.default_rng(99)
low_frac = np.exp(-np.abs(dip_rng.normal(0.0, 0.015, 3000)))
low_frac[dip_rng.random(3000) < 0.25] = 1.0
worst, n_cases, early_seen, saw_dead, low_moved = 0.0, 0, set(), False, False
for path in (calm, wild):
    uu = path.values.copy()
    for trig_name, tt in (("on u", uu), ("on price", uu * div_drag)):
        for low_name, lw in (("close-only", tt), ("with lows", tt * low_frac)):
            for reset in cal.RESETS:
                pe = cal.period_end_flags(path.index, reset)
                for drop in (0.0, 0.35):
                    for mode in (LEVEL, CLOSE, NEXT_CLOSE):
                        nav_n, fl_n, te_n = k.periodic_reset_nav(uu, tt, lw, rate_l, acc_l, acc2_l, pe, 2.0, 0.022, fee_l,
                                                                 drop, mode)
                        nav_r, fl_r, te_r = ref_periodic(uu, tt, lw, rate_l, acc_l, acc2_l, pe, 2.0, 0.022, fee_l, drop, mode)
                        worst = max(worst, max_rel_diff(nav_n, nav_r))
                        n_cases += 1
                        same = np.array_equal(fl_n, fl_r) and te_n == te_r
                        if fl_n.any():
                            early_seen.add((reset, mode))
                        saw_dead |= te_n >= 0
                        if low_name == "with lows" and drop > 0:
                            nav_c, fl_c, _ = k.periodic_reset_nav(uu, tt, tt, rate_l, acc_l, acc2_l, pe, 2.0, 0.022, fee_l,
                                                                  drop, mode)
                            low_moved |= not np.array_equal(fl_c, fl_n)
                        if not same:
                            check(f"kernel vs Python loop: flags and termination agree ({trig_name}, {low_name}, {reset}, "
                                  f"drop {drop}, mode {mode})", False,
                                  f"flags {fl_n.sum()} vs {fl_r.sum()}, terminated {te_n} vs {te_r}")
    nav_n, te_n = k.daily_reset_nav(uu, rate_l, acc_l, acc2_l, 2.0, 0.022, fee_l)
    nav_r, te_r = ref_daily(uu, rate_l, acc_l, acc2_l, 2.0, 0.022, fee_l)
    worst = max(worst, max_rel_diff(nav_n, nav_r))
    n_cases += 1
    saw_dead |= te_n >= 0
    if te_n != te_r:
        check("kernel vs Python loop: daily termination agrees", False, f"{te_n} vs {te_r}")
check(f"kernel vs Python loop: {n_cases} cases (2 triggers x close-only/with lows x 3 resets x trigger on/off x 3 early "
      f"modes + daily, calm and wild paths, two day counts, a fee step) agree to 1e-12 (max rel diff {worst:.1e})",
      worst < 1e-12 and n_cases == 146)
check("kernel vs Python loop: the paths exercised an early reset for every reset type and all 3 modes, and a wipeout",
      len(early_seen) == 9 and saw_dead, f"early resets seen for {sorted(early_seen)}; wipeout {saw_dead}")
check("kernel vs Python loop: the lows changed at least one early-reset date (so the low branch was compared, not idle)",
      low_moved)

# m) early_mode "level", the base case: the fund resets intraday at exactly the trigger level (-35% = index 65).
#    Same dip as d): index 100 -> 64 -> 70.4, L = 2, zero costs, no month end inside.
#    Day 1, at the trigger moment the index is at 65:  NAV = 2 x 65/100 - 1 = 0.30.   New base: NAV 0.30 at 65.
#           rest of day 1, 65 -> 64, on the new base:  NAV = 0.30 x (2 x 64/65 - 1) = 0.30 x 63/65 = 0.290769...
#    Day 2, 70.4, same base (65):                       NAV = 0.30 x (2 x 70.4/65 - 1) = 0.30 x 75.8/65 = 0.349846...
#    (close mode, test d: 0.28 then 0.336. The level reset de-levers before the last 1% of the fall.)
lv = periodic(dip, "monthly", early_drop=0.35, early_mode="level")
check("kernel: level mode: reset at index 65 gives NAV 0.30; day 1 closes at 0.30 x 63/65 = 0.290769, "
      "day 2 (+10%) at 0.30 x 75.8/65 = 0.349846; reset dated 2024-01-03",
      abs(lv.iloc[1] - 0.30 * 63 / 65) < 1e-12 and abs(lv.iloc[2] - 0.30 * 75.8 / 65) < 1e-12
      and lv.attrs["early_resets"] == ["2024-01-03"], (lv.iloc[1], lv.iloc[2], lv.attrs["early_resets"]))
lv_default = k.periodic_reset_series(dip, 0.0, reset="monthly", L=2.0, spread_per_nav=0.0, fee=0.0, early_drop=0.35)
check("kernel: the wrapper's default early_mode is 'level' (the prospectus base case)",
      lv_default.equals(lv) and lv_default.attrs["model"]["early_mode"] == "level")

# m2) level mode on a period-end day: two resets that day. Dates 01-30, 01-31 (month end), 02-01; index 100, 64, 70.4.
#    01-31: level reset at 65 (NAV 0.30), close 64: 0.30 x 63/65 = 0.290769. It is also the month end, so the fund
#           resets again at the close: base NAV 0.290769 at 64.
#    02-01: +10% on that base: 0.290769 x (2 x 1.1 - 1) = 0.290769 x 1.2 = 0.348923
#    Only the first reset is an early one: early_resets == ["2024-01-31"]. (close mode, test g: 0.336, none listed.)
lv_end = periodic(onend, "monthly", early_drop=0.35, early_mode="level")
check("kernel: level mode, trigger on a month end: level reset then period reset; final 0.30 x 63/65 x 1.2 = 0.348923, "
      "one early reset listed", abs(lv_end.iloc[1] - 0.30 * 63 / 65) < 1e-12
      and abs(lv_end.iloc[2] - 0.30 * 63 / 65 * 1.2) < 1e-12 and lv_end.attrs["early_resets"] == ["2024-01-31"],
      (lv_end.iloc[1], lv_end.iloc[2], lv_end.attrs["early_resets"]))

# m3) a -50% day. Index 100 -> 50 -> 55.
#    no trigger, close and next_close: 2 x 50/100 - 1 = 0 at the close, so the fund is finished on day 1.
#    level: reset at 65 (NAV 0.30), close 50: 0.30 x (2 x 50/65 - 1) = 0.30 x 35/65 = 0.161538...
#           day 2, 55: 0.30 x (2 x 55/65 - 1) = 0.30 x 45/65 = 0.207692...
half = pd.Series([100.0, 50.0, 55.0], index=pd.bdate_range("2024-01-02", periods=3))
h_lv = periodic(half, "monthly", early_drop=0.35, early_mode="level")
h_others = [periodic(half, "monthly", early_drop=d, early_mode=m_)
            for d, m_ in ((None, "level"), (0.35, "close"), (0.35, "next_close"))]
check("kernel: a -50% day finishes the fund with no trigger and in close / next_close mode (terminated 2024-01-03)",
      all(s_.attrs["terminated"] == "2024-01-03" and s_.iloc[1] == 0 and s_.iloc[2] == 0 for s_ in h_others),
      [s_.attrs["terminated"] for s_ in h_others])
check("kernel: level mode survives the -50% day: 0.30 x 35/65 = 0.161538, then 0.30 x 45/65 = 0.207692",
      abs(h_lv.iloc[1] - 0.30 * 35 / 65) < 1e-12 and abs(h_lv.iloc[2] - 0.30 * 45 / 65) < 1e-12
      and h_lv.attrs["terminated"] is None and h_lv.attrs["early_resets"] == ["2024-01-03"],
      (h_lv.iloc[1], h_lv.iloc[2], h_lv.attrs))

# m4) a -60% day passes TWO trigger levels: 65, then 65 x 0.65 = 42.25. Index 100 -> 40 -> 44.
#    first reset at 65: NAV 0.30. 40 is 38.5% below 65, so the trigger fires again on the new base:
#    second reset at 42.25: NAV = 0.30 x (2 x 42.25/65 - 1) = 0.30 x 0.30 = 0.09
#    close 40: 0.09 x (2 x 40/42.25 - 1) = 0.09 x 37.75/42.25 = 0.080414...
#    day 2, 44: 0.09 x (2 x 44/42.25 - 1) = 0.09 x 45.75/42.25 = 0.097456...
#    The day is listed once in early_resets.
sixty = pd.Series([100.0, 40.0, 44.0], index=pd.bdate_range("2024-01-02", periods=3))
s_lv = periodic(sixty, "monthly", early_drop=0.35, early_mode="level")
check("kernel: level mode, -60% in a day: two resets (65 then 42.25), NAV 0.09 x 37.75/42.25 = 0.080414, "
      "then 0.09 x 45.75/42.25 = 0.097456",
      abs(s_lv.iloc[1] - 0.09 * 37.75 / 42.25) < 1e-12 and abs(s_lv.iloc[2] - 0.09 * 45.75 / 42.25) < 1e-12
      and s_lv.attrs["early_resets"] == ["2024-01-03"], (s_lv.iloc[1], s_lv.iloc[2], s_lv.attrs["early_resets"]))

# m5) level mode with costs: the day's carry and fee are charged BEFORE the trigger, then start again from 0.
#    Dip 100 -> 64 -> 70.4 on Tue/Wed/Thu, so each step is one day: the financing accrues 1/360 (ACT/360) and the
#    fee 1/365. Rate 5%, spread_per_nav 2.2%, fee 1%.
#    Day 1: carry = ((2-1) x 5% + 2.2%) x 1/360 = 0.072/360 per unit of NAV0 (= 1); fees = 1% x NAV(day 0) / 365
#           NAV_hit = 1 x (2 x 0.65 - 1) - 0.072/360 - 0.01/365                    (= 0.29977260...)
#           close:  NAV1 = NAV_hit x (2 x 64/65 - 1)                                  (carry and fees are 0 again)
#    Day 2: carry = 0.072/360 on the new base; fees = 1% x NAV1 / 365
#           NAV2 = NAV_hit x (2 x 70.4/65 - 1) - NAV_hit x 0.072/360 - 0.01 x NAV1 / 365
c_lv = periodic(dip, "monthly", rate=0.05, spread_per_nav=0.022, fee=0.01, early_drop=0.35, early_mode="level")
nav_hit = (2 * 0.65 - 1) - 0.072 / 360 - 0.01 / 365
nav1 = nav_hit * (2 * 64 / 65 - 1)
nav2 = nav_hit * (2 * 70.4 / 65 - 1) - nav_hit * 0.072 / 360 - 0.01 * nav1 / 365
check(f"kernel: level mode with costs: carry and fee charged before the trigger (NAV at the trigger {nav_hit:.8f}), "
      f"then restarted from 0 on the new base: {nav1:.8f}, {nav2:.8f}",
      abs(c_lv.iloc[1] - nav1) < 1e-12 and abs(c_lv.iloc[2] - nav2) < 1e-12, (c_lv.iloc[1], c_lv.iloc[2]))

# n) a separate trigger series. The prospectus trigger watches the PRICE of SPY / QQQ; a total-return (TR) run
#    marks NAV on the TR level. NAV must move with u; only the trigger test uses the trigger series.
#    n1) close mode. Price P: 100, 64.5, 70.95.  TR U = P x 1.01 after day 0: 100, 65.145, 71.6595.
#        The price is down 35.5% on day 1 (trigger); the TR only 34.855% (it would not trigger on its own).
#        trigger = P: reset at day 1's close on U: NAV1 = 2 x 0.65145 - 1 = 0.3029
#                     day 2 (U +10%): 0.3029 x (2 x 1.1 - 1) = 0.3029 x 1.2 = 0.36348
#        trigger = U (the default): no reset; day 2: 2 x 0.716595 - 1 = 0.43319
nd = pd.bdate_range("2024-01-02", periods=3)
px_n = pd.Series([100.0, 64.5, 70.95], index=nd, name="PRICE")
tr_n = pd.Series([100.0, 65.145, 71.6595], index=nd, name="TR")
n_p = periodic(tr_n, "monthly", early_drop=0.35, early_mode="close", trigger=px_n)
n_u = periodic(tr_n, "monthly", early_drop=0.35, early_mode="close")
check("kernel: close mode, trigger on the price: resets on the price's -35.5% (NAV 0.3029 on the TR), "
      "then 0.3029 x 1.2 = 0.36348",
      abs(n_p.iloc[1] - 0.3029) < 1e-12 and abs(n_p.iloc[2] - 0.36348) < 1e-12 and n_p.attrs["early_resets"] == ["2024-01-03"]
      and n_p.attrs["model"]["trigger"] == "PRICE", (n_p.iloc[1], n_p.iloc[2], n_p.attrs))
check("kernel: the same TR with the default trigger (the TR itself, -34.855%) does not reset: final 0.43319",
      abs(n_u.iloc[2] - 0.43319) < 1e-12 and n_u.attrs["early_resets"] == [] and n_u.attrs["model"]["trigger"] == "underlying",
      (n_u.iloc[2], n_u.attrs))
#    n2) level mode, with dividends earned between the last reset and the trigger day.
#        Price P: 100, 90, 64.5.  TR U: 100, 91, 64.5 x 91/90 = 65.2167 (by day 1 the TR is 91/90 ahead of the price).
#        Day 1: -10%, no trigger: NAV1 = 2 x 0.91 - 1 = 0.82.
#        Day 2: the price passes 65 (-35%). The TR moved in step with the price since day 1's close, so at that
#               moment it is 65 x 91/90 = 65.7222: NAV_hit = 2 x 0.657222 - 1 = 0.314444; new TR base 65.7222.
#               close: U / base = 64.5/65, so NAV2 = 0.314444 x (2 x 64.5/65 - 1) = 0.314444 x 64/65 = 0.309607
#        (Taking the TR at the trigger as U0 x 0.65 = 65 would give 0.30 x (2 x 65.2167/65 - 1) = 0.302: it would
#        drop the 1.1% of dividends earned since the reset.)
px_2 = pd.Series([100.0, 90.0, 64.5], index=nd, name="PRICE")
tr_2 = pd.Series([100.0, 91.0, 64.5 * 91 / 90], index=nd, name="TR")
n2 = periodic(tr_2, "monthly", early_drop=0.35, early_mode="level", trigger=px_2)
n2_hit = 2 * (65 * 91 / 90) / 100 - 1
check(f"kernel: level mode, price trigger on a TR run: NAV at the trigger {n2_hit:.6f} (the TR keeps its dividends), "
      f"close {n2_hit * 64 / 65:.6f}",
      abs(n2.iloc[1] - 0.82) < 1e-12 and abs(n2.iloc[2] - n2_hit * 64 / 65) < 1e-12
      and n2.attrs["early_resets"] == ["2024-01-04"], (n2.iloc[1], n2.iloc[2], n2.attrs["early_resets"]))

# o) row 0 is a reset (DESIGN 8). A run on the underlying sliced from a period end (a reset date) equals the
#    full-history run read as a ratio, nav[t] / nav[s]; a slice starting mid-quarter does not, because it resets on
#    its first row and the real fund does not. With costs, the trigger on, and early resets inside the slice.
u_o = wild.iloc[:2500]                                   # before the -55% crash, so nothing terminates
r_o = pd.Series(rate_l[:2500], index=u_o.index)
ends_o = np.flatnonzero(cal.period_end_flags(u_o.index, "quarterly"))
s_end = int(ends_o[ends_o < 900][-1])                   # the last quarter end before the three -15% days
s_mid = s_end + 30                                      # ~halfway through the next quarter
o_cost = dict(rate=r_o, spread_per_nav=0.022, fee=0.0103, early_drop=0.35)
o_worst, o_resets = 0.0, {}
s_end_iso = str(u_o.index[s_end].date())
for mode in ("level", "close", "next_close"):
    full = periodic(u_o, "quarterly", early_mode=mode, **o_cost)
    cut = periodic(u_o.iloc[s_end:], "quarterly", early_mode=mode, **{**o_cost, "rate": r_o.iloc[s_end:]})
    o_worst = max(o_worst, max_rel_diff(cut.values, full.values[s_end:] / full.values[s_end]))
    after = [d_ for d_ in full.attrs["early_resets"] if d_ > s_end_iso]          # early resets after the slice start
    o_resets[mode] = (cut.attrs["early_resets"], after)
check(f"row 0: slicing the underlying from a quarter end ({s_end_iso}) reproduces nav[t]/nav[s] of the full run in "
      f"all 3 modes (max rel diff {o_worst:.1e}, limit 1e-12), with the same early resets (at least one in each)",
      o_worst < 1e-12 and all(c_ == a_ and len(c_) > 0 for c_, a_ in o_resets.values()), o_resets)
full_l = periodic(u_o, "quarterly", **o_cost)
mid = periodic(u_o.iloc[s_mid:], "quarterly", **{**o_cost, "rate": r_o.iloc[s_mid:]})
gap_mid = abs(mid.iloc[-1] / (full_l.iloc[-1] / full_l.iloc[s_mid]) - 1)
check(f"row 0: a slice from mid-quarter ({u_o.index[s_mid].date()}) does NOT reproduce it "
      f"(final value off by {gap_mid:.2%}): read multi-start results as ratios of the full run",
      not cal.period_end_flags(u_o.index, "quarterly")[s_mid] and gap_mid > 1e-3, gap_mid)
full_d = daily(u_o, rate=r_o, spread_per_nav=0.022, fee=0.0103)
cut_d = daily(u_o.iloc[s_mid:], rate=r_o.iloc[s_mid:], spread_per_nav=0.022, fee=0.0103)
d_diff = max_rel_diff(cut_d.values, full_d.values[s_mid:] / full_d.values[s_mid])
check(f"row 0: the daily twin resets every close, so even a mid-quarter slice reproduces its ratios "
      f"(max rel diff {d_diff:.1e})", d_diff < 1e-12)

# -----------------------------------------------------------------------------------------------------------------
# 2b. R2 E1: the buy-once margin position compounds its loan (kernel.margin_position_nav)
# -----------------------------------------------------------------------------------------------------------------
s24 = pd.DatetimeIndex(nyse.sessions(dt.date(2023, 12, 29), dt.date(2024, 12, 31)))
flat24 = pd.Series(100.0, index=s24)
af24, ae24, z24 = arrays(s24)
# (a) constant 5% rate, no spread or fee, flat index: the loan is (L-1) x prod(1 + 0.05 x g/360) over the day gaps g,
#     so equity = L - (L-1) x prod(1 + 0.05 x a_fin). Checked for L = 2 and L = 3.
for L_ in (2.0, 3.0):
    mg_a, _ = k.margin_position_nav(flat24.values.copy(), np.full(len(s24), 0.05), af24, ae24, L_, 0.0, z24)
    want_a = L_ - (L_ - 1.0) * np.cumprod(1.0 + 0.05 * af24)
    check(f"margin (E1 a): flat index, 5%, L={L_:g}: equity = L - (L-1) x prod(1 + 0.05 x days/360) on every row (1e-12); "
          f"after 2024 {mg_a[-1]:.6f}", np.abs(mg_a - want_a).max() < 1e-12, np.abs(mg_a - want_a).max())
# (b) one calendar quarter, 2024-03-28 (Q1's last session) to 2024-06-28 (Q2's): 92 days. Simple interest on the loan
#     of 1: 0.05 x 92/360 = 1.27778%. Compounded daily over the 63 day steps: prod(1 + 0.05 g/360) - 1, larger by the
#     interest on interest, about (sum x)^2/2 - sum x^2/2 = (0.0127778)^2/2 - 1.6e-6 = 8.0e-5 of NAV. So over a
#     QUARTER at 5% the two conventions differ by 8.0e-5 of NAV, not by less than 2e-5 (the R2 brief) or 1e-5 (the R1
#     memo). Over a MONTH (2024-05-31 to 2024-06-28, 28 days: x = 0.003889, x^2/2 = 7.6e-6, less the same kind of
#     small correction: 7.0e-6) it is below 2e-5. The
#     calendar kernel keeps simple interest inside a period because that is the swap's convention (the financing leg
#     accrues on the reset notional and settles at the reset), not because the gap is negligible.
q2 = s24[(s24 >= "2024-03-28") & (s24 <= "2024-06-28")]
gaps = {}
for label_, ix_ in (("quarter", q2), ("month", s24[(s24 >= "2024-05-31") & (s24 <= "2024-06-28")])):
    uu_, n_ = np.full(len(ix_), 100.0), len(ix_)
    af_, ae_, z_ = arrays(ix_)
    simple_, _, _ = k.periodic_reset_nav(uu_, uu_, uu_, np.full(n_, 0.05), af_, ae_, np.zeros(n_, dtype=np.bool_), 2.0, 0.0,
                                         z_, 0.0, k.EARLY_LEVEL)
    comp_, _ = k.margin_position_nav(uu_, np.full(n_, 0.05), af_, ae_, 2.0, 0.0, z_)
    exact_ = np.prod(1.0 + 0.05 * af_) - 1.0 - 0.05 * af_.sum()      # the interest on interest, in NAV units
    gaps[label_] = (simple_[-1] - comp_[-1], exact_)
check(f"margin (E1 b): over Q2 2024 at 5% simple minus compounded = the interest on interest (to rounding, 1e-14): "
      f"{gaps['quarter'][0]:.2e} of NAV (about 8.0e-5; below 1e-4); over one month {gaps['month'][0]:.2e} (below 2e-5)",
      abs(gaps["quarter"][0] - gaps["quarter"][1]) < 1e-14 and abs(gaps["month"][0] - gaps["month"][1]) < 1e-14
      and 7.5e-5 < gaps["quarter"][0] < 1e-4 and 0 < gaps["month"][0] < 2e-5, gaps)
# (c) zero costs: equity = 1 + L x (u_t/u_0 - 1) EXACTLY (==), not just to rounding. Why exact: the kernel computes
#     2 x u_t/u_0 - 1 and 2 x (a/b) is exact in binary floating point; with u_t/u_0 between 0.5 and 2, x - 1 is exact
#     too (Sterbenz), so both expressions round the same number 2x - 1 once.
u_c = walk("2015-01-02", 400, seed=8, vol=0.01)
x_c = u_c.values / u_c.values[0]
mg_c = periodic(u_c, "never")
check("margin (E1 c): zero costs, the margin position equals 1 + 2 x (u_t/u_0 - 1) exactly on every row "
      f"(u_t/u_0 stays in [{x_c.min():.2f}, {x_c.max():.2f}])",
      x_c.min() >= 0.5 and x_c.max() <= 2.0 and np.array_equal(mg_c.values, 1.0 + 2.0 * (x_c - 1.0)))
# (d) a planted 10-year window: every calendar day from 2015-01-01 to 2025-01-01 (3654 rows, 3653 one-day steps), the
#     index flat at 100 and 300 on the last day, constant 5%, L = 2, no spread or fee:
#       loan = (1 + 0.05/360)^3653 = exp(3653 x ln(1.000138889)) = exp(0.507326) = 1.660844
#       equity = 2 x 3 - 1.660844 = 4.339156      (simple interest would give 6 - (1 + 0.05 x 3653/360) = 4.492639)
#     With a 1% spread (borrowed, so it compounds too): loan = (1+i)^N + (0.01/360) x ((1+i)^N - 1)/i, i = 0.05/360
#       = 1.660844 + 0.2 x 0.660844 = 1.793013, equity = 4.206987.
d10 = pd.date_range("2015-01-01", "2025-01-01", freq="D")
u10 = pd.Series(100.0, index=d10)
u10.iloc[-1] = 300.0
m10 = periodic(u10, "never", rate=0.05)
m10s = periodic(u10, "never", rate=0.05, spread_per_nav=0.01)
check(f"margin (E1 d): 10 years at 5% on a loan of 1: equity 6 - (1 + 0.05/360)^3653 = 4.339156 (got {m10.iloc[-1]:.6f}); "
      "simple interest would say 4.492639",
      len(d10) == 3654 and abs(m10.iloc[-1] - (6.0 - (1.0 + 0.05 / 360) ** 3653)) < 1e-12 and abs(m10.iloc[-1] - 4.339156) < 1e-6)
check(f"margin (E1 d): with a borrowed 1% spread the loan is 1.660844 + 0.2 x 0.660844 = 1.793013, equity 4.206987 "
      f"(got {m10s.iloc[-1]:.6f})", abs(m10s.iloc[-1] - 4.206987) < 1e-6, m10s.iloc[-1])
check("margin (E1): the wrapper labels it a buy-once margin position with a compounding loan",
      m10.attrs["model"]["structure"] == "buy_once_margin" and "compounds" in m10.attrs["model"]["interest"]
      and m10.attrs["terminated"] is None and m10.name == "synthetic_2x_never")

# -----------------------------------------------------------------------------------------------------------------
# 2c. R2 E4: the -35% trigger on the day's LOW (BACKLOG B4)
# -----------------------------------------------------------------------------------------------------------------
# Index closes 100, 70, 72 with lows 100, 64, 70: on day 1 the low is 36% below the base (breach), the close only 30%.
#   level:      reset at 65 (NAV 2 x 0.65 - 1 = 0.30); day 1 marked at 0.30 x (2 x 70/65 - 1) = 0.30 x 75/65 = 0.346154;
#               day 2: 0.30 x (2 x 72/65 - 1) = 0.30 x 79/65 = 0.364615
#   close:      reset at day 1's close 70: NAV 2 x 0.70 - 1 = 0.40; day 2: 0.40 x (2 x 72/70 - 1) = 0.40 x 74/70 = 0.422857
#   next_close: day 1 0.40 (no reset yet); day 2 2 x 0.72 - 1 = 0.44, reset at that close (dated day 2)
#   close-only (no trigger_low): no reset at all; day 1 0.40, day 2 0.44
d3 = pd.bdate_range("2024-01-02", periods=3)
c3 = pd.Series([100.0, 70.0, 72.0], index=d3, name="PX")
l3 = pd.Series([100.0, 64.0, 70.0], index=d3, name="PX_low")
e4 = {m_: periodic(c3, "monthly", early_drop=0.35, early_mode=m_, trigger_low=l3) for m_ in ("level", "close", "next_close")}
e4_none = periodic(c3, "monthly", early_drop=0.35)
check("low trigger, level: the low (64) breaches -35%: reset at 65 (NAV 0.30), day 1 at 0.30 x 75/65 = 0.346154, "
      "day 2 at 0.30 x 79/65 = 0.364615",
      abs(e4["level"].iloc[1] - 0.30 * 75 / 65) < 1e-12 and abs(e4["level"].iloc[2] - 0.30 * 79 / 65) < 1e-12
      and e4["level"].attrs["early_resets"] == ["2024-01-03"], (e4["level"].iloc[1], e4["level"].iloc[2]))
check("low trigger, close: resets at day 1's close 70 with NAV 0.40; day 2 at 0.40 x 74/70 = 0.422857",
      abs(e4["close"].iloc[1] - 0.40) < 1e-12 and abs(e4["close"].iloc[2] - 0.40 * 74 / 70) < 1e-12
      and e4["close"].attrs["early_resets"] == ["2024-01-03"], (e4["close"].iloc[1], e4["close"].iloc[2]))
check("low trigger, next_close: no reset on day 1 (0.40), reset at day 2's close (0.44), dated 2024-01-04",
      abs(e4["next_close"].iloc[1] - 0.40) < 1e-12 and abs(e4["next_close"].iloc[2] - 0.44) < 1e-12
      and e4["next_close"].attrs["early_resets"] == ["2024-01-04"])
check("low trigger: the close-only run of the same path does not reset at all (-30% at the close): 0.40, 0.44",
      abs(e4_none.iloc[1] - 0.40) < 1e-12 and abs(e4_none.iloc[2] - 0.44) < 1e-12 and e4_none.attrs["early_resets"] == [])
# A low through TWO levels while the close is back above the second: closes 100, 50, 55; lows 100, 40, 50.
#   level: reset at 65 (0.30), the low 40 is also below 65 x 0.65 = 42.25: reset at 42.25, NAV 0.30 x (2 x 42.25/65 - 1)
#          = 0.30 x 0.30 = 0.09; the close 50 is marked on that base: 0.09 x (2 x 50/42.25 - 1) = 0.09 x 57.75/42.25
#          = 0.123018; day 2 (55): 0.09 x 67.75/42.25 = 0.144320
#   the close-only level run resets once (50 is not below 42.25): 0.30 x (2 x 50/65 - 1) = 0.30 x 35/65 = 0.161538
c2l = pd.Series([100.0, 50.0, 55.0], index=d3)
l2l = pd.Series([100.0, 40.0, 50.0], index=d3)
two_lv = periodic(c2l, "monthly", early_drop=0.35, trigger_low=l2l)
check("low trigger, level: a low through two levels resets twice (65, 42.25) and marks the close 50 on the last base: "
      "0.09 x 57.75/42.25 = 0.123018, then 0.09 x 67.75/42.25 = 0.144320",
      abs(two_lv.iloc[1] - 0.09 * 57.75 / 42.25) < 1e-12 and abs(two_lv.iloc[2] - 0.09 * 67.75 / 42.25) < 1e-12
      and two_lv.attrs["early_resets"] == ["2024-01-03"], (two_lv.iloc[1], two_lv.iloc[2]))
check("low trigger: without the low the same path resets once: 0.30 x 35/65 = 0.161538",
      abs(periodic(c2l, "monthly", early_drop=0.35).iloc[1] - 0.30 * 35 / 65) < 1e-12)
# The low passes the level and the close ends ABOVE the old base: closes 100, 101, 102; lows 100, 60, 101. The fund
# de-levers at 65 (NAV 0.30) and rides the rebound on the new base: day 1 0.30 x (2 x 101/65 - 1) = 0.30 x 137/65
# = 0.632308; day 2 0.30 x (2 x 102/65 - 1) = 0.30 x 139/65 = 0.641538 (close-only: 1.02, 1.04).
reb = periodic(pd.Series([100.0, 101.0, 102.0], index=d3), "monthly", early_drop=0.35,
               trigger_low=pd.Series([100.0, 60.0, 101.0], index=d3))
check("low trigger, level: a touch of -40% that closes at +1% still resets (0.30) and rides the rebound on the new base: "
      "0.30 x 137/65 = 0.632308, then 0.30 x 139/65 = 0.641538",
      abs(reb.iloc[1] - 0.30 * 137 / 65) < 1e-12 and abs(reb.iloc[2] - 0.30 * 139 / 65) < 1e-12, (reb.iloc[1], reb.iloc[2]))
# Placeholder bars: low == close everywhere gives the close-only run bit for bit, in every mode, on the wild path
# (which has early resets and a wipe-out).
ph_same = all(np.array_equal(periodic(wild, r_, early_drop=0.35, early_mode=m_, rate=0.03, spread_per_nav=0.022,
                                      fee=0.0103, trigger_low=wild).values,
                             periodic(wild, r_, early_drop=0.35, early_mode=m_, rate=0.03, spread_per_nav=0.022,
                                      fee=0.0103).values)
              for r_ in cal.RESETS for m_ in ("level", "close", "next_close"))
ph = periodic(wild, "quarterly", early_drop=0.35, trigger_low=wild).attrs["trigger_low"]
check("low trigger: placeholder lows (low == close on every row) reproduce the close-only run exactly in all 9 "
      "reset x mode cases; attrs say no real low was used and count every row as a placeholder",
      ph_same and ph["first_real_low"] is None and ph["placeholder_rows"] == len(wild))
mixed_low = pd.Series(np.where(np.arange(len(wild)) < 500, wild.values, wild.values * 0.99), index=wild.index)
mx = periodic(wild, "quarterly", early_drop=0.35, trigger_low=mixed_low).attrs
check("low trigger: attrs record the first date with a real low (row 500) and the placeholder count (500)",
      mx["trigger_low"]["first_real_low"] == str(wild.index[500].date()) and mx["trigger_low"]["placeholder_rows"] == 500
      and mx["model"]["trigger_low"] == "unnamed low series")
raises("low trigger: a low above the close is impossible data and is refused",
       lambda: periodic(c3, "monthly", early_drop=0.35, trigger_low=c3 * 1.01), "above the trigger close")
raises("low trigger: a low on another index is refused",
       lambda: periodic(c3, "monthly", early_drop=0.35, trigger_low=l3.iloc[1:]), "same index")
mq_spec = products.PRODUCTS["MQQQ"]
check("low trigger: kernel.run passes trigger_low through (MQQQ via its spec equals the bare wrapper, bit for bit)",
      np.array_equal(k.run(mq_spec, c3, 0.0, trigger_low=l3).values,
                     k.periodic_reset_series(c3, 0.0, reset="monthly", L=2.0, spread_per_nav=costs.spread_per_nav(mq_spec.costs),
                                             fee=mq_spec.fee, early_drop=0.35, trigger_low=l3).values))
raises("low trigger: kernel.run refuses a trigger_low for a daily product (no trigger to read it)",
       lambda: k.run(products.twin_of(mq_spec), c3, 0.0, trigger_low=l3), "no trigger")

# =================================================================================================================
# 3. wrappers: input checks and labels
# =================================================================================================================
m = periodic(idx, "monthly", rate=0.04, spread_per_nav=0.022, fee=0.0103, early_drop=0.35, early_mode="next_close")
check("wrapper: name and attrs (model parameters, early mode, trigger, early resets, terminated)",
      m.name == "synthetic_2x_monthly" and daily(idx).name == "synthetic_2x_daily"
      and m.attrs["model"]["early_drop"] == 0.35 and m.attrs["model"]["early_mode"] == "next_close"
      and m.attrs["model"]["trigger"] == "underlying" and "early_delay" not in m.attrs["model"]
      and m.attrs["model"]["fee"] == 0.0103 and m.attrs["model"]["spread_per_nav"] == 0.022
      and m.attrs["early_resets"] == [] and m.attrs["terminated"] is None)
gap_ix = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-12", "2024-01-15"])          # a 9-day hole
gap_u = pd.Series([100.0, 101.0, 102.0, 103.0], index=gap_ix)
raises("wrapper: a gap over 7 days raises (a missing row could hide a period end)",
       lambda: periodic(gap_u, "monthly"), "gap of 9 days (first at 2024-01-12)")
raises("wrapper: the daily wrapper refuses the same gap", lambda: daily(gap_u), "gap of 9 days")
check("wrapper: allow_gaps=True accepts it",
      len(k.periodic_reset_series(gap_u, 0.0, reset="monthly", L=2.0, spread_per_nav=0.0, fee=0.0, early_drop=None,
                                  allow_gaps=True)) == 4)
raises("wrapper: rate on a different index raises",
       lambda: periodic(two, "monthly", rate=pd.Series(0.01, index=two.index + pd.Timedelta(days=1))), "same index")
nan_mid = pd.Series([0.01, np.nan, 0.01], index=two.index)
raises("wrapper: a missing rate after the first row raises", lambda: periodic(two, "monthly", rate=nan_mid), "not finite")
lagged = pd.Series([np.nan, 0.05, 0.05], index=two.index)                       # what a one-row lag leaves
check("wrapper: NaN on the first rate row (unused: nothing accrues on day one) is accepted",
      periodic(two, "monthly", rate=lagged).iloc[-1] == periodic(two, "monthly", rate=pd.Series(0.05, index=two.index)).iloc[-1])
raises("wrapper: a rate in percent (5.0) raises", lambda: periodic(two, "monthly", rate=5.0), "percentage")
raises("wrapper: L below 1 raises", lambda: periodic(two, "monthly", L=0.5), "below the minimum")
raises("wrapper: reset 'daily' is refused by the calendar wrapper", lambda: periodic(two, "daily"), "reset must be")
raises("wrapper: a non-positive level raises",
       lambda: periodic(pd.Series([100.0, 0.0, 1.0], index=two.index), "monthly"), "finite and positive")
raises("wrapper: an unknown early_mode raises", lambda: periodic(two, "monthly", early_drop=0.35, early_mode="intraday"),
       "early_mode must be one of")
raises("wrapper: early_mode as a kernel number (0) is refused: the wrapper takes the name",
       lambda: periodic(two, "monthly", early_drop=0.35, early_mode=0), "early_mode must be one of")
raises("wrapper: the old early_delay argument is gone (a stale call fails instead of silently changing meaning)",
       lambda: k.periodic_reset_series(two, 0.0, reset="monthly", L=2.0, spread_per_nav=0.0, fee=0.0, early_drop=0.35,
                                       early_delay=0), "early_delay")
raises("wrapper: a trigger on a different index raises",
       lambda: periodic(two, "monthly", early_drop=0.35, trigger=pd.Series(100.0, index=two.index + pd.Timedelta(days=1))),
       "same index")
raises("wrapper: a non-positive trigger level raises",
       lambda: periodic(two, "monthly", early_drop=0.35, trigger=pd.Series([100.0, 0.0, 1.0], index=two.index)),
       "finite and positive")
raises("wrapper: a trigger that is a bare array (no dates to align) raises",
       lambda: periodic(two, "monthly", early_drop=0.35, trigger=two.values), "pandas Series")
pe_two = cal.period_end_flags(two.index, "monthly")
z3 = np.zeros(3)
raises("kernel: an early_mode code other than 0/1/2 raises",
       lambda: k.periodic_reset_nav(two.values.copy(), two.values.copy(), two.values.copy(), z3, z3, z3, pe_two,
                                    2.0, 0.0, z3, 0.35, 3), "early_mode")
raises("kernel: a trigger array of the wrong length raises",
       lambda: k.periodic_reset_nav(two.values.copy(), two.values[:2].copy(), two.values.copy(), z3, z3, z3, pe_two,
                                    2.0, 0.0, z3, 0.35, k.EARLY_LEVEL), "trig")
raises("kernel: a trigger-low array of the wrong length raises",
       lambda: k.periodic_reset_nav(two.values.copy(), two.values.copy(), two.values[:2].copy(), z3, z3, z3, pe_two,
                                    2.0, 0.0, z3, 0.35, k.EARLY_LEVEL), "trig_low")
raises("kernel: a fee array of the wrong length raises (the kernels take one fee per row)",
       lambda: k.periodic_reset_nav(two.values.copy(), two.values.copy(), two.values.copy(), z3, z3, z3, pe_two,
                                    2.0, 0.0, np.zeros(2), 0.35, k.EARLY_LEVEL), "fee")
raises("wrapper: a missing fee raises (no silent default)", lambda: periodic(two, "monthly", fee=None), "must be a number")
raises("wrapper: dates out of order raise", lambda: periodic(two.iloc[::-1], "monthly"), "strictly increasing")
raises("wrapper: early_drop is required (cannot be switched off by forgetting it)",
       lambda: k.periodic_reset_series(two, 0.0, reset="monthly", L=2.0, spread_per_nav=0.0, fee=0.0), "early_drop")

# =================================================================================================================
# 4. costs.py and products.py
# =================================================================================================================
base = products.PRODUCTS["MQQQ"].costs
check("costs: spread_per_nav = 1.1% x 2 turns = 2.2% of NAV", abs(costs.spread_per_nav(base) - 0.022) < 1e-15)
check("costs: base spread 1.1% ASSUMED, sensitivity 0.8% / 1.4%",
      costs.SPREAD_BASE == 0.011 and costs.SPREAD_BASE_STATUS == "ASSUMED" and costs.SPREAD_SENSITIVITY == (0.008, 0.014))
open_spread = replace(base, spread=None, spread_status="OPEN", spread_source="not published")
raises("costs: an OPEN spread must be supplied before use", lambda: costs.spread_per_nav(open_spread), "OPEN")
raises("costs: an OPEN fee must be supplied before use",
       lambda: costs.annual_fee(replace(base, fee=None, fee_status="OPEN", fee_source="unknown")), "OPEN")
raises("costs: a value with status OPEN is contradictory", lambda: replace(base, spread_status="OPEN"), "must be None")
raises("costs: no value but status ASSUMED is refused", lambda: replace(base, spread=None), "use status OPEN")
raises("costs: a status without a source date/name is refused", lambda: replace(base, fee_status="VERIFIED"), "status must be")
raises("costs: a fee in percent (1.0) is refused", lambda: replace(base, fee=1.0), "percentage")
raises("costs: an empty source is refused", lambda: replace(base, spread_source=" "), "give a source")
b = costs.banner(base, replace(base, spread=0.008, label="MQQQ low spread"))
check("costs: banner shows statuses, the spread sensitivity and warns about the ASSUMED spread",
      "VERIFIED_prospectus_2026-07-31" in b and "SPREAD SENSITIVITY" in b and "0.80%" in b and "1.40%" in b
      and "WARNING: MQQQ: spread 0.011 is ASSUMED" in b and "MQQQ low spread" in b, b)

P = products.PRODUCTS
want = {"SPYQ": ("LIVE", "SPX", "quarterly", 0.0100), "MQQQ": ("LIVE", "NDX", "monthly", 0.0103),
        "QQQP": ("LIVE", "NDX", "quarterly", 0.0100), "HYP_SPX_M": ("MODELED", "SPX", "monthly", 0.0100),
        "HYP_SPX_W": ("MODELED", "SPX", "weekly", 0.0100), "HYP_NDX_W": ("MODELED", "NDX", "weekly", 0.0100),
        "TWIN_SPX_D": ("DAILY_TWIN", "SPX", "daily", 0.0100), "TWIN_NDX_D": ("DAILY_TWIN", "NDX", "daily", 0.0100)}
got = {n: (p.kind, p.underlying, p.reset, p.fee) for n, p in P.items()}
check("products: registry holds the 8 products with the right kind, underlying, reset and fee", got == want, got)
check("products: live fees VERIFIED from the prospectus with page numbers, inception dates set",
      all(P[n].costs.fee_status == "VERIFIED_prospectus_2026-07-31" and "p." in P[n].costs.fee_source for n in ("SPYQ", "MQQQ", "QQQP"))
      and (P["SPYQ"].inception, P["MQQQ"].inception, P["QQQP"].inception) == ("2024-09-30", "2024-08-30", "2024-09-30"))
check("products: modeled and twin fees are ASSUMED",
      all(P[n].costs.fee_status == "ASSUMED" for n in P if P[n].kind != "LIVE"))
check("products: KINDS has MODELED and no longer HYPOTHETICAL (R2 step 2: the weekly and SPY-monthly designs traded 2024-25)",
      "MODELED" in products.KINDS and "HYPOTHETICAL" not in products.KINDS)
check("products: each MODELED design names its liquidated live counterpart and the filing (SPYM / SPYB / QQQW, 2024-08-30 to 2025-02-28)",
      all(t in P[n].note and "2024-08-30 to 2025-02-28" in P[n].note and "semi-annual" in P[n].note
          for n, t in (("HYP_SPX_M", "SPYM"), ("HYP_SPX_W", "SPYB"), ("HYP_NDX_W", "QQQW"))),
      [P[n].note for n in ("HYP_SPX_M", "HYP_SPX_W", "HYP_NDX_W")])
check("products: every calendar product has the 35% trigger (VERIFIED for live, ASSUMED for modeled); twins none",
      all(p.early_drop == 0.35 for p in P.values() if p.reset != "daily")
      and all(p.early_drop is None for p in P.values() if p.reset == "daily")
      and all(P[n].early_drop_status.startswith("VERIFIED") for n in ("SPYQ", "MQQQ", "QQQP"))
      and all(P[n].early_drop_status == "ASSUMED" for n in ("HYP_SPX_M", "HYP_SPX_W", "HYP_NDX_W")))
check("products: twins use the same spread, turns and rate as the calendar funds (reset rule is the only difference)",
      len({(p.costs.spread, p.costs.turns, p.costs.rate_name, p.costs.spread_status) for p in P.values()}) == 1)
bh, bt, bl = products.banner(P["HYP_SPX_W"]), products.banner(P["TWIN_NDX_D"]), products.banner(P["MQQQ"])
check("products: banner labels MODELED (with the live record) and DAILY TWIN, and never labels a live fund either way",
      "MODELED: a live fund of this design traded 2024-08-30 to 2025-02-28; no live fund exists today" in bh
      and "DAILY TWIN: synthetic comparison series" in bt
      and "MODELED" not in bl and "HYPOTHETICAL" not in bh and "DAILY TWIN" not in bl, bh + "\n" + bt + "\n" + bl)
check("products: banner states kind, reset, L, fee, spread, turns and statuses",
      all(x in bl for x in ("kind=LIVE", "reset=monthly", "L=2", "fee 1.03%", "spread 1.10%", "x 2 turns",
                            "VERIFIED_prospectus_2026-07-31", "ASSUMED", "WARNING")), bl)
raises("products: a DAILY_TWIN must reset daily", lambda: replace(P["TWIN_SPX_D"], reset="monthly",
                                                                  early_drop_status="ASSUMED"), "DAILY_TWIN")
raises("products: a daily fund cannot have an early trigger", lambda: replace(P["TWIN_SPX_D"], early_drop=0.35), "no in-period trigger")
raises("products: unknown kind raises", lambda: replace(P["MQQQ"], kind="REAL"), "kind must be")
raises("products: a LIVE product needs an inception date", lambda: replace(P["MQQQ"], inception=None), "inception")

# turns must match L (audit finding 3: a 3x fund on the 2x default would be charged 2/3 of its spread)
mq = P["MQQQ"]
raises("costs: turns has no default (it depends on L), nor do its status and source",
       lambda: costs.CostSpec(fee=0.01, fee_status="ASSUMED", fee_source="test", spread=0.011, spread_status="ASSUMED",
                              spread_source="test"), "turns")
raises("costs: turns None is refused", lambda: replace(base, turns=None), "turns must be")
raises("costs: an unknown spread_basis is refused", lambda: replace(base, spread_basis="gross"), "spread_basis")
check("costs: expected turns at L=3: notional 3, borrowed 2, swaps None (from a filing); 0 on every basis at L=1",
      (costs.expected_turns(3.0, "notional"), costs.expected_turns(3.0, "borrowed"), costs.expected_turns(3.0, "swaps"))
      == (3.0, 2.0, None) and all(costs.expected_turns(1.0, b_) == 0.0 for b_ in costs.SPREAD_BASES))
check("products: every registered product has turns = L = 2 on the notional basis (TURNS_2X)",
      all(p.costs.turns == p.L == costs.TURNS_2X == 2.0 and p.costs.spread_basis == "notional" for p in P.values()))
raises("products: a 3x spec built with 2 turns raises", lambda: replace(mq, L=3.0), "does not match L = 3")
raises("costs: check_turns refuses the 2x costs at L = 3", lambda: costs.check_turns(base, 3.0), "expected 3")
mq3 = replace(mq, L=3.0, costs=replace(mq.costs, turns=3.0))
check("products: the same spec with 3 turns is accepted and pays 1.1% x 3 = 3.3% of NAV",
      abs(costs.spread_per_nav(mq3.costs) - 0.033) < 1e-15)
one = replace(mq, L=1.0, costs=replace(mq.costs, turns=0.0))
check("products: L=1 with turns 0 is accepted and pays no spread (an unlevered fund holds the index, no swap)",
      costs.spread_per_nav(one.costs) == 0.0)
raises("products: L=1 with 2 turns raises", lambda: replace(mq, L=1.0), "expected 0")
check("costs: on the 'swaps' basis the filed turns (e.g. 2.42) are accepted at any L (no rule to check)",
      costs.check_turns(replace(base, spread_basis="swaps", turns=2.42), 3.0) is None)
check("costs: describe() states the basis next to the turns", "x 2 turns [ASSUMED, notional basis]" in costs.describe(base),
      costs.describe(base))

# twin_of (audit finding 7): the twin copies the compared fund's fee and costs
tw = products.twin_of(mq)
check("products: twin_of(MQQQ) is TWIN_MQQQ, a daily twin on NDX at L=2 with MQQQ's fee 1.03% and identical costs "
      "(only the label and the fee source's 'copied from' note differ)",
      tw.name == "TWIN_MQQQ" and tw.kind == "DAILY_TWIN" and tw.reset == "daily" and tw.underlying == "NDX"
      and tw.L == 2.0 and tw.fee == 0.0103 and tw.early_drop is None and tw.early_drop_status == "NOT_APPLICABLE"
      and tw.costs.fee_source.startswith("copied from MQQQ: ")
      and replace(tw.costs, label=mq.costs.label, fee_source=mq.costs.fee_source) == mq.costs, tw)
check("products: twin_of copies fee, spread and turns for every calendar product",
      all(products.twin_of(p).costs.fee == p.costs.fee and products.twin_of(p).costs.spread == p.costs.spread
          and costs.spread_per_nav(products.twin_of(p).costs) == costs.spread_per_nav(p.costs)
          and products.twin_of(p).underlying == p.underlying for p in P.values() if p.reset != "daily"))
low = replace(mq, costs=replace(mq.costs, spread=0.008, spread_source="sensitivity: low end of the F8 fit range"))
check("products: twin_of a sensitivity copy carries the changed spread (0.8%), so the pair always matches",
      products.twin_of(low).costs.spread == 0.008 and products.twin_of(mq3).L == 3.0
      and products.twin_of(mq3).costs.turns == 3.0)
raises("products: twin_of a daily product raises", lambda: products.twin_of(P["TWIN_SPX_D"]), "already resets daily")
check("products: banner labels the twin as a DAILY TWIN", "DAILY TWIN: synthetic comparison series" in products.banner(tw))

# =================================================================================================================
# 5. timing: 20,000 rows x 3 resets x 10 cost cases (plus the 10 daily twins), through the pandas wrappers
# =================================================================================================================
big = walk("1950-01-02", 20000, seed=5, vol=0.011)
big_rate = pd.Series(0.03 + 0.02 * np.sin(np.arange(20000) / 1000.0), index=big.index)
cases = [(s * 2, f) for s in costs.SPREAD_SENSITIVITY + (costs.SPREAD_BASE,) for f in (0.0095, 0.0100, 0.0103)]
cases.append((0.0, 0.0))                                                            # 10 cost cases
periodic(big.iloc[:50], "weekly", rate=big_rate.iloc[:50], spread_per_nav=0.022, fee=0.01, early_drop=0.35)   # warm-up
daily(big.iloc[:50], rate=big_rate.iloc[:50], spread_per_nav=0.022, fee=0.01)
t0 = time.perf_counter()
for reset in cal.RESETS:
    for spn, fee in cases:
        periodic(big, reset, rate=big_rate, spread_per_nav=spn, fee=fee, early_drop=0.35)
for spn, fee in cases:
    daily(big, rate=big_rate, spread_per_nav=spn, fee=fee)
elapsed = time.perf_counter() - t0
print(f"     timing: 30 calendar + 10 daily runs on {len(big):,} rows took {elapsed:.3f} s")
check("timing: 20,000 rows x 3 resets x 10 cost cases (+10 daily) under 1 s after warm-up", elapsed < 1.0, f"{elapsed:.3f} s")
