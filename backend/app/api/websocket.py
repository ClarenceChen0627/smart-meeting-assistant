from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.schemas.ws_message import FinalizeControlMessage

router = APIRouter()


@router.websocket("/ws/meeting")
async def meeting_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    scene = websocket.query_params.get("scene", "finance")
    target_lang = websocket.query_params.get("target_lang")
    provider = websocket.query_params.get("provider")
    manager = websocket.app.state.session_manager
    session = await manager.create_session(websocket, scene, target_lang, provider)

    try:
        while True:
            message = await websocket.receive()
            message_type = message.get("type")

            if message_type == "websocket.disconnect":
                break

            payload = message.get("bytes")
            if payload is not None:
                await manager.enqueue_audio(session, payload)
                continue

            text_payload = message.get("text")
            if text_payload is None:
                await manager.send_error(session, "Unsupported websocket payload.")
                continue

            try:
                control = FinalizeControlMessage.model_validate(json.loads(text_payload))
            except (json.JSONDecodeError, ValidationError):
                await manager.send_error(session, "Unsupported control message.")
                continue

            if control.type == "finalize":
                await manager.finalize(session)
                break
    except WebSocketDisconnect:
        pass
    finally:
        await manager.cleanup(session)
