"""NYSE trading sessions from 1970-01-01 on, written out from the exchange's holiday rules (no extra packages).

Why this exists: a calendar fund resets at the close of the last NYSE business day of each week / month / quarter
(prospectus: "business day = any day the NYSE is open"). periods.period_end_flags uses this module to find that
day from the exchange calendar instead of from the last row of the data, so a missing row can never move a reset.

Terms
- session: a day the NYSE is open (a full day or an early close; early closes do not matter here).
- observed holiday: when a fixed-date holiday falls on a weekend, the exchange closes on a weekday instead:
  Saturday -> the Friday before, Sunday -> the Monday after. Exception (the exchange's Saturday-holiday rule):
  the Friday stays OPEN when it is the last business day of a month, because it closes a monthly (or yearly)
  accounting period. In practice: New Year's Day on a Saturday closes nothing (Friday Dec 31 is open), and
  Memorial Day on Saturday 1970-05-30 closed nothing (Friday 1970-05-29, the last business day of May, traded;
  the SPX file has a full bar that day, range 73.53-76.92).

Rule set, 1970-01-01 to today (ported from target_funds/definedtarget/calendar.py, which holds the 2022+ rules,
and extended backwards with the documented rule changes):
- New Year's Day (Jan 1; observed; so no closure at all when it falls on a Saturday).
- Martin Luther King Jr. Day, 3rd Monday of January: from 1998 only.
- Washington's Birthday: Feb 22 (observed) up to 1970; 3rd Monday of February from 1971 (Uniform Monday Holiday Act).
- Good Friday (two days before Easter Sunday): every year.
- Memorial Day: May 30 (observed) up to 1970; last Monday of May from 1971.
- Juneteenth (June 19, observed): from 2022.
- Independence Day (July 4, observed).
- Labor Day, 1st Monday of September.
- Election Day (the Tuesday after the first Monday of November): presidential election years 1972, 1976 and
  1980 only. The exchange closed every Election Day up to 1968 and in presidential years up to 1980.
  VERIFIED against the exchange's own record ("History of New York Stock Exchange Holidays", revised January
  2011: "Election Day: closed every year through 1968. Closed presidential election years only, 1972-1980");
  the SPX export has no rows on those three days, which agrees.
- Thanksgiving, 4th Thursday of November.
- Christmas (Dec 25, observed).
- SPECIAL_CLOSURES: one-off full-day closures (days of mourning, weather, emergencies), a dated list below.
  VERIFIED 2026-10-24 for 1970-2011 against the exchange's own "New York Stock Exchange Special Closings,
  1885-date" (revised January 2011): its full-day closings in those years are exactly the entries below, and
  every other entry in the document is an early close, a late opening, a trading halt or a moment of silence.
  The Saturday-holiday rule is the exchange's Rule 51 as the same document states it (adopted 1959-07-03: the
  preceding Friday is closed "unless it ends a monthly or yearly accounting period"). The three entries after
  2011 (Hurricane Sandy 2012, the 2018 and 2025 days of mourning) are consistent with the price data: it has no row
  on any of them, and it has sessions on the days either side. The exchange's notices for these three closures are
  not kept in this folder. Each entry carries its reason.

Not modeled: early (1 pm) closes; any rule before 1970 (the 1968-69 paperwork-crisis Wednesday closures and
the 1969 one-off closures are out of range). Functions refuse dates before VALID_FROM.

    holidays(2024)                       # frozenset of rule-based full-day holidays in 2024
    is_session(date(2024, 3, 29))        # False: Good Friday
    sessions(date(2024, 1, 1), date(2024, 1, 31))
"""
from datetime import date, timedelta
from functools import lru_cache

import numpy as np

VALID_FROM = date(1970, 1, 1)
VALID_TO = date(2100, 12, 31)          # the rules are projected forward; one-off closures are added by hand

# One-off full-day closures from 1970 on (not covered by the yearly rules). Add new ones here when announced.
SPECIAL_CLOSURES = {
    date(1972, 12, 28): "national day of mourning, President Truman",
    date(1973, 1, 25): "national day of mourning, President Johnson",
    date(1977, 7, 14): "New York City blackout",
    date(1985, 9, 27): "Hurricane Gloria",
    date(1994, 4, 27): "national day of mourning, President Nixon",
    date(2001, 9, 11): "terrorist attacks of September 11",
    date(2001, 9, 12): "terrorist attacks of September 11",
    date(2001, 9, 13): "terrorist attacks of September 11",
    date(2001, 9, 14): "terrorist attacks of September 11",
    date(2004, 6, 11): "national day of mourning, President Reagan",
    date(2007, 1, 2): "national day of mourning, President Ford",
    date(2012, 10, 29): "Hurricane Sandy",
    date(2012, 10, 30): "Hurricane Sandy",
    date(2018, 12, 5): "national day of mourning, President George H. W. Bush",
    date(2025, 1, 9): "national day of mourning, President Carter",
}

ELECTION_DAY_YEARS = (1972, 1976, 1980)     # presidential Election Day closures inside the valid range


def easter(year):
    """Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year, month, weekday, n):
    """The n-th given weekday (Mon=0) of a month; n=-1 means the last one."""
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d):
    """The weekday the exchange closes for a holiday dated d, or None if it closes no day.

    Sunday -> the Monday after. Saturday -> the Friday before, UNLESS that Friday is the last weekday of its month
    (it closes a monthly accounting period, so the exchange stays open: no closure at all). A weekday stays.
    """
    if d.weekday() == 5:
        friday = d - timedelta(days=1)
        if (friday + timedelta(days=3)).month != friday.month:      # the next Monday is in a new month
            return None
        return friday
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _check_year(year):
    if not VALID_FROM.year <= year <= VALID_TO.year:
        raise ValueError(f"the NYSE rule set here covers {VALID_FROM.year}-{VALID_TO.year}, not {year}")


@lru_cache(maxsize=None)
def holidays(year):
    """Set of rule-based NYSE full-day holidays in a calendar year (one-off closures are in SPECIAL_CLOSURES)."""
    _check_year(year)
    out = set()
    out.add(_observed(date(year, 1, 1)))                   # New Year's Day (Sunday -> Monday Jan 2; Saturday -> none)
    if year >= 1998:
        out.add(_nth_weekday(year, 1, 0, 3))               # Martin Luther King Jr. Day
    if year >= 1971:
        out.add(_nth_weekday(year, 2, 0, 3))               # Washington's Birthday, 3rd Monday
        out.add(_nth_weekday(year, 5, 0, -1))              # Memorial Day, last Monday of May
    else:
        out.add(_observed(date(year, 2, 22)))              # Washington's Birthday, fixed date
        out.add(_observed(date(year, 5, 30)))              # Memorial Day, fixed date
    out.add(easter(year) - timedelta(days=2))              # Good Friday
    if year >= 2022:
        out.add(_observed(date(year, 6, 19)))              # Juneteenth
    out.add(_observed(date(year, 7, 4)))                   # Independence Day
    out.add(_nth_weekday(year, 9, 0, 1))                   # Labor Day
    if year in ELECTION_DAY_YEARS:
        out.add(_nth_weekday(year, 11, 0, 1) + timedelta(days=1))   # Election Day (Tuesday after 1st Monday)
    out.add(_nth_weekday(year, 11, 3, 4))                  # Thanksgiving
    out.add(_observed(date(year, 12, 25)))                 # Christmas
    out.discard(None)                                      # a Saturday holiday on a month-end Friday closes nothing
    return frozenset(out)


def is_session(d):
    """True if the NYSE is open (full day or early close) on date d."""
    _check_year(d.year)
    return d.weekday() < 5 and d not in holidays(d.year) and d not in SPECIAL_CLOSURES


def next_session(d):
    """The first NYSE session strictly after d."""
    d += timedelta(days=1)
    while not is_session(d):
        d += timedelta(days=1)
    return d


def previous_session(d):
    """The last NYSE session strictly before d."""
    d -= timedelta(days=1)
    while not is_session(d):
        d -= timedelta(days=1)
    return d


def sessions(start, end):
    """All NYSE sessions from start to end inclusive, as a list of dates."""
    out, d = [], start
    while d <= end:
        if is_session(d):
            out.append(d)
        d += timedelta(days=1)
    return out


_EPOCH = date(1970, 1, 1)


@lru_cache(maxsize=1)
def session_day_numbers():
    """Every session from VALID_FROM to VALID_TO as a sorted int64 array of days since 1970-01-01 (cached).

    The fast form used by periods.py: one array lookup per period instead of a Python loop per row.
    """
    days = np.arange((VALID_FROM - _EPOCH).days, (VALID_TO - _EPOCH).days + 1, dtype=np.int64)
    weekday = (days + 3) % 7                               # 1970-01-01 was a Thursday (Monday = 0)
    closed = set()
    for y in range(VALID_FROM.year, VALID_TO.year + 1):
        closed.update((d - _EPOCH).days for d in holidays(y))
    closed.update((d - _EPOCH).days for d in SPECIAL_CLOSURES)
    keep = (weekday < 5) & ~np.isin(days, np.fromiter(closed, dtype=np.int64))
    return days[keep]
