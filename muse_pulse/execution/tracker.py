"""OrderStateTracker — 주문 상태 관리."""
from __future__ import annotations

from ..core.types import Order, OrderResult


class OrderStateTracker:
    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._results: dict[str, OrderResult] = {}

    def register(self, order: Order) -> None:
        if order.order_id:
            self._orders[order.order_id] = order

    def update(self, result: OrderResult) -> None:
        self._results[result.order_id] = result

    def get_result(self, order_id: str) -> OrderResult | None:
        return self._results.get(order_id)

    def open_orders(self) -> list[Order]:
        closed = {oid for oid, r in self._results.items() if r.status == "FILLED"}
        return [o for oid, o in self._orders.items() if oid not in closed]
