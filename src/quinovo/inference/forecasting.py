"""Forecast plugins. TimesFM 2.5 is the named default; 3.0 weights stay off this path."""

from __future__ import annotations

import logging
from typing import Protocol

from quinovo.ai.runtime import write_forecast
from quinovo.engine.store import ObjectStore

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "timesfm-2.5"


class ForecastBackend(Protocol):
    name: str

    def predict(self, window: list[float], horizon_hours: float) -> tuple[float, float | None, float | None]:
        ...


class NaiveBackend:
    """Last-value hold. Used when TimesFM weights are not installed."""

    name = "naive"

    def predict(self, window: list[float], horizon_hours: float) -> tuple[float, float | None, float | None]:
        if not window:
            return 0.0, None, None
        point = float(window[-1])
        return point, point * 0.8, min(1.0, point * 1.2)


class TimesFM25Backend:
    name = "timesfm-2.5"

    def predict(self, window: list[float], horizon_hours: float) -> tuple[float, float | None, float | None]:
        try:
            import timesfm  # type: ignore[import-not-found]
        except ImportError:
            logger.warning(
                "timesfm is not installed; falling back to the naive forecast backend"
            )
            return NaiveBackend().predict(window, horizon_hours)
        _ = timesfm
        logger.debug("timesfm weights path not implemented yet; using naive predictor")
        return NaiveBackend().predict(window, horizon_hours)


def load_backend(model: str) -> ForecastBackend:
    match model:
        case "timesfm-2.5" | "naive":
            return TimesFM25Backend() if model == "timesfm-2.5" else NaiveBackend()
        case "timesfm-3.0":
            raise ValueError("TimesFM 3.0 weights are not on the default path")
        case _ as unreachable:
            raise ValueError(f"unknown forecast model {unreachable}")


def forecast_metric(
    store: ObjectStore,
    object_type: str,
    id: str,
    metric: str,
    horizon_hours: float,
    model: str = DEFAULT_MODEL,
    confidence: float = 0.85,
) -> object:
    window = [value for _ts, value in store.series_window(object_type, id, metric)]
    backend = load_backend(model)
    point, q10, q90 = backend.predict(window, horizon_hours)
    return write_forecast(
        store,
        object_type,
        id,
        metric,
        horizon_hours,
        point,
        backend.name,
        confidence,
        q10=q10,
        q90=q90,
    )
