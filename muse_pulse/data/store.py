"""LocalParquetStore — DataStorePort 의 Phase 1 구현체.

[역할]
  분봉 데이터를 로컬 Parquet 파일로 저장/로드한다.
  pykrx 로 수집한 데이터를 캐싱하여 반복 실행 시 재수집을 방지한다.

[교체 계획]
  Phase 2 에서 TimescaleDB(또는 InfluxDB)로 교체 예정.
  DataStorePort 인터페이스(core/ports.py)를 그대로 유지하면
  이 파일만 교체해도 상위 레이어(HistoricalDataLoader)는 수정 불필요.

[파일 구조]
  muse_pulse/data_store/
    {ticker}/
      minute_bars.parquet   ← timestamp 인덱스, OHLCV 컬럼
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
        # base_dir 미지정 시 settings.data_dir = muse_pulse/data_store/ 사용
        self._base = base_dir or settings.data_dir

    def _path(self, ticker: str) -> Path:
        """종목별 디렉토리를 생성하고 Parquet 파일 경로를 반환."""
        p = self._base / ticker
        p.mkdir(parents=True, exist_ok=True)
        return p / "minute_bars.parquet"

    def save_bars(self, bars: list[Bar]) -> None:
        """Bar 리스트를 Parquet 에 저장 (기존 데이터와 병합, 중복 제거).

        중복 처리 전략: 동일 timestamp 가 있으면 새 데이터(keep="last")를 우선.
        이는 pykrx 재수집 시 최신 데이터로 덮어쓰는 것을 허용하기 위함.
        """
        if not bars:
            return
        ticker = bars[0].ticker

        # Bar dataclass → DataFrame 변환 (vars() 로 필드명 유지)
        new_df = pd.DataFrame([vars(b) for b in bars])
        new_df["timestamp"] = pd.to_datetime(new_df["timestamp"])
        # timestamp 를 인덱스로 설정하여 시계열 슬라이싱 효율화
        new_df = new_df.set_index("timestamp").sort_index()

        path = self._path(ticker)
        if path.exists():
            # 기존 Parquet + 신규 데이터 병합 후 중복 제거
            old_df = pd.read_parquet(path)
            combined = pd.concat([old_df, new_df])
            combined = combined[~combined.index.duplicated(keep="last")].sort_index()
            combined.to_parquet(path)
        else:
            new_df.to_parquet(path)

    def load_bars(self, ticker: str, start: datetime, end: datetime) -> list[Bar]:
        """지정 구간의 Bar 리스트를 Parquet 에서 읽어 반환.

        파일 없으면 빈 리스트 반환 → HistoricalDataLoader 가 수집을 트리거.
        timestamp 마스킹으로 불필요한 메모리 사용을 줄임.
        반환된 Bar 들은 모두 is_complete=True (저장 시점에 완성된 봉만 저장).
        """
        path = self._path(ticker)
        if not path.exists():
            return []

        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index)

        # 구간 필터링: start 이상 ~ end 이하
        mask = (df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))
        sub = df.loc[mask]

        # DataFrame 행 → Bar 객체 변환
        return [
            Bar(
                ticker=ticker,
                timestamp=row.name.to_pydatetime(),   # Index → Python datetime
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                is_complete=True,  # 캐시된 데이터는 항상 완성 봉
            )
            for _, row in sub.iterrows()
        ]

    def list_tickers(self) -> list[str]:
        """저장된 종목 코드 목록 반환 (data_store/ 하위 디렉토리 이름)."""
        return [p.name for p in self._base.iterdir() if p.is_dir()]
