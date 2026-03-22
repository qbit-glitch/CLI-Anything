"""
introspect.py — Walk a Click command tree and emit ToolSpec objects with JSON Schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Parameters that the MCP wrapper injects itself — skip them during introspection.
_SKIP_PARAMS = {"help", "json", "project"}


@dataclass
class ToolSpec:
    tool_name: str          # e.g. "blender_scene_new"
    description: str
    parameters: dict        # JSON Schema object {"type":"object","properties":{...}}
    required: list[str]     # required parameter names
    cli_argv_prefix: list[str]  # e.g. ["scene", "new"]
    entry_point: str        # e.g. "cli-anything-blender"
    positional_params: list[str] = field(default_factory=list)  # click.Argument names

    def build_argv(self, kwargs: dict) -> list[str]:
        """Convert kwargs dict to CLI argv tokens.

        Parameters listed in ``positional_params`` are emitted as bare values
        (no ``--`` prefix) because they correspond to Click ``Argument``
        objects which are positional, not options.  All other parameters are
        emitted as ``--{name} {value}`` option pairs.
        """
        argv = list(self.cli_argv_prefix)
        for key, value in kwargs.items():
            if value is None:
                continue
            if key in self.positional_params:
                # Positional argument — bare value, no --prefix
                argv.append(str(value))
            else:
                param_name = key.replace("_", "-")
                if isinstance(value, bool):
                    if value:
                        argv.append(f"--{param_name}")
                elif isinstance(value, list):
                    for v in value:
                        argv.extend([f"--{param_name}", str(v)])
                else:
                    argv.extend([f"--{param_name}", str(value)])
        return argv


def introspect_group(group, harness: str, prefix: list[str], entry_point: str = "") -> list[ToolSpec]:
    """Recursively walk a Click Group tree, emitting a ToolSpec for each leaf command.

    Args:
        group:        A click.Group (or click.MultiCommand) instance.
        harness:      Short harness name, e.g. "blender".
        prefix:       Accumulated subcommand path, e.g. ["scene"].
        entry_point:  Binary entry-point name, e.g. "cli-anything-blender".
                      Passed through to every ToolSpec so callers do not need
                      to patch it afterwards.

    Returns:
        Flat list of ToolSpec objects for all leaf commands found.
    """
    import click

    specs: list[ToolSpec] = []

    if not hasattr(group, "commands"):
        return specs

    for cmd_name, cmd_obj in group.commands.items():
        if isinstance(cmd_obj, click.Group):
            # Recurse into sub-group, forwarding entry_point
            specs.extend(introspect_group(cmd_obj, harness, prefix + [cmd_name], entry_point=entry_point))
        elif isinstance(cmd_obj, click.Command):
            spec = _build_tool_spec(cmd_obj, cmd_name, harness, prefix, entry_point=entry_point)
            specs.append(spec)

    return specs


def _build_tool_spec(
    cmd: "click.Command",
    cmd_name: str,
    harness: str,
    prefix: list[str],
    entry_point: str = "",
) -> ToolSpec:
    """Build a ToolSpec for a single leaf Click command."""
    import click

    # tool_name: harness + "_" + full path joined with "_", dashes → underscores
    path_parts = prefix + [cmd_name]
    tool_name = harness + "_" + "_".join(p.replace("-", "_") for p in path_parts)

    description = cmd.help or ""

    properties: dict[str, dict] = {}
    required_params: list[str] = []
    positional_params: list[str] = []

    for param in cmd.params:
        name = param.name or ""
        if name in _SKIP_PARAMS:
            continue
        param_name, schema = click_param_to_schema(param)
        properties[param_name] = schema

        if isinstance(param, click.Argument):
            # Positional arguments: required when they have no default
            positional_params.append(param_name)
            if param.required:
                required_params.append(param_name)

    parameters = {
        "type": "object",
        "properties": properties,
    }

    return ToolSpec(
        tool_name=tool_name,
        description=description,
        parameters=parameters,
        required=required_params,
        cli_argv_prefix=path_parts,
        entry_point=entry_point,
        positional_params=positional_params,
    )


def click_param_to_schema(param) -> tuple[str, dict]:
    """Convert a Click parameter to (name, JSON schema property dict).

    Handles:
    - click.Option with is_flag      → bool
    - click.Option with type=Choice  → enum
    - click.Option with type=INT     → integer
    - click.Option with type=FLOAT   → number
    - click.Argument                 → string (required flagged by caller)
    - multiple=True                  → array of the base type
    - default                        → included when not None
    - help                           → included as description
    """
    import click

    name: str = param.name or ""
    schema: dict[str, Any] = {}

    # Determine base type
    base_type: str = "string"

    if hasattr(param, "is_flag") and param.is_flag:
        base_type = "boolean"
    elif param.type is not None:
        ct = param.type
        if ct == click.INT or ct is click.INT:
            base_type = "integer"
        elif ct == click.FLOAT or ct is click.FLOAT:
            base_type = "number"
        elif ct == click.BOOL or ct is click.BOOL:
            base_type = "boolean"
        elif isinstance(ct, click.Choice):
            base_type = "string"
            schema["enum"] = list(ct.choices)
        elif isinstance(ct, click.IntRange):
            base_type = "integer"
            if ct.min is not None:
                schema["minimum"] = ct.min
            if ct.max is not None:
                schema["maximum"] = ct.max
        elif isinstance(ct, click.FloatRange):
            base_type = "number"
            if ct.min is not None:
                schema["minimum"] = ct.min
            if ct.max is not None:
                schema["maximum"] = ct.max

    # Handle multiple=True → wrap in array
    if getattr(param, "multiple", False):
        schema["type"] = "array"
        schema["items"] = {"type": base_type}
    else:
        schema["type"] = base_type

    # Default value — skip None and Click's Sentinel.UNSET marker
    default = getattr(param, "default", None)
    if default is not None and not callable(default):
        try:
            from click._utils import Sentinel
            if isinstance(default, Sentinel):
                default = None
        except ImportError:
            # Older Click without Sentinel — fall through
            pass
    if default is not None:
        schema["default"] = default

    # Help text as description
    help_text = getattr(param, "help", None)
    if help_text:
        schema["description"] = help_text

    return name, schema
