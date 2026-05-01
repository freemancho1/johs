"""HistoricalDataLoader — 과거 분봉 데이터 수집 및 로컬 캐싱.

Phase 1: pykrx 일봉 기반 합성 분봉 생성 (KIS REST API 키 미설정 시 대체).
KIS_APP_KEY 환경변수가 설정되어 있으면 KIS REST API 로 실제 분봉 수집.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ..core.types import Bar
from ..config.settings import settings
from .store import LocalParquetStore
from .calendar import trading_days, market_open_dt, KST

_MINUTES_PER_DAY = 390   # 09:00~15:30


class HistoricalDataLoader:
    def __init__(self, store: LocalParquetStore | None = None) -> None:
        self._store = store or LocalParquetStore()

    def load(
        self,
        ticker: str,
        start: date,
        end: date,
        force_refresh: bool = False,
    ) -> list[Bar]:
        """캐시 우선 로드. 캐시 없으면 수집 후 저장."""
        start_dt = datetime.combine(start, datetime.min.time(), tzinfo=KST)
        end_dt = datetime.combine(end, datetime.max.time(), tzinfo=KST)

        cached = self._store.load_bars(ticker, start_dt, end_dt)
        if cached and not force_refresh:
            return cached

        bars = self._fetch(ticker, start, end)
        self._store.save_bars(bars)
        return bars

    def _fetch(self, ticker: str, start: date, end: date) -> list[Bar]:
        if settings.kis_app_key:
            return self._fetch_kis(ticker, start, end)
        return self._fetch_synthetic(ticker, start, end)

    def _fetch_kis(self, ticker: str, start: date, end: date) -> list[Bar]:
        """KIS REST API 분봉 조회 (stub — API 키 설정 후 구현)."""
        raise NotImplementedError(
            "KIS REST API 분봉 수집은 KIS_APP_KEY 설정 후 kis_client.py 에서 구현 예정."
        )

    def _fetch_synthetic(self, ticker: str, start: date, end: date) -> list[Bar]:
        """pykrx 일봉을 기반으로 분봉을 합성 (개발/테스트 용도).
        실거래 배포 시 반드시 실제 분봉으로 교체해야 한다.
        """
        try:
            from pykrx import stock as krx
        except ImportError:
            raise RuntimeError("pykrx 패키지가 필요합니다: pip install pykrx")

        from_str = start.strftime("%Y%m%d")
        to_str = end.strftime("%Y%m%d")
        df = krx.get_market_ohlcv_by_date(from_str, to_str, ticker)
        if df.empty:
            return []

        bars: list[Bar] = []
        rng = np.random.default_rng(seed=42)

        for day, row in df.iterrows():
            d = day.date() if hasattr(day, "date") else day
            o, h, l, c, v = (
                float(row["시가"]), float(row["고가"]),
                float(row["저가"]), float(row["종가"]),
                int(row["거래량"]),
            )
            bars.extend(_synthesize_minute_bars(ticker, d, o, h, l, c, v, rng))

        return bars


def _synthesize_minute_bars(
    ticker: str,
    d: date,
    day_open: float,
    day_high: float,
    day_low: float,
    day_close: float,
    day_volume: int,
    rng: np.random.Generator,
) -> list[Bar]:
    """일봉 OHLCV → 분봉 390개 합성.
    브라운 운동 기반으로 종가가 day_close 에 수렴하도록 생성.
    """
    n = _MINUTES_PER_DAY
    # 수익률 경로 생성
    drift = (day_close / day_open - 1.0) / n
    vol = abs(day_high - day_low) / day_open / np.sqrt(n) * 1.5
    increments = rng.normal(drift, vol, n)
    prices = day_open * np.cumprod(1 + increments)
    # 고가/저가 범위 내로 클리핑
    prices = np.clip(prices, day_low, day_high)
    prices[-1] = day_close  # 종가 고정

    # 거래량 분산 — 시가·점심·마감에 집중
    vol_weights = _volume_weights(n, rng)
    volumes = (vol_weights * day_volume).astype(int)

    open_dt = market_open_dt(d)
    bars: list[Bar] = []
    prev = day_open
    for i in range(n):
        ts = open_dt + timedelta(minutes=i)
        o = prev
        c = prices[i]
        h = max(o, c) * (1 + rng.uniform(0, vol * 0.5))
        lo = min(o, c) * (1 - rng.uniform(0, vol * 0.5))
        h = min(h, day_high)
        lo = max(lo, day_low)
        bars.append(Bar(
            ticker=ticker,
            timestamp=ts,
            open=round(o, 0),
            high=round(h, 0),
            low=round(lo, 0),
            close=round(c, 0),
            volume=int(volumes[i]),
            is_complete=True,
        ))
        prev = c
    return bars


def _volume_weights(n: int, rng: np.random.Generator) -> np.ndarray:
    """시가(처음 30분), 점심(120~150분), 마감(360~390분)에 거래량 집중."""
    w = rng.uniform(0.5, 1.5, n)
    w[:30] *= 3.0
    w[120:150] *= 1.5
    w[360:] *= 2.5
    return w / w.sum()
