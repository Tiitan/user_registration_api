"""Minimal metrics interfaces and in-memory implementation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

Tags = Mapping[str, str] | None
MetricKey = tuple[str, tuple[tuple[str, str], ...]]


def _normalized_tags(tags: Tags) -> tuple[tuple[str, str], ...]:
    """Return deterministic, hashable tag tuples."""
    if not tags:
        return ()
    return tuple(sorted((str(key), str(value)) for key, value in tags.items()))


def _metric_key(name: str, tags: Tags) -> MetricKey:
    """Build the dictionary key for a metric name and tags."""
    return (name, _normalized_tags(tags))


class MetricsRecorder(Protocol):
    """Protocol for metric counters, histograms, and gauges."""

    def inc(self, name: str, *, value: float = 1.0, tags: Tags = None) -> None:
        """Increment a counter metric."""
        ...

    def observe(self, name: str, value: float, *, tags: Tags = None) -> None:
        """Record a histogram observation."""
        ...

    def set(self, name: str, value: float, *, tags: Tags = None) -> None:
        """Set a gauge metric value."""
        ...


class NoOpMetricsRecorder:
    """Metrics recorder that drops all measurements."""

    def inc(self, name: str, *, value: float = 1.0, tags: Tags = None) -> None:
        """Ignore counter increments."""
        return None

    def observe(self, name: str, value: float, *, tags: Tags = None) -> None:
        """Ignore histogram observations."""
        return None

    def set(self, name: str, value: float, *, tags: Tags = None) -> None:
        """Ignore gauge updates."""
        return None


@dataclass(frozen=True)
class HistogramSnapshot:
    """Snapshot of histogram count and accumulated total."""

    count: int
    total: float


class InMemoryMetricsRecorder:
    """Thread-safe in-memory recorder used by tests and local runs."""

    def __init__(self) -> None:
        """Initialize empty metric stores."""
        self._lock = Lock()
        self._counters: dict[MetricKey, float] = {}
        self._gauges: dict[MetricKey, float] = {}
        self._histograms: dict[MetricKey, HistogramSnapshot] = {}

    def inc(self, name: str, *, value: float = 1.0, tags: Tags = None) -> None:
        """Increment a named counter."""
        key = _metric_key(name, tags)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + float(value)

    def observe(self, name: str, value: float, *, tags: Tags = None) -> None:
        """Add one sample to a histogram."""
        key = _metric_key(name, tags)
        with self._lock:
            previous = self._histograms.get(key, HistogramSnapshot(count=0, total=0.0))
            self._histograms[key] = HistogramSnapshot(count=previous.count + 1, total=previous.total + float(value))

    def set(self, name: str, value: float, *, tags: Tags = None) -> None:
        """Set a named gauge."""
        key = _metric_key(name, tags)
        with self._lock:
            self._gauges[key] = float(value)

    def get_counter(self, name: str, *, tags: Tags = None) -> float:
        """Read a counter value, defaulting to zero."""
        key = _metric_key(name, tags)
        with self._lock:
            return self._counters.get(key, 0.0)

    def get_gauge(self, name: str, *, tags: Tags = None) -> float:
        """Read a gauge value, defaulting to zero."""
        key = _metric_key(name, tags)
        with self._lock:
            return self._gauges.get(key, 0.0)

    def get_histogram(self, name: str, *, tags: Tags = None) -> HistogramSnapshot:
        """Read a histogram snapshot, defaulting to zero samples."""
        key = _metric_key(name, tags)
        with self._lock:
            return self._histograms.get(key, HistogramSnapshot(count=0, total=0.0))

    def reset(self) -> None:
        """Clear all collected metrics."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()

    def snapshot_counters(self) -> dict[MetricKey, float]:
        """Return a copy of all counters."""
        with self._lock:
            return dict(self._counters)

    def snapshot_gauges(self) -> dict[MetricKey, float]:
        """Return a copy of all gauges."""
        with self._lock:
            return dict(self._gauges)

    def snapshot_histograms(self) -> dict[MetricKey, HistogramSnapshot]:
        """Return a copy of all histogram snapshots."""
        with self._lock:
            return dict(self._histograms)
