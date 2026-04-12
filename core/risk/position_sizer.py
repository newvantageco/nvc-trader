"""
Position sizing — Van Tharp fixed fractional method with regime and conviction multipliers.

Formula: lot_size = (equity × base_risk% × regime_mult × conviction_mult) / (stop_pips × pip_value)

Regime multipliers (from 26-year FX research):
  TRENDING        → 1.0×  (full size, trend is your friend)
  RANGING         → 0.7×  (whipsaws more likely)
  CRISIS / VOLATILE → 0.3×  (protect capital first)
  BREAKOUT        → 1.0×  (momentum confirmed)

Conviction multipliers:
  HIGH   (≥4/5 factors aligned) → 1.3×
  MEDIUM (3/5 factors aligned)  → 1.0×
  LOW    (2/5 factors aligned)  → 0.6×  (shouldn't be trading, but cap damage if forced)

Hard ceiling: never exceed 2% risk on any single trade regardless of multipliers.
"""

import os
from loguru import logger

# Pip values (USD per pip per standard lot = 100,000 units)
PIP_VALUES_USD = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0, "NZDUSD": 10.0,
    "USDJPY": 9.09, "USDCAD": 7.46, "USDCHF": 10.93,
    "EURJPY": 9.09, "GBPJPY": 9.09,
    "XAUUSD": 1.0,   # per $0.01 move per lot
    "XAGUSD": 50.0,
    "USOIL":  10.0,
    "UKOIL":  10.0,
    "NATGAS": 10.0,
}

PIP_SIZES = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001,
    "NZDUSD": 0.0001, "USDCAD": 0.0001, "USDCHF": 0.0001,
    "USDJPY": 0.01,   "EURJPY": 0.01,   "GBPJPY": 0.01,
    "XAUUSD": 0.01,   "XAGUSD": 0.001,
    "USOIL":  0.01,   "UKOIL":  0.01,   "NATGAS": 0.001,
}

# Regime → position size multiplier
REGIME_MULTIPLIERS: dict[str, float] = {
    "TRENDING_BULLISH": 1.0,
    "TRENDING_BEARISH": 1.0,
    "BREAKOUT":         1.0,
    "RANGING":          0.7,
    "EXHAUSTED":        0.3,
    "VOLATILE":         0.3,
    "CRISIS":           0.3,
}

# Factors aligned (out of 5) → conviction multiplier
CONVICTION_MULTIPLIERS: dict[int, float] = {
    5: 1.3,
    4: 1.3,
    3: 1.0,
    2: 0.6,
    1: 0.0,   # never trade with 1 factor
    0: 0.0,
}


class PositionSizer:
    def __init__(self) -> None:
        self.base_risk_pct = float(os.environ.get("MAX_RISK_PER_TRADE_PCT", 1.0))
        self.hard_max_risk_pct = 2.0   # absolute ceiling — cannot be exceeded
        self.min_lot = 0.01
        self.max_lot = 5.0

    def calculate_lot(
        self,
        instrument:      str,
        entry_price:     float,
        stop_loss:       float,
        account_equity:  float,
        regime:          str = "RANGING",
        factors_aligned: int = 3,
        circuit_mult:    float = 1.0,   # from CircuitBreaker.size_multiplier()
    ) -> dict:
        """
        Calculate the correct lot size using Van Tharp formula + multipliers.
        Returns full sizing context for Claude to use directly.
        """
        pip_size  = PIP_SIZES.get(instrument, 0.0001)
        pip_value = PIP_VALUES_USD.get(instrument, 10.0)

        sl_pips = abs(entry_price - stop_loss) / pip_size
        if sl_pips <= 0:
            return {"lot_size": 0.0, "error": "Stop loss distance is zero", "risk_usd": 0}

        regime_mult     = REGIME_MULTIPLIERS.get(regime, 0.7)
        conviction_mult = CONVICTION_MULTIPLIERS.get(min(factors_aligned, 5), 0.6)

        # Effective risk % after all multipliers
        # circuit_mult: 0.0 = no trade, 0.5 = R5 weekly limit, 1.0 = normal
        effective_risk_pct = self.base_risk_pct * regime_mult * conviction_mult * circuit_mult
        # Hard cap at 2%
        effective_risk_pct = min(effective_risk_pct, self.hard_max_risk_pct)

        risk_usd  = account_equity * (effective_risk_pct / 100)
        raw_lots  = risk_usd / (sl_pips * pip_value)
        lots      = max(self.min_lot, min(round(raw_lots, 2), self.max_lot))

        actual_risk_usd = lots * sl_pips * pip_value
        actual_risk_pct = actual_risk_usd / account_equity * 100

        logger.info(
            f"[SIZER] {instrument}: regime={regime}({regime_mult}×) "
            f"conviction={factors_aligned}/5({conviction_mult}×) "
            f"circuit={circuit_mult}× → "
            f"risk={effective_risk_pct:.2f}% → {lots} lots "
            f"(${actual_risk_usd:.2f} at risk)"
        )

        return {
            "lot_size":           lots,
            "sl_pips":            round(sl_pips, 1),
            "risk_usd":           round(actual_risk_usd, 2),
            "risk_pct":           round(actual_risk_pct, 3),
            "regime_mult":        regime_mult,
            "conviction_mult":    conviction_mult,
            "circuit_mult":       circuit_mult,
            "effective_risk_pct": round(effective_risk_pct, 2),
        }

    def validate_lot(
        self,
        instrument:     str,
        lot_size:       float,
        stop_loss_price: float,
        account_equity:  float,
        entry_price:    float | None = None,
    ) -> dict:
        """
        Validate and cap a proposed lot size against the 2% hard limit.
        Returns {"valid": bool, "lot_size": float, "reason": str}.
        """
        if entry_price is None:
            if self.min_lot <= lot_size <= self.max_lot:
                return {"valid": True, "lot_size": round(lot_size, 2), "reason": "ok"}
            return {
                "valid": False, "lot_size": 0,
                "reason": f"Lot {lot_size} out of bounds [{self.min_lot}, {self.max_lot}]"
            }

        pip_size  = PIP_SIZES.get(instrument, 0.0001)
        pip_value = PIP_VALUES_USD.get(instrument, 10.0)

        sl_pips = abs(entry_price - stop_loss_price) / pip_size
        if sl_pips <= 0:
            return {"valid": False, "lot_size": 0, "reason": "Stop loss distance is zero"}

        # Hard cap: never exceed 2% on a single trade
        max_risk_usd = account_equity * (self.hard_max_risk_pct / 100)
        max_lots     = max_risk_usd / (sl_pips * pip_value)
        max_lots     = max(self.min_lot, min(max_lots, self.max_lot))
        safe_lot     = min(lot_size, max_lots)
        safe_lot     = round(safe_lot, 2)

        if safe_lot < self.min_lot:
            return {
                "valid": False, "lot_size": 0,
                "reason": f"Safe lot {safe_lot} below minimum {self.min_lot}"
            }

        if safe_lot < lot_size:
            logger.info(f"[SIZER] Hard-capped {lot_size} → {safe_lot} lots for {instrument} (2% risk rule)")

        return {"valid": True, "lot_size": safe_lot, "reason": "ok"}

    def compute_sl_tp(
        self,
        instrument:         str,
        direction:          str,
        entry_price:        float,
        atr:                float,
        sl_atr_multiplier:  float = 1.5,
        tp_atr_multiplier:  float = 2.5,
    ) -> dict:
        """Compute ATR-based stop loss and take profit levels."""
        sl_distance = atr * sl_atr_multiplier
        tp_distance = atr * tp_atr_multiplier

        if direction == "BUY":
            sl = entry_price - sl_distance
            tp = entry_price + tp_distance
        else:
            sl = entry_price + sl_distance
            tp = entry_price - tp_distance

        return {
            "stop_loss":   round(sl, 5),
            "take_profit": round(tp, 5),
            "risk_reward": round(tp_distance / sl_distance, 2),
        }
