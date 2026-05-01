"""SignalLogger / OrderLogger — 모든 신호·주문·체결을 JSONL 로 기록."""
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
        record = {
            "type": type(signal).__name__,
            "data": _serialize(signal),
        }
        self._log.info(json.dumps(record, ensure_ascii=False, default=str))
        self._append("signals.jsonl", record)

    def _append(self, filename: str, record: dict) -> None:
        path = self._dir / filename
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


class OrderLogger:
    def __init__(self, log_dir: Path | None = None) -> None:
        self._dir = log_dir or settings.log_dir
        self._log = logging.getLogger("order")

    def log(self, order: Order, result: OrderResult) -> None:
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
