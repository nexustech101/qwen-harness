from __future__ import annotations

import importlib
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def _make_client(tmp_path, monkeypatch) -> TestClient:
    db_file = tmp_path / "unified_backend_test.db"
    monkeypatch.setenv("USER_API_DATABASE_URL", f"sqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("USER_API_JWT_SECRET", "test-secret-key-12345")
    monkeypatch.setenv("USER_API_FIREBASE_ENABLED", "false")
    monkeypatch.setenv("USER_API_STRIPE_ENABLED", "false")
    monkeypatch.setenv("USER_API_LOG_JSON", "false")

    import api.config.config as account_config

    account_config.get_settings.cache_clear()

    import api.router as unified_api

    importlib.reload(unified_api)
    return TestClient(unified_api.create_app())


def _register_and_login(client: TestClient, email: str, password: str) -> tuple[int, str]:
    reg = client.post(
        "/api/auth/register",
        json={"email": email, "full_name": email.split("@")[0], "password": password},
    )
    assert reg.status_code == 201
    user_id = reg.json()["id"]

    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    token = login.json()["access_token"]
    return user_id, token


def test_unified_router_registration(tmp_path, monkeypatch):
    with _make_client(tmp_path, monkeypatch) as client:
        paths = {route.path for route in client.app.routes}
        assert "/api/sessions" in paths
        assert "/api/auth/login" in paths
        assert "/api/users" in paths
        assert "/api/billing/subscription" in paths
        assert "/api/ops/meta/version" in paths


def test_guest_session_is_ephemeral_mode(tmp_path, monkeypatch):
    with _make_client(tmp_path, monkeypatch) as client:
        create = client.post("/api/sessions", json={"project_root": str(Path.cwd())})
        assert create.status_code == 201
        body = create.json()
        assert body["persistence_mode"] == "guest"
        assert body["owner_user_id"] is None


def test_chat_only_session_does_not_require_project_root(tmp_path, monkeypatch):
    with _make_client(tmp_path, monkeypatch) as client:
        create = client.post("/api/sessions", json={"chat_only": True, "title": "Hello there"})
        assert create.status_code == 201
        body = create.json()
        assert body["chat_only"] is True
        assert body["title"] == "Hello there"
        assert body["project_name"] == "Hello there"
        assert Path(body["project_root"]).name == "chat-sessions"


def test_authenticated_session_is_persistent_and_owner_scoped(tmp_path, monkeypatch):
    with _make_client(tmp_path, monkeypatch) as client:
        user1_id, token1 = _register_and_login(client, "owner@example.com", "OwnerPass123!")
        _, token2 = _register_and_login(client, "other@example.com", "OtherPass123!")

        create = client.post(
            "/api/sessions",
            json={"project_root": str(Path.cwd())},
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert create.status_code == 201
        payload = create.json()
        session_id = payload["id"]
        assert payload["persistence_mode"] == "persistent"
        assert payload["owner_user_id"] == user1_id

        owner_get = client.get(
            f"/api/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert owner_get.status_code == 200

        other_get = client.get(
            f"/api/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert other_get.status_code == 404


def test_websocket_rejects_invalid_optional_token(tmp_path, monkeypatch):
    with _make_client(tmp_path, monkeypatch) as client:
        create = client.post("/api/sessions", json={"project_root": str(Path.cwd())})
        assert create.status_code == 201
        session_id = create.json()["id"]

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/api/sessions/{session_id}/ws?token=not-a-token"):
                pass

        assert exc_info.value.code == 4401


def test_upload_rejects_file_above_limit(tmp_path, monkeypatch):
    with _make_client(tmp_path, monkeypatch) as client:
        create = client.post("/api/sessions", json={"project_root": str(Path.cwd())})
        assert create.status_code == 201
        session_id = create.json()["id"]

        oversized = io.BytesIO(b"x" * (10 * 1024 * 1024 + 1))
        response = client.post(
            f"/api/sessions/{session_id}/uploads",
            files={"files": ("big.txt", oversized, "text/plain")},
        )

        assert response.status_code == 413


def test_conversation_history_is_modeled_for_owner_and_ops_export(tmp_path, monkeypatch):
    with _make_client(tmp_path, monkeypatch) as client:
        user_id, token = _register_and_login(client, "history@example.com", "HistoryPass123!")
        create = client.post(
            "/api/sessions",
            json={"project_root": str(Path.cwd())},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create.status_code == 201
        session_id = create.json()["id"]

        from api.services.chat_service import append_chat_message
        from api.services.user_service import get_user_by_id

        append_chat_message(session_id, user_id, "user", "Trainable prompt", {"source": "test"})
        append_chat_message(
            session_id,
            user_id,
            "assistant",
            "Trainable answer",
            {"turns": 1, "reason": "done"},
            "main",
        )

        history = client.get(
            f"/api/sessions/{session_id}/history",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert history.status_code == 200
        body = history.json()
        assert body["session"]["id"] == session_id
        assert [item["role"] for item in body["messages"]] == ["user", "assistant"]
        assert body["messages"][0]["metadata"] == {"source": "test"}
        assert {event["event_type"] for event in body["usage_events"]} >= {"conversation.message_created"}

        admin = get_user_by_id(user_id)
        admin.is_admin = True
        admin.save()

        export = client.get(
            "/api/ops/conversation-history",
            headers={"Authorization": f"Bearer {token}"},
            params={"session_id": session_id},
        )
        assert export.status_code == 200
        assert export.json()["items"][0]["session"]["id"] == session_id
