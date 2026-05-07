"""
StreamingParser — moved here from api/services/response_parser.py.

Handles token-by-token classification of LLM output for SSE events:
  - <think>…</think>  → "thinking" kind
  - <tool_response>…</tool_response>  → suppressed
  - everything else → "content" kind

Also provides AnthropicThinkingHandler for Anthropic's native thinking blocks.
"""

from __future__ import annotations

from api.services.response_parser import StreamingParser  # re-export intact

__all__ = ["StreamingParser"]
