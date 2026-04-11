"""
Edge Filter — The A+ Setup Gate.

This is the core of the platform's edge. Before any trade fires, 8 conditions
are evaluated. A trade only passes if it scores 6/8 or higher.

Why 8 conditions, not just a score?
  A 0.70 composite score could be achieved by three mediocre factors all
  agreeing. The edge filter requires INDEPENDENT confirmation across different
  data domains — technical, institutional, macro, timing, and risk.

The 8 Conditions:
  1. REGIME      — Market is trending OR ranging (not volatile, not exhausted)
  2. TECHNICAL   — TA score ≥ 0.62 (EMA aligned, RSI not extreme, MACD confirmed)
  3. SENTIMENT   — Sentiment aligned with trade direction (score in correct half)
  4. INSTITUTIONAL — COT + order book not contradicting the trade
  5. MACRO       — Rate differential and yield curve support the direction
  6. SESSION     — Entry is during liquid session (not Sunday, not Asia dead zone for majors)
  7. SPREAD      — Current spread ≤ 1.5× normal (no news spike)
  8. RISK        — Account has headroom: daily DD < 2.5% AND position count < 7

Scoring:
  8/8 → A++ setup  → full size, 3:1 RR
  7/8 → A+ setup   → full size, 2.5:1 RR
  6/8 → A  setup   → half size, 2:1 RR minimum
  5/8 or lower → NO TRADE

Additional edge layers:
  INSTITUTIONAL DIVERGENCE PLAY:
    - COT hedge funds NET SHORT + retail > 65% long → strong SELL signal (and vice versa)
    - Automatically upgrades the pass threshold by 1 (5/8 becomes acceptable)
    - This is the most statistically reliable setup we have

  FRESH BREAKOUT BONUS:
    - Regime = BREAKOUT + technical confirms direction → auto A+

  NEWS AFTERMATH PLAY:
    - High-impact news event occurred < 30 min ago + price has retraced 50-61.8%
    → Specific entry logic for news aftermath reversions
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple
from loguru import logger


class EdgeCheckResult(NamedTuple):
    passes:         bool
    score:          int          # 0–8 conditions met
    grade:          str          # A++, A+, A, FAIL
    conditions:     dict         # each condition: True/False
    recommended_size: float      # fraction of max size (0.0–1.0)
    recommended_rr:   float      # minimum risk:reward ratio
    special_setup:    str | None  # INSTITUTIONAL_DIVERGENCE / BREAKOUT / NEWS_AFTERMATH / None
    notes:          list[str]


# Normal spread baselines in pips
NORMAL_SPREAD_PIPS: dict[str, float] = {
    "EURUSD": 0.5, "GBPUSD": 0.7, "USDJPY": 0.5,
    "AUDUSD": 0.7, "USDCAD": 0.8, "NZDUSD": 0.9,
    "USDCHF": 0.8, "EURJPY": 0.8, "GBPJPY": 1.2,
    "XAUUSD": 15,  "XAGUSD": 50,  "USOIL":  3.0,
    "UKOIL":  3.0, "NATGAS": 5.0,
}


class EdgeFilter:
    """Evaluates whether a trading setup has sufficient statistical edge."""

    def evaluate(
        self,
        instrument:   str,
        direction:    str,                # BUY or SELL
        ta_score:     float,              # 0.0–1.0
        sentiment:    dict,               # from FinBERT
        order_flow:   dict,               # from COT + order book
        macro:        dict,               # from FRED
        regime:       dict,               # from RegimeDetector
        account:      dict,               # equity, daily_drawdown_pct, open_positions
        spread_pips:  float | None = None,
        news_event_minutes_ago: int | None = None,
    ) -> EdgeCheckResult:
        """Run all 8 conditions and return the result."""

        conditions: dict[str, bool] = {}
        notes: list[str] = []
        special_setup: str | None = None

        # ── Condition 1: Regime ───────────────────────────────────────────────
        r = regime.get("regime", "RANGING")
        regime_ok = r in ("TRENDING_BULLISH", "TRENDING_BEARISH", "RANGING", "BREAKOUT")
        # Must also match direction for trending regimes
        if r == "TRENDING_BULLISH" and direction == "SELL":
            regime_ok = False
            notes.append("Shorting into a bullish trend — high risk")
        if r == "TRENDING_BEARISH" and direction == "BUY":
            regime_ok = False
            notes.append("Buying into a bearish trend — high risk")
        if r in ("VOLATILE", "EXHAUSTED"):
            regime_ok = False
            notes.append(f"Regime {r} — not tradeable")

        conditions["regime"] = regime_ok
        if regime_ok:
            notes.append(f"Regime: {r} ✓")

        # Breakout bonus
        if r == "BREAKOUT":
            special_setup = "BREAKOUT"
            notes.append("BREAKOUT regime — auto A+ upgrade eligible")

        # ── Condition 2: Technical ────────────────────────────────────────────
        ta_ok = ta_score >= 0.62
        conditions["technical"] = ta_ok
        notes.append(f"TA score: {ta_score:.2f} {'✓' if ta_ok else '✗ (need ≥0.62)'}")

        # ── Condition 3: Sentiment ────────────────────────────────────────────
        sentiment_score = sentiment.get("normalised_score", 0.5)
        dominant_bias   = sentiment.get("dominant_bias", "neutral")
        sent_ok = (
            (direction == "BUY"  and sentiment_score > 0.52) or
            (direction == "SELL" and sentiment_score < 0.48)
        )
        conditions["sentiment"] = sent_ok
        notes.append(
            f"Sentiment: {dominant_bias} ({sentiment_score:.2f}) "
            f"{'✓' if sent_ok else '✗ (not aligned)'}"
        )

        # ── Condition 4: Institutional (COT + Order Book) ─────────────────────
        combined = order_flow.get("combined_signal", {})
        ib_signal   = combined.get("signal", "NEUTRAL")
        retail_long = combined.get("retail_long_pct", 50)
        noncomm_pct = combined.get("noncomm_net_pct", 0)

        inst_ok = (
            (direction == "BUY"  and ib_signal in ("STRONG_BUY", "MODERATE_BUY", "NEUTRAL")) or
            (direction == "SELL" and ib_signal in ("STRONG_SELL", "MODERATE_SELL", "NEUTRAL"))
        )

        # Hard block: if institutions are strongly opposed, override
        if direction == "BUY"  and ib_signal == "STRONG_SELL":
            inst_ok = False
        if direction == "SELL" and ib_signal == "STRONG_BUY":
            inst_ok = False

        conditions["institutional"] = inst_ok

        # Institutional Divergence Play detection
        if (
            (direction == "SELL" and noncomm_pct > 15  and retail_long > 65) or
            (direction == "BUY"  and noncomm_pct < -15 and retail_long < 35)
        ):
            special_setup = "INSTITUTIONAL_DIVERGENCE"
            notes.append("⚡ INSTITUTIONAL DIVERGENCE: hedge funds and retail on opposite sides — high-probability setup")

        notes.append(
            f"Order flow: {ib_signal} | retail {retail_long:.0f}% long | "
            f"hedge funds {noncomm_pct:+.1f}% OI {'✓' if inst_ok else '✗'}"
        )

        # ── Condition 5: Macro ────────────────────────────────────────────────
        usd_bias       = macro.get("usd_bias", "NEUTRAL")
        yield_signal   = macro.get("yield_curve_signal", "NORMAL")
        rate_diffs     = macro.get("rate_differentials", {})
        rate_diff      = rate_diffs.get(instrument, 0)

        macro_ok = True
        macro_notes = []

        # Inverted yield curve → avoid risk assets, favour safe havens
        if yield_signal == "INVERTED":
            if instrument in ("USOIL", "UKOIL", "AUDUSD", "NZDUSD") and direction == "BUY":
                macro_ok = False
                macro_notes.append("Inverted yield curve → avoid risk-on longs")

        # Rate differential for FX pairs
        if instrument in rate_diffs:
            if direction == "BUY"  and rate_diff < -0.5:
                macro_ok = False
                macro_notes.append(f"Rate differential {rate_diff:.2f}% against BUY direction")
            elif direction == "SELL" and rate_diff > 0.5:
                macro_ok = False
                macro_notes.append(f"Rate differential {rate_diff:.2f}% against SELL direction")

        conditions["macro"] = macro_ok
        if macro_notes:
            notes.extend(macro_notes)
        else:
            notes.append(f"Macro: yield={yield_signal}, USD={usd_bias}, rate_diff={rate_diff:+.2f} ✓")

        # ── Condition 6: Session ──────────────────────────────────────────────
        hour = datetime.now(timezone.utc).hour
        day  = datetime.now(timezone.utc).weekday()   # 0=Mon, 6=Sun

        # No trading: Sunday after 21:00 or before Monday 00:00
        is_dead_zone = (day == 6 and hour >= 21) or (day == 6 and hour < 21 and hour >= 0)

        # Active sessions for each instrument type
        is_forex     = instrument not in ("XAUUSD", "XAGUSD", "USOIL", "UKOIL", "NATGAS")
        in_london_ny = (7 <= hour < 21)   # London + NY combined
        in_ny_only   = (12 <= hour < 21)  # commodities prefer NY

        if is_dead_zone:
            session_ok = False
            notes.append("Session: Sunday dead zone ✗")
        elif is_forex:
            session_ok = in_london_ny
            notes.append(f"Session: {'London/NY ✓' if session_ok else 'Asia/dead zone ✗'}")
        else:
            session_ok = in_ny_only or (7 <= hour < 12)   # London open also ok for gold
            notes.append(f"Session: {'active ✓' if session_ok else 'low liquidity ✗'}")

        conditions["session"] = session_ok

        # ── Condition 7: Spread ───────────────────────────────────────────────
        if spread_pips is not None:
            normal_spread  = NORMAL_SPREAD_PIPS.get(instrument, 2.0)
            spread_ok      = spread_pips <= normal_spread * 1.5
            conditions["spread"] = spread_ok
            notes.append(
                f"Spread: {spread_pips:.1f} pips "
                f"({'✓' if spread_ok else f'✗ (>{normal_spread * 1.5:.1f} normal max)'})"
            )
        else:
            conditions["spread"] = True   # assume OK if we can't check
            notes.append("Spread: not checked (assumed OK)")

        # ── Condition 8: Risk / Account Headroom ─────────────────────────────
        daily_dd   = account.get("daily_drawdown_pct", 0.0)
        open_count = account.get("open_positions", 0)

        risk_ok = daily_dd < 2.5 and open_count < 7
        conditions["risk"] = risk_ok
        if not risk_ok:
            if daily_dd >= 2.5:
                notes.append(f"Risk: daily drawdown {daily_dd:.1f}% ≥ 2.5% limit ✗")
            if open_count >= 7:
                notes.append(f"Risk: {open_count} open trades ≥ 7 limit ✗")
        else:
            notes.append(f"Risk: DD={daily_dd:.1f}%, positions={open_count}/7 ✓")

        # ── News aftermath detection ──────────────────────────────────────────
        if news_event_minutes_ago is not None and 5 <= news_event_minutes_ago <= 30:
            special_setup = "NEWS_AFTERMATH"
            notes.append("⚡ NEWS AFTERMATH: 5-30 min post-event — watch for 50-61.8% retracement entry")

        # ── Grade ─────────────────────────────────────────────────────────────
        score_count = sum(conditions.values())

        # Special setups get a free pass on one condition
        if special_setup in ("INSTITUTIONAL_DIVERGENCE",):
            effective_score = score_count + 1
            notes.append(f"Special setup bonus: {special_setup} adds +1 to score")
        elif special_setup == "BREAKOUT" and ta_ok:
            effective_score = score_count + 1
            notes.append("Breakout bonus: +1 to score")
        else:
            effective_score = score_count

        if effective_score >= 8:
            grade = "A++"
            passes = True
            rec_size = 1.0
            rec_rr   = 3.0
        elif effective_score == 7:
            grade = "A+"
            passes = True
            rec_size = 1.0
            rec_rr   = 2.5
        elif effective_score == 6:
            grade = "A"
            passes = True
            rec_size = 0.5
            rec_rr   = 2.0
        else:
            grade = "FAIL"
            passes = False
            rec_size = 0.0
            rec_rr   = 0.0
            notes.append(f"BLOCKED: only {effective_score}/8 conditions met (need ≥6)")

        logger.info(
            f"[EdgeFilter] {instrument} {direction}: {grade} ({score_count}/8) "
            f"special={special_setup}"
        )

        return EdgeCheckResult(
            passes=passes,
            score=score_count,
            grade=grade,
            conditions=conditions,
            recommended_size=rec_size,
            recommended_rr=rec_rr,
            special_setup=special_setup,
            notes=notes,
        )
