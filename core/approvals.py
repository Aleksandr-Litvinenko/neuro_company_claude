"""Очередь man-in-the-middle: агенты предлагают, ты одобряешь/отклоняешь."""
from __future__ import annotations

from typing import Any, Callable

from . import crm, db, events
from .config import APPROVAL_POLICY

# Реестр исполнителей: kind -> функция(contact_id, payload) для выполнения после approve.
_executors: dict[str, Callable[[int, dict], None]] = {}


def register_executor(kind: str, fn: Callable[[int, dict], None]) -> None:
    _executors[kind] = fn


def needs_human(kind: str, escalate: bool = False) -> bool:
    if escalate:
        return True
    return APPROVAL_POLICY.get(kind, True)


def propose(kind: str, contact_id: int, proposed_by: str, title: str,
            payload: dict[str, Any], escalate: bool = False) -> dict[str, Any]:
    """
    Агент предлагает действие. Если политика разрешает авто — выполняем сразу.
    Иначе — кладём карточку тебе на «Стол одобрений» и ждём решения.
    """
    risk = "high" if needs_human(kind, escalate) else "low"
    if risk == "low":
        _run(kind, contact_id, payload)
        return {"auto": True, "kind": kind}

    aid = db.execute(
        """INSERT INTO approvals (kind, contact_id, proposed_by, title, payload,
            risk, status, created_at) VALUES (?,?,?,?,?,?, 'pending', ?)""",
        (kind, contact_id, proposed_by, title, db.dumps(payload), risk, db.now()),
    )
    card = get(aid)
    events.emit("approval_new", approval=card)
    events.log(f"⚑ Нужно твоё решение: {title}", "warn")
    return {"auto": False, "approval_id": aid}


def get(aid: int) -> dict[str, Any] | None:
    row = db.one("SELECT * FROM approvals WHERE id=?", (aid,))
    if row:
        row["payload"] = db.loads(row.get("payload"))
        row["contact"] = crm.get(row["contact_id"]) if row.get("contact_id") else None
    return row


def has_pending(contact_id: int) -> bool:
    row = db.one(
        "SELECT 1 FROM approvals WHERE contact_id=? AND status='pending' LIMIT 1",
        (contact_id,),
    )
    return row is not None


def count_pending(kind: str | None = None) -> int:
    if kind:
        return db.one("SELECT COUNT(*) AS n FROM approvals WHERE status='pending' AND kind=?", (kind,))["n"]
    return db.one("SELECT COUNT(*) AS n FROM approvals WHERE status='pending'")["n"]


def list_pending() -> list[dict[str, Any]]:
    rows = db.query("SELECT * FROM approvals WHERE status='pending' ORDER BY created_at ASC")
    for r in rows:
        r["payload"] = db.loads(r.get("payload"))
        r["contact"] = crm.get(r["contact_id"]) if r.get("contact_id") else None
    return rows


def resolve(aid: int, decision: str, note: str = "", override: dict | None = None) -> dict[str, Any]:
    """decision: 'approved' | 'rejected'. override — правки payload от человека (напр. mode встречи)."""
    card = get(aid)
    if not card or card["status"] != "pending":
        return {"ok": False, "error": "not_pending"}

    db.execute(
        "UPDATE approvals SET status=?, human_note=?, decided_at=? WHERE id=?",
        (decision, note, db.now(), aid),
    )
    payload = card["payload"] or {}
    if override:
        payload.update(override)

    if decision == "approved":
        _run(card["kind"], card["contact_id"], payload)
        events.log(f"✓ Одобрено: {card['title']}", "good")
    else:
        events.log(f"✗ Отклонено: {card['title']}", "bad")
        if card.get("contact_id"):
            crm.set_stage(card["contact_id"], "LOST")
            crm.log_interaction(card["contact_id"], "task", "out", card["proposed_by"],
                                "Проект/КП отклонён оператором", outcome="rejected")

    events.emit("approval_resolved", approval_id=aid, decision=decision)
    return {"ok": True}


def _run(kind: str, contact_id: int, payload: dict) -> None:
    fn = _executors.get(kind)
    if fn:
        fn(contact_id, payload)
    else:
        events.log(f"⚠ Нет исполнителя для '{kind}'", "warn")
