"""FeatureExtractor — OHLCV Bar 리스트 → 기술적 지표 피처 행렬(numpy).

[14개 피처]
  모멘텀:  rsi_14
  추세:    macd, macd_signal, macd_diff
  변동성:  bb_upper, bb_mid, bb_lower, bb_pband, atr_14
  거래량:  obv, volume_ratio
  수익률:  ret_1, ret_5, ret_20

[ta 라이브러리]
  기본은 'ta' 패키지 사용. 없으면 직접 구현 fallback 실행.
  두 구현이 동일 결과를 내도록 설계되어 있으나,
  production 에서는 ta 설치를 권장 (검증된 구현).

[이 행렬이 어디로 가는가]
  extractor.extract(bars)  →  NumericalNormalizer.transform(bars, matrix)
  → Z-score 정규화 후 NumericalInput 으로 감싸져 ThresholdModel 에 전달.
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

    # 피처 순서 고정 — ThresholdModel 의 _IDX 매핑과 반드시 일치해야 함
    FEATURE_NAMES = [
        "rsi_14",                              # RSI(14): 과매수/과매도 모멘텀
        "macd", "macd_signal", "macd_diff",    # MACD: 추세 전환 감지
        "bb_upper", "bb_mid", "bb_lower",      # 볼린저밴드: 가격 채널
        "bb_pband",                            # 볼린저밴드 위치 (0=하단, 1=상단)
        "obv",                                 # OBV: 거래량-가격 확산 지표
        "atr_14",                              # ATR(14): 변동성 크기
        "volume_ratio",                        # 현재 거래량 / 최근 20봉 평균
        "ret_1", "ret_5", "ret_20",            # 1분/5분/20분 수익률
    ]

    def extract(self, bars: list[Bar]) -> np.ndarray:
        """Bar 리스트 → shape [len(bars), 14] float32 행렬.

        NaN 은 0.0으로 채워진다 (초기 봉에서 지표 계산 전 NaN 발생).
        """
        df = self._to_df(bars)
        features = self._compute(df)
        return features.values.astype(np.float32)

    def _to_df(self, bars: list[Bar]) -> pd.DataFrame:
        """Bar 리스트 → pandas DataFrame 변환."""
        return pd.DataFrame({
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [float(b.volume) for b in bars],
        })

    def _compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """14개 기술 지표 계산."""
        c = df["close"]
        h = df["high"]
        lo = df["low"]
        v = df["volume"]

        if _TA_AVAILABLE:
            # ── ta 라이브러리 사용 (권장) ─────────────────────────────────────
            rsi = ta.momentum.RSIIndicator(c, window=14).rsi()

            macd_obj = ta.trend.MACD(c)
            macd = macd_obj.macd()           # MACD 선 = EMA(12) - EMA(26)
            macd_sig = macd_obj.macd_signal() # 시그널 선 = MACD.EMA(9)
            macd_diff = macd_obj.macd_diff()  # 히스토그램 = MACD - Signal

            bb = ta.volatility.BollingerBands(c, window=20, window_dev=2)
            bb_upper = bb.bollinger_hband()   # 상단밴드 = 20MA + 2σ
            bb_mid = bb.bollinger_mavg()      # 중간밴드 = 20MA
            bb_lower = bb.bollinger_lband()   # 하단밴드 = 20MA - 2σ
            # pband: (close - lower) / (upper - lower) → 0=하단, 0.5=중간, 1=상단
            bb_pband = bb.bollinger_pband()

            obv = ta.volume.OnBalanceVolumeIndicator(c, v).on_balance_volume()
            atr = ta.volatility.AverageTrueRange(h, lo, c, window=14).average_true_range()
        else:
            # ── fallback: ta 없을 때 직접 계산 ──────────────────────────────
            rsi = self._rsi(c, 14)
            macd, macd_sig, macd_diff = self._macd(c)
            bb_upper, bb_mid, bb_lower = self._bollinger(c)
            bb_pband = (c - bb_lower) / (bb_upper - bb_lower + 1e-8)
            obv = (v * np.sign(c.diff())).cumsum()
            atr = (h - lo).rolling(14).mean()

        # ── 공통 계산 ─────────────────────────────────────────────────────────
        # volume_ratio: 현재 거래량이 최근 20봉 평균의 몇 배인가 (거래량 급증 감지)
        vol_ratio = v / (v.rolling(20).mean() + 1e-8)
        # 단기~중기 수익률: 모멘텀 및 추세 확인용
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
        # 초반 봉(지표 계산 불가 구간)의 NaN → 0.0 채움
        return result.fillna(0.0)

    # ── fallback 구현 ──────────────────────────────────────────────────────────

    @staticmethod
    def _rsi(close: pd.Series, window: int) -> pd.Series:
        """Wilder 방식 RSI.
        gain/loss 를 rolling mean 으로 계산 (ta 와 동일 결과).
        """
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = (-delta.clip(upper=0)).rolling(window).mean()
        rs = gain / (loss + 1e-8)
        return 100 - 100 / (1 + rs)

    @staticmethod
    def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
        """표준 MACD: EMA(12) - EMA(26), 시그널 EMA(9)."""
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        return macd, signal, macd - signal

    @staticmethod
    def _bollinger(close: pd.Series, window: int = 20) -> tuple[pd.Series, pd.Series, pd.Series]:
        """볼린저밴드: 20MA ± 2σ."""
        mid = close.rolling(window).mean()
        std = close.rolling(window).std()
        return mid + 2 * std, mid, mid - 2 * std
