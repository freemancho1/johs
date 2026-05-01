"""PerformanceEvaluator — 백테스트 성과 지표 계산."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass
class TradeRecord:
    ticker: str
    direction: str
    entry_price: float
    exit_price: float
    quantity: int
    entry_time: object
    exit_time: object
    exit_reason: str          # TAKE_PROFIT / STOP_LOSS / TIMEOUT / FORCE_CLOSE
    cost: float               # 총 거래 비용


@dataclass
class PerformanceReport:
    total_trades: int
    win_rate: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    total_return_pct: float
    avg_return_per_trade_pct: float
    total_cost: float

    def __str__(self) -> str:
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
        if not trades:
            return PerformanceReport(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        returns = []
        for t in trades:
            if t.direction == "BUY":
                ret = (t.exit_price - t.entry_price) / t.entry_price
            else:
                ret = (t.entry_price - t.exit_price) / t.entry_price
            ret -= t.cost / (t.entry_price * t.quantity + 1e-8)
            returns.append(ret)

        arr = np.array(returns)
        wins = arr[arr > 0]
        losses = arr[arr <= 0]

        win_rate = len(wins) / len(arr)
        profit_factor = (
            float(wins.sum()) / float(-losses.sum() + 1e-8) if losses.size else np.inf
        )
        total_return = float(arr.sum())
        avg_return = float(arr.mean())
        sharpe = float(arr.mean() / (arr.std() + 1e-8) * np.sqrt(252 * 390))

        # 최대 낙폭 (누적 수익률 기준)
        cumulative = np.cumprod(1 + arr)
        peak = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - peak) / (peak + 1e-8)
        max_dd = float(drawdown.min())

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
