"""Phase 1 백테스트 실행 스크립트.

[실행 흐름]
  1. 커맨드라인 인자 파싱 (argparse)
  2. 데이터 로드 → LocalParquetStore 캐시 확인 → 없으면 pykrx 합성
  3. Walk-Forward 검증: 60일 학습 + 10일 테스트 슬라이딩 윈도우

사용법:
    cd muse_pulse
    python scripts/run_backtest.py [--ticker 005930] [--start 20230101] [--end 20231231]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

# ── 패키지 경로 등록 ──────────────────────────────────────────────────────────
# 이 스크립트는 muse_pulse/scripts/ 안에 있으므로
# 두 단계 위(johs/)를 sys.path 에 추가해야 "from muse_pulse..." import 가 가능하다.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ── 컴포넌트 임포트 ───────────────────────────────────────────────────────────
from muse_pulse.data.loader import HistoricalDataLoader   # pykrx/KIS → Bar 리스트
from muse_pulse.data.store import LocalParquetStore       # Parquet 캐시
from muse_pulse.backtest.walk_forward import WalkForwardValidator
from muse_pulse.config.settings import settings           # 전역 설정 싱글톤


def parse_args():
    p = argparse.ArgumentParser(description="MPS Phase 1 백테스트")
    # 종목 코드: KRX 6자리 문자열. 기본값은 삼성전자(005930)
    p.add_argument("--ticker", default="005930", help="종목 코드 (기본: 삼성전자)")
    # 기간 인자: YYYYMMDD 형식 문자열. date() 로 변환 후 loader.load() 에 전달
    p.add_argument("--start", default="20230101", help="시작일 YYYYMMDD")
    p.add_argument("--end", default="20231231", help="종료일 YYYYMMDD")
    # 초기 자본: PositionSizer 와 PerformanceEvaluator 의 기준점
    p.add_argument("--capital", type=float, default=10_000_000.0, help="초기 자본")
    return p.parse_args()


def main():
    args = parse_args()

    # 문자열 "20230101" → date(2023, 1, 1) 변환
    start = date(int(args.start[:4]), int(args.start[4:6]), int(args.start[6:]))
    end = date(int(args.end[:4]), int(args.end[4:6]), int(args.end[6:]))

    # ── 실행 요약 출력 ─────────────────────────────────────────────────────────
    # roundtrip_cost = commission*2 + tax + slippage*2 ≈ 0.41%
    # 신호 combined_score >= 0.55 가 이 비용을 이기는지 확인하는 것이 백테스트 목적
    print(f"\n{'='*60}")
    print(f"  MPS Phase 1 백테스트")
    print(f"  종목: {args.ticker}  |  기간: {start} ~ {end}")
    print(f"  초기 자본: {args.capital:,.0f}원")
    print(f"  보수적 왕복 비용: {settings.cost.roundtrip_cost:.2%}")
    print(f"{'='*60}\n")

    # ── 1단계: 데이터 로드 ─────────────────────────────────────────────────────
    # LocalParquetStore 캐시 → 없으면 pykrx 일봉으로 합성 분봉 생성
    # 반환값: list[Bar] — timestamp 순 정렬, is_complete=True
    print("▸ 데이터 로드 중...")
    store = LocalParquetStore()
    loader = HistoricalDataLoader(store)
    bars = loader.load(args.ticker, start, end)
    print(f"  총 {len(bars):,}봉 로드 완료\n")

    if not bars:
        print("데이터가 없습니다. pykrx 설치 및 네트워크 연결을 확인하세요.")
        return

    # ── 2단계: Walk-Forward 검증 ───────────────────────────────────────────────
    # 학습 60거래일 + 테스트 10거래일 슬라이딩 윈도우를 반복
    # 각 윈도우마다 독립 HistoricalSimulator 를 생성하여 PerformanceReport 반환
    # → 여러 구간의 평균 성과로 과적합 여부 판단
    print("▸ Walk-Forward 검증 실행 중...")
    validator = WalkForwardValidator(
        test_days=10,
        capital=args.capital,
    )
    reports = validator.run(bars)
    print(f"\n  Walk-Forward 결과 ({len(reports)}개 구간):")
    for i, r in enumerate(reports, 1):
        print(f"  [{i:02d}] {r}")

    print("\n백테스트 완료.")
    # 로그 파일 위치: logs/signals.jsonl, logs/orders.jsonl
    print(f"로그 위치: {settings.log_dir}")


if __name__ == "__main__":
    main()
