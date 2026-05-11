from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ProviderMetric:
    operation: str
    provider: str
    count: int = 0
    error_count: int = 0
    total_latency_seconds: float = 0.0
    max_latency_seconds: float = 0.0

    def record(self, *, latency_seconds: float, success: bool) -> None:
        self.count += 1
        if not success:
            self.error_count += 1
        self.total_latency_seconds += max(0.0, latency_seconds)
        self.max_latency_seconds = max(self.max_latency_seconds, max(0.0, latency_seconds))

    def to_dict(self) -> dict[str, Any]:
        average = self.total_latency_seconds / self.count if self.count else 0.0
        return {
            "operation": self.operation,
            "provider": self.provider,
            "count": self.count,
            "error_count": self.error_count,
            "average_latency_seconds": round(average, 3),
            "max_latency_seconds": round(self.max_latency_seconds, 3),
            "total_latency_seconds": round(self.total_latency_seconds, 3),
        }


class ObservabilityService:
    def __init__(self) -> None:
        self._started_at = _utc_now_iso()
        self._started_perf = perf_counter()
        self._lock = threading.Lock()
        self._request_count = 0
        self._request_status_counts: dict[str, int] = {}
        self._provider_metrics: dict[tuple[str, str], ProviderMetric] = {}

    @property
    def started_at(self) -> str:
        return self._started_at

    def record_request(self, *, status_code: int, latency_seconds: float) -> None:
        with self._lock:
            self._request_count += 1
            bucket = str(status_code)
            self._request_status_counts[bucket] = self._request_status_counts.get(bucket, 0) + 1

    def record_provider_operation(
        self,
        *,
        operation: str,
        provider: str | None,
        latency_seconds: float,
        success: bool,
    ) -> None:
        normalized_provider = (provider or "unknown").strip().lower() or "unknown"
        key = (operation, normalized_provider)
        with self._lock:
            metric = self._provider_metrics.get(key)
            if metric is None:
                metric = ProviderMetric(operation=operation, provider=normalized_provider)
                self._provider_metrics[key] = metric
            metric.record(latency_seconds=latency_seconds, success=success)

    def snapshot(
        self,
        *,
        service_name: str,
        service_version: str,
        demo_mode: bool,
        provider_statuses: list[dict[str, Any]],
        upload_queue: dict[str, Any],
    ) -> dict[str, Any]:
        now_perf = perf_counter()
        with self._lock:
            request_count = self._request_count
            request_status_counts = dict(sorted(self._request_status_counts.items()))
            provider_metrics = [
                metric.to_dict()
                for metric in sorted(
                    self._provider_metrics.values(),
                    key=lambda item: (item.operation, item.provider),
                )
            ]
        return {
            "service": {
                "name": service_name,
                "version": service_version,
                "demoMode": demo_mode,
                "startedAt": self._started_at,
                "uptimeSeconds": round(now_perf - self._started_perf, 3),
                "timestamp": _utc_now_iso(),
            },
            "requests": {
                "total": request_count,
                "byStatus": request_status_counts,
            },
            "providers": {
                "statuses": provider_statuses,
                "operations": provider_metrics,
            },
            "uploadQueue": upload_queue,
        }
