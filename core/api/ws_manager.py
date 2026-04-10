"""WebSocket connection manager — broadcasts to all connected dashboard clients."""

import json
from fastapi import WebSocket
from loguru import logger


class WSManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        logger.debug(f"[WS] Client connected. Total: {len(self._connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.remove(websocket)
        logger.debug(f"[WS] Client disconnected. Total: {len(self._connections)}")

    async def broadcast(self, data: dict) -> None:
        if not self._connections:
            return
        message = json.dumps(data, default=str)
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)
