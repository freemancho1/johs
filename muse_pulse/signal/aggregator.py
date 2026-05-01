"""SignalAggregator — 수치 트랙 + 패턴 트랙 신호 결합.

'변경할 수 있는 것': 가중 평균 → 메타 모델 → 강화학습 정책으로 단계적 발전 예정.
"""
from __future__ import annotations

from ..core.types import NumericalSignal, PatternSignal, TradeSignal


_DIR_SCORE = {"BUY": 1.0, "SELL": -1.0, "HOLD": 0.0}


class SignalAggregator:
    def __init__(
        self,
        num_weight: float = 0.5,
        pat_weight: float = 0.5,
    ) -> None:
        self._nw = num_weight
        self._pw = pat_weight

    def combine(
        self,
        num: NumericalSignal,
        pat: PatternSignal,
    ) -> TradeSignal | None:
        """두 트랙이 같은 방향이고 합의 점수가 임계값 이상일 때 TradeSignal 반환.
        방향이 다르거나 둘 다 HOLD 이면 None.
        """
        if num.direction == "HOLD" and pat.direction == "HOLD":
            return None

        # 방향이 다르면 합의 실패
        if (
            num.direction != "HOLD"
            and pat.direction != "HOLD"
            and num.direction != pat.direction
        ):
            return None

        # 한쪽이 HOLD 면 다른 쪽 방향 채택, 신뢰도는 그쪽만 반영
        if num.direction == "HOLD":
            direction = pat.direction
            combined = pat.confidence * self._pw
        elif pat.direction == "HOLD":
            direction = num.direction
            combined = num.confidence * self._nw
        else:
            direction = num.direction
            combined = num.confidence * self._nw + pat.confidence * self._pw

        total_latency = num.latency_ms + pat.latency_ms

        return TradeSignal(
            ticker=num.ticker,
            timestamp=num.timestamp,
            direction=direction,
            combined_score=round(combined, 4),
            num_track_conf=num.confidence,
            pat_track_conf=pat.confidence,
            total_latency_ms=total_latency,
        )
