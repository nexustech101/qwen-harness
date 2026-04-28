"""
Main entry point for the coding agent.

Usage:
    qwen-coder                                 # Interactive REPL (dispatch mode)
    qwen-coder "create a hello.py"             # Single prompt (dispatch mode)
    qwen-coder --direct "simple fix"           # Direct single-agent mode
    qwen-coder --planner-model mistral ...     # Override planner model
    qwen-coder --coder-model qwen3-coder ...   # Override coder model

    @TODO: Use the click library for a more robust cli coding agent.
"""

from __future__ import annotations

import argparse
import sys

from app import config


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="qwen-coder",
        description="Coding agent powered by local LLMs",
    )
    parser.add_argument(
        "prompt", nargs="?", default=None,
        help="Single prompt (omit for interactive mode)",
    )

    # ── Model overrides ────────────────────────────────────────────────────
    parser.add_argument(
        "--model", "-m", default=None,
        help=f"Override ALL models (default: {config.MODEL})",
    )
    parser.add_argument(
        "--planner-model", default=None,
        help=f"Model for task decomposition (default: {config.PLANNER_MODEL})",
    )
    parser.add_argument(
        "--coder-model", default=None,
        help=f"Model for code generation (default: {config.CODER_MODEL})",
    )

    # ── Execution mode ─────────────────────────────────────────────────────
    parser.add_argument(
        "--direct", action="store_true",
        help="Use direct single-agent mode (no decomposition)",
    )
    parser.add_argument(
        "--no-async", dest="no_async", action="store_true",
        help="Disable async dispatch (use sequential instead)",
    )
    parser.add_argument(
        "--max-turns", "-t", type=int, default=config.MAX_TURNS,
        help=f"Max turns (default: {config.MAX_TURNS})",
    )

    # ── API server ─────────────────────────────────────────────────────────
    parser.add_argument(
        "--serve", action="store_true",
        help="Start the FastAPI server instead of CLI mode",
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="API server host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port", "-p", type=int, default=8000,
        help="API server port (default: 8000)",
    )

    args = parser.parse_args()

    # ── API server mode ────────────────────────────────────────────────────
    if args.serve:
        import uvicorn
        from api.router import app as api_app
        uvicorn.run(api_app, host=args.host, port=args.port)
        return

    # Dispatch is the default; --direct turns it off
    use_dispatch = not args.direct
    async_dispatch = use_dispatch and not args.no_async

    # If --model is set, it overrides both role models (unless they're also set)
    planner_model = args.planner_model or args.model
    coder_model = args.coder_model or args.model

    if args.prompt:
        from app.core.orchestrator import Orchestrator
        try:
            result = Orchestrator(
                model=args.model,
                planner_model=planner_model,
                coder_model=coder_model,
                max_turns=args.max_turns,
                use_dispatch=use_dispatch,
                async_dispatch=async_dispatch,
            ).run(args.prompt)
        except KeyboardInterrupt:
            print("\ninterrupted")
            sys.exit(130)
        if result.reason != "done":
            sys.exit(1)
    else:
        from app.interactive import run_interactive
        run_interactive(
            model=args.model,
            planner_model=planner_model,
            coder_model=coder_model,
            max_turns=args.max_turns,
            use_dispatch=use_dispatch,
            async_dispatch=async_dispatch,
        )

    return 0


if __name__ == "__main__":
    main()
