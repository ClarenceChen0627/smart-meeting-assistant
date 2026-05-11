from __future__ import annotations

import pytest
from fastapi import FastAPI, File, Request, UploadFile, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.upload_validation import read_validated_upload
from app.core.config import Settings
from app.middleware.security import (
    api_token_auth_middleware,
    is_websocket_authorized,
    security_headers_middleware,
)
from app.schemas.meeting_history import MeetingHistoryStatus, MeetingMetadataUpdate, MeetingSourceType
from app.services.meeting_history_service import MeetingHistoryService


def test_api_token_auth_protects_non_public_http_paths(tmp_path) -> None:
    app = FastAPI()
    app.state.settings = Settings(
        meeting_history_db_path=str(tmp_path / "meetings.sqlite3"),
        api_access_token="secret-token",
    )
    app.middleware("http")(security_headers_middleware)
    app.middleware("http")(api_token_auth_middleware)

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "UP"}

    @app.get("/api/meetings")
    async def meetings() -> dict:
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        unauthorized = client.get("/api/meetings")
        assert unauthorized.status_code == 401
        assert unauthorized.json() == {"detail": "API access token is required."}

        bearer = client.get("/api/meetings", headers={"Authorization": "Bearer secret-token"})
        assert bearer.status_code == 200
        assert bearer.headers["X-Content-Type-Options"] == "nosniff"

        api_token = client.get("/api/meetings", headers={"X-API-Token": "secret-token"})
        assert api_token.status_code == 200


def test_websocket_token_auth_accepts_query_token_and_rejects_missing_token(tmp_path) -> None:
    app = FastAPI()
    app.state.settings = Settings(
        meeting_history_db_path=str(tmp_path / "meetings.sqlite3"),
        api_access_token="secret-token",
    )

    @app.websocket("/ws/test")
    async def websocket_endpoint(websocket: WebSocket):
        if not is_websocket_authorized(websocket):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        await websocket.send_json({"ok": True})
        await websocket.close()

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/test"):
                pass

        with client.websocket_connect("/ws/test?access_token=secret-token") as websocket:
            assert websocket.receive_json() == {"ok": True}


def test_upload_validation_enforces_content_type_and_size(tmp_path) -> None:
    app = FastAPI()
    app.state.settings = Settings(
        meeting_history_db_path=str(tmp_path / "meetings.sqlite3"),
        max_upload_bytes=4,
        allowed_upload_content_types=["audio/wav"],
    )

    @app.post("/upload")
    async def upload(request: Request, file: UploadFile = File(...)) -> dict:
        payload = await read_validated_upload(file, request.app.state.settings)
        return {"size": len(payload)}

    with TestClient(app) as client:
        accepted = client.post("/upload", files={"file": ("tiny.wav", b"1234", "audio/wav")})
        assert accepted.status_code == 200
        assert accepted.json() == {"size": 4}

        too_large = client.post("/upload", files={"file": ("large.wav", b"12345", "audio/wav")})
        assert too_large.status_code == 413

        wrong_type = client.post("/upload", files={"file": ("notes.txt", b"abc", "text/plain")})
        assert wrong_type.status_code == 415


def test_meeting_metadata_and_filters_hide_archived_by_default(tmp_path) -> None:
    service = MeetingHistoryService(tmp_path / "meetings.sqlite3")
    service.create_meeting(
        meeting_id="meeting-active",
        scene="general",
        target_lang=None,
        provider="demo",
        status=MeetingHistoryStatus.FINALIZED,
        source_type=MeetingSourceType.LIVE,
        source_name="active.wav",
    )
    service.create_meeting(
        meeting_id="meeting-archived",
        scene="finance",
        target_lang=None,
        provider="dashscope",
        status=MeetingHistoryStatus.FAILED,
        source_type=MeetingSourceType.UPLOAD,
        source_name="archived.wav",
    )

    archived = service.update_metadata(
        "meeting-archived",
        MeetingMetadataUpdate(favorite=True, archived=True, tags=["Customer", "Q2"]),
    )
    assert archived is not None
    assert archived.favorite is True
    assert archived.archived is True
    assert archived.tags == ["Customer", "Q2"]

    assert [meeting.meeting_id for meeting in service.list_meetings()] == ["meeting-active"]
    assert [meeting.meeting_id for meeting in service.list_meetings(archived=True)] == ["meeting-archived"]
    assert [meeting.meeting_id for meeting in service.list_meetings(archived=None, favorite=True)] == ["meeting-archived"]
    assert [meeting.meeting_id for meeting in service.list_meetings(archived=None, tag="customer")] == ["meeting-archived"]
    assert [meeting.meeting_id for meeting in service.list_meetings(archived=None, q="active")] == ["meeting-active"]
