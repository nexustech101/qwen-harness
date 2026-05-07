"""
MCP tool registrations — wraps api/tools/ implementations for MCP clients.

Each @mcp.tool function delegates to LangChain @tool functions so that both
the REST/WebSocket API and MCP clients share the exact same implementations.
"""

from __future__ import annotations

from api.mcp.server import mcp

from api.tools.file_tools import read_file, write_file, edit_file, list_directory, file_exists
from api.tools.system_tools import run_command, get_working_directory
from api.tools.web_tools import http_get
from api.tools.web_search_tools import (
    web_search as _web_search,
    fetch_page as _fetch_page,
    extract_links as _extract_links,
    get_page_metadata as _get_page_metadata,
    research_topic as _research_topic,
)
from api.tools.analysis_tools import search_in_file, count_lines
from api.tools.workspace_tools import grep_workspace as _grep_ws, find_files as _find_files
from api.tools.code_tools import check_syntax, run_tests, apply_patch


@mcp.tool
def mcp_read_file(path: str, start: int | None = None, end: int | None = None) -> str:
    """Read file content with optional line range."""
    args: dict = {"path": path}
    if start is not None:
        args["start"] = start
    if end is not None:
        args["end"] = end
    return read_file.invoke(args)


@mcp.tool
def mcp_write_file(path: str, content: str, append: bool = False) -> str:
    """Write content to a file, optionally appending."""
    return write_file.invoke({"path": path, "content": content, "append": append})


@mcp.tool
def mcp_edit_file(path: str, old_content: str, new_content: str) -> str:
    """Replace a specific string in a file."""
    return edit_file.invoke({"path": path, "old_content": old_content, "new_content": new_content})


@mcp.tool
def mcp_list_directory(path: str = ".") -> str:
    """List files and directories at the given path."""
    return list_directory.invoke({"path": path})


@mcp.tool
def mcp_file_exists(path: str) -> str:
    """Check whether a path exists."""
    return file_exists.invoke({"path": path})


@mcp.tool
def mcp_run_command(command: str, working_dir: str | None = None, timeout: int = 30) -> str:
    """Execute a shell command and return its output."""
    args: dict = {"command": command, "timeout": timeout}
    if working_dir is not None:
        args["working_dir"] = working_dir
    return run_command.invoke(args)


@mcp.tool
def mcp_get_working_directory() -> str:
    """Return the current working directory."""
    return get_working_directory.invoke({})


@mcp.tool
def mcp_http_get(url: str, max_bytes: int = 200_000) -> str:
    """Fetch the text content of a URL."""
    return http_get.invoke({"url": url, "max_bytes": max_bytes})


@mcp.tool
def mcp_grep_workspace(pattern: str, is_regex: bool = False, include: str | None = None, max_results: int = 100) -> str:
    """Search for a pattern across workspace files."""
    args: dict = {"pattern": pattern, "is_regex": is_regex, "max_results": max_results}
    if include is not None:
        args["include"] = include
    return _grep_ws.invoke(args)


@mcp.tool
def mcp_find_files(pattern: str, path: str = ".") -> str:
    """Find files matching a glob pattern."""
    return _find_files.invoke({"pattern": pattern, "path": path})


@mcp.tool
def mcp_check_syntax(path: str) -> str:
    """Check a Python file for syntax errors."""
    return check_syntax.invoke({"path": path})


@mcp.tool
def mcp_search_in_file(path: str, pattern: str, is_regex: bool = False) -> str:
    """Search for a pattern in a specific file."""
    return search_in_file.invoke({"path": path, "pattern": pattern, "is_regex": is_regex})


# ── Web Research tools (no filesystem access required) ─────────────────────────

@mcp.tool
def mcp_web_search(
    query: str,
    num_results: int = 6,
    recency: str | None = None,
) -> str:
    """
    Search the web and return ranked results with title, URL, and snippet.

    Uses Brave Search API when AGENT_API_BRAVE_SEARCH_KEY is set,
    otherwise falls back to DuckDuckGo (no key required).

    recency: 'd' last day, 'w' last week, 'm' last month, 'y' last year
    """
    args: dict = {"query": query, "num_results": num_results}
    if recency is not None:
        args["recency"] = recency
    return _web_search.invoke(args)


@mcp.tool
def mcp_fetch_page(
    url: str,
    max_chars: int = 8_000,
    include_links: bool = False,
) -> str:
    """
    Fetch a web page and return its content as clean, readable markdown.

    Strips navigation, ads, scripts and boilerplate. Preserves headings,
    paragraphs, code blocks and lists.
    """
    return _fetch_page.invoke({"url": url, "max_chars": max_chars, "include_links": include_links})


@mcp.tool
def mcp_extract_links(
    url: str,
    filter_domain: str | None = None,
    limit: int = 30,
) -> str:
    """
    Extract all hyperlinks from a web page.

    filter_domain: only return links matching this domain (e.g. 'docs.python.org')
    """
    args: dict = {"url": url, "limit": limit}
    if filter_domain is not None:
        args["filter_domain"] = filter_domain
    return _extract_links.invoke(args)


@mcp.tool
def mcp_get_page_metadata(url: str) -> str:
    """
    Return metadata from a web page without downloading its full content.

    Extracts: title, description, Open Graph tags, canonical URL,
    publication date, schema.org type.
    """
    return _get_page_metadata.invoke({"url": url})


@mcp.tool
def mcp_research_topic(
    query: str,
    max_sources: int = 4,
    focus: str | None = None,
    recency: str | None = None,
) -> str:
    """
    Conduct multi-source web research on a topic.

    Searches the web, fetches content from the top sources, and returns a
    structured brief with source content and a citation index.

    focus:   optional sub-topic or angle to narrow the research
    recency: 'd' (day), 'w' (week), 'm' (month), 'y' (year)
    """
    args: dict = {"query": query, "max_sources": max_sources}
    if focus is not None:
        args["focus"] = focus
    if recency is not None:
        args["recency"] = recency
    return _research_topic.invoke(args)