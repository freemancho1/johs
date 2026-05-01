"""리스크 가드 모음 — 모델과 완전히 분리된 독립 가드레일."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from ..core.types import Order, TradeSignal
from ..config.settings import settings
from ..data.calendar import force_close_dt


class TripleBarrierGuard:
    """Triple Barrier 기반 손절/익절/시간만료 기준가 계산."""

    def __init__(self) -> None:
        self._cfg = settings.triple_barrier

    def build_order(
        self,
        signal: TradeSignal,
        entry_price: float,
        quantity: int,
        entry_time: datetime,
    ) -> Order:
        if signal.direction == "BUY":
            take_profit = entry_price * (1 + self._cfg.take_profit)
            stop_loss = entry_price * (1 - self._cfg.stop_loss)
        else:
            take_profit = entry_price * (1 - self._cfg.take_profit)
            stop_loss = entry_price * (1 + self._cfg.stop_loss)

        expire_at = min(
            entry_time + timedelta(minutes=self._cfg.time_horizon),
            force_close_dt(
                entry_time.date(),
                settings.phase.force_close_minutes_before,
            ),
        )

        return Order(
            ticker=signal.ticker,
            direction=signal.direction,
            quantity=quantity,
            order_type="MARKET",
            stop_loss=round(stop_loss, 0),
            take_profit=round(take_profit, 0),
            expire_at=expire_at,
        )


class IntradayCloseoutGuard:
    """장 마감 강제청산 — 오버나잇 갭 리스크 원천 차단."""

    def should_force_close(self, current_time: datetime) -> bool:
        target = force_close_dt(
            current_time.date(),
            settings.phase.force_close_minutes_before,
        )
        return current_time >= target


class StopLossTakeProfitGuard:
    """포지션 보유 중 실시간 손절/익절 체크."""

    def check(
        self,
        order: Order,
        current_price: float,
        current_time: datetime,
    ) -> Literal["HOLD", "STOP_LOSS", "TAKE_PROFIT", "TIMEOUT", "FORCE_CLOSE"]:
        if current_time >= order.expire_at:
            if IntradayCloseoutGuard().should_force_close(current_time):
                return "FORCE_CLOSE"
            return "TIMEOUT"
        if order.direction == "BUY":
            if current_price >= order.take_profit:
                return "TAKE_PROFIT"
            if current_price <= order.stop_loss:
                return "STOP_LOSS"
        else:
            if current_price <= order.take_profit:
                return "TAKE_PROFIT"
            if current_price >= order.stop_loss:
                return "STOP_LOSS"
        return "HOLD"
