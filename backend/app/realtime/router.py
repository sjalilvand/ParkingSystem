import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.realtime.manager import manager

router = APIRouter()


@router.websocket("/ws/v1/events")
async def events_socket(ws: WebSocket, token: str = Query(default="")):
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            await ws.close(code=4401)
            return
        user_id = payload.get("sub")
    except Exception:
        await ws.close(code=4401)
        return

    await manager.connect(user_id, ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect(user_id, ws)
    except Exception:
        manager.disconnect(user_id, ws)