"""정규화 — 수치 트랙(롤링 Z-score)과 패턴 트랙(0~1 상대 정규화)은 방식이 다르다."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.types import Bar, NumericalInput, PatternInput
from ..config.settings import settings


class NumericalNormalizer:
    """롤링 Z-score 정규화.
    '지금 이 시점의 평소 대비 비정상도'를 표현한다.
    """

    def __init__(self, window_size: int | None = None) -> None:
        self._w = window_size or settings.phase.lookback_minutes

    def transform(self, bars: list[Bar], feature_matrix: np.ndarray) -> NumericalInput:
        """feature_matrix: shape [len(bars), num_features] — raw 피처."""
        if len(bars) < self._w:
            raise ValueError(
                f"롤백 윈도우({self._w})보다 데이터가 부족합니다: {len(bars)}봉."
            )
        window = feature_matrix[-self._w:]
        mu = window.mean(axis=0)
        std = window.std(axis=0) + 1e-8
        normalized = (window - mu) / std
        return NumericalInput(
            window=normalized.astype(np.float32),
            window_size=self._w,
            ticker=bars[-1].ticker,
            bar_timestamp=bars[-1].timestamp,
        )


class PatternNormalizer:
    """윈도우 내 최저~최고가를 0~1로 매핑하는 상대 정규화.
    절대 가격이 아닌 형태가 핵심이므로 종목·가격대와 무관하게 동일 패턴을 인식한다.
    """

    def __init__(self, window_size: int | None = None) -> None:
        self._w = window_size or settings.phase.lookback_minutes

    def transform(self, bars: list[Bar]) -> PatternInput:
        if len(bars) < self._w:
            raise ValueError(
                f"롤백 윈도우({self._w})보다 데이터가 부족합니다: {len(bars)}봉."
            )
        window_bars = bars[-self._w:]
        ohlcv = np.array(
            [[b.open, b.high, b.low, b.close, b.volume] for b in window_bars],
            dtype=np.float64,
        )
        # 가격 열(OHLC)만 0~1 정규화; 거래량은 별도 정규화
        price_cols = ohlcv[:, :4]
        p_min = price_cols.min()
        p_max = price_cols.max()
        if p_max - p_min < 1e-8:
            price_norm = np.zeros_like(price_cols)
        else:
            price_norm = (price_cols - p_min) / (p_max - p_min)

        vol_col = ohlcv[:, 4:5]
        v_max = vol_col.max()
        vol_norm = vol_col / (v_max + 1e-8)

        normalized = np.concatenate([price_norm, vol_norm], axis=1).astype(np.float32)
        return PatternInput(
            ohlcv_series=normalized,
            ticker=bars[-1].ticker,
            bar_timestamp=bars[-1].timestamp,
        )
