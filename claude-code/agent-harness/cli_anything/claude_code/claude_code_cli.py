#!/usr/bin/env python3
"""Claude Code CLI — Stateful programmatic control of Claude Code sessions.

Usage:
    # One-shot prompt
    cli-anything-claude-code prompt "Write a hello world in Python"

    # Session management
    cli-anything-claude-code session new --model claude-sonnet-4-6
    cli-anything-claude-code session list

    # MCP server management
    cli-anything-claude-code mcp list
    cli-anything-claude-code mcp add myserver npx -- -y @myorg/mcp-server

    # Interactive REPL
    cli-anything-claude-code
"""

import sys
import os
import json
import click
from typing import Optional

from cli_anything.claude_code.core.session import Session
from cli_anything.claude_code.core import conversation as conv_mod
from cli_anything.claude_code.core import agents as agents_mod
from cli_anything.claude_code.core import mcp_config as mcp_mod

# Global session state
_session: Optional[Session] = None
_json_output = False
_repl_mode = False


def get_session() -> Session:
    global _session
    if _session is None:
        _session = Session()
    return _session


def output(data, message: str = ""):
    if _json_output:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        if message:
            click.echo(message)
        if isinstance(data, dict):
            _print_dict(data)
        elif isinstance(data, list):
            _print_list(data)
        else:
            click.echo(str(data))


def _print_dict(d: dict, indent: int = 0):
    prefix = "  " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            click.echo(f"{prefix}{k}:")
            _print_dict(v, indent + 1)
        elif isinstance(v, list):
            click.echo(f"{prefix}{k}:")
            _print_list(v, indent + 1)
        else:
            click.echo(f"{prefix}{k}: {v}")


def _print_list(items: list, indent: int = 0):
    prefix = "  " * indent
    for i, item in enumerate(items):
        if isinstance(item, dict):
            click.echo(f"{prefix}[{i}]")
            _print_dict(item, indent + 1)
        else:
            click.echo(f"{prefix}- {item}")


def handle_error(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError as e:
            if _json_output:
                click.echo(json.dumps({"error": str(e), "type": "file_not_found"}))
            else:
                click.echo(f"Error: {e}", err=True)
            if not _repl_mode:
                sys.exit(1)
        except (ValueError, IndexError, RuntimeError) as e:
            if _json_output:
                click.echo(json.dumps({"error": str(e), "type": type(e).__name__}))
            else:
                click.echo(f"Error: {e}", err=True)
            if not _repl_mode:
                sys.exit(1)
        except KeyError as e:
            if _json_output:
                click.echo(json.dumps({"error": str(e), "type": "key_error"}))
            else:
                click.echo(f"Error: {e}", err=True)
            if not _repl_mode:
                sys.exit(1)
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


# ── Main CLI Group ──────────────────────────────────────────────
@click.group(invoke_without_command=True)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cli(ctx, use_json):
    """Claude Code CLI — Programmatic control of AI sessions.

    Run without a subcommand to enter interactive REPL mode.
    """
    global _json_output
    _json_output = use_json

    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


# ── Session Commands ──────────────────────────────────────────────
@cli.group("session")
def session_group():
    """Conversation session management commands."""
    pass


@session_group.command("new")
@click.option("--model", "-m", default="claude-sonnet-4-6", help="Model to use")
@click.option("--system", "-s", default=None, help="System prompt")
@handle_error
def session_new(model, system):
    """Create new conversation session."""
    sess = get_session()
    conv = conv_mod.create_conversation(model=model, system_prompt=system)
    sess.set_project(conv)
    output(sess.status(), f"New session created: {conv['session_id']}")


@session_group.command("list")
@handle_error
def session_list():
    """List all sessions (backend + local)."""
    from cli_anything.claude_code.utils.claude_backend import list_sessions
    sessions = list_sessions()
    sess = get_session()
    local = sess.status()
    result = {
        "local_session": local,
        "backend_sessions": sessions,
    }
    output(result, f"Found {len(sessions)} backend session(s)")


@session_group.command("resume")
@click.option("--session-id", "-i", required=True, help="Session ID to resume")
@handle_error
def session_resume(session_id):
    """Resume a session by ID."""
    sess = get_session()
    conv = conv_mod.create_conversation()
    conv["session_id"] = session_id
    sess.set_project(conv)
    output(sess.status(), f"Resumed session: {session_id}")


@session_group.command("info")
@click.option("--session-id", "-i", default=None, help="Session ID (default: current)")
@handle_error
def session_info(session_id):
    """Show session info."""
    sess = get_session()
    proj = sess.get_project()
    if session_id and proj.get("session_id") != session_id:
        output({"error": f"Session {session_id} not loaded"})
        return
    info = {
        "session_id": proj.get("session_id"),
        "model": proj.get("model"),
        "message_count": len(proj.get("messages", [])),
        "estimated_tokens": conv_mod.estimate_tokens(proj),
        "system_prompt": proj.get("system_prompt"),
        "metadata": proj.get("metadata", {}),
    }
    output(info)


@session_group.command("delete")
@click.option("--session-id", "-i", required=True, help="Session ID to delete")
@handle_error
def session_delete(session_id):
    """Delete a session (resets local state if it matches)."""
    sess = get_session()
    proj = sess.get_project()
    if proj.get("session_id") == session_id:
        new_conv = conv_mod.create_conversation()
        sess.set_project(new_conv)
        output({"deleted": session_id, "new_session_id": new_conv["session_id"]},
               f"Deleted session {session_id}, started fresh")
    else:
        output({"error": f"Session {session_id} is not the current session"})


# ── Prompt Command ──────────────────────────────────────────────
@cli.command("prompt")
@click.argument("text")
@click.option("--model", "-m", default=None, help="Model override")
@click.option("--system", "-s", default=None, help="System prompt")
@click.option("--continue", "continue_session", is_flag=True,
              help="Continue current session (pass session_id to backend)")
@click.option("--permission-mode", default=None,
              type=click.Choice(["default", "acceptEdits", "bypassPermissions"]),
              help="Permission mode")
@click.option("--stream", is_flag=True, help="Stream output (not yet implemented)")
@handle_error
def prompt_cmd(text, model, system, continue_session, permission_mode, stream):
    """Run a prompt non-interactively."""
    from cli_anything.claude_code.utils.claude_backend import run_prompt

    sess = get_session()
    proj = sess.get_project()

    # Use the backend session ID (set from a prior successful call), not the local UUID
    backend_session_id = proj.get("backend_session_id") if continue_session else None
    effective_model = model or proj.get("model", "claude-sonnet-4-6")
    effective_system = system or proj.get("system_prompt")

    sess.snapshot("before prompt")

    result = run_prompt(
        prompt=text,
        model=effective_model,
        system_prompt=effective_system,
        session_id=backend_session_id,
        permission_mode=permission_mode,
    )

    if result.get("error"):
        # Backend failed — revert the snapshot, do not pollute history
        sess.undo()
        output(result)
        return

    # Only record history after a successful backend response
    conv_mod.append_message(proj, "user", text)

    # Persist backend session ID for future --continue calls
    if result.get("session_id"):
        proj["backend_session_id"] = result["session_id"]

    # Capture assistant response from result
    response_text = (
        result.get("result")
        or result.get("content")
        or result.get("response")
        or ""
    )
    if response_text:
        conv_mod.append_message(proj, "assistant", str(response_text))

    output(result)


# ── Tool Commands ──────────────────────────────────────────────
@cli.group("tool")
def tool_group():
    """Tool management commands."""
    pass


@tool_group.command("list")
@handle_error
def tool_list():
    """List available tools."""
    tools = [
        {"name": "Bash", "description": "Execute bash commands"},
        {"name": "Read", "description": "Read files"},
        {"name": "Write", "description": "Write files"},
        {"name": "Edit", "description": "Edit files"},
        {"name": "Glob", "description": "Find files by pattern"},
        {"name": "Grep", "description": "Search file contents"},
        {"name": "WebSearch", "description": "Search the web"},
        {"name": "WebFetch", "description": "Fetch web content"},
        {"name": "TodoRead", "description": "Read todo list"},
        {"name": "TodoWrite", "description": "Write todo list"},
    ]
    output(tools, f"{len(tools)} tools available")


@tool_group.command("call")
@click.argument("name")
@click.argument("args_json")
@handle_error
def tool_call(name, args_json):
    """Call a tool by name with JSON args."""
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON args: {e}")
    output({"tool": name, "args": args, "note": "Direct tool calls require a running session"})


# ── Agent Commands ──────────────────────────────────────────────
@cli.group("agent")
def agent_group():
    """Agent configuration commands."""
    pass


@agent_group.command("list")
@handle_error
def agent_list():
    """List configured agents."""
    agents = agents_mod.list_agents()
    output(agents, f"{len(agents)} agent(s) configured")


@agent_group.command("create")
@click.argument("name")
@click.option("--system", "-s", required=True, help="System prompt for the agent")
@click.option("--model", "-m", default="claude-sonnet-4-6", help="Model to use")
@click.option("--allowed-tools", default=None, help="Comma-separated allowed tools")
@click.option("--disallowed-tools", default=None, help="Comma-separated disallowed tools")
@click.option("--permission-mode", default="default",
              type=click.Choice(["default", "acceptEdits", "bypassPermissions"]))
@handle_error
def agent_create(name, system, model, allowed_tools, disallowed_tools, permission_mode):
    """Create new agent config."""
    allowed = [t.strip() for t in allowed_tools.split(",")] if allowed_tools else []
    disallowed = [t.strip() for t in disallowed_tools.split(",")] if disallowed_tools else []
    agent = agents_mod.create_agent(
        name=name,
        system_prompt=system,
        model=model,
        allowed_tools=allowed,
        disallowed_tools=disallowed,
        permission_mode=permission_mode,
    )
    path = agents_mod.save_agent(agent)
    output({"agent": agent, "saved_to": path}, f"Agent '{name}' created")


@agent_group.command("delete")
@click.argument("name")
@handle_error
def agent_delete(name):
    """Delete agent config."""
    agents_mod.delete_agent(name)
    output({"deleted": name}, f"Agent '{name}' deleted")


# ── MCP Commands ──────────────────────────────────────────────
@cli.group("mcp")
def mcp_group():
    """MCP server configuration commands."""
    pass


@mcp_group.command("list")
@handle_error
def mcp_list():
    """List MCP servers."""
    servers = mcp_mod.list_mcp_servers()
    output(servers, f"{len(servers)} MCP server(s) configured")


@mcp_group.command("add")
@click.argument("name")
@click.argument("command")
@click.argument("args", nargs=-1)
@click.option("--env", multiple=True, help="Env var in KEY=VALUE format")
@handle_error
def mcp_add(name, command, args, env):
    """Add MCP server. Usage: mcp add NAME COMMAND [ARGS...]"""
    env_dict = {}
    for e in env:
        if "=" in e:
            k, v = e.split("=", 1)
            env_dict[k] = v
    mcp_mod.add_mcp_server(
        name=name,
        command=command,
        args=list(args) if args else None,
        env=env_dict if env_dict else None,
    )
    output({"added": name, "command": command, "args": list(args)},
           f"MCP server '{name}' added")


@mcp_group.command("remove")
@click.argument("name")
@handle_error
def mcp_remove(name):
    """Remove MCP server."""
    mcp_mod.remove_mcp_server(name)
    output({"removed": name}, f"MCP server '{name}' removed")


# ── Config Commands ──────────────────────────────────────────────
@cli.group("config")
def config_group():
    """CLI configuration commands."""
    pass


_CONFIG_PATH = os.path.expanduser("~/.claude/cli_anything_config.json")


def _load_config(path: str = _CONFIG_PATH) -> dict:
    """Load config from disk; return empty dict if missing or invalid."""
    import json as _json
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _save_config(data: dict, path: str = _CONFIG_PATH) -> None:
    """Atomically write config to disk using fcntl.flock when available."""
    import json as _json
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        f = open(path, "r+", encoding="utf-8")
    except FileNotFoundError:
        f = open(path, "w", encoding="utf-8")
    with f:
        _locked = False
        try:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            _locked = True
        except (ImportError, OSError):
            pass
        try:
            f.seek(0)
            f.truncate()
            _json.dump(data, f, indent=2)
            f.flush()
        finally:
            if _locked:
                import fcntl as _fcntl
                _fcntl.flock(f.fileno(), _fcntl.LOCK_UN)


@config_group.command("get")
@click.argument("key")
@handle_error
def config_get(key):
    """Get a config value."""
    store = _load_config()
    value = store.get(key)
    if value is None:
        output({"key": key, "value": None, "note": "Not set"})
    else:
        output({"key": key, "value": value})


@config_group.command("set")
@click.argument("key")
@click.argument("value")
@handle_error
def config_set(key, value):
    """Set a config value."""
    store = _load_config()
    store[key] = value
    _save_config(store)
    output({"key": key, "value": value}, f"Set {key}={value}")


@config_group.command("list")
@handle_error
def config_list():
    """List all config values."""
    store = _load_config()
    output(store, f"{len(store)} config value(s)")


# ── Undo / Redo ──────────────────────────────────────────────
@cli.command("undo")
@handle_error
def undo():
    """Undo last operation."""
    sess = get_session()
    desc = sess.undo()
    output({"undone": desc or "(unnamed)"}, f"Undone: {desc or '(unnamed)'}")


@cli.command("redo")
@handle_error
def redo():
    """Redo last undone operation."""
    sess = get_session()
    desc = sess.redo()
    output({"redone": desc or "(unnamed)"}, f"Redone: {desc or '(unnamed)'}")


# ── REPL ──────────────────────────────────────────────
@cli.command("repl")
@handle_error
def repl():
    """Start interactive REPL session."""
    from cli_anything.claude_code.utils.repl_skin import ReplSkin

    global _repl_mode
    _repl_mode = True

    skin = ReplSkin("claude_code", version="1.0.0")
    skin.print_banner()

    pt_session = skin.create_prompt_session()

    _repl_commands = {
        "session":  "new|list|resume|info|delete",
        "prompt":   "TEXT [--model] [--system] [--continue] [--permission-mode]",
        "tool":     "list|call",
        "agent":    "list|create|delete",
        "mcp":      "list|add|remove",
        "config":   "get|set|list",
        "undo":     "undo last operation",
        "redo":     "redo last undone operation",
        "help":     "show this help",
        "quit":     "exit REPL",
    }

    while True:
        try:
            sess = get_session()
            project_name = ""
            modified = False
            if sess.has_project():
                proj = sess.project
                if proj:
                    project_name = proj.get("session_id", "")[:8]
                modified = sess._modified

            line = skin.get_input(
                pt_session, project_name=project_name, modified=modified
            ).strip()
            if not line:
                continue
            if line.lower() in ("quit", "exit", "q"):
                skin.print_goodbye()
                break
            if line.lower() == "help":
                skin.help(_repl_commands)
                continue

            args = line.split()
            try:
                cli.main(args, standalone_mode=False)
            except SystemExit:
                pass
            except click.exceptions.UsageError as e:
                skin.warning(f"Usage error: {e}")
            except Exception as e:
                skin.error(str(e))

        except (EOFError, KeyboardInterrupt):
            skin.print_goodbye()
            break

    _repl_mode = False


# ── Entry Point ──────────────────────────────────────────────
def main():
    cli()


if __name__ == "__main__":
    main()
