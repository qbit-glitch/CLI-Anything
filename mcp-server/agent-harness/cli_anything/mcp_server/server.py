"""
server.py — FastMCP server entry point for CLI-Anything.

Auto-discovers all installed cli-anything-* harnesses, introspects their
Click command trees, and registers each leaf command as a native MCP tool.
Also registers session-management tools and MCP Resources for SKILL.md files.
"""
from __future__ import annotations

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .discovery import discover_harnesses, find_cli_group
from .introspect import introspect_group
from .session_bridge import SessionBridge
from .resources import register_resources
from .pipelines import register_pipelines
from .utils import subprocess_runner

# registry.json lives at the repo root — 4 levels above this file's directory
# server.py  →  mcp_server/  →  cli_anything/  →  agent-harness/  →  mcp-server/  →  repo-root
REGISTRY_PATH = str(Path(__file__).parents[4] / "registry.json")

mcp = FastMCP(
    "cli-anything",
    instructions=(
        "CLI-Anything exposes desktop software CLIs (Blender, GIMP, Shotcut, etc.) "
        "as native MCP tools. Use blender_* tools for 3D work, gimp_* for image editing, "
        "shotcut_*/kdenlive_* for video, inkscape_* for SVG, audacity_* for audio, "
        "image3d_* for 2D→3D conversion, claude_code_* for AI session management. "
        "Use mcp_session_new(harness_name) to create a stateful session, then pass "
        "session_id to subsequent tools for stateful operations."
    ),
)

_bridge = SessionBridge()


def make_tool_handler(spec, bridge: SessionBridge, runner):
    """Create a closure-based async MCP tool handler for a ToolSpec.

    Using a factory function (not an inline lambda) to avoid the classic
    loop-variable late-binding bug.
    """

    async def handler(session_id: str = None, **kwargs) -> dict:  # type: ignore[assignment]
        project_path: str | None = None
        if session_id:
            try:
                project_path = bridge.get_project_path(session_id)
            except KeyError:
                return {"error": f"Session {session_id} not found"}
        return runner.run_cli_tool(
            spec.entry_point,
            spec.build_argv(kwargs),
            project_path,
        )

    handler.__name__ = spec.tool_name
    handler.__doc__ = spec.description
    return handler


def main() -> None:
    """Discover harnesses, register tools/resources, and start the MCP server."""
    harnesses = discover_harnesses(registry_path=REGISTRY_PATH)

    registered_tool_names: set[str] = set()
    for h in harnesses:
        try:
            group = find_cli_group(h)
            specs = introspect_group(group, h.name, [], entry_point=h.entry_point)
            for spec in specs:
                if spec.tool_name in registered_tool_names:
                    print(
                        f"Warning: tool name collision '{spec.tool_name}' "
                        f"(from {h.name}), skipping duplicate",
                        file=sys.stderr,
                    )
                    continue
                registered_tool_names.add(spec.tool_name)
                handler = make_tool_handler(spec, _bridge, subprocess_runner)
                mcp.add_tool(
                    handler,
                    name=spec.tool_name,
                    description=spec.description,
                )
        except Exception as exc:
            print(f"Warning: skipped {h.name}: {exc}", file=sys.stderr)

    # Session management tools
    @mcp.tool(description="Create a new stateful CLI-Anything session")
    def mcp_session_new(harness_name: str) -> dict:
        """Create a new stateful session for the named harness.

        Returns session_id to pass to subsequent tool calls.
        """
        session_id = _bridge.new_session(harness_name)
        return {"session_id": session_id, "harness": harness_name}

    @mcp.tool(description="List all active CLI-Anything sessions")
    def mcp_session_list() -> dict:
        """Return all active sessions."""
        return {"sessions": _bridge.list_sessions()}

    @mcp.tool(description="Delete a CLI-Anything session and its project file")
    def mcp_session_delete(session_id: str) -> dict:
        """Delete a session by its session_id."""
        _bridge.delete_session(session_id)
        return {"deleted": session_id}

    @mcp.tool(description="Clean up CLI-Anything sessions older than N hours")
    def mcp_session_cleanup(max_age_hours: int = 24) -> dict:
        """Remove stale sessions.  Returns count of removed sessions."""
        removed = _bridge.cleanup_stale(max_age_hours)
        return {"removed": removed}

    register_resources(mcp, harnesses, REGISTRY_PATH)
    register_pipelines(mcp, _bridge, subprocess_runner)

    # Report discovered harnesses to stderr for diagnostics
    harness_names = [h.name for h in harnesses]
    print(
        f"CLI-Anything MCP server: discovered {len(harnesses)} harness(es): "
        f"{', '.join(harness_names) or '(none)'}",
        file=sys.stderr,
    )

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
