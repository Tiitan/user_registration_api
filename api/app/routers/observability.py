"""Observability endpoints router."""

from __future__ import annotations

from collections import defaultdict
from typing import cast

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, SummaryMetricFamily

from api.app.observability.metrics import InMemoryMetricsRecorder, MetricsRecorder

router = APIRouter(tags=["health"])


class _InMemoryMetricsCollector:
    """Expose in-memory recorder data through prometheus_client families."""

    def __init__(self, metrics: InMemoryMetricsRecorder) -> None:
        self._metrics = metrics

    def collect(self):  # type: ignore[no-untyped-def]
        counter_groups: dict[tuple[str, tuple[str, ...]], list[tuple[tuple[str, ...], float]]] = defaultdict(list)
        for (name, tags), value in self._metrics.snapshot_counters().items():
            label_names = tuple(label for label, _ in tags)
            label_values = tuple(label_value for _, label_value in tags)
            counter_groups[(name, label_names)].append((label_values, value))
        for (name, label_names), rows in sorted(counter_groups.items()):
            family = CounterMetricFamily(name, f"{name} from in-memory recorder", labels=list(label_names))
            for label_values, value in rows:
                family.add_metric(list(label_values), value)
            yield family

        histogram_groups: dict[tuple[str, tuple[str, ...]], list[tuple[tuple[str, ...], int, float]]] = defaultdict(list)
        for (name, tags), snapshot in self._metrics.snapshot_histograms().items():
            label_names = tuple(label for label, _ in tags)
            label_values = tuple(label_value for _, label_value in tags)
            histogram_groups[(name, label_names)].append((label_values, snapshot.count, snapshot.total))
        for (name, label_names), rows in sorted(histogram_groups.items()):
            family = SummaryMetricFamily(name, f"{name} summary from in-memory recorder", labels=list(label_names))
            for label_values, count_value, sum_value in rows:
                family.add_metric(list(label_values), count_value=count_value, sum_value=sum_value)
            yield family

        gauge_groups: dict[tuple[str, tuple[str, ...]], list[tuple[tuple[str, ...], float]]] = defaultdict(list)
        for (name, tags), value in self._metrics.snapshot_gauges().items():
            label_names = tuple(label for label, _ in tags)
            label_values = tuple(label_value for _, label_value in tags)
            gauge_groups[(name, label_names)].append((label_values, value))
        for (name, label_names), rows in sorted(gauge_groups.items()):
            family = GaugeMetricFamily(name, f"{name} from in-memory recorder", labels=list(label_names))
            for label_values, value in rows:
                family.add_metric(list(label_values), value)
            yield family


@router.get("/metrics", summary="Prometheus metrics", description="Prometheus scrape endpoint exposing in-process instrumentation metrics.")
async def prometheus_metrics(request: Request) -> Response:
    """Return current in-process metrics in Prometheus scrape format."""
    metrics = cast(MetricsRecorder | None, getattr(request.app.state, "metrics", None))
    if not isinstance(metrics, InMemoryMetricsRecorder):
        return Response(content=b"", media_type=CONTENT_TYPE_LATEST)
    registry = CollectorRegistry(auto_describe=False)
    registry.register(_InMemoryMetricsCollector(metrics))
    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
