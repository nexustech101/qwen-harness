"""Small context window manager over the project graph."""

from __future__ import annotations

from graph.query import ProjectGraphQuery
from graph.store import GraphStore


class GraphContextManager:
    def __init__(self, store: GraphStore) -> None:
        self.store = store
        self.graph = store.load_or_refresh()
        self.query = ProjectGraphQuery(self.graph)

    def load(self, query: str, limit: int = 5) -> dict:
        state = self.store.read_context_state()
        loaded: list[str] = list(state.get("loaded", []))
        symbol_ids = self._match_symbol_ids(query, limit)
        for symbol_id in symbol_ids:
            if symbol_id not in loaded:
                loaded.append(symbol_id)
        state["loaded"] = loaded
        self.store.write_context_state(state)
        return self.budget_summary()

    def evict(self, symbol_id_or_query: str = "") -> dict:
        state = self.store.read_context_state()
        if not symbol_id_or_query:
            state["loaded"] = []
        else:
            remove_ids = set(self._match_symbol_ids(symbol_id_or_query, 50))
            state["loaded"] = [sid for sid in state.get("loaded", []) if sid not in remove_ids and sid != symbol_id_or_query]
        self.store.write_context_state(state)
        return self.budget_summary()

    def budget_summary(self) -> dict:
        state = self.store.read_context_state()
        rendered = self.prompt_context()
        used = _estimate_tokens(rendered)
        budget = int(state.get("budget_tokens", 1200))
        return {
            "budget_tokens": budget,
            "used_tokens": used,
            "free_tokens": max(budget - used, 0),
            "loaded_count": len(state.get("loaded", [])),
            "loaded": list(state.get("loaded", [])),
        }

    def prompt_context(self) -> str:
        state = self.store.read_context_state()
        sections = []
        for symbol_id in state.get("loaded", []):
            details = self.query.symbol_details(symbol_id)
            if not details:
                continue
            sections.append(_render_symbol(details))
        return "\n\n".join(sections) if sections else "(no graph context loaded)"

    def _match_symbol_ids(self, query: str, limit: int) -> list[str]:
        if query in self.graph.symbols:
            return [query]
        return [item["symbol_id"] for item in self.query.find_symbol(query, limit=limit)]


def _render_symbol(details: dict) -> str:
    lines = [
        f"### {details['symbol_id']}",
        f"- kind: {details['kind']}",
        f"- location: {details['path']}:{details['line']}",
    ]
    if details.get("signature"):
        lines.append(f"- signature: {details['signature']}")
    if details.get("doc_summary"):
        lines.append(f"- doc: {details['doc_summary']}")
    if details.get("callers"):
        callers = ", ".join(item["symbol_id"] for item in details["callers"][:5])
        lines.append(f"- callers: {callers}")
    if details.get("callees"):
        callees = ", ".join(item["symbol_id"] for item in details["callees"][:5])
        lines.append(f"- callees: {callees}")
    return "\n".join(lines)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0

