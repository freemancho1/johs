"""리스크 가드 모음 — 모델과 완전히 분리된 독립 가드레일.

[설계 원칙]
  모델이 얼마나 확신에 차 있더라도 리스크 가드를 우회할 수 없다.
  가드는 모델의 출력을 신뢰하지 않는다 — 언제나 독립적으로 작동한다.

[세 가지 가드]
  TripleBarrierGuard    : 주문 생성 시 TP/SL/만료 기준가 설정
  IntradayCloseoutGuard : 장 마감 강제청산 여부 판단
  StopLossTakeProfitGuard: 매 봉마다 보유 포지션의 청산 조건 체크
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from ..core.types import Order, TradeSignal
from ..config.settings import settings
from ..data.calendar import force_close_dt


class TripleBarrierGuard:
    """Triple Barrier 기반 주문 생성.

    [Triple Barrier 란]
      진입 이후 세 가지 장벽(barrier) 중 하나를 먼저 터치하면 청산:
        상단 장벽(+0.5%): 익절
        하단 장벽(-0.3%): 손절
        시간 장벽(60분): 시간 만료 청산

      비대칭 설정(TP=0.5% > SL=0.3%)의 이유:
        손실을 이익보다 더 빨리 차단 → 승률이 낮아도 수익 기대값 유지 가능.
        예: 승률 40%, 평균 이익 0.5%, 평균 손실 0.3% → EV = 0.4*0.5 - 0.6*0.3 = +0.02%

    [만료 시각]
      min(진입 + 60분, 당일 강제청산 시각(15:15))
      → 60분이 지나도 15:15 이전이면 15:15 에 강제청산.
    """

    def __init__(self) -> None:
        self._cfg = settings.triple_barrier

    def build_order(
        self,
        signal: TradeSignal,
        entry_price: float,
        quantity: int,
        entry_time: datetime,
    ) -> Order:
        """TradeSignal → Order 변환. TP/SL 절대 가격과 만료 시각을 계산해 Order 에 포함."""
        if signal.direction == "BUY":
            # BUY: 상단 +0.5% = 익절, 하단 -0.3% = 손절
            take_profit = entry_price * (1 + self._cfg.take_profit)
            stop_loss = entry_price * (1 - self._cfg.stop_loss)
        else:
            # SELL(공매도): 하단 -0.5% = 익절, 상단 +0.3% = 손절
            take_profit = entry_price * (1 - self._cfg.take_profit)
            stop_loss = entry_price * (1 + self._cfg.stop_loss)

        # 만료 시각: 진입 후 60분 vs 당일 강제청산 중 더 이른 시각
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
            stop_loss=round(stop_loss, 0),      # 원 단위로 반올림
            take_profit=round(take_profit, 0),
            expire_at=expire_at,
        )


class IntradayCloseoutGuard:
    """장 마감 강제청산 — 오버나잇 갭 리스크 원천 차단.

    KOSPI 는 15:30 마감이지만 15:15(15분 전)에 강제청산.
    이유: 시장가 주문 체결에 걸리는 시간 + 마감 직전 유동성 저하 고려.
    force_close_minutes_before = 15 (settings.phase 에서 설정)
    """

    def should_force_close(self, current_time: datetime) -> bool:
        """현재 시각이 강제청산 기준 시각(15:15) 이후이면 True."""
        target = force_close_dt(
            current_time.date(),
            settings.phase.force_close_minutes_before,
        )
        return current_time >= target


class StopLossTakeProfitGuard:
    """포지션 보유 중 매 봉마다 손절/익절/만료 조건 체크.

    [반환값과 의미]
      "HOLD"        : 아무 조건도 충족 안 됨 → 포지션 유지
      "TAKE_PROFIT" : 익절 기준가 도달 → 수익 실현 청산
      "STOP_LOSS"   : 손절 기준가 도달 → 손실 한도 청산
      "TIMEOUT"     : 60분 만료 → 방향 없는 청산
      "FORCE_CLOSE" : 15:15 강제청산 → 오버나잇 방지 청산

    [체크 순서]
      1. 만료 시각 초과 여부 (TIMEOUT vs FORCE_CLOSE)
      2. BUY 포지션: 고가 달성(TAKE_PROFIT) → 손절(STOP_LOSS)
      3. SELL 포지션: 저가 달성(TAKE_PROFIT) → 고가 달성(STOP_LOSS)
    """

    def check(
        self,
        order: Order,
        current_price: float,
        current_time: datetime,
    ) -> Literal["HOLD", "STOP_LOSS", "TAKE_PROFIT", "TIMEOUT", "FORCE_CLOSE"]:
        # ── 만료 체크 ────────────────────────────────────────────────────────
        if current_time >= order.expire_at:
            # 15:15 이후이면 FORCE_CLOSE, 60분 만료이면 TIMEOUT
            if IntradayCloseoutGuard().should_force_close(current_time):
                return "FORCE_CLOSE"
            return "TIMEOUT"

        # ── BUY 포지션 ───────────────────────────────────────────────────────
        if order.direction == "BUY":
            if current_price >= order.take_profit:
                return "TAKE_PROFIT"
            if current_price <= order.stop_loss:
                return "STOP_LOSS"

        # ── SELL(공매도) 포지션 ──────────────────────────────────────────────
        else:
            if current_price <= order.take_profit:  # 가격 하락이 이익
                return "TAKE_PROFIT"
            if current_price >= order.stop_loss:    # 가격 상승이 손실
                return "STOP_LOSS"

        return "HOLD"
