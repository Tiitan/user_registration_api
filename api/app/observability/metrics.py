from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

Tags = Mapping[str, str] | None
MetricKey = tuple[str, tuple[tuple[str, str], ...]]


def _normalized_tags(tags: Tags) -> tuple[tuple[str, str], ...]:
    if not tags:
        return ()
    return tuple(sorted((str(key), str(value)) for key, value in tags.items()))


def _metric_key(name: str, tags: Tags) -> MetricKey:
    return (name, _normalized_tags(tags))


class MetricsRecorder(Protocol):
    def inc(self, name: str, *, value: float = 1.0, tags: Tags = None) -> None:
        ...

    def observe(self, name: str, value: float, *, tags: Tags = None) -> None:
        ...

    def set(self, name: str, value: float, *, tags: Tags = None) -> None:
        ...


class NoOpMetricsRecorder:
    def inc(self, name: str, *, value: float = 1.0, tags: Tags = None) -> None:
        return None

    def observe(self, name: str, value: float, *, tags: Tags = None) -> None:
        return None

    def set(self, name: str, value: float, *, tags: Tags = None) -> None:
        return None


@dataclass(frozen=True)
class HistogramSnapshot:
    count: int
    total: float


class InMemoryMetricsRecorder:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[MetricKey, float] = {}
        self._gauges: dict[MetricKey, float] = {}
        self._histograms: dict[MetricKey, HistogramSnapshot] = {}

    def inc(self, name: str, *, value: float = 1.0, tags: Tags = None) -> None:
        key = _metric_key(name, tags)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + float(value)

    def observe(self, name: str, value: float, *, tags: Tags = None) -> None:
        key = _metric_key(name, tags)
        with self._lock:
            previous = self._histograms.get(key, HistogramSnapshot(count=0, total=0.0))
            self._histograms[key] = HistogramSnapshot(count=previous.count + 1, total=previous.total + float(value))

    def set(self, name: str, value: float, *, tags: Tags = None) -> None:
        key = _metric_key(name, tags)
        with self._lock:
            self._gauges[key] = float(value)

    def get_counter(self, name: str, *, tags: Tags = None) -> float:
        key = _metric_key(name, tags)
        with self._lock:
            return self._counters.get(key, 0.0)

    def get_gauge(self, name: str, *, tags: Tags = None) -> float:
        key = _metric_key(name, tags)
        with self._lock:
            return self._gauges.get(key, 0.0)

    def get_histogram(self, name: str, *, tags: Tags = None) -> HistogramSnapshot:
        key = _metric_key(name, tags)
        with self._lock:
            return self._histograms.get(key, HistogramSnapshot(count=0, total=0.0))

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
