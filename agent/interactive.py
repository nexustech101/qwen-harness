"""
Interactive REPL for the Agent harness.

A Rich-powered shell that communicates with the API server via MCPAgentClient.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path

import httpx
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from agent import config
from agent.core.client import MCPAgentClient
from agent.core.orchestrator import Orchestrator

# ── Version ────────────────────────────────────────────────────────────────────

_VERSION = "3.0.0"

# ── Spinner frames ─────────────────────────────────────────────────────────────

_SPINNER = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]


# ── Rich panels / tables ───────────────────────────────────────────────────────

def _banner(model: str, provider: str, session_id: str, server: str) -> Panel:
    provider_color = {"ollama": "green", "openai": "cyan", "anthropic": "magenta"}.get(provider, "cyan")
    content = Text.assemble(
        ("⚡ agent-shell  ", "bold white"),
        (f"v{_VERSION}\n", "dim"),
        ("\n", ""),
        ("Provider : ", "dim"), (f"{provider}\n", provider_color),
        ("Model    : ", "dim"), (model, "bold cyan"), ("\n", ""),
        ("Server   : ", "dim"), (server, "dim cyan"), ("\n", ""),
        ("Session  : ", "dim"), (session_id[:8] + "…", "dim"),
        ("\n\n", ""),
        ("Type ", "dim"), ("/help", "cyan"), (" for commands, ", "dim"),
        ("quit", "cyan"), (" to exit", "dim"),
    )
    return Panel(content, border_style="cyan", padding=(0, 2), width=56)


def _session_panel(session: dict) -> Panel:
    status_color = {"idle": "green", "running": "yellow", "error": "red"}.get(
        session.get("status", ""), "dim"
    )
    msg_count = session.get("message_count", 0)
    title = session.get("title") or "Untitled"
    content = Text.assemble(
        ("ID      : ", "dim"), (session.get("id", "?")[:8] + "…", "cyan"), ("\n", ""),
        ("Title   : ", "dim"), (title, "bold"), ("\n", ""),
        ("Model   : ", "dim"), (session.get("model", "?"), "cyan"), ("\n", ""),
        ("Status  : ", "dim"), (f"[{status_color}]{session.get('status', '?')}[/{status_color}]\n", ""),
        ("Messages: ", "dim"), (str(msg_count), "cyan"),
    )
    return Panel(content, title="[cyan]Session[/cyan]", border_style="dim", padding=(0, 2))


def _new_session_panel(session_id: str) -> Panel:
    content = Text.assemble(
        ("✓ New session created\n", "green"),
        ("ID: ", "dim"), (session_id, "cyan"),
    )
    return Panel(content, border_style="green", padding=(0, 2), width=56)


def _switched_panel(title: str, session_id: str) -> Panel:
    content = Text.assemble(
        ("⇄ Switched session\n", "cyan"),
        ("Title: ", "dim"), (title, "bold"), ("\n", ""),
        ("ID   : ", "dim"), (session_id[:8] + "…", "dim"),
    )
    return Panel(content, border_style="cyan", padding=(0, 2), width=56)


def _models_table(models: list[str], current: str) -> Table:
    t = Table(
        title="Available Models",
        border_style="dim",
        header_style="bold cyan",
        show_lines=False,
        width=54,
    )
    t.add_column("", width=2, no_wrap=True)
    t.add_column("Model", style="cyan")
    for m in models:
        marker = "[bold cyan]▶[/bold cyan]" if m == current else " "
        t.add_row(marker, m)
    return t


def _sessions_table(sessions: list[dict], current_id: str) -> Table:
    t = Table(
        title="Sessions",
        border_style="dim",
        header_style="bold cyan",
        show_lines=False,
    )
    t.add_column("#", style="dim", width=3, no_wrap=True)
    t.add_column("", width=2, no_wrap=True)
    t.add_column("Title", style="bold")
    t.add_column("Model", style="dim")
    t.add_column("Msgs", style="dim", width=5, no_wrap=True)
    t.add_column("Status", width=8, no_wrap=True)
    for i, s in enumerate(sessions, 1):
        active = s["id"] == current_id
        marker = "[bold cyan]▶[/bold cyan]" if active else " "
        status = s.get("status", "")
        status_col = {
            "idle": "[dim]idle[/dim]",
            "running": "[yellow]running[/yellow]",
            "error": "[red]error[/red]",
        }.get(status, f"[dim]{status}[/dim]")
        t.add_row(
            str(i),
            marker,
            s.get("title") or "Untitled",
            s.get("model", "?"),
            str(s.get("message_count", 0)),
            status_col,
        )
    return t


def _workflows_table(workflows: list[dict]) -> Table:
    t = Table(
        title="Workflows",
        border_style="dim",
        header_style="bold cyan",
        show_lines=False,
    )
    t.add_column("Name", style="cyan")
    t.add_column("Enabled", width=8)
    t.add_column("Description", style="dim")
    for wf in workflows:
        status = "[green]● on[/green]" if wf.get("enabled") else "[dim]○ off[/dim]"
        t.add_row(wf.get("name", "?"), status, wf.get("description", ""))
    return t


def _tools_table(tools: list[dict]) -> Table:
    t = Table(
        title=f"Tools  [dim]({len(tools)} registered)[/dim]",
        border_style="dim",
        header_style="bold cyan",
        show_lines=False,
    )
    t.add_column("Name", style="cyan", no_wrap=True, min_width=22)
    t.add_column("Description", style="dim")
    for tool in tools:
        t.add_row(tool.get("name", "?"), tool.get("description", "")[:72])
    return t


def _help_table() -> Table:
    t = Table(
        title="Commands",
        border_style="dim",
        header_style="bold cyan",
        show_lines=False,
        show_header=False,
        width=60,
    )
    t.add_column("Command", style="cyan", no_wrap=True, min_width=24)
    t.add_column("Description", style="dim")

    sections: list[tuple[str, list[tuple[str, str]]]] = [
        ("Session", [
            ("/new", "Start a new chat session"),
            ("/sessions", "List, switch, or delete sessions"),
            ("/session", "Show current session details"),
            ("/rename [title]", "Rename the current session"),
            ("/context", "Session context summary"),
            ("/history [n]", "Show last n messages (default 10)"),
            ("/export [path]", "Export conversation to Markdown"),
        ]),
        ("Model & Provider", [
            ("/models", "List available models"),
            ("/model [name]", "Show or switch model"),
            ("/provider [name]", "Switch provider  (ollama/openai/anthropic)"),
        ]),
        ("Tools", [
            ("/tools", "List all registered tools"),
            ("/tool <name> [json]", "Invoke a tool directly"),
        ]),
        ("Input", [
            ("/paste", "Multiline / paste mode  (END to submit)"),
            ("/workspace [path]", "Show or change workspace directory"),
        ]),
        ("Config & Debug", [
            ("/config", "Show current shell configuration"),
            ("/trace", "Toggle verbose event trace"),
        ]),
        ("View", [
            ("/workflows", "List workflows"),
            ("/clear", "Clear the terminal"),
            ("/help", "Show this help"),
            ("quit / exit / q", "Exit the shell"),
        ]),
    ]

    for section_title, rows in sections:
        t.add_row(f"[dim]── {section_title} ──[/dim]", "")
        for cmd, desc in rows:
            t.add_row(f"  {cmd}", desc)

    return t


def _config_panel(model: str, provider: str, workspace: str, trace: bool) -> Panel:
    provider_color = {"ollama": "green", "openai": "cyan", "anthropic": "magenta"}.get(provider, "cyan")
    content = Text.assemble(
        ("Provider : ", "dim"), (f"{provider}\n", provider_color),
        ("Model    : ", "dim"), (model, "cyan"), ("\n", ""),
        ("Server   : ", "dim"), (config.API_BASE_URL, "dim cyan"), ("\n", ""),
        ("Workspace: ", "dim"), (workspace, "dim"), ("\n", ""),
        ("Trace    : ", "dim"), ("on" if trace else "off", "green" if trace else "dim"),
    )
    return Panel(content, title="[cyan]Configuration[/cyan]", border_style="dim", padding=(0, 2))


def _error_panel(message: str, hint: str = "") -> Panel:
    body: list = [Text(message, style="red")]
    if hint:
        body.append(Text(f"\n{hint}", style="dim"))
    return Panel(Group(*body), title="[red]Error[/red]", border_style="red", padding=(0, 2))


def _tool_call_row(name: str, args: dict) -> Text:
    """Inline tool-call annotation shown inside the streaming Live block."""
    args_preview = "  ".join(
        f"[dim]{k}=[/dim][cyan]{str(v)[:40]}[/cyan]"
        for k, v in list(args.items())[:3]
    )
    return Text.from_markup(f"  [dim]⚙[/dim] [bold cyan]{name}[/bold cyan]  {args_preview}")


def _tool_result_row(name: str, result_text: str, ok: bool = True) -> Text:
    icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
    summary = result_text.strip().splitlines()[0] if result_text.strip() else "(empty)"
    summary = (summary[:100] + "…") if len(summary) > 100 else summary
    return Text.from_markup(f"  {icon} [dim]{name}:[/dim] {summary}")


# ── Multiline input ────────────────────────────────────────────────────────────

def _read_multiline(console: Console) -> str:
    """Collect multi-line / paste input.  Type END on a blank line to submit."""
    console.print(
        Panel(
            Text.assemble(
                ("Paste your content below.\n", "dim"),
                ("Type [bold cyan]END[/bold cyan] on an empty line or Ctrl+D to submit.", "dim"),
            ),
            border_style="dim",
            padding=(0, 2),
        )
    )
    lines: list[str] = []
    while True:
        try:
            line = console.input("[dim]  ·[/dim] ")
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


# ── Streaming turn renderer ────────────────────────────────────────────────────

async def _stream_turn(
    console: Console,
    orchestrator: Orchestrator,
    prompt: str,
    trace: bool = False,
) -> None:
    """Stream a single chat turn, rendering tokens and tool events live."""
    content_buf = ""
    thinking_buf = ""
    tool_log: list[Text] = []
    received_any = False
    spin_idx = 0
    t_start = time.monotonic()

    def _render() -> object:
        items: list = []

        # Tool activity log (printed above the content)
        for row in tool_log:
            items.append(row)

        if not received_any:
            frame = _SPINNER[spin_idx % len(_SPINNER)]
            items.append(Text(f"  {frame} waiting…", style="dim"))
        elif thinking_buf and not content_buf:
            lines = thinking_buf.splitlines()
            preview = "\n".join(lines[-12:])
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
        elif received_any and not thinking_buf:
            items.append(Text("▋", style="dim"))

        return Group(*items) if len(items) > 1 else (items[0] if items else Text(""))

    stream = await orchestrator.run(prompt)

    with Live(_render(), console=console, refresh_per_second=15, vertical_overflow="visible") as live:
        async for event in stream:
            etype = event.get("type", "")
            data = event.get("data", event)

            if trace:
                live.console.print(f"[dim]  trace: {etype} {str(data)[:120]}[/dim]")

            if etype == "thinking_delta":
                received_any = True
                thinking_buf += data.get("text", "")
                live.update(_render())

            elif etype == "clear_content":
                content_buf = ""
                live.update(_render())

            elif etype == "content_delta":
                received_any = True
                delta = data.get("text", "")
                content_buf += delta
                live.update(_render())

            elif etype == "response_text":
                received_any = True
                text = data.get("text", "")
                if text and len(text) > len(content_buf):
                    content_buf = text
                live.update(_render())

            elif etype in ("tool_call", "tool_dispatch"):
                received_any = True
                name = data.get("tool", data.get("name", "?"))
                args = data.get("args", data.get("arguments", {}))
                tool_log.append(_tool_call_row(name, args))
                live.update(_render())

            elif etype == "tool_result":
                name = data.get("tool", data.get("name", "?"))
                result = str(data.get("result", data.get("summary", data.get("output", ""))))
                ok = bool(data.get("success", data.get("ok", True)))
                tool_log.append(_tool_result_row(name, result, ok))
                live.update(_render())

            elif etype == "stream_end":
                live.update(Text(""))
                break

            elif etype in ("turn_done", "turn_start"):
                if etype == "turn_done":
                    live.update(Text(""))
                    break

            elif etype == "error":
                live.stop()
                console.print(_error_panel(
                    data.get("message", data.get("detail", "unknown error")),
                    hint="Use /trace to see raw event output.",
                ))
                return

            elif etype in ("thinking", "token"):
                received_any = True
                if etype == "thinking":
                    thinking_buf += data.get("delta", data.get("text", ""))
                else:
                    content_buf += data.get("delta", data.get("text", ""))
                live.update(_render())

            else:
                spin_idx += 1
                live.update(_render())

    elapsed = time.monotonic() - t_start

    # ── Permanent final render ────────────────────────────────────────────────
    for row in tool_log:
        console.print(row)

    if thinking_buf:
        console.print(
            Text.from_markup(f"  [dim italic]◦ reasoned for {len(thinking_buf):,} chars[/dim italic]")
        )

    if content_buf:
        console.print(Markdown(content_buf))

    console.print(Text.from_markup(f"\n  [dim]⚡ {elapsed:.1f}s[/dim]\n"))


# ── Main REPL ─────────────────────────────────────────────────────────────────

async def _run_repl(model: str) -> None:
    console = Console()
    current_provider: str = os.getenv("AGENT_LLM_PROVIDER", "ollama")
    trace_mode: bool = False
    workspace_dir: str = config.WORKSPACE_HOME

    async with MCPAgentClient() as client:
        # ── Connection check ───────────────────────────────────────────────────
        try:
            await client.health()
        except (httpx.ConnectError, httpx.TimeoutException):
            console.print(_error_panel(
                f"Cannot connect to {config.API_BASE_URL}",
                hint="Start the API server with:  agent-api",
            ))
            return

        # Pull provider from server config if available
        try:
            cfg_resp = await client._http.get("/api/config")
            current_provider = cfg_resp.json().get("llm_provider", current_provider)
        except Exception:
            pass

        orchestrator = await Orchestrator.create(client, model=model)

        console.print()
        console.print(_banner(model, current_provider, orchestrator.session_id, config.API_BASE_URL))
        console.print()

        def _prompt_str() -> str:
            short = model.split(":")[0] if ":" in model else model
            return f"[bold cyan]{short}[/bold cyan] [green]❯[/green] "

        while True:
            try:
                user_input = console.input(_prompt_str()).strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Goodbye[/dim]")
                return

            if not user_input:
                continue

            cmd = user_input.lower()

            # ── Quit ──────────────────────────────────────────────────────────
            if cmd in ("quit", "exit", "q"):
                console.print("[dim]Goodbye[/dim]")
                return

            # ── Clear ─────────────────────────────────────────────────────────
            if cmd in ("clear", "/clear"):
                console.clear()
                continue

            # ── Help ──────────────────────────────────────────────────────────
            if cmd in ("/help", "help"):
                console.print()
                console.print(_help_table())
                console.print()
                continue

            # ── /session ──────────────────────────────────────────────────────
            if cmd == "/session":
                try:
                    s = await client.get_session(orchestrator.session_id)
                    console.print()
                    console.print(_session_panel(s))
                    console.print()
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")
                continue

            # ── /new ──────────────────────────────────────────────────────────
            if cmd == "/new":
                orchestrator = await Orchestrator.create(client, model=model)
                console.print()
                console.print(_new_session_panel(orchestrator.session_id))
                console.print()
                continue

            # ── /rename [title] ───────────────────────────────────────────────
            if cmd.startswith("/rename"):
                parts = user_input.split(None, 1)
                if len(parts) > 1:
                    new_title = parts[1].strip()
                else:
                    try:
                        new_title = console.input("[green]❯[/green] [dim]New title:[/dim] ").strip()
                    except (KeyboardInterrupt, EOFError):
                        continue
                if new_title:
                    try:
                        await client._http.patch(
                            f"/api/sessions/{orchestrator.session_id}",
                            json={"title": new_title},
                        )
                        console.print(f"[cyan]Session renamed:[/cyan] {new_title}")
                    except Exception:
                        console.print(f"[dim]Title noted (server does not persist renames yet).[/dim]")
                console.print()
                continue

            # ── /sessions ─────────────────────────────────────────────────────
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
                            raw = console.input(
                                "[green]❯[/green] [dim]Select # to switch, "
                                "[bold cyan]d<n>[/bold cyan] to delete, Enter to cancel:[/dim] "
                            ).strip()
                        except (KeyboardInterrupt, EOFError):
                            raw = ""
                        if not raw:
                            pass
                        elif raw.lower().startswith("d"):
                            idx_str = raw[1:].strip()
                            try:
                                idx = int(idx_str) - 1
                                if 0 <= idx < len(sessions):
                                    sel = sessions[idx]
                                    await client.delete_session(sel["id"])
                                    if sel["id"] == orchestrator.session_id:
                                        orchestrator = await Orchestrator.create(client, model=model)
                                        console.print("[yellow]Active session deleted — started new session.[/yellow]")
                                    else:
                                        console.print(f"[green]✓ Deleted:[/green] {sel.get('title') or sel['id'][:8]}")
                                else:
                                    console.print("[red]Invalid selection[/red]")
                            except (ValueError, Exception) as e:
                                console.print(f"[red]Error: {e}[/red]")
                        else:
                            try:
                                idx = int(raw) - 1
                                if 0 <= idx < len(sessions):
                                    sel = sessions[idx]
                                    orchestrator = Orchestrator(client, sel["id"])
                                    console.print()
                                    console.print(_switched_panel(sel.get("title") or "Untitled", sel["id"]))
                                else:
                                    console.print("[red]Invalid selection[/red]")
                            except ValueError:
                                console.print("[red]Invalid input[/red]")
                except Exception as e:
                    console.print(f"[red]Error fetching sessions: {e}[/red]")
                console.print()
                continue

            # ── /models ───────────────────────────────────────────────────────
            if cmd == "/models":
                try:
                    models = await client.list_models()
                    if not models:
                        console.print("[dim]No models returned (check provider config).[/dim]")
                    else:
                        console.print()
                        console.print(_models_table(models, model))
                        console.print()
                except Exception as e:
                    console.print(f"[red]Error fetching models: {e}[/red]")
                continue

            # ── /model [name] ─────────────────────────────────────────────────
            if cmd.startswith("/model "):
                model = user_input[7:].strip()
                console.print(f"[cyan]Model:[/cyan] {model}")
                console.print()
                continue

            if cmd == "/model":
                console.print(f"[cyan]Model:[/cyan] {model}")
                console.print()
                continue

            # ── /provider [name] ──────────────────────────────────────────────
            if cmd.startswith("/provider "):
                new_prov = user_input[10:].strip().lower()
                if new_prov in ("ollama", "openai", "anthropic"):
                    current_provider = new_prov
                    console.print(f"[cyan]Provider:[/cyan] {current_provider}")
                else:
                    console.print(
                        f"[red]Unknown provider '[bold]{new_prov}[/bold]'. "
                        f"Choose: ollama, openai, anthropic[/red]"
                    )
                console.print()
                continue

            if cmd == "/provider":
                console.print(f"[cyan]Provider:[/cyan] {current_provider}")
                console.print()
                continue

            # ── /tools ────────────────────────────────────────────────────────
            if cmd == "/tools":
                try:
                    tools = await client.list_tools()
                    if not tools:
                        console.print(Panel("[dim](no tools registered)[/dim]", border_style="dim", padding=(0, 2)))
                    else:
                        console.print()
                        console.print(_tools_table(tools))
                        console.print()
                except Exception as e:
                    console.print(f"[red]Error fetching tools: {e}[/red]")
                continue

            # ── /tool <name> [json] ───────────────────────────────────────────
            if cmd.startswith("/tool "):
                parts = user_input[6:].strip().split(None, 1)
                tool_name = parts[0] if parts else ""
                raw_args = parts[1] if len(parts) > 1 else "{}"
                try:
                    tool_args = json.loads(raw_args) if raw_args.strip() else {}
                except json.JSONDecodeError as e:
                    console.print(f"[red]Invalid JSON args: {e}[/red]")
                    continue
                try:
                    t0 = time.monotonic()
                    result = await client.call_tool(tool_name, tool_args)
                    elapsed = time.monotonic() - t0
                    result_str = str(result)
                    if result_str.strip().startswith(("{", "[")):
                        try:
                            pretty = json.dumps(json.loads(result_str), indent=2)
                            renderable = Syntax(pretty, "json", theme="monokai", word_wrap=True)
                        except Exception:
                            renderable = Text(result_str)
                    else:
                        renderable = Text(result_str)
                    console.print()
                    console.print(
                        Panel(
                            renderable,
                            title=f"[cyan]{tool_name}[/cyan]  [dim]⚡ {elapsed:.2f}s[/dim]",
                            border_style="dim",
                            padding=(0, 1),
                        )
                    )
                    console.print()
                except Exception as e:
                    console.print(_error_panel(f"Tool error: {e}"))
                continue

            # ── /history [n] ──────────────────────────────────────────────────
            if cmd.startswith("/history"):
                parts = user_input.split(None, 1)
                n = 10
                if len(parts) > 1:
                    try:
                        n = int(parts[1].strip())
                    except ValueError:
                        pass
                try:
                    history = await client.get_messages(orchestrator.session_id, limit=n)
                    if not history:
                        console.print(Panel("[dim](no messages)[/dim]", border_style="dim", padding=(0, 2)))
                    else:
                        console.print()
                        console.print(Rule(f"[dim]Last {min(n, len(history))} messages[/dim]", style="dim"))
                        for msg in history[-n:]:
                            role = msg.get("role", "?")
                            text = (msg.get("content", "") or "").strip()
                            if role == "user":
                                console.print(Text.from_markup(f"\n[bold green]you[/bold green]  [dim]{text[:600]}[/dim]"))
                            else:
                                console.print()
                                console.print(Markdown(text[:1200]))
                        console.print()
                except Exception as e:
                    console.print(f"[red]Error fetching history: {e}[/red]")
                continue

            # ── /context ──────────────────────────────────────────────────────
            if cmd == "/context":
                try:
                    s = await client.get_session(orchestrator.session_id)
                    console.print()
                    console.print(_session_panel(s))
                    console.print()
                except Exception as e:
                    console.print(f"[red]Error fetching context: {e}[/red]")
                continue

            # ── /workspace [path] ─────────────────────────────────────────────
            if cmd.startswith("/workspace"):
                parts = user_input.split(None, 1)
                if len(parts) > 1:
                    workspace_dir = str(Path(parts[1].strip()).resolve())
                    console.print(f"[cyan]Workspace:[/cyan] {workspace_dir}")
                else:
                    console.print(f"[cyan]Workspace:[/cyan] {workspace_dir}")
                console.print()
                continue

            # ── /paste ────────────────────────────────────────────────────────
            if cmd == "/paste":
                text = _read_multiline(console)
                if text.strip():
                    console.print()
                    try:
                        await _stream_turn(console, orchestrator, text, trace=trace_mode)
                    except KeyboardInterrupt:
                        console.print("\n[dim]interrupted[/dim]")
                continue

            # ── /export [path] ────────────────────────────────────────────────
            if cmd.startswith("/export"):
                parts = user_input.split(None, 1)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                export_path = parts[1].strip() if len(parts) > 1 else f"conversation_{ts}.md"
                try:
                    msgs = await client.get_messages(orchestrator.session_id, limit=10000)
                    if not msgs:
                        console.print("[dim]No messages to export.[/dim]")
                    else:
                        lines = [
                            f"# Conversation — {orchestrator.session_id}\n",
                            f"_Exported: {datetime.now().isoformat(timespec='seconds')}_\n\n",
                        ]
                        for msg in msgs:
                            role = msg.get("role", "?")
                            body = msg.get("content", "") or ""
                            lines.append(f"\n## {role}\n\n{body}\n")
                        Path(export_path).write_text("\n".join(lines), encoding="utf-8")
                        console.print(f"[green]✓ Exported[/green] → {export_path}")
                except Exception as e:
                    console.print(_error_panel(f"Export error: {e}"))
                console.print()
                continue

            # ── /config ───────────────────────────────────────────────────────
            if cmd == "/config":
                console.print()
                console.print(_config_panel(model, current_provider, workspace_dir, trace_mode))
                console.print()
                continue

            # ── /trace ────────────────────────────────────────────────────────
            if cmd == "/trace":
                trace_mode = not trace_mode
                state = "[green]on[/green]" if trace_mode else "[dim]off[/dim]"
                console.print(f"[dim]Trace:[/dim] {state}")
                console.print()
                continue

            # ── /workflows ────────────────────────────────────────────────────
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

            # ── Unknown slash command ──────────────────────────────────────────
            if cmd.startswith("/"):
                console.print(
                    f"[dim]Unknown command. Type [bold cyan]/help[/bold cyan] for the command list.[/dim]"
                )
                console.print()
                continue

            # ── Normal prompt — stream response ───────────────────────────────
            try:
                await _stream_turn(console, orchestrator, user_input, trace=trace_mode)
            except KeyboardInterrupt:
                console.print("\n[dim]interrupted[/dim]")
            except Exception as e:
                console.print(_error_panel(str(e)))


def run_interactive(model: str | None = None) -> None:
    """Entry point for the interactive shell."""
    asyncio.run(_run_repl(model or config.MODEL))
