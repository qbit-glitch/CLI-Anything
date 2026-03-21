"""
SKILL.md Generator for CLI-Anything

This module extracts metadata from CLI-Anything harnesses and generates
SKILL.md files following the skill-creator methodology.

The generated SKILL.md files contain:
- YAML frontmatter with name and description (triggering metadata)
- Markdown body with usage instructions
- Command documentation
- Examples for AI agents
"""

import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


def _format_display_name(name: str) -> str:
    """Format software name for display (replace underscores/hyphens with spaces, then title)."""
    return name.replace("_", " ").replace("-", " ").title()


@dataclass
class CommandInfo:
    """Information about a CLI command."""
    name: str
    description: str


@dataclass
class CommandGroup:
    """A group of related CLI commands."""
    name: str
    description: str
    commands: list[CommandInfo] = field(default_factory=list)


@dataclass
class Example:
    """An example of CLI usage."""
    title: str
    description: str
    code: str


@dataclass
class SkillMetadata:
    """Metadata extracted from a CLI-Anything harness."""
    skill_name: str
    skill_description: str
    software_name: str
    skill_intro: str
    version: str
    system_package: Optional[str] = None
    command_groups: list[CommandGroup] = field(default_factory=list)
    examples: list[Example] = field(default_factory=list)


def extract_cli_metadata(harness_path: str) -> SkillMetadata:
    """
    Extract metadata from a CLI-Anything harness directory.

    Args:
        harness_path: Path to the agent-harness directory

    Returns:
        SkillMetadata containing extracted information
    """
    harness_path = Path(harness_path)

    # Find the cli_anything/<software> directory
    cli_anything_dir = harness_path / "cli_anything"
    if not cli_anything_dir.exists():
        raise ValueError(
            f"cli_anything directory not found in {harness_path}. "
            "Ensure the harness structure includes cli_anything/<software>/"
        )
    software_dirs = [d for d in cli_anything_dir.iterdir()
                     if d.is_dir() and (d / "__init__.py").exists()]

    if not software_dirs:
        raise ValueError(f"No CLI package found in {harness_path}")

    software_dir = software_dirs[0]
    software_name = software_dir.name

    # Extract metadata from README.md
    readme_path = software_dir / "README.md"
    skill_intro = ""
    system_package = None

    if readme_path.exists():
        readme_content = readme_path.read_text(encoding="utf-8")
        skill_intro = extract_intro_from_readme(readme_content)
        system_package = extract_system_package(readme_content)

    # Extract version from setup.py
    setup_path = harness_path / "setup.py"
    version = "1.0.0"

    if setup_path.exists():
        version = extract_version_from_setup(setup_path)

    # Extract commands from CLI file
    cli_file = software_dir / f"{software_name}_cli.py"
    command_groups = []

    if cli_file.exists():
        command_groups = extract_commands_from_cli(cli_file)

    # Generate examples based on software type
    examples = generate_examples(software_name, command_groups)

    # Build skill name and description
    skill_name = f"cli-anything-{software_name}"
    skill_description = f"Command-line interface for {_format_display_name(software_name)} - {skill_intro[:100]}..."

    return SkillMetadata(
        skill_name=skill_name,
        skill_description=skill_description,
        software_name=software_name,
        skill_intro=skill_intro,
        version=version,
        system_package=system_package,
        command_groups=command_groups,
        examples=examples
    )


def extract_intro_from_readme(content: str) -> str:
    """Extract introduction text from README content."""
    # Find the first paragraph after the title
    lines = content.split("\n")
    intro_lines = []
    in_intro = False

    for line in lines:
        line = line.strip()
        if not line:
            if in_intro and intro_lines:
                break
            continue
        if line.startswith("# "):
            in_intro = True
            continue
        if line.startswith("##"):
            break
        if in_intro:
            intro_lines.append(line)

    return " ".join(intro_lines) or f"CLI interface for the software."


def extract_system_package(content: str) -> Optional[str]:
    """Extract system package installation command from README."""
    # Look for apt/brew install patterns
    patterns = [
        r"`apt install ([\w\-]+)`",
        r"`brew install ([\w\-]+)`",
        r"apt-get install ([\w\-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            package = match.group(1)
            if "apt" in pattern:
                return f"apt install {package}"
            elif "brew" in pattern:
                return f"brew install {package}"

    return None


def extract_version_from_setup(setup_path: Path) -> str:
    """Extract version from setup.py."""
    content = setup_path.read_text(encoding="utf-8")
    match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
    if match:
        return match.group(1)
    return "1.0.0"


def extract_commands_from_cli(cli_path: Path) -> list[CommandGroup]:
    """Extract command groups and commands from CLI file."""
    content = cli_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    groups = []

    # ---------------------------------------------------------------
    # Line-scanner approach: scan line-by-line for decorator blocks.
    # @xxx.group(...) and @xxx.command(...) always appear on a single
    # line in Click CLIs; subsequent @click.option(...) lines may have
    # nested parentheses so we skip them without regex matching.
    # ---------------------------------------------------------------

    # Patterns that apply only to the single trigger line
    _group_trigger = re.compile(r'^@(\w+)\.group\(')
    _cmd_trigger   = re.compile(r'^@(\w+)\.command\(')
    _def_line      = re.compile(r'^\s*def\s+(\w+)\s*\(')
    _decorator     = re.compile(r'^\s*@')

    def _docstring_after_def(start_idx: int) -> str:
        """Return the first docstring found after the def line at start_idx."""
        # Look ahead up to 3 lines for the opening triple-quote
        for offset in range(1, 4):
            if start_idx + offset >= len(lines):
                break
            stripped = lines[start_idx + offset].strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                q = '"""' if stripped.startswith('"""') else "'''"
                # Collect until closing triple-quote
                doc_lines = [stripped[3:]]
                if stripped.endswith(q) and len(stripped) > 3:
                    # Single-line docstring — slice off both opening and closing """
                    return stripped[3:-3].strip()
                for j in range(start_idx + offset + 1, min(start_idx + offset + 20, len(lines))):
                    l = lines[j]
                    if q in l:
                        doc_lines.append(l[:l.index(q)])
                        break
                    doc_lines.append(l)
                return " ".join(part.strip() for part in doc_lines if part.strip())
        return ""

    # Build group index: group_var_name → CommandGroup
    group_map: dict[str, CommandGroup] = {}

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # ---- group detection ----
        gm = _group_trigger.match(line)
        if gm:
            # Extract explicit string argument from @xxx.group("name") if present
            _group_name_arg = re.search(r'\.group\(\s*["\']([^"\']+)["\']', line)
            # Scan forward past additional decorators to reach def
            j = i + 1
            while j < len(lines) and _decorator.match(lines[j].strip()):
                j += 1
            dm = _def_line.match(lines[j].strip()) if j < len(lines) else None
            if dm:
                group_func_name = dm.group(1)
                # Skip root CLI entry points — these are not real command groups
                if group_func_name in ("cli", "main"):
                    i = j + 1
                    continue
                if _group_name_arg:
                    # Use the Click decorator's string argument as the canonical name
                    group_key_name = _group_name_arg.group(1)
                    group_name = group_key_name.replace("_", " ").replace("-", " ").title()
                else:
                    group_key_name = group_func_name
                    group_name = group_func_name.replace("_", " ").title()
                doc = _docstring_after_def(j)
                cg = CommandGroup(
                    name=group_name,
                    description=doc or f"Commands for {group_name.lower()} operations.",
                    commands=[]
                )
                groups.append(cg)
                # Map both the decorator key and the function name to the group
                group_map[group_key_name.lower().replace("-", "_")] = cg
                group_map[group_func_name.lower()] = cg
            i = j + 1
            continue

        # ---- command detection ----
        cm = _cmd_trigger.match(line)
        if cm:
            deco_group_var = cm.group(1).lower()
            # Extract explicit string argument from @xxx.command("name") if present
            _cmd_name_arg = re.search(r'\.command\(\s*["\']([^"\']+)["\']', line)
            # Scan forward past additional decorators to reach def
            j = i + 1
            while j < len(lines) and _decorator.match(lines[j].strip()):
                j += 1
            dm = _def_line.match(lines[j].strip()) if j < len(lines) else None
            if dm:
                cmd_func = dm.group(1)
                doc = _docstring_after_def(j)
                # Use Click decorator name when present, fall back to function name
                cmd_name = _cmd_name_arg.group(1) if _cmd_name_arg else cmd_func.replace("_", "-")
                cmd_info = CommandInfo(
                    name=cmd_name,
                    description=doc or f"Execute {cmd_func} operation."
                )
                # Match to group
                if deco_group_var in group_map:
                    group_map[deco_group_var].commands.append(cmd_info)
                else:
                    # Fallback: check groups list by normalised name
                    for grp in groups:
                        if grp.name.lower().replace(" ", "_") == deco_group_var:
                            grp.commands.append(cmd_info)
                            break
            i = j + 1
            continue

        i += 1

    # If no groups found, create a default group with all discovered commands
    if not groups:
        default_group = CommandGroup(
            name="General",
            description="General commands for the CLI.",
            commands=[]
        )
        # Re-scan for command defs without group context
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            cm = _cmd_trigger.match(line)
            if cm:
                j = i + 1
                while j < len(lines) and _decorator.match(lines[j].strip()):
                    j += 1
                dm = _def_line.match(lines[j].strip()) if j < len(lines) else None
                if dm:
                    cmd_func = dm.group(1)
                    doc = _docstring_after_def(j)
                    default_group.commands.append(CommandInfo(
                        name=cmd_func.replace("_", "-"),
                        description=doc or f"Execute {cmd_func} operation."
                    ))
                i = j + 1
                continue
            i += 1
        if default_group.commands:
            groups.append(default_group)

    return groups


def generate_examples(software_name: str, command_groups: list[CommandGroup]) -> list[Example]:
    """Generate usage examples based on software type and available commands."""
    examples = []

    # Basic project creation example
    examples.append(Example(
        title="Create a New Project",
        description=f"Create a new {software_name} project file.",
        code=f"""cli-anything-{software_name} project new -o myproject.json
# Or with JSON output for programmatic use
cli-anything-{software_name} --json project new -o myproject.json"""
    ))

    # REPL usage example
    examples.append(Example(
        title="Interactive REPL Session",
        description="Start an interactive session with undo/redo support.",
        code=f"""cli-anything-{software_name}
# Enter commands interactively
# Use 'help' to see available commands
# Use 'undo' and 'redo' for history navigation"""
    ))

    # Export example if export commands exist
    for group in command_groups:
        if "export" in group.name.lower():
            examples.append(Example(
                title="Export Project",
                description="Export the project to a final output format.",
                code=f"""cli-anything-{software_name} --project myproject.json export render output.pdf --overwrite"""
            ))
            break

    return examples


def generate_skill_md(metadata: SkillMetadata, template_path: Optional[str] = None) -> str:
    """
    Generate SKILL.md content from metadata using Jinja2 template.

    Args:
        metadata: SkillMetadata containing CLI information
        template_path: Optional path to custom template file

    Returns:
        Generated SKILL.md content as string
    """
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError:
        # Fallback to simple string formatting if Jinja2 not available
        return generate_skill_md_simple(metadata)

    # Load template
    if template_path is None:
        template_path = Path(__file__).parent / "templates" / "SKILL.md.template"
    else:
        template_path = Path(template_path)

    if not template_path.exists():
        return generate_skill_md_simple(metadata)

    env = Environment(loader=FileSystemLoader(template_path.parent))
    template = env.get_template(template_path.name)

    # Render template
    return template.render(
        skill_name=metadata.skill_name,
        skill_description=metadata.skill_description,
        software_name=metadata.software_name,
        skill_intro=metadata.skill_intro,
        version=metadata.version,
        system_package=metadata.system_package,
        command_groups=[{
            "name": g.name,
            "description": g.description,
            "commands": [{"name": c.name, "description": c.description} for c in g.commands]
        } for g in metadata.command_groups],
        examples=[{
            "title": e.title,
            "description": e.description,
            "code": e.code
        } for e in metadata.examples]
    )


def generate_skill_md_simple(metadata: SkillMetadata) -> str:
    """Generate SKILL.md without Jinja2 dependency."""
    lines = [
        "---",
        f'name: "{metadata.skill_name}"',
        f'description: "{metadata.skill_description}"',
        "---",
        "",
        f"# {metadata.skill_name}",
        "",
        metadata.skill_intro,
        "",
        "## Installation",
        "",
        f"This CLI is installed as part of the cli-anything-{metadata.software_name} package:",
        "",
        f"```bash",
        f"pip install cli-anything-{metadata.software_name}",
        f"```",
        "",
        "**Prerequisites:**",
        "- Python 3.10+",
        f"- {_format_display_name(metadata.software_name)} must be installed on your system",
    ]

    if metadata.system_package:
        lines.extend([
            f"- Install {metadata.software_name}: `{metadata.system_package}`"
        ])

    lines.extend([
        "",
        "## Usage",
        "",
        "### Basic Commands",
        "",
        "```bash",
        "# Show help",
        f"cli-anything-{metadata.software_name} --help",
        "",
        "# Start interactive REPL mode",
        f"cli-anything-{metadata.software_name}",
        "",
        "# Create a new project",
        f"cli-anything-{metadata.software_name} project new -o project.json",
        "",
        "# Run with JSON output (for agent consumption)",
        f"cli-anything-{metadata.software_name} --json project info -p project.json",
        "```",
        "",
    ])

    # Add command groups
    if metadata.command_groups:
        lines.append("## Command Groups")
        lines.append("")

        for group in metadata.command_groups:
            lines.append(f"### {group.name}")
            lines.append("")
            lines.append(group.description)
            lines.append("")

            if group.commands:
                lines.append("| Command | Description |")
                lines.append("|---------|-------------|")
                for cmd in group.commands:
                    lines.append(f"| `{cmd.name}` | {cmd.description} |")
                lines.append("")

    # Add examples
    if metadata.examples:
        lines.append("## Examples")
        lines.append("")

        for example in metadata.examples:
            lines.append(f"### {example.title}")
            lines.append("")
            lines.append(example.description)
            lines.append("")
            lines.append("```bash")
            lines.append(example.code)
            lines.append("```")
            lines.append("")

    # Add AI agent guidance
    lines.extend([
        "## For AI Agents",
        "",
        "When using this CLI programmatically:",
        "",
        "1. **Always use `--json` flag** for parseable output",
        "2. **Check return codes** - 0 for success, non-zero for errors",
        "3. **Parse stderr** for error messages on failure",
        "4. **Use absolute paths** for all file operations",
        "5. **Verify outputs exist** after export operations",
        "",
        "## Version",
        "",
        metadata.version,
    ])

    return "\n".join(lines)


def _group_prefixes(group_key: str) -> list[str]:
    """
    Return candidate prefixes to strip from a command key for a given group key.

    For a group key like "object_group", CLI functions are typically named
    "object_remove" (not "object_group_remove"), so we try both the full key
    and common short forms (strip trailing _group, _grp, _cmd suffixes).
    """
    candidates = [group_key]
    for suffix in ("_group", "_grp", "_cmd"):
        if group_key.endswith(suffix):
            candidates.append(group_key[: -len(suffix)])
    return candidates


def update_registry_commands(harness_path: str, registry_path: str) -> None:
    """
    Enrich a registry.json entry with mcp_tool_prefix and commands array.

    Reads the harness CLI metadata, builds a flat commands list from all
    command groups, then writes the enriched data back to registry.json.
    Safe to re-run — existing mcp_tool_prefix/commands fields are overwritten
    with fresh data (idempotent).

    Args:
        harness_path: Path to the agent-harness directory (e.g. "blender/agent-harness")
        registry_path: Path to registry.json

    Raises:
        ValueError: If the harness entry is not found in registry.json
        Exception: If extract_cli_metadata fails (re-raised with context)
    """
    import json

    # Step 1 — extract metadata (raises on failure with original exception + context)
    try:
        metadata = extract_cli_metadata(harness_path)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to extract CLI metadata from '{harness_path}': {exc}"
        ) from exc

    software_name = metadata.software_name

    # Step 2 — build flat commands array
    commands = []
    for group in metadata.command_groups:
        # Normalise group name: title-cased with spaces → lowercase underscores
        group_key = group.name.lower().replace(" ", "_")
        for cmd in group.commands:
            # Normalise command name: hyphens → underscores
            cmd_key = cmd.name.replace("-", "_")
            # Strip leading group prefix from cmd_key when present.
            # CLI function names often include the group name as a prefix
            # (e.g. "scene_new" in group "scene", "object_remove" in group "object_group").
            # We try the full group key first, then any trailing "_group"/"_grp" suffix
            # stripped variant, to avoid double-prefixes in the combined name.
            for candidate_prefix in _group_prefixes(group_key):
                pfx = candidate_prefix + "_"
                if cmd_key.startswith(pfx):
                    cmd_key = cmd_key[len(pfx):]
                    break
            # First line of docstring only, stripped
            description = cmd.description.splitlines()[0].strip()
            commands.append({
                "name": f"{group_key}_{cmd_key}",
                "group": group_key,
                "description": description,
            })

    # Step 3 — read registry.json
    registry_file = Path(registry_path)
    data = json.loads(registry_file.read_text(encoding="utf-8"))

    # Step 4 — locate entry
    entry = next(
        (e for e in data.get("clis", []) if e.get("name") == software_name),
        None,
    )
    if entry is None:
        raise ValueError(f"Harness '{software_name}' not found in registry.json")

    # Step 5 — update entry in-place (idempotent: overwrites on re-run)
    entry["mcp_tool_prefix"] = software_name
    entry["commands"] = commands

    # Step 6 — write back pretty-printed
    registry_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def generate_skill_file(harness_path: str, output_path: Optional[str] = None,
                        template_path: Optional[str] = None) -> str:
    """
    Generate a SKILL.md file for a CLI-Anything harness.

    Args:
        harness_path: Path to the agent-harness directory
        output_path: Optional output path for SKILL.md (default: cli_anything/<software>/skills/SKILL.md)
        template_path: Optional path to custom Jinja2 template

    Returns:
        Path to the generated SKILL.md file
    """
    # Extract metadata
    metadata = extract_cli_metadata(harness_path)

    # Generate content
    content = generate_skill_md(metadata, template_path)

    # Determine output path
    if output_path is None:
        # Default to skills/ directory under harness_path
        harness_path_obj = Path(harness_path)
        output_path = harness_path_obj / "cli_anything" / metadata.software_name / "skills" / "SKILL.md"
    else:
        output_path = Path(output_path)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write file
    output_path.write_text(content, encoding="utf-8")

    return str(output_path)


# CLI interface for standalone usage
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate SKILL.md for CLI-Anything harnesses"
    )
    parser.add_argument(
        "harness_path",
        nargs="?",
        help="Path to the agent-harness directory"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output path for SKILL.md (default: cli_anything/<software>/skills/SKILL.md)",
        default=None
    )
    parser.add_argument(
        "-t", "--template",
        help="Path to custom Jinja2 template",
        default=None
    )
    parser.add_argument(
        "--update-registry",
        nargs=2,
        metavar=("HARNESS_PATH", "REGISTRY_PATH"),
        help="Enrich a registry.json entry with mcp_tool_prefix and commands[]"
    )

    args = parser.parse_args()

    if args.update_registry:
        harness_path_arg, registry_path_arg = args.update_registry
        update_registry_commands(harness_path_arg, registry_path_arg)
        print(f"Registry updated for harness at '{harness_path_arg}'")
    elif args.harness_path:
        output_file = generate_skill_file(
            args.harness_path,
            args.output,
            args.template
        )
        print(f"Generated: {output_file}")
    else:
        parser.print_help()
