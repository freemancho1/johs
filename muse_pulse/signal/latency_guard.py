"""LatencyGuard — 합산 지연시간 초과 신호 폐기.

[원칙: "지연시간은 곧 비용"]
  분봉 단타에서 신호 생성부터 체결까지 5초 이상 걸리면
  봉의 정보가 이미 시장에 반영되어 알파(alpha)가 사라진다.
  → 느린 신호는 아예 내지 않는 게 낫다.

[임계값]
  max_total_ms = max_inference(3000) + max_network(1000) + max_order(1000) = 5000ms
  Phase 1 (백테스트)에서는 모든 추론이 수ms 이내이므로 항상 통과.
  실거래 전환 시 실제 네트워크 지연을 측정하여 임계값을 보정해야 함.
"""
from __future__ import annotations

from ..core.types import TradeSignal
from ..config.settings import settings


class LatencyGuard:
    def __init__(self, max_total_ms: float | None = None) -> None:
        # 기본값: settings.latency.max_total_ms = 5000ms
        self._max = max_total_ms or settings.latency.max_total_ms

    def allow(self, signal: TradeSignal) -> bool:
        """지연시간이 임계값 이하이면 True (신호 허용)."""
        return signal.total_latency_ms <= self._max

    def filter(self, signal: TradeSignal | None) -> TradeSignal | None:
        """None 이 들어오면 None 반환, 지연시간 초과면 None 반환.

        HistoricalSimulator 에서는 None 체크가 연쇄적으로 이루어지므로
        중간에 None 이 발생하면 해당 봉의 신호 처리가 자동으로 종료된다.
        """
        if signal is None:
            return None
        return signal if self.allow(signal) else None
