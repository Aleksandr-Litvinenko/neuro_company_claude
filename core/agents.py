"""
ИИ-сотрудники. Демо-логика двигает сделки по цепочке и шлёт события `flow`
для анимации. Реальные интеграции — в местах `# TODO[LIVE]`.

Цепочка: КЛИЕНТ → МЕНЕДЖЕР(1/2) → РП → [твоё согласование Проект+КП] →
АНАЛИТИК → РАЗРАБОТЧИК/КОНСУЛЬТАНТ → ТЕСТИРОВЩИК → ПРИЁМЩИК → СДАНО.
"""
from __future__ import annotations

import random

from . import approvals, config, crm, events
from .config import DEMO_MODE

CH_COLOR = {"call": "#00e5ff", "telegram": "#39ff14", "whatsapp": "#39ff14", "email": "#ffb000"}

OUTREACH = {
    "call": {"ru": ["Холодный звонок, выявил потребность", "Дозвонился ЛПР, кратко про услуги"],
             "en": ["Cold call, captured the need", "Reached DM, quick pitch on services"]},
    "telegram": {"ru": ["Написал в Telegram, уточнил задачу", "Ответил на вопрос по срокам"],
                 "en": ["Messaged on Telegram, qualified the task", "Answered the timeline question"]},
    "email": {"ru": ["Письмо с примерами работ", "Follow-up с мини-кейсом"],
              "en": ["Email with work samples", "Follow-up with a mini-case"]},
}
PROJECT_SCOPES = ["внедрение CRM", "автоматизация продаж", "интеграция с 1С",
                  "портал самообслуживания", "аналитический дашборд", "чат-бот поддержки"]


# ── Статус агентов на панели ─────────────────────────────────────────────────
_status: dict[str, dict] = {a["id"]: {"status": "idle", "task": ""} for a in config.WORKFORCE}


def set_status(agent_id: str, status: str, task: str = "") -> None:
    _status[agent_id] = {"status": status, "task": task}
    events.emit("agent_status", agent_id=agent_id, status=status, task=task)


def workforce_state() -> list[dict]:
    return [{**a, **_status.get(a["id"], {"status": "idle", "task": ""})} for a in config.WORKFORCE]


# ── «Мозг» агента (LLM) — нужен только в боевом режиме ────────────────────────
def think(model: str, system: str, prompt: str) -> str:
    if DEMO_MODE or not config.ANTHROPIC_API_KEY:
        return ""
    from anthropic import Anthropic  # TODO[LIVE]: реальный вызов модели
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(model=model, max_tokens=600, system=system,
                                 messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _lang(c: dict) -> str:
    return "ru" if (c.get("lang") or "en").startswith("ru") else "en"


# ── ПРОДАЖИ ──────────────────────────────────────────────────────────────────
def manager_reach(contact: dict) -> None:
    """NEW → менеджер выходит на связь с новым клиентом."""
    cid = contact["id"]; m = f"m{crm.mgr_of(cid)}"
    set_status(m, "working", f"Контакт: {contact['name']}")
    ch = random.choice(["call", "telegram", "email"])
    summary = random.choice(OUTREACH[ch][_lang(contact)])
    # TODO[LIVE]: реальный звонок/сообщение/письмо новому клиенту.
    events.flow("client", m, contact, "#00e5ff", "обращение")
    events.flow(m, "client", contact, CH_COLOR[ch], "ответ")
    crm.log_interaction(cid, ch, "out", config.NODE_AGENT[m], summary)
    crm.bump_score(cid, 6)
    crm.set_stage(cid, "CONTACTED")
    set_status(m, "idle")


def manager_handoff(contact: dict) -> None:
    """CONTACTED → менеджер передаёт лида руководителю проекта."""
    cid = contact["id"]; m = f"m{crm.mgr_of(cid)}"
    set_status(m, "working", f"Передаю РП: {contact['name']}")
    events.flow(m, "rp", contact, "#ff2bd6", "передача РП")
    crm.log_interaction(cid, "task", "out", config.NODE_AGENT[m], "Передал запрос руководителю проекта")
    crm.set_stage(cid, "RP_REVIEW")
    set_status(m, "idle")


def rp_review(contact: dict) -> None:
    """RP_REVIEW → РП оценивает. 50% отсеивается, остальные идут на согласование."""
    cid = contact["id"]
    set_status("rp", "working", f"Оценка: {contact['name']}")
    if random.random() < config.RP_DROP_RATE:
        crm.set_stage(cid, "LOST")
        events.flow("rp", "client", contact, "#ff4d6d", "отказ")
        crm.log_interaction(cid, "task", "out", "РП", "Не подходит по критериям — отсеян", outcome="lost")
        set_status("rp", "idle")
        return
    # не захламляем твой стол: если очередь полна — РП подождёт
    if approvals.count_pending("project_kp") >= config.MAX_OPEN_DESK:
        set_status("rp", "idle")
        return
    _rp_form_project(contact)
    set_status("rp", "idle")


def _rp_form_project(contact: dict) -> None:
    cid = contact["id"]
    amount = random.choice([4500, 6000, 9000, 12000, 18000])
    scope = random.choice(PROJECT_SCOPES)
    crm.set_stage(cid, "APPROVAL")
    events.flow("rp", "you", contact, "#ffb000", "Проект+КП")
    approvals.propose(
        "project_kp", cid, "РП",
        f"Проект + КП: {contact['name']} ({contact.get('company') or '—'})",
        {"amount": amount, "scope": scope, "note": f"{scope} · оценка €{amount}"},
    )


def exec_project_kp(cid: int, payload: dict) -> None:
    """После твоего согласования — запуск производства."""
    c = crm.get(cid)
    crm.set_stage(cid, "DELIVERY"); crm.set_step(cid, 0)
    events.flow("rp", "analyst", c, "#7c5cff", "в работу")
    crm.log_interaction(cid, "task", "out", "РП",
                        f"Проект и КП согласованы (€{payload.get('amount', '—')}) — старт работ",
                        outcome="approved")


# ── ПРОИЗВОДСТВО ─────────────────────────────────────────────────────────────
def delivery_step(contact: dict) -> None:
    """DELIVERY → выполняем следующий этап производства."""
    cid = contact["id"]; step = contact.get("step", 0) or 0
    steps = config.DELIVERY_STEPS
    if step >= len(steps):
        set_status("acceptor", "working", f"Сдача: {contact['name']}")
        events.flow("acceptor", "done", contact, "#39ff14", "сдано")
        crm.set_stage(cid, "WON")
        crm.log_interaction(cid, "task", "out", "ПРИЁМЩИК", "Работа сдана и принята заказчиком", outcome="won")
        set_status("acceptor", "idle")
        return
    s = steps[step]; node = s["node"]
    set_status(node, "working", f"{config.NODE_AGENT[node]}: {contact['name']}")
    for a, b in s["flows"]:
        events.flow(a, b, contact, s["color"], "")
    crm.log_interaction(cid, "task", "out", config.NODE_AGENT[node], s["summary"],
                        outcome="report" if s["report"] else "")
    crm.set_step(cid, step + 1)
    set_status(node, "idle")


def register_all() -> None:
    approvals.register_executor("project_kp", exec_project_kp)
