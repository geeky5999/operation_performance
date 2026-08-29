import pandas as pd

from analytics import forecast_series, reactive_analysis


def sample_data():
    return pd.read_csv("sample_data/operations_kpis.csv")


def test_reactive_finds_may_drop():
    out = reactive_analysis(sample_data(), "date", "fulfillment_rate")
    assert str(out["worst_date"].date()) == "2025-05-01"
    assert out["worst_value"] == 84.1


def test_forecast_horizon():
    out = forecast_series(sample_data(), "date", "order_volume", 3)
    assert len(out["forecast"]) == 3
    assert out["rmse"] >= 0

