"""BarValidator — look-ahead bias 방지 경계선.

[핵심 원칙]
  09:31:00 시점에는 09:30봉이 완성(is_complete=True)된 이후에만 신호를 생성할 수 있다.
  현재 진행 중인 봉(is_complete=False)의 데이터를 신호에 사용하면
  "아직 일어나지 않은 미래"의 정보를 쓰는 것이므로 엄격히 금지된다.

[실거래 vs 백테스트]
  실거래: WebSocket 에서 봉 완성 이벤트(is_complete=True)를 받을 때만 파이프라인 진입.
  백테스트: 합성 봉은 모두 is_complete=True 로 생성되므로 사실상 전부 통과.
            실제 틱 데이터 사용 시 is_complete=False 봉이 섞일 수 있어 이 필터가 중요해짐.

이 클래스는 단순하지만 전체 시스템에서 가장 중요한 불변식(invariant)을 지킨다.
"""
from __future__ import annotations

from ..core.types import Bar


class BarValidator:
    def validate(self, bar: Bar) -> bool:
        """완성된 봉이면 True, 진행 중인 봉이면 False."""
        return bar.is_complete

    def filter(self, bars: list[Bar]) -> list[Bar]:
        """미완성 봉(is_complete=False)을 제거하고 완성 봉 리스트만 반환.

        HistoricalSimulator.run() 의 첫 번째 단계로 호출된다.
        필터링 후 봉 수가 lookback + 1 미만이면 simulator 가 ValueError 를 발생시킨다.
        """
        return [b for b in bars if b.is_complete]
