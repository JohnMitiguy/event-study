"""Tests for the chart helpers in src/event_study/reporting.py."""

from event_study.reporting import percent_label


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
