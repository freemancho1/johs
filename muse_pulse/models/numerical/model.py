"""수치 분석 트랙 모델.

[Phase 1: ThresholdModel]
  RSI 과매도/과매수 + MACD 크로스오버 조합의 룰 기반 신호 생성.
  단순하지만 해석이 가능하고 파이프라인 전체가 정상 작동하는지 검증하는 데 적합.

[교체 계획]
  Phase 2: 학습 기반 모델(LSTM / Transformer) 로 교체.
  ModelPort 인터페이스를 유지하므로 이 파일만 교체하면 됨.

[신호 조건]
  BUY : RSI < 35 (과매도) AND MACD 골든크로스 (전봉 diff<0, 현봉 diff>=0)
  SELL: RSI > 65 (과매수) AND MACD 데드크로스 (전봉 diff>0, 현봉 diff<=0)
  HOLD: 위 조건 불충족

  confidence 계산 (BUY 예시):
    conf = min(1.0, (rsi_lo - rsi) / rsi_lo + 0.3)
    RSI 가 낮을수록 더 강한 확신도. 기본값 0.3 은 크로스오버 자체의 베이스 신뢰도.
"""
from __future__ import annotations

import time
from datetime import datetime

import numpy as np

from ...core.types import NumericalInput, NumericalSignal
from ...models.numerical.extractor import FeatureExtractor

# FeatureExtractor.FEATURE_NAMES 순서에서 각 피처의 열 인덱스를 미리 매핑.
# ThresholdModel 내에서 w[-1][_IDX["rsi_14"]] 처럼 이름으로 접근 가능.
_IDX = {name: i for i, name in enumerate(FeatureExtractor.FEATURE_NAMES)}


class ThresholdModel:
    """Phase 1 임시 수치 모델 — RSI 과매도/과매수 + MACD 크로스오버."""

    def __init__(
        self,
        rsi_oversold: float = 35.0,    # RSI 과매도 임계값 (이 이하 → BUY 후보)
        rsi_overbought: float = 65.0,  # RSI 과매수 임계값 (이 이상 → SELL 후보)
    ) -> None:
        self._rsi_lo = rsi_oversold
        self._rsi_hi = rsi_overbought

    def predict(
        self, inp: NumericalInput
    ) -> tuple[str, float, dict]:
        """방향, 신뢰도, 피처 기여도 튜플 반환.

        inp.window 는 Z-score 정규화된 값이므로
        절대적인 RSI 35 기준이 아닌 상대적 위치를 판단함에 주의.
        (NumericalNormalizer 가 정규화했으므로 실제 RSI 원본 값이 아님)
        """
        w = inp.window          # shape [N, 14] — Z-score 정규화된 피처 행렬
        last = w[-1]            # 가장 최근 봉의 피처 벡터
        prev = w[-2] if len(w) >= 2 else last  # 직전 봉 피처 (크로스오버 판단용)

        # 주요 피처 추출
        rsi = float(last[_IDX["rsi_14"]])
        macd_diff_now = float(last[_IDX["macd_diff"]])    # 현재 MACD 히스토그램
        macd_diff_prev = float(prev[_IDX["macd_diff"]])   # 전봉 MACD 히스토그램
        bb_pband = float(last[_IDX["bb_pband"]])           # 볼린저밴드 위치
        ret_1 = float(last[_IDX["ret_1"]])                 # 직전 1분 수익률

        # 관측 가능성: 신호에 기여한 피처 값을 항상 기록
        contrib = {
            "rsi_14": rsi,
            "macd_diff": macd_diff_now,
            "bb_pband": bb_pband,
            "ret_1": ret_1,
        }

        # ── BUY 조건: RSI 과매도 + MACD 골든크로스 ───────────────────────────
        # 골든크로스: 히스토그램이 음수에서 양수로 전환 (MACD 선이 시그널 선을 상향 돌파)
        if rsi < self._rsi_lo and macd_diff_prev < 0 and macd_diff_now >= 0:
            # RSI 가 낮을수록 신뢰도 증가: (35-rsi)/35 + 0.3 (최대 1.0 캡)
            conf = min(1.0, (self._rsi_lo - rsi) / self._rsi_lo + 0.3)
            return "BUY", round(conf, 4), contrib

        # ── SELL 조건: RSI 과매수 + MACD 데드크로스 ──────────────────────────
        # 데드크로스: 히스토그램이 양수에서 음수로 전환 (MACD 선이 시그널 선을 하향 돌파)
        if rsi > self._rsi_hi and macd_diff_prev > 0 and macd_diff_now <= 0:
            # RSI 가 높을수록 신뢰도 증가: (rsi-65)/(100-65) + 0.3
            conf = min(1.0, (rsi - self._rsi_hi) / (100 - self._rsi_hi) + 0.3)
            return "SELL", round(conf, 4), contrib

        return "HOLD", 0.0, contrib

    def run(self, inp: NumericalInput) -> NumericalSignal:
        """추론 시간을 측정하며 NumericalSignal 을 생성하고 반환.

        latency_ms 는 LatencyGuard 에서 총 지연시간 계산에 사용된다.
        """
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
