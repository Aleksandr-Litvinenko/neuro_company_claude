"""SQLite-хранилище CRM. Лёгкое, без ORM — позже мигрирует на Postgres."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from .config import DB_PATH

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, company TEXT, role TEXT,
    email TEXT, phone TEXT, telegram TEXT,
    lang TEXT DEFAULT 'en',
    source TEXT,
    stage TEXT DEFAULT 'NEW',
    score INTEGER DEFAULT 0,
    step INTEGER DEFAULT 0,
    owner TEXT DEFAULT 'AI',
    created_at REAL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER,
    channel TEXT,           -- call / email / telegram / whatsapp / meeting
    direction TEXT,         -- out / in
    agent TEXT,
    summary TEXT,
    content TEXT,
    sentiment TEXT,         -- positive / neutral / negative
    outcome TEXT,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER,
    scheduled_at REAL,
    mode TEXT,              -- human_join / client_self / skip
    status TEXT DEFAULT 'planned',
    result TEXT,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT,
    contact_id INTEGER,
    proposed_by TEXT,
    title TEXT,
    payload TEXT,           -- json
    risk TEXT,              -- low / high
    status TEXT DEFAULT 'pending',  -- pending / approved / rejected
    human_note TEXT,
    created_at REAL, decided_at REAL
);
"""


def init() -> None:
    with _lock:
        c = conn()
        c.executescript(SCHEMA)
        # безопасная миграция для старых БД
        cols = [r[1] for r in c.execute("PRAGMA table_info(contacts)").fetchall()]
        if "step" not in cols:
            c.execute("ALTER TABLE contacts ADD COLUMN step INTEGER DEFAULT 0")
        c.commit()


def now() -> float:
    return time.time()


def execute(sql: str, params: tuple = ()) -> int:
    with _lock:
        c = conn()
        cur = c.execute(sql, params)
        c.commit()
        return cur.lastrowid


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with _lock:
        c = conn()
        rows = c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def one(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def loads(s: str | None) -> Any:
    return json.loads(s) if s else None
