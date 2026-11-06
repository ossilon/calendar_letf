"""Trading-calendar helpers: which reset period each trading day belongs to, where each period ends, and how much
time each row accrues.

Terms used here
- trading day: a row in the data (a day the market was open). This module never adds a row.
- period id: a whole number that is the same for every trading day in one calendar week, month or quarter.
- period end: the day a calendar-reset fund resets its leverage, at the close. The prospectus defines it as the
  last NYSE business day of the week / month / quarter. From 1970-01-01 on `period_end_flags` takes that day from
  the exchange calendar (nyse.py) and REFUSES data that lack it, so a missing row can never move a reset. Before
  1970 (no exchange calendar here) and under calendar=None it falls back to the LAST ROW of each period, and the
  final row of the series is never flagged (we cannot know whether the period continues after the data stop).
- accrual fraction: calendar days since the previous row / days_in_year. Financing legs on US overnight-rate
  swaps (OBFR, fed funds) accrue ACT/360 (days / 360); the expense ratio accrues on a 365-day year. A Monday after
  a normal weekend accrues 3 days, so financing and fees are charged for weekends and holidays too.

    ends = period_end_flags(dates, "monthly")     # True on the last NYSE session of each month (from 1970)
    a_fin = accrual_fraction(dates, 360)          # 0 on the first row, then days / 360
    a_fee = accrual_fraction(dates)               # 0 on the first row, then days / 365
"""
import numpy as np
import pandas as pd

from . import nyse

RESETS = ("weekly", "monthly", "quarterly")

# "never": the buy-once margin benchmark (BACKLOG C7 / B3). Every row carries the same period id and no row is a
# period end, so the position is never reset. It is deliberately NOT inside RESETS: kernel.PERIODIC_RESETS and the
# kernel tests loop over RESETS (and expect every member to have period ends), so adding it there would change what
# those tests check. ALL_RESETS is the full list.
NEVER = "never"
ALL_RESETS = RESETS + (NEVER,)

CALENDARS = ("nyse", None)        # period_end_flags(calendar=...): the exchange calendar, or the old last-row rule
NYSE_FROM = pd.Timestamp(nyse.VALID_FROM)    # periods ending before this date use the last-row rule
DAY_COUNTS = (360, 365)           # accrual_fraction(days_in_year=...): ACT/360 (money market) or ACT/365

# Python numbers days with date.toordinal(), where 0001-01-01 is day 1. 1970-01-01 is day 719163.
# numpy counts days from 1970-01-01, so adding this constant converts numpy's count to Python's ordinal.
_ORDINAL_OF_1970_01_01 = 719163


def _as_dates(dates):
    """Return the dates as a DatetimeIndex of plain calendar dates, after checking they are usable.

    Time of day and time zone are dropped (a daily close is labeled by its date). The dates must be strictly
    increasing with no repeats, otherwise "the last row of a period" would have no clear meaning.
    """
    if isinstance(dates, np.ndarray) and dates.dtype.kind in "iub":
        raise ValueError("dates must be dates (a DatetimeIndex), not period ids or numbers")
    idx = pd.DatetimeIndex(dates)
    if idx.tz is not None:
        idx = idx.tz_localize(None)       # keep the local calendar date
    idx = idx.normalize()                 # midnight, i.e. just the date
    if not (idx.is_monotonic_increasing and idx.is_unique):
        raise ValueError("dates must be strictly increasing with no repeated dates")
    return idx


def _day_numbers(idx):
    """Whole days since 1970-01-01 for each date (negative before 1970)."""
    return idx.values.astype("datetime64[D]").astype(np.int64)


def period_ids(dates, reset):
    """One integer per trading day naming its reset period.

    weekly:    Python ordinal of the Monday of that date's week (a week runs Monday to Sunday, so a week that
               spans New Year is still one period)
    monthly:   year * 100 + month              (2024-01-15 -> 202401)
    quarterly: year * 10 + (month - 1) // 3    (2024-05-15 -> 20241, i.e. quarter index 1 = April-June)
    never:     0 on every row (the buy-once margin benchmark: no period ever ends)
    """
    idx = _as_dates(dates)
    if reset == "weekly":
        monday = _day_numbers(idx) - idx.dayofweek.to_numpy().astype(np.int64)   # dayofweek: Monday=0 ... Sunday=6
        return monday + _ORDINAL_OF_1970_01_01
    if reset == "monthly":
        return (idx.year * 100 + idx.month).to_numpy().astype(np.int64)
    if reset == "quarterly":
        return (idx.year * 10 + (idx.month - 1) // 3).to_numpy().astype(np.int64)
    if reset == NEVER:
        return np.zeros(len(idx), dtype=np.int64)       # one id for every row: no period ever ends
    raise ValueError(f"reset must be one of {ALL_RESETS}, got {reset!r}")


def last_row_flags(ids):
    """The old rule: True on the last ROW of each period id; the final row of the series is never flagged.

    A row is a period end when the NEXT row carries a different id. The final row has no next row, so it stays
    False. A missing row at a period end silently moves the flag to the row before the hole, which is why
    period_end_flags uses the exchange calendar from 1970 on.
    """
    ids = np.asarray(ids)
    flags = np.zeros(len(ids), dtype=np.bool_)
    if len(ids) > 1:
        flags[:-1] = ids[:-1] != ids[1:]
    return flags


def _period_bounds(idx, reset):
    """First and last CALENDAR day of each row's period, as days since 1970-01-01 (two int64 arrays)."""
    day = _day_numbers(idx)
    if reset == "weekly":
        first = day - idx.dayofweek.to_numpy().astype(np.int64)                 # the Monday
        return first, first + 6                                                  # ... to the Sunday
    month = idx.values.astype("datetime64[M]").astype(np.int64)                  # months since 1970-01
    if reset == "monthly":
        start = month
        n_months = 1
    elif reset == "quarterly":
        start = month - month % 3                    # 1970-01 is a quarter start; numpy's % is never negative
        n_months = 3
    else:
        raise ValueError(f"no period bounds for reset {reset!r}")
    first = start.astype("datetime64[M]").astype("datetime64[D]").astype(np.int64)
    last = (start + n_months).astype("datetime64[M]").astype("datetime64[D]").astype(np.int64) - 1
    return first, last


def _last_sessions(first, last):
    """For each period [first, last] (day numbers, inside the calendar's range): its last NYSE session, or -1 if
    the period holds no session at all."""
    sess = nyse.session_day_numbers()
    hi = (pd.Timestamp(nyse.VALID_TO) - pd.Timestamp("1970-01-01")).days
    if (last > hi).any():
        raise ValueError(f"dates beyond {nyse.VALID_TO}: the exchange calendar here ends there")
    pos = np.searchsorted(sess, last, side="right") - 1
    out = np.where(pos >= 0, sess[np.maximum(pos, 0)], -1)
    return np.where(out >= first, out, -1)


def expected_period_ends(dates, reset):
    """The last NYSE session of each week / month / quarter touched by `dates`, as a sorted DatetimeIndex.

    Uses the exchange calendar only (nyse.py), never the data rows: these are the days a calendar fund resets.
    Every period touched must end on or after 1970-01-01 (the calendar's first day). reset "never" has no ends.
    """
    idx = _as_dates(dates)
    if reset == NEVER:
        return pd.DatetimeIndex([])
    period_ids(idx[:1], reset)                                  # validates the name
    first, last = _period_bounds(idx, reset)
    if len(idx) and last.min() < 0:
        raise ValueError(f"a {reset} period ends before {NYSE_FROM.date()}; the exchange calendar here starts then")
    ends = np.unique(_last_sessions(first, last))
    ends = ends[ends >= 0]
    return pd.DatetimeIndex(ends.astype("datetime64[D]"))


def period_end_flags(dates, reset, *, calendar="nyse"):
    """True on the rows where a calendar fund resets (the close of the last business day of each period).

    calendar="nyse" (default): for every period that ends on or after 1970-01-01, the flag sits on the row dated
        the period's last NYSE session (expected_period_ends). If that session lies inside the data's date range
        but has no row, this RAISES, naming the date: a missing month-end row would otherwise move the reset.
        Rows that are not sessions (a holiday row in made-up data, a stale bar on a closure day) are allowed; a
        non-session row after the last session of a period is simply marked on the new base, as the real fund
        would be. The FINAL row is flagged when it is the last session of its period (the period is complete).
        Periods that end before 1970-01-01 use the last-row rule below. There the only protection against a
        missing period-end row is loader.check_missing_weekdays (a pile of missing weekdays in a year) and
        loader.check_gaps (no hole over 7 days); a single missing weekday is not caught before 1970.
    calendar=None: the old rule everywhere (last_row_flags): the last row of each period, never the final row.
        Kept for the local cross-checks against the earlier engines, which use that rule.
    reset "never" (the buy-once benchmark) has no period ends: all False.
    """
    idx = _as_dates(dates)
    ids = period_ids(idx, reset)                                # also validates the reset name
    if calendar not in CALENDARS:
        raise ValueError(f"calendar must be one of {CALENDARS}, got {calendar!r}")
    if reset == NEVER or len(idx) == 0:
        return np.zeros(len(idx), dtype=np.bool_)
    flags = last_row_flags(ids)
    if calendar is None:
        return flags
    first, last = _period_bounds(idx, reset)
    on_cal = last >= 0                                          # periods ending on or after 1970-01-01
    if not on_cal.any():
        return flags
    day = _day_numbers(idx)
    expected = _last_sessions(first[on_cal], last[on_cal])
    flags[on_cal] = day[on_cal] == expected
    # A session that should end a period, lies inside the data's range, and has no row: refuse.
    want = np.unique(expected[expected >= 0])
    inside = want[(want >= day[0]) & (want <= day[-1])]
    missing = inside[~np.isin(inside, day)]
    if missing.size:
        shown = ", ".join(str(d) for d in missing[:5].astype("datetime64[D]"))
        raise ValueError(f"{reset} period end(s) missing from the data: {shown} (the last NYSE session of the period "
                         f"has no row; {missing.size} in all). A reset there cannot be placed; fix the data, or pass "
                         "calendar=None to fall back to the last-row rule knowingly")
    return flags


WEEKDAYS = ("mon", "tue", "wed", "thu", "fri")


def anchored_period_end_flags(dates, reset, anchor):
    """Reset flags for a fund that resets on another day of its period than the last session (BACKLOG B12).

    weekly     anchor one of WEEKDAYS: the close of the last row on or before that weekday in each Monday-Sunday week
               ("fri" is the standard rule: the week's last session)
    monthly    anchor a day of the month 1-28: the close of the last row on or before that day in each month
    quarterly  anchor (k, d): the last row on or before day d of the quarter's k-th month (k = 1, 2, 3); the standard
               quarter end is not an anchor here (use period_end_flags)
    From 1970-01-01 only rows that are NYSE sessions can be reset days, as in period_end_flags: a stray row on a closure
    day (the S&P 500 data hold one on 1985-09-27, when the NYSE was shut for Hurricane Gloria) never carries a reset.
    Before 1970 every data row counts. A period whose anchor date lies after the last row is not flagged (the data stop
    before the reset); a period with no session on or before its anchor (an anchor on a holiday Monday, say) has no
    reset that period. Returns a bool array.
    """
    idx = _as_dates(dates)
    n = len(idx)
    flags = np.zeros(n, dtype=np.bool_)
    if n == 0:
        return flags
    day = _day_numbers(idx)
    if reset == "weekly":
        if anchor not in WEEKDAYS:
            raise ValueError(f"weekly anchor must be one of {WEEKDAYS}, got {anchor!r}")
        monday = day - idx.dayofweek.to_numpy().astype(np.int64)
        target = monday + WEEKDAYS.index(anchor)
        group = monday
    elif reset == "monthly":
        if not (isinstance(anchor, int) and 1 <= anchor <= 28):
            raise ValueError(f"monthly anchor must be a day 1-28, got {anchor!r}")
        month = idx.values.astype("datetime64[M]")
        target = month.astype("datetime64[D]").astype(np.int64) + (anchor - 1)
        group = month.astype(np.int64)
    elif reset == "quarterly":
        k, d = anchor if isinstance(anchor, tuple) else (None, None)
        if k not in (1, 2, 3) or not (isinstance(d, int) and 1 <= d <= 28):
            raise ValueError(f"quarterly anchor must be (month 1-3, day 1-28), got {anchor!r}")
        month = idx.values.astype("datetime64[M]").astype(np.int64)
        qstart = month - month % 3
        target = (qstart + (k - 1)).astype("datetime64[M]").astype("datetime64[D]").astype(np.int64) + (d - 1)
        group = qstart
    else:
        raise ValueError(f"reset must be one of {RESETS}, got {reset!r}")
    session = (day < 0) | np.isin(day, nyse.session_day_numbers())         # rows before 1970 all count
    on_or_before = (day <= target) & session
    for g in np.unique(group):
        rows = np.flatnonzero((group == g) & on_or_before)
        tgt = target[group == g][0]
        if rows.size and tgt <= day[-1]:
            flags[rows[-1]] = True
    return flags


def session_mismatches(dates, start=None, end=None):
    """Where the data's calendar and the NYSE calendar disagree, from max(start, 1970-01-01, first row) to the
    last row (or `end`): dict(missing=[sessions with no row], extra=[rows that are not sessions]) as ISO dates."""
    idx = _as_dates(dates)
    lo = max(NYSE_FROM, idx[0]) if start is None else max(NYSE_FROM, pd.Timestamp(start), idx[0])
    hi = idx[-1] if end is None else min(pd.Timestamp(end), idx[-1])
    sub = idx[(idx >= lo) & (idx <= hi)]
    sess = nyse.session_day_numbers()
    lo_d, hi_d = (lo - pd.Timestamp("1970-01-01")).days, (hi - pd.Timestamp("1970-01-01")).days
    sess = sess[(sess >= lo_d) & (sess <= hi_d)]
    day = _day_numbers(sub)
    missing = sess[~np.isin(sess, day)].astype("datetime64[D]")
    extra = day[~np.isin(day, sess)].astype("datetime64[D]")
    return dict(missing=[str(d) for d in missing], extra=[str(d) for d in extra])


def gap_days(dates):
    """Calendar days between each row and the one before it, as whole numbers; 0 on the first row."""
    idx = _as_dates(dates)
    out = np.zeros(len(idx), dtype=np.int64)
    if len(idx) > 1:
        out[1:] = np.diff(_day_numbers(idx))
    return out


def accrual_fraction(dates, days_in_year=365):
    """Calendar days since the previous row / days_in_year, as float64; 0 on the first row (nothing has accrued).

    days_in_year=365 (default): the same numbers as letf's data_io.accrual_fraction (a Friday-to-Monday step
    accrues 3/365); the fee leg and cash use it. days_in_year=360: ACT/360, the money-market convention of the
    financing legs on overnight-rate swaps (OBFR, fed funds); a Friday-to-Monday step accrues 3/360.
    """
    if days_in_year not in DAY_COUNTS or isinstance(days_in_year, bool):
        raise ValueError(f"days_in_year must be one of {DAY_COUNTS} (ACT/360 or ACT/365), got {days_in_year!r}")
    return gap_days(dates) / float(days_in_year)
