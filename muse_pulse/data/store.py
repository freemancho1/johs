"""LocalParquetStore — DataStorePort 의 Phase 1 구현체.
반드시 변경될 것: 시계열 DB (TimescaleDB / InfluxDB) 로 교체 예정.
교체 시 이 파일만 교체하고 DataStorePort 인터페이스는 유지한다.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from ..core.types import Bar
from ..config.settings import settings


class LocalParquetStore:
    """종목별 분봉 데이터를 Parquet 파일로 저장/로드."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = base_dir or settings.data_dir

    def _path(self, ticker: str) -> Path:
        p = self._base / ticker
        p.mkdir(parents=True, exist_ok=True)
        return p / "minute_bars.parquet"

    def save_bars(self, bars: list[Bar]) -> None:
        if not bars:
            return
        ticker = bars[0].ticker
        new_df = pd.DataFrame([vars(b) for b in bars])
        new_df["timestamp"] = pd.to_datetime(new_df["timestamp"])
        new_df = new_df.set_index("timestamp").sort_index()

        path = self._path(ticker)
        if path.exists():
            old_df = pd.read_parquet(path)
            combined = pd.concat([old_df, new_df])
            combined = combined[~combined.index.duplicated(keep="last")].sort_index()
            combined.to_parquet(path)
        else:
            new_df.to_parquet(path)

    def load_bars(self, ticker: str, start: datetime, end: datetime) -> list[Bar]:
        path = self._path(ticker)
        if not path.exists():
            return []
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index)
        mask = (df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))
        sub = df.loc[mask]
        return [
            Bar(
                ticker=ticker,
                timestamp=row.name.to_pydatetime(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                is_complete=True,
            )
            for _, row in sub.iterrows()
        ]

    def list_tickers(self) -> list[str]:
        return [p.name for p in self._base.iterdir() if p.is_dir()]
