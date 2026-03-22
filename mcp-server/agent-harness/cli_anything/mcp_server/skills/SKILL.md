---
name: cli-anything-mcp-server
version: "1.0.0"
description: >
  FastMCP server that auto-discovers all installed CLI-Anything harnesses and
  exposes their Click commands as native MCP tools with JSON Schema parameters.
entry_point: cli-anything-mcp-server
category: integration
requires: []
mcp_tool_prefix: mcp
---

# CLI-Anything MCP Server

## Installation

```bash
# Install the MCP server
pip install git+https://github.com/HKUDS/CLI-Anything.git#subdirectory=mcp-server/agent-harness

# Also install the harnesses you want to use, e.g.:
pip install git+https://github.com/HKUDS/CLI-Anything.git#subdirectory=blender/agent-harness
pip install git+https://github.com/HKUDS/CLI-Anything.git#subdirectory=gimp/agent-harness
```

## Register in Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "cli-anything": {
      "command": "cli-anything-mcp-server",
      "args": [],
      "env": {}
    }
  }
}
```

Or with `python -m`:

```json
{
  "mcpServers": {
    "cli-anything": {
      "command": "python3",
      "args": ["-m", "cli_anything.mcp_server"]
    }
  }
}
```

## Tool Naming Pattern

Every CLI leaf command is exposed as:

```
{harness}_{subcommand_path_with_underscores}
```

| CLI invocation | MCP tool name |
|---|---|
| `cli-anything-blender scene new` | `blender_scene_new` |
| `cli-anything-gimp filter apply` | `gimp_filter_apply` |
| `cli-anything-shotcut project open` | `shotcut_project_open` |
| `cli-anything-audacity track delete` | `audacity_track_delete` |
| `cli-anything-inkscape svg export` | `inkscape_svg_export` |
| `cli-anything-image3d generate` | `image3d_generate` |
| `cli-anything-claude-code prompt run` | `claude_code_prompt_run` |

## Session Management Tools

| Tool | Description |
|---|---|
| `mcp_session_new(harness_name)` | Create a new stateful session, returns `session_id` |
| `mcp_session_list()` | List all active sessions |
| `mcp_session_delete(session_id)` | Delete a session and its project file |
| `mcp_session_cleanup(max_age_hours)` | Remove sessions older than N hours |

## MCP Resources

| URI | Contents |
|---|---|
| `skill://<harness>` | SKILL.md for the named harness |
| `registry://all` | Full `registry.json` with all 14+ harnesses |
| `harness://list` | JSON list of currently discovered harnesses |

## Pipeline Tools

| Tool | Description |
|---|---|
| `pipeline_image_to_3d_animation` | image3d generate → blender import-mesh → rotation keyframes |
| `pipeline_text_to_video` | blender text3d create → render animation → output |

## Example Agent Workflow

```python
# 1. Create a Blender session
result = mcp.call_tool("mcp_session_new", {"harness_name": "blender"})
sid = result["session_id"]

# 2. Create a scene
mcp.call_tool("blender_scene_new", {"session_id": sid, "name": "MyScene"})

# 3. Add a cube and animate it
mcp.call_tool("blender_object_add", {"session_id": sid, "type": "cube"})
mcp.call_tool("blender_animation_keyframe", {
    "session_id": sid,
    "property": "location[0]",
    "frame": 1,
    "value": 0.0
})

# 4. Clean up
mcp.call_tool("mcp_session_delete", {"session_id": sid})
```
