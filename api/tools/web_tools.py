"""
Web tools — HTTP fetching for documentation, APIs, and reference material.
"""

from __future__ import annotations

import re

from urllib.parse import urlparse
from typing import Annotated

from langchain_core.tools import tool

MAX_TOOL_RESULT_CHARS = 50_000

_BLOCKED_SCHEMES = {"file", "ftp", "data", "javascript"}


def _validate_url(url: str) -> str | None:
    """Return an error message if the URL is invalid, else None."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL format"
    if parsed.scheme not in ("http", "https"):
        return f"Only http/https URLs allowed, got: {parsed.scheme}"
    if not parsed.hostname:
        return "No hostname in URL"
    hostname = parsed.hostname.lower()
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return "Requests to localhost are not allowed"
    if hostname.startswith(("10.", "192.168.", "172.")):
        return "Requests to private IP ranges are not allowed"
    return None


@tool
def http_get(
    url: Annotated[str, "URL to fetch"],
    max_bytes: Annotated[int, "Maximum bytes to read (hard cap: 200000)"] = 50_000,
    headers: Annotated[dict | None, "Optional HTTP headers"] = None,
) -> str:
    """Fetch content from a URL (documentation, APIs, web pages). Returns text content."""
    import urllib.request
    import urllib.error

    error = _validate_url(url)
    if error:
        return f"ERROR: {error}"
    try:
        max_bytes = min(max_bytes, 200_000)
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "agent-mcp/3.0")
        req.add_header("Accept", "text/html,application/json,text/plain,*/*")
        if headers:
            for key, value in headers.items():
                if isinstance(key, str) and isinstance(value, str):
                    req.add_header(key, value)
        with urllib.request.urlopen(req, timeout=15) as response:
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(max_bytes)
        encoding = "utf-8"
        ct_match = re.search(r"charset=([^\s;]+)", content_type)
        if ct_match:
            encoding = ct_match.group(1)
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            text = raw.decode("utf-8", errors="replace")
        if "html" in content_type.lower():
            text = _strip_html(text)
        if len(text) > MAX_TOOL_RESULT_CHARS:
            text = text[:MAX_TOOL_RESULT_CHARS] + "\n[CONTENT TRUNCATED]"
        return text
    except urllib.error.HTTPError as exc:
        return f"ERROR: HTTP {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return f"ERROR: URL error: {exc.reason}"
    except TimeoutError:
        return "ERROR: Request timed out (15s)"
    except Exception as exc:
        return f"ERROR: {exc}"


def _strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&nbsp;", " ").replace("&#39;", "'")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r" {3,}", "\n", text)
    return text