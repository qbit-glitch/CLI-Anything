"""
discovery.py — Scan installed packages for cli-anything-* entry points.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# This package's own console-script entry point — excluded from discovery by
# exact name (not prefix) to avoid self-registration and to prevent legitimate
# harnesses whose names start with "mcp" from being silently excluded.
_MCP_SERVER_ENTRY_POINT = "cli-anything-mcp-server"

# All CLI-Anything harnesses live under this namespace (project convention).
# Any module name that doesn't start with this prefix is rejected before import.
_ALLOWED_MODULE_NAMESPACE = "cli_anything."


def _validate_module_name(module_name: str) -> None:
    """Raise ValueError if module_name is outside the cli_anything namespace.

    This is a whitelist guard: only modules under the ``cli_anything.*``
    namespace are permitted to be imported.  All legitimate CLI-Anything
    harnesses use this namespace (see CLAUDE.md: Namespace Package Convention).
    """
    if not module_name.startswith(_ALLOWED_MODULE_NAMESPACE):
        raise ValueError(
            f"Module '{module_name}' is outside the '{_ALLOWED_MODULE_NAMESPACE}' "
            f"namespace. Only cli_anything.* modules are permitted."
        )


@dataclass
class HarnessInfo:
    name: str               # e.g. "blender"
    entry_point: str        # e.g. "cli-anything-blender"
    cli_module: str         # e.g. "cli_anything.blender.blender_cli"
    cli_attr: str           # e.g. "main" (the Click group function)
    skill_md_path: Optional[str] = None


def discover_harnesses(registry_path: str | None = None) -> list[HarnessInfo]:
    """Scan installed packages for cli-anything-* entry points.

    When *registry_path* is provided, only harnesses whose short names appear
    in registry.json are imported.  This is a supply-chain guard: it prevents
    a malicious package installed in the same virtualenv from being
    auto-imported at server startup just because its name starts with
    ``cli-anything-``.

    Module names are additionally validated against the ``cli_anything.*``
    namespace before any import occurs.

    The MCP server's own entry point is always excluded by exact name.
    """
    # Load allowed harness names from registry.json for supply-chain protection.
    allowed_names: set[str] | None = None
    if registry_path:
        try:
            reg = json.loads(Path(registry_path).read_text(encoding="utf-8"))
            allowed_names = {e["name"] for e in reg.get("clis", []) if "name" in e}
        except Exception as exc:
            print(
                f"Warning: could not load registry for harness whitelist: {exc}",
                file=sys.stderr,
            )

    eps = importlib.metadata.entry_points(group="console_scripts")
    harnesses: list[HarnessInfo] = []

    for ep in eps:
        if not ep.name.startswith("cli-anything-"):
            continue

        # Exclude this package's own entry point by exact name.
        if ep.name == _MCP_SERVER_ENTRY_POINT:
            continue

        # ep.value is e.g. "cli_anything.blender.blender_cli:main"
        if ":" not in ep.value:
            continue
        cli_module, cli_attr = ep.value.rsplit(":", 1)

        # Namespace whitelist: reject modules outside cli_anything.* before import.
        try:
            _validate_module_name(cli_module)
        except ValueError as exc:
            print(f"Warning: skipping '{ep.name}': {exc}", file=sys.stderr)
            continue

        # Derive harness name: strip "cli-anything-" prefix
        name = ep.name[len("cli-anything-"):]

        # Registry whitelist: skip entries not in registry.json.
        if allowed_names is not None and name not in allowed_names:
            print(
                f"Warning: skipping unlisted entry point '{ep.name}' "
                f"(not in registry.json) — add a registry entry to enable it",
                file=sys.stderr,
            )
            continue

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
    """Try to locate the SKILL.md file for a harness module.

    *cli_module* must already have been validated by ``_validate_module_name``
    before this function is called (enforced by ``discover_harnesses``).
    """
    # Secondary check: callers outside discover_harnesses must also validate.
    _validate_module_name(cli_module)
    try:
        mod = importlib.import_module(cli_module)  # nosemgrep
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

    Raises ValueError if *info.cli_module* is outside the cli_anything.*
    namespace (supply-chain guard).
    """
    import click

    # Namespace whitelist: reject imports outside cli_anything.* before import.
    _validate_module_name(info.cli_module)

    mod = importlib.import_module(info.cli_module)  # nosemgrep

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
