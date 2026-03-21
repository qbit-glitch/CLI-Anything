"""Agent configuration management for Claude Code CLI harness."""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import json

CLAUDE_DIR = Path.home() / ".claude"


@dataclass
class Agent:
    name: str
    system_prompt: str
    model: str = "claude-sonnet-4-6"
    allowed_tools: list = field(default_factory=list)
    disallowed_tools: list = field(default_factory=list)
    permission_mode: str = "default"


def create_agent(
    name: str,
    system_prompt: str,
    model: str = "claude-sonnet-4-6",
    allowed_tools: Optional[list] = None,
    disallowed_tools: Optional[list] = None,
    permission_mode: str = "default",
) -> dict:
    """Create a new agent config dict."""
    return {
        "name": name,
        "system_prompt": system_prompt,
        "model": model,
        "allowed_tools": allowed_tools or [],
        "disallowed_tools": disallowed_tools or [],
        "permission_mode": permission_mode,
    }


def _agents_dir(config_dir: Optional[str] = None) -> Path:
    base = Path(config_dir) if config_dir else CLAUDE_DIR
    agents_path = base / "cli_anything_agents"
    agents_path.mkdir(parents=True, exist_ok=True)
    return agents_path


def list_agents(config_dir: Optional[str] = None) -> list:
    """List all saved agent configs."""
    d = _agents_dir(config_dir)
    agents = []
    for f in sorted(d.glob("*.json")):
        try:
            agents.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return agents


def save_agent(agent: dict, config_dir: Optional[str] = None) -> str:
    """Save an agent config to disk. Returns path."""
    d = _agents_dir(config_dir)
    name = agent["name"]
    # Sanitize name for filename
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    path = d / f"{safe_name}.json"
    path.write_text(json.dumps(agent, indent=2), encoding="utf-8")
    return str(path)


def delete_agent(name: str, config_dir: Optional[str] = None) -> None:
    """Delete an agent config by name. Raises FileNotFoundError if not found."""
    d = _agents_dir(config_dir)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    path = d / f"{safe_name}.json"
    if not path.exists():
        # Try scanning all files for matching name field
        for f in d.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("name") == name:
                    f.unlink()
                    return
            except (json.JSONDecodeError, OSError):
                pass
        raise FileNotFoundError(f"Agent '{name}' not found.")
    path.unlink()
