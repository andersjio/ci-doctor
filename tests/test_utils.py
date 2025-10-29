from datetime import datetime, timezone, timedelta
from ci_doctor.utils import iso_to_dt, duration_ms, median_ms, human_ms


def test_iso_to_dt_z_and_offset():
    dt_z = iso_to_dt("2024-01-01T00:00:00Z")
    dt_off = iso_to_dt("2024-01-01T00:00:00+00:00")
    assert dt_z == dt_off


def test_duration_ms():
    start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(seconds=90)
    assert duration_ms(start, end) == 90000


def test_median_ms():
    assert median_ms([]) == 0
    assert median_ms([1]) == 1
    assert median_ms([1, 3, 2]) == 2
    assert median_ms([1, 2, 3, 4]) == 2  # floor of mean of middle pair


def test_human_ms():
    assert human_ms(None) == "n/a"
    assert human_ms(15_000) == "15s"
    assert human_ms(125_000) == "2m05s"
    assert human_ms(3_900_000) == "1h05m"


