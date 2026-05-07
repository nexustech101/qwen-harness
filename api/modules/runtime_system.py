"""Runtime utility routes (config, models)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.config.config import get_settings
from api.schemas.agent import ConfigResponse, OllamaModel

router = APIRouter(tags=["agent-runtime"])
settings = get_settings()


@router.get("/config", response_model=ConfigResponse)
async def get_config():
    return ConfigResponse(
        ollama_host=settings.ollama_host,
        default_model=settings.default_model,
        llm_provider=settings.llm_provider,
        api_version=settings.api_version,
    )


@router.get("/models", response_model=list[OllamaModel])
async def list_models():
    try:
        import ollama

        client = ollama.Client(host=settings.ollama_host)
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
