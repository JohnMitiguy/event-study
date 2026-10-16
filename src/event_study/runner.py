"""Run the market model over a table of events.

For each event: slice_windows on both series, fit_market_model on the
estimation window (min_obs = est_length), car_test on each event window.

An event that raises EventDataError (day 0 not in the data, too little
history, NaN returns, a perfect fit, ...) is kept in the results with status
"failed", the message in `error` and NaN for the numbers; the other events
still run. Any other exception, including a plain ValueError (bad parameters,
a broken index), stops the run: it is a problem with the whole run, not with
one event.

A flat benchmark also stops the run. If the benchmark return is the same on
every day of an event's estimation window, fit_market_model raises a plain
ValueError (beta can't be estimated). A benchmark with no variance is
treated as a broken series, for example stale or forward-filled prices,
not as one failed event: the same fault would likely affect other events
too, and the data should be fixed rather than the event reported as failed.

Any average across events must count N from status "ok" rows only and
report every failed event with its reason (pandas' .mean() silently skips
the NaN numbers of failed events).

"Widest window" below means the span from the earliest start to the latest
end of the configured event windows: (-5, 5) for the defaults
((-1, 1), (-5, 5)).

Overlap diagnostics (no events are dropped because of them):
- est_overlap_days: days in this event's estimation window that fall inside
  any other event's widest window. Those days carry another event's
  reaction, which inflates resid_std and can bend alpha and beta.
- nearby_events: other events whose widest window shares a day with this
  event's widest window, so their CARs partly measure the same days.
Both are counted by NYSE session position (event_days.session_position),
not by row in the returns data, so events whose day 0 is before or after the
data still count. This matches the windows' row counting only when the data
holds every NYSE session, which scripts/run_opec.py checks.
"""

import pandas as pd

from event_study.errors import EventDataError
from event_study.event_days import nyse_calendar, session_position
from event_study.market_model import abnormal_returns, car_test, fit_market_model
from event_study.windows import (
    DEFAULT_EST_LENGTH,
    DEFAULT_EVENT_WINDOWS,
    DEFAULT_GAP,
    slice_windows,
    window_label,
)

# Columns copied from the events table into the results, in this order.
CARRIED_COLUMNS = (
    "event_id",
    "decision_group",
    "direction",
    "surprise_flag",
    "event_time",
    "used_leak",
    "day0",
)
FIT_COLUMNS = ("alpha", "beta", "resid_std", "n")
DIAGNOSTIC_COLUMNS = ("est_overlap_days", "nearby_events")


def widest_window(event_windows) -> tuple[int, int]:
    """(earliest start, latest end) across the event windows."""
    return min(start for start, _ in event_windows), max(end for _, end in event_windows)


def car_column(window: tuple[int, int]) -> str:
    """(-1, 1) -> "car_[-1,+1]"."""
    return f"car_{window_label(window)}"


def stat_column(window: tuple[int, int]) -> str:
    """(-1, 1) -> "t_[-1,+1]"."""
    return f"t_{window_label(window)}"


def window_columns(event_windows) -> list[str]:
    """CAR and test-stat column names, two per window."""
    columns = []
    for window in event_windows:
        columns += [car_column(window), stat_column(window)]
    return columns


def result_columns(event_windows) -> list[str]:
    """Column order of the results table."""
    return [
        *CARRIED_COLUMNS,
        *FIT_COLUMNS,
        *window_columns(event_windows),
        *DIAGNOSTIC_COLUMNS,
        "status",
        "error",
    ]


def _check_windows(event_windows) -> None:
    """Raise ValueError if an event window appears more than once.

    Each window gets its own CAR and t columns, named from its start and
    end, so a repeated window would give the results table duplicate
    columns. tuple() makes [-1, 1] and (-1, 1) count as the same window.
    """
    windows = [tuple(w) for w in event_windows]
    repeated = sorted({w for w in windows if windows.count(w) > 1})
    if repeated:
        labels = ", ".join(window_label(w) for w in repeated)
        raise ValueError(f"event_windows lists the same window more than once: {labels}")


def _check_events(events: pd.DataFrame) -> None:
    missing = [c for c in CARRIED_COLUMNS if c not in events.columns]
    if missing:
        raise ValueError(f"events is missing column(s): {', '.join(missing)}")
    if not events["event_id"].is_unique:
        raise ValueError("events has duplicate event_id values")


def _run_one(security, benchmark, day0, est_length, gap, event_windows):
    """Fit and test one event. Returns (numbers for its results row,
    abnormal returns over the widest window indexed by event day).

    Raises EventDataError (or ValueError for bad input) from slice_windows
    or the market model.
    """
    wide = widest_window(event_windows)
    # Slice the widest window too, in case it is not one of the configured
    # windows. dict.fromkeys drops it again if it already is.
    windows = tuple(dict.fromkeys((*event_windows, wide)))
    sec_est, sec_events = slice_windows(security, day0, est_length, gap, windows)
    bench_est, bench_events = slice_windows(benchmark, day0, est_length, gap, windows)
    fit = fit_market_model(sec_est, bench_est, min_obs=est_length)

    values = {"alpha": fit.alpha, "beta": fit.beta, "resid_std": fit.resid_std, "n": fit.n}
    for window in event_windows:
        result = car_test(fit, sec_events[window], bench_events[window])
        values[car_column(window)] = result.car
        values[stat_column(window)] = result.test_stat

    abnormal = abnormal_returns(fit, sec_events[wide], bench_events[wide])
    # Relabel dates as event days: -5, -4, ..., +5 for the defaults.
    abnormal.index = range(wide[0], wide[1] + 1)
    return values, abnormal


def overlap_diagnostics(
    day0s: pd.Series, est_length: int, gap: int, event_windows
) -> pd.DataFrame:
    """est_overlap_days and nearby_events per event (see the module docstring).

    Returns a frame with the same index as day0s. Days are NYSE session
    positions, so every event counts whether or not the price data covers
    it. Raises ValueError if a day 0 is not an NYSE session (load_events
    only produces sessions).
    """
    start, end = widest_window(event_windows)
    positions = [session_position(d) for d in day0s]
    wide_days = [set(range(p + start, p + end + 1)) for p in positions]

    rows = []
    for i, p in enumerate(positions):
        others = [days for j, days in enumerate(wide_days) if j != i]
        est_days = set(range(p - gap - est_length + 1, p - gap + 1))
        # set().union(*others) combines all the other events' days into one set.
        rows.append(
            {
                "est_overlap_days": len(est_days & set().union(*others)),
                "nearby_events": sum(1 for days in others if days & wide_days[i]),
            }
        )
    return pd.DataFrame(rows, index=day0s.index, columns=list(DIAGNOSTIC_COLUMNS), dtype="Int64")


def events_needing_later_data(
    events: pd.DataFrame, last_date: pd.Timestamp, event_windows
) -> list[str]:
    """event_ids whose widest window ends after last_date (the last data date).

    The widest window's end is counted in NYSE sessions from day 0, so this
    works without the data. An end past the calendar itself also counts.
    Used to stop a run that needs fresher prices than the cache holds,
    instead of recording those events as failed.
    """
    _, end = widest_window(event_windows)
    sessions = nyse_calendar().sessions
    needing = []
    for event_id, day0 in zip(events["event_id"], events["day0"], strict=True):
        last_needed = session_position(day0) + end
        if last_needed >= len(sessions) or sessions[last_needed] > last_date:
            needing.append(event_id)
    return needing


def run_events(
    events: pd.DataFrame,
    security_returns: pd.Series,
    benchmark_returns: pd.Series,
    est_length: int = DEFAULT_EST_LENGTH,
    gap: int = DEFAULT_GAP,
    event_windows=DEFAULT_EVENT_WINDOWS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run every event. Returns (results, abnormal).

    events: a table like events.load_events returns; it needs CARRIED_COLUMNS
    and unique event_ids. security_returns and benchmark_returns must share
    the same dates (fit_market_model checks this per event).

    results: one row per event, columns from result_columns(event_windows).
    status is "ok" or "failed". Failed events have NaN numbers and a message
    in `error` (None when the event ran).

    abnormal: abnormal returns for events that ran, indexed by event_id, one
    column per event day across the widest window (-5 ... 5 by default).
    Failed events have no row.

    Raises ValueError (stopping the run) for a repeated event window, a bad
    events table, bad parameters, a broken index, or a benchmark that is
    flat over an estimation window (see the module docstring).
    """
    _check_windows(event_windows)
    _check_events(events)
    diagnostics = overlap_diagnostics(events["day0"], est_length, gap, event_windows)

    number_rows = []
    abnormal_rows = {}
    for event in events.to_dict("records"):
        try:
            values, abnormal = _run_one(
                security_returns, benchmark_returns, event["day0"], est_length, gap, event_windows
            )
        except EventDataError as err:
            number_rows.append({"status": "failed", "error": str(err)})
        else:
            number_rows.append(values | {"status": "ok", "error": None})
            abnormal_rows[event["event_id"]] = abnormal

    # Put the pieces side by side. Taking the carried columns straight from
    # `events` keeps their types (e.g. surprise_flag stays 0/1/<NA>).
    # reset_index(drop=True) numbers the rows 0, 1, 2, ... in all three, so
    # concat lines them up row for row.
    number_columns = [*FIT_COLUMNS, *window_columns(event_windows)]
    # Missing keys (the numbers of a failed event) become NaN.
    numbers = pd.DataFrame(number_rows, columns=[*number_columns, "status", "error"])
    numbers = numbers.astype({c: float for c in number_columns} | {"n": "Int64"})
    results = pd.concat(
        [
            events[list(CARRIED_COLUMNS)].reset_index(drop=True),
            numbers,
            diagnostics.reset_index(drop=True),
        ],
        axis=1,
    )[result_columns(event_windows)]

    start, end = widest_window(event_windows)
    abnormal_table = pd.DataFrame.from_dict(
        abnormal_rows, orient="index", columns=list(range(start, end + 1)), dtype=float
    )
    abnormal_table.index.name = "event_id"
    return results, abnormal_table
