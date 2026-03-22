---
name: claude-code
version: 1.0.0
entry_point: cli-anything-claude-code
description: Programmatic control of Claude Code sessions — run prompts, manage conversations, configure MCP servers and agents.
supported_models:
  - claude-sonnet-4-6
  - claude-opus-4-5
  - claude-haiku-3-5
---

# Claude Code CLI Skill

Wraps the `claude` binary to give AI agents a stateful, structured interface
for running Claude Code sessions programmatically.

## Command Groups

### session
Manage conversation sessions.
- `session new [--model MODEL] [--system PROMPT]` — create a new session
- `session list` — list backend + local sessions
- `session resume --session-id ID` — resume an existing session
- `session info [--session-id ID]` — show current session details
- `session delete --session-id ID` — delete a session

### prompt
Run a single prompt non-interactively.
- `prompt TEXT [--model MODEL] [--system PROMPT] [--continue] [--permission-mode MODE]`

### tool
Tool management.
- `tool list` — list available Claude Code tools
- `tool call NAME ARGS_JSON` — call a tool by name

### agent
Manage named agent configurations with custom system prompts.
- `agent list` — list saved agents
- `agent create NAME --system PROMPT [--model MODEL]` — create agent
- `agent delete NAME` — remove agent

### mcp
Manage MCP server entries in `~/.claude/settings.json`.
- `mcp list` — list configured MCP servers
- `mcp add NAME COMMAND [ARGS...] [--env KEY=VALUE]` — add server
- `mcp remove NAME` — remove server

### config
Simple key-value CLI configuration.
- `config get KEY` — read a value
- `config set KEY VALUE` — write a value
- `config list` — list all values

### undo / redo
- `undo` — undo last conversation mutation
- `redo` — redo last undone mutation

## REPL Mode

Run `cli-anything-claude-code` with no arguments to enter the interactive REPL
with history, autocomplete, and the Anthropic purple accent theme.

## Examples

```bash
# Quick prompt
cli-anything-claude-code prompt "Explain async/await in Python"

# Continuing a session
cli-anything-claude-code session new --model claude-sonnet-4-6
cli-anything-claude-code prompt "What is 2+2?" --continue

# Add an MCP server
cli-anything-claude-code mcp add filesystem npx -- -y @modelcontextprotocol/server-filesystem /tmp

# Create a coding agent
cli-anything-claude-code agent create coder \
  --system "You are an expert Python developer. Always write tests." \
  --model claude-sonnet-4-6
```
