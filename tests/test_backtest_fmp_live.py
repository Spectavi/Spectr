import pandas as pd
import pytest

from spectr.fetch.fmp import FMPInterface
import spectr.spectr as spectr_module


def _date_window(days: int) -> tuple[str, str]:
    """Return (start, end) ISO dates spanning ``days`` ending today."""
    end_ts = pd.Timestamp.today().normalize()
    start_ts = end_ts - pd.Timedelta(days=days - 1)
    return start_ts.date().isoformat(), end_ts.date().isoformat()


def test_fmp_backtest_fetches_requested_range_live():
    try:
        api = FMPInterface()
    except ValueError:
        pytest.skip("DATA_API_KEY not configured for FMPInterface")

    start, end = _date_window(3)

    try:
        df = api.fetch_chart_data_for_backtest(
            "AAPL", from_date=start, to_date=end, interval="5min"
        )
    except Exception as exc:
        pytest.skip(f"FMP live request failed: {exc}")

    assert not df.empty

    covers, (data_from, data_to, req_from, req_to) = spectr_module._index_covers_date_range(
        df.index, start, end
    )
    assert covers, f"Data {data_from} → {data_to} did not cover requested {req_from} → {req_to}"


@pytest.mark.parametrize(
    ("days", "interval"),
    [
        (30, "1min"),
        (180, "5min"),
        (365, "5min"),
    ],
)
def test_fmp_backtest_longer_ranges_live(days, interval):
    try:
        api = FMPInterface()
    except ValueError:
        pytest.skip("DATA_API_KEY not configured for FMPInterface")

    start, end = _date_window(days)

    try:
        df = api.fetch_chart_data_for_backtest(
            "AAPL", from_date=start, to_date=end, interval=interval
        )
    except Exception as exc:
        pytest.skip(f"FMP live request failed: {exc}")

    assert not df.empty

    covers, (data_from, data_to, req_from, req_to) = spectr_module._index_covers_date_range(
        df.index, start, end
    )
    assert covers, f"[{interval}] Data {data_from} → {data_to} did not cover requested {req_from} → {req_to}"
