"""LatencyMonitor — 컴포넌트별 지연시간 측정 및 병목 식별."""
from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager


class LatencyMonitor:
    def __init__(self) -> None:
        self._records: dict[str, list[float]] = defaultdict(list)

    @contextmanager
    def measure(self, component: str):
        t0 = time.perf_counter()
        yield
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self._records[component].append(elapsed_ms)

    def record(self, component: str, latency_ms: float) -> None:
        self._records[component].append(latency_ms)

    def summary(self) -> dict[str, dict]:
        import numpy as np
        result = {}
        for comp, values in self._records.items():
            arr = np.array(values)
            result[comp] = {
                "count": len(arr),
                "mean_ms": round(float(arr.mean()), 2),
                "p95_ms": round(float(np.percentile(arr, 95)), 2),
                "max_ms": round(float(arr.max()), 2),
            }
        return result
