"""PositionSizer — 포지션 크기 결정."""
from __future__ import annotations

from ..config.settings import settings


class PositionSizer:
    def __init__(
        self,
        capital: float | None = None,
        max_position_pct: float | None = None,
    ) -> None:
        self._capital = capital or settings.risk.initial_capital
        self._max_pct = max_position_pct or settings.risk.max_position_pct

    def calc_quantity(self, price: float, available_cash: float) -> int:
        """매수 가능 수량. 계좌 대비 최대 비율 + 가용 현금 중 작은 쪽 적용."""
        max_amount = min(
            available_cash,
            self._capital * self._max_pct,
        )
        qty = int(max_amount // price)
        return max(qty, 0)

    def update_capital(self, capital: float) -> None:
        self._capital = capital
