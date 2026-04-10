"""
Supabase client wrapper.
All DB operations go through this class.
"""

import os
from typing import Any

from loguru import logger
from supabase import create_client, Client


class SupabaseClient:
    def __init__(self) -> None:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if url and key:
            self._client: Client = create_client(url, key)
        else:
            self._client = None
            logger.warning("[DB] Supabase not configured — running in dry-run mode")

    async def insert(self, table: str, data: dict) -> dict | None:
        if not self._client:
            logger.debug(f"[DB DRY-RUN] INSERT {table}: {str(data)[:120]}")
            return None
        try:
            result = self._client.table(table).insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as exc:
            logger.error(f"[DB] Insert failed on {table}: {exc}")
            return None

    async def select(self, table: str, filters: dict | None = None) -> list[dict]:
        if not self._client:
            return []
        try:
            query = self._client.table(table).select("*")
            if filters:
                for k, v in filters.items():
                    query = query.eq(k, v)
            result = query.execute()
            return result.data or []
        except Exception as exc:
            logger.error(f"[DB] Select failed on {table}: {exc}")
            return []

    async def update(self, table: str, filters: dict, data: dict) -> dict | None:
        if not self._client:
            return None
        try:
            query = self._client.table(table)
            for k, v in filters.items():
                query = query.eq(k, v)
            result = query.update(data).execute()
            return result.data[0] if result.data else None
        except Exception as exc:
            logger.error(f"[DB] Update failed on {table}: {exc}")
            return None
