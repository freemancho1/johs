"""PositionSizer — 포지션 크기 결정.

[원칙: Kelly 기준 이전, 고정 비율 먼저]
  Phase 1 에서는 Kelly 기준(최적 베팅 비율 이론)을 사용하지 않는다.
  이유: Kelly 는 정확한 승률과 손익비를 알아야 하는데,
        Phase 1 은 그 통계가 아직 충분히 쌓이지 않았기 때문.
  → 단순히 계좌 대비 10% 고정 비율 적용.

[계산 방식]
  max_amount = min(현재 보유 현금, 초기 자본 * 10%)
  qty = max_amount // 현재가 (소수점 버림 — 주식은 정수 단위)

  현재 현금이 초기 자본의 10% 이하이면 그게 최대치.
  초기 자본 기준 10%를 한도로 두는 이유: 자본이 불어나도 과도한 집중 방지.
"""
from __future__ import annotations

from ..config.settings import settings


class PositionSizer:
    def __init__(
        self,
        capital: float | None = None,
        max_position_pct: float | None = None,
    ) -> None:
        # 초기 자본 기준점: 계좌 규모 대비 최대 포지션 비율 계산에 사용
        self._capital = capital or settings.risk.initial_capital
        self._max_pct = max_position_pct or settings.risk.max_position_pct

    def calc_quantity(self, price: float, available_cash: float) -> int:
        """매수 가능 수량 계산.

        available_cash: 현재 미사용 현금 (초기 자본 - 진입 비용 누적)
        price: 현재 봉의 close 가격 (시장가 주문 기준가)
        """
        # 두 한도 중 작은 쪽: 현재 현금 vs 초기 자본의 10%
        max_amount = min(
            available_cash,
            self._capital * self._max_pct,
        )
        qty = int(max_amount // price)  # 소수점 버림 (주식은 정수 단위)
        return max(qty, 0)  # 음수 방지 (현금 부족 시 0 반환)

    def update_capital(self, capital: float) -> None:
        """자본 기준점 갱신 (Walk-Forward 등에서 구간별 자본 재설정 시 사용)."""
        self._capital = capital
