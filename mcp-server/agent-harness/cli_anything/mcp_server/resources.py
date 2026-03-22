"""
resources.py — Register MCP Resources for SKILL.md files and registry.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .discovery import HarnessInfo


def _make_skill_reader(path: str):
    """Factory to avoid late-binding closure bug."""
    def read() -> str:
        return Path(path).read_text(encoding="utf-8")
    return read


def _make_harness_list_reader(harnesses: list):
    """Factory for harness list resource."""
    def read() -> str:
        return json.dumps(
            [
                {
                    "name": h.name,
                    "entry_point": h.entry_point,
                    "skill_md_path": h.skill_md_path,
                }
                for h in harnesses
            ],
            indent=2,
        )
    return read


def register_resources(mcp, harnesses: list, registry_path: str) -> None:
    """Register MCP Resources for every SKILL.md and for the registry.

    Resources registered:
    - ``skill://<name>``   for each harness that has a SKILL.md
    - ``registry://all``   full registry.json contents
    - ``harness://list``   JSON list of discovered harnesses
    """
    # Per-harness SKILL.md resources
    for h in harnesses:
        if h.skill_md_path and Path(h.skill_md_path).exists():
            mcp.resource(f"skill://{h.name}")(
                _make_skill_reader(h.skill_md_path)
            )

    # registry://all
    def read_registry() -> str:
        p = Path(registry_path)
        if p.exists():
            return p.read_text(encoding="utf-8")
        return json.dumps({"error": f"registry not found at {registry_path}"})

    mcp.resource("registry://all")(read_registry)

    # harness://list
    mcp.resource("harness://list")(_make_harness_list_reader(harnesses))
