"""
discovery.py — Scan installed packages for cli-anything-* entry points.
"""
from __future__ import annotations

import importlib
import importlib.metadata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class HarnessInfo:
    name: str               # e.g. "blender"
    entry_point: str        # e.g. "cli-anything-blender"
    cli_module: str         # e.g. "cli_anything.blender.blender_cli"
    cli_attr: str           # e.g. "main" (the Click group function)
    skill_md_path: Optional[str] = None


def discover_harnesses() -> list[HarnessInfo]:
    """Scan installed packages for cli-anything-* entry points.

    Filters to entries whose name starts with "cli-anything-" but NOT
    "cli-anything-mcp".  Returns a list of HarnessInfo objects.
    """
    eps = importlib.metadata.entry_points(group="console_scripts")
    harnesses: list[HarnessInfo] = []

    for ep in eps:
        if not ep.name.startswith("cli-anything-"):
            continue
        if ep.name.startswith("cli-anything-mcp"):
            continue

        # ep.value is e.g. "cli_anything.blender.blender_cli:main"
        if ":" not in ep.value:
            continue
        cli_module, cli_attr = ep.value.rsplit(":", 1)

        # Derive harness name: strip "cli-anything-" prefix
        name = ep.name[len("cli-anything-"):]

        skill_md_path = _find_skill_md(cli_module)

        harnesses.append(
            HarnessInfo(
                name=name,
                entry_point=ep.name,
                cli_module=cli_module,
                cli_attr=cli_attr,
                skill_md_path=skill_md_path,
            )
        )

    return harnesses


def _find_skill_md(cli_module: str) -> Optional[str]:
    """Try to locate the SKILL.md file for a harness by importing its module."""
    try:
        mod = importlib.import_module(cli_module)
        if not hasattr(mod, "__file__") or mod.__file__ is None:
            return None
        # Module lives at e.g. .../cli_anything/blender/blender_cli.py
        # SKILL.md is at  .../cli_anything/blender/skills/SKILL.md
        module_dir = Path(mod.__file__).parent
        candidate = module_dir / "skills" / "SKILL.md"
        if candidate.exists():
            return str(candidate)
    except Exception:
        pass
    return None


def find_cli_group(info: HarnessInfo):
    """Import harness module and return the root click.Group.

    Returns the click.Group object (NOT just the :main function) so that
    introspect_group can walk its command tree.
    """
    import click

    mod = importlib.import_module(info.cli_module)

    # First try the named attribute
    attr = getattr(mod, info.cli_attr, None)
    if isinstance(attr, click.Group):
        return attr

    # Walk all module-level names looking for a click.Group
    for name in dir(mod):
        obj = getattr(mod, name)
        if isinstance(obj, click.Group):
            return obj

    raise RuntimeError(
        f"No click.Group found in {info.cli_module} "
        f"(checked attr '{info.cli_attr}' and all module members)"
    )
