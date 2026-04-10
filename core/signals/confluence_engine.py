"""
Signal confluence engine.
Aggregates TA score, sentiment score, momentum, and macro into one signal score.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConfluenceScore:
    instrument:     str
    direction:      str           # BUY / SELL / NEUTRAL
    total_score:    float         # 0.0 – 1.0 (≥0.60 = tradeable)
    ta_score:       float
    sentiment_score: float
    momentum_score: float
    macro_score:    float
    atr:            float         # for SL/TP calculation
    entry_price:    float
    stop_loss:      float
    take_profit:    float
    reasons:        list[str] = field(default_factory=list)
    tradeable:      bool = False


# Weights — must sum to 1.0
WEIGHTS = {
    "ta":        0.40,
    "sentiment": 0.35,
    "momentum":  0.15,
    "macro":     0.10,
}

# Minimum score to generate a signal
THRESHOLD_FULL = 0.75   # full lot size
THRESHOLD_HALF = 0.60   # half lot size


class ConfluenceEngine:
    """
    Combines all signal inputs into a single directional score.
    Called by the Claude agent to validate whether a signal meets the bar.
    """

    def compute(
        self,
        instrument:      str,
        ta_analysis:     dict,
        sentiment_data:  dict,
        price_data:      dict,
        macro_data:      dict | None = None,
    ) -> ConfluenceScore:

        entry_price = price_data.get("ask", 0.0)
        atr = self._extract_atr(ta_analysis)

        # ── 1. Technical score ─────────────────────────────────────────────────
        ta_score, ta_direction, ta_reasons = self._score_ta(ta_analysis)

        # ── 2. Sentiment score ─────────────────────────────────────────────────
        sent_raw   = sentiment_data.get("score", 0.0)          # -1.0 to +1.0
        sent_norm  = sentiment_data.get("normalised", 0.5)      # 0.0 to 1.0
        sent_bias  = sentiment_data.get("bias", "neutral")
        sent_count = sentiment_data.get("article_count", 0)

        # Low article count → reduce confidence
        coverage_factor = min(sent_count / 10, 1.0)
        sentiment_score = sent_norm * coverage_factor
        sent_direction  = "BUY" if sent_raw > 0.1 else "SELL" if sent_raw < -0.1 else "NEUTRAL"

        # ── 3. Momentum score ─────────────────────────────────────────────────
        momentum_score, mom_direction = self._score_momentum(ta_analysis)

        # ── 4. Macro score ────────────────────────────────────────────────────
        macro_score = self._score_macro(macro_data or {})

        # ── Weighted composite ────────────────────────────────────────────────
        total = (
            ta_score        * WEIGHTS["ta"] +
            sentiment_score * WEIGHTS["sentiment"] +
            momentum_score  * WEIGHTS["momentum"] +
            macro_score     * WEIGHTS["macro"]
        )

        # ── Determine direction ───────────────────────────────────────────────
        votes = {
            "BUY":  (1 if ta_direction == "BUY"     else 0) * WEIGHTS["ta"] +
                    (1 if sent_direction == "BUY"    else 0) * WEIGHTS["sentiment"] +
                    (1 if mom_direction  == "BUY"    else 0) * WEIGHTS["momentum"],
            "SELL": (1 if ta_direction == "SELL"     else 0) * WEIGHTS["ta"] +
                    (1 if sent_direction == "SELL"   else 0) * WEIGHTS["sentiment"] +
                    (1 if mom_direction  == "SELL"   else 0) * WEIGHTS["momentum"],
        }

        if votes["BUY"] > votes["SELL"] + 0.10:
            direction = "BUY"
        elif votes["SELL"] > votes["BUY"] + 0.10:
            direction = "SELL"
        else:
            direction = "NEUTRAL"
            total = min(total, 0.55)   # kill ambiguous signals

        # ── SL / TP ───────────────────────────────────────────────────────────
        sl, tp = self._compute_sl_tp(instrument, direction, entry_price, atr)

        # ── Build reasons ─────────────────────────────────────────────────────
        reasons = ta_reasons + [
            f"Sentiment: {sent_bias} ({sent_raw:+.2f}, {sent_count} articles)",
            f"Momentum score: {momentum_score:.2f}",
        ]

        return ConfluenceScore(
            instrument      = instrument,
            direction       = direction,
            total_score     = round(total, 4),
            ta_score        = round(ta_score, 4),
            sentiment_score = round(sentiment_score, 4),
            momentum_score  = round(momentum_score, 4),
            macro_score     = round(macro_score, 4),
            atr             = atr,
            entry_price     = entry_price,
            stop_loss       = sl,
            take_profit     = tp,
            reasons         = reasons,
            tradeable       = total >= THRESHOLD_HALF and direction != "NEUTRAL",
        )

    # ─── Private scorers ──────────────────────────────────────────────────────

    def _score_ta(self, ta: dict) -> tuple[float, str, list[str]]:
        """Score TA across all timeframes."""
        overall_bias  = ta.get("overall_bias", "neutral")
        ta_score_raw  = ta.get("ta_score", 0.5)
        reasons: list[str] = [f"TA overall: {overall_bias} ({ta_score_raw:.2f})"]

        h4 = ta.get("timeframes", {}).get("H4", {})
        d1 = ta.get("timeframes", {}).get("D1", {})

        # Bonus for pattern matches
        patterns = h4.get("patterns", []) + d1.get("patterns", [])
        if patterns:
            reasons.append(f"Patterns: {', '.join(patterns)}")
            ta_score_raw = min(ta_score_raw + 0.05 * len(patterns), 1.0)

        # MACD confirmation on H4
        h4_macd = h4.get("macd", {})
        if h4_macd.get("bullish_cross"):
            reasons.append("H4 MACD bullish crossover")
            ta_score_raw = min(ta_score_raw + 0.03, 1.0)
        elif h4_macd.get("bearish_cross"):
            reasons.append("H4 MACD bearish crossover")

        direction = "BUY" if overall_bias == "bullish" else "SELL" if overall_bias == "bearish" else "NEUTRAL"
        return ta_score_raw, direction, reasons

    def _score_momentum(self, ta: dict) -> tuple[float, str]:
        """Score momentum from RSI and recent price action."""
        h1 = ta.get("timeframes", {}).get("H1", {})
        rsi_data = h1.get("rsi", {})
        rsi_val  = rsi_data.get("value", 50.0) or 50.0
        rsi_mom  = rsi_data.get("momentum", 0.0) or 0.0

        # RSI in bullish range (45–65) with positive momentum
        if 45 <= rsi_val <= 65 and rsi_mom > 2:
            return 0.72, "BUY"
        if 35 <= rsi_val <= 55 and rsi_mom < -2:
            return 0.72, "SELL"
        if rsi_val > 65:
            return 0.60, "BUY" if rsi_mom > 0 else "NEUTRAL"
        if rsi_val < 35:
            return 0.60, "SELL" if rsi_mom < 0 else "NEUTRAL"
        return 0.50, "NEUTRAL"

    def _score_macro(self, macro: dict) -> float:
        """Score macro environment (interest rate differential, growth trend)."""
        if not macro:
            return 0.50   # neutral when no data
        score = macro.get("score", 0.50)
        return max(0.0, min(1.0, score))

    def _extract_atr(self, ta: dict) -> float:
        """Extract ATR from H4 timeframe (best for SL sizing)."""
        h4 = ta.get("timeframes", {}).get("H4", {})
        return float(h4.get("atr") or 0.001)

    def _compute_sl_tp(
        self, instrument: str, direction: str, entry: float, atr: float
    ) -> tuple[float, float]:
        sl_mult = 1.5
        tp_mult = 2.5
        if direction == "BUY":
            sl = entry - atr * sl_mult
            tp = entry + atr * tp_mult
        elif direction == "SELL":
            sl = entry + atr * sl_mult
            tp = entry - atr * tp_mult
        else:
            sl = tp = entry
        return round(sl, 5), round(tp, 5)
