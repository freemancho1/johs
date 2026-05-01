"""BarValidator — look-ahead bias 방지선.

09:31:00 시점의 신호는 09:30 봉이 완성된 이후에만 생성 가능하다.
is_complete=False 인 봉은 이 경계에서 무조건 차단된다.
"""
from __future__ import annotations

from ..core.types import Bar


class BarValidator:
    def validate(self, bar: Bar) -> bool:
        """완성된 봉이면 True, 아니면 False."""
        return bar.is_complete

    def filter(self, bars: list[Bar]) -> list[Bar]:
        """미완성 봉 제거 후 반환."""
        return [b for b in bars if b.is_complete]
