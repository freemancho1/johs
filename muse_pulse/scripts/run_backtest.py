"""Phase 1 백테스트 실행 스크립트.

사용법:
    cd muse_pulse
    python scripts/run_backtest.py [--ticker 005930] [--start 20230101] [--end 20231231]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

# 패키지 루트를 sys.path 에 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muse_pulse.data.loader import HistoricalDataLoader
from muse_pulse.data.store import LocalParquetStore
from muse_pulse.backtest.simulator import HistoricalSimulator
from muse_pulse.backtest.walk_forward import WalkForwardValidator, split_by_trading_day
from muse_pulse.config.settings import settings


def parse_args():
    p = argparse.ArgumentParser(description="MPS Phase 1 백테스트")
    p.add_argument("--ticker", default="005930", help="종목 코드 (기본: 삼성전자)")
    p.add_argument("--start", default="20230101", help="시작일 YYYYMMDD")
    p.add_argument("--end", default="20231231", help="종료일 YYYYMMDD")
    p.add_argument("--capital", type=float, default=10_000_000.0, help="초기 자본")
    p.add_argument("--walk-forward", action="store_true", help="Walk-Forward 검증 실행")
    return p.parse_args()


def main():
    args = parse_args()
    start = date(int(args.start[:4]), int(args.start[4:6]), int(args.start[6:]))
    end = date(int(args.end[:4]), int(args.end[4:6]), int(args.end[6:]))

    print(f"\n{'='*60}")
    print(f"  MPS Phase 1 백테스트")
    print(f"  종목: {args.ticker}  |  기간: {start} ~ {end}")
    print(f"  초기 자본: {args.capital:,.0f}원")
    print(f"  보수적 왕복 비용: {settings.cost.roundtrip_cost:.2%}")
    print(f"{'='*60}\n")

    # 1. 데이터 로드
    print("▸ 데이터 로드 중...")
    store = LocalParquetStore()
    loader = HistoricalDataLoader(store)
    bars = loader.load(args.ticker, start, end)
    print(f"  총 {len(bars):,}봉 로드 완료\n")

    if not bars:
        print("데이터가 없습니다. pykrx 설치 및 네트워크 연결을 확인하세요.")
        return

    if args.walk_forward:
        # 2a. Walk-Forward 검증
        print("▸ Walk-Forward 검증 실행 중...")
        validator = WalkForwardValidator(
            train_days=60,
            test_days=10,
            capital=args.capital,
        )
        reports = validator.run(bars)
        print(f"\n  Walk-Forward 결과 ({len(reports)}개 구간):")
        for i, r in enumerate(reports, 1):
            print(f"  [{i:02d}] {r}")
    else:
        # 2b. 단순 Train/Val/Test 분할
        print("▸ 70/15/15 시간순 분할...")
        train, val, test = split_by_trading_day(bars)
        print(f"  학습: {len(train):,}봉 | 검증: {len(val):,}봉 | 테스트: {len(test):,}봉\n")

        print("▸ 검증 구간 백테스트 실행...")
        sim_val = HistoricalSimulator(capital=args.capital)
        val_report = sim_val.run(train + val)   # 학습 버퍼 포함
        print(f"\n  [검증] {val_report}\n")

        print("▸ 테스트 구간 백테스트 실행...")
        sim_test = HistoricalSimulator(capital=args.capital)
        test_report = sim_test.run(train + val + test)
        print(f"\n  [테스트] {test_report}\n")

    print("백테스트 완료.")
    print(f"로그 위치: {settings.log_dir}")


if __name__ == "__main__":
    main()
