"""정규화 레이어 — 수치 트랙(롤링 Z-score)과 패턴 트랙(0~1 상대 정규화).

[왜 두 가지 정규화를 쓰는가]
  수치 트랙(NumericalNormalizer):
    RSI, MACD, 볼린저밴드 등 기술 지표의 "지금이 평소와 얼마나 다른가"를 표현해야 한다.
    → 롤링 Z-score: (현재값 - 최근 평균) / 최근 표준편차
    → 결과값 0은 평균, +2는 2σ 위 비정상적 상승, -2는 2σ 아래 비정상적 하락.

  패턴 트랙(PatternNormalizer):
    캔들 패턴은 절대 가격 수준과 무관해야 한다 (20만원 주식의 망치형 = 5만원 주식의 망치형).
    → 0~1 Min-Max 정규화: 윈도우 내 최저가를 0, 최고가를 1로 매핑.
    → 동일 패턴이 가격대에 무관하게 같은 특징 벡터를 가지게 됨.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.types import Bar, NumericalInput, PatternInput
from ..config.settings import settings


class NumericalNormalizer:
    """롤링 Z-score 정규화.

    입력: Bar 리스트 + FeatureExtractor 가 계산한 raw feature_matrix (shape [N, 14])
    출력: NumericalInput (window: 마지막 lookback 행만 추출 후 Z-score 적용)

    Z-score 계산 방식:
      mu  = window 전체 행의 컬럼별 평균
      std = window 전체 행의 컬럼별 표준편차 + 1e-8 (0 나눗셈 방지)
      normalized = (window - mu) / std
    """

    def __init__(self, window_size: int | None = None) -> None:
        # lookback_minutes 기본값: settings.phase.lookback_minutes = 120
        self._w = window_size or settings.phase.lookback_minutes

    def transform(self, bars: list[Bar], feature_matrix: np.ndarray) -> NumericalInput:
        """feature_matrix: shape [len(bars), num_features] — FeatureExtractor.extract() 결과.

        마지막 self._w 개 행만 잘라서 Z-score 적용.
        전체를 쓰지 않고 마지막 윈도우만 쓰는 이유: 롤링 정규화이므로 최근 기간 기준.
        """
        if len(bars) < self._w:
            raise ValueError(
                f"롤백 윈도우({self._w})보다 데이터가 부족합니다: {len(bars)}봉."
            )

        window = feature_matrix[-self._w:]   # 최근 lookback 행 추출
        mu = window.mean(axis=0)             # 각 피처의 평균 (shape [14])
        std = window.std(axis=0) + 1e-8      # 각 피처의 표준편차 (0 방지)
        normalized = (window - mu) / std      # Z-score 변환

        return NumericalInput(
            window=normalized.astype(np.float32),
            window_size=self._w,
            ticker=bars[-1].ticker,
            bar_timestamp=bars[-1].timestamp,
        )


class PatternNormalizer:
    """윈도우 내 최저가~최고가를 0~1로 매핑하는 상대 정규화.

    입력: Bar 리스트 (버퍼에서 마지막 lookback 개 봉 사용)
    출력: PatternInput (ohlcv_series: OHLC는 0~1, Volume은 max 기준 0~1)

    [가격 정규화]
      p_min = 윈도우 내 모든 OHLC 값의 최솟값
      p_max = 윈도우 내 모든 OHLC 값의 최댓값
      price_norm = (price - p_min) / (p_max - p_min)
      → 값 0 = 윈도우 내 최저점, 1 = 윈도우 내 최고점

    [거래량 정규화]
      vol_norm = volume / max_volume_in_window
      → OHLC 와 별도로 정규화하는 이유: 가격 단위와 거래량 단위가 완전히 다르기 때문.
    """

    def __init__(self, window_size: int | None = None) -> None:
        self._w = window_size or settings.phase.lookback_minutes

    def transform(self, bars: list[Bar]) -> PatternInput:
        """Bar 리스트에서 마지막 lookback 봉을 OHLCV 행렬로 변환 후 정규화."""
        if len(bars) < self._w:
            raise ValueError(
                f"롤백 윈도우({self._w})보다 데이터가 부족합니다: {len(bars)}봉."
            )

        window_bars = bars[-self._w:]
        # shape [lookback, 5]: 각 행 = [Open, High, Low, Close, Volume]
        ohlcv = np.array(
            [[b.open, b.high, b.low, b.close, b.volume] for b in window_bars],
            dtype=np.float64,
        )

        # 가격 4개 열(Open, High, Low, Close) 0~1 Min-Max 정규화
        price_cols = ohlcv[:, :4]
        p_min = price_cols.min()
        p_max = price_cols.max()
        if p_max - p_min < 1e-8:
            # 가격 변동이 없는 경우(극단적 상황) → 모든 값을 0으로
            price_norm = np.zeros_like(price_cols)
        else:
            price_norm = (price_cols - p_min) / (p_max - p_min)

        # 거래량 열: 윈도우 내 최대 거래량 기준 0~1
        vol_col = ohlcv[:, 4:5]
        v_max = vol_col.max()
        vol_norm = vol_col / (v_max + 1e-8)

        # 두 정규화 결과를 다시 합쳐서 [lookback, 5] shape 복원
        normalized = np.concatenate([price_norm, vol_norm], axis=1).astype(np.float32)

        return PatternInput(
            ohlcv_series=normalized,
            ticker=bars[-1].ticker,
            bar_timestamp=bars[-1].timestamp,
        )
