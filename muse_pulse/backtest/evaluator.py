"""PerformanceEvaluator — 백테스트 성과 지표 계산.

[계산하는 지표]
  total_trades           : 완결 거래 수 (진입+청산 쌍)
  win_rate               : 수익 거래 비율
  profit_factor          : 총 수익 / 총 손실 (1 이상이면 수익 > 손실)
  max_drawdown           : 자산 고점 대비 최대 낙폭 (음수; 클수록 나쁨)
  sharpe_ratio           : 연환산 샤프 비율 (위험 조정 수익률)
  total_return_pct       : 전체 기간 총 수익률 (거래당 수익률 합산)
  avg_return_per_trade   : 거래당 평균 수익률
  total_cost             : 전체 기간 총 거래 비용

[샤프 비율 계산 방식]
  거래당 수익률 배열에서 mean/std 를 구한 후 연환산.
  annualization factor = sqrt(252 * 390)
    252: 연간 거래일 수
    390: 하루 분봉 수 (09:00~15:30)
  → 분봉 단위 전략을 연간 수익률 기준으로 비교 가능하게 만듦.
  주의: 거래 빈도가 낮으면 샤프 비율이 극단값을 가질 수 있음.

[최대 낙폭 계산]
  누적 수익률 배열 → 누적 고점 → (현재 - 고점) / 고점
  → 고점 대비 최악의 순간에 얼마나 떨어졌는가
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass
class TradeRecord:
    """완결된 거래 한 건의 기록 (진입 + 청산).

    HistoricalSimulator 가 청산 시마다 생성하여 리스트에 추가.
    PerformanceEvaluator.evaluate() 의 입력으로 사용.
    """
    ticker: str
    direction: str          # "BUY" or "SELL"
    entry_price: float
    exit_price: float
    quantity: int
    entry_time: object      # 진입 시 order_id 문자열 (예: "005930_091532")
    exit_time: object       # 청산 봉의 timestamp (datetime)
    exit_reason: str        # TAKE_PROFIT / STOP_LOSS / TIMEOUT / FORCE_CLOSE
    cost: float             # 왕복 총 거래 비용 (매수비용 + 매도비용)


@dataclass
class PerformanceReport:
    """백테스트 성과 요약 보고서."""
    total_trades: int
    win_rate: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    total_return_pct: float
    avg_return_per_trade_pct: float
    total_cost: float

    def __str__(self) -> str:
        """run_backtest.py 의 출력 형식."""
        return (
            f"총 거래: {self.total_trades}건 | "
            f"승률: {self.win_rate:.1%} | "
            f"수익 인수: {self.profit_factor:.2f} | "
            f"최대낙폭: {self.max_drawdown:.1%} | "
            f"샤프: {self.sharpe_ratio:.2f} | "
            f"총 수익률: {self.total_return_pct:.2%} | "
            f"거래당 수익률: {self.avg_return_per_trade_pct:.4%} | "
            f"총 비용: {self.total_cost:,.0f}원"
        )


class PerformanceEvaluator:
    def evaluate(
        self,
        trades: list[TradeRecord],
        initial_capital: float,
    ) -> PerformanceReport:
        """TradeRecord 리스트 → PerformanceReport 변환.

        거래가 없으면 모든 지표가 0인 빈 보고서 반환.
        """
        if not trades:
            return PerformanceReport(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        # ── 거래당 순수익률 계산 ──────────────────────────────────────────────
        returns = []
        for t in trades:
            if t.direction == "BUY":
                # BUY: (청산가 - 진입가) / 진입가
                ret = (t.exit_price - t.entry_price) / t.entry_price
            else:
                # SELL(공매도): (진입가 - 청산가) / 진입가
                ret = (t.entry_price - t.exit_price) / t.entry_price
            # 비용 차감: cost / (진입금액) → 비율로 변환
            # 1e-8: entry_price*quantity=0 인 엣지 케이스 방지
            ret -= t.cost / (t.entry_price * t.quantity + 1e-8)
            returns.append(ret)

        arr = np.array(returns)
        wins = arr[arr > 0]    # 수익 거래 수익률 배열
        losses = arr[arr <= 0] # 손실 거래 수익률 배열 (0 포함 — 손익분기)

        # ── 기본 통계 ─────────────────────────────────────────────────────────
        win_rate = len(wins) / len(arr)

        # profit_factor: 총 수익 / 총 손실 절대값
        # losses 가 없으면 inf (모든 거래가 수익) — 너무 좋으면 오히려 의심
        profit_factor = (
            float(wins.sum()) / float(-losses.sum() + 1e-8) if losses.size else np.inf
        )

        total_return = float(arr.sum())   # 단순 수익률 합 (복리 아님 — 대략적 지표)
        avg_return = float(arr.mean())    # 거래당 평균 순수익률

        # ── 샤프 비율 (연환산) ────────────────────────────────────────────────
        # 거래당 수익률 기준 → 분봉 하루 390봉 * 연 252거래일로 연환산
        sharpe = float(arr.mean() / (arr.std() + 1e-8) * np.sqrt(252 * 390))

        # ── 최대 낙폭 (누적 수익률 기준) ──────────────────────────────────────
        # 1. 누적 수익률 계산: 각 거래 후 자산 변화를 곱으로 표현
        cumulative = np.cumprod(1 + arr)
        # 2. 누적 고점: 각 시점까지의 최대값
        peak = np.maximum.accumulate(cumulative)
        # 3. 낙폭: (현재 - 고점) / 고점 (음수 — 클수록 나쁨)
        drawdown = (cumulative - peak) / (peak + 1e-8)
        max_dd = float(drawdown.min())  # 최솟값 = 최대 낙폭

        total_cost = sum(t.cost for t in trades)

        return PerformanceReport(
            total_trades=len(trades),
            win_rate=win_rate,
            profit_factor=profit_factor,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            total_return_pct=total_return,
            avg_return_per_trade_pct=avg_return,
            total_cost=total_cost,
        )
