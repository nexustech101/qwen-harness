# Chat Response Contract Recommendation

## Current Shapes

Persisted messages currently return:

```json
{
  "role": "assistant",
  "content": "Markdown or raw model/parser text",
  "timestamp": 1714065605.13,
  "metadata": {
    "turns": 1,
    "reason": "done",
    "tool_calls_made": 0,
    "files_modified": [],
    "elapsed_seconds": 1.2
  }
}
```

Live WebSocket events include raw stream and parsed events:

```json
{ "type": "content_delta", "agent": "main", "data": { "text": "..." }, "timestamp": 1714065605.13 }
{ "type": "thinking_delta", "agent": "main", "data": { "text": "..." }, "timestamp": 1714065605.13 }
{ "type": "response_text", "agent": "main", "data": { "text": "..." }, "timestamp": 1714065605.13 }
```

The parser currently accepts native tool calls, structured JSON, legacy JSON tool calls, arrays, and plain text. For structured JSON, final display text is expected in `response`.

## Frontend Cleanup Added

The frontend now strips `<think>...</think>` blocks from displayed assistant content, unwraps fenced JSON when it contains a structured parser payload, and renders the `response` field as Markdown. Reasoning remains collapsible.

## Recommended Backend Contract

For a cleaner long-term frontend contract, return explicit display parts instead of only raw `content`:

```json
{
  "role": "assistant",
  "content": "Human-readable Markdown answer only",
  "timestamp": 1714065605.13,
  "metadata": {
    "turns": 1,
    "reason": "done",
    "tool_calls_made": 0,
    "files_modified": [],
    "elapsed_seconds": 1.2
  },
  "display": {
    "format": "markdown",
    "text": "Human-readable Markdown answer only",
    "reasoning": "Optional hidden reasoning/trace summary",
    "parser_mode": "plain|structured|native|legacy|array",
    "status": "completed|in-progress|blocked|error"
  }
}
```

For WebSocket events, prefer:

```json
{
  "type": "assistant_delta",
  "agent": "main",
  "data": {
    "channel": "answer",
    "format": "markdown",
    "text": "delta text"
  },
  "timestamp": 1714065605.13
}
```

and:

```json
{
  "type": "assistant_message",
  "agent": "main",
  "data": {
    "format": "markdown",
    "text": "final answer",
    "metadata": {}
  },
  "timestamp": 1714065605.13
}
```

This would let the frontend avoid guessing whether `content` is raw JSON, tool-call JSON, reasoning, or display Markdown.
