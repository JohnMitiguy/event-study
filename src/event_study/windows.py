"""Slice a daily returns series into estimation and event windows.

Everything counts by integer position (row number) in the returns index,
never by calendar days. With day 0 at position p:

- Estimation window: positions p - gap - est_length + 1 through p - gap,
  inclusive. It ENDS on event day -gap. With the defaults (120, 10) that is
  p-129 .. p-10, so it ends on day -10 and days -9..-1 are not in it.
- Event window (start, end): positions p + start through p + end, inclusive.
  (-1, 1) is p-1 .. p+1.

Assumptions:
- Every trading day has a row. If the data source dropped a day, positions
  shift silently; this module does not cross-check the exchange calendar.
- NaN returns inside a window are passed through untouched.
"""

from datetime import date

import pandas as pd

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


def _check_params(est_length: int, event_windows) -> None:
    if est_length < 1:
        raise ValueError(f"est_length must be at least 1, got {est_length}")
    for start, end in event_windows:
        if start > end:
            raise ValueError(f"event window ({start}, {end}) has start after end")


def day_zero_position(returns: pd.Series, day0: date | pd.Timestamp) -> int:
    """Integer position of day0 in the returns index.

    day0 must match an index date exactly; a missing date raises ValueError
    rather than snapping to a neighbouring trading day. day0 must be tz-naive,
    like the index.
    """
    ts = pd.Timestamp(day0)
    if ts.tz is not None:
        raise ValueError(f"day0 {day0} must be tz-naive (a plain date), got time zone {ts.tz}")
    if ts not in returns.index:
        raise ValueError(f"day0 {ts.date()} is not in the returns index")
    return returns.index.get_loc(ts)


def slice_windows(
    returns: pd.Series,
    day0: date | pd.Timestamp,
    est_length: int = DEFAULT_EST_LENGTH,
    gap: int = DEFAULT_GAP,
    event_windows=DEFAULT_EVENT_WINDOWS,
) -> tuple[pd.Series, dict[tuple[int, int], pd.Series]]:
    """Return (estimation window, {(start, end): event window}).

    Each window is a slice of `returns` with its original dates as the index.
    See the module docstring for which positions each window covers.

    Raises ValueError if the index or parameters are invalid, day0 is not in
    the index, the estimation window starts before the first row, an event
    window runs outside the series, or the estimation window ends on or after
    the first day of any event window (look-ahead).
    """
    _check_index(returns)
    _check_params(est_length, event_windows)
    p = day_zero_position(returns, day0)
    n = len(returns)

    est_first = p - gap - est_length + 1
    est_last = p - gap
    if est_first < 0:
        raise ValueError(
            f"estimation window needs {-est_first} more row(s) before "
            f"{returns.index[0].date()} (first row)"
        )

    event_slices = {}
    for start, end in event_windows:
        first, last = p + start, p + end
        if first < 0 or last >= n:
            raise ValueError(
                f"event window ({start}, {end}) runs outside the series "
                f"({returns.index[0].date()} to {returns.index[-1].date()})"
            )
        if est_last >= first:
            raise ValueError(
                f"estimation window ends on day {-gap}, which is on or after the "
                f"start of event window ({start}, {end}); increase gap"
            )
        # iloc's end is exclusive, hence the + 1.
        event_slices[(start, end)] = returns.iloc[first : last + 1]

    estimation = returns.iloc[est_first : est_last + 1]
    return estimation, event_slices
