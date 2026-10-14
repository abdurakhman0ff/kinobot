"""SQLite ulanishi (aiosqlite, WAL). Bitta instans uchun bitta ulanish.

Yozuvlar umumiy lock orqali ketma-ket bajariladi; ko'p bosqichli amallar `tx()` ichida.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, AsyncIterator, Iterable, Sequence

import aiosqlite

Params = Sequence[Any] | dict[str, Any]

_in_tx: ContextVar[bool] = ContextVar("_in_tx", default=False)


class Database:
    def __init__(self) -> None:
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self.path = ""

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Baza ulanmagan")
        return self._conn

    async def connect(self, path: str) -> None:
        self.path = path
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        # isolation_level=None: avtomatik commit, tranzaksiyalar qo'lda (BEGIN IMMEDIATE)
        self._conn = await aiosqlite.connect(path, isolation_level=None)
        self._conn.row_factory = aiosqlite.Row
        for pragma in (
            "PRAGMA journal_mode=WAL",
            "PRAGMA foreign_keys=ON",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA busy_timeout=5000",
        ):
            await self._conn.execute(pragma)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ---------- o'qish ----------

    async def fetchone(self, sql: str, params: Params = ()) -> dict[str, Any] | None:
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
        return dict(row) if row is not None else None

    async def fetchall(self, sql: str, params: Params = ()) -> list[dict[str, Any]]:
        async with self.conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def fetchval(self, sql: str, params: Params = (), default: Any = None) -> Any:
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
        if row is None or row[0] is None:
            return default
        return row[0]

    # ---------- yozish ----------

    async def _run(self, sql: str, params: Params) -> aiosqlite.Cursor:
        if _in_tx.get():
            return await self.conn.execute(sql, params)
        async with self._lock:
            return await self.conn.execute(sql, params)

    async def execute(self, sql: str, params: Params = ()) -> int:
        """Ta'sirlangan qatorlar soni."""
        cur = await self._run(sql, params)
        count = cur.rowcount
        await cur.close()
        return count

    async def insert(self, sql: str, params: Params = ()) -> int:
        """Oxirgi qo'shilgan qator ID si."""
        cur = await self._run(sql, params)
        rowid = cur.lastrowid or 0
        await cur.close()
        return rowid

    async def executemany(self, sql: str, seq: Iterable[Params]) -> None:
        if _in_tx.get():
            await self.conn.executemany(sql, seq)
            return
        async with self._lock:
            await self.conn.executemany(sql, seq)

    @asynccontextmanager
    async def tx(self) -> AsyncIterator[None]:
        if _in_tx.get():
            yield
            return
        async with self._lock:
            token = _in_tx.set(True)
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                await self.conn.execute("ROLLBACK")
                raise
            else:
                await self.conn.execute("COMMIT")
            finally:
                _in_tx.reset(token)

    @asynccontextmanager
    async def exclusive(self) -> AsyncIterator[None]:
        """Boshqa yozuvlarsiz ishlash (masalan VACUUM INTO)."""
        async with self._lock:
            yield


db = Database()
