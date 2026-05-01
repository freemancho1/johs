"""
컴포넌트 교체 비용을 낮추기 위한 Protocol 인터페이스 모음.
'반드시 변경될 것' 항목들은 모두 이 인터페이스 뒤에 격리된다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
import numpy as np

from .types import Bar, Order, OrderResult, NumericalSignal, PatternSignal, TradeSignal


@runtime_checkable
class DataStorePort(Protocol):
    """분봉 저장소 인터페이스 — 로컬 Parquet → 시계열 DB 교체 시 이 인터페이스만 유지."""
    def save_bars(self, bars: list[Bar]) -> None: ...
    def load_bars(self, ticker: str, start: datetime, end: datetime) -> list[Bar]: ...
    def list_tickers(self) -> list[str]: ...


@runtime_checkable
class ModelPort(Protocol):
    """수치/패턴 모델 교체 인터페이스 — 임계값 기반 → LSTM → Transformer 교체 시 유지."""
    def predict(self, input_data) -> tuple[str, float, dict]:
        """(direction, confidence, feature_contrib) 반환."""
        ...


@runtime_checkable
class OrderClientPort(Protocol):
    """주문 채널 인터페이스 — PaperTrader ↔ KISOrderClient 교체 시 유지."""
    def submit_order(self, order: Order) -> OrderResult: ...
    def cancel_order(self, order_id: str) -> bool: ...
    def get_order_status(self, order_id: str) -> OrderResult: ...


@runtime_checkable
class ObservabilityPort(Protocol):
    """관측 가능성 인터페이스 — 모든 컴포넌트가 이 포트를 통해 이벤트를 기록."""
    def emit_signal(self, signal: NumericalSignal | PatternSignal | TradeSignal) -> None: ...
    def emit_order(self, order: Order, result: OrderResult) -> None: ...
    def emit_latency(self, component: str, latency_ms: float) -> None: ...
    def save_chart_snapshot(
        self, ticker: str, timestamp: datetime, image: np.ndarray
    ) -> None: ...
