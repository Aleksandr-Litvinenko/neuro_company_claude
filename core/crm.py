"""Логика CRM: контакты, стадии воронки, лог интеракций, метрики, инспекция узлов."""
from __future__ import annotations

from typing import Any

from . import config, db, events
from .config import DELIVERY_STEPS, NODE_AGENT, STAGES

CHANNEL_LABEL = {
    "call": "Звонок", "email": "E-mail", "telegram": "Telegram",
    "whatsapp": "WhatsApp", "meeting": "Встреча", "task": "Задача",
}


def mgr_of(cid: int) -> int:
    """Какой из двух менеджеров ведёт контакт (детерминированно по id)."""
    return (cid % 2) + 1


# ── Контакты ─────────────────────────────────────────────────────────────────
def add_contact(**f: Any) -> int:
    f.setdefault("lang", "en"); f.setdefault("stage", "NEW")
    f.setdefault("owner", "AI"); f.setdefault("score", 0); f.setdefault("step", 0)
    cid = db.execute(
        """INSERT INTO contacts (name, company, role, email, phone, telegram,
            lang, source, stage, score, step, owner, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (f.get("name"), f.get("company"), f.get("role"), f.get("email"),
         f.get("phone"), f.get("telegram"), f["lang"], f.get("source"),
         f["stage"], f["score"], f["step"], f["owner"], db.now(), db.now()),
    )
    c = get(cid)
    events.emit("contact_new", contact=c)
    events.log(f"+ Новый запрос: {c['name']} ({c.get('company') or '—'})", "good")
    return cid


def get(cid: int) -> dict[str, Any] | None:
    return db.one("SELECT * FROM contacts WHERE id=?", (cid,))


def list_contacts(limit: int = 500) -> list[dict[str, Any]]:
    return db.query("SELECT * FROM contacts ORDER BY updated_at DESC LIMIT ?", (limit,))


def set_stage(cid: int, stage: str) -> None:
    db.execute("UPDATE contacts SET stage=?, updated_at=? WHERE id=?", (stage, db.now(), cid))
    events.emit("stage_change", contact=get(cid), stage=stage)


def set_step(cid: int, step: int) -> None:
    db.execute("UPDATE contacts SET step=?, updated_at=? WHERE id=?", (step, db.now(), cid))


def bump_score(cid: int, delta: int) -> None:
    db.execute("UPDATE contacts SET score=score+?, updated_at=? WHERE id=?", (delta, db.now(), cid))


def log_interaction(cid: int, channel: str, direction: str, agent: str,
                    summary: str, content: str = "", sentiment: str = "neutral",
                    outcome: str = "") -> int:
    iid = db.execute(
        """INSERT INTO interactions (contact_id, channel, direction, agent,
            summary, content, sentiment, outcome, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (cid, channel, direction, agent, summary, content, sentiment, outcome, db.now()),
    )
    db.execute("UPDATE contacts SET updated_at=? WHERE id=?", (db.now(), cid))
    c = get(cid)
    events.emit("interaction", contact=c, channel=channel, direction=direction,
                agent=agent, summary=summary, sentiment=sentiment)
    arrow = "→" if direction == "out" else "←"
    name = c["name"] if c else f"#{cid}"
    events.log(f"{CHANNEL_LABEL.get(channel, channel)} {arrow} {name}: {summary}",
               "bad" if sentiment == "negative" else "info")
    return iid


# ── Аналитика ────────────────────────────────────────────────────────────────
def pipeline_counts() -> dict[str, int]:
    counts = {s: 0 for s in STAGES}
    for row in db.query("SELECT stage, COUNT(*) AS n FROM contacts GROUP BY stage"):
        counts[row["stage"]] = row["n"]
    return counts


def metrics() -> dict[str, Any]:
    p = pipeline_counts()
    total = sum(p.values())
    won = p.get("WON", 0)
    return {
        "requests": total,
        "dialog": p.get("NEW", 0) + p.get("CONTACTED", 0) + p.get("RP_REVIEW", 0),
        "awaiting": p.get("APPROVAL", 0),
        "delivery": p.get("DELIVERY", 0),
        "won": won,
        "lost": p.get("LOST", 0),
        "conversion": round(100 * won / total, 1) if total else 0.0,
    }


# ── Инспекция узлов (кликабельная панель) ────────────────────────────────────
def conversation(cid: int) -> list[dict[str, Any]]:
    return db.query("SELECT * FROM interactions WHERE contact_id=? ORDER BY created_at ASC, id ASC", (cid,))


def dialogues(stages: list[str], mgr: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Контакты на заданных стадиях + их последнее сообщение."""
    ph = ",".join("?" * len(stages))
    sql = f"""
        SELECT c.id, c.name, c.company, c.role, c.stage, c.lang, c.score, c.step, c.updated_at,
               i.summary AS last_summary, i.channel AS last_channel,
               i.sentiment AS last_sentiment, i.direction AS last_dir, i.created_at AS last_at,
               (SELECT COUNT(*) FROM interactions x WHERE x.contact_id=c.id) AS msg_count
        FROM contacts c
        LEFT JOIN interactions i ON i.id = (
            SELECT id FROM interactions y WHERE y.contact_id=c.id ORDER BY created_at DESC, id DESC LIMIT 1
        )
        WHERE c.stage IN ({ph})"""
    params: list[Any] = list(stages)
    if mgr:
        sql += " AND ((c.id % 2) + 1) = ?"
        params.append(mgr)
    sql += " ORDER BY c.updated_at DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


def _step_node(step: int) -> str:
    if 0 <= step < len(DELIVERY_STEPS):
        return DELIVERY_STEPS[step]["node"]
    return "done"


def _step_label(step: int) -> str:
    if 0 <= step < len(DELIVERY_STEPS):
        return DELIVERY_STEPS[step]["summary"]
    return "Готово к сдаче"


def delivery_board(node: str | None = None, limit: int = 80) -> list[dict[str, Any]]:
    """Сделки в производстве: текущий этап и узел. Опц. фильтр по узлу."""
    rows = dialogues(["DELIVERY"], limit=limit)
    out = []
    for r in rows:
        r["cur_node"] = _step_node(r["step"] or 0)
        r["cur_step"] = _step_label(r["step"] or 0)
        if node is None or r["cur_node"] == node:
            out.append(r)
    return out


def reports_by(node: str, limit: int = 12) -> list[dict[str, Any]]:
    agent = NODE_AGENT.get(node, node)
    return db.query(
        """SELECT i.*, c.name AS contact_name FROM interactions i
           LEFT JOIN contacts c ON c.id=i.contact_id
           WHERE i.agent=? ORDER BY i.created_at DESC LIMIT ?""",
        (agent, limit),
    )
