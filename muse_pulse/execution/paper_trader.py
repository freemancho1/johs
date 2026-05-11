"""PaperTrader — 모의투자 실행기 (Phase 1).

[역할]
  실제 KIS API 없이 주문 제출 → 체결 결과를 시뮬레이션한다.
  슬리피지를 보수적으로 반영하여 실거래와의 괴리를 줄인다.

[슬리피지 모델]
  BUY:  filled_price = current_price + slippage  (불리하게 체결)
  SELL: filled_price = current_price - slippage  (불리하게 체결)
  slippage = current_price * slippage_rate(0.1%)

  실제 시장에서 시장가 주문은 호가창에서 불리한 방향으로 매칭되므로
  매수는 현재가보다 약간 높게, 매도는 낮게 체결되는 것이 현실적.

[한계 — Phase 1 에서 미구현]
  - 부분 체결 없음: 항상 FILLED (대형주 단일 소량 주문 가정)
  - 주문 거부 없음: 항상 체결 (서킷브레이커, 가격 제한 미고려)
  - 체결 지연 없음: 즉시 체결 (latency 는 LatencyGuard 로 별도 관리)

[교체 계획]
  OrderClientPort 인터페이스 구현 → KISOrderClient 로 교체 시 이 파일만 교체.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from ..core.types import Order, OrderResult
from ..config.settings import settings


class PaperTrader:
    def __init__(self, slippage_rate: float | None = None) -> None:
        # slippage_rate 기본값: settings.cost.slippage_rate = 0.001 (0.1%)
        self._slip = slippage_rate or settings.cost.slippage_rate
        # 주문 결과 저장 (order_id → OrderResult)
        self._results: dict[str, OrderResult] = {}

    def submit_order(self, order: Order, current_price: float) -> OrderResult:
        """주문 제출 후 즉시 체결 결과 반환.

        order.order_id 가 없으면 UUID 로 생성.
        체결가에 슬리피지 반영 (매수: +, 매도: -).
        """
        order_id = order.order_id or str(uuid.uuid4())[:8]
        slippage = current_price * self._slip

        # 슬리피지 방향: 투자자에게 불리한 방향
        if order.direction == "BUY":
            filled_price = current_price + slippage   # 더 비싸게 매수
        else:
            filled_price = current_price - slippage   # 더 싸게 매도

        result = OrderResult(
            order_id=order_id,
            status="FILLED",
            filled_price=round(filled_price, 0),   # 원 단위 반올림
            filled_qty=order.quantity,
            timestamp=datetime.now(),
            slippage=slippage,
        )
        self._results[order_id] = result
        return result

    def cancel_order(self, order_id: str) -> bool:
        """주문 취소 (Phase 1 에서는 이미 즉시 체결되므로 사실상 사용 안 됨)."""
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
        """주문 상태 조회."""
        return self._results.get(order_id)
