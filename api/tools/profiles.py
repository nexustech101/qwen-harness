"""
Tool profiles — named subsets of tools scoped to specific agent contexts.

Every profile is a flat list of LangChain @tool instances. The graph nodes
look up the active profile from AgentState so the LLM only sees tools it is
allowed to use.

Profiles
--------
default        — Full tool set: file I/O, shell, web, graph, analysis, email.
                 Intended for the CLI coding agent and server-side automation.

web_research   — Read-only, network-only tool set for the frontend-facing agent:
                 web search, page fetching, graph analysis, workspace read-only
                 query tools. No file writes, no shell execution.
"""

from __future__ import annotations

from typing import Literal

# ── Tool imports ───────────────────────────────────────────────────────────────
# Default (coding agent) tools
from api.tools.file_tools import read_file, write_file, edit_file, file_exists, list_directory
from api.tools.system_tools import get_working_directory, run_command
from api.tools.analysis_tools import search_in_file, count_lines
from api.tools.code_tools import check_syntax, run_tests, apply_patch
from api.tools.workspace_tools import (
    grep_workspace, find_files, create_directory,
    move_file, delete_file, copy_file, diff_files,
)
from api.tools.agent_tools import (
    workspace_read, agent_report, agent_read, send_directive, request_help,
)
from api.tools.gmail_tools import check_email, categorize_emails, reply_to_email
from api.tools.graph_tools import (
    graph_refresh, graph_summary, graph_report, graph_stats, graph_query,
    graph_shortest_path, graph_neighbors, graph_community,
    graph_find_symbol, graph_symbol_details, graph_usages,
)

# Original single-URL fetch (kept for backward compat)
from api.tools.web_tools import http_get

# New web research tools
from api.tools.web_search_tools import (
    web_search,
    fetch_page,
    extract_links,
    get_page_metadata,
    research_topic,
)

# ── Profile definitions ────────────────────────────────────────────────────────

#: Complete tool set — coding/automation agent.
DEFAULT_TOOLS = [
    # Filesystem
    read_file, write_file, edit_file, file_exists, list_directory,
    # Shell
    get_working_directory, run_command,
    # Web (original)
    http_get,
    # Web (research)
    web_search, fetch_page, extract_links, get_page_metadata, research_topic,
    # Analysis
    search_in_file, count_lines,
    # Code
    check_syntax, run_tests, apply_patch,
    # Workspace
    grep_workspace, find_files, create_directory, move_file, delete_file, copy_file, diff_files,
    # Agent comms
    workspace_read, agent_report, agent_read, send_directive, request_help,
    # Graph
    graph_refresh, graph_summary, graph_report, graph_stats, graph_query,
    graph_shortest_path, graph_neighbors, graph_community,
    graph_find_symbol, graph_symbol_details, graph_usages,
    # Email
    check_email, categorize_emails, reply_to_email,
]

#: Web-research / frontend tool set — no filesystem writes, no shell execution.
#: Modelled after the tool permissions used in consumer-facing AI assistants:
#: pure network access + read-only workspace introspection.
WEB_RESEARCH_TOOLS = [
    # ── Web & Research ────────────────────────────────────────────────────────
    web_search,          # ranked web search results
    fetch_page,          # fetch + clean a single URL
    extract_links,       # enumerate links on a page
    get_page_metadata,   # OG / meta tags without full fetch
    research_topic,      # multi-source research brief
    http_get,            # raw HTTP fetch (backward compat / API access)

    # ── Graph intelligence (read-only) ────────────────────────────────────────
    graph_summary,       # codebase overview
    graph_query,         # semantic/structural graph queries
    graph_stats,         # graph metrics
    graph_find_symbol,   # locate a symbol
    graph_symbol_details,# symbol schema + docstring
    graph_usages,        # where a symbol is used

    # ── Workspace read-only ───────────────────────────────────────────────────
    grep_workspace,      # text search across workspace files
    find_files,          # locate files by name/glob

    # ── File read (no write) ──────────────────────────────────────────────────
    read_file,           # read file content
    file_exists,         # check path existence
    list_directory,      # list directory contents

    # ── Static analysis (read-only) ───────────────────────────────────────────
    search_in_file,      # search within a specific file
    count_lines,         # line/word/char count
    check_syntax,        # syntax validation (read-only)

    # ── Agent communication ───────────────────────────────────────────────────
    workspace_read,      # read project/plan/status specs
    agent_report,        # report status to orchestrator

    # ── Email (read + categorise, no send) ───────────────────────────────────
    check_email,
    categorize_emails,
]

# ── Profile registry ───────────────────────────────────────────────────────────

ProfileName = Literal["default", "web_research"]

PROFILES: dict[str, list] = {
    "default": DEFAULT_TOOLS,
    "web_research": WEB_RESEARCH_TOOLS,
}


def get_tools_for_profile(profile: str) -> list:
    """
    Return the tool list for *profile*.

    Falls back to ``DEFAULT_TOOLS`` for unrecognised profile names so callers
    never receive an empty list.
    """
    return PROFILES.get(profile, DEFAULT_TOOLS)


def profile_summary() -> dict[str, list[str]]:
    """Return a {profile_name: [tool_names]} mapping — useful for API introspection."""
    return {name: [t.name for t in tools] for name, tools in PROFILES.items()}
