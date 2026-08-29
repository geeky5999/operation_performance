from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestRegressor
from sklearn.inspection import permutation_importance
from statsmodels.tsa.holtwinters import ExponentialSmoothing


def prepare_data(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    data = df.copy()
    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data = data.dropna(subset=[date_col]).sort_values(date_col)
    for col in data.columns:
        if col != date_col:
            data[col] = pd.to_numeric(data[col], errors="coerce")
    return data.reset_index(drop=True)


def reactive_analysis(df: pd.DataFrame, date_col: str, target: str) -> dict:
    data = prepare_data(df, date_col).dropna(subset=[target]).copy()
    if len(data) < 4:
        raise ValueError("Reactive analysis needs at least 4 valid observations.")

    x = data[[target]].to_numpy()
    contamination = min(0.2, max(1 / len(data), 0.05))
    model = IsolationForest(contamination=contamination, random_state=42)
    data["anomaly"] = model.fit_predict(x) == -1
    data["change_pct"] = data[target].pct_change() * 100

    numeric = data.select_dtypes(include=np.number).columns.tolist()
    drivers = [c for c in numeric if c not in {target, "change_pct"}]
    impact = []
    if drivers and len(data) >= 8:
        clean = data[[target] + drivers].dropna()
        if len(clean) >= 8:
            reg = RandomForestRegressor(n_estimators=250, random_state=42)
            reg.fit(clean[drivers], clean[target])
            result = permutation_importance(reg, clean[drivers], clean[target], n_repeats=10, random_state=42)
            impact = sorted(
                [{"driver": c, "importance": float(v)} for c, v in zip(drivers, result.importances_mean)],
                key=lambda z: abs(z["importance"]), reverse=True,
            )[:5]

    worst = data.loc[data[target].idxmin()]
    previous = data.loc[data[date_col] < worst[date_col], target]
    baseline = float(previous.tail(3).mean()) if not previous.empty else float(data[target].median())
    return {
        "data": data,
        "anomalies": data.loc[data["anomaly"], [date_col, target, "change_pct"]],
        "drivers": impact,
        "worst_date": worst[date_col],
        "worst_value": float(worst[target]),
        "baseline": baseline,
        "gap_pct": float((worst[target] - baseline) / baseline * 100) if baseline else np.nan,
    }


def forecast_series(df: pd.DataFrame, date_col: str, target: str, periods: int) -> dict:
    data = prepare_data(df, date_col).dropna(subset=[target]).copy()
    if len(data) < 6:
        raise ValueError("Forecasting needs at least 6 valid observations.")

    series = data.set_index(date_col)[target].astype(float)
    inferred = pd.infer_freq(series.index)
    freq = inferred or "MS"
    seasonal_periods = 12 if len(series) >= 24 and freq.upper().startswith("M") else None
    model = ExponentialSmoothing(
        series,
        trend="add",
        seasonal="add" if seasonal_periods else None,
        seasonal_periods=seasonal_periods,
        initialization_method="estimated",
    ).fit(optimized=True)
    prediction = model.forecast(periods)
    future_index = pd.date_range(series.index[-1], periods=periods + 1, freq=freq)[1:]
    prediction.index = future_index

    residuals = series - model.fittedvalues
    margin = 1.96 * float(residuals.std(ddof=1)) if len(residuals) > 2 else 0.0
    forecast = pd.DataFrame({
        date_col: future_index,
        "forecast": prediction.to_numpy(),
        "lower_95": prediction.to_numpy() - margin,
        "upper_95": prediction.to_numpy() + margin,
    })
    return {"history": data[[date_col, target]], "forecast": forecast, "rmse": float(np.sqrt(np.mean(residuals**2)))}

