"""Fuzz tests for load_events: random malformed CSV files.

The rule under test: load_events either returns a fully checked table or
raises ValueError with a readable message. It must never raise anything else
(KeyError, TypeError, IndexError, ...), because callers only expect
ValueError for a bad file.

hypothesis builds each file from valid rows (test_events.valid_row), then
damages it: junk or blank cells, wrong-looking dates, repeated event_ids,
dropped or shuffled columns, stray commas, quotes and newlines in the raw
text, different text encodings, and files cut off part way. Some examples
are plain random bytes.

Every error must also name the file: the loader's row checks start with
"events file <path>", and file-level problems (not UTF-8, NUL bytes, CSV
parse errors) start with the path itself.
"""

import csv
import io
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_events import valid_row

from event_study.event_days import nyse_calendar
from event_study.events import REQUIRED_COLUMNS, load_events

COLUMNS = list(REQUIRED_COLUMNS)
SESSIONS = nyse_calendar().sessions
ENCODINGS = ["utf-8", "utf-8-sig", "utf-16", "cp1252", "latin-1"]

# Times that look nearly right, or are right except for daylight saving or
# the calendar range.
NEAR_MISS_TIMES = [
    "2024-06-04",
    "2024-06-04 10:00:00",
    "2024-6-4 10:00",
    "2024-06-04T10:00",
    "06/04/2024 10:00",
    "2024-13-01 10:00",
    "2024-02-30 10:00",
    "2024-06-04 24:00",
    "2024-06-04 10:60",
    "2024-03-10 02:30",  # skipped by daylight saving
    "2024-11-03 01:30",  # happens twice
    "1999-12-31 10:00",  # before the trading calendar
    "2099-01-05 10:00",  # after the trading calendar
    "0000-01-01 00:00",
    "0224-06-04 10:00",  # 2024 with two digits swapped
    "9999-12-31 18:59",
    "9999-12-31 19:00",  # year 10000 in UTC
    "9999-12-31 23:59",
]

time_like = st.one_of(
    st.sampled_from(NEAR_MISS_TIMES),
    # The right shape with random numbers. Python's \d also matches
    # non-ASCII digits (Arabic-Indic, fullwidth...), which hypothesis uses.
    st.from_regex(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", fullmatch=True),
    st.text(alphabet="0123456789-: /T", max_size=20),
)
junk_cell = st.one_of(
    st.just(""),
    st.sampled_from([" ", ",", '"', "\n", "nan", "NA", "None", "\t"]),
    time_like,
    st.text(max_size=20),
)


@st.composite
def damaged_rows(draw) -> tuple[list[str], list[dict]]:
    """(header, rows) with random columns and cells changed."""
    columns = COLUMNS + draw(st.sampled_from([[], ["extra_column"]]))
    if draw(st.integers(0, 3)) == 0:
        dropped = draw(st.sets(st.sampled_from(columns), max_size=2))
        columns = [c for c in columns if c not in dropped]
    if draw(st.booleans()):
        columns = list(draw(st.permutations(columns)))

    rows = []
    for i in range(draw(st.integers(min_value=0, max_value=4))):
        row = valid_row(event_id=f"fuzz_{i}") | {"extra_column": "x"}
        for column in columns:
            # Roughly one cell in four gets damaged.
            if draw(st.integers(0, 3)) == 0:
                row[column] = draw(junk_cell)
        if rows and "event_id" in columns and draw(st.integers(0, 4)) == 0:
            row["event_id"] = rows[0]["event_id"]  # repeated id
        rows.append({c: row[c] for c in columns})
    return columns, rows


@st.composite
def damaged_text(draw) -> str:
    """CSV text from damaged_rows, then with raw characters inserted or removed.

    csv.writer quotes values properly; the raw edits afterwards are what a
    hand edit could do: an unquoted comma, a lone quote, a broken line.
    """
    columns, rows = draw(damaged_rows())
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator=draw(st.sampled_from(["\n", "\r\n", "\r"])))
    writer.writerow(columns)
    writer.writerows([row[c] for c in columns] for row in rows)
    text = buffer.getvalue()

    for _ in range(draw(st.integers(min_value=0, max_value=3))):
        position = draw(st.integers(min_value=0, max_value=len(text)))
        edit = draw(st.sampled_from([",", '"', "\n", ",,", "delete"]))
        if edit == "delete":
            text = text[:position] + text[position + 1 :]
        else:
            text = text[:position] + edit + text[position:]
    return text


@st.composite
def messy_csv(draw) -> bytes:
    """File contents: damaged CSV text in a random encoding, or random bytes."""
    if draw(st.integers(0, 9)) == 0:
        return draw(st.binary(max_size=300))
    text = draw(damaged_text())
    encoding = draw(st.sampled_from(ENCODINGS))
    # errors="replace" writes "?" for characters cp1252/latin-1 can't hold.
    data = text.encode(encoding, errors="replace")
    if draw(st.integers(0, 4)) == 0:
        data = data[: draw(st.integers(min_value=0, max_value=len(data)))]
    return data


def load_bytes(data: bytes, use_leak: bool = True):
    """Write data to a temporary events.csv and load it.

    Returns (events, None) if it loads or (None, err) if it raises ValueError.
    Any other exception is not caught, so it fails the test.

    tempfile is used instead of pytest's tmp_path because hypothesis calls the
    test many times and tmp_path would be shared across those calls.
    """
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "events.csv"
        path.write_bytes(data)
        try:
            return load_events(path, use_leak=use_leak), None
        except ValueError as err:
            return None, err


def assert_readable(err: ValueError) -> None:
    """A message a person can act on: non-empty text that names the file.

    load_bytes always names the file events.csv.
    """
    message = str(err).strip()
    assert message, f"{type(err).__name__} with an empty message"
    assert any(ch.isalpha() for ch in message)
    assert "events.csv" in message


def assert_checked(events: pd.DataFrame) -> None:
    """What a successfully loaded table must always satisfy."""
    for column in REQUIRED_COLUMNS:
        assert column in events.columns
    assert (events["event_id"] != "").all()
    assert events["event_id"].is_unique
    assert events["announcement_datetime_et"].notna().all()
    assert events["event_time"].notna().all()
    assert events["day0"].isin(SESSIONS).all()


@given(messy_csv(), st.booleans())
def test_messy_file_loads_cleanly_or_raises_value_error(data, use_leak):
    events, err = load_bytes(data, use_leak)
    if err is not None:
        assert_readable(err)
    else:
        assert_checked(events)


@given(damaged_rows(), st.booleans())
def test_damaged_cells_load_cleanly_or_raise_value_error(header_and_rows, use_leak):
    """Cell damage only, written as clean UTF-8: exercises the row checks
    rather than the CSV parser."""
    columns, rows = header_and_rows
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    events, err = load_bytes(buffer.getvalue().encode("utf-8"), use_leak)
    if err is not None:
        assert_readable(err)
    else:
        assert_checked(events)
        assert len(events) == len(rows)


# --- Specific nasty files -----------------------------------------------------


def csv_text(rows: list[dict], columns=COLUMNS) -> str:
    """Valid CSV text for these rows, header first."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


HEADER = ",".join(COLUMNS) + "\n"
GOOD_LINE = csv_text([valid_row()]).splitlines()[1] + "\n"
SECOND_LINE = GOOD_LINE.replace("test_event_1", "test_event_2")

RAISES = {
    "empty file": b"",
    "whitespace only": b"   \n\n",
    "missing column": csv_text(
        [{c: v for c, v in valid_row().items() if c != "source_url"}],
        [c for c in COLUMNS if c != "source_url"],
    ).encode(),
    "duplicate ids": (HEADER + GOOD_LINE + GOOD_LINE).encode(),
    "stray comma in second row": (HEADER + GOOD_LINE + SECOND_LINE.replace("fake", "fake,")).encode(),
    "trailing comma on every row": (HEADER + GOOD_LINE.replace("\n", ",\n")).encode(),
    "unterminated quote": (HEADER + '"' + GOOD_LINE).encode(),
    "utf-16": (HEADER + GOOD_LINE).encode("utf-16"),
    "cp1252 accent": (HEADER + GOOD_LINE.replace("fake row", "caf\xe9")).encode("cp1252"),
    "blank fields only": (HEADER + "," * (len(COLUMNS) - 1) + "\n").encode(),
    "header repeated as a row": (HEADER + GOOD_LINE + HEADER).encode(),
    "arabic-indic digits": csv_text(
        [valid_row(announcement_datetime_et="٢٠٢٤-٠٦-٠٤ ١٠:٠٠")]
    ).encode(),
    "fullwidth digits": csv_text(
        [valid_row(announcement_datetime_et="２０２４-０６-０４ １０:００")]
    ).encode(),
    "day 0 past the calendar": csv_text(
        # After the close on the calendar's last session: no next session.
        [valid_row(announcement_datetime_et=f"{SESSIONS[-1].date()} 17:00")]
    ).encode(),
}

LOADS = {
    "header only": HEADER.encode(),
    "utf-8 with byte order mark": (HEADER + GOOD_LINE).encode("utf-8-sig"),
    "old Mac line endings": (HEADER + GOOD_LINE).replace("\n", "\r").encode(),
    "Windows line endings": (HEADER + GOOD_LINE).replace("\n", "\r\n").encode(),
    "spaces around values": csv_text(
        [valid_row(event_id="  test_event_1 ", direction=" cut")]
    ).encode(),
}


@pytest.mark.parametrize("data", RAISES.values(), ids=RAISES.keys())
def test_nasty_file_raises_value_error(data):
    _, err = load_bytes(data)
    assert err is not None, "loaded without error"
    assert_readable(err)


@pytest.mark.parametrize("data", LOADS.values(), ids=LOADS.keys())
def test_harmless_variation_loads(data):
    events, err = load_bytes(data)
    assert err is None, str(err)
    assert_checked(events)




# --- Fixed problems found by the fuzz tests -----------------------------------

LAST_YEAR = SESSIONS[-1].year


def error_for(data: bytes) -> tuple[str, str]:
    """Load data from a temporary events.csv; return (its path, the error message).

    Fails the test if the file loads, or raises something other than ValueError.
    """
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "events.csv"
        path.write_bytes(data)
        with pytest.raises(ValueError) as info:
            load_events(path)
    return str(path), str(info.value)


@pytest.mark.parametrize(
    "name",
    [
        "empty file",
        "whitespace only",
        "stray comma in second row",
        "trailing comma on every row",
        "unterminated quote",
        "utf-16",
        "cp1252 accent",
    ],
)
def test_file_level_errors_start_with_the_path(name):
    path, message = error_for(RAISES[name])
    assert message.startswith(path)


@pytest.mark.parametrize("name", ["utf-16", "cp1252 accent"])
def test_wrong_encoding_says_utf8(name):
    _, message = error_for(RAISES[name])
    assert "UTF-8" in message


def test_missing_file_raises_value_error(tmp_path):
    path = tmp_path / "no_such_file.csv"
    with pytest.raises(ValueError) as info:
        load_events(path)
    assert str(info.value).startswith(str(path))
    assert "FileNotFoundError" in str(info.value)


@pytest.mark.parametrize(
    "column", ["event_id", "announcement_datetime_et", "source_url", "notes"]
)
def test_nul_byte_in_a_field_is_rejected(column):
    original = valid_row()[column]
    damaged = original[:4] + "\x00" + original[4:]
    path, message = error_for(csv_text([valid_row(**{column: damaged})]).encode())
    assert message.startswith(path)
    assert "NUL byte" in message
    assert "line 2" in message


def test_nul_byte_line_number_counts_every_line_ending():
    # Header, then two rows with \r\n endings; the NUL is in the second row.
    text = (HEADER + GOOD_LINE + SECOND_LINE.replace("fake", "fa\x00ke")).replace("\n", "\r\n")
    _, message = error_for(text.encode())
    assert "line 3" in message


@pytest.mark.parametrize(
    "lines",
    [
        # A trailing comma on each row: empty extra field.
        [GOOD_LINE.replace("\n", ",\n")],
        # Extra text on each row: would have been dropped silently.
        [GOOD_LINE.replace("\n", ",extra\n"), SECOND_LINE.replace("\n", ",extra\n")],
        # The old crash: once shifted, event_id held the same announcement
        # time twice and the duplicate check raised TypeError.
        [GOOD_LINE.replace("\n", ",\n"), SECOND_LINE.replace("\n", ",\n")],
    ],
    ids=["trailing comma", "extra text", "repeated value after shift"],
)
def test_extra_field_on_every_row_is_rejected(lines):
    path, message = error_for((HEADER + "".join(lines)).encode())
    assert message.startswith(path)
    assert "more fields than the header" in message


@pytest.mark.parametrize(
    "text",
    [
        "9999-12-31 23:59",  # used to raise NotImplementedError
        "9999-12-31 19:00",
        "0224-06-04 10:00",  # used to be blamed on daylight saving
        "0001-01-01 12:00",
        "1999-12-31 23:59",
        f"{LAST_YEAR + 1}-01-04 10:00",
    ],
)
@pytest.mark.parametrize("column", ["announcement_datetime_et", "leak_datetime_et"])
def test_year_outside_calendar_is_rejected(text, column):
    row = valid_row(**{column: text})
    if column == "leak_datetime_et":
        row["leak_source_url"] = "https://example.com/leak"
    _, message = error_for(csv_text([row]).encode())
    year = int(text[:4])
    assert f"line 2 (test_event_1): {column}: {text} has year {year}" in message
    assert f"supported range 2000 to {LAST_YEAR}" in message
    assert "daylight saving" not in message


@pytest.mark.parametrize(
    "text", ["2000-01-03 10:00", f"{SESSIONS[-2].date()} 10:00"], ids=["first", "last"]
)
def test_years_at_the_ends_of_the_range_still_load(text):
    events, err = load_bytes(csv_text([valid_row(announcement_datetime_et=text)]).encode())
    assert err is None, str(err)
    assert_checked(events)
