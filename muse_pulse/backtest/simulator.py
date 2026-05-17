"""HistoricalSimulator — 과거 분봉 재생 기반 백테스트 엔진.

[전체 파이프라인 한눈에 보기]
  Bar 리스트 → (BarValidator) → deque 버퍼에 순차 추가
  매 봉마다:
    ① 보유 포지션 체크 (StopLossTakeProfitGuard): 청산 조건 만족 시 청산
    ② 룩백 미달 봉은 건너뜀 (지표 계산 불가)
    ③ 포지션 있으면 신규 신호 생략 (동시 다중 포지션 없음 — Phase 1 단순화)
    ④ 피처 추출 + 정규화 → 두 트랙 모델 추론
    ⑤ 신호 합의 + 지연 필터 + 점수 필터
    ⑥ 수량 계산 → Triple Barrier 기준으로 주문 생성 → 체결
  전체 거래 기록 → PerformanceEvaluator → PerformanceReport 반환

[단순화 사항 (Phase 1)]
  - 단일 포지션: open_order 변수 하나로 관리 (동시 다중 포지션 없음)
  - 항상 시장가 즉시 체결
  - 공매도는 코드 상 지원하나 Phase 1 신호 필터링으로 사실상 미발생
"""
from __future__ import annotations

from collections import deque
from datetime import datetime


from ..core.types import Bar, Order, TradeSignal
from ..config.settings import settings
from ..features.validator import BarValidator
from ..features.normalizer import NumericalNormalizer, PatternNormalizer
from ..models.numerical.extractor import FeatureExtractor
from ..models.numerical.model import ThresholdModel
from ..models.pattern.rules import RuleBasedPatternEngine
from ..signal.aggregator import SignalAggregator
from ..signal.latency_guard import LatencyGuard
from ..signal.filter import SignalFilter
from ..risk.cost_model import CostModel
from ..risk.sizer import PositionSizer
from ..risk.guards import TripleBarrierGuard, StopLossTakeProfitGuard
from ..execution.paper_trader import PaperTrader
from ..execution.tracker import OrderStateTracker
from ..observability.logger import SignalLogger, OrderLogger
from ..observability.latency import LatencyMonitor
from .evaluator import PerformanceEvaluator, TradeRecord, PerformanceReport


class HistoricalSimulator:
    def __init__(
        self,
        capital: float | None = None,
        lookback: int | None = None,
    ) -> None:
        self._cap = capital or settings.risk.initial_capital
        # 룩백 윈도우: 기술 지표(RSI/MACD/BB) 계산에 필요한 최소 봉 수
        # 기본값 120봉 = 2시간 치 분봉
        self._lookback = lookback or settings.phase.lookback_minutes

        # ── 파이프라인 컴포넌트 초기화 ────────────────────────────────────────
        # 각 컴포넌트는 독립적으로 초기화 → 테스트 시 개별 교체 가능
        self._validator = BarValidator()             # look-ahead bias 방지 필터
        self._num_norm = NumericalNormalizer(self._lookback)   # 수치 트랙 Z-score 정규화
        self._pat_norm = PatternNormalizer(self._lookback)     # 패턴 트랙 0~1 정규화
        self._extractor = FeatureExtractor()         # OHLCV → 14개 기술 지표
        self._num_model = ThresholdModel()           # 수치 트랙 신호 생성 (Phase 1: RSI+MACD)
        self._pat_engine = RuleBasedPatternEngine()  # 패턴 트랙 신호 생성 (7가지 캔들 패턴)
        self._aggregator = SignalAggregator()        # 두 트랙 합의 (가중 평균)
        self._lat_guard = LatencyGuard()             # 지연시간 5초 초과 신호 폐기
        self._sig_filter = SignalFilter()            # combined_score < 0.55 신호 폐기
        self._cost_model = CostModel()               # 매수/매도 비용 계산
        self._sizer = PositionSizer(self._cap)       # 포지션 수량 계산 (계좌 10% 고정)
        self._barrier_guard = TripleBarrierGuard()   # TP/SL/만료 기준가 설정
        self._sl_tp_guard = StopLossTakeProfitGuard() # 매 봉 청산 조건 체크
        self._trader = PaperTrader()                 # 모의 체결 실행
        self._tracker = OrderStateTracker()          # 주문 상태 추적 (실거래용)
        self._sig_logger = SignalLogger()            # 신호 JSONL 기록
        self._ord_logger = OrderLogger()             # 주문/체결 JSONL 기록
        self._latency = LatencyMonitor()             # 컴포넌트별 지연시간 측정

    def run(self, bars: list[Bar]) -> PerformanceReport:
        """백테스트 메인 루프 — Bar 리스트를 시간 순서대로 재생하여 거래를 시뮬레이션.

        반환: PerformanceReport (총 거래 수, 승률, 샤프 등 성과 지표)
        """
        # ── 전처리: 미완성 봉 제거 ────────────────────────────────────────────
        # is_complete=False 봉이 섞여 있으면 look-ahead bias 발생 위험
        bars = self._validator.filter(bars)

        # 룩백 + 1봉 이상 없으면 의미 있는 백테스트 불가
        if len(bars) < self._lookback + 1:
            raise ValueError(f"데이터 부족: {len(bars)}봉 (최소 {self._lookback + 1}봉 필요)")

        # ── 상태 변수 초기화 ──────────────────────────────────────────────────
        # maxlen=lookback+50: 가장 오래된 봉이 자동 삭제 → 메모리 효율
        # +50은 기술 지표 초기화 구간(NaN 봉)을 여유롭게 포함하기 위함
        buffer: deque[Bar] = deque(maxlen=self._lookback + 50)
        trades: list[TradeRecord] = []   # 완결된 거래 기록 (진입+청산 쌍)
        cash = self._cap                 # 현재 사용 가능한 현금
        open_order: Order | None = None  # 현재 보유 중인 포지션 (None=미보유)

        # ── 메인 루프: 봉 하나씩 재생 ────────────────────────────────────────
        for bar in bars:
            buffer.append(bar)

            # ── ① 보유 포지션 청산 체크 ──────────────────────────────────────
            # open_order 가 있으면 현재 봉 종가로 TP/SL/만료 조건 확인
            if open_order is not None:
                action = self._sl_tp_guard.check(open_order, bar.close, bar.timestamp)

                if action != "HOLD":
                    # 청산 조건 충족: 현재 봉 종가로 시장가 청산 주문 실행
                    result = self._trader.submit_order(open_order, bar.close)
                    cost = self._cost_model.sell_cost(result.filled_price, result.filled_qty)
                    self._ord_logger.log(open_order, result)

                    # order.price 는 진입 시 bar.close 로 항상 채워진다 (Optional 타입 좁힘)
                    assert open_order.price is not None

                    # 손익 계산: 진입가 vs 청산가 차이 * 수량
                    if open_order.direction == "BUY":
                        # BUY 진입 → 청산가가 높을수록 이익
                        pnl = (result.filled_price - open_order.price) * result.filled_qty
                    else:
                        # SELL 진입 → 청산가가 낮을수록 이익 (공매도)
                        pnl = (open_order.price - result.filled_price) * result.filled_qty

                    # 현금 복원: 진입 시 사용한 금액 + 손익 - 매도 비용
                    cash += open_order.price * open_order.quantity + pnl - cost

                    # 거래 기록 생성 (진입 + 청산 쌍)
                    trades.append(TradeRecord(
                        ticker=open_order.ticker,
                        direction=open_order.direction,
                        entry_price=open_order.price,
                        exit_price=result.filled_price,
                        quantity=open_order.quantity,
                        entry_time=open_order.order_id,   # 진입 시 order_id = 진입 시각 문자열
                        exit_time=bar.timestamp,
                        exit_reason=action,               # TAKE_PROFIT/STOP_LOSS/TIMEOUT/FORCE_CLOSE
                        # 왕복 비용: 진입 시 매수 비용 + 청산 시 매도 비용
                        cost=cost + self._cost_model.buy_cost(
                            open_order.price, open_order.quantity
                        ),
                    ))
                    open_order = None  # 포지션 해제

            # ── ② 룩백 미달 구간은 신호 생성 생략 ────────────────────────────
            # buffer 에 lookback 봉 이상 쌓이기 전까지는 지표 계산이 의미 없음
            if len(buffer) < self._lookback:
                continue

            # ── ③ 포지션 보유 중에는 신규 신호 생략 ─────────────────────────
            # Phase 1 원칙: 한 번에 하나의 포지션만 (동시 다중 진입 없음)
            if open_order is not None:
                continue

            buf_list = list(buffer)  # deque → list (슬라이싱을 위해)

            # ── ④ 피처 추출 및 정규화 ────────────────────────────────────────
            with self._latency.measure("feature"):
                # FeatureExtractor: Bar 리스트 → shape [N, 14] numpy 행렬
                raw = self._extractor.extract(buf_list)
                # NumericalNormalizer: 마지막 lookback 행 추출 + Z-score 정규화
                num_inp = self._num_norm.transform(buf_list, raw)
                # PatternNormalizer: 마지막 lookback 봉 OHLCV → 0~1 상대 정규화
                pat_inp = self._pat_norm.transform(buf_list)

            # ── ⑤-A 수치 트랙 신호 생성 ─────────────────────────────────────
            # ThresholdModel: RSI + MACD 크로스오버 → NumericalSignal
            with self._latency.measure("numerical"):
                num_sig = self._num_model.run(num_inp)

            # ── ⑤-B 패턴 트랙 신호 생성 ─────────────────────────────────────
            # RuleBasedPatternEngine: 7가지 캔들 패턴 체크 → PatternSignal
            with self._latency.measure("pattern"):
                pat_sig = self._pat_engine.run(pat_inp, buf_list)

            # ── ⑥ 신호 합의 + 가드 적용 ─────────────────────────────────────
            # SignalAggregator: 두 신호 결합 → TradeSignal 또는 None
            trade_sig = self._aggregator.combine(num_sig, pat_sig)
            # LatencyGuard: 추론 지연 5초 초과 신호 폐기
            trade_sig = self._lat_guard.filter(trade_sig)
            # SignalFilter: combined_score < 0.55 신호 폐기
            trade_sig = self._sig_filter.filter(trade_sig)

            # 신호 없음 → 다음 봉으로
            if trade_sig is None:
                continue

            # 최종 통과한 신호 기록 (logs/signals.jsonl)
            self._sig_logger.log(trade_sig)

            # ── ⑦ 수량 계산 ──────────────────────────────────────────────────
            # PositionSizer: min(현재 현금, 초기 자본*10%) // 현재가
            qty = self._sizer.calc_quantity(bar.close, cash)
            if qty <= 0:
                continue  # 현금 부족 → 주문 건너뜀

            # ── ⑧ 주문 생성 및 체결 ──────────────────────────────────────────
            # TripleBarrierGuard: TP/SL 가격 + 만료 시각 계산 → Order 객체 생성
            order = self._barrier_guard.build_order(trade_sig, bar.close, qty, bar.timestamp)
            # order_id: "{ticker}_{HHMMSS}" 형식으로 진입 시각 추적 가능
            order.order_id = f"{bar.ticker}_{bar.timestamp.strftime('%H%M%S')}"
            order.price = bar.close  # 진입가 기록 (청산 시 손익 계산에 사용)

            # PaperTrader: 시장가 즉시 체결 (슬리피지 포함)
            result = self._trader.submit_order(order, bar.close)
            cost = self._cost_model.buy_cost(result.filled_price, qty)
            # 현금 차감: 체결금액 + 매수 비용(수수료+슬리피지)
            cash -= result.filled_price * qty + cost
            self._ord_logger.log(order, result)
            open_order = order  # 포지션 보유 시작

        # ── 성과 평가 ─────────────────────────────────────────────────────────
        # 모든 완결 거래(TradeRecord 리스트)로 성과 지표 계산
        evaluator = PerformanceEvaluator()
        report = evaluator.evaluate(trades, self._cap)
        return report
