# CLI-Anything MCP Server

## What It Does

The CLI-Anything MCP Server is a [FastMCP](https://github.com/jlowin/fastmcp) server that:

1. **Auto-discovers** all installed `cli-anything-*` packages by scanning `console_scripts` entry points.
2. **Introspects** each harness's Click command tree and converts every leaf command into a native MCP tool with a JSON Schema parameter definition.
3. **Exposes** SKILL.md files and `registry.json` as MCP Resources.
4. **Provides** session management tools so agents can maintain stateful project files across multiple tool calls.
5. **Ships** composite pipeline tools for common multi-CLI workflows (e.g. image→3D→Blender animation).

## Architecture

```
server.py          FastMCP setup, tool registration loop, session tools
discovery.py       Scan entry_points(group="console_scripts") for cli-anything-*
introspect.py      Walk Click Group tree → ToolSpec + JSON Schema
session_bridge.py  UUID session_id ↔ ~/.cli-anything-mcp/sessions/<id>.json
resources.py       skill://<name>, registry://all, harness://list resources
pipelines.py       Composite multi-CLI pipeline tools
utils/
  subprocess_runner.py  shutil.which + subprocess.run wrapper
```

## Tool Naming Convention

Every CLI leaf command becomes a tool named:

```
{harness}_{subcommand_path_with_underscores}
```

Examples:
- `blender scene new`      → `blender_scene_new`
- `gimp filter apply`      → `gimp_filter_apply`
- `audacity track delete`  → `audacity_track_delete`

## Session Management

Stateful operations require a session:

```
mcp_session_new(harness_name)   → {"session_id": "uuid", "harness": "blender"}
blender_scene_new(session_id=..., name="MyScene")
mcp_session_delete(session_id)
mcp_session_cleanup(max_age_hours=24)
```

Session project files live at `~/.cli-anything-mcp/sessions/<uuid>.json`.

## MCP Resources

| URI | Contents |
|-----|----------|
| `skill://<name>` | SKILL.md for the named harness |
| `registry://all` | Full `registry.json` |
| `harness://list` | JSON list of discovered harnesses |

## Installation

```bash
pip install git+https://github.com/HKUDS/CLI-Anything.git#subdirectory=mcp-server/agent-harness
```

Then register in `~/.claude/settings.json` (see SKILL.md).
