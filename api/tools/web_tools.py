"""
Web tools — HTTP fetching for documentation, APIs, and reference material.

Agents need to read documentation, check API responses, and fetch reference
material from the web.
"""

from __future__ import annotations

import re

from urllib.parse import urlparse
from typing import Annotated, Literal

from app import config
from app.core.state import ToolResult
from api.tools.registry import registry

# Domains that are never allowed (internal/private ranges handled separately)
_BLOCKED_SCHEMES = {"file", "ftp", "data", "javascript"}


def _validate_url(url: str) -> str | None:
    """Validate URL, return error message if invalid, None if OK."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL format"

    if parsed.scheme not in ("http", "https"):
        return f"Only http/https URLs allowed, got: {parsed.scheme}"

    if not parsed.hostname:
        return "No hostname in URL"

    # Block private/internal IPs
    hostname = parsed.hostname.lower()
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return "Requests to localhost are not allowed"

    # Block common internal ranges
    if hostname.startswith(("10.", "192.168.", "172.")):
        return "Requests to private IP ranges are not allowed"

    return None


@registry.tool(
    name="http_get",
    category="web",
    description="Fetch content from a URL (documentation, APIs, web pages). Returns text content.",
    idempotent=True,
)
def http_get(
    url: Annotated[str, "The URL to fetch"],
    max_bytes: Annotated[int, "The maximum number of bytes to read"] = 50_000,
    headers: Annotated[dict | None, "Optional headers to include in the request"] = None,
) -> ToolResult:
    try:
        # Validate URL
        error = _validate_url(url)
        if error:
            return ToolResult(success=False, data="", error=error)

        # Use urllib (stdlib) to avoid adding requests dependency
        import urllib.request
        import urllib.error

        max_bytes = min(max_bytes, 200_000)  # Hard cap at 200KB

        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "qwen-coder-agent/1.0")  # Change user agent
        req.add_header("Accept", "text/html,application/json,text/plain,*/*")

        if headers:
            for key, value in headers.items():
                if isinstance(key, str) and isinstance(value, str):
                    req.add_header(key, value)

        with urllib.request.urlopen(req, timeout=15) as response:
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(max_bytes)

        # Try to decode
        encoding = "utf-8"
        # Check for charset in Content-Type
        ct_match = re.search(r"charset=([^\s;]+)", content_type)
        if ct_match:
            encoding = ct_match.group(1)
        # encoding = ct_match.group(1) or "utf-8"

        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            text = raw.decode("utf-8", errors="replace")

        # For HTML, do a basic strip of tags to get readable text
        if "html" in content_type.lower():
            text = _strip_html(text)

        # Truncate
        truncated = len(raw) >= max_bytes
        if len(text) > config.MAX_TOOL_RESULT_CHARS:
            text = text[: config.MAX_TOOL_RESULT_CHARS] + "\n[CONTENT TRUNCATED]"
            truncated = True

        return ToolResult(
            success=True,
            data=text,
            metadata={
                "content_type": content_type,
                "bytes": len(raw),
                "truncated": truncated,
                "url": url,
            },
        )
    except urllib.error.HTTPError as e:
        return ToolResult(
            success=False, data="",
            error=f"HTTP {e.code}: {e.reason}",
        )
    except urllib.error.URLError as e:
        return ToolResult(
            success=False, data="",
            error=f"URL error: {e.reason}",
        )
    except TimeoutError:
        return ToolResult(success=False, data="", error="Request timed out (15s)")
    except Exception as e:
        return ToolResult(success=False, data="", error=f"HTTP error: {e}")


def _strip_html(html: str) -> str:
    """Basic HTML tag stripper — extracts readable text."""
    # Remove script and style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&nbsp;", " ").replace("&#39;", "'")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Put some structure back — split on long runs
    text = re.sub(r" {3,}", "\n", text)
    return text

