"""Настройки, оргструктура и политика man-in-the-middle."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


_load_env()


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# ── Режим ────────────────────────────────────────────────────────────────────
DEMO_MODE = _bool("DEMO_MODE", True)
TICK_SECONDS = float(os.environ.get("TICK_SECONDS", "2.0"))

# ── Модели мозгов агентов ────────────────────────────────────────────────────
MODEL_WORKER = os.environ.get("MODEL_WORKER", "claude-sonnet-4-6")
MODEL_BRIEF = os.environ.get("MODEL_BRIEF", "claude-opus-4-8")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

DB_PATH = BASE_DIR / "data.db"
WEB_DIR = BASE_DIR / "web"

# ── Воронка / стадии ─────────────────────────────────────────────────────────
# NEW       — поступил запрос
# CONTACTED — менеджер вышел на связь
# RP_REVIEW — передан РП на оценку (здесь 50% отсеивается)
# APPROVAL  — РП сформировал Проект + КП, ждёт твоего согласования
# DELIVERY  — согласовано, идёт работа команды
# WON       — сдано и принято
# LOST      — отсеяно
STAGES = ["NEW", "CONTACTED", "RP_REVIEW", "APPROVAL", "DELIVERY", "WON", "LOST"]
TERMINAL = ["WON", "LOST"]

# ── ИИ-штат (id = ключ узла на панели) ───────────────────────────────────────
WORKFORCE = [
    {"id": "m1",         "name": "МЕНЕДЖЕР-1",  "role": "Обзвон/письма новым", "color": "#00e5ff"},
    {"id": "m2",         "name": "МЕНЕДЖЕР-2",  "role": "Обзвон/письма новым", "color": "#18b6ff"},
    {"id": "rp",         "name": "РП",          "role": "Проект + КП",         "color": "#ff2bd6"},
    {"id": "analyst",    "name": "АНАЛИТИК",    "role": "Декомпозиция",        "color": "#7c5cff"},
    {"id": "developer",  "name": "РАЗРАБОТЧИК", "role": "Реализация",          "color": "#39ff14"},
    {"id": "consultant", "name": "КОНСУЛЬТАНТ", "role": "Настройка в базе",    "color": "#ffb000"},
    {"id": "tester",     "name": "ТЕСТИРОВЩИК", "role": "Тестирование+отчёт",  "color": "#00d0c0"},
    {"id": "acceptor",   "name": "ПРИЁМЩИК",    "role": "Приёмка+отчёт",       "color": "#ff8a3d"},
]
NODE_AGENT = {a["id"]: a["name"] for a in WORKFORCE}

# ── Этапы производства (после согласования Проекта+КП) ────────────────────────
# Аналитик декомпозирует → разработчик реализует И консультант настраивает в базе
# → тестировщик пишет отчёт после каждого → приёмщик принимает и пишет отчёт.
DELIVERY_STEPS = [
    {"node": "analyst",    "summary": "Декомпозировал задачу на подзадачи",      "color": "#7c5cff", "flows": [["rp", "analyst"]],          "report": False},
    {"node": "developer",  "summary": "Реализовал функционал",                   "color": "#39ff14", "flows": [["analyst", "developer"]],   "report": False},
    {"node": "consultant", "summary": "Настроил решение в базе",                 "color": "#ffb000", "flows": [["analyst", "consultant"]],  "report": False},
    {"node": "tester",     "summary": "Отчёт о тестировании: после разработчика", "color": "#00d0c0", "flows": [["developer", "tester"]],    "report": True},
    {"node": "tester",     "summary": "Отчёт о тестировании: после консультанта", "color": "#00d0c0", "flows": [["consultant", "tester"]],   "report": True},
    {"node": "acceptor",   "summary": "Отчёт о приёмке — работа принята",        "color": "#ff8a3d", "flows": [["tester", "acceptor"]],     "report": True},
]

# ── Политика одобрений (man-in-the-middle) ───────────────────────────────────
# На твой стол приходит ТОЛЬКО согласование Проекта+КП. Остальное — авто.
APPROVAL_POLICY = {
    "project_kp": True,   # Проект + КП → всегда к тебе
}

# ── Демо-параметры ───────────────────────────────────────────────────────────
NEW_REQUEST_SECONDS = 120      # новый запрос клиента каждые 2 минуты
DELIVERY_INJECT_SECONDS = 95   # «ранее согласованный» проект в работу (чтобы команда не простаивала)
RP_DROP_RATE = 0.5             # 50% отсеивается на РП
MAX_OPEN_DESK = 3              # чтобы твой стол не захламлялся: не более N карточек в очереди
