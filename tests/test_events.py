"""Tests for the events loader. Every row here is fake (example.com sources)."""

import csv
from pathlib import Path

import pandas as pd
import pytest

from event_study.events import (
    MASK_COLUMNS,
    REQUIRED_COLUMNS,
    load_events,
    load_mask_events,
    main_and_shifted_day0s,
    parse_eastern,
)

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
        "time_assumed": "",
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
    for column in [*REQUIRED_COLUMNS, "event_time", "used_leak", "day0", "time_assumed"]:
        assert column in events.columns


# --- time_assumed ------------------------------------------------------------


def test_time_assumed_defaults_to_false_and_parses(tmp_path):
    assert not load_one(tmp_path)["time_assumed"]
    assert load_one(tmp_path, time_assumed="1")["time_assumed"]
    assert not load_one(tmp_path, time_assumed="0")["time_assumed"]


def test_time_assumed_rejects_other_values(tmp_path):
    with pytest.raises(ValueError, match="time_assumed is 'yes'"):
        load_one(tmp_path, time_assumed="yes")


def test_time_assumed_with_leak_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="time_assumed is 1 but the row has a leak time"):
        load_one(
            tmp_path,
            time_assumed="1",
            leak_datetime_et="2024-06-04 09:00",
            leak_source_url="https://example.com/leak",
        )


def shifted_day0(tmp_path, announced, time_assumed):
    path = write_events(
        tmp_path, [valid_row(announcement_datetime_et=announced, time_assumed=time_assumed)]
    )
    return load_events(path, shift_assumed=True).iloc[0]["day0"]


def test_shift_moves_only_time_assumed_rows(tmp_path):
    # Tue 2024-06-04 10:00: day 0 is that Tuesday, shifted to Wednesday.
    assert shifted_day0(tmp_path, "2024-06-04 10:00", "1") == pd.Timestamp("2024-06-05")
    assert shifted_day0(tmp_path, "2024-06-04 10:00", "0") == pd.Timestamp("2024-06-04")
    # Without the option nothing moves.
    assert load_one(tmp_path, time_assumed="1")["day0"] == pd.Timestamp("2024-06-04")


def test_shift_skips_weekend_and_holiday(tmp_path):
    # Fri 2024-05-24 12:00 -> Mon 27 May is Memorial Day -> Tue 28 May.
    assert shifted_day0(tmp_path, "2024-05-24 12:00", "1") == pd.Timestamp("2024-05-28")


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
        # Before the trading calendar starts, so the year-range check raises
        # first, before event_day_zero is ever called.
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


# --- Mask-only file ------------------------------------------------------------

REAL_MASK_CSV = REAL_EVENTS_CSV.parent / "opec_mask_only.csv"


def mask_row(**changes) -> dict:
    """A fake mask-only row that passes every check (Tuesday, 10:00)."""
    row = {
        "event_id": "mask_1",
        "announcement_datetime_et": "2024-06-04 10:00",
        "time_assumed": "",
        "source_url": "https://example.com/release",
        "reason": "fake row for tests",
    }
    return row | changes


def load_masks(tmp_path: Path, rows: list[dict], shift_assumed: bool = False) -> pd.DataFrame:
    return load_mask_events(write_events(tmp_path, rows, MASK_COLUMNS), shift_assumed)


def test_real_csv_and_mask_file_load():
    """The committed files pass every check (a typo there would stop the run)."""
    events = load_events(REAL_EVENTS_CSV)
    masks = load_mask_events(REAL_MASK_CSV)
    assert events["event_id"].is_unique and masks["event_id"].is_unique
    # A mask row is never also a tested event.
    assert not set(masks["event_id"]) & set(events["event_id"])


def test_mask_day0_rolls_like_an_event(tmp_path):
    # Friday 5 Jul 2024 10:00 is a session; Thursday 4 Jul is a holiday.
    masks = load_masks(
        tmp_path,
        [
            mask_row(event_id="a", announcement_datetime_et="2024-07-04 10:00"),
            mask_row(event_id="b", announcement_datetime_et="2024-06-04 16:00"),
        ],
    )
    assert masks["day0"].tolist() == [pd.Timestamp("2024-07-05"), pd.Timestamp("2024-06-05")]
    assert masks["time_assumed"].tolist() == [False, False]


def test_mask_shift_moves_only_time_assumed_rows(tmp_path):
    rows = [mask_row(event_id="a", time_assumed="1"), mask_row(event_id="b", time_assumed="0")]
    masks = load_masks(tmp_path, rows, shift_assumed=True)
    assert masks["day0"].tolist() == [pd.Timestamp("2024-06-05"), pd.Timestamp("2024-06-04")]


def test_main_and_shifted_day0s_adds_the_next_session_of_time_assumed_rows_only(tmp_path):
    rows = [
        mask_row(event_id="firm"),  # Tuesday 2024-06-04 10:00
        mask_row(event_id="assumed", announcement_datetime_et="2024-06-14 12:00", time_assumed="1"),
        mask_row(event_id="zero", announcement_datetime_et="2024-07-09 10:00", time_assumed="0"),
    ]
    path = write_events(tmp_path, rows, MASK_COLUMNS)
    day0s = main_and_shifted_day0s(load_mask_events(path), load_mask_events(path, True))
    # Friday 14 Jun 2024: the shifted day 0 is Monday 17 Jun.
    assert day0s.tolist() == [
        pd.Timestamp("2024-06-04"),
        pd.Timestamp("2024-06-14"),
        pd.Timestamp("2024-07-09"),
        pd.Timestamp("2024-06-17"),
    ]


def test_main_and_shifted_day0s_works_on_events_files(tmp_path):
    rows = [
        valid_row(event_id="firm"),
        valid_row(event_id="assumed", announcement_datetime_et="2024-09-10 12:00", time_assumed="1"),
    ]
    path = write_events(tmp_path, rows)
    day0s = main_and_shifted_day0s(load_events(path), load_events(path, shift_assumed=True))
    assert day0s.tolist() == [
        pd.Timestamp("2024-06-04"),
        pd.Timestamp("2024-09-10"),
        pd.Timestamp("2024-09-11"),
    ]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"reason": ""}, "reason is blank"),
        ({"source_url": ""}, "source_url is blank"),
        ({"time_assumed": "yes"}, "time_assumed is 'yes'"),
        ({"announcement_datetime_et": "2024-06-04"}, "not in the format"),
    ],
)
def test_bad_mask_row_raises(tmp_path, changes, message):
    with pytest.raises(ValueError, match=rf"(?s)mask-only file .*line 2 \(mask_1\): .*{message}"):
        load_masks(tmp_path, [mask_row(**changes)])


def test_mask_file_duplicate_id_and_missing_column(tmp_path):
    with pytest.raises(ValueError, match="'mask_1' is used more than once"):
        load_masks(tmp_path, [mask_row(), mask_row()])
    row = mask_row()
    del row["reason"]
    path = write_events(tmp_path, [row], MASK_COLUMNS[:-1])
    with pytest.raises(ValueError, match="missing column"):
        load_mask_events(path)
