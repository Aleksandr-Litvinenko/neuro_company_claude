"""Диспетчер: двигает сделки по цепочке продажи → согласование → производство."""
from __future__ import annotations

import asyncio
import random
import time

from . import agents, approvals, crm, events
from .config import TICK_SECONDS

COOLDOWN = 4.0       # сек между действиями по одной сделке
MAX_PER_TICK = 3     # параллельных действий за тик


class Orchestrator:
    def __init__(self) -> None:
        self.paused = False

    async def run(self) -> None:
        agents.register_all()
        events.log("◢ Оркестратор запущен. Команда на смене.", "good")
        for a in agents.workforce_state():
            agents.set_status(a["id"], "idle")
        while True:
            if not self.paused:
                try:
                    self.tick()
                except Exception as exc:
                    events.log(f"tick error: {exc}", "bad")
            await asyncio.sleep(TICK_SECONDS)

    def tick(self) -> None:
        now = time.time()
        active = [c for c in crm.list_contacts() if c["stage"] not in ("WON", "LOST")]
        random.shuffle(active)
        acted = 0
        for c in active:
            if acted >= MAX_PER_TICK:
                break
            if approvals.has_pending(c["id"]):
                continue  # ждём твоего согласования — не трогаем
            if now - (c["updated_at"] or 0) < COOLDOWN:
                continue
            self.advance(c)
            acted += 1

    def advance(self, c: dict) -> None:
        stage = c["stage"]
        if stage == "NEW":
            agents.manager_reach(c)
        elif stage == "CONTACTED":
            agents.manager_handoff(c)
        elif stage == "RP_REVIEW":
            agents.rp_review(c)          # 50% отсев или → на твой стол
        elif stage == "DELIVERY":
            agents.delivery_step(c)      # этапы производства


orchestrator = Orchestrator()
