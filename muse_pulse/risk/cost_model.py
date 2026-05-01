"""CostModel — 보수적 거래 비용 계산 (변경 불가 원칙)."""
from __future__ import annotations

from ..config.settings import settings


class CostModel:
    def __init__(self) -> None:
        self._cfg = settings.cost

    def buy_cost(self, price: float, qty: int) -> float:
        amount = price * qty
        return amount * (self._cfg.commission_rate + self._cfg.slippage_rate)

    def sell_cost(self, price: float, qty: int) -> float:
        amount = price * qty
        return amount * (
            self._cfg.commission_rate
            + self._cfg.tax_rate
            + self._cfg.slippage_rate
        )

    def roundtrip_cost(self, price: float, qty: int) -> float:
        return self.buy_cost(price, qty) + self.sell_cost(price, qty)

    def min_profitable_return(self) -> float:
        """신호 임계값 설정 기준 — 이 수익률을 넘어야 이익."""
        return self._cfg.roundtrip_cost
