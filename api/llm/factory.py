"""Multi-provider LLM factory.

Usage::

    from api.llm.factory import create_llm

    llm = create_llm("ollama", model="qwen2.5-coder:7b")
    llm = create_llm("openai", model="gpt-4o")
    llm = create_llm("anthropic", model="claude-3-5-haiku-20241022")
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel


def create_llm(
    provider: str,
    model: str | None = None,
    *,
    temperature: float = 0.0,
    streaming: bool = True,
    **kwargs: Any,
) -> BaseChatModel:
    """Return a LangChain ``BaseChatModel`` for the requested provider.

    Parameters
    ----------
    provider:
        One of ``"ollama"``, ``"openai"``, ``"anthropic"``.
    model:
        Model identifier.  Falls back to the per-provider default in
        ``api.config.config.Settings`` when *None*.
    temperature:
        Sampling temperature (0 = deterministic / greedy).
    streaming:
        Whether to enable streaming (``True`` by default so the streaming
        event loop in ``api.agent.streaming`` works).
    kwargs:
        Extra kwargs forwarded to the underlying client constructor.
    """
    from api.config.config import get_settings

    settings = get_settings()

    match provider:
        case "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=model or settings.default_model,
                base_url=settings.ollama_host,
                temperature=temperature,
                **kwargs,
            )

        case "openai":
            from langchain_openai import ChatOpenAI

            api_key = settings.openai_api_key
            if api_key is None:
                raise ValueError(
                    "AGENT_API_OPENAI_API_KEY is not set — cannot use OpenAI provider."
                )

            return ChatOpenAI(
                model=model or settings.openai_default_model,
                api_key=api_key.get_secret_value(),
                temperature=temperature,
                streaming=streaming,
                **kwargs,
            )

        case "anthropic":
            from langchain_anthropic import ChatAnthropic

            api_key = settings.anthropic_api_key
            if api_key is None:
                raise ValueError(
                    "AGENT_API_ANTHROPIC_API_KEY is not set — cannot use Anthropic provider."
                )

            return ChatAnthropic(
                model=model or settings.anthropic_default_model,
                api_key=api_key.get_secret_value(),
                temperature=temperature,
                streaming=streaming,
                **kwargs,
            )

        case _:
            raise ValueError(
                f"Unknown LLM provider: {provider!r}. "
                "Choose one of: 'ollama', 'openai', 'anthropic'."
            )
