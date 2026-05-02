"""HistoricalDataLoader — 과거 분봉 데이터 수집 및 로컬 캐싱.

[수집 전략]
  1순위: LocalParquetStore 캐시 → 같은 구간이 저장되어 있으면 재수집 생략.
  2순위: KIS_APP_KEY 환경변수 설정 시 KIS REST API 로 실제 분봉 조회 (미구현 stub).
  3순위: pykrx 일봉 기반 합성 분봉 생성 (Phase 1 개발·테스트 전용).

[합성 분봉의 한계]
  브라운 운동으로 생성한 분봉은 실제 틱 데이터와 통계 분포가 완전히 다르다.
  따라서 이 데이터로 나온 백테스트 결과는 전략 아이디어 검증 수준이며,
  실거래 전 반드시 실제 KIS 분봉 데이터로 교체해야 한다.
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

_MINUTES_PER_DAY = 390   # 09:00~15:30 = 390분


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
        """캐시 우선 로드. 캐시 없거나 force_refresh=True 이면 수집 후 저장.

        [흐름]
          1. start~end datetime 범위로 캐시 조회
          2. 캐시 히트 → 즉시 반환 (수집 없음)
          3. 캐시 미스 → _fetch() → store.save_bars() → 반환
        """
        # date → datetime 변환: start는 당일 00:00:00, end는 당일 23:59:59
        start_dt = datetime.combine(start, datetime.min.time(), tzinfo=KST)
        end_dt = datetime.combine(end, datetime.max.time(), tzinfo=KST)

        cached = self._store.load_bars(ticker, start_dt, end_dt)
        if cached and not force_refresh:
            return cached

        bars = self._fetch(ticker, start, end)
        self._store.save_bars(bars)
        return bars

    def _fetch(self, ticker: str, start: date, end: date) -> list[Bar]:
        """API 키 유무에 따라 실제 KIS API 또는 합성 데이터 선택."""
        if settings.kis_app_key:
            return self._fetch_kis(ticker, start, end)
        return self._fetch_synthetic(ticker, start, end)

    def _fetch_kis(self, ticker: str, start: date, end: date) -> list[Bar]:
        """KIS REST API 분봉 조회 (stub — API 키 설정 후 kis_client.py 에서 구현).

        구현 시 고려사항:
          - KIS API 는 한 번에 최대 100~200봉만 반환 → 날짜 범위를 쪼개서 반복 호출
          - OAuth 토큰 만료(약 24시간) 처리 필요
          - 요청 한도 초과(429) 시 지수 백오프 재시도
        """
        raise NotImplementedError(
            "KIS REST API 분봉 수집은 KIS_APP_KEY 설정 후 kis_client.py 에서 구현 예정."
        )

    def _fetch_synthetic(self, ticker: str, start: date, end: date) -> list[Bar]:
        """pykrx 일봉 OHLCV → 분봉 390개×영업일 수 합성.

        [경고] 개발/테스트 전용. 실거래 배포 시 반드시 실제 분봉으로 교체.
        합성 봉은 브라운 운동 기반이므로 실제 KOSPI 미시구조(호가창, 체결 패턴)와 다름.
        """
        try:
            from pykrx import stock as krx
        except ImportError:
            raise RuntimeError("pykrx 패키지가 필요합니다: pip install pykrx")

        from_str = start.strftime("%Y%m%d")
        to_str = end.strftime("%Y%m%d")
        # pykrx 일봉 조회: 컬럼 = 시가, 고가, 저가, 종가, 거래량 (한국어 컬럼명)
        df = krx.get_market_ohlcv_by_date(from_str, to_str, ticker)
        if df.empty:
            return []

        bars: list[Bar] = []
        # seed=42 고정: 동일 조건에서 동일 합성 결과 재현 가능 → 백테스트 재현성
        rng = np.random.default_rng(seed=42)

        for day, row in df.iterrows():
            d = day.date() if hasattr(day, "date") else day
            o, h, l, c, v = (
                float(row["시가"]), float(row["고가"]),
                float(row["저가"]), float(row["종가"]),
                int(row["거래량"]),
            )
            # 각 거래일마다 390개 분봉 생성하여 bars 에 추가
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
    """일봉 OHLCV → 분봉 390개 합성 (브라운 운동 기반).

    [알고리즘]
      1. 드리프트 = (종가/시가 - 1) / 390  → 분봉이 평균적으로 이 방향으로 움직임
      2. 변동성 = (고가-저가)/시가 / sqrt(390) * 1.5  → 일봉 레인지를 분봉에 분산
      3. 390개 랜덤 수익률 생성 → 누적곱으로 가격 경로 생성
      4. day_low ~ day_high 로 클리핑 → 일봉 레인지 초과 방지
      5. 마지막 분봉 종가 = day_close 로 고정 → 일봉 종가 일치 보장
    """
    n = _MINUTES_PER_DAY
    # 분봉별 드리프트와 변동성
    drift = (day_close / day_open - 1.0) / n
    vol = abs(day_high - day_low) / day_open / np.sqrt(n) * 1.5
    increments = rng.normal(drift, vol, n)

    # 누적 수익률 → 가격 경로
    prices = day_open * np.cumprod(1 + increments)
    prices = np.clip(prices, day_low, day_high)
    prices[-1] = day_close  # 마지막 봉 종가를 일봉 종가에 강제 일치

    # 거래량 분산: 실제 KOSPI 패턴 모방 (시가·점심·마감 집중)
    vol_weights = _volume_weights(n, rng)
    volumes = (vol_weights * day_volume).astype(int)

    open_dt = market_open_dt(d)  # 당일 09:00:00 KST datetime
    bars: list[Bar] = []
    prev = day_open  # 각 분봉의 시가 = 직전 분봉 종가

    for i in range(n):
        ts = open_dt + timedelta(minutes=i)
        o = prev
        c = prices[i]
        # 고가/저가: 시가·종가 범위에 작은 노이즈 추가 (현실적 캔들 형태)
        h = max(o, c) * (1 + rng.uniform(0, vol * 0.5))
        lo = min(o, c) * (1 - rng.uniform(0, vol * 0.5))
        # 일봉 레인지 초과 방지
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
            is_complete=True,  # 합성 봉은 항상 완성 봉으로 표시
        ))
        prev = c  # 다음 봉 시가 = 현재 봉 종가

    return bars


def _volume_weights(n: int, rng: np.random.Generator) -> np.ndarray:
    """KOSPI 거래량 패턴 모방: 시가·점심·마감에 집중.

    실제 KOSPI 거래량은 장 초반(09:00~09:30)과 장 마감(15:00~15:30)에 급증하고,
    점심 시간대(12:00~12:30)에도 소폭 증가하는 U자형 패턴을 보인다.
    """
    w = rng.uniform(0.5, 1.5, n)  # 기본 균등 분포
    w[:30] *= 3.0        # 처음 30분(09:00~09:30): 3배 거래량 (시가 급등락)
    w[120:150] *= 1.5    # 120~150분(11:00~11:30): 1.5배 (점심 전 포지션 조정)
    w[360:] *= 2.5       # 360~390분(15:00~15:30): 2.5배 (마감 전 청산)
    return w / w.sum()   # 합이 1이 되도록 정규화 → day_volume * 각 가중치 = 분봉 거래량
