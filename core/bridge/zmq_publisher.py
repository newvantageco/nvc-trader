"""
ZeroMQ bridge: Python → MT5 signal publisher, MT5 → Python fill receiver.
Uses PUSH/PULL pattern over TCP. MT5 EA listens on ZMQ_SIGNAL_PORT.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

import zmq
import zmq.asyncio
from loguru import logger


class ZMQPublisher:
    """
    Sends trade signals to the MT5 Expert Advisor via ZeroMQ PUSH socket.
    Receives fill confirmations via PULL socket.
    """

    def __init__(self) -> None:
        self.host = os.environ.get("ZMQ_HOST", "localhost")
        self.signal_port = int(os.environ.get("ZMQ_SIGNAL_PORT", 5555))
        self.fill_port = int(os.environ.get("ZMQ_FILL_PORT", 5556))
        self._ctx: zmq.asyncio.Context | None = None
        self._push: zmq.asyncio.Socket | None = None
        self._pull: zmq.asyncio.Socket | None = None

    def _ensure_connected(self) -> None:
        if self._ctx is None:
            self._ctx = zmq.asyncio.Context()
            self._push = self._ctx.socket(zmq.PUSH)
            self._push.connect(f"tcp://{self.host}:{self.signal_port}")
            self._pull = self._ctx.socket(zmq.PULL)
            self._pull.bind(f"tcp://*:{self.fill_port}")
            logger.info(f"[ZMQ] Connected → MT5 on {self.host}:{self.signal_port}")

    async def send_signal(self, signal: dict) -> dict:
        """Send a trade signal and wait for fill confirmation (5s timeout)."""
        self._ensure_connected()
        payload = json.dumps(signal)
        await self._push.send_string(payload)
        logger.debug(f"[ZMQ] Signal sent: {payload[:120]}")

        # Wait for fill confirmation
        try:
            poller = zmq.asyncio.Poller()
            poller.register(self._pull, zmq.POLLIN)
            events = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: dict(poller.poll(5000))
                ),
                timeout=6.0,
            )
            if self._pull in events:
                raw = await self._pull.recv_string()
                fill = json.loads(raw)
                logger.info(f"[ZMQ] Fill received: {fill}")
                return fill
        except asyncio.TimeoutError:
            logger.warning("[ZMQ] Fill confirmation timeout — assuming PENDING")

        return {
            "status": "PENDING",
            "signal_id": signal.get("signal_id"),
            "fill_time": datetime.now(timezone.utc).isoformat(),
        }

    async def close_position(self, ticket: int, reason: str) -> dict:
        """Send close instruction for an open position."""
        self._ensure_connected()
        msg = json.dumps({"action": "CLOSE", "ticket": ticket, "reason": reason})
        await self._push.send_string(msg)
        return {"status": "CLOSE_SENT", "ticket": ticket}

    async def modify_position(
        self, ticket: int, new_sl: float | None, new_tp: float | None
    ) -> dict:
        self._ensure_connected()
        msg = json.dumps({
            "action": "MODIFY",
            "ticket": ticket,
            "new_sl": new_sl,
            "new_tp": new_tp,
        })
        await self._push.send_string(msg)
        return {"status": "MODIFY_SENT", "ticket": ticket}

    async def get_account_info(self) -> dict:
        """
        In production: query MT5 via its Python API (MetaTrader5 package).
        Returns mock data when MT5 is not connected.
        """
        try:
            import MetaTrader5 as mt5
            if not mt5.initialize():
                raise RuntimeError("MT5 init failed")
            info = mt5.account_info()
            if info is None:
                raise RuntimeError("No account info")
            return {
                "balance": info.balance,
                "equity": info.equity,
                "margin": info.margin,
                "free_margin": info.margin_free,
                "daily_drawdown_pct": 0.0,   # computed separately from DB
                "weekly_drawdown_pct": 0.0,
                "monthly_drawdown_pct": 0.0,
                "system_status": "active",
            }
        except Exception:
            logger.debug("[MT5] Using mock account data (MT5 not connected)")
            return {
                "balance": 10000.0,
                "equity": 10000.0,
                "margin": 0.0,
                "free_margin": 10000.0,
                "daily_drawdown_pct": 0.0,
                "weekly_drawdown_pct": 0.0,
                "monthly_drawdown_pct": 0.0,
                "system_status": "demo",
            }

    async def get_positions(self) -> list[dict]:
        """Get open positions from MT5."""
        try:
            import MetaTrader5 as mt5
            positions = mt5.positions_get()
            if positions is None:
                return []
            return [
                {
                    "ticket": p.ticket,
                    "instrument": p.symbol,
                    "direction": "BUY" if p.type == 0 else "SELL",
                    "lot_size": p.volume,
                    "entry_price": p.price_open,
                    "current_price": p.price_current,
                    "stop_loss": p.sl,
                    "take_profit": p.tp,
                    "profit": p.profit,
                    "open_time": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
                }
                for p in positions
            ]
        except Exception:
            return []

    def close(self) -> None:
        if self._ctx:
            self._push and self._push.close()
            self._pull and self._pull.close()
            self._ctx.term()
