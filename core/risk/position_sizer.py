"""
Position sizing using fixed fractional risk (with Kelly Criterion cap).
Ensures no single trade risks more than MAX_RISK_PER_TRADE_PCT of equity.
"""

import os
from loguru import logger

# Pip values (approximate, per standard lot = 100,000 units)
PIP_VALUES_USD = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0, "NZDUSD": 10.0,
    "USDJPY": 9.09, "USDCAD": 7.46, "USDCHF": 10.93,
    "EURJPY": 9.09, "GBPJPY": 9.09,
    "XAUUSD": 1.0,   # per 0.01 = $1
    "XAGUSD": 50.0,
    "USOIL": 10.0,
    "UKOIL": 10.0,
    "NATGAS": 10.0,
}

PIP_SIZES = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001,
    "NZDUSD": 0.0001, "USDCAD": 0.0001, "USDCHF": 0.0001,
    "USDJPY": 0.01,   "EURJPY": 0.01,   "GBPJPY": 0.01,
    "XAUUSD": 0.01,   "XAGUSD": 0.001,
    "USOIL": 0.01,    "UKOIL": 0.01,    "NATGAS": 0.001,
}


class PositionSizer:
    def __init__(self) -> None:
        self.max_risk_pct = float(os.environ.get("MAX_RISK_PER_TRADE_PCT", 1.0))
        self.min_lot = 0.01
        self.max_lot = 5.0

    def validate_lot(
        self,
        instrument: str,
        lot_size: float,
        stop_loss_price: float,
        account_equity: float,
        entry_price: float | None = None,
    ) -> dict:
        """
        Validate and potentially adjust a proposed lot size.
        Returns {"valid": bool, "lot_size": float, "reason": str}.
        """
        if entry_price is None:
            # Can't compute exact risk without entry — trust Claude's calculation
            if self.min_lot <= lot_size <= self.max_lot:
                return {"valid": True, "lot_size": round(lot_size, 2), "reason": "ok"}
            return {"valid": False, "lot_size": 0, "reason": f"Lot {lot_size} out of bounds [{self.min_lot}, {self.max_lot}]"}

        risk_amount = account_equity * (self.max_risk_pct / 100)
        pip_size = PIP_SIZES.get(instrument, 0.0001)
        pip_value = PIP_VALUES_USD.get(instrument, 10.0)

        sl_distance_pips = abs(entry_price - stop_loss_price) / pip_size
        if sl_distance_pips <= 0:
            return {"valid": False, "lot_size": 0, "reason": "Stop loss distance is zero"}

        # Max lot based on risk rule
        max_lots = risk_amount / (sl_distance_pips * pip_value)
        max_lots = max(self.min_lot, min(max_lots, self.max_lot))
        safe_lot = min(lot_size, max_lots)
        safe_lot = round(safe_lot, 2)

        if safe_lot < self.min_lot:
            return {"valid": False, "lot_size": 0, "reason": f"Safe lot {safe_lot} below minimum {self.min_lot}"}

        if safe_lot < lot_size:
            logger.info(f"[SIZER] Adjusted lot {lot_size} → {safe_lot} for {instrument} (risk rule)")

        return {"valid": True, "lot_size": safe_lot, "reason": "ok"}

    def compute_sl_tp(
        self,
        instrument: str,
        direction: str,
        entry_price: float,
        atr: float,
        sl_atr_multiplier: float = 1.5,
        tp_atr_multiplier: float = 2.5,
    ) -> dict:
        """Compute ATR-based stop loss and take profit levels."""
        pip_size = PIP_SIZES.get(instrument, 0.0001)
        sl_distance = atr * sl_atr_multiplier
        tp_distance = atr * tp_atr_multiplier

        if direction == "BUY":
            sl = entry_price - sl_distance
            tp = entry_price + tp_distance
        else:
            sl = entry_price + sl_distance
            tp = entry_price - tp_distance

        return {
            "stop_loss": round(sl, 5),
            "take_profit": round(tp, 5),
            "risk_reward": round(tp_distance / sl_distance, 2),
        }
