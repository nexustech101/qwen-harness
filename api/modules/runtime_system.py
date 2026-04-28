"""Runtime utility routes (config, models, and folder browsing)."""

from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, HTTPException

from app import config
from api.schemas.agent import ConfigResponse, OllamaModel

router = APIRouter(tags=["agent-runtime"])


@router.get("/config", response_model=ConfigResponse)
async def get_config():
    return ConfigResponse(
        ollama_host=config.OLLAMA_HOST,
        workspace_home=config.WORKSPACE_HOME,
        workspace_projects_dir=config.WORKSPACE_PROJECTS_DIR,
        workspace_index_file=config.WORKSPACE_INDEX_FILE,
        default_model=config.DEFAULT_MODEL,
        model=config.MODEL,
        planner_model=config.PLANNER_MODEL,
        coder_model=config.CODER_MODEL,
        router_mode=config.ROUTER_MODE,
        context_mode=config.CONTEXT_MODE,
        tool_scope_mode=config.TOOL_SCOPE_MODE,
        max_turns=config.MAX_TURNS,
        max_messages=config.MAX_MESSAGES,
        sub_agent_max_turns=config.SUB_AGENT_MAX_TURNS,
        max_concurrent_agents=config.MAX_CONCURRENT_AGENTS,
    )


@router.get("/models", response_model=list[OllamaModel])
async def list_models():
    try:
        import ollama

        client = ollama.Client(host=config.OLLAMA_HOST)
        response = client.list()
        return [
            OllamaModel(
                name=model.model or "",
                size=int(model.size or 0),
                modified_at=str(model.modified_at or ""),
                family=model.details.family if model.details else None,
                parameter_size=model.details.parameter_size if model.details else None,
                quantization_level=model.details.quantization_level if model.details else None,
            )
            for model in response.models
        ]
    except Exception as exc:
        raise HTTPException(502, f"Failed to fetch models from Ollama: {exc}")


@router.get("/browse-folder")
async def browse_folder():
    result: dict[str, str | None] = {"path": None}

    def _pick() -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            folder = filedialog.askdirectory(title="Select Project Folder")
            root.destroy()
            result["path"] = folder or None
        except Exception:
            result["path"] = None

    picker_thread = threading.Thread(target=_pick, daemon=True)
    picker_thread.start()
    while picker_thread.is_alive():
        await asyncio.sleep(0.05)

    return {"path": result["path"]}
