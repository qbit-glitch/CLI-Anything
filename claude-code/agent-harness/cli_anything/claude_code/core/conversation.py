"""Conversation state management for Claude Code CLI harness."""

from dataclasses import dataclass, field
from typing import Optional
import json
import uuid
from pathlib import Path
from datetime import datetime


@dataclass
class ConversationState:
    session_id: str
    model: str
    messages: list  # list of {"role": str, "content": str}
    system_prompt: Optional[str] = None
    tool_calls: list = field(default_factory=list)
    total_tokens: int = 0
    metadata: dict = field(default_factory=dict)


def create_conversation(
    model: str = "claude-sonnet-4-6",
    system_prompt: Optional[str] = None,
) -> dict:
    """Create a new conversation state dict."""
    return {
        "session_id": str(uuid.uuid4()),
        "model": model,
        "messages": [],
        "system_prompt": system_prompt,
        "tool_calls": [],
        "total_tokens": 0,
        "metadata": {
            "created": datetime.now().isoformat(),
            "modified": datetime.now().isoformat(),
        },
    }


def append_message(
    conv: dict,
    role: str,
    content: str,
    tool_calls: Optional[list] = None,
) -> None:
    """Append a message to conversation history."""
    msg: dict = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    }
    if tool_calls:
        msg["tool_calls"] = tool_calls
        conv.setdefault("tool_calls", []).extend(tool_calls)
    conv["messages"].append(msg)
    conv["metadata"]["modified"] = datetime.now().isoformat()


def _content_char_count(content) -> int:
    """Return approximate character count of a message content value.

    Handles both plain strings and Claude API list-of-blocks format
    (e.g. tool-use responses where content is a list of dicts).
    Using str() on a list produces Python repr with brackets/quotes that
    wildly overcounts the actual text content.
    """
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(
            len(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return len(str(content))


def estimate_tokens(conv: dict) -> int:
    """Rough token estimate: sum of len(content)//4 for all messages."""
    total = 0
    if conv.get("system_prompt"):
        total += len(conv["system_prompt"]) // 4
    for msg in conv.get("messages", []):
        total += _content_char_count(msg.get("content", "")) // 4
    return total


def trim_to_context_window(conv: dict, max_tokens: int = 100_000) -> dict:
    """Remove oldest non-system messages until within token budget.

    Returns a new conv dict (does not mutate in-place).
    """
    import copy
    trimmed = copy.deepcopy(conv)
    while estimate_tokens(trimmed) > max_tokens and trimmed["messages"]:
        trimmed["messages"].pop(0)
    return trimmed


def export_transcript(conv: dict, path: str) -> str:
    """Save conversation as markdown. Return resolved path.

    Raises ValueError if *path* resolves outside the user's home directory,
    preventing path-traversal writes to system files.
    """
    import tempfile

    out_path = Path(path).resolve()
    home = Path.home().resolve()
    tmp = Path(tempfile.gettempdir()).resolve()
    if not out_path.is_relative_to(home) and not out_path.is_relative_to(tmp):
        raise ValueError(
            f"export_transcript: path must be within home or temp directory, got {out_path}"
        )

    lines = [
        "# Conversation Transcript",
        "",
        f"**Session:** {conv.get('session_id', 'unknown')}",
        f"**Model:** {conv.get('model', 'unknown')}",
        f"**Created:** {conv.get('metadata', {}).get('created', '')}",
        "",
    ]
    if conv.get("system_prompt"):
        lines += [
            "## System Prompt",
            "",
            conv["system_prompt"],
            "",
        ]
    lines.append("## Messages")
    lines.append("")
    for msg in conv.get("messages", []):
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        ts = msg.get("timestamp", "")
        lines.append(f"### {role}  _{ts}_")
        lines.append("")
        lines.append(content if isinstance(content, str) else str(content))
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return str(out_path)
