"""HistoricalSimulator — 과거 분봉 재생 기반 백테스트.

봉 완성 이벤트 타이밍을 실거래와 동일하게 재현한다.
FeaturePipeline → 두 트랙 → SignalConfluenceEngine → RiskManager → PaperTrader
전 과정을 단일 루프에서 실행한다.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime

from tqdm import tqdm

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
        self._lookback = lookback or settings.phase.lookback_minutes

        # 컴포넌트 초기화
        self._validator = BarValidator()
        self._num_norm = NumericalNormalizer(self._lookback)
        self._pat_norm = PatternNormalizer(self._lookback)
        self._extractor = FeatureExtractor()
        self._num_model = ThresholdModel()
        self._pat_engine = RuleBasedPatternEngine()
        self._aggregator = SignalAggregator()
        self._lat_guard = LatencyGuard()
        self._sig_filter = SignalFilter()
        self._cost_model = CostModel()
        self._sizer = PositionSizer(self._cap)
        self._barrier_guard = TripleBarrierGuard()
        self._sl_tp_guard = StopLossTakeProfitGuard()
        self._trader = PaperTrader()
        self._tracker = OrderStateTracker()
        self._sig_logger = SignalLogger()
        self._ord_logger = OrderLogger()
        self._latency = LatencyMonitor()

    def run(self, bars: list[Bar]) -> PerformanceReport:
        bars = self._validator.filter(bars)
        if len(bars) < self._lookback + 1:
            raise ValueError(f"데이터 부족: {len(bars)}봉 (최소 {self._lookback + 1}봉 필요)")

        buffer: deque[Bar] = deque(maxlen=self._lookback + 50)
        trades: list[TradeRecord] = []
        cash = self._cap
        open_order: Order | None = None

        for bar in tqdm(bars, desc="백테스트 진행"):
            buffer.append(bar)

            # ── 보유 포지션 청산 체크 ──────────────────────────────────────
            if open_order is not None:
                action = self._sl_tp_guard.check(open_order, bar.close, bar.timestamp)
                if action != "HOLD":
                    result = self._trader.submit_order(open_order, bar.close)
                    cost = self._cost_model.sell_cost(result.filled_price, result.filled_qty)
                    self._ord_logger.log(open_order, result)

                    # 손익 계산 후 cash 복원
                    if open_order.direction == "BUY":
                        pnl = (result.filled_price - open_order.price) * result.filled_qty
                    else:
                        pnl = (open_order.price - result.filled_price) * result.filled_qty
                    cash += open_order.price * open_order.quantity + pnl - cost

                    trades.append(TradeRecord(
                        ticker=open_order.ticker,
                        direction=open_order.direction,
                        entry_price=open_order.price,
                        exit_price=result.filled_price,
                        quantity=open_order.quantity,
                        entry_time=open_order.order_id,
                        exit_time=bar.timestamp,
                        exit_reason=action,
                        cost=cost + self._cost_model.buy_cost(
                            open_order.price, open_order.quantity
                        ),
                    ))
                    open_order = None

            if len(buffer) < self._lookback:
                continue

            # ── 신규 신호 생성 (포지션 없을 때만) ─────────────────────────
            if open_order is not None:
                continue

            buf_list = list(buffer)

            # 피처 추출 + 정규화
            with self._latency.measure("feature"):
                raw = self._extractor.extract(buf_list)
                num_inp = self._num_norm.transform(buf_list, raw)
                pat_inp = self._pat_norm.transform(buf_list)

            # 수치 트랙
            with self._latency.measure("numerical"):
                num_sig = self._num_model.run(num_inp)

            # 패턴 트랙
            with self._latency.measure("pattern"):
                pat_sig = self._pat_engine.run(pat_inp, buf_list)

            # 신호 합의
            trade_sig = self._aggregator.combine(num_sig, pat_sig)
            trade_sig = self._lat_guard.filter(trade_sig)
            trade_sig = self._sig_filter.filter(trade_sig)

            if trade_sig is None:
                continue

            self._sig_logger.log(trade_sig)

            # 주문 생성
            qty = self._sizer.calc_quantity(bar.close, cash)
            if qty <= 0:
                continue

            order = self._barrier_guard.build_order(trade_sig, bar.close, qty, bar.timestamp)
            order.order_id = f"{bar.ticker}_{bar.timestamp.strftime('%H%M%S')}"
            order.price = bar.close

            result = self._trader.submit_order(order, bar.close)
            cost = self._cost_model.buy_cost(result.filled_price, qty)
            cash -= result.filled_price * qty + cost
            self._ord_logger.log(order, result)
            open_order = order

        evaluator = PerformanceEvaluator()
        report = evaluator.evaluate(trades, self._cap)
        return report
