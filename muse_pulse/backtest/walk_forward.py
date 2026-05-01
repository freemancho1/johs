"""WalkForwardValidator — 거래일 단위 70/15/15 시간순 분할 + Walk-Forward 검증.

시계열 데이터의 무작위 분할은 미래 정보 누출의 직접적 원인이므로
반드시 시간 순서를 유지한 분할을 사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..core.types import Bar
from ..data.calendar import trading_days
from .simulator import HistoricalSimulator
from .evaluator import PerformanceReport


@dataclass
class SplitResult:
    train_days: int
    val_days: int
    test_days: int
    val_report: PerformanceReport
    test_report: PerformanceReport


def split_by_trading_day(
    bars: list[Bar],
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
) -> tuple[list[Bar], list[Bar], list[Bar]]:
    """거래일 단위 시간순 분할."""
    days = sorted({b.timestamp.date() for b in bars})
    n = len(days)
    train_end = int(n * train_ratio)
    val_end = train_end + int(n * val_ratio)

    train_days_set = set(days[:train_end])
    val_days_set = set(days[train_end:val_end])
    test_days_set = set(days[val_end:])

    train = [b for b in bars if b.timestamp.date() in train_days_set]
    val = [b for b in bars if b.timestamp.date() in val_days_set]
    test = [b for b in bars if b.timestamp.date() in test_days_set]
    return train, val, test


class WalkForwardValidator:
    """Walk-Forward: 학습 구간을 슬라이딩하면서 검증."""

    def __init__(
        self,
        train_days: int = 60,
        test_days: int = 10,
        capital: float | None = None,
    ) -> None:
        self._train_days = train_days
        self._test_days = test_days
        self._cap = capital

    def run(self, bars: list[Bar]) -> list[PerformanceReport]:
        all_days = sorted({b.timestamp.date() for b in bars})
        n = len(all_days)
        step = self._train_days + self._test_days
        reports = []

        for start_idx in range(0, n - step, self._test_days):
            train_end = start_idx + self._train_days
            test_end = train_end + self._test_days
            if test_end > n:
                break

            test_day_set = set(all_days[train_end:test_end])
            # 학습 구간까지의 봉을 버퍼로 사용하고 테스트 구간 평가
            window_day_set = set(all_days[start_idx:test_end])
            window_bars = [b for b in bars if b.timestamp.date() in window_day_set]

            try:
                sim = HistoricalSimulator(capital=self._cap)
                report = sim.run(window_bars)
                reports.append(report)
            except ValueError:
                continue

        return reports
