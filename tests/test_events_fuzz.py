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

pandas' own parse errors (EmptyDataError, ParserError) and
UnicodeDecodeError are all subclasses of ValueError, so they count as
ValueError here.
"""

import csv
import io
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import assume, given
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
    # Known bug, kept out so it doesn't hide other failures: times from
    # 9999-12-31 19:00 raise NotImplementedError (see
    # test_last_evening_of_year_9999_raises_value_error).
).filter(lambda cell: not cell.startswith("9999-12-31"))


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


def hits_index_column_bug(data: bytes) -> bool:
    """True for files that trigger the known bug in
    test_extra_field_on_every_row_with_repeated_id.

    When every data row has one more field than the header, pandas uses the
    first field as the row index (so it is no longer 0, 1, 2, ...). If the
    event_id column then has a repeated value, the loader crashes with
    TypeError. The fuzz tests skip exactly these files (hypothesis.assume),
    so that bug doesn't make them fail at random and hide new problems.
    """
    try:
        table = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)
    except ValueError:
        return False
    if isinstance(table.index, pd.RangeIndex) or "event_id" not in table.columns:
        return False
    ids = table["event_id"].str.strip()
    return bool((ids.duplicated(keep=False) & (ids != "")).any())


def assert_readable(err: ValueError) -> None:
    """A message a person can act on: non-empty text, not a bare repr."""
    message = str(err).strip()
    assert message, f"{type(err).__name__} with an empty message"
    assert any(ch.isalpha() for ch in message)


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
    assume(not hits_index_column_bug(data))
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
    data = buffer.getvalue().encode("utf-8")
    assume(not hits_index_column_bug(data))
    events, err = load_bytes(data, use_leak)
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


# --- Known problems (expected to fail until fixed) ----------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "pandas' C parser cuts a field at a NUL byte and drops the rest, so "
        "'abc\\x00def' loads as 'abc' with no error. A bad file should not "
        "load partly changed."
    ),
)
# A NUL inside a time cuts it short and the format check catches it, so
# only free-text columns are tested.
@pytest.mark.parametrize("column", ["event_id", "source_url", "notes"])
def test_nul_byte_in_a_field_is_rejected(column):
    original = valid_row()[column]
    damaged = original[:4] + "\x00" + original[4:]
    data = csv_text([valid_row(**{column: damaged})]).encode()
    _, err = load_bytes(data)
    assert err is not None, "file with a NUL byte loaded without error"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "pandas' EmptyDataError, ParserError and UnicodeDecodeError reach the "
        "caller unwrapped. They are ValueErrors, but unlike the loader's own "
        "messages they don't name the events file, and the wording is the "
        "parser's ('Error tokenizing data. C error: ...', \"'utf-8' codec "
        "can't decode byte 0xff ...\")."
    ),
)
@pytest.mark.parametrize(
    "name", ["empty file", "stray comma in second row", "unterminated quote", "utf-16"]
)
def test_parser_errors_name_the_file(name):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "events.csv"
        path.write_bytes(RAISES[name])
        with pytest.raises(ValueError) as info:
            load_events(path)
    assert str(path) in str(info.value)


@pytest.mark.xfail(
    strict=True,
    raises=TypeError,
    reason=(
        "When every data row has one field more than the header (e.g. a "
        "trailing comma on each row), pandas silently uses the first column "
        "as the row index and shifts the rest left. _duplicate_id_errors then "
        "computes 'i + 2' on a text index label and raises TypeError if the "
        "shifted event_id column has a repeated value."
    ),
)
def test_extra_field_on_every_row_with_repeated_id():
    # Two events announced at the same time, each line ending in a comma.
    # After the shift, event_id holds the (repeated) announcement time.
    rows = [valid_row(event_id="test_event_1"), valid_row(event_id="test_event_2")]
    lines = csv_text(rows).splitlines()
    text = lines[0] + "\n" + "".join(line + ",\n" for line in lines[1:])
    _, err = load_bytes(text.encode())
    assert err is not None


@pytest.mark.xfail(
    strict=True,
    raises=NotImplementedError,
    reason=(
        "parse_eastern calls tz_localize, which raises NotImplementedError "
        "(not ValueError) for 9999-12-31 19:00 or later: in UTC that is "
        "year 10000. load_events only collects ValueErrors, so the whole load "
        "crashes instead of listing the row's problem."
    ),
)
@pytest.mark.parametrize("column", ["announcement_datetime_et", "leak_datetime_et"])
def test_last_evening_of_year_9999_raises_value_error(column):
    row = valid_row(**{column: "9999-12-31 23:59"})
    if column == "leak_datetime_et":
        row["leak_source_url"] = "https://example.com/leak"
    _, err = load_bytes(csv_text([row]).encode())
    assert err is not None


@pytest.mark.xfail(
    strict=True,
    reason=(
        "For early years (at least 0001-1000) tz_localize returns NaT, which "
        "parse_eastern reads as the daylight-saving gap, so a typo like "
        "0224-06-04 is reported as 'clocks jumped from 2:00 to 3:00' instead "
        "of as a bad or out-of-range date."
    ),
)
def test_typo_year_is_not_blamed_on_daylight_saving():
    row = valid_row(announcement_datetime_et="0224-06-04 10:00")
    _, err = load_bytes(csv_text([row]).encode())
    assert err is not None
    assert "daylight saving" not in str(err)
