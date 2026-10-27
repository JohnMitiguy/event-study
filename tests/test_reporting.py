"""Tests for the chart and run-info helpers in src/event_study/reporting.py."""

from event_study.reporting import file_sha256, percent_label


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
