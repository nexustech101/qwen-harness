# Unified API Reference

This document is contract-first for the unified backend at `app/account_api`.

All HTTP routes are rooted at `/api`.
All WebSocket routes are rooted at `/api`.

## 1. Purpose-Based Route Map

- Runtime and orchestration: health, model/config introspection, sessions, messages, agents, uploads, file browsing, websocket streaming.
- Identity and access: register, login, refresh, logout, me, password change.
- User management: admin list and deactivate, self/admin profile read and patch.
- Billing (user): subscription, checkout, portal, webhook.
- Operations (admin): audit events, schema/version metadata, billing operations.

## 2. Global Conventions

- Content type: `application/json` unless noted.
- Auth: `Authorization: Bearer <access_token>`.
- Correlation: `X-Request-ID` is accepted; response includes `X-Request-ID`.
- Time format: ISO-8601 UTC strings for account/billing/ops models.
- Runtime timestamps: `created_at` in runtime session responses is Unix seconds (`float`).
- Default error shape:

```json
{
  "detail": "Human-readable error message"
}
```

## 3. Auth and Session Modes

The runtime API supports two modes.

- Guest mode: no auth token. Sessions exist in memory only and do not survive process restart.
- Persistent mode: valid access token. Session and message history are persisted to database and scoped to the authenticated user.

Important behavior:

- Optional-auth runtime endpoints treat missing token as guest.
- Invalid token on optional-auth runtime endpoints returns `401`.
- Invalid token on optional-auth WebSocket connections closes with code `4401`.
- Persistent session ownership violations return `404` (`Session not found`).

## 4. Core Response Objects

### 4.1 UserPublic

```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "User Example",
  "is_active": true,
  "is_admin": false,
  "created_at": "2026-04-24T12:00:00+00:00",
  "updated_at": "2026-04-24T12:00:00+00:00",
  "last_login_at": "2026-04-24T12:30:00+00:00"
}
```

### 4.2 TokenPair

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 900
}
```

### 4.3 SessionResponse (runtime)

```json
{
  "id": "c4f7f94b-0d2f-4ff2-b42f-a4f3eb9d3382",
  "project_root": "C:/repo",
  "project_name": "repo",
  "title": null,
  "chat_only": false,
  "workspace_key": "repo-abc123",
  "workspace_root": "C:/Users/charl/.qwen-coder/workspaces/repo-abc123",
  "persistence_mode": "guest",
  "owner_user_id": null,
  "status": "idle",
  "model": "qwen2.5-coder:7b",
  "created_at": 1714065600.23,
  "stats": {
    "total_turns": 0,
    "total_tool_calls": 0,
    "elapsed_seconds": 0.0,
    "files_modified": [],
    "message_count": 0
  },
  "agents": []
}
```

### 4.4 BillingSubscriptionPublic

```json
{
  "user_id": 123,
  "stripe_customer_id": "cus_...",
  "stripe_subscription_id": "sub_...",
  "subscription_status": "active",
  "price_id": "price_...",
  "current_period_end": "2031-01-01T00:00:00+00:00",
  "cancel_at_period_end": false,
  "has_access": true,
  "updated_at": "2030-12-01T00:00:00+00:00"
}
```

## 5. Runtime and Chat Endpoints

### 5.1 System Runtime

#### `GET /api/health`

Response `200`:

```json
{
  "status": "ok",
  "service": "Qwen Coder API",
  "time": "2026-04-24T12:00:00+00:00",
  "ip": "127.0.0.1",
  "request_id": "req-123",
  "ollama_connected": true,
  "version": "1.0.0"
}
```

#### `GET /api/config`

Returns runtime config used by frontend and tooling:

- `ollama_host`, `default_model`, `model`, `planner_model`, `coder_model`
- `router_mode`, `context_mode`, `tool_scope_mode`
- workspace path fields
- turn and concurrency limits

#### `GET /api/models`

Returns available Ollama models.

#### `GET /api/browse-folder`

Opens a native folder picker (desktop environment). Returns:

```json
{ "path": "C:/selected/project" }
```

or

```json
{ "path": null }
```

### 5.2 Sessions

#### `POST /api/sessions`

Auth: optional.

Request:

```json
{
  "project_root": "C:/repo",
  "title": null,
  "chat_only": false,
  "model": "qwen2.5-coder:7b",
  "planner_model": null,
  "coder_model": null,
  "max_turns": null,
  "use_dispatch": false,
  "async_dispatch": false
}
```

Response:

- `201`: `SessionResponse`
- `400`: invalid `project_root`

Projectless chat behavior:

- `project_root` may be omitted when `chat_only` is `true`.
- Chat-only sessions use an internal workspace root and are returned with `chat_only: true`.
- Authenticated chat-only sessions persist like other sessions; guest chat-only sessions are temporary.

#### `GET /api/sessions`

Auth: optional.

Behavior:

- authenticated: returns caller-owned persistent sessions (hydrated from DB) and active in-memory sessions for that user.
- guest: returns in-memory guest sessions only.

Response:

- `200`: `SessionResponse[]`

#### `GET /api/sessions/{session_id}`

Auth: optional with ownership enforcement for persistent sessions.

Response:

- `200`: `SessionResponse`
- `404`: not found or not owned

#### `DELETE /api/sessions/{session_id}`

Auth: optional with ownership enforcement for persistent sessions.

Response:

- `200`: `{ "status": "deleted" }`
- `404`: not found or not owned

### 5.3 Messages and Agent Execution

#### `POST /api/sessions/{session_id}/messages`

Auth: optional with ownership enforcement for persistent sessions.

Request:

```json
{
  "prompt": "Implement feature X",
  "direct": false,
  "attachments": ["upload_id_1", "upload_id_2"]
}
```

Response:

- `200`: `{ "status": "running", "session_id": "..." }`
- `400`: missing/expired attachment
- `404`: session not found
- `409`: session already running

#### `GET /api/sessions/{session_id}/messages`

Response:

- `200`: `MessageResponse[]`
- `404`: session not found or not owned

#### `GET /api/sessions/{session_id}/history`

Auth required.

Returns the persisted conversation history envelope for one authenticated session:

- session metadata from `chat_sessions`
- ordered message records from `chat_messages`
- observability events from `llm_usage_events`

Response:

- `200`: `ConversationHistoryResponse`
- `401`: missing/invalid token
- `404`: session not found or not owned

#### `GET /api/sessions/{session_id}/agents`

Response:

- `200`: `AgentSummary[]`

#### `GET /api/sessions/{session_id}/agents/{agent_name}`

Response:

- `200`: `AgentDetailResponse`
- `404`: session or agent not found

#### `POST /api/sessions/{session_id}/agents/{agent_name}/prompt`

Request body:

```json
{
  "prompt": "Continue with integration tests"
}
```

Response:

- `200`: `{ "status": "running", "session_id": "..." }`
- `404`: session/agent not found
- `409`: session already running

### 5.4 Uploads and File Inspection

#### `POST /api/sessions/{session_id}/uploads`

Content type: `multipart/form-data` (`files[]`).

Limits:

- max files/request: 10
- max file size: 10 MB
- max total/request: 50 MB

Response:

- `201`: `UploadResponse`
- `400`: invalid MIME/extension
- `404`: session not found
- `413`: size limit exceeded

#### `GET /api/sessions/{session_id}/uploads/{upload_id}`

Response:

- `200`: file stream
- `403`: symlink blocked
- `404`: not found

#### `GET /api/sessions/{session_id}/uploads/{upload_id}/thumbnail`

Response:

- `200`: PNG thumbnail for image uploads
- `204`: upload is not an image
- `404`: not found
- `500`: thumbnail generation failed

#### `DELETE /api/sessions/{session_id}/uploads/{upload_id}`

Response:

- `200`: `{ "status": "deleted" }`

#### `GET /api/sessions/{session_id}/files`

Response:

- `200`: file tree entries

#### `GET /api/sessions/{session_id}/files/{file_path:path}`

Response:

- `200`: `{ path, content, size, lines }`
- `403`: path outside project root
- `404`: file/session not found

### 5.5 WebSocket Runtime Stream

#### `WS /api/sessions/{session_id}/ws`

Auth:

- optional `Authorization: Bearer <token>` header, or
- optional `?token=<access_token>` query param.

Connection behavior:

- if token is present but invalid: closes with code `4401`.
- if session not found/owned: closes with code `4004`.
- sends `connected` event on open.
- sends periodic `ping` when idle.

Client command:

- send `{ "type": "cancel", "session_id": "..." }` to cancel active run.

Event envelope:

```json
{
  "type": "tool_result",
  "agent": "main",
  "data": {},
  "timestamp": 1714065605.13
}
```

## 6. Identity and Access Endpoints

### 6.1 Auth

#### `POST /api/auth/register`

Request:

```json
{
  "email": "user@example.com",
  "full_name": "User Example",
  "password": "StrongPass123!"
}
```

Response:

- `201`: `UserPublic`
- `409`: duplicate email
- `422`: validation failure

#### `POST /api/auth/login`

Request:

```json
{
  "email": "user@example.com",
  "password": "StrongPass123!"
}
```

Response:

- `200`: `TokenPair`
- `401`: invalid credentials

#### `POST /api/auth/firebase/exchange`

Request:

```json
{
  "id_token": "<firebase_id_token>",
  "create_if_missing": true
}
```

Response:

- `200`: `{ user, access_token, refresh_token, token_type, expires_in }`

#### `POST /api/auth/refresh`

Request:

```json
{ "refresh_token": "<jwt>" }
```

Response:

- `200`: `TokenPair`
- `401`: invalid/expired/revoked refresh token

#### `POST /api/auth/logout`

Auth required.

Request:

```json
{ "refresh_token": "<jwt or null>" }
```

Behavior:

- refresh token present: revoke that session only.
- refresh token null: revoke all sessions for current user.

Response:

- `204`: no content

#### `GET /api/auth/me`

Auth required.

Response:

- `200`: `UserPublic`

#### `POST /api/auth/change-password`

Auth required.

Request:

```json
{
  "current_password": "OldPass123!",
  "new_password": "NewStrongPass123!"
}
```

Response:

- `204`: no content
- `400`: current password incorrect

### 6.2 User Management

#### `GET /api/users`

Auth: admin required.

Query:

- `limit` (1..100, default `25`)
- `offset` (>=0, default `0`)
- `is_active` (optional)

Response:

- `200`: `UserPage`

#### `GET /api/users/{user_id}`

Auth: user required.

Access rules:

- admin can read any user.
- non-admin can read only self.

Response:

- `200`: `UserPublic`
- `403`: access denied

#### `PATCH /api/users/{user_id}`

Auth: user required.

Request (`UserUpdate`, all optional):

```json
{
  "full_name": "Updated Name",
  "is_active": true,
  "is_admin": false
}
```

Access rules:

- admin can patch any user and can set `is_active` / `is_admin`.
- non-admin can patch only self and cannot set `is_active` / `is_admin`.

Response:

- `200`: `UserPublic`
- `403`: access denied or forbidden field mutation

#### `DELETE /api/users/{user_id}`

Auth: admin required.

Behavior:

- deactivates user.
- revokes all refresh sessions.

Response:

- `204`: no content

## 7. Billing Endpoints

### 7.1 User Billing Scope

#### `GET /api/billing/subscription`

Auth required.

Response:

- `200`: `BillingSubscriptionPublic`
- `404`: no billing account

#### `POST /api/billing/checkout-session`

Auth required.

Request body object is required; `price_id` is optional:

```json
{ "price_id": "price_optional_override" }
```

Response:

- `201`: `BillingCheckoutResponse`
- `502`: provider failure
- `503`: billing disabled/misconfigured

#### `POST /api/billing/portal-session`

Auth required.

Request body: none.

Response:

- `200`: `BillingPortalResponse`
- `502`: provider failure
- `503`: billing disabled/misconfigured

#### `POST /api/billing/webhook`

Auth: none (provider endpoint).

Headers:

- `Stripe-Signature` required for signed verification.

Body:

- raw provider event payload.

Response:

- `204`: accepted
- `400`: webhook/signature payload error
- `502`: provider failure
- `503`: billing disabled/misconfigured

### 7.2 Admin Billing Ops

#### `GET /api/ops/billing/accounts`

Auth: admin required.

Query:

- `limit` (1..200, default `50`)
- `offset` (>=0, default `0`)
- `user_id`, `stripe_customer_id`, `stripe_subscription_id`, `subscription_status`, `price_id`, `cancel_at_period_end` (all optional)

Response:

- `200`: `BillingSubscriptionPage`

#### `GET /api/ops/billing/users/{user_id}/subscription`

Response:

- `200`: `BillingSubscriptionPublic`
- `404`: no billing account

#### `POST /api/ops/billing/users/{user_id}/checkout-session`

Request body optional:

```json
{ "price_id": "price_optional_override" }
```

Response:

- `201`: `BillingCheckoutResponse`
- `502`: provider failure
- `503`: disabled/misconfigured

#### `POST /api/ops/billing/users/{user_id}/portal-session`

Response:

- `200`: `BillingPortalResponse`
- `502`: provider failure
- `503`: disabled/misconfigured

#### `POST /api/ops/billing/users/{user_id}/sync`

Response:

- `200`: `BillingSubscriptionPublic`
- `502`: provider failure
- `503`: disabled/misconfigured

## 8. Operations Endpoints

### `GET /api/ops/audit-events`

Auth: admin required.

Query:

- `limit` (1..200, default `50`)
- `offset` (>=0, default `0`)
- `action`, `email`, `success`, `user_id`, `created_after`, `created_before` (optional)

Response:

- `200`: `AuthEventPage`

### `GET /api/ops/conversation-history`

Auth: admin required.

Exports persisted conversation histories for analytics, evaluation, and model-improvement workflows.

Query:

- `limit` (1..100, default `25`)
- `offset` (>=0, default `0`)
- `user_id`, `session_id`, `status`, `model`, `project_name`, `created_after`, `created_before` (optional)

Response:

- `200`: `ConversationHistoryPage`

### `GET /api/ops/meta/migrations`

Auth: admin required.

Response:

- `200`: `MigrationMetadataResponse`

### `GET /api/ops/meta/version`

Auth: admin required.

Response:

- `200`: `VersionMetadataResponse`

## 9. Error and Status Mapping

Common statuses used across domains:

- `400`: malformed request or domain condition failure.
- `401`: missing/invalid token.
- `403`: forbidden role or field mutation.
- `404`: record not found or ownership mismatch.
- `409`: uniqueness conflict or duplicate condition.
- `413`: upload size limits exceeded.
- `422`: validation/query contract failure.
- `429`: rate limit exceeded.
- `500`: internal processing error.
- `502`: upstream billing provider failure.
- `503`: billing/integration disabled or misconfigured.

## 10. Persistence Model

Shared database stores all persistent domains:

- users
- refresh sessions
- auth events
- billing accounts
- schema migration records
- persistent chat sessions
- persistent chat messages
- llm usage events

Guest sessions are intentionally ephemeral and never written to DB.

## 11. Conversation Data Model

Persistent authenticated runtime sessions are stored as normalized rows and exported through typed API schemas.

### 11.1 Database Tables

#### `chat_sessions`

One row per authenticated/persistent runtime session.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string | Public session UUID. Primary key. |
| `user_id` | integer | Owner. Indexed foreign key to `users.id`. |
| `project_root` | string | Absolute project root selected by the user. |
| `project_name` | string/null | Display/project grouping name. |
| `workspace_key` | string/null | Indexed workspace identifier. |
| `workspace_root` | string/null | Backend workspace path. |
| `model` | string | Runtime model selected for the session. |
| `status` | string | `idle`, `running`, `error`, `cancelled`, etc. |
| `created_at` | ISO-8601 string | Session creation time. |
| `updated_at` | ISO-8601 string | Last metadata/status update. |
| `last_activity_at` | ISO-8601 string | Last message/status activity. |

#### `chat_messages`

One row per persisted conversation message.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer | Autoincrement primary key. |
| `session_id` | string | Indexed foreign key to `chat_sessions.id`. |
| `user_id` | integer/null | Indexed owner for retrieval and export. |
| `role` | string | `user`, `assistant`, `error`, or future role values. |
| `content` | string | Full message text. |
| `agent_name` | string/null | Agent attribution, usually `main` for assistant messages. |
| `metadata` | JSON/null | Structured turn metadata such as reason, turns, tool counts, files modified. |
| `created_at` | ISO-8601 string | Message creation time. |

#### `llm_usage_events`

Append-only observability stream for conversation and runtime events.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer | Autoincrement primary key. |
| `session_id` | string/null | Indexed session reference. |
| `user_id` | integer/null | Indexed user reference. |
| `event_type` | string | Indexed event name, e.g. `conversation.message_created`. |
| `payload` | JSON/null | Structured event payload. |
| `created_at` | ISO-8601 string | Event creation time. |

Current conversation event types:

- `conversation.message_created`
- `conversation.run_started`
- `conversation.run_completed`
- `conversation.run_cancelled`
- `conversation.run_failed`

### 11.2 API Export Shape

`ConversationHistoryResponse`:

```json
{
  "session": {
    "id": "session-uuid",
    "user_id": 123,
    "project_root": "C:/repo",
    "project_name": "repo",
    "workspace_key": "repo-abc123",
    "workspace_root": "C:/Users/charl/.qwen-coder/workspaces/repo-abc123",
    "model": "qwen2.5-coder:7b",
    "status": "idle",
    "created_at": "2026-04-24T12:00:00+00:00",
    "updated_at": "2026-04-24T12:01:00+00:00",
    "last_activity_at": "2026-04-24T12:01:00+00:00"
  },
  "messages": [
    {
      "id": 1,
      "session_id": "session-uuid",
      "user_id": 123,
      "role": "user",
      "content": "Implement feature X",
      "agent_name": null,
      "metadata": {},
      "content_length": 19,
      "created_at": "2026-04-24T12:00:10+00:00"
    }
  ],
  "usage_events": [
    {
      "id": 10,
      "session_id": "session-uuid",
      "user_id": 123,
      "event_type": "conversation.message_created",
      "payload": {
        "message_id": 1,
        "role": "user",
        "content_length": 19
      },
      "created_at": "2026-04-24T12:00:10+00:00"
    }
  ]
}
```

Analytics guidance:

- Join `chat_sessions.id` to `chat_messages.session_id` and `llm_usage_events.session_id`.
- Use `chat_messages.id` ordering for deterministic conversation reconstruction.
- Use `metadata` and `payload` as structured JSON fields during export; keep raw `content` separate for privacy review and training-data filtering.
- Prefer `/api/ops/conversation-history` for admin/data-science exports because it returns normalized session, message, and observability records together.

## 12. Adding Backend Features

The backend is organized by domain. Add new API features by adding narrow files in the matching layer instead of expanding existing route or manager modules.

Recommended flow:

1. Define request/response contracts in `app/schemas/<domain>.py`.
2. Put database models in `app/db/models.py` only when the feature needs persistence; add a migration record in the same file.
3. Put business logic in `app/services/<domain>_service.py`. Services should own domain decisions and raise domain-specific exceptions.
4. Put HTTP routes in `app/api/routes/<domain>.py`. Routes should stay thin: validate transport details, call services through `run_db` for synchronous database work, map domain errors, and return schemas.
5. Register the router in `app/api/routes/__init__.py`.
6. Put provider SDK calls in `app/integrations/<provider>.py`; keep Stripe, Firebase, model providers, and other external systems out of route handlers.
7. Add focused tests under `tests/unit/api/` for route contract, auth/ownership behavior, and error mapping.
8. Update this API reference whenever a route, request body, response body, auth rule, close code, or status mapping changes.

Runtime feature boundaries:

- Session lifecycle and in-memory session lookup live in `app/api/session_manager.py`.
- Long-running agent execution is isolated in `app/api/runtime_executor.py`.
- Persistent chat/session storage calls are wrapped by `app/api/runtime_persistence.py`.
- Upload validation and streaming staging live in `app/api/uploads.py`.
- File browsing helpers live in `app/api/routes/runtime_common.py`.

Design rules for downstream agents:

- Do not add large new behavior to `session_manager.py`; create a small module and call it from the route or session object.
- Do not call synchronous database or filesystem-heavy work directly from async routes; use `run_db`.
- Keep optional-auth behavior consistent: missing token means guest where documented, invalid token is rejected.
- Avoid string-based exception mapping. Import domain exception classes and centralize API status mapping.
- Prefer bounded streaming for request bodies and bounded traversal for filesystem APIs.
