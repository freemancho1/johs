"""SignalAggregator — 수치 트랙 + 패턴 트랙 신호 결합.

[결합 원칙: "두 트랙이 동의해야 진입"]
  단일 트랙만으로 진입하면 오신호(false positive)가 많아진다.
  두 트랙이 서로 다른 방향을 가리키면 시장 신호가 명확하지 않은 것으로 판단하여 기권.

[결합 로직]
  ① 둘 다 HOLD → None (신호 없음)
  ② 방향이 반대 → None (합의 실패)
  ③ 한쪽만 HOLD → 나머지 트랙의 방향 채택, 점수는 그 트랙 conf * 가중치(0.5)
  ④ 둘 다 방향 동의 → combined = num_conf*0.5 + pat_conf*0.5

[교체 계획]
  Phase 2: 단순 가중 평균 → 메타 모델(스태킹) 또는 강화학습 정책으로 발전 예정.
  두 트랙의 과거 성과를 기반으로 가중치를 동적 조정하는 방식 검토 중.
"""
from __future__ import annotations

from typing import cast

from ..core.types import BSDirection, NumericalSignal, PatternSignal, TradeSignal

# 방향 → 수치 매핑 (현재 코드에서는 직접 사용하지 않으나 향후 방향 비교 일반화 시 활용)
_DIR_SCORE = {"BUY": 1.0, "SELL": -1.0, "HOLD": 0.0}


class SignalAggregator:
    def __init__(
        self,
        num_weight: float = 0.5,  # 수치 트랙 가중치
        pat_weight: float = 0.5,  # 패턴 트랙 가중치
    ) -> None:
        self._nw = num_weight
        self._pw = pat_weight

    def combine(
        self,
        num: NumericalSignal,
        pat: PatternSignal,
    ) -> TradeSignal | None:
        """두 트랙 신호를 결합하여 TradeSignal 또는 None 반환.

        반환이 None 인 경우:
          - 둘 다 HOLD: 아무 신호도 없음
          - 방향 충돌: 시장 방향 불명확 → 기권이 최선

        combined_score 가 SignalFilter 의 min_combined_score(0.55)를 통과해야
        최종 TradeSignal 이 HistoricalSimulator 에 전달된다.
        """
        # ── Case 1: 둘 다 HOLD ────────────────────────────────────────────────
        if num.direction == "HOLD" and pat.direction == "HOLD":
            return None

        # ── Case 2: 방향 충돌 ────────────────────────────────────────────────
        # 두 트랙 모두 비HOLD 인데 방향이 다른 경우
        if (
            num.direction != "HOLD"
            and pat.direction != "HOLD"
            and num.direction != pat.direction
        ):
            return None

        # ── Case 3: 한쪽만 HOLD ──────────────────────────────────────────────
        # 패턴 트랙만 신호 → 패턴 방향, 점수 = pat_conf * 0.5
        if num.direction == "HOLD":
            direction = pat.direction
            combined = pat.confidence * self._pw
        # 수치 트랙만 신호 → 수치 방향, 점수 = num_conf * 0.5
        elif pat.direction == "HOLD":
            direction = num.direction
            combined = num.confidence * self._nw
        # ── Case 4: 둘 다 동일 방향 ─────────────────────────────────────────
        else:
            direction = num.direction  # 같은 방향이므로 어느 것이든 동일
            combined = num.confidence * self._nw + pat.confidence * self._pw

        total_latency = num.latency_ms + pat.latency_ms

        return TradeSignal(
            ticker=num.ticker,
            timestamp=num.timestamp,
            direction=cast(BSDirection, direction),
            combined_score=round(combined, 4),
            num_track_conf=num.confidence,
            pat_track_conf=pat.confidence,
            total_latency_ms=total_latency,
        )
