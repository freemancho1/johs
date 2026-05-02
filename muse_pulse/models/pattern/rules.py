"""RuleBasedPatternEngine — 캔들스틱·차트 패턴 룰 기반 판정.

[7가지 패턴, 우선순위 순]
  단봉:   hammer (망치형), shooting_star (유성형)
  이중봉: bullish_engulfing (강세 장악형), bearish_engulfing (약세 장악형)
  삼봉:   morning_star (샛별형), evening_star (저녁별형)
  차트:   box_breakout (박스권 돌파)

[우선순위 정책]
  첫 번째 매칭에서 즉시 반환 (break-first).
  삼봉 패턴이 단봉 패턴보다 우선순위가 낮은 이유:
  현재 코드에서는 단봉이 먼저 검사되므로, 실제로는 단봉이 우선된다.
  이는 Phase 1 에서 의도적 선택 — 삼봉 패턴이 더 강력하지만 드물기 때문.

[교체 계획]
  Phase 2: CNN 기반 차트 이미지 인식으로 일부 대체.
  source 필드를 "RULE" → "CNN" 으로 바꾸면 상위 레이어 변경 없이 통합 가능.
"""
from __future__ import annotations

import time
from datetime import datetime

import numpy as np

from ...core.types import Bar, PatternInput, PatternSignal


class RuleBasedPatternEngine:
    def run(self, inp: PatternInput, bars: list[Bar]) -> PatternSignal:
        """패턴 감지 후 PatternSignal 반환. 지연시간 측정 포함."""
        t0 = time.perf_counter()
        direction, confidence, pattern_name = self._detect(inp, bars)
        latency_ms = (time.perf_counter() - t0) * 1000

        return PatternSignal(
            ticker=inp.ticker,
            timestamp=inp.bar_timestamp,
            direction=direction,
            confidence=confidence,
            pattern_name=pattern_name,
            source="RULE",    # Phase 1: 룰 기반
            latency_ms=latency_ms,
        )

    def _detect(
        self, inp: PatternInput, bars: list[Bar]
    ) -> tuple[str, float, str]:
        """우선순위 순서로 패턴을 검사하고 첫 번째 매칭을 반환.

        bars 는 원본 Bar 리스트 (절대 가격 사용: 비율 계산에 필요).
        inp.ohlcv_series 는 정규화된 값 (현재 이 메서드에서는 미사용, 향후 CNN 용).
        """
        if len(bars) < 5:
            return "HOLD", 0.0, "none"

        checks = [
            self._hammer,
            self._shooting_star,
            self._bullish_engulfing,
            self._bearish_engulfing,
            self._morning_star,
            self._evening_star,
            self._box_breakout,
        ]
        for fn in checks:
            direction, conf, name = fn(bars)
            if direction != "HOLD":
                return direction, conf, name

        return "HOLD", 0.0, "none"

    # ── 단봉 패턴 ──────────────────────────────────────────────────────────────

    def _hammer(self, bars: list[Bar]) -> tuple[str, float, str]:
        """망치형(Hammer) — 하락 추세 후 반전 신호.

        조건: 아래꼬리 >= 몸통*2  AND  윗꼬리 <= 몸통*0.3
        해석: 매도세가 강했으나 매수세가 강하게 반격 → 반등 기대.
        신뢰도 0.6: 단봉 패턴은 확인이 필요하므로 중간 수준.
        """
        b = bars[-1]
        body = abs(b.close - b.open)
        lower_shadow = min(b.open, b.close) - b.low
        upper_shadow = b.high - max(b.open, b.close)
        if body < 1e-8:  # 도지봉(몸통 거의 없음) 제외
            return "HOLD", 0.0, ""
        if lower_shadow >= body * 2 and upper_shadow <= body * 0.3:
            return "BUY", 0.6, "hammer"
        return "HOLD", 0.0, ""

    def _shooting_star(self, bars: list[Bar]) -> tuple[str, float, str]:
        """유성형(Shooting Star) — 상승 추세 후 반전 신호.

        조건: 윗꼬리 >= 몸통*2  AND  아래꼬리 <= 몸통*0.3
        해석: 매수세가 강했으나 매도세가 강하게 반격 → 하락 기대.
        """
        b = bars[-1]
        body = abs(b.close - b.open)
        upper_shadow = b.high - max(b.open, b.close)
        lower_shadow = min(b.open, b.close) - b.low
        if body < 1e-8:
            return "HOLD", 0.0, ""
        if upper_shadow >= body * 2 and lower_shadow <= body * 0.3:
            return "SELL", 0.6, "shooting_star"
        return "HOLD", 0.0, ""

    # ── 이중봉 패턴 ──────────────────────────────────────────────────────────

    def _bullish_engulfing(self, bars: list[Bar]) -> tuple[str, float, str]:
        """강세 장악형(Bullish Engulfing) — 강력한 반전 신호.

        조건:
          전봉: 음봉 (close < open)
          현봉: 양봉 (close > open)
          현봉 시가 < 전봉 종가  (갭 다운 시작 → 매도 압력 컸으나)
          현봉 종가 > 전봉 시가  (이전 몸통 전체를 포괄 → 강한 매수세)
        신뢰도 0.7: 이중봉 확인으로 단봉보다 신뢰도 높음.
        """
        if len(bars) < 2:
            return "HOLD", 0.0, ""
        prev, curr = bars[-2], bars[-1]
        if (
            prev.close < prev.open               # 전봉: 음봉
            and curr.close > curr.open            # 현봉: 양봉
            and curr.open < prev.close            # 갭 다운 시가
            and curr.close > prev.open            # 전봉 몸통 완전 포괄
        ):
            return "BUY", 0.7, "bullish_engulfing"
        return "HOLD", 0.0, ""

    def _bearish_engulfing(self, bars: list[Bar]) -> tuple[str, float, str]:
        """약세 장악형(Bearish Engulfing) — 상승 후 하락 반전 신호.

        조건: 전봉 양봉, 현봉 음봉이 전봉 몸통을 완전히 감쌈.
        """
        if len(bars) < 2:
            return "HOLD", 0.0, ""
        prev, curr = bars[-2], bars[-1]
        if (
            prev.close > prev.open               # 전봉: 양봉
            and curr.close < curr.open            # 현봉: 음봉
            and curr.open > prev.close            # 갭 업 시가
            and curr.close < prev.open            # 전봉 몸통 완전 포괄
        ):
            return "SELL", 0.7, "bearish_engulfing"
        return "HOLD", 0.0, ""

    # ── 삼봉 패턴 ──────────────────────────────────────────────────────────────

    def _morning_star(self, bars: list[Bar]) -> tuple[str, float, str]:
        """샛별형(Morning Star) — 하락 추세에서 반전하는 삼봉 패턴.

        조건:
          b1: 음봉 (하락 지속)
          b2: 도지/소형봉 (body2 < b1 body * 0.3) — 매수·매도 균형, 방향 탐색
          b3: 양봉이 b1 몸통의 중간 이상 회복 — 매수세 확인
        신뢰도 0.75: 3봉 확인으로 높은 신뢰도.
        """
        if len(bars) < 3:
            return "HOLD", 0.0, ""
        b1, b2, b3 = bars[-3], bars[-2], bars[-1]
        body2 = abs(b2.close - b2.open)
        body1 = abs(b1.close - b1.open)
        if (
            b1.close < b1.open                        # b1: 음봉
            and body2 < body1 * 0.3                   # b2: 도지 또는 소형봉
            and b3.close > b3.open                    # b3: 양봉
            and b3.close > (b1.open + b1.close) / 2  # b3 종가가 b1 몸통 중간 이상
        ):
            return "BUY", 0.75, "morning_star"
        return "HOLD", 0.0, ""

    def _evening_star(self, bars: list[Bar]) -> tuple[str, float, str]:
        """저녁별형(Evening Star) — 상승 추세에서 반전하는 삼봉 패턴.

        morning_star 의 반전 버전.
        b1 양봉 → b2 도지 → b3 음봉이 b1 몸통 중간 이하 하락.
        """
        if len(bars) < 3:
            return "HOLD", 0.0, ""
        b1, b2, b3 = bars[-3], bars[-2], bars[-1]
        body2 = abs(b2.close - b2.open)
        body1 = abs(b1.close - b1.open)
        if (
            b1.close > b1.open                        # b1: 양봉
            and body2 < body1 * 0.3                   # b2: 도지 또는 소형봉
            and b3.close < b3.open                    # b3: 음봉
            and b3.close < (b1.open + b1.close) / 2  # b3 종가가 b1 몸통 중간 이하
        ):
            return "SELL", 0.75, "evening_star"
        return "HOLD", 0.0, ""

    # ── 차트 패턴 ──────────────────────────────────────────────────────────────

    def _box_breakout(self, bars: list[Bar]) -> tuple[str, float, str]:
        """박스권 돌파(Box Breakout) — 횡보 구간 이탈 신호.

        [알고리즘]
          1. 직전 20봉(현재봉 제외)의 최고가 = 저항선(resistance)
          2. 직전 20봉의 최저가 = 지지선(support)
          3. 현재 봉 종가가 저항선 * 1.001 초과 → 상단 돌파 (BUY)
          4. 현재 봉 종가가 지지선 * 0.999 미만 → 하단 돌파 (SELL)
          0.1% 버퍼(1.001, 0.999): 저항선·지지선 바로 위 수준의 잡음을 걸러냄.

        신뢰도 0.65: 단봉보다 높지만 이중봉보다 낮은 중간 수준.
        """
        if len(bars) < 21:
            return "HOLD", 0.0, ""

        # 현재봉 제외 직전 20봉
        box = bars[-21:-1]
        highs = [b.high for b in box]
        lows = [b.low for b in box]
        resistance = max(highs)
        support = min(lows)
        curr = bars[-1]

        if curr.close > resistance * 1.001:
            return "BUY", 0.65, "box_breakout_up"
        if curr.close < support * 0.999:
            return "SELL", 0.65, "box_breakout_down"
        return "HOLD", 0.0, ""
