"""
Main entry point for the agent shell.

Usage:
    agent                          # Interactive REPL
    agent "what files are here?"   # Single prompt (non-interactive)
    agent --model qwen2.5-coder:7b # Override model
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from agent import config


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="agent",
        description="Agent shell — connects to the API server",
    )
    parser.add_argument(
        "prompt", nargs="?", default=None,
        help="Single prompt (omit for interactive mode)",
    )
    parser.add_argument(
        "--model", "-m", default=None,
        help=f"Model to use (default: {config.MODEL})",
    )
    args = parser.parse_args()

    model = args.model or config.MODEL

    if args.prompt:
        from agent.core.client import MCPAgentClient
        from agent.core.orchestrator import Orchestrator

        async def _run_once() -> int:
            async with MCPAgentClient() as client:
                orch = await Orchestrator.create(client, model=model)
                async for event in await orch.run(args.prompt):
                    etype = event.get("type", "")
                    if etype == "token":
                        print(event.get("delta", ""), end="", flush=True)
                    elif etype == "turn_done":
                        print()
                        break
                    elif etype == "error":
                        print(f"\nError: {event.get('detail', 'unknown')}", file=sys.stderr)
                        return 1
            return 0

        try:
            return asyncio.run(_run_once())
        except KeyboardInterrupt:
            print("\ninterrupted")
            return 130
    else:
        from agent.interactive import run_interactive
        run_interactive(model=model)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
