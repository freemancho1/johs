"""Triple Barrier 라벨링.

익절선·손절선·시간만료 중 먼저 닿는 것을 라벨로 사용.
 1 : 익절 (take_profit 먼저 도달)
-1 : 손절 (stop_loss 먼저 도달)
 0 : 시간만료 (두 선 모두 닿지 않고 time_horizon 경과)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config.settings import TripleBarrierConfig, settings


class LabelGenerator:
    def __init__(self, cfg: TripleBarrierConfig | None = None) -> None:
        self._cfg = cfg or settings.triple_barrier

    def label(self, closes: pd.Series) -> pd.Series:
        """
        Parameters
        ----------
        closes : pd.Series
            분봉 종가 시계열 (DatetimeIndex).

        Returns
        -------
        pd.Series
            인덱스가 closes 와 동일한 라벨 시리즈 (1 / -1 / 0).
            마지막 time_horizon 봉은 라벨 생성 불가 → NaN.
        """
        tp = self._cfg.take_profit
        sl = self._cfg.stop_loss
        h = self._cfg.time_horizon

        labels = pd.Series(index=closes.index, dtype=float)

        for i in range(len(closes) - 1):
            entry = closes.iloc[i]
            future = closes.iloc[i + 1: i + h + 1]
            if future.empty:
                break
            ret = (future - entry) / entry
            first_tp = (ret >= tp).idxmax() if (ret >= tp).any() else None
            first_sl = (ret <= -sl).idxmax() if (ret <= -sl).any() else None

            if first_tp is None and first_sl is None:
                labels.iloc[i] = 0
            elif first_tp is None:
                labels.iloc[i] = -1
            elif first_sl is None:
                labels.iloc[i] = 1
            else:
                labels.iloc[i] = 1 if first_tp <= first_sl else -1

        return labels

    def label_bars(self, closes: list[float]) -> np.ndarray:
        """단순 배열 버전 — 백테스트 시뮬레이터에서 사용."""
        tp = self._cfg.take_profit
        sl = self._cfg.stop_loss
        h = self._cfg.time_horizon
        n = len(closes)
        result = np.full(n, np.nan)

        for i in range(n - 1):
            entry = closes[i]
            end = min(i + h + 1, n)
            for j in range(i + 1, end):
                ret = (closes[j] - entry) / entry
                if ret >= tp:
                    result[i] = 1.0
                    break
                if ret <= -sl:
                    result[i] = -1.0
                    break
            else:
                result[i] = 0.0

        return result
