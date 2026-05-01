"""LatencyGuard — 합산 지연시간 초과 신호 폐기.

지연시간은 곧 비용 원칙: 임계값을 넘으면 해당 신호를 폐기한다.
"""
from __future__ import annotations

from ..core.types import TradeSignal
from ..config.settings import settings


class LatencyGuard:
    def __init__(self, max_total_ms: float | None = None) -> None:
        self._max = max_total_ms or settings.latency.max_total_ms

    def allow(self, signal: TradeSignal) -> bool:
        """지연시간이 임계값 이하이면 True."""
        return signal.total_latency_ms <= self._max

    def filter(self, signal: TradeSignal | None) -> TradeSignal | None:
        if signal is None:
            return None
        return signal if self.allow(signal) else None
