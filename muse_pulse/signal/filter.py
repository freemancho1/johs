"""SignalFilter — 합의 점수 임계값 미만 약한 신호 제거."""
from __future__ import annotations

from ..core.types import TradeSignal
from ..config.settings import settings


class SignalFilter:
    def __init__(self, min_score: float | None = None) -> None:
        self._min = min_score or settings.signal.min_combined_score

    def allow(self, signal: TradeSignal) -> bool:
        return signal.combined_score >= self._min

    def filter(self, signal: TradeSignal | None) -> TradeSignal | None:
        if signal is None:
            return None
        return signal if self.allow(signal) else None
