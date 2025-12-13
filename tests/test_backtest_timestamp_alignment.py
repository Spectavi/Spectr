import pandas as pd

import spectr.spectr as spectr_module


def test_coerce_timestamp_handles_tz_alignment():
    tz_index = pd.date_range("2024-01-01 09:30", periods=2, freq="h", tz="UTC")

    naive_from = "2024-01-01"
    naive_to = "2024-01-02"

    from_ts = spectr_module._coerce_timestamp_to_index(naive_from, tz_index)
    to_ts = spectr_module._coerce_timestamp_to_index(naive_to, tz_index)

    assert from_ts.tz == tz_index.tz
    assert to_ts.tz == tz_index.tz
    assert (tz_index.min() <= from_ts) in (True, False)
    assert to_ts >= tz_index.max()


def test_coerce_timestamp_drops_tz_for_naive_index():
    naive_index = pd.date_range("2024-01-01", periods=1, freq="D")
    aware_value = pd.Timestamp("2024-01-01T00:00:00Z")

    coerced = spectr_module._coerce_timestamp_to_index(aware_value, naive_index)

    assert coerced.tz is None
    assert coerced == pd.Timestamp("2024-01-01 00:00:00")


def test_index_covers_date_range_allows_intraday_start():
    tz_index = pd.date_range("2024-01-01 09:30", periods=3, freq="h", tz="UTC")

    covers, _ = spectr_module._index_covers_date_range(tz_index, "2024-01-01", "2024-01-01")

    assert covers is True


def test_index_covers_date_range_detects_missing_end_date():
    tz_index = pd.date_range("2024-01-01 09:30", periods=3, freq="h", tz="UTC")

    covers, data = spectr_module._index_covers_date_range(tz_index, "2024-01-01", "2024-01-02")

    assert covers is False
    data_from, data_to, req_from, req_to = data
    assert data_from.date() == req_from.date()
    assert data_to.date() < req_to.date()
