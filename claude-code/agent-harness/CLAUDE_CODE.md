# Claude Code CLI Harness

This harness wraps the `claude` binary to give AI agents (and humans) a stateful,
structured interface for running Claude Code sessions programmatically.

## Quick Start

```bash
# Install
cd claude-code/agent-harness && pip install -e ".[dev]"

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
```

## Architecture

Three-layer pattern:

1. **CLI layer** (`claude_code_cli.py`) — Click CLI with REPL, global `_session`, `--json` flag
2. **Core layer** (`core/`) — Pure logic: conversation state, session undo/redo, agent configs, MCP config
3. **Utils layer** (`utils/claude_backend.py`) — Subprocess wrapper for the `claude` binary

## Session Files

Sessions are saved as JSON to `~/.cli-anything-claude_code/sessions/`. Each session
contains conversation history, model, system prompt, and token estimates.

## MCP Config

`core/mcp_config.py` reads/writes `~/.claude/settings.json` with `fcntl.flock` for
atomic updates. Use `cli-anything-claude-code mcp add/remove` to manage MCP servers.
