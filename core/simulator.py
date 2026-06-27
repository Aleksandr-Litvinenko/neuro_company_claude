"""Demo-генератор потока: новый запрос каждые 2 минуты + подпитка производства."""
from __future__ import annotations

import asyncio
import random
import time

from . import config, crm, events
from .config import DEMO_MODE

FIRST_RU = ["Алексей", "Мария", "Дмитрий", "Ольга", "Иван", "Екатерина", "Сергей", "Анна"]
FIRST_EN = ["James", "Emma", "Liam", "Olivia", "Noah", "Sophia", "Lucas", "Mia"]
LAST_RU = ["Соколов", "Иванова", "Кузнецов", "Петрова", "Волков", "Смирнова"]
LAST_EN = ["Carter", "Bennett", "Hughes", "Foster", "Reed", "Parker"]
COMPANIES = ["NovaLabs", "BrightFlow", "AtlasGroup", "ФинПрайм", "ТехноРост", "Quanta", "Меридиан", "ScaleUp"]
ROLES = ["CEO", "CMO", "Head of Growth", "Owner", "Founder", "Коммерч. директор"]
REQUESTS = ["нужна автоматизация", "запрос на CRM", "интеграция систем",
            "хотят дашборд", "бот для поддержки", "перенос в облако"]


def _name() -> tuple[str, str]:
    ru = random.random() < 0.5
    n = f"{random.choice(FIRST_RU if ru else FIRST_EN)} {random.choice(LAST_RU if ru else LAST_EN)}"
    return n, ("ru" if ru else "en")


def _new_request(stage: str = "NEW") -> int:
    n, lang = _name()
    return crm.add_contact(
        name=n, company=random.choice(COMPANIES), role=random.choice(ROLES),
        email=f"lead{random.randint(100, 999)}@example.com",
        phone=f"+{random.randint(1, 79)}{random.randint(1000000000, 9999999999)}",
        telegram=f"@{n.split()[0].lower()}{random.randint(1, 99)}",
        lang=lang, source=random.choice(REQUESTS), stage=stage,
    )


async def run() -> None:
    if not DEMO_MODE:
        return
    events.log("◢ DEMO: новый запрос каждые 2 мин · 50% отсев на РП.", "warn")
    # первый тик: чуть раньше, чтобы было видно механику
    last_req = time.time() - (config.NEW_REQUEST_SECONDS - 20)
    last_inj = time.time() - (config.DELIVERY_INJECT_SECONDS - 12)
    while True:
        now = time.time()
        if now - last_req >= config.NEW_REQUEST_SECONDS:
            _new_request("NEW"); last_req = now
        if now - last_inj >= config.DELIVERY_INJECT_SECONDS:
            # «ранее согласованный» проект уходит в производство (поток работы команды)
            _new_request("DELIVERY"); last_inj = now
        await asyncio.sleep(3)
