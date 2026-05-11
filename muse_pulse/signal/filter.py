"""SignalFilter — 합의 점수 임계값 미만의 약한 신호 제거.

[임계값 0.55 의 의미]
  combined_score = num_conf * 0.5 + pat_conf * 0.5
  0.55 를 달성하려면 두 트랙 평균 신뢰도가 55% 이상이어야 함.
  예: hammer(0.6) + RSI 과매도 골든크로스(0.35 conf) → combined=0.475 → 폐기
      hammer(0.6) + RSI 과매도 골든크로스(0.55 conf) → combined=0.575 → 통과

  왕복 비용 ≈ 0.25% 를 커버하려면 최소 이 신뢰도가 필요하다는 가정.

[LatencyGuard 와의 순서]
  SignalAggregator → LatencyGuard → SignalFilter 순으로 적용.
  지연이 과도한 신호를 먼저 제거하고, 그 다음 약한 신호를 제거.
"""
from __future__ import annotations

from ..core.types import TradeSignal
from ..config.settings import settings


class SignalFilter:
    def __init__(self, min_score: float | None = None) -> None:
        # 기본값: settings.signal.min_combined_score = 0.55
        self._min = min_score or settings.signal.min_combined_score

    def allow(self, signal: TradeSignal) -> bool:
        """combined_score 가 임계값 이상이면 True."""
        return signal.combined_score >= self._min

    def filter(self, signal: TradeSignal | None) -> TradeSignal | None:
        """임계값 미만 신호 → None 반환으로 파이프라인 종료."""
        if signal is None:
            return None
        return signal if self.allow(signal) else None
