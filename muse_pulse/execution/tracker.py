"""OrderStateTracker — 주문 상태 관리.

[역할]
  현재 열려 있는 주문(미체결 or 체결 후 포지션 보유 중)을 추적한다.
  HistoricalSimulator 에서는 open_order 변수로 직접 관리하므로
  이 클래스는 현재 백테스트에서 직접 호출되지 않는다.
  실거래 전환 시 WebSocket 이벤트 기반 상태 관리를 위해 설계된 컴포넌트.

[실거래에서의 역할]
  - KIS WebSocket 에서 체결 이벤트를 받아 register/update 호출
  - open_orders() 로 미청산 포지션 목록을 IntradayCloseoutGuard 에 전달
"""
from __future__ import annotations

from ..core.types import Order, OrderResult


class OrderStateTracker:
    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}         # order_id → Order
        self._results: dict[str, OrderResult] = {}  # order_id → OrderResult

    def register(self, order: Order) -> None:
        """새 주문 등록. order_id 없는 주문은 무시."""
        if order.order_id:
            self._orders[order.order_id] = order

    def update(self, result: OrderResult) -> None:
        """체결/취소 결과로 상태 업데이트."""
        self._results[result.order_id] = result

    def get_result(self, order_id: str) -> OrderResult | None:
        """주문 ID 로 결과 조회."""
        return self._results.get(order_id)

    def open_orders(self) -> list[Order]:
        """아직 FILLED 처리되지 않은 미청산 주문 목록 반환.

        등록된 주문 중 결과가 없거나 FILLED 가 아닌 주문을 반환.
        실거래에서 장 마감 강제청산 대상 포지션 식별에 사용.
        """
        closed = {oid for oid, r in self._results.items() if r.status == "FILLED"}
        return [o for oid, o in self._orders.items() if oid not in closed]
