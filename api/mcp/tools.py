"""
MCP tool registrations — wraps api/tools/ implementations for MCP clients.

Each `@mcp.tool` function delegates to the tool registry so that both the
REST/WebSocket API and MCP clients share the exact same tool implementations.

Import this module as a side effect after `api.mcp.server` has been imported.
"""

from __future__ import annotations

# Load all tool implementations into the registry (side-effect imports)
import api.tools.file_tools       # noqa: F401
import api.tools.system_tools     # noqa: F401
import api.tools.code_tools       # noqa: F401
import api.tools.analysis_tools   # noqa: F401
import api.tools.workspace_tools  # noqa: F401
import api.tools.web_tools        # noqa: F401
import api.tools.gmail_tools      # noqa: F401

from api.mcp.server import mcp
from api.tools.registry import registry


def _call_tool(name: str, **kwargs: object) -> str:
    """Invoke a registry tool and return its output as a string."""
    result = registry.call(name, kwargs)
    if not result.success:
        raise RuntimeError(result.error or "Tool failed")
    return str(result.data)


# ── File tools ─────────────────────────────────────────────────────────────────

@mcp.tool
def read_file(path: str, start: int | None = None, end: int | None = None) -> str:
    """Read file content with optional line range."""
    return _call_tool("read_file", path=path, start=start, end=end)


@mcp.tool
def write_file(path: str, content: str, append: bool = False) -> str:
    """Write content to a file, optionally appending."""
    return _call_tool("write_file", path=path, content=content, append=append)


@mcp.tool
def edit_file(path: str, old_content: str, new_content: str) -> str:
    """Replace a specific string in a file."""
    return _call_tool("edit_file", path=path, old_content=old_content, new_content=new_content)


@mcp.tool
def list_directory(path: str = ".") -> str:
    """List files and directories at the given path."""
    return _call_tool("list_directory", path=path)


@mcp.tool
def file_exists(path: str) -> str:
    """Check whether a path exists."""
    return _call_tool("file_exists", path=path)


# ── System tools ───────────────────────────────────────────────────────────────

@mcp.tool
def run_command(command: str, working_dir: str | None = None, timeout: int = 30) -> str:
    """Execute a shell command and return its output."""
    return _call_tool("run_command", command=command, working_dir=working_dir, timeout=timeout)


@mcp.tool
def get_working_directory() -> str:
    """Return the current working directory."""
    return _call_tool("get_working_directory")


# ── Code tools ─────────────────────────────────────────────────────────────────

@mcp.tool
def grep_workspace(pattern: str, path: str = ".", include: str | None = None) -> str:
    """Search for a regex pattern across workspace files."""
    return _call_tool("grep_workspace", pattern=pattern, path=path, include=include)


@mcp.tool
def find_files(pattern: str, path: str = ".") -> str:
    """Find files matching a glob pattern."""
    return _call_tool("find_files", pattern=pattern, path=path)


# ── Web tools ──────────────────────────────────────────────────────────────────

@mcp.tool
def fetch_url(url: str) -> str:
    """Fetch the text content of a URL."""
    return _call_tool("fetch_url", url=url)


# ── Gmail tools ────────────────────────────────────────────────────────────────

@mcp.tool
def check_email(
    max_results: int = 10,
    query: str = "",
    include_body: bool = True,
) -> str:
    """Fetch emails from the Gmail inbox and return a JSON array.

    Each item contains: id, thread_id, subject, from, to, cc, date, snippet, body, labels.

    Args:
        max_results: Number of emails to return (1-50).
        query: Gmail search query, e.g. 'is:unread' or 'from:alice@example.com'.
        include_body: When False, skips the full body fetch for faster results.
    """
    return _call_tool("check_email", max_results=max_results, query=query, include_body=include_body)


@mcp.tool
def categorize_emails(max_results: int = 50, query: str = "") -> str:
    """Fetch emails and group them by Gmail category.

    Returns a JSON object mapping each category name (personal, social, promotions,
    updates, forums, inbox, etc.) to a list of email summaries.

    Args:
        max_results: Total emails to fetch and categorize (1-100).
        query: Optional Gmail search query to narrow the set of emails.
    """
    return _call_tool("categorize_emails", max_results=max_results, query=query)


@mcp.tool
def reply_to_email(message_id: str, body: str) -> str:
    """Send a plain-text reply to an existing Gmail message.

    The reply is correctly threaded via In-Reply-To / References headers.
    Returns JSON with the sent message's id and thread_id.

    Args:
        message_id: The Gmail message ID to reply to (from the 'id' field of check_email).
        body: Plain-text content of the reply.
    """
    return _call_tool("reply_to_email", message_id=message_id, body=body)
