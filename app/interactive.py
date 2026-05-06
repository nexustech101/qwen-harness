"""
Interactive REPL for the Agent harness.

A Rich-powered shell that communicates with the API server via MCPAgentClient.
"""

from __future__ import annotations

import asyncio

import httpx
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app import config
from app.core.client import MCPAgentClient
from app.core.orchestrator import Orchestrator


def _banner(model: str, session_id: str, server: str) -> Panel:
    """Startup banner panel."""
    content = Text.assemble(
        ("agent-shell\n", "bold cyan"),
        ("Model  : ", "dim"), (model, "cyan"), ("\n", ""),
        ("Server : ", "dim"), (server, "cyan"), ("\n", ""),
        ("Session: ", "dim"), (session_id, "cyan"),
    )
    return Panel(content, border_style="cyan", padding=(0, 2), width=60)


def _session_panel(session_id: str) -> Panel:
    content = Text.assemble(("Session: ", "dim"), (session_id, "cyan"))
    return Panel(content, border_style="dim", padding=(0, 2), width=60)


def _new_session_panel(session_id: str) -> Panel:
    content = Text.assemble(("New session: ", "dim"), (session_id, "cyan"))
    return Panel(content, border_style="cyan", padding=(0, 2), width=60)


def _switched_panel(title: str, session_id: str) -> Panel:
    content = Text.assemble(
        ("Switched to: ", "dim"), (title, "bold"), "\n",
        ("Session: ", "dim"), (session_id, "cyan"),
    )
    return Panel(content, border_style="cyan", padding=(0, 2), width=60)


def _models_table(models: list[str], current: str) -> Table:
    t = Table(title="Available Models", border_style="dim", header_style="bold cyan", show_lines=False, width=50)
    t.add_column("", width=2, no_wrap=True)
    t.add_column("Model", style="cyan")
    for m in models:
        marker = "[bold cyan]▶[/bold cyan]" if m == current else " "
        t.add_row(marker, m)
    return t


def _sessions_table(sessions: list[dict], current_id: str) -> Table:
    t = Table(title="Sessions", border_style="dim", header_style="bold cyan", show_lines=False)
    t.add_column("#", style="dim", width=3, no_wrap=True)
    t.add_column("", width=2, no_wrap=True)
    t.add_column("Title", style="bold")
    t.add_column("ID", style="dim")
    t.add_column("Status", style="dim")
    for i, s in enumerate(sessions, 1):
        active = s["id"] == current_id
        marker = "[bold cyan]▶[/bold cyan]" if active else " "
        t.add_row(
            str(i),
            marker,
            s.get("title") or "Untitled",
            s["id"][:8] + "…",
            s.get("status", ""),
        )
    return t


def _workflows_table(workflows: list[dict]) -> Table:
    t = Table(title="Workflows", border_style="dim", header_style="bold cyan", show_lines=False)
    t.add_column("Name", style="cyan")
    t.add_column("Status", width=6)
    t.add_column("Description", style="dim")
    for wf in workflows:
        status = "[green]on[/green]" if wf.get("enabled") else "[dim]off[/dim]"
        t.add_row(wf["name"], status, wf.get("description", ""))
    return t


def _help_table() -> Table:
    t = Table(title="Commands", border_style="dim", header_style="bold cyan", show_lines=False, show_header=False, width=52)
    t.add_column("Command", style="cyan", no_wrap=True)
    t.add_column("Description", style="dim")
    rows = [
        ("/new", "Start a new chat session"),
        ("/sessions", "List and switch between sessions"),
        ("/session", "Show current session ID"),
        ("/models", "List available models"),
        ("/workflows", "List workflows"),
        ("/clear", "Clear the terminal"),
        ("/help", "Show this help"),
        ("quit", "Exit the shell"),
    ]
    for cmd, desc in rows:
        t.add_row(cmd, desc)
    return t


def _read_multiline(console: Console) -> str:
    """Collect multi-line input (for pasting code, logs, etc.).

    Reads lines until the user types ``END`` on a line by itself or presses
    Ctrl+D (EOF).  Returns the collected text as a single string.
    """
    console.print(
        "[dim]Paste your content below. "
        "Type [bold cyan]END[/bold cyan] on an empty line (or Ctrl+D) to submit.[/dim]"
    )
    lines: list[str] = []
    while True:
        try:
            line = console.input("")
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines)



async def _run_repl(model: str) -> None:
    console = Console()

    async with MCPAgentClient() as client:
        # Verify server is reachable
        try:
            await client.health()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            console.print(Panel(
                Text.assemble(("Cannot connect to ", "red"), (config.API_BASE_URL, "bold"), ("\n", ""), (str(e), "dim red")),
                title="[red]Connection Error[/red]", border_style="red", padding=(0, 2),
            ))
            return

        orchestrator = await Orchestrator.create(client, model=model)

        console.print()
        console.print(_banner(model, orchestrator.session_id, config.API_BASE_URL))
        console.print()

        while True:
            try:
                user_input = console.input("[green]>[/green] ").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Goodbye[/dim]")
                return

            if not user_input:
                continue

            cmd = user_input.lower()

            if cmd in ("quit", "exit", "q"):
                console.print("[dim]Goodbye[/dim]")
                return

            if cmd in ("clear", "/clear"):
                console.clear()
                continue

            if cmd in ("/help", "help"):
                console.print()
                console.print(_help_table())
                console.print()
                continue

            if cmd == "/session":
                console.print()
                console.print(_session_panel(orchestrator.session_id))
                console.print()
                continue

            if cmd == "/new":
                orchestrator = await Orchestrator.create(client, model=model)
                console.print()
                console.print(_new_session_panel(orchestrator.session_id))
                console.print()
                continue

            if cmd == "/sessions":
                try:
                    sessions = await client.list_sessions()
                    if not sessions:
                        console.print(Panel("[dim](no sessions)[/dim]", border_style="dim", padding=(0, 2)))
                    else:
                        console.print()
                        console.print(_sessions_table(sessions, orchestrator.session_id))
                        console.print()
                        try:
                            raw = console.input("[green]>[/green] [dim]Select number (or Enter to cancel):[/dim] ").strip()
                        except (KeyboardInterrupt, EOFError):
                            raw = ""
                        if raw:
                            try:
                                idx = int(raw) - 1
                                if 0 <= idx < len(sessions):
                                    sel = sessions[idx]
                                    orchestrator = Orchestrator(client, sel["id"])
                                    title = sel.get("title") or "Untitled"
                                    console.print()
                                    console.print(_switched_panel(title, sel["id"]))
                                    console.print()
                                else:
                                    console.print("[red]Invalid selection[/red]")
                            except ValueError:
                                console.print("[red]Invalid input[/red]")
                except Exception as e:
                    console.print(f"[red]Error fetching sessions: {e}[/red]")
                continue

            if cmd == "/models":
                try:
                    models = await client.list_models()
                    console.print()
                    console.print(_models_table(models, model))
                    console.print()
                except Exception as e:
                    console.print(f"[red]Error fetching models: {e}[/red]")
                continue

            if cmd == "/workflows":
                try:
                    workflows = await client.list_workflows()
                    if not workflows:
                        console.print(Panel("[dim](no workflows)[/dim]", border_style="dim", padding=(0, 2)))
                    else:
                        console.print()
                        console.print(_workflows_table(workflows))
                        console.print()
                except Exception as e:
                    console.print(f"[red]Error fetching workflows: {e}[/red]")
                continue

            # Normal prompt — stream the response
            try:
                await _stream_turn(console, orchestrator, user_input)
            except KeyboardInterrupt:
                console.print("\n[dim]interrupted[/dim]")
                continue
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                continue


async def _stream_turn(
    console: Console,
    orchestrator: Orchestrator,
    prompt: str,
) -> None:
    """Stream a single chat turn, rendering tokens and tool events.

    Rendering strategy:
      - ``thinking`` events  → dim italic indicator updated live
      - ``token`` events     → Markdown rendered live (re-parsed each refresh)
      - ``tool_call``        → printed above the live area inline
      - ``tool_result``      → printed above the live area inline
      - ``turn_done``        → stream ends; final Markdown state stays visible
    """
    content_buf = ""
    thinking_buf = ""

    def _render(done: bool = False) -> object:
        """Build the current Live renderable from accumulated buffers."""
        items: list = []
        if thinking_buf:
            if done:
                items.append(
                    Text(f"◦ thought for {len(thinking_buf):,} chars", style="dim italic")
                )
            else:
                # Show last ~20 lines of thinking text live
                lines = thinking_buf.splitlines()
                preview = "\n".join(lines[-20:])
                items.append(
                    Panel(
                        Text(preview, style="dim"),
                        title="[dim italic]thinking[/dim italic]",
                        border_style="dim",
                        padding=(0, 1),
                    )
                )
        if content_buf:
            items.append(Markdown(content_buf))
        elif not thinking_buf:
            items.append(Text("▋", style="dim"))
        return Group(*items) if len(items) > 1 else (items[0] if items else Text(""))

    stream = await orchestrator.run(prompt)
    with Live(_render(), console=console, refresh_per_second=15) as live:
        async for event in stream:
            etype = event.get("type", "")

            if etype == "thinking":
                thinking_buf += event.get("delta", "")
                live.update(_render())

            elif etype == "token":
                content_buf += event.get("delta", "")
                # Suppress live rendering when response looks like a raw JSON
                # tool call — prevents long JSON from scrolling into the
                # terminal's scrollback buffer where it cannot be erased.
                if not content_buf.lstrip().startswith("{"):
                    live.update(_render())

            elif etype == "clear_content":
                content_buf = ""
                live.update(_render())

            elif etype == "tool_call":
                name = event.get("name", "?")
                args = event.get("args", {})
                args_preview = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:2])
                console.print(f"  [dim]⚙ [cyan]{name}[/cyan]({args_preview})[/dim]")

            elif etype == "tool_result":
                name = event.get("name", "?")
                ok = event.get("success", event.get("ok", True))
                output = str(event.get("output", event.get("summary", "")))
                icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
                summary = (output[:120] + "…") if len(output) > 120 else output
                console.print(f"  [dim]{icon} {name}: {summary}[/dim]")

            elif etype == "turn_done":
                # Clear the live area; full render happens below outside Live
                live.update(Text(""))
                break

            elif etype == "error":
                live.stop()
                console.print(f"[red]Error: {event.get('detail', 'unknown')}[/red]")
                return

    # Render the final response outside Live so it is never height-clipped.
    # Skip content that looks like a raw JSON tool call — if _parse_text_tool_calls
    # detected it, content_buf was already cleared via clear_content; if it
    # somehow wasn't detected we still don't want raw JSON printed to the user.
    if thinking_buf:
        console.print(Text(f"◦ thought for {len(thinking_buf):,} chars", style="dim italic"))
    if content_buf and not content_buf.lstrip().startswith("{"):
        console.print(Markdown(content_buf))
    console.print()


def run_interactive(model: str | None = None) -> None:
    """Entry point for the interactive shell."""
    asyncio.run(_run_repl(model or config.MODEL))
