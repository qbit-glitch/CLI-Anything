"""MCP server configuration management for Claude Code CLI harness.

Manages the mcpServers section of ~/.claude/settings.json using
fcntl.flock for atomic read-modify-write operations.
"""

import json
import os
from pathlib import Path
from typing import Optional

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


def _load_settings(settings_path: Path) -> dict:
    """Load settings.json, returning empty dict if missing or invalid."""
    if not settings_path.exists():
        return {}
    try:
        return json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _atomic_write_settings(settings_path: Path, data: dict) -> None:
    """Write settings.json crash-safely via tmp file + atomic replace.

    Replaces the previous in-place truncate approach which could corrupt
    settings.json on SIGKILL between truncate() and flush().
    """
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2)
    tmp = settings_path.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(settings_path)
    finally:
        # Clean up tmp file if replace failed (e.g. permission error)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def list_mcp_servers(settings_path: Optional[str] = None) -> list:
    """List all configured MCP servers.

    Returns a list of dicts, each with 'name' plus the server config fields.
    """
    path = Path(settings_path) if settings_path else SETTINGS_PATH
    settings = _load_settings(path)
    servers = settings.get("mcpServers", {})
    result = []
    for name, config in servers.items():
        entry = {"name": name}
        entry.update(config)
        result.append(entry)
    return result


def add_mcp_server(
    name: str,
    command: str,
    args: Optional[list] = None,
    env: Optional[dict] = None,
    settings_path: Optional[str] = None,
) -> None:
    """Add or update an MCP server entry in settings.json."""
    path = Path(settings_path) if settings_path else SETTINGS_PATH
    settings = _load_settings(path)
    servers = settings.setdefault("mcpServers", {})

    server_config: dict = {"command": command}
    if args:
        server_config["args"] = args
    if env:
        server_config["env"] = env

    servers[name] = server_config
    _atomic_write_settings(path, settings)


def remove_mcp_server(
    name: str,
    settings_path: Optional[str] = None,
) -> None:
    """Remove an MCP server entry from settings.json.

    Raises KeyError if the server is not found.
    """
    path = Path(settings_path) if settings_path else SETTINGS_PATH
    settings = _load_settings(path)
    servers = settings.get("mcpServers", {})

    if name not in servers:
        raise KeyError(f"MCP server '{name}' not found in settings.")

    del servers[name]
    settings["mcpServers"] = servers
    _atomic_write_settings(path, settings)
