"""Capture Ollama model output formats for parser fixture generation.

Usage:
    python -m app.scripts.capture_model_formats --models qwen2.5-coder:7b
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ollama import Client

from agent import config


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "echo_tool",
            "description": "Echo a message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "second_tool",
            "description": "Secondary tool for multi-tool tests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {"type": "string"},
                },
                "required": ["value"],
            },
        },
    },
]


SCENARIOS = [
    {
        "id": "native_tool_single",
        "user": "Call echo_tool with message 'hello-capture'. Return only tool call.",
    },
    {
        "id": "structured_json",
        "user": (
            "Respond as JSON object with reasoning, tools, response. "
            "Include one tool call to echo_tool."
        ),
    },
    {
        "id": "top_level_array",
        "user": "Return ONLY a JSON array with two tool calls: echo_tool and second_tool.",
    },
    {
        "id": "legacy_object",
        "user": "Return ONLY a legacy tool object: {name, arguments} for echo_tool.",
    },
    {
        "id": "malformed_json",
        "user": (
            "Return JSON for one tool call but intentionally include a trailing comma "
            "before closing object."
        ),
    },
    {
        "id": "plain_text",
        "user": "Reply in one plain sentence and do not call tools.",
    },
]


@dataclass
class CaptureRecord:
    timestamp: str
    model: str
    scenario: str
    run_mode: str
    prompt: str
    content: str
    tool_calls: list
    chunks: list


def _serialize_tool_calls(raw_calls) -> list:
    out: list = []
    for call in raw_calls or []:
        fn = getattr(call, "function", None)
        if fn:
            out.append({"name": fn.name, "arguments": fn.arguments})
        elif isinstance(call, dict):
            out.append(call)
        else:
            out.append({"raw": str(call)})
    return out


def _run_non_stream(client: Client, model: str, scenario: dict) -> CaptureRecord:
    messages = [
        {"role": "system", "content": "You are a format probe. Follow instructions exactly."},
        {"role": "user", "content": scenario["user"]},
    ]
    resp = client.chat(model=model, messages=messages, tools=TOOLS, stream=False)
    msg = resp.message
    return CaptureRecord(
        timestamp=_utc_now(),
        model=model,
        scenario=scenario["id"],
        run_mode="non_stream",
        prompt=scenario["user"],
        content=msg.content or "",
        tool_calls=_serialize_tool_calls(getattr(msg, "tool_calls", None)),
        chunks=[],
    )


def _run_stream(client: Client, model: str, scenario: dict) -> CaptureRecord:
    messages = [
        {"role": "system", "content": "You are a format probe. Follow instructions exactly."},
        {"role": "user", "content": scenario["user"]},
    ]

    chunks: list = []
    content_parts: list[str] = []
    final_calls = []

    for i, chunk in enumerate(client.chat(model=model, messages=messages, tools=TOOLS, stream=True)):
        msg = chunk.message
        delta = msg.content or ""
        thinking = getattr(msg, "thinking", None) or ""
        chunk_calls = _serialize_tool_calls(getattr(msg, "tool_calls", None))
        if delta:
            content_parts.append(delta)
        if chunk_calls:
            final_calls = chunk_calls
        chunks.append(
            {
                "index": i,
                "done": bool(getattr(chunk, "done", False)),
                "content": delta,
                "thinking": thinking,
                "tool_calls": chunk_calls,
            }
        )

    return CaptureRecord(
        timestamp=_utc_now(),
        model=model,
        scenario=scenario["id"],
        run_mode="stream",
        prompt=scenario["user"],
        content="".join(content_parts),
        tool_calls=final_calls,
        chunks=chunks,
    )


def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "-" for c in name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture Ollama model output formats")
    parser.add_argument(
        "--models",
        default=config.MODEL,
        help="Comma-separated model names",
    )
    parser.add_argument(
        "--output",
        default=str(
            Path(config.WORKSPACE_HOME).expanduser().resolve()
            / "captures"
            / "model_formats.jsonl"
        ),
        help="Output JSONL path",
    )
    parser.add_argument(
        "--write-fixtures",
        action="store_true",
        help="Also write per-scenario text fixtures under tests/fixtures/llm_responses",
    )
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    client = Client(host=config.OLLAMA_HOST)

    records: list[CaptureRecord] = []
    for model in models:
        for scenario in SCENARIOS:
            try:
                records.append(_run_non_stream(client, model, scenario))
            except Exception as e:
                records.append(
                    CaptureRecord(
                        timestamp=_utc_now(),
                        model=model,
                        scenario=scenario["id"],
                        run_mode="non_stream",
                        prompt=scenario["user"],
                        content=f"ERROR: {e}",
                        tool_calls=[],
                        chunks=[],
                    )
                )

            try:
                records.append(_run_stream(client, model, scenario))
            except Exception as e:
                records.append(
                    CaptureRecord(
                        timestamp=_utc_now(),
                        model=model,
                        scenario=scenario["id"],
                        run_mode="stream",
                        prompt=scenario["user"],
                        content=f"ERROR: {e}",
                        tool_calls=[],
                        chunks=[],
                    )
                )

    with out_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    if args.write_fixtures:
        fixtures_dir = Path("tests/fixtures/llm_responses")
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        latest_by_scenario: dict[str, CaptureRecord] = {}
        for record in records:
            # Prefer non-stream records for parser fixture text.
            if record.run_mode == "non_stream":
                latest_by_scenario[record.scenario] = record
        for scenario, record in latest_by_scenario.items():
            model_tag = _safe_name(record.model)
            fixture_path = fixtures_dir / f"{scenario}__{model_tag}.txt"
            fixture_path.write_text(record.content, encoding="utf-8")

    print(f"Wrote {len(records)} records to {out_path}")


if __name__ == "__main__":
    main()
