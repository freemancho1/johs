"""FeatureExtractor — OHLCV → 기술적 지표 피처 행렬.

ta 라이브러리 기반. RSI / MACD / 볼린저밴드 / OBV / ATR.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ...core.types import Bar

try:
    import ta
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False


class FeatureExtractor:
    """Bar 리스트 → numpy 피처 행렬 변환."""

    FEATURE_NAMES = [
        "rsi_14",
        "macd", "macd_signal", "macd_diff",
        "bb_upper", "bb_mid", "bb_lower", "bb_pband",
        "obv",
        "atr_14",
        "volume_ratio",   # 현재 거래량 / 20봉 평균
        "ret_1", "ret_5", "ret_20",
    ]

    def extract(self, bars: list[Bar]) -> np.ndarray:
        """shape [len(bars), len(FEATURE_NAMES)] 반환."""
        df = self._to_df(bars)
        features = self._compute(df)
        return features.values.astype(np.float32)

    def _to_df(self, bars: list[Bar]) -> pd.DataFrame:
        return pd.DataFrame({
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [float(b.volume) for b in bars],
        })

    def _compute(self, df: pd.DataFrame) -> pd.DataFrame:
        c = df["close"]
        h = df["high"]
        lo = df["low"]
        v = df["volume"]

        if _TA_AVAILABLE:
            rsi = ta.momentum.RSIIndicator(c, window=14).rsi()
            macd_obj = ta.trend.MACD(c)
            macd = macd_obj.macd()
            macd_sig = macd_obj.macd_signal()
            macd_diff = macd_obj.macd_diff()
            bb = ta.volatility.BollingerBands(c, window=20, window_dev=2)
            bb_upper = bb.bollinger_hband()
            bb_mid = bb.bollinger_mavg()
            bb_lower = bb.bollinger_lband()
            bb_pband = bb.bollinger_pband()
            obv = ta.volume.OnBalanceVolumeIndicator(c, v).on_balance_volume()
            atr = ta.volatility.AverageTrueRange(h, lo, c, window=14).average_true_range()
        else:
            # ta 없을 때 직접 계산 (fallback)
            rsi = self._rsi(c, 14)
            macd, macd_sig, macd_diff = self._macd(c)
            bb_upper, bb_mid, bb_lower = self._bollinger(c)
            bb_pband = (c - bb_lower) / (bb_upper - bb_lower + 1e-8)
            obv = (v * np.sign(c.diff())).cumsum()
            atr = (h - lo).rolling(14).mean()

        vol_ratio = v / (v.rolling(20).mean() + 1e-8)
        ret_1 = c.pct_change(1)
        ret_5 = c.pct_change(5)
        ret_20 = c.pct_change(20)

        result = pd.DataFrame({
            "rsi_14": rsi,
            "macd": macd,
            "macd_signal": macd_sig,
            "macd_diff": macd_diff,
            "bb_upper": bb_upper,
            "bb_mid": bb_mid,
            "bb_lower": bb_lower,
            "bb_pband": bb_pband,
            "obv": obv,
            "atr_14": atr,
            "volume_ratio": vol_ratio,
            "ret_1": ret_1,
            "ret_5": ret_5,
            "ret_20": ret_20,
        })
        return result.fillna(0.0)

    @staticmethod
    def _rsi(close: pd.Series, window: int) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = (-delta.clip(upper=0)).rolling(window).mean()
        rs = gain / (loss + 1e-8)
        return 100 - 100 / (1 + rs)

    @staticmethod
    def _macd(close: pd.Series):
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        return macd, signal, macd - signal

    @staticmethod
    def _bollinger(close: pd.Series, window: int = 20):
        mid = close.rolling(window).mean()
        std = close.rolling(window).std()
        return mid + 2 * std, mid, mid - 2 * std
