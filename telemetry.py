from __future__ import annotations

import os
from contextlib import contextmanager
from time import perf_counter

from prometheus_client import Counter, Gauge, Histogram, start_http_server

REQUESTS = Counter("ops_analysis_requests_total", "Analysis requests", ["agent", "status"])
LATENCY = Histogram("ops_analysis_duration_seconds", "Analysis duration", ["agent"])
FORECAST_RMSE = Gauge("ops_forecast_rmse", "Latest forecast RMSE", ["kpi"])

_started = False


def start_metrics_server() -> None:
    global _started
    if not _started:
        try:
            start_http_server(int(os.getenv("METRICS_PORT", "8000")))
            _started = True
        except OSError:
            pass


@contextmanager
def observe(agent: str):
    started = perf_counter()
    try:
        yield
        REQUESTS.labels(agent=agent, status="success").inc()
    except Exception:
        REQUESTS.labels(agent=agent, status="error").inc()
        raise
    finally:
        LATENCY.labels(agent=agent).observe(perf_counter() - started)


def log_forecast_run(kpi: str, periods: int, rmse: float) -> None:
    FORECAST_RMSE.labels(kpi=kpi).set(rmse)
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        return
    try:
        import mlflow
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment("operations-performance-forecasting")
        with mlflow.start_run():
            mlflow.log_params({"model": "holt_winters", "kpi": kpi, "forecast_periods": periods})
            mlflow.log_metric("in_sample_rmse", rmse)
    except Exception:
        # Analytics must remain available if observability is temporarily unavailable.
        return

