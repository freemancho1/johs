"""ChartSnapshotSaver — 패턴 신호 발생 시점 차트 이미지 저장."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..config.settings import settings
from ..core.types import Bar


class ChartSnapshotSaver:
    def __init__(self, snapshot_dir: Path | None = None) -> None:
        self._dir = snapshot_dir or settings.snapshot_dir

    def save(
        self,
        ticker: str,
        timestamp: datetime,
        bars: list[Bar],
        pattern_name: str = "",
    ) -> Path:
        try:
            import mplfinance as mpf
            import pandas as pd
        except ImportError:
            return Path()

        df = pd.DataFrame({
            "Open": [b.open for b in bars],
            "High": [b.high for b in bars],
            "Low": [b.low for b in bars],
            "Close": [b.close for b in bars],
            "Volume": [b.volume for b in bars],
        }, index=pd.DatetimeIndex([b.timestamp for b in bars]))

        ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
        fname = f"{ticker}_{ts_str}_{pattern_name}.png"
        out = self._dir / fname

        mpf.plot(
            df,
            type="candle",
            volume=True,
            title=f"{ticker} {ts_str} [{pattern_name}]",
            savefig=str(out),
            style="charles",
        )
        return out
