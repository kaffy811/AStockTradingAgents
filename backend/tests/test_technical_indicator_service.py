"""Deterministic checks of the indicator contract consumed by technical agents."""

from datetime import date, timedelta
import json

import pytest

from app.services.technical_indicator_service import TechnicalIndicatorService


pytestmark = pytest.mark.unit


@pytest.fixture
def service():
    return TechnicalIndicatorService()


def _bars(closes, volumes=None):
    """Build chronological bars without using the calculation under test."""
    if volumes is None:
        volumes = [100] * len(closes)
    return [
        {
            "date": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
            "close": close,
            "high": float(close) + 2,
            "low": float(close) - 2,
            "volume": volume,
        }
        for i, (close, volume) in enumerate(zip(closes, volumes, strict=True))
    ]


def test_moving_averages_returns_and_price_positions(service):
    result = service.calculate(_bars(list(range(1, 81))))

    # The last five closes are 76..80; the 5/20-period bases are 75/60.
    expected = {
        "bar_count": 80,
        "latest_date": "2026-03-21",
        "latest_close": 80.0,
        "ma5": 78.0,
        "ma10": 75.5,
        "ma20": 70.5,
        "ma60": 50.5,
        "return_1d_pct": 1.27,
        "return_5d_pct": 6.67,
        "return_20d_pct": 33.33,
        "price_vs_ma20_pct": 13.48,
        "price_vs_ma60_pct": 58.42,
        "short_term_trend": "上升",
        "medium_term_trend": "上升",
    }
    for key, value in expected.items():
        assert result[key] == value, key


@pytest.mark.parametrize("window", [5, 10, 20, 60])
def test_moving_average_requires_a_complete_window(service, window):
    key = f"ma{window}"
    assert service.calculate(_bars([10] * (window - 1)))[key] is None
    assert service.calculate(_bars([10] * window))[key] == 10.0


@pytest.mark.parametrize("period", [1, 5, 20])
@pytest.mark.parametrize(("latest", "expected"), [(12, 20.0), (8, -20.0)])
def test_return_requires_one_more_close_than_the_period(service, period, latest, expected):
    key = f"return_{period}d_pct"
    assert service.calculate(_bars([10] * period))[key] is None
    result = service.calculate(_bars([10] * period + [latest]))
    assert result[key] == expected


def test_highs_and_lows_use_the_latest_window(service):
    bars = _bars(list(range(1, 81)))
    # Index 0 is outside both windows; index 30 is only in the 60-bar window.
    bars[0].update(high=9999, low=-9999)
    bars[30].update(high=500, low=0.5)
    result = service.calculate(bars)

    assert result["high_20d"] == 82.0
    assert result["low_20d"] == 59.0
    assert result["high_60d"] == 500.0
    assert result["low_60d"] == 0.5


def test_short_history_still_provides_available_range_extremes(service):
    result = service.calculate(_bars([10, 15, 12]))
    assert result["ma5"] is None
    assert result["high_20d"] == result["high_60d"] == 17.0
    assert result["low_20d"] == result["low_60d"] == 8.0


def test_volume_averages_and_ratios_include_the_latest_bar(service):
    result = service.calculate(_bars([10] * 20, [100] * 15 + [200] * 5))
    assert result["volume_latest"] == 200.0
    assert result["volume_avg_5d"] == 200.0
    assert result["volume_avg_20d"] == 125.0
    assert result["volume_ratio_5_20"] == 1.6
    assert result["volume_ratio_today"] == 1.0
    assert result["volume_signal"] == "近期放量"


@pytest.mark.parametrize(
    ("volumes", "signal"),
    [
        ([100] * 19 + [1000], "单日明显放量"),
        ([200] * 15 + [100] * 5, "近期缩量"),
        ([100] * 20, "量能平稳"),
        ([7] * 15 + [9] * 5, "量能平稳"),  # ratio == 1.2
        ([16] * 15 + [12] * 5, "量能平稳"),  # ratio == 0.8
        ([200] * 15 + [85] * 4 + [160], "单日明显放量"),
        ([100] * 15 + [87.5] * 4 + [150], "量能平稳"),  # today ratio == 1.5
    ],
    ids=["spike", "contraction", "flat", "upper-bound", "lower-bound", "spike-priority", "today-bound"],
)
def test_volume_signal_thresholds_and_priority(service, volumes, signal):
    result = service.calculate(_bars([10] * 20, volumes))
    assert result["volume_signal"] == signal


@pytest.mark.parametrize(
    ("fast_close", "trend"),
    [(1004, "上升"), (1003, "横盘"), (1000, "横盘"), (997, "横盘"), (996, "下降")],
)
def test_trend_thresholds(service, fast_close, trend):
    # MA10 is exactly 1000, so MA5 == 1003/997 gives exactly +/-0.3%.
    bars = _bars([2000 - fast_close] * 5 + [fast_close] * 5)
    assert service.calculate(bars)["short_term_trend"] == trend


def test_zero_denominators_produce_none_without_division_errors(service):
    result = service.calculate(_bars([0] * 21, [0] * 21))
    for key in (
        "return_1d_pct", "return_5d_pct", "return_20d_pct",
        "price_vs_ma20_pct", "price_vs_ma60_pct",
        "volume_ratio_5_20", "volume_ratio_today",
    ):
        assert result[key] is None, key
    assert result["ma20"] == 0.0
    assert result["volume_avg_20d"] == 0.0
    assert result["short_term_trend"] == "数据不足"
    assert result["volume_signal"] == "数据不足"


def test_close_only_bars_preserve_price_indicators(service):
    result = service.calculate([{"close": "10.5"} for _ in range(20)])
    assert result["ma20"] == 10.5
    assert result["return_1d_pct"] == 0.0
    assert result["short_term_trend"] == "横盘"
    for key in (
        "high_20d", "low_20d", "high_60d", "low_60d", "volume_latest",
        "volume_avg_5d", "volume_avg_20d", "volume_ratio_5_20", "volume_ratio_today",
    ):
        assert result[key] is None, key
    assert result["volume_signal"] == "数据不足"
    assert json.loads(json.dumps(result, allow_nan=False)) == result


@pytest.mark.parametrize(
    "bars",
    [[], [{}, {"close": None}, {"close": "bad"}, {"close": float("nan")}]],
    ids=["empty", "no-valid-closes"],
)
def test_no_valid_prices_returns_a_stable_json_schema(service, bars):
    result = service.calculate(bars)
    assert result.keys() == service.calculate(_bars([10] * 60)).keys()
    assert result["bar_count"] == 0
    for key, value in result.items():
        if key.endswith("trend") or key == "volume_signal":
            assert value == "数据不足", key
        elif key != "bar_count":
            assert value is None, key
    assert json.loads(json.dumps(result, allow_nan=False)) == result
