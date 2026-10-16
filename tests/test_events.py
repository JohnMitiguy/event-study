"""Tests for the events loader. Every row here is fake (example.com sources)."""

import csv
from pathlib import Path

import pandas as pd
import pytest

from event_study.events import REQUIRED_COLUMNS, load_events, parse_eastern

REAL_EVENTS_CSV = Path(__file__).parent.parent / "events" / "opec_events.csv"


def valid_row(**changes) -> dict:
    """A fake row that passes every check, with any columns changed.

    2024-06-04 is a Tuesday, so 10:00 is during market hours.
    """
    row = {
        "event_id": "test_event_1",
        "announcement_datetime_et": "2024-06-04 10:00",
        "leak_datetime_et": "",
        "leak_source_url": "",
        "decision_group": "ministerial",
        "direction": "cut",
        "surprise_flag": "",
        "confound_note": "",
        "source_url": "https://example.com/announcement",
        "notes": "fake row for tests",
    }
    return row | changes


def write_events(tmp_path: Path, rows: list[dict], columns=REQUIRED_COLUMNS) -> Path:
    """Write rows to a CSV in pytest's temporary folder and return its path.

    csv.DictWriter handles quoting, so values with commas stay in one column.
    """
    path = tmp_path / "events.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(columns))
        writer.writeheader()
        writer.writerows(rows)
    return path


def load_one(tmp_path: Path, use_leak: bool = True, **changes) -> pd.Series:
    """Load a one-row file and return that row."""
    events = load_events(write_events(tmp_path, [valid_row(**changes)]), use_leak=use_leak)
    return events.iloc[0]


def ts_et(text: str) -> pd.Timestamp:
    return pd.Timestamp(text, tz="America/New_York")


# --- The real CSV -----------------------------------------------------------


def test_real_csv_header_matches_required_columns():
    with REAL_EVENTS_CSV.open(newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == list(REQUIRED_COLUMNS)


# --- Valid rows ---------------------------------------------------------------


def test_no_leak_uses_announcement(tmp_path):
    row = load_one(tmp_path)
    assert row["event_time"] == ts_et("2024-06-04 10:00")
    assert row["announcement_datetime_et"] == ts_et("2024-06-04 10:00")
    assert pd.isna(row["leak_datetime_et"])
    assert not row["used_leak"]
    assert row["day0"] == pd.Timestamp("2024-06-04")


def test_leak_sets_event_time_and_day0(tmp_path):
    # Leak on Saturday: day 0 is Monday, not the Tuesday announcement.
    row = load_one(
        tmp_path,
        leak_datetime_et="2024-06-01 10:00",
        leak_source_url="https://example.com/leak",
    )
    assert row["event_time"] == ts_et("2024-06-01 10:00")
    assert row["used_leak"]
    assert row["day0"] == pd.Timestamp("2024-06-03")


def test_use_leak_false_uses_announcement(tmp_path):
    row = load_one(
        tmp_path,
        use_leak=False,
        leak_datetime_et="2024-06-01 10:00",
        leak_source_url="https://example.com/leak",
    )
    assert row["event_time"] == ts_et("2024-06-04 10:00")
    assert not row["used_leak"]
    assert row["day0"] == pd.Timestamp("2024-06-04")
    # The leak is still parsed and kept.
    assert row["leak_datetime_et"] == ts_et("2024-06-01 10:00")


def test_after_close_rolls_forward(tmp_path):
    row = load_one(tmp_path, announcement_datetime_et="2024-06-04 16:00")
    assert row["day0"] == pd.Timestamp("2024-06-05")


def test_column_types(tmp_path):
    rows = [
        valid_row(event_id="a", surprise_flag="1"),
        valid_row(event_id="b", surprise_flag="0"),
        valid_row(event_id="c", surprise_flag=""),
    ]
    events = load_events(write_events(tmp_path, rows))
    assert str(events["event_time"].dt.tz) == "America/New_York"
    assert events["day0"].dt.tz is None
    assert events["surprise_flag"].tolist()[:2] == [1, 0]
    assert pd.isna(events["surprise_flag"].iloc[2])


def test_extra_columns_kept_and_spaces_trimmed(tmp_path):
    path = write_events(
        tmp_path,
        [valid_row(direction=" hold ", my_extra="x, y")],
        columns=[*REQUIRED_COLUMNS, "my_extra"],
    )
    row = load_events(path).iloc[0]
    assert row["direction"] == "hold"
    assert row["my_extra"] == "x, y"


def test_header_only_gives_empty_frame(tmp_path):
    events = load_events(write_events(tmp_path, []))
    assert len(events) == 0
    for column in [*REQUIRED_COLUMNS, "event_time", "used_leak", "day0"]:
        assert column in events.columns


# --- Daylight saving ----------------------------------------------------------


@pytest.mark.parametrize(
    "text, hours_behind_utc",
    [
        ("2024-01-02 10:00", 5),  # winter: EST
        ("2024-07-01 10:00", 4),  # summer: EDT
        ("2024-03-10 01:59", 5),  # last minute before spring forward
        ("2024-03-10 03:00", 4),  # first minute after spring forward
        ("2024-11-03 00:59", 4),  # last minute before the repeated hour
        ("2024-11-03 02:00", 5),  # first minute after the repeated hour
        ("2006-03-12 02:30", 5),  # pre-2007 rules: DST began April 2 in 2006
    ],
)
def test_parse_eastern_offsets(text, hours_behind_utc):
    stamp = parse_eastern(text)
    assert stamp.utcoffset() == pd.Timedelta(hours=-hours_behind_utc)


@pytest.mark.parametrize(
    "text, message",
    [
        ("2024-03-10 02:00", "does not exist"),
        ("2024-03-10 02:30", "does not exist"),
        ("2006-04-02 02:30", "does not exist"),  # pre-2007 spring forward
        ("2024-11-03 01:00", "happened twice"),
        ("2024-11-03 01:30", "happened twice"),
    ],
)
def test_parse_eastern_rejects_dst_gaps(text, message):
    with pytest.raises(ValueError, match=message):
        parse_eastern(text)


def test_dst_error_in_leak_column(tmp_path):
    with pytest.raises(ValueError, match="leak_datetime_et: 2024-03-10 02:30 does not exist"):
        load_one(
            tmp_path,
            leak_datetime_et="2024-03-10 02:30",
            leak_source_url="https://example.com/leak",
        )


def test_leak_compared_as_moments_across_fall_back(tmp_path):
    # 00:30 EDT is earlier than 02:00 EST by 2.5 real hours.
    row = load_one(
        tmp_path,
        announcement_datetime_et="2024-11-03 02:00",
        leak_datetime_et="2024-11-03 00:30",
        leak_source_url="https://example.com/leak",
    )
    assert row["announcement_datetime_et"] - row["leak_datetime_et"] == pd.Timedelta(hours=2.5)


# --- Bad rows -----------------------------------------------------------------

LEAK = {"leak_datetime_et": "2024-06-03 10:00", "leak_source_url": "https://example.com/leak"}


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"event_id": ""}, "event_id is blank"),
        ({"announcement_datetime_et": ""}, "announcement_datetime_et is blank"),
        ({"announcement_datetime_et": "2024-06-04T10:00"}, "not in the format"),
        ({"announcement_datetime_et": "2024-06-04 10:00:00"}, "not in the format"),
        ({"announcement_datetime_et": "2024-6-4 10:00"}, "not in the format"),
        ({"announcement_datetime_et": "06/04/2024 10:00"}, "not in the format"),
        ({"announcement_datetime_et": "2024-06-04 10:00-04:00"}, "not in the format"),
        ({"announcement_datetime_et": "2024-02-30 10:00"}, "not a real date"),
        ({"announcement_datetime_et": "2024-06-04 25:00"}, "not a real date"),
        ({"leak_datetime_et": "2024-06-03 10:00"}, "both be filled or both blank"),
        ({"leak_source_url": "https://example.com/leak"}, "both be filled or both blank"),
        (LEAK | {"leak_datetime_et": "2024-06-04 10:00"}, "not earlier than"),
        (LEAK | {"leak_datetime_et": "2024-06-05 10:00"}, "not earlier than"),
        ({"decision_group": "opec"}, "decision_group is 'opec'"),
        ({"direction": "cuts"}, "direction is 'cuts'"),
        ({"surprise_flag": "2"}, "surprise_flag is '2'"),
        ({"surprise_flag": "yes"}, "surprise_flag is 'yes'"),
        ({"source_url": ""}, "source_url is blank"),
        # Before the trading calendar starts, so event_day_zero raises.
        ({"announcement_datetime_et": "1999-06-01 10:00"}, "has year 1999, outside the supported range 2000 to"),
    ],
)
def test_bad_row_raises(tmp_path, changes, message):
    with pytest.raises(ValueError, match=message):
        load_one(tmp_path, **changes)


def test_duplicate_event_id(tmp_path):
    path = write_events(tmp_path, [valid_row(), valid_row()])
    with pytest.raises(ValueError, match=r"'test_event_1' is used more than once \(lines 2, 3\)"):
        load_events(path)


def test_all_problems_reported_together(tmp_path):
    rows = [
        valid_row(event_id="ok"),
        valid_row(event_id="bad_a", direction="cuts"),
        valid_row(event_id="bad_b", source_url="", announcement_datetime_et="2024-11-03 01:30"),
    ]
    with pytest.raises(ValueError) as caught:
        load_events(write_events(tmp_path, rows))
    message = str(caught.value)
    assert "3 problem(s)" in message
    assert "line 3 (bad_a): direction" in message
    assert "line 4 (bad_b): announcement_datetime_et" in message
    assert "line 4 (bad_b): source_url is blank" in message


def test_missing_column(tmp_path):
    columns = [c for c in REQUIRED_COLUMNS if c != "source_url"]
    row = {c: v for c, v in valid_row().items() if c != "source_url"}
    with pytest.raises(ValueError, match="missing column.*source_url"):
        load_events(write_events(tmp_path, [row], columns=columns))
