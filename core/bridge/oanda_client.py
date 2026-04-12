"""
OANDA v20 REST API execution adapter.
Replaces ZeroMQ/MT5 for cloud-native trading.
Supports demo (practice) and live accounts.

Sign up free: https://www.oanda.com/register/#/sign-up/demo
"""

import os
from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger

# OANDA instrument name mapping (NVC → OANDA format)
INSTRUMENT_MAP = {
    "EURUSD": "EUR_USD", "GBPUSD": "GBP_USD", "USDJPY": "USD_JPY",
    "AUDUSD": "AUD_USD", "USDCAD": "USD_CAD", "NZDUSD": "NZD_USD",
    "USDCHF": "USD_CHF", "EURJPY": "EUR_JPY", "GBPJPY": "GBP_JPY",
    "XAUUSD": "XAU_USD", "XAGUSD": "XAG_USD",
    "USOIL":  "WTICO_USD", "UKOIL": "BCO_USD", "NATGAS": "NATGAS_USD",
}

OANDA_PRACTICE_URL = "https://api-fxpractice.oanda.com"
OANDA_LIVE_URL     = "https://api-fxtrade.oanda.com"

# Approximate mid prices for dry-run/test mode — kept intentionally rough
# (1-pip precision is enough; these are never used for real P&L)
DRY_RUN_PRICES: dict[str, float] = {
    "EURUSD": 1.0850, "GBPUSD": 1.2700, "USDJPY": 149.50,
    "AUDUSD": 0.6550, "USDCAD": 1.3600, "NZDUSD": 0.6050,
    "USDCHF": 0.9050, "EURJPY": 162.00, "GBPJPY": 190.00,
    "XAUUSD": 2320.0, "XAGUSD": 27.50,
    "USOIL": 78.50,   "UKOIL": 82.00,   "NATGAS": 1.75,
}


class OandaClient:
    """
    Full execution layer via OANDA REST API v20.
    Works on demo (practice) and live accounts.
    No MT5 or ZeroMQ required — runs from any cloud server.
    """

    def __init__(self) -> None:
        self.api_key    = os.environ.get("OANDA_API_KEY", "")
        self.account_id = os.environ.get("OANDA_ACCOUNT_ID", "")
        live            = os.environ.get("OANDA_LIVE", "false").lower() == "true"
        self.base_url   = OANDA_LIVE_URL if live else OANDA_PRACTICE_URL
        self.is_live    = live

        if not self.api_key or not self.account_id:
            logger.warning("[OANDA] API key or account ID not set — running in dry-run mode")

        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept-Datetime-Format": "RFC3339",
        }

    # ─── Account Info ─────────────────────────────────────────────────────────

    async def get_account_info(self) -> dict:
        if not self._is_configured():
            return self._mock_account()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{self.base_url}/v3/accounts/{self.account_id}/summary",
                    headers=self._headers,
                )
                r.raise_for_status()
                data = r.json()["account"]

            balance  = float(data["balance"])
            equity   = float(data["NAV"])
            margin   = float(data["marginUsed"])
            pl       = float(data["unrealizedPL"])

            return {
                "balance": balance,
                "equity": equity,
                "margin": margin,
                "free_margin": equity - margin,
                "unrealised_pl": pl,
                "daily_drawdown_pct": 0.0,   # computed from DB snapshots
                "weekly_drawdown_pct": 0.0,
                "monthly_drawdown_pct": 0.0,
                "currency": data.get("currency", "USD"),
                "system_status": "live" if self.is_live else "demo",
                "broker": "OANDA",
            }
        except Exception as exc:
            logger.error(f"[OANDA] get_account_info failed: {exc}")
            return self._mock_account()

    # ─── Open Positions ────────────────────────────────────────────────────────

    async def get_positions(self) -> list[dict]:
        if not self._is_configured():
            return []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{self.base_url}/v3/accounts/{self.account_id}/openTrades",
                    headers=self._headers,
                )
                r.raise_for_status()
                trades = r.json().get("trades", [])

            return [
                {
                    "ticket": int(t["id"]),
                    "instrument": self._from_oanda(t["instrument"]),
                    "direction": "BUY" if float(t["currentUnits"]) > 0 else "SELL",
                    "lot_size": abs(float(t["currentUnits"])) / 100_000,
                    "entry_price": float(t["price"]),
                    "current_price": float(t.get("price", t["price"])),
                    "stop_loss": float(t["stopLossOrder"]["price"]) if t.get("stopLossOrder") else 0.0,
                    "take_profit": float(t["takeProfitOrder"]["price"]) if t.get("takeProfitOrder") else 0.0,
                    "profit": float(t.get("unrealizedPL", 0)),
                    "open_time": t.get("openTime", ""),
                }
                for t in trades
            ]
        except Exception as exc:
            logger.error(f"[OANDA] get_positions failed: {exc}")
            return []

    # ─── Execute Trade ─────────────────────────────────────────────────────────

    async def send_signal(self, signal: dict) -> dict:
        """
        Execute a trade via OANDA REST API.
        Converts NVC signal format to OANDA order format.
        """
        instrument = signal["instrument"]
        direction  = signal["direction"]
        lot_size   = signal["lot_size"]
        sl         = signal.get("stop_loss")
        tp         = signal.get("take_profit")
        signal_id  = signal.get("signal_id", "")

        oanda_instrument = INSTRUMENT_MAP.get(instrument)
        if not oanda_instrument:
            return {"status": "REJECTED", "reason": f"Instrument {instrument} not in OANDA map"}

        # OANDA units: 1 lot = 100,000 units for forex
        units = int(lot_size * 100_000)
        if direction == "SELL":
            units = -units

        order_body: dict[str, Any] = {
            "order": {
                "type": "MARKET",
                "instrument": oanda_instrument,
                "units": str(units),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
                "clientExtensions": {
                    "id": signal_id[:32] if signal_id else "nvc",
                    "comment": f"NVC|{signal.get('reason', '')[:50]}",
                },
            }
        }

        # Attach SL/TP if provided
        if sl:
            order_body["order"]["stopLossOnFill"] = {
                "price": f"{sl:.5f}",
                "timeInForce": "GTC",
            }
        if tp:
            order_body["order"]["takeProfitOnFill"] = {
                "price": f"{tp:.5f}",
                "timeInForce": "GTC",
            }

        if not self._is_configured():
            mid = DRY_RUN_PRICES.get(instrument, 1.09000)
            logger.info(f"[OANDA DRY-RUN] Would execute: {direction} {lot_size} {instrument} @ ~{mid}")
            return {
                "status": "FILLED",
                "ticket": 99999999,
                "fill_price": mid,
                "fill_time": datetime.now(timezone.utc).isoformat(),
                "mode": "dry_run",
            }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    f"{self.base_url}/v3/accounts/{self.account_id}/orders",
                    headers=self._headers,
                    json=order_body,
                )
                data = r.json()

            if "orderFillTransaction" in data:
                fill = data["orderFillTransaction"]
                logger.success(
                    f"[OANDA] FILLED {direction} {instrument} "
                    f"@ {fill['price']} | ticket={fill['tradeOpened']['tradeID']}"
                )
                return {
                    "status": "FILLED",
                    "ticket": int(fill["tradeOpened"]["tradeID"]),
                    "fill_price": float(fill["price"]),
                    "fill_time": fill["time"],
                    "units": fill["units"],
                }

            if "orderCancelTransaction" in data:
                reason = data["orderCancelTransaction"].get("reason", "unknown")
                logger.warning(f"[OANDA] Order CANCELLED: {reason}")
                return {"status": "CANCELLED", "reason": reason}

            logger.error(f"[OANDA] Unexpected response: {data}")
            return {"status": "FAILED", "reason": str(data)}

        except Exception as exc:
            logger.exception(f"[OANDA] send_signal failed: {exc}")
            return {"status": "ERROR", "reason": str(exc)}

    # ─── Close Position ────────────────────────────────────────────────────────

    async def close_position(self, ticket: int, reason: str) -> dict:
        if not self._is_configured():
            return {"status": "CLOSE_DRY_RUN", "ticket": ticket}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.put(
                    f"{self.base_url}/v3/accounts/{self.account_id}/trades/{ticket}/close",
                    headers=self._headers,
                )
                r.raise_for_status()
                data = r.json()
                logger.info(f"[OANDA] Closed trade {ticket}: {reason}")
                return {"status": "CLOSED", "ticket": ticket, "data": data}
        except Exception as exc:
            logger.error(f"[OANDA] close_position failed: {exc}")
            return {"status": "ERROR", "reason": str(exc)}

    # ─── Modify SL/TP ─────────────────────────────────────────────────────────

    async def modify_position(
        self, ticket: int, new_sl: float | None, new_tp: float | None
    ) -> dict:
        if not self._is_configured():
            return {"status": "MODIFY_DRY_RUN"}
        try:
            body: dict = {}
            if new_sl:
                body["stopLoss"] = {"price": f"{new_sl:.5f}", "timeInForce": "GTC"}
            if new_tp:
                body["takeProfit"] = {"price": f"{new_tp:.5f}", "timeInForce": "GTC"}

            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.put(
                    f"{self.base_url}/v3/accounts/{self.account_id}/trades/{ticket}/orders",
                    headers=self._headers,
                    json=body,
                )
                r.raise_for_status()
            return {"status": "MODIFIED", "ticket": ticket}
        except Exception as exc:
            logger.error(f"[OANDA] modify_position failed: {exc}")
            return {"status": "ERROR", "reason": str(exc)}

    # ─── Live Prices ──────────────────────────────────────────────────────────

    async def get_price(self, instrument: str) -> dict:
        oanda_instrument = INSTRUMENT_MAP.get(instrument, instrument)
        if not self._is_configured():
            mid = DRY_RUN_PRICES.get(instrument, 1.09000)
            return {"bid": mid - 0.00015, "ask": mid + 0.00015, "spread": 0.3}
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    f"{self.base_url}/v3/accounts/{self.account_id}/pricing",
                    headers=self._headers,
                    params={"instruments": oanda_instrument},
                )
                r.raise_for_status()
                price_data = r.json()["prices"][0]

            bid = float(price_data["bids"][0]["price"])
            ask = float(price_data["asks"][0]["price"])
            return {
                "bid": bid,
                "ask": ask,
                "spread": round((ask - bid) * 10000, 1),  # in pips
                "tradeable": price_data.get("tradeable", True),
            }
        except Exception as exc:
            logger.warning(f"[OANDA] get_price failed for {instrument}: {exc}")
            return {"bid": 0.0, "ask": 0.0, "spread": 0.0}

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _is_configured(self) -> bool:
        return bool(self.api_key and self.account_id)

    @staticmethod
    def _from_oanda(oanda_symbol: str) -> str:
        reverse = {v: k for k, v in INSTRUMENT_MAP.items()}
        return reverse.get(oanda_symbol, oanda_symbol.replace("_", ""))

    @staticmethod
    def _mock_account() -> dict:
        # $100 demo account — NOT 100k. Using wrong value breaks Kelly sizing,
        # drawdown %, and every risk calculation downstream.
        return {
            "balance": 100.0,
            "equity": 100.0,
            "margin": 0.0,
            "free_margin": 100.0,
            "unrealised_pl": 0.0,
            "daily_drawdown_pct": 0.0,
            "weekly_drawdown_pct": 0.0,
            "monthly_drawdown_pct": 0.0,
            "currency": "USD",
            "system_status": "dry_run",
            "broker": "OANDA (not configured)",
        }
