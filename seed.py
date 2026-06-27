"""Стартовый backlog (B2B-услуги), если база пустая."""
from __future__ import annotations

from core import crm

SEED = [
    dict(name="Дмитрий Орлов", company="ТехноРост", role="Коммерч. директор",
         lang="ru", source="запрос на CRM", stage="NEW"),
    dict(name="Emma Bennett", company="BrightFlow", role="Head of Growth",
         lang="en", source="нужна автоматизация", stage="NEW"),
    dict(name="Сергей Волков", company="Меридиан", role="CEO",
         lang="ru", source="интеграция систем", stage="NEW"),
    dict(name="James Carter", company="AtlasGroup", role="Owner",
         lang="en", source="хотят дашборд", stage="RP_REVIEW"),
    dict(name="Ольга Петрова", company="ScaleUp", role="CMO",
         lang="ru", source="бот для поддержки", stage="RP_REVIEW"),
    # уже в производстве (ранее согласованные) — чтобы команда сразу работала
    dict(name="Liam Foster", company="Quanta", role="Founder",
         lang="en", source="перенос в облако", stage="DELIVERY", step=1),
    dict(name="Анна Смирнова", company="ФинПрайм", role="Founder",
         lang="ru", source="запрос на CRM", stage="DELIVERY", step=3),
]


def run() -> None:
    if crm.list_contacts(limit=1):
        return
    for s in SEED:
        crm.add_contact(**s)
