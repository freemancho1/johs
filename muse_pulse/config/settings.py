"""전역 설정 싱글톤 — 모든 컴포넌트가 이 파일에서 파라미터를 읽는다.

[설계 원칙]
  - 파라미터를 코드 곳곳에 하드코딩하지 않는다. 변경할 때 이 파일 하나만 수정.
  - 각 dataclass 는 독립적 관심사(비용, 지연시간, 신호, 리스크)를 담당한다.
  - Settings 인스턴스는 모듈 수준에서 한 번만 생성 (싱글톤 패턴).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PhaseConfig:
    """단계별 종목 범위 및 시장 시간 설정.

    Phase 1 은 삼성전자 단일 종목으로 시작한다.
    확장 시 tickers 리스트에 종목 코드를 추가하면 된다.
    """
    tickers: list[str] = field(default_factory=lambda: ["005930"])  # 삼성전자
    # 롤백 윈도우: 신호 생성 전 반드시 확보해야 할 과거 봉 수
    # RSI(14), MACD(26), BB(20), ATR(14) 중 가장 긴 게 26봉이므로 120이면 충분하나
    # 롤링 Z-score 정규화를 위해 더 긴 120 사용
    lookback_minutes: int = 120
    market_open: str = "09:00"
    market_close: str = "15:30"
    # 마감 15분 전(15:15) 에 모든 포지션 강제청산 → 오버나잇 갭 리스크 원천 차단
    force_close_minutes_before: int = 15


@dataclass
class TripleBarrierConfig:
    """Triple Barrier 라벨링 임계값.

    백테스트 기준과 실거래 기준이 동일해야 한다.
    take_profit  : 진입가 기준 +0.5% 도달 시 익절
    stop_loss    : 진입가 기준 -0.3% 도달 시 손절 (비대칭 → 손실 제한 우선)
    time_horizon : 60분 안에 TP/SL 미도달 시 시간 만료로 청산
    """
    take_profit: float = 0.005    # +0.5%
    stop_loss: float = 0.003      # 0.3% (절대값; 하락 시 적용)
    time_horizon: int = 60        # 분 단위


@dataclass
class CostConfig:
    """보수적 거래 비용 모델.

    실제 수익에 비용을 과소평가하면 백테스트가 낙관적이 된다.
    슬리피지 0.1% 는 KRX 시장가 주문 기준 현실적 상한선.

    왕복 비용(roundtrip_cost) ≈ 0.25% → 이것이 진입 신호의 최소 기대수익 기준.
    combined_score >= 0.55 임계값도 이 비용을 커버할 수 있는 신뢰도에서 도출됨.
    """
    commission_rate: float = 0.00015   # 0.015% 편도 (증권사 할인 기준)
    tax_rate: float = 0.0018           # 매도 시 증권거래세 0.18%
    slippage_rate: float = 0.001       # 슬리피지 0.1% (보수적 추정)

    @property
    def roundtrip_cost(self) -> float:
        """왕복 최소 비용.
        매수 비용(commission + slippage) + 매도 비용(commission + tax + slippage)
        = 0.015%*2 + 0.18% + 0.1%*2 ≈ 0.413%
        신호 임계값 설정의 하한선으로 사용.
        """
        return self.commission_rate * 2 + self.tax_rate + self.slippage_rate


@dataclass
class LatencyConfig:
    """지연시간 관리.

    단타 전략은 신호 → 체결까지의 지연이 수익에 직결된다.
    Phase 1 은 느슨하게 시작 (총 5초), 이후 실측 후 강화.

    max_inference_ms : 피처 추출 + 두 모델 추론 합산
    max_network_ms   : KIS API 왕복 지연 (미래 실거래 시)
    max_order_ms     : 주문 제출 → 체결 확인까지
    """
    max_inference_ms: float = 3000.0
    max_network_ms: float = 1000.0
    max_order_ms: float = 1000.0

    @property
    def max_total_ms(self) -> float:
        """합산 최대 허용 지연시간 = 5000ms."""
        return self.max_inference_ms + self.max_network_ms + self.max_order_ms


@dataclass
class SignalConfig:
    """신호 합의 임계값.

    combined_score = num_conf * 0.5 + pat_conf * 0.5
    min_combined_score = 0.55: 두 트랙이 모두 약한 신호(0.5+0.6)/2=0.55 이상
    이 값보다 낮은 신호는 SignalFilter 에서 폐기된다.
    """
    min_combined_score: float = 0.55
    latency_guard_enabled: bool = True


@dataclass
class RiskConfig:
    """리스크 관리 파라미터.

    max_position_pct = 0.1 → 계좌 잔액의 10% 이상 한 종목에 집중하지 않는다.
    Phase 1 단일 종목이므로 이 값이 사실상 전체 포지션 크기를 결정한다.
    """
    max_position_pct: float = 0.1      # 계좌 대비 최대 포지션 비율 10%
    initial_capital: float = 10_000_000.0   # 초기 자본 1천만 원


@dataclass
class Settings:
    """전역 설정 컨테이너.

    root_dir 는 muse_pulse/ 패키지 루트 디렉토리를 가리킨다.
    모든 디렉토리 프로퍼티는 없으면 자동으로 생성된다(mkdir parents).
    """
    # __file__ 은 muse_pulse/config/settings.py → .parent = config/ → .parent = muse_pulse/
    root_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    phase: PhaseConfig = field(default_factory=PhaseConfig)
    triple_barrier: TripleBarrierConfig = field(default_factory=TripleBarrierConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    latency: LatencyConfig = field(default_factory=LatencyConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

    @property
    def data_dir(self) -> Path:
        """분봉 Parquet 파일 저장 위치: muse_pulse/data_store/"""
        p = self.root_dir / "data_store"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def log_dir(self) -> Path:
        """JSONL 로그 저장 위치: muse_pulse/logs/"""
        p = self.root_dir / "logs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def snapshot_dir(self) -> Path:
        """패턴 차트 스냅샷 PNG 저장 위치: muse_pulse/snapshots/"""
        p = self.root_dir / "snapshots"
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ── KIS API 자격증명 ────────────────────────────────────────────────────
    # 환경변수에서 읽는 이유: 소스 코드에 비밀키를 절대 하드코딩하지 않기 위함.
    # .env 파일 + python-dotenv 를 쓰거나, 셸에서 export KIS_APP_KEY=... 로 설정.
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
        """True 이면 KIS 모의투자 환경 사용 (기본값 True — 실수로 실거래 진입 방지)."""
        return os.environ.get("KIS_MOCK", "true").lower() == "true"


# ── 전역 싱글톤 ──────────────────────────────────────────────────────────────
# 모든 컴포넌트가 "from muse_pulse.config.settings import settings" 로 이 객체를 공유.
# 테스트에서 settings.risk.initial_capital = 5_000_000 처럼 직접 변경 가능.
settings = Settings()
