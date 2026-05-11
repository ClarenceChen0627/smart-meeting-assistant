from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.audit import router as audit_router
from app.api.glossary import router as glossary_router
from app.core.config import Settings
from app.schemas.glossary import GlossaryTermCreate, GlossaryTermUpdate
from app.services.audit_log_service import AuditLogService
from app.services.glossary_service import GlossaryService
from app.services.glossary_store_service import GlossaryStoreService, GlossaryTermAlreadyExists


def build_client(store: GlossaryStoreService, audit_service: AuditLogService | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(audit_router)
    app.include_router(glossary_router)
    app.state.glossary_store_service = store
    if audit_service is not None:
        app.state.audit_log_service = audit_service
    return TestClient(app)


def test_glossary_crud_and_duplicate_validation(tmp_path) -> None:
    store = GlossaryStoreService(tmp_path / "meeting_history.sqlite3")

    with build_client(store) as client:
        create_response = client.post(
            "/api/glossary/terms",
            json={
                "term": "queue wen",
                "replacement": "Qwen",
                "note": "DashScope model family",
            },
        )
        duplicate_response = client.post(
            "/api/glossary/terms",
            json={"term": "QUEUE WEN", "replacement": "Qwen"},
        )

        created = create_response.json()
        update_response = client.patch(
            f"/api/glossary/terms/{created['id']}",
            json={"term": "queuewen", "replacement": "Qwen"},
        )
        list_response = client.get("/api/glossary/terms")
        delete_response = client.delete(f"/api/glossary/terms/{created['id']}")
        missing_delete_response = client.delete(f"/api/glossary/terms/{created['id']}")

    assert create_response.status_code == 201
    assert created["term"] == "queue wen"
    assert created["replacement"] == "Qwen"
    assert created["note"] == "DashScope model family"
    assert created["created_at"].endswith("Z")
    assert duplicate_response.status_code == 409
    assert update_response.status_code == 200
    assert update_response.json()["term"] == "queuewen"
    assert list_response.status_code == 200
    assert [item["term"] for item in list_response.json()] == ["queuewen"]
    assert delete_response.status_code == 204
    assert missing_delete_response.status_code == 404


def test_glossary_crud_writes_global_audit_events(tmp_path) -> None:
    db_path = tmp_path / "meeting_history.sqlite3"
    store = GlossaryStoreService(db_path)
    audit_service = AuditLogService(db_path)

    with build_client(store, audit_service) as client:
        create_response = client.post(
            "/api/glossary/terms",
            json={"term": "queue wen", "replacement": "Qwen"},
        )
        created = create_response.json()
        update_response = client.patch(
            f"/api/glossary/terms/{created['id']}",
            json={"note": "DashScope model family"},
        )
        delete_response = client.delete(f"/api/glossary/terms/{created['id']}")
        audit_response = client.get("/api/audit-events?scope=global&entity_type=glossary_term")
        missing_update_response = client.patch(
            "/api/glossary/terms/missing",
            json={"term": "not-recorded"},
        )

    assert create_response.status_code == 201
    assert update_response.status_code == 200
    assert delete_response.status_code == 204
    assert missing_update_response.status_code == 404
    events = audit_response.json()
    assert [event["action"] for event in events] == ["delete", "update", "create"]
    assert events[0]["before"]["term"] == "queue wen"
    assert events[0]["after"] is None
    assert events[1]["metadata"]["updated_fields"] == ["note"]
    assert events[2]["before"] is None
    assert events[2]["after"]["replacement"] == "Qwen"
    assert len(audit_service.list_events(scope=AuditLogService.SCOPE_GLOBAL)) == 3


def test_glossary_store_rejects_duplicate_updates(tmp_path) -> None:
    store = GlossaryStoreService(tmp_path / "meeting_history.sqlite3")
    first = store.create_term(GlossaryTermCreate(term="Qwen", replacement="Tongyi Qianwen"))
    second = store.create_term(GlossaryTermCreate(term="OKR", note="Objectives and key results"))

    with pytest.raises(GlossaryTermAlreadyExists):
        store.update_term(second.id, GlossaryTermUpdate(term="qwen"))

    assert store.list_terms()[0].id == second.id
    assert first.id != second.id


def test_resolve_terms_prefers_meeting_terms_then_global_then_env_and_limits_to_50(tmp_path) -> None:
    store = GlossaryStoreService(tmp_path / "meeting_history.sqlite3")
    store.create_term(GlossaryTermCreate(term="Qwen", replacement="Tongyi Qianwen"))
    store.create_term(GlossaryTermCreate(term="OKR", note="Objectives and key results"))
    for index in range(60):
        store.create_term(GlossaryTermCreate(term=f"Term {index:02d}", replacement=f"Replacement {index:02d}"))

    service = GlossaryService(
        Settings(custom_glossary_terms="okr=>Objectives; env-only=>Environment only"),
        store,
    )

    resolved = service.resolve_terms("qwen=>Meeting Qwen; meeting-only=>Meeting only")

    assert len(resolved) == 50
    assert resolved[0].term == "qwen"
    assert resolved[0].replacement == "Meeting Qwen"
    assert resolved[1].term == "meeting-only"
    assert resolved[2].term == "OKR"
    assert all(term.term != "env-only" for term in resolved)
    assert sum(1 for term in resolved if term.term.casefold() == "qwen") == 1
