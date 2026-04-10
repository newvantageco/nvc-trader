"""
Portfolio-level risk management.
Tracks open position correlations and enforces aggregate exposure limits.
"""

from __future__ import annotations
from dataclasses import dataclass

from loguru import logger

# Known correlation groups — instruments that move together
CORRELATION_GROUPS: list[set[str]] = [
    {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"},   # USD strength drives all
    {"USDJPY", "EURJPY", "GBPJPY"},               # JPY pairs
    {"USOIL", "UKOIL"},                            # crude oil twins
    {"XAUUSD", "XAGUSD"},                          # precious metals
]

MAX_CORRELATED_RISK_PCT  = 3.0   # max combined risk % across correlated group
MAX_SINGLE_CURRENCY_PCT  = 4.0   # max total USD exposure, etc.
MAX_TOTAL_PORTFOLIO_RISK = 6.0   # absolute ceiling across all open trades


@dataclass
class PortfolioCheck:
    allowed:     bool
    reason:      str
    current_risk: float


class PortfolioManager:
    """
    Before any new trade, checks that adding it won't breach correlation limits.
    Also tracks total portfolio heat.
    """

    def check_new_trade(
        self,
        instrument:       str,
        trade_risk_pct:   float,   # risk % for the proposed new trade
        open_positions:   list[dict],
        account_equity:   float,
    ) -> PortfolioCheck:

        # Compute existing risk per instrument
        existing_risk = self._compute_existing_risk(open_positions, account_equity)
        total_risk    = sum(existing_risk.values())

        # 1. Total portfolio heat
        if total_risk + trade_risk_pct > MAX_TOTAL_PORTFOLIO_RISK:
            return PortfolioCheck(
                allowed      = False,
                reason       = f"Total portfolio risk would reach {total_risk + trade_risk_pct:.1f}% (limit {MAX_TOTAL_PORTFOLIO_RISK}%)",
                current_risk = total_risk,
            )

        # 2. Correlated group check
        for group in CORRELATION_GROUPS:
            if instrument not in group:
                continue
            group_risk = sum(existing_risk.get(sym, 0) for sym in group)
            if group_risk + trade_risk_pct > MAX_CORRELATED_RISK_PCT:
                return PortfolioCheck(
                    allowed      = False,
                    reason       = f"Correlated group risk would reach {group_risk + trade_risk_pct:.1f}% (limit {MAX_CORRELATED_RISK_PCT}%)",
                    current_risk = group_risk,
                )

        return PortfolioCheck(
            allowed      = True,
            reason       = "OK",
            current_risk = total_risk,
        )

    def get_exposure_report(
        self, open_positions: list[dict], account_equity: float
    ) -> dict:
        """Full exposure breakdown for the dashboard."""
        existing_risk = self._compute_existing_risk(open_positions, account_equity)
        total_risk    = sum(existing_risk.values())

        group_exposure = []
        for group in CORRELATION_GROUPS:
            group_risk = sum(existing_risk.get(sym, 0) for sym in group)
            if group_risk > 0:
                group_exposure.append({
                    "instruments": list(group),
                    "risk_pct":    round(group_risk, 2),
                    "limit_pct":   MAX_CORRELATED_RISK_PCT,
                    "utilised_pct": round(group_risk / MAX_CORRELATED_RISK_PCT * 100, 1),
                })

        return {
            "total_risk_pct":  round(total_risk, 2),
            "max_risk_pct":    MAX_TOTAL_PORTFOLIO_RISK,
            "utilised_pct":    round(total_risk / MAX_TOTAL_PORTFOLIO_RISK * 100, 1),
            "per_instrument":  existing_risk,
            "correlated_groups": group_exposure,
        }

    @staticmethod
    def _compute_existing_risk(
        positions: list[dict], equity: float
    ) -> dict[str, float]:
        """Estimate risk % per open position based on distance to SL."""
        risk_map: dict[str, float] = {}
        if equity <= 0:
            return risk_map
        for p in positions:
            instrument  = p.get("instrument", "")
            entry       = p.get("entry_price", 0.0)
            sl          = p.get("stop_loss", 0.0)
            lot_size    = p.get("lot_size", 0.0)
            direction   = p.get("direction", "BUY")

            if not (entry and sl and lot_size):
                risk_map[instrument] = 1.0   # assume 1% if no data
                continue

            sl_distance = abs(entry - sl)
            # Rough P&L estimate: $10 per pip per lot for forex
            pip_value   = 10.0
            from core.risk.position_sizer import PIP_SIZES
            pip_size = PIP_SIZES.get(instrument, 0.0001)
            sl_pips   = sl_distance / pip_size
            risk_usd  = sl_pips * pip_value * lot_size
            risk_pct  = (risk_usd / equity) * 100
            risk_map[instrument] = round(risk_pct, 3)

        return risk_map
