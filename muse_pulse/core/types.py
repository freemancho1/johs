from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional
import numpy as np


@dataclass
class Bar:
    """분봉 기본 단위. is_complete=False 인 봉은 하위 컴포넌트에 절대 전달하지 않는다."""
    ticker: str
    timestamp: datetime        # 봉 시작 시각
    open: float
    high: float
    low: float
    close: float
    volume: int
    is_complete: bool = False


@dataclass
class NumericalInput:
    """수치 분석 트랙 입력 — 롤링 Z-score 정규화된 피처 행렬."""
    window: np.ndarray         # shape [N, num_features]
    window_size: int           # 120~240
    ticker: str
    bar_timestamp: datetime


@dataclass
class PatternInput:
    """패턴 인식 트랙 입력 — 0~1 상대 정규화된 OHLCV 시계열 + 차트 이미지."""
    ohlcv_series: np.ndarray           # shape [N, 5]
    ticker: str
    bar_timestamp: datetime
    chart_image: Optional[np.ndarray] = None   # shape [H, W, C]; 비전 모델 미사용 시 None


@dataclass
class NumericalSignal:
    """수치 트랙이 SignalConfluenceEngine 으로 내보내는 신호."""
    ticker: str
    timestamp: datetime
    direction: Literal["BUY", "SELL", "HOLD"]
    confidence: float                  # 0.0~1.0
    feature_contrib: dict              # 피처별 기여도 — 관측 가능성 원칙
    latency_ms: float


@dataclass
class PatternSignal:
    """패턴 트랙이 SignalConfluenceEngine 으로 내보내는 신호."""
    ticker: str
    timestamp: datetime
    direction: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    pattern_name: str
    source: Literal["RULE", "CNN", "VISION"]
    latency_ms: float


@dataclass
class TradeSignal:
    """SignalConfluenceEngine 이 RiskManager 로 전달하는 합의 신호."""
    ticker: str
    timestamp: datetime
    direction: Literal["BUY", "SELL"]
    combined_score: float
    num_track_conf: float
    pat_track_conf: float
    total_latency_ms: float


@dataclass
class Order:
    """RiskManager 가 승인하여 OrderExecutor 에 전달하는 주문."""
    ticker: str
    direction: Literal["BUY", "SELL"]
    quantity: int
    order_type: Literal["MARKET", "LIMIT"]
    stop_loss: float           # 손절 기준가 (절대 가격)
    take_profit: float         # 익절 기준가 (절대 가격)
    expire_at: datetime        # 시간만료 or 마감 강제청산 시각
    price: Optional[float] = None
    order_id: Optional[str] = None


@dataclass
class Reject:
    """RiskManager 가 주문을 거부할 때 반환."""
    reason: str
    signal: TradeSignal


@dataclass
class OrderResult:
    """OrderExecutor 가 반환하는 체결 결과."""
    order_id: str
    status: Literal["PENDING", "FILLED", "PARTIAL", "CANCELLED"]
    filled_price: float
    filled_qty: int
    timestamp: datetime
    slippage: float            # 기대가 - 체결가
