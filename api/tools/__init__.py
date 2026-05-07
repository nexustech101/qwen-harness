"""api/tools — LangChain @tool implementations.

Tool profiles (named subsets) are defined in api.tools.profiles:
  default       — full coding-agent tool set
  web_research  — web + read-only tools for the frontend-facing agent
"""

from api.tools.file_tools import read_file, write_file, edit_file, file_exists, list_directory
from api.tools.system_tools import get_working_directory, run_command
from api.tools.web_tools import http_get
from api.tools.web_search_tools import (
    web_search,
    fetch_page,
    extract_links,
    get_page_metadata,
    research_topic,
)
from api.tools.analysis_tools import search_in_file, count_lines
from api.tools.code_tools import check_syntax, run_tests, apply_patch
from api.tools.workspace_tools import (
    grep_workspace,
    find_files,
    create_directory,
    move_file,
    delete_file,
    copy_file,
    diff_files,
)
from api.tools.agent_tools import workspace_read, agent_report, agent_read, send_directive, request_help
from api.tools.gmail_tools import check_email, categorize_emails, reply_to_email
from api.tools.graph_tools import (
    graph_refresh,
    graph_summary,
    graph_report,
    graph_stats,
    graph_query,
    graph_shortest_path,
    graph_neighbors,
    graph_community,
    graph_find_symbol,
    graph_symbol_details,
    graph_usages,
)
from api.tools.profiles import (
    DEFAULT_TOOLS,
    WEB_RESEARCH_TOOLS,
    PROFILES,
    get_tools_for_profile,
    profile_summary,
)

# Backward-compat alias — existing code that imports ALL_TOOLS gets the full set
ALL_TOOLS = DEFAULT_TOOLS

__all__ = (
    [t.name for t in ALL_TOOLS]
    + [
        "ALL_TOOLS",
        "DEFAULT_TOOLS",
        "WEB_RESEARCH_TOOLS",
        "PROFILES",
        "get_tools_for_profile",
        "profile_summary",
    ]
)