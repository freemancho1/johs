"""핵심 데이터 타입 정의 — 모든 컴포넌트가 이 파일의 타입만 교환한다.

[데이터 흐름 순서]
  Bar → (BarValidator) → [NumericalInput, PatternInput]
      → [NumericalSignal, PatternSignal]
      → (SignalAggregator) → TradeSignal
      → (TripleBarrierGuard) → Order
      → (PaperTrader) → OrderResult

각 타입이 어느 경계를 통과하는지 알면 전체 파이프라인이 보인다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional
import numpy as np


# ── 원시 시장 데이터 ────────────────────────────────────────────────────────

@dataclass
class Bar:
    """분봉 기본 단위.

    [look-ahead bias 방지 핵심]
    is_complete=False 인 봉은 BarValidator 에서 무조건 필터링된다.
    실거래에서는 현재 진행 중인 봉(is_complete=False)을 신호에 사용하면
    봉이 완성되기 전 정보를 미리 쓰는 셈이 되므로 절대 허용하지 않는다.
    백테스트에서도 동일 규칙 적용 → 합성 데이터는 is_complete=True 로 생성.
    """
    ticker: str             # KRX 종목 코드 (예: "005930")
    timestamp: datetime     # 봉 시작 시각 (09:00 봉 = 09:00:00 KST)
    open: float
    high: float
    low: float
    close: float
    volume: int
    is_complete: bool = False  # 봉 완성 여부 — False 인 봉은 파이프라인에 진입 불가


# ── 모델 입력 타입 ──────────────────────────────────────────────────────────

@dataclass
class NumericalInput:
    """수치 분석 트랙 입력.

    NumericalNormalizer 가 feature_matrix 에 롤링 Z-score 를 적용한 결과.
    window shape: [lookback_minutes, num_features(14)]
    각 값은 "지금 이 지표 값이 최근 lookback 기간 대비 몇 표준편차인가"를 나타냄.
    → 절대값이 아닌 상대적 비정상도를 모델에 입력하므로 종목·시기에 무관하게 일반화.
    """
    window: np.ndarray      # shape [N, num_features] — dtype float32
    window_size: int        # 120~240 (settings.phase.lookback_minutes)
    ticker: str
    bar_timestamp: datetime


@dataclass
class PatternInput:
    """패턴 인식 트랙 입력.

    PatternNormalizer 가 OHLCV 를 윈도우 내 최소·최대 기준 0~1 로 변환한 결과.
    ohlcv_series shape: [lookback_minutes, 5] — [Open, High, Low, Close, Volume]
    절대 가격 제거 이유: 동일한 캔들 패턴이 주가 수준에 무관하게 같은 의미여야 하므로.
    chart_image: 비전 모델(CNN/VLM) 도입 시 사용. Phase 1 에서는 None.
    """
    ohlcv_series: np.ndarray           # shape [N, 5] — dtype float32
    ticker: str
    bar_timestamp: datetime
    chart_image: Optional[np.ndarray] = None   # shape [H, W, C]; Phase 1 미사용


# ── 모델 출력 (신호) 타입 ───────────────────────────────────────────────────

@dataclass
class NumericalSignal:
    """수치 트랙 → SignalAggregator 로 전달되는 신호.

    direction: ThresholdModel(Phase 1) 또는 LSTM(Phase 2+)이 판정한 방향
    confidence: 모델의 확신도 0.0~1.0
    feature_contrib: 어떤 피처가 이 신호를 만들었는지 (관측 가능성 원칙)
                     logs/signals.jsonl 에 기록되어 사후 분석에 활용
    latency_ms: 모델 추론에 걸린 시간 — LatencyGuard 의 판단 근거
    """
    ticker: str
    timestamp: datetime
    direction: Literal["BUY", "SELL", "HOLD"]
    confidence: float                  # 0.0~1.0
    feature_contrib: dict              # {"rsi_14": 28.3, "macd_diff": 0.12, ...}
    latency_ms: float


@dataclass
class PatternSignal:
    """패턴 트랙 → SignalAggregator 로 전달되는 신호.

    pattern_name: 감지된 패턴 이름 (예: "hammer", "morning_star")
    source: 신호 생성 방식 — "RULE"(Phase 1), "CNN"(Phase 2), "VISION"(Phase 3)
    """
    ticker: str
    timestamp: datetime
    direction: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    pattern_name: str
    source: Literal["RULE", "CNN", "VISION"]
    latency_ms: float


@dataclass
class TradeSignal:
    """SignalAggregator → RiskManager 로 전달되는 합의 신호.

    두 트랙이 같은 방향에 동의했고, 합산 지연시간이 임계값 이하이고,
    combined_score >= 0.55 일 때만 이 객체가 생성된다.
    HOLD 방향은 없다 — 합의에 실패하면 None 이 반환되어 신호 자체가 없어짐.

    combined_score 계산식:
      - 두 트랙 모두 신호: num_conf * 0.5 + pat_conf * 0.5
      - 한 트랙만 신호: 해당 트랙 conf * 해당 가중치 (0.5)
    """
    ticker: str
    timestamp: datetime
    direction: Literal["BUY", "SELL"]   # HOLD 없음 — 합의 성공만 전달
    combined_score: float               # 0.0~1.0
    num_track_conf: float
    pat_track_conf: float
    total_latency_ms: float             # num.latency_ms + pat.latency_ms


# ── 주문 및 체결 결과 타입 ──────────────────────────────────────────────────

@dataclass
class Order:
    """RiskManager 가 승인하여 실행 레이어(PaperTrader/KISOrderClient)에 전달하는 주문.

    stop_loss, take_profit: Triple Barrier 기준으로 TripleBarrierGuard 가 계산한 절대 가격.
    expire_at: min(진입시각 + 60분, 당일 강제청산 시각(15:15))
    order_id: 백테스트에서는 "{ticker}_{시각}" 문자열, 실거래에서는 KIS 주문번호.
    """
    ticker: str
    direction: Literal["BUY", "SELL"]
    quantity: int
    order_type: Literal["MARKET", "LIMIT"]
    stop_loss: float           # 손절 기준가 (절대 가격, 원 단위)
    take_profit: float         # 익절 기준가 (절대 가격, 원 단위)
    expire_at: datetime        # 이 시각 이후 봉에서 TIMEOUT 또는 FORCE_CLOSE 처리
    price: Optional[float] = None       # 진입가 (submit_order 이후 채워짐)
    order_id: Optional[str] = None      # 고유 주문 ID


@dataclass
class Reject:
    """RiskManager 가 주문을 거부할 때 반환하는 이유 객체.

    현재 Phase 1 에서는 Reject 를 발생시키는 명시적 규칙이 없지만
    (수량 = 0 이면 주문 자체를 건너뜀)
    향후 추가 리스크 규칙(일일 손실 한도 초과 등) 구현 시 사용.
    """
    reason: str
    signal: TradeSignal


@dataclass
class OrderResult:
    """PaperTrader(또는 KISOrderClient)가 주문 제출 후 반환하는 체결 결과.

    Phase 1(PaperTrader): 항상 FILLED — 부분 체결·거부 미시뮬레이션.
    실거래 전환 시 PARTIAL, CANCELLED 케이스도 처리해야 함.

    slippage: filled_price - 주문 당시 시장가 (BUY 는 양수, SELL 은 음수).
              CostModel 의 slippage_rate 와 별개로 기록 (실제 슬리피지 모니터링용).
    """
    order_id: str
    status: Literal["PENDING", "FILLED", "PARTIAL", "CANCELLED"]
    filled_price: float     # 실제 체결가 (슬리피지 포함)
    filled_qty: int
    timestamp: datetime
    slippage: float         # 기대가 대비 체결가 차이 (양수 = 불리하게 체결)
