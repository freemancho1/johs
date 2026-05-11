"""MarketDataFeeder — 실시간 분봉 스트리밍 인터페이스.

Phase 1: 로컬 Bar 리스트를 순서대로 재생하는 BacktestFeeder 구현.
Phase 2+: KIS WebSocket 기반 실시간 피더로 교체 예정.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from ..core.types import Bar


class BacktestFeeder:
    """과거 Bar 리스트를 시간순으로 재생하는 피더 (백테스트 전용)."""

    def __init__(self, bars: list[Bar]) -> None:
        self._bars = sorted(bars, key=lambda b: b.timestamp)

    def stream(self) -> Iterator[Bar]:
        for bar in self._bars:
            yield bar

    def __len__(self) -> int:
        return len(self._bars)


class KISRealtimeFeeder:
    """KIS Open API WebSocket 기반 실시간 분봉 피더 (stub).
    KIS_APP_KEY 설정 후 구현 예정.
    """

    def __init__(self, tickers: list[str]) -> None:
        self._tickers = tickers

    def stream(self) -> Iterator[Bar]:
        raise NotImplementedError(
            "KIS WebSocket 실시간 피더는 KIS_APP_KEY 설정 후 구현 예정."
        )
