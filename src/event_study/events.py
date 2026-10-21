"""Load and check the events CSV (e.g. events/opec_events.csv).

The README describes each column. load_events checks every row against the
rules below and, if anything is wrong, raises one ValueError listing every
problem by file line number (the header is line 1), so you can fix the whole
file in one pass. A bad file is never partly loaded.

File-level rules (checked first; any failure stops with one ValueError whose
message starts with the file path):
- The file is UTF-8 text (a byte-order mark is fine). Excel's plain "CSV"
  and UTF-16 exports are not.
- No NUL bytes. pandas would silently cut a field short at one.
- No row has more fields than the header. A stray or trailing comma would
  otherwise shift values into the wrong columns or drop them.
- pandas can parse it as CSV (no unclosed quotes, not empty).

Row rules:
- All REQUIRED_COLUMNS are present. Extra columns are allowed and kept.
- event_id is filled in and unique.
- announcement_datetime_et is required; it and leak_datetime_et are naive
  US Eastern wall-clock times written exactly as YYYY-MM-DD HH:MM, with a
  year from 2000 (CALENDAR_START) to the last year of the trading calendar.
  The year is checked before any time zone conversion: pandas' conversion
  misbehaves far outside that range (year 224 was reported as a
  daylight-saving gap, 9999-12-31 evening crashed).
- leak_datetime_et and leak_source_url are both filled or both blank, and a
  leak time must be strictly earlier than the announcement time.
- decision_group, direction, surprise_flag and time_assumed take only the
  allowed values.
- time_assumed is 1 for a weekday event with no timed source (DECISIONS.md):
  announcement_datetime_et then holds the announcement date with a
  placeholder time, not a real one. Blank or 0 means the time is not
  assumed. A row with a leak time cannot be time_assumed: a timed leak is a
  known time.
- source_url is filled in.
- Day 0 can be computed from the event time (event_days.event_day_zero),
  which fails for times outside the trading calendar.

Daylight saving: each naive time gets the America/New_York zone, which picks
EST or EDT from the date (including the pre-2007 US rules). Two kinds of
wall-clock time are rejected because they do not name one moment:
- Nonexistent: on the March "spring forward" night, clocks jump from 2:00 to
  3:00, so 02:00-02:59 never happened.
- Ambiguous: on the November "fall back" night, clocks go from 2:00 back to
  1:00, so 01:00-01:59 happened twice (once EDT, once EST) and the CSV has no
  way to say which.
Both fall in the early hours of a Sunday, so a real event there is most
likely a conversion mistake. Not catchable here: a time converted from Vienna
with the wrong offset is still a valid Eastern time, just the wrong one.
"""

import io
import re
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

from event_study.event_days import (
    CALENDAR_START,
    EASTERN_TZ_NAME,
    event_day_zero,
    next_session,
    nyse_calendar,
)

REQUIRED_COLUMNS = (
    "event_id",
    "announcement_datetime_et",
    "leak_datetime_et",
    "leak_source_url",
    "decision_group",
    "direction",
    "surprise_flag",
    "confound_note",
    "source_url",
    "notes",
    "time_assumed",
)
DECISION_GROUPS = ("ministerial", "voluntary_group", "saudi_unilateral")
DIRECTIONS = ("cut", "hold", "increase")
SURPRISE_FLAGS = ("", "0", "1")  # blank means unknown
TIME_ASSUMED_FLAGS = ("", "0", "1")  # blank means 0 (the time is not assumed)

DATETIME_FORMAT = "%Y-%m-%d %H:%M"
# strptime alone would accept "2024-3-4 9:00"; this insists on exact digits.
_DATETIME_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")

# Column dtypes for the parsed times. "us" (microseconds) is pandas 3's
# default resolution; setting it keeps an empty file's columns the same type.
_EASTERN_DTYPE = f"datetime64[us, {EASTERN_TZ_NAME}]"
_DAY_DTYPE = "datetime64[us]"


def parse_eastern(text: str) -> pd.Timestamp:
    """Turn "YYYY-MM-DD HH:MM" (naive Eastern) into a tz-aware Timestamp.

    Raises ValueError for the wrong format, an impossible date, a year
    outside the trading calendar, or a time that does not exist or happens
    twice because of daylight saving (see the module docstring).
    """
    if not _DATETIME_PATTERN.fullmatch(text):
        raise ValueError(f"{text!r} is not in the format YYYY-MM-DD HH:MM")
    try:
        parsed = datetime.strptime(text, DATETIME_FORMAT)
    except ValueError:
        raise ValueError(f"{text!r} is not a real date and time") from None
    _check_year(text, parsed.year)
    naive = pd.Timestamp(parsed)

    # nonexistent="NaT" returns "not a time" instead of raising, which lets
    # us tell this case apart from the ambiguous one below.
    if pd.isna(naive.tz_localize(EASTERN_TZ_NAME, ambiguous=True, nonexistent="NaT")):
        raise ValueError(
            f"{text} does not exist in US Eastern time: clocks jumped from 2:00 to 3:00 "
            "that night (daylight saving began). Check the source time and its conversion."
        )
    # ambiguous=True picks the EDT reading, False the EST one. They differ
    # only for a time that happened twice.
    as_edt = naive.tz_localize(EASTERN_TZ_NAME, ambiguous=True)
    as_est = naive.tz_localize(EASTERN_TZ_NAME, ambiguous=False)
    if as_edt != as_est:
        raise ValueError(
            f"{text} happened twice in US Eastern time: clocks fell back from 2:00 to 1:00 "
            "that night, so it could be EDT or EST. Check the source time."
        )
    return as_edt


def _check_year(text: str, year: int) -> None:
    """Raise ValueError unless year is within the trading calendar's years.

    The last year comes from the calendar, which ends about a year after
    today, so it moves forward over time.
    """
    first_year = pd.Timestamp(CALENDAR_START).year
    last_year = nyse_calendar().last_session.year
    if not first_year <= year <= last_year:
        raise ValueError(
            f"{text} has year {year}, outside the supported range {first_year} to "
            f"{last_year} (the NYSE trading calendar). Check the year for a typo."
        )


def _read_text(path: Path) -> str:
    """The file's contents as text. Raises ValueError starting with the path.

    Read as UTF-8; "utf-8-sig" also drops a byte-order mark at the start if
    there is one. Any error (missing file, not UTF-8, ...) becomes ValueError.
    """
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except Exception as err:
        raise ValueError(
            f"{path}: could not read the file as UTF-8 text ({type(err).__name__}: {err}). "
            "Save it as UTF-8 CSV."
        ) from err
    if "\x00" in text:
        # Count lines the way pandas does: \r\n, \r or \n each end one.
        line = len(re.split(r"\r\n|\r|\n", text[: text.index("\x00") + 1]))
        raise ValueError(
            f"{path}: contains a NUL byte (character code 0) on line {line}. pandas would "
            "silently cut that field short. The file may be corrupted or saved in the "
            "wrong format."
        )
    return text


def _parse_csv(path: Path, text: str) -> pd.DataFrame:
    """Parse CSV text with every value as text. Raises ValueError starting with the path.

    dtype=str stops pandas guessing types (an event_id "001" stays "001");
    keep_default_na=False keeps blank cells as "" instead of NaN.

    index_col=False: when every data row has one field more than the header
    (e.g. a trailing comma on each line), pandas would otherwise quietly use
    the first column as the row index and shift every value one column left.
    With index_col=False it instead drops the extra fields and gives a
    ParserWarning. Turning that warning into an error rejects the file, so
    no value is lost or moved. A row with extra fields among normal rows
    raises ParserError either way.
    """
    try:
        # catch_warnings restores the normal warning settings afterwards.
        with warnings.catch_warnings():
            warnings.simplefilter("error", pd.errors.ParserWarning)
            return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, index_col=False)
    except pd.errors.ParserWarning:
        raise ValueError(
            f"{path}: some rows have more fields than the header, usually from a stray or "
            "trailing comma. Put values containing commas in double quotes."
        ) from None
    except Exception as err:
        raise ValueError(
            f"{path}: could not be read as CSV ({type(err).__name__}: {err})"
        ) from err


def _read_table(path: Path) -> pd.DataFrame:
    """Read the CSV with every value as text, blanks as "" and spaces trimmed.

    File-level problems (see the module docstring) raise ValueError starting
    with the path. A missing required column also raises ValueError.
    """
    table = _parse_csv(path, _read_text(path))
    for column in table.columns:
        table[column] = table[column].str.strip()
    missing = [c for c in REQUIRED_COLUMNS if c not in table.columns]
    if missing:
        raise ValueError(f"events file {path} is missing column(s): {', '.join(missing)}")
    return table


def _parse_time(row: dict, column: str, errors: list[str]) -> pd.Timestamp | None:
    """Parse one time column, adding any problem to errors. Blank gives None."""
    text = row[column]
    if text == "":
        return None
    try:
        return parse_eastern(text)
    except ValueError as err:
        errors.append(f"{column}: {err}")
        return None


def _check_choices(row: dict, errors: list[str]) -> None:
    """Columns that only take a fixed set of values, plus source_url."""
    for column, allowed in (
        ("decision_group", DECISION_GROUPS),
        ("direction", DIRECTIONS),
        ("surprise_flag", SURPRISE_FLAGS),
        ("time_assumed", TIME_ASSUMED_FLAGS),
    ):
        if row[column] not in allowed:
            shown = ", ".join(repr(a) for a in allowed)
            errors.append(f"{column} is {row[column]!r}, must be one of {shown}")
    if row["source_url"] == "":
        errors.append("source_url is blank")


def _check_row(row: dict, use_leak: bool, shift_assumed: bool) -> tuple[dict, list[str]]:
    """Check one row and work out its times.

    Returns (parsed values, list of problems). Parsed values are None where
    a problem stopped them from being computed.
    """
    errors: list[str] = []
    if row["event_id"] == "":
        errors.append("event_id is blank")

    if row["announcement_datetime_et"] == "":
        errors.append("announcement_datetime_et is blank")
    announced = _parse_time(row, "announcement_datetime_et", errors)
    leak = _parse_time(row, "leak_datetime_et", errors)

    if (row["leak_datetime_et"] == "") != (row["leak_source_url"] == ""):
        errors.append("leak_datetime_et and leak_source_url must both be filled or both blank")
    # Both are tz-aware, so this compares real moments, not clock readings.
    if announced is not None and leak is not None and leak >= announced:
        errors.append(f"leak time {leak} is not earlier than announcement time {announced}")
    _check_choices(row, errors)
    time_assumed = row["time_assumed"] == "1"
    if time_assumed and row["leak_datetime_et"] != "":
        errors.append("time_assumed is 1 but the row has a leak time, which is a known time")

    # Event time rule from CLAUDE.md: the leak if there is one, else the
    # announcement. Untimed leaks never reach here: their row has a blank leak.
    used_leak = use_leak and row["leak_datetime_et"] != ""
    event_time = leak if used_leak else announced
    day0 = None
    if event_time is not None:
        try:
            day0 = event_day_zero(event_time)
            if shift_assumed and time_assumed:
                day0 = next_session(day0)
        except ValueError as err:
            errors.append(f"day 0: {err}")

    parsed = {
        "announcement_datetime_et": announced,
        "leak_datetime_et": leak,
        "event_time": event_time,
        "used_leak": used_leak,
        "day0": day0,
        "time_assumed": time_assumed,
    }
    return parsed, errors


def _duplicate_id_errors(table: pd.DataFrame) -> list[str]:
    """One message per repeated (non-blank) event_id, naming its lines."""
    ids = table["event_id"]
    # keep=False marks every copy, not just the second and later ones.
    repeated = ids[ids.duplicated(keep=False) & (ids != "")]
    messages = []
    for event_id, group in repeated.groupby(repeated):
        lines = ", ".join(str(i + 2) for i in group.index)
        messages.append(f"event_id {event_id!r} is used more than once (lines {lines})")
    return messages


def load_events(
    path: Path | str, use_leak: bool = True, shift_assumed: bool = False
) -> pd.DataFrame:
    """Read and check an events CSV. Returns one row per event.

    use_leak=True (main results): event time is leak_datetime_et if filled,
    else announcement_datetime_et. use_leak=False (the robustness check in
    DECISIONS.md): event time is always the announcement. The leak columns
    are checked either way.

    shift_assumed=True (the third report in DECISIONS.md): day 0 of every
    time_assumed row moves one trading day later, in case the announcement
    came after the close. Rows with a known time are not moved.

    The returned frame keeps every CSV column (extras too) and:
    - announcement_datetime_et, leak_datetime_et: tz-aware America/New_York
      Timestamps (leak is NaT when blank)
    - surprise_flag: 0, 1, or <NA> when blank (pandas nullable integer)
    - time_assumed: True or False (blank counts as False)
    - adds event_time (tz-aware), used_leak (bool) and day0 (tz-naive date,
      matching the returns index; already shifted when shift_assumed)

    A file with only the header row gives an empty frame with these columns.
    Raises ValueError listing every problem found (see the module docstring).
    """
    path = Path(path)
    table = _read_table(path)

    errors = _duplicate_id_errors(table)
    parsed_rows = []
    # to_dict("records") gives one plain dict per row, e.g. row["event_id"].
    for i, row in enumerate(table.to_dict("records")):
        parsed, row_errors = _check_row(row, use_leak, shift_assumed)
        parsed_rows.append(parsed)
        label = row["event_id"] or "no event_id"
        errors.extend(f"line {i + 2} ({label}): {e}" for e in row_errors)
    if errors:
        raise ValueError(
            f"events file {path} has {len(errors)} problem(s):\n  " + "\n  ".join(errors)
        )

    events = table.copy()
    for column, dtype in (
        ("announcement_datetime_et", _EASTERN_DTYPE),
        ("leak_datetime_et", _EASTERN_DTYPE),
        ("event_time", _EASTERN_DTYPE),
        ("used_leak", bool),
        ("day0", _DAY_DTYPE),
        ("time_assumed", bool),
    ):
        values = [p[column] for p in parsed_rows]
        events[column] = pd.Series(values, index=table.index, dtype=dtype)
    events["surprise_flag"] = table["surprise_flag"].map({"": pd.NA, "0": 0, "1": 1}).astype("Int64")
    return events
