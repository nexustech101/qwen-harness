"""
Interactive REPL for the coding agent.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from app import config
from app.core.orchestrator import Orchestrator


def run_interactive(
    model: str | None = None,
    planner_model: str | None = None,
    coder_model: str | None = None,
    max_turns: int | None = None,
    use_dispatch: bool = True,
    async_dispatch: bool = True,
) -> None:
    """Launch the interactive agent REPL."""
    console = Console()
    orchestrator = Orchestrator(
        model=model,
        planner_model=planner_model,
        coder_model=coder_model,
        max_turns=max_turns,
        console=console,
        use_dispatch=use_dispatch,
        async_dispatch=async_dispatch,
    )

    mode_label = "dispatch" if use_dispatch else "direct"
    console.print()
    console.print("  [bold cyan]qwen-coder[/bold cyan] [dim]interactive mode[/dim]")
    console.print(f"  [dim]Mode: {mode_label} | Type a task, 'quit' to exit[/dim]")
    console.print(
        f"  [dim]Workspace: {orchestrator._workspace.workspace_key} "
        f"({orchestrator._workspace.root})[/dim]"
    )
    console.print("  [dim]Shortcuts: /clear  /agents  /context  /trace  /help[/dim]")
    console.print()

    while True:
        try:
            user_input = console.input("[green]>[/green] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye[/dim]")
            raise SystemExit(0)

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd in ("quit", "exit", "q"):
            console.print("[dim]Goodbye[/dim]")
            raise SystemExit(0)
        if cmd in ("clear", "/clear"):
            console.clear()
            continue
        if cmd in ("/help", "help"):
            console.print("  [dim]/clear  /agents  /context  /trace  quit[/dim]")
            continue
        if cmd == "/agents":
            agents = orchestrator._workspace.list_agents()
            if not agents:
                console.print("  [dim](no agents in workspace)[/dim]")
                continue
            for name in agents:
                summary = orchestrator._workspace.agent_summary(name)
                console.print(
                    f"  [cyan]{name}[/cyan] status={summary.get('status', 'unknown')} "
                    f"completed={summary.get('completed', 'no')}"
                )
            continue
        if cmd == "/context":
            summary = orchestrator._workspace.read_context_summary().strip()
            log_tail = orchestrator._workspace.read_context_log().strip()
            if summary:
                console.print("\n[bold]Rolling Context[/bold]")
                console.print(summary[-3000:])
            else:
                console.print("  [dim](no context summary)[/dim]")
            if log_tail:
                console.print("\n[bold]Context Log (tail)[/bold]")
                console.print(log_tail[-3000:])
            continue
        if cmd == "/trace":
            log_path = Path(config.LOG_FILE)
            if not log_path.exists():
                console.print("  [dim](trace log not found)[/dim]")
                continue
            text = log_path.read_text(encoding="utf-8", errors="replace")
            console.print("\n[bold]Trace Log (tail)[/bold]")
            console.print(text[-4000:])
            continue

        try:
            orchestrator.run(user_input)
        except KeyboardInterrupt:
            console.print("\n[dim]interrupted[/dim]")
            continue
