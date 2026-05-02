"""SignalLogger / OrderLogger — 모든 신호·주문·체결을 JSONL 로 기록.

[관측 가능성 원칙]
  전략이 왜 진입/청산했는지, 어떤 피처가 신호를 만들었는지
  나중에 분석할 수 있어야 한다.
  → 모든 신호와 주문을 JSONL(JSON Lines) 형식으로 저장.

[파일 구조]
  logs/
    signals.jsonl  ← 모든 TradeSignal 기록
    orders.jsonl   ← 모든 주문 + 체결 결과 기록

[JSONL 선택 이유]
  한 줄 = 한 레코드 → 파일에 append 만 하면 됨.
  cat signals.jsonl | jq '.data.combined_score' 로 즉시 분석 가능.
  DataFrame 변환: pd.read_json("signals.jsonl", lines=True)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from ..core.types import NumericalSignal, Order, OrderResult, PatternSignal, TradeSignal
from ..config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)


def _serialize(obj):
    """dataclass·datetime → JSON 직렬화 가능한 dict/str 변환."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return {k: _serialize(v) for k, v in vars(obj).items()}
    return obj


class SignalLogger:
    def __init__(self, log_dir: Path | None = None) -> None:
        self._dir = log_dir or settings.log_dir
        self._log = logging.getLogger("signal")

    def log(self, signal: NumericalSignal | PatternSignal | TradeSignal) -> None:
        """신호를 Python logging + JSONL 파일 두 곳에 동시 기록.

        type 필드로 신호 종류(NumericalSignal/PatternSignal/TradeSignal)를 구분.
        data 필드에 신호의 모든 속성 포함 (feature_contrib 포함 → 사후 분석 가능).
        """
        record = {
            "type": type(signal).__name__,
            "data": _serialize(signal),
        }
        self._log.info(json.dumps(record, ensure_ascii=False, default=str))
        self._append("signals.jsonl", record)

    def _append(self, filename: str, record: dict) -> None:
        """JSONL 파일에 한 줄 추가 (append 모드)."""
        path = self._dir / filename
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


class OrderLogger:
    def __init__(self, log_dir: Path | None = None) -> None:
        self._dir = log_dir or settings.log_dir
        self._log = logging.getLogger("order")

    def log(self, order: Order, result: OrderResult) -> None:
        """주문과 체결 결과를 함께 기록.

        order: 방향·수량·TP/SL·만료 시각 포함
        result: 실제 체결가·수량·슬리피지 포함
        두 객체를 함께 기록해야 "진입 의도 vs 실제 체결" 비교 분석 가능.
        """
        record = {
            "order": _serialize(order),
            "result": _serialize(result),
        }
        self._log.info(json.dumps(record, ensure_ascii=False, default=str))
        self._append("orders.jsonl", record)

    def _append(self, filename: str, record: dict) -> None:
        path = self._dir / filename
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
