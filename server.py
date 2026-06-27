"""NEUROCORP — FastAPI сервер: REST + WebSocket + раздача киберпанк-панели."""
from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import seed
from core import agents, approvals, config, crm, db, events
from core.orchestrator import orchestrator
from core import simulator

app = FastAPI(title="NEUROCORP")


def snapshot() -> dict:
    return {
        "company": "NEUROCORP",
        "demo": config.DEMO_MODE,
        "paused": orchestrator.paused,
        "workforce": agents.workforce_state(),
        "pipeline": crm.pipeline_counts(),
        "metrics": crm.metrics(),
        "approvals": approvals.list_pending(),
        "contacts": crm.list_contacts(limit=60),
        "feed": events.recent(60),
        "stages": config.STAGES,
        "policy": config.APPROVAL_POLICY,
    }


@app.on_event("startup")
async def _startup() -> None:
    db.init()
    agents.register_all()
    seed.run()
    app.state.tasks = [
        asyncio.create_task(orchestrator.run()),
        asyncio.create_task(simulator.run()),
    ]


@app.on_event("shutdown")
async def _shutdown() -> None:
    for t in getattr(app.state, "tasks", []):
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(config.WEB_DIR / "index.html")


@app.get("/api/state")
async def api_state() -> JSONResponse:
    return JSONResponse(snapshot())


@app.get("/api/contact/{cid}")
async def api_contact(cid: int) -> JSONResponse:
    return JSONResponse({"contact": crm.get(cid), "interactions": crm.conversation(cid)})


DELIVERY_NODES = {"analyst", "developer", "consultant", "tester", "acceptor"}


@app.get("/api/inspect/{node}")
async def api_inspect(node: str) -> JSONResponse:
    if node in ("m1", "m2"):
        return JSONResponse({"node": node,
                             "dialogues": crm.dialogues(["NEW", "CONTACTED"], mgr=1 if node == "m1" else 2)})
    if node == "rp":
        return JSONResponse({"node": "rp", "dialogues": crm.dialogues(["RP_REVIEW", "APPROVAL"])})
    if node == "you":
        return JSONResponse({"node": "you", "approvals": approvals.list_pending()})
    if node in DELIVERY_NODES:
        return JSONResponse({"node": node, "board": crm.delivery_board(node), "reports": crm.reports_by(node)})
    if node == "done":
        return JSONResponse({"node": "done", "dialogues": crm.dialogues(["WON"])})
    if node == "clients":
        return JSONResponse({"node": "clients", "contacts": crm.list_contacts(80)})
    return JSONResponse({"error": "unknown node"}, status_code=404)


@app.post("/api/approvals/{aid}/resolve")
async def api_resolve(aid: int, body: dict) -> JSONResponse:
    res = approvals.resolve(
        aid,
        decision=body.get("decision", "approved"),
        note=body.get("note", ""),
        override=body.get("override"),
    )
    return JSONResponse(res)


@app.post("/api/leads")
async def api_lead(body: dict) -> JSONResponse:
    cid = crm.add_contact(
        name=body.get("name") or "Без имени",
        company=body.get("company"),
        role=body.get("role"),
        email=body.get("email"),
        phone=body.get("phone"),
        telegram=body.get("telegram"),
        lang=body.get("lang", "ru"),
        source=body.get("source", "Manual"),
    )
    return JSONResponse({"ok": True, "id": cid})


@app.post("/api/control")
async def api_control(body: dict) -> JSONResponse:
    action = body.get("action")
    if action == "pause":
        orchestrator.paused = True
        events.log("⏸ Все агенты на паузе (оператор).", "warn")
    elif action == "resume":
        orchestrator.paused = False
        events.log("▶ Агенты возобновили работу.", "good")
    return JSONResponse({"ok": True, "paused": orchestrator.paused})


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    await socket.accept()
    q = events.subscribe()
    try:
        await socket.send_json({"type": "snapshot", "data": snapshot()})
        while True:
            evt = await q.get()
            await socket.send_json(evt)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        events.unsubscribe(q)


# Статика панели (styles.css, app.js)
app.mount("/web", StaticFiles(directory=config.WEB_DIR), name="web")
