"""수치 분석 트랙 모델.

Phase 1: ThresholdModel — RSI/MACD 임계값 기반 신호 생성.
'반드시 변경될 것': 학습 기반 모델(LSTM/Transformer)로 교체 예정.
ModelPort 인터페이스를 유지하면 교체 시 이 파일만 변경한다.
"""
from __future__ import annotations

import time
from datetime import datetime

import numpy as np

from ...core.types import NumericalInput, NumericalSignal
from ...models.numerical.extractor import FeatureExtractor

# 피처 인덱스 (FeatureExtractor.FEATURE_NAMES 순서 기준)
_IDX = {name: i for i, name in enumerate(FeatureExtractor.FEATURE_NAMES)}


class ThresholdModel:
    """Phase 1 임시 모델 — RSI 과매도/과매수 + MACD 크로스오버."""

    def __init__(
        self,
        rsi_oversold: float = 35.0,
        rsi_overbought: float = 65.0,
    ) -> None:
        self._rsi_lo = rsi_oversold
        self._rsi_hi = rsi_overbought

    def predict(
        self, inp: NumericalInput
    ) -> tuple[str, float, dict]:
        """(direction, confidence, feature_contrib) 반환."""
        w = inp.window           # shape [N, num_features]
        last = w[-1]
        prev = w[-2] if len(w) >= 2 else last

        rsi = float(last[_IDX["rsi_14"]])
        macd_diff_now = float(last[_IDX["macd_diff"]])
        macd_diff_prev = float(prev[_IDX["macd_diff"]])
        bb_pband = float(last[_IDX["bb_pband"]])
        ret_1 = float(last[_IDX["ret_1"]])

        contrib = {
            "rsi_14": rsi,
            "macd_diff": macd_diff_now,
            "bb_pband": bb_pband,
            "ret_1": ret_1,
        }

        # 매수 조건: RSI 과매도 + MACD 골든크로스
        if rsi < self._rsi_lo and macd_diff_prev < 0 and macd_diff_now >= 0:
            conf = min(1.0, (self._rsi_lo - rsi) / self._rsi_lo + 0.3)
            return "BUY", round(conf, 4), contrib

        # 매도 조건: RSI 과매수 + MACD 데드크로스
        if rsi > self._rsi_hi and macd_diff_prev > 0 and macd_diff_now <= 0:
            conf = min(1.0, (rsi - self._rsi_hi) / (100 - self._rsi_hi) + 0.3)
            return "SELL", round(conf, 4), contrib

        return "HOLD", 0.0, contrib

    def run(self, inp: NumericalInput) -> NumericalSignal:
        t0 = time.perf_counter()
        direction, confidence, contrib = self.predict(inp)
        latency_ms = (time.perf_counter() - t0) * 1000
        return NumericalSignal(
            ticker=inp.ticker,
            timestamp=inp.bar_timestamp,
            direction=direction,
            confidence=confidence,
            feature_contrib=contrib,
            latency_ms=latency_ms,
        )
