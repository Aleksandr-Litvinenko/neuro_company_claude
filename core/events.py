"""Шина событий: оркестратор/агенты публикуют, панель слушает по WebSocket."""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

_subscribers: set[asyncio.Queue] = set()
_recent: deque[dict] = deque(maxlen=200)  # буфер для лога/реплея новым клиентам


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def recent(n: int = 60) -> list[dict]:
    items = list(_recent)
    return items[-n:]


def emit(event_type: str, **data: Any) -> None:
    """Синхронная публикация события всем подписчикам панели."""
    evt = {"type": event_type, "ts": time.time(), "data": data}
    _recent.append(evt)
    for q in list(_subscribers):
        try:
            q.put_nowait(evt)
        except asyncio.QueueFull:
            # Медленный клиент — выкидываем самое старое, кладём новое.
            try:
                q.get_nowait()
                q.put_nowait(evt)
            except Exception:
                pass


def log(line: str, level: str = "info") -> None:
    """Строка в ленту терминала панели."""
    emit("log", line=line, level=level)


def flow(src: str, dst: str, contact: dict | None = None,
         color: str = "#00e5ff", label: str = "") -> None:
    """Анимация потока по цепочке узлов. src/dst — ключи узлов или 'client'."""
    c = contact or {}
    emit("flow", src=src, dst=dst, color=color, label=label,
         contact_id=c.get("id"), name=c.get("name"))
