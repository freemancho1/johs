"""RuleBasedPatternEngine — 캔들스틱·차트 패턴 룰 기반 판정.

'반드시 변경될 것': 학습 기반 패턴 인식 비중 증가 예정.
"""
from __future__ import annotations

import time
from datetime import datetime

import numpy as np

from ...core.types import Bar, PatternInput, PatternSignal


class RuleBasedPatternEngine:
    def run(self, inp: PatternInput, bars: list[Bar]) -> PatternSignal:
        t0 = time.perf_counter()
        direction, confidence, pattern_name = self._detect(inp, bars)
        latency_ms = (time.perf_counter() - t0) * 1000
        return PatternSignal(
            ticker=inp.ticker,
            timestamp=inp.bar_timestamp,
            direction=direction,
            confidence=confidence,
            pattern_name=pattern_name,
            source="RULE",
            latency_ms=latency_ms,
        )

    def _detect(
        self, inp: PatternInput, bars: list[Bar]
    ) -> tuple[str, float, str]:
        """우선순위 순서로 패턴을 검사하고 첫 번째 매칭을 반환."""
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

    # ── 단봉 패턴 ──────────────────────────────────────────────────────────

    def _hammer(self, bars: list[Bar]) -> tuple[str, float, str]:
        b = bars[-1]
        body = abs(b.close - b.open)
        lower_shadow = min(b.open, b.close) - b.low
        upper_shadow = b.high - max(b.open, b.close)
        if body < 1e-8:
            return "HOLD", 0.0, ""
        if lower_shadow >= body * 2 and upper_shadow <= body * 0.3:
            return "BUY", 0.6, "hammer"
        return "HOLD", 0.0, ""

    def _shooting_star(self, bars: list[Bar]) -> tuple[str, float, str]:
        b = bars[-1]
        body = abs(b.close - b.open)
        upper_shadow = b.high - max(b.open, b.close)
        lower_shadow = min(b.open, b.close) - b.low
        if body < 1e-8:
            return "HOLD", 0.0, ""
        if upper_shadow >= body * 2 and lower_shadow <= body * 0.3:
            return "SELL", 0.6, "shooting_star"
        return "HOLD", 0.0, ""

    # ── 이중봉 패턴 ────────────────────────────────────────────────────────

    def _bullish_engulfing(self, bars: list[Bar]) -> tuple[str, float, str]:
        if len(bars) < 2:
            return "HOLD", 0.0, ""
        prev, curr = bars[-2], bars[-1]
        if (
            prev.close < prev.open               # 전봉 음봉
            and curr.close > curr.open            # 현봉 양봉
            and curr.open < prev.close            # 갭 다운 시가
            and curr.close > prev.open            # 이전 몸통 완전 포괄
        ):
            return "BUY", 0.7, "bullish_engulfing"
        return "HOLD", 0.0, ""

    def _bearish_engulfing(self, bars: list[Bar]) -> tuple[str, float, str]:
        if len(bars) < 2:
            return "HOLD", 0.0, ""
        prev, curr = bars[-2], bars[-1]
        if (
            prev.close > prev.open
            and curr.close < curr.open
            and curr.open > prev.close
            and curr.close < prev.open
        ):
            return "SELL", 0.7, "bearish_engulfing"
        return "HOLD", 0.0, ""

    # ── 삼봉 패턴 ──────────────────────────────────────────────────────────

    def _morning_star(self, bars: list[Bar]) -> tuple[str, float, str]:
        if len(bars) < 3:
            return "HOLD", 0.0, ""
        b1, b2, b3 = bars[-3], bars[-2], bars[-1]
        body2 = abs(b2.close - b2.open)
        body1 = abs(b1.close - b1.open)
        if (
            b1.close < b1.open                       # 첫봉 음봉
            and body2 < body1 * 0.3                  # 도지/소형봉
            and b3.close > b3.open                   # 셋봉 양봉
            and b3.close > (b1.open + b1.close) / 2  # 첫봉 중간 이상 회복
        ):
            return "BUY", 0.75, "morning_star"
        return "HOLD", 0.0, ""

    def _evening_star(self, bars: list[Bar]) -> tuple[str, float, str]:
        if len(bars) < 3:
            return "HOLD", 0.0, ""
        b1, b2, b3 = bars[-3], bars[-2], bars[-1]
        body2 = abs(b2.close - b2.open)
        body1 = abs(b1.close - b1.open)
        if (
            b1.close > b1.open
            and body2 < body1 * 0.3
            and b3.close < b3.open
            and b3.close < (b1.open + b1.close) / 2
        ):
            return "SELL", 0.75, "evening_star"
        return "HOLD", 0.0, ""

    # ── 차트 패턴 ──────────────────────────────────────────────────────────

    def _box_breakout(self, bars: list[Bar]) -> tuple[str, float, str]:
        """최근 20봉 박스권 상단/하단 돌파."""
        if len(bars) < 21:
            return "HOLD", 0.0, ""
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
