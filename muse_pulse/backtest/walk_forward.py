"""WalkForwardValidator — 거래일 단위 슬라이딩 윈도우 검증.

[Walk-Forward 검증이 필요한 이유]
  Walk-Forward 는 시장의 비정상성(regime change)을 고려하여
  여러 시기에 걸쳐 전략이 일관되게 작동하는지 확인한다.

[슬라이딩 윈도우 방식]
  버퍼 2거래일 + 테스트 10거래일을 하나의 윈도우로 설정.
  윈도우를 test_days(10거래일)씩 앞으로 슬라이딩하며 반복.
  스텝 = test_days 이므로 각 거래일이 테스트셋에 정확히 한 번만 등장한다.

  버퍼 크기 근거: lookback_minutes(120봉) ÷ 390봉/일 = 0.31일 → 올림 1일 + 여유 1일 = 2일.
  1년(252거래일) 기준 윈도우 수: (252 - (buffer=2 + test=10)) / step(=test=10) = 24개.

  예시 (총 120 거래일, buffer=2, test=10):
    [0~1]버퍼  [2~11]테스트  → report[0]
    [10~11]버퍼 [12~21]테스트 → report[1]
    ...

  결과 해석: report 들의 평균 승률/샤프 비율이 일관되면 전략이 안정적.
             특정 구간에서만 좋으면 시장 국면(regime)에 의존하는 전략일 가능성.
"""
from __future__ import annotations

import math

from ..config.settings import settings
from ..core.types import Bar
from .simulator import HistoricalSimulator
from .evaluator import PerformanceReport

_BARS_PER_DAY = 390  # KRX 09:00~15:30, 1분봉 기준


class WalkForwardValidator:
    """Walk-Forward: 버퍼 구간을 슬라이딩하면서 복수 구간 검증.

    각 윈도우마다 독립 HistoricalSimulator 인스턴스를 생성하므로
    상태 오염 없이 격리된 평가가 보장된다.
    """

    def __init__(
        self,
        buffer_days: int | None = None,  # None 이면 lookback_minutes 로 자동 계산
        test_days: int = 10,
        capital: float | None = None,
    ) -> None:
        if buffer_days is None:
            buffer_days = math.ceil(settings.phase.lookback_minutes / _BARS_PER_DAY) + 1
        self._buffer_days = buffer_days
        self._test_days = test_days
        self._cap = capital

    def run(self, bars: list[Bar]) -> list[PerformanceReport]:
        """전체 bars 에 걸쳐 슬라이딩 윈도우를 적용하고 각 구간의 성과 보고서 반환.

        [윈도우 진행 방식]
          윈도우 크기 = buffer_days + test_days
          start_idx 를 test_days 씩 증가

        [ValueError 처리]
          데이터 부족 구간(lookback 미달)은 건너뜀.
          이는 정상 동작 — 데이터가 부족한 첫 윈도우는 skip.
        """
        all_days = sorted({b.timestamp.date() for b in bars})
        n = len(all_days)
        window_size = self._buffer_days + self._test_days
        reports = []

        for start_idx in range(0, n - window_size, self._test_days):
            buffer_end = start_idx + self._buffer_days
            test_end = buffer_end + self._test_days

            if test_end > n:
                break  # 마지막 불완전 윈도우 제외

            # 윈도우 전체(버퍼+테스트) Bar 추출
            # 버퍼 구간 = 지표 계산용 룩백, 테스트 구간 = 실제 신호 발생 구간
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
