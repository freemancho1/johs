from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
_MARKET_OPEN = time(9, 0)
_MARKET_CLOSE = time(15, 30)


def is_trading_day(dt: date) -> bool:
    """주말 제외. 공휴일은 pykrx 로 확인하지 않고 간단히 주말만 처리 (Phase 1 충분)."""
    return dt.weekday() < 5


def is_trading_time(dt: datetime) -> bool:
    """정규장 시간(09:00~15:30) 여부."""
    if not is_trading_day(dt.date()):
        return False
    t = dt.time()
    return _MARKET_OPEN <= t < _MARKET_CLOSE


def market_open_dt(d: date) -> datetime:
    return datetime.combine(d, _MARKET_OPEN, tzinfo=KST)


def market_close_dt(d: date) -> datetime:
    return datetime.combine(d, _MARKET_CLOSE, tzinfo=KST)


def force_close_dt(d: date, minutes_before: int = 15) -> datetime:
    """강제청산 기준 시각 — 마감 N분 전."""
    return market_close_dt(d) - timedelta(minutes=minutes_before)


def trading_days(start: date, end: date) -> list[date]:
    """start~end 사이 거래일 목록 (양 끝 포함)."""
    result = []
    cur = start
    while cur <= end:
        if is_trading_day(cur):
            result.append(cur)
        cur += timedelta(days=1)
    return result


def prev_trading_day(d: date) -> date:
    cur = d - timedelta(days=1)
    while not is_trading_day(cur):
        cur -= timedelta(days=1)
    return cur
