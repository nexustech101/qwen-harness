"""System routes — health, config, and Ollama model listing."""

from __future__ import annotations

import ollama
from fastapi import APIRouter, HTTPException

from api.config.config import get_settings

router = APIRouter(tags=["system"])
settings = get_settings()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": settings.api_version}


@router.get("/config")
async def get_config() -> dict:
    return {
        "app_name": settings.app_name,
        "api_version": settings.api_version,
        "ollama_host": settings.ollama_host,
        "default_model": settings.default_model,
        "mcp_server_name": settings.mcp_server_name,
        "llm_provider": settings.llm_provider,
    }


@router.get("/models")
async def list_models() -> list[dict]:
    try:
        client = ollama.Client(host=settings.ollama_host)
        response = client.list()
        return [
            {
                "name": m.model or "",
                "size": int(m.size or 0),
                "modified_at": str(m.modified_at or ""),
                "family": m.details.family if m.details else None,
                "parameter_size": m.details.parameter_size if m.details else None,
                "quantization_level": m.details.quantization_level if m.details else None,
            }
            for m in response.models
        ]
    except Exception as exc:
        raise HTTPException(502, f"Ollama unavailable: {exc}")
