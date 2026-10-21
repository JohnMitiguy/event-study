"""Slice a daily returns series into estimation and event windows.

Everything counts by integer position (row number) in the returns index,
never by calendar days. With day 0 at position p:

- Estimation window: the est_length latest rows at or before position
  p - gap whose dates are not in skip_dates. With no skip_dates that is
  positions p - gap - est_length + 1 through p - gap, inclusive: with the
  defaults (120, 10), p-129 .. p-10, so it ends on day -10 and days -9..-1
  are not in it.
- Skipped rows: each row whose date is in skip_dates is left out, and the
  window reaches one row further back instead, so it always has est_length
  rows, but they may not be consecutive. If row p - gap itself is skipped,
  the window ends on the latest unskipped row before it. It never uses a row
  after p - gap. The runner passes the days inside other events' windows.
- Event window (start, end): positions p + start through p + end, inclusive.
  (-1, 1) is p-1 .. p+1. skip_dates never change an event window.

Assumptions:
- Every trading day has a row. If the data source dropped a day, positions
  shift silently; this module does not cross-check the exchange calendar.
- NaN returns inside a window are passed through untouched.
- The market model does not need consecutive days: each day is one
  (benchmark, security) pair in the regression, so gaps left by skipped
  days don't matter to it.

Errors: problems with one event's position in the data (day 0 missing, a
window running off either end) raise EventDataError. A bad index or bad
parameters raise plain ValueError.
"""

from datetime import date

import numpy as np
import pandas as pd

from event_study.errors import EventDataError

# Defaults only. Every function takes these as parameters.
DEFAULT_EST_LENGTH = 120
DEFAULT_GAP = 10
DEFAULT_EVENT_WINDOWS = ((-1, 1), (-5, 5))


def window_label(window: tuple[int, int]) -> str:
    """(-1, 1) -> "[-1,+1]". Used as a column name and in printouts."""
    start, end = window
    return f"[{start:+d},{end:+d}]"


def _check_index(returns: pd.Series) -> None:
    """Raise ValueError unless the index is a tz-naive, sorted, unique DatetimeIndex.

    Counting by position only means something if each row is one trading day
    in date order.
    """
    index = returns.index
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError(f"returns must have a DatetimeIndex, got {type(index).__name__}")
    if index.tz is not None:
        raise ValueError(f"returns index must be tz-naive, got time zone {index.tz}")
    if not index.is_monotonic_increasing:
        raise ValueError("returns index must be sorted in increasing date order")
    if not index.is_unique:
        raise ValueError("returns index has duplicate dates")


def _check_params(est_length: int, gap: int, event_windows) -> None:
    """Raise ValueError for impossible or look-ahead parameters.

    Look-ahead rules: the estimation window ends on day -gap, so
    - gap >= 1 makes it end on day -1 or earlier, never on day 0 or later;
    - -gap < start makes it end before each event window starts.
    Both depend only on the parameters, so they are checked here, before any
    data, and fail the same way for every event.
    """
    if est_length < 1:
        raise ValueError(f"est_length must be at least 1, got {est_length}")
    if gap < 1:
        raise ValueError(
            f"gap must be at least 1, got {gap}: the estimation window must end before day 0"
        )
    for start, end in event_windows:
        if start > end:
            raise ValueError(f"event window ({start}, {end}) has start after end")
        if -gap >= start:
            raise ValueError(
                f"estimation window ends on day {-gap}, which is on or after the "
                f"start of event window ({start}, {end}); increase gap"
            )


def day_zero_position(returns: pd.Series, day0: date | pd.Timestamp) -> int:
    """Integer position of day0 in the returns index.

    day0 must match an index date exactly; a missing date raises
    EventDataError rather than snapping to a neighbouring trading day. day0
    must be tz-naive, like the index (a tz-aware day0 raises ValueError).
    """
    ts = pd.Timestamp(day0)
    if ts.tz is not None:
        raise ValueError(f"day0 {day0} must be tz-naive (a plain date), got time zone {ts.tz}")
    if ts not in returns.index:
        raise EventDataError(f"day0 {ts.date()} is not in the returns index")
    return returns.index.get_loc(ts)


def _check_skip_dates(skip_dates) -> pd.DatetimeIndex:
    """skip_dates as a DatetimeIndex. Raise ValueError if it has a time zone.

    The returns index is tz-naive, so tz-aware dates would match no row and
    silently skip nothing.
    """
    skip = pd.DatetimeIndex(skip_dates)
    if skip.tz is not None:
        raise ValueError(f"skip_dates must be tz-naive (plain dates), got time zone {skip.tz}")
    return skip


def _estimation_rows(
    returns: pd.Series, skipped: np.ndarray, last: int, est_length: int
) -> np.ndarray:
    """Row numbers of the estimation window: the est_length latest rows at or
    before row `last` that are not skipped.

    skipped holds one True/False per row of returns (True = leave the row
    out). Raises EventDataError if fewer than est_length rows are left.
    """
    # max(..., 0): if last is negative, no row qualifies. Without it, a
    # negative slice end would count back from the END of the array.
    candidates = skipped[: max(last + 1, 0)]
    # ~ flips True and False; flatnonzero lists the row numbers that are
    # True, in order. So `kept` is every unskipped row from 0 through last.
    kept = np.flatnonzero(~candidates)
    if len(kept) < est_length:
        # Rows from `last` back to the first row are too few. If last is
        # before the first row, the rows in between are missing too.
        missing = est_length - len(kept) + max(-(last + 1), 0)
        message = (
            f"estimation window needs {missing} more row(s) before "
            f"{returns.index[0].date()} (first row)"
        )
        n_skipped = len(candidates) - len(kept)
        if n_skipped:
            message += f"; {n_skipped} day(s) were skipped as inside other events' windows"
        raise EventDataError(message)
    return kept[-est_length:]


def slice_windows(
    returns: pd.Series,
    day0: date | pd.Timestamp,
    est_length: int = DEFAULT_EST_LENGTH,
    gap: int = DEFAULT_GAP,
    event_windows=DEFAULT_EVENT_WINDOWS,
    skip_dates=(),
) -> tuple[pd.Series, dict[tuple[int, int], pd.Series]]:
    """Return (estimation window, {(start, end): event window}).

    Each window is a slice of `returns` with its original dates as the index.
    See the module docstring for which positions each window covers.

    skip_dates: dates to leave out of the estimation window (a list or
    DatetimeIndex of tz-naive dates). Dates that are not in the index, or
    that come after day -gap, change nothing.

    Raises ValueError if the index or parameters are invalid (including
    gap < 1 and tz-aware skip_dates), or if the estimation window ends on or
    after the first day of any event window (look-ahead). Raises
    EventDataError if day0 is not in the index, the estimation window
    (after skipping) needs rows before the first row, or an event window runs
    outside the series.
    """
    _check_index(returns)
    _check_params(est_length, gap, event_windows)
    skip = _check_skip_dates(skip_dates)
    p = day_zero_position(returns, day0)
    n = len(returns)

    # isin gives one True/False per row: is that row's date in skip?
    skipped = returns.index.isin(skip)
    est_rows = _estimation_rows(returns, skipped, p - gap, est_length)

    event_slices = {}
    for start, end in event_windows:
        first, last = p + start, p + end
        if first < 0 or last >= n:
            raise EventDataError(
                f"event window ({start}, {end}) runs outside the series "
                f"({returns.index[0].date()} to {returns.index[-1].date()})"
            )
        # iloc's end is exclusive, hence the + 1.
        event_slices[(start, end)] = returns.iloc[first : last + 1]

    # iloc with a list of row numbers takes exactly those rows, in order.
    estimation = returns.iloc[est_rows]
    return estimation, event_slices
