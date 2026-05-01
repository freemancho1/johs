from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PhaseConfig:
    """단계별 종목 범위 설정."""
    tickers: list[str] = field(default_factory=lambda: ["005930"])  # 삼성전자
    lookback_minutes: int = 120        # 룩백 윈도우 (변경 가능)
    market_open: str = "09:00"
    market_close: str = "15:30"
    force_close_minutes_before: int = 15   # 마감 강제청산 기준


@dataclass
class TripleBarrierConfig:
    """Triple Barrier 라벨링 임계값 (변경 가능)."""
    take_profit: float = 0.005    # +0.5%
    stop_loss: float = 0.003      # 0.3% (절대값; 하락 시 적용)
    time_horizon: int = 60        # 분 단위


@dataclass
class CostConfig:
    """보수적 거래 비용 모델 (변경 불가 원칙)."""
    commission_rate: float = 0.00015   # 0.015% 편도
    tax_rate: float = 0.0018           # 매도 시 증권거래세 0.18%
    slippage_rate: float = 0.001       # 슬리피지 0.1% (보수적)

    @property
    def roundtrip_cost(self) -> float:
        """왕복 최소 비용 — 신호 임계값 설정 기준."""
        return self.commission_rate * 2 + self.tax_rate + self.slippage_rate


@dataclass
class LatencyConfig:
    """지연시간 관리 (초기엔 느슨하게, 검증 후 강화)."""
    max_inference_ms: float = 3000.0
    max_network_ms: float = 1000.0
    max_order_ms: float = 1000.0

    @property
    def max_total_ms(self) -> float:
        return self.max_inference_ms + self.max_network_ms + self.max_order_ms


@dataclass
class SignalConfig:
    """신호 합의 임계값."""
    min_combined_score: float = 0.55   # 이 이하 신호는 폐기
    latency_guard_enabled: bool = True


@dataclass
class RiskConfig:
    """리스크 관리 파라미터."""
    max_position_pct: float = 0.1      # 계좌 대비 최대 포지션 비율
    initial_capital: float = 10_000_000.0   # 초기 자본 (1천만 원)


@dataclass
class Settings:
    root_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    phase: PhaseConfig = field(default_factory=PhaseConfig)
    triple_barrier: TripleBarrierConfig = field(default_factory=TripleBarrierConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    latency: LatencyConfig = field(default_factory=LatencyConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

    @property
    def data_dir(self) -> Path:
        p = self.root_dir / "data_store"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def log_dir(self) -> Path:
        p = self.root_dir / "logs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def snapshot_dir(self) -> Path:
        p = self.root_dir / "snapshots"
        p.mkdir(parents=True, exist_ok=True)
        return p

    # KIS API 자격증명 — 환경변수에서 읽음
    @property
    def kis_app_key(self) -> str:
        return os.environ.get("KIS_APP_KEY", "")

    @property
    def kis_app_secret(self) -> str:
        return os.environ.get("KIS_APP_SECRET", "")

    @property
    def kis_account_no(self) -> str:
        return os.environ.get("KIS_ACCOUNT_NO", "")

    @property
    def kis_mock(self) -> bool:
        """True 이면 모의투자 환경 (기본값)."""
        return os.environ.get("KIS_MOCK", "true").lower() == "true"


# 전역 싱글톤
settings = Settings()
