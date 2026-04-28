"""Request/response contracts for agent runtime endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    project_root: str | None = None
    title: str | None = None
    chat_only: bool = False
    model: str | None = None
    planner_model: str | None = None
    coder_model: str | None = None
    max_turns: int | None = None
    use_dispatch: bool = False
    async_dispatch: bool = False


class SendPromptRequest(BaseModel):
    prompt: str
    direct: bool = False
    attachments: list[str] = Field(default_factory=list)


class SessionStats(BaseModel):
    total_turns: int = 0
    total_tool_calls: int = 0
    elapsed_seconds: float = 0.0
    files_modified: list[str] = Field(default_factory=list)
    message_count: int = 0


class AgentSummary(BaseModel):
    name: str
    status: str
    model: str
    turns_used: int = 0
    max_turns: int = 0
    goal: str = ""


class SessionResponse(BaseModel):
    id: str
    project_root: str
    project_name: str
    title: str | None = None
    chat_only: bool = False
    workspace_key: str
    workspace_root: str
    persistence_mode: str = "guest"
    owner_user_id: int | None = None
    status: str
    model: str
    created_at: float
    stats: SessionStats
    agents: list[AgentSummary] = Field(default_factory=list)


class MessageResponse(BaseModel):
    role: str
    content: str
    timestamp: float | None = None
    metadata: dict[str, Any] | None = None


class AgentDetailResponse(AgentSummary):
    messages: list[MessageResponse] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)


class PromptAccepted(BaseModel):
    status: str = "running"
    session_id: str


class FileTreeEntry(BaseModel):
    name: str
    path: str
    type: str
    size: int | None = None
    children: list["FileTreeEntry"] | None = None


class FileContentResponse(BaseModel):
    path: str
    content: str
    size: int
    lines: int


class ConfigResponse(BaseModel):
    ollama_host: str
    workspace_home: str
    workspace_projects_dir: str
    workspace_index_file: str
    default_model: str
    model: str
    planner_model: str
    coder_model: str
    router_mode: str
    context_mode: str
    tool_scope_mode: str
    max_turns: int
    max_messages: int
    sub_agent_max_turns: int
    max_concurrent_agents: int


class UploadMeta(BaseModel):
    id: str
    filename: str
    mime_type: str
    size: int
    url: str
    thumbnail_url: str | None = None


class UploadResponse(BaseModel):
    uploads: list[UploadMeta]


class OllamaModel(BaseModel):
    name: str
    size: int
    modified_at: str
    family: str | None = None
    parameter_size: str | None = None
    quantization_level: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str = "Qwen Coder API"
    time: str | None = None
    ip: str | None = None
    request_id: str | None = None
    ollama_connected: bool
    version: str = "1.0.0"
