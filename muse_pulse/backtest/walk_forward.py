"""WalkForwardValidator — 거래일 단위 슬라이딩 윈도우 검증.

[Walk-Forward 검증이 필요한 이유]
  단순 70/15/15 분할은 파라미터 튜닝 후 테스트 구간에서 과적합될 수 있다.
  Walk-Forward 는 시장의 비정상성(regime change)을 고려하여
  여러 시기에 걸쳐 전략이 일관되게 작동하는지 확인한다.

[슬라이딩 윈도우 방식]
  학습 60거래일 + 테스트 10거래일을 하나의 윈도우로 설정.
  윈도우를 10거래일씩 앞으로 슬라이딩하며 반복.

  예시 (총 120 거래일, train=60, test=10):
    [0~59]학습  [60~69]테스트  → report[0]
    [10~69]학습 [70~79]테스트  → report[1]
    [20~79]학습 [80~89]테스트  → report[2]
    ...

  결과 해석: report 들의 평균 승률/샤프 비율이 일관되면 전략이 안정적.
             특정 구간에서만 좋으면 시장 국면(regime)에 의존하는 전략일 가능성.

[split_by_trading_day]
  거래일 단위로 분할 — 달력 기준이 아님.
  이유: 주말·공휴일을 건너뛰는 시계열에서 날짜 기준 분할은 불균형 초래.
  무작위 분할 금지: 미래 봉이 과거 학습 구간에 들어가면 미래 정보 누출.
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
    """70/15/15 분할 결과 (현재 미사용, 향후 분석용)."""
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
    """거래일 단위 시간순 70/15/15 분할.

    [알고리즘]
      1. 전체 거래일 목록 추출 (중복 제거, 정렬)
      2. 70%/15% 비율로 거래일 인덱스 경계 계산
      3. 각 구간의 거래일 집합으로 Bar 필터링

    [왜 봉 수가 아닌 거래일 기준인가]
      봉 수 기준으로 분할하면 거래량이 많은 날(봉 수 많음)이 특정 구간에 몰릴 수 있다.
      거래일 기준은 시간적 대표성을 균등하게 유지한다.
    """
    # 봉 timestamp 에서 날짜만 추출 → 중복 제거 후 정렬
    days = sorted({b.timestamp.date() for b in bars})
    n = len(days)  # 전체 거래일 수

    # 경계 인덱스 계산
    train_end = int(n * train_ratio)               # 예: 250일 * 0.7 = 175번째 거래일까지
    val_end = train_end + int(n * val_ratio)        # 175 + 37 = 212번째까지

    # 각 구간의 날짜 집합 (O(1) 조회를 위해 set 사용)
    train_days_set = set(days[:train_end])
    val_days_set = set(days[train_end:val_end])
    test_days_set = set(days[val_end:])

    # 날짜 기준으로 Bar 분류
    train = [b for b in bars if b.timestamp.date() in train_days_set]
    val = [b for b in bars if b.timestamp.date() in val_days_set]
    test = [b for b in bars if b.timestamp.date() in test_days_set]

    return train, val, test


class WalkForwardValidator:
    """Walk-Forward: 학습 구간을 슬라이딩하면서 복수 구간 검증.

    각 윈도우마다 독립 HistoricalSimulator 인스턴스를 생성하므로
    상태 오염 없이 격리된 평가가 보장된다.
    """

    def __init__(
        self,
        train_days: int = 60,   # 학습 버퍼 크기 (거래일)
        test_days: int = 10,    # 평가 구간 크기 (거래일)
        capital: float | None = None,
    ) -> None:
        self._train_days = train_days
        self._test_days = test_days
        self._cap = capital

    def run(self, bars: list[Bar]) -> list[PerformanceReport]:
        """전체 bars 에 걸쳐 슬라이딩 윈도우를 적용하고 각 구간의 성과 보고서 반환.

        [윈도우 진행 방식]
          step = train_days + test_days (= 70일)
          start_idx 를 test_days(10일)씩 증가

        [ValueError 처리]
          데이터 부족 구간(lookback 미달)은 건너뜀.
          이는 정상 동작 — 데이터가 부족한 첫 윈도우는 skip.
        """
        all_days = sorted({b.timestamp.date() for b in bars})
        n = len(all_days)
        step = self._train_days + self._test_days  # 전체 윈도우 크기
        reports = []

        for start_idx in range(0, n - step, self._test_days):
            # 현재 윈도우의 학습/테스트 경계
            train_end = start_idx + self._train_days
            test_end = train_end + self._test_days

            if test_end > n:
                break  # 마지막 불완전 윈도우 제외

            # 테스트 구간 날짜 집합 (결과 해석용, 현재 미사용)
            test_day_set = set(all_days[train_end:test_end])

            # 윈도우 전체(학습+테스트) Bar 추출
            # 학습 구간 = 룩백 버퍼, 테스트 구간 = 실제 신호 발생 구간
            window_day_set = set(all_days[start_idx:test_end])
            window_bars = [b for b in bars if b.timestamp.date() in window_day_set]

            try:
                sim = HistoricalSimulator(capital=self._cap)
                report = sim.run(window_bars)
                reports.append(report)
            except ValueError:
                # 데이터 부족 → 이 윈도우는 skip (정상적으로 발생 가능)
                continue

        return reports
