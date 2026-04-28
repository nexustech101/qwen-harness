# Projectless Chat API Notes

## Implemented Support

The frontend now supports starting a chat without choosing a project first. The first prompt creates a runtime session with:

```json
{
  "chat_only": true,
  "title": "First user prompt...",
  "model": "optional-model-name"
}
```

via `POST /api/sessions`. The backend creates the session under an internal workspace directory:

```text
{AGENT_WORKSPACE_HOME}/chat-sessions
```

The normal runtime APIs are then reused:

- `POST /api/sessions/{session_id}/messages`
- `GET /api/sessions`
- `GET /api/sessions/{session_id}/messages`
- `WS /api/sessions/{session_id}/ws`

Authenticated users get persistent chat history through the existing `chat_sessions` and `chat_messages` persistence layer. Guests get in-memory temporary chat sessions.

## Remaining Backend Gaps

These are not required for the current frontend flow, but they would make projectless chat more complete:

- `PATCH /api/sessions/{session_id}` to rename/update a chat title after creation.
- A dedicated conversation endpoint such as `POST /api/conversations` if chat-only sessions should be a separate domain from coding-agent project sessions.
- A no-tools or limited-tools runtime mode for pure LLM conversations, so projectless chat cannot accidentally use filesystem tools in the internal chat workspace.
- Session list metadata for previews, such as `last_message_preview`, `last_message_at`, and `message_count`, so the sidebar can show richer chat history without fetching every message.
- Optional guest local persistence or server-side anonymous conversation IDs if temporary guest chats should survive browser reloads.

## Current Tradeoff

Projectless chat currently reuses the coding-agent runtime and points it at a safe internal workspace. That keeps streaming, auth, billing, and persisted history working with minimal backend surface area, but it is still technically a runtime session rather than a separate pure chat service.
