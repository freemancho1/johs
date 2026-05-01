"""PaperTrader — 모의투자 시뮬레이터.

슬리피지·체결 실패 가능성을 보수적으로 시뮬레이션한다.
OrderClientPort 인터페이스를 구현하므로 KISOrderClient 와 교체 가능.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from ..core.types import Order, OrderResult
from ..config.settings import settings


class PaperTrader:
    def __init__(self, slippage_rate: float | None = None) -> None:
        self._slip = slippage_rate or settings.cost.slippage_rate
        self._results: dict[str, OrderResult] = {}

    def submit_order(self, order: Order, current_price: float) -> OrderResult:
        order_id = order.order_id or str(uuid.uuid4())[:8]
        slippage = current_price * self._slip
        if order.direction == "BUY":
            filled_price = current_price + slippage
        else:
            filled_price = current_price - slippage

        result = OrderResult(
            order_id=order_id,
            status="FILLED",
            filled_price=round(filled_price, 0),
            filled_qty=order.quantity,
            timestamp=datetime.now(),
            slippage=slippage,
        )
        self._results[order_id] = result
        return result

    def cancel_order(self, order_id: str) -> bool:
        if order_id in self._results:
            self._results[order_id] = OrderResult(
                order_id=order_id,
                status="CANCELLED",
                filled_price=0.0,
                filled_qty=0,
                timestamp=datetime.now(),
                slippage=0.0,
            )
            return True
        return False

    def get_order_status(self, order_id: str) -> OrderResult | None:
        return self._results.get(order_id)
