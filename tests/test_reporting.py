"""Tests for the chart and run-info helpers in src/event_study/reporting.py."""

import math

import matplotlib.image
import pandas as pd
import pytest

from event_study.reporting import (
    car_interval,
    draw_event_car_dots,
    draw_move_timing_chart,
    draw_social_preview,
    file_sha256,
    percent_label,
    signed,
    split_car,
)


def test_file_sha256_ignores_crlf_versus_lf(tmp_path):
    """A CSV checked out with Windows line endings hashes like the LF original."""
    lf = tmp_path / "lf.csv"
    crlf = tmp_path / "crlf.csv"
    lf.write_bytes(b"event_id,reason\na,first\nb,second\n")
    crlf.write_bytes(b"event_id,reason\r\na,first\r\nb,second\r\n")
    assert file_sha256(lf) == file_sha256(crlf)


def test_file_sha256_still_changes_with_content(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_bytes(b"event_id,reason\r\na,first\r\n")
    second.write_bytes(b"event_id,reason\r\na,First\r\n")
    assert file_sha256(first) != file_sha256(second)
    # A lone carriage return is content, not a Windows line ending.
    lone = tmp_path / "lone.csv"
    plain = tmp_path / "plain.csv"
    lone.write_bytes(b"event_id,reason\ra,first\n")
    plain.write_bytes(b"event_id,reason\na,first\n")
    assert file_sha256(lone) != file_sha256(plain)


def test_percent_label_keeps_half_percent_ticks_apart():
    """Ticks 0.5% apart get distinct labels (they used to round to "2%, 2%")."""
    labels = [percent_label(x) for x in (0.0, 0.005, 0.01, 0.015, 0.02, 0.025)]
    assert labels == ["0%", "0.5%", "1%", "1.5%", "2%", "2.5%"]


def test_percent_label_whole_percents_unchanged():
    assert percent_label(0.04) == "4%"
    assert percent_label(-0.12) == "−12%"


def test_percent_label_float_noise_and_negative_zero():
    assert percent_label(0.015000000000000001) == "1.5%"
    assert percent_label(-0.0) == "0%"
    assert percent_label(-0.005) == "−0.5%"


def abnormal_table() -> pd.DataFrame:
    """Two events, days -2 to +1, with the column names read back from a CSV."""
    return pd.DataFrame(
        {"-2": [0.01, 0.03], "-1": [0.02, 0.00], "0": [0.005, -0.01], "1": [0.0, 0.02]},
        index=pd.Index(["a", "b"], name="event_id"),
    )


def test_split_car_before_and_from_day0():
    """a: before 0.03, after 0.005; b: before 0.03, after 0.01. Means 0.03 and 0.0075."""
    before, after = split_car(abnormal_table())
    assert before == pytest.approx(0.03)
    assert after == pytest.approx(0.0075)
    # The two parts add up to the mean CAR over every day.
    assert before + after == pytest.approx(abnormal_table().sum(axis=1).mean())


def test_signed_uses_unicode_minus():
    assert signed(0.031) == "+3.10%"
    assert signed(-0.0282) == "−2.82%"


def results_table() -> pd.DataFrame:
    """Two ok events and one failed one, with a [-1,+1] CAR and resid_std."""
    return pd.DataFrame(
        {
            "event_id": ["opec_2020_01_02", "opec_2021_03_04", "opec_2022_05_06"],
            "direction": ["cut", "increase", "cut"],
            "status": ["ok", "ok", "failed"],
            "resid_std": [0.01, 0.02, float("nan")],
            "car_[-1,+1]": [0.03, -0.02, float("nan")],
        }
    )


def test_car_interval_matches_the_per_event_t():
    """Standard error = resid_std * sqrt(3) on [-1,+1], as in market_model.car_test."""
    rows = results_table().iloc[:2]
    interval = car_interval(rows, (-1, 1))
    se = 0.01 * math.sqrt(3)
    assert interval.loc[0, "low"] == pytest.approx(0.03 - 1.96 * se)
    assert interval.loc[0, "high"] == pytest.approx(0.03 + 1.96 * se)
    assert list(interval["event_id"]) == ["opec_2020_01_02", "opec_2021_03_04"]


def test_charts_write_png_files(tmp_path):
    """Each chart function saves a file; a failed event (no CAR) does not stop the dot chart."""
    timing = tmp_path / "timing.png"
    draw_move_timing_chart({"Group": abnormal_table()}, timing, title="T", caption="C")
    dots = tmp_path / "dots.png"
    draw_event_car_dots(
        results_table(),
        dots,
        window=(-1, 1),
        group_column="direction",
        group_labels={"cut": "Cuts", "increase": "Increases"},
        colors={"cut": "#2a78d6", "increase": "#eb6834"},
        title="T",
        xlabel="X",
        caption="C",
    )
    assert timing.stat().st_size > 0
    assert dots.stat().st_size > 0


def test_social_preview_is_1280_by_640(tmp_path):
    """GitHub asks for a 1280 x 640 image (at least 640 x 320, 2:1)."""
    path = tmp_path / "preview.png"
    draw_social_preview(
        {"Group": abnormal_table()},
        path,
        title="T",
        subtitle="S",
        footer="F",
        url="U",
        chart_title="C",
    )
    height, width = matplotlib.image.imread(path).shape[:2]
    assert (width, height) == (1280, 640)
