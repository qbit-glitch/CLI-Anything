"""
subprocess_runner.py — Invoke CLI-Anything harness commands via subprocess.
"""
from __future__ import annotations

import json
import shutil
import subprocess


def run_cli_tool(
    entry_point: str,
    argv: list[str],
    project_path: str | None = None,
    timeout: int = 60,
) -> dict:
    """Invoke a CLI-Anything harness command and return a normalised result dict.

    Args:
        entry_point:  Binary name, e.g. "cli-anything-blender".
        argv:         Subcommand + option tokens, e.g. ["scene", "new", "--name", "Foo"].
        project_path: If provided, appends ``--project <project_path>`` to the call.
        timeout:      Seconds before the subprocess is killed (default 60).

    Returns:
        ``{"success": bool, "data": dict, "error": str|None, "returncode": int}``
    """
    binary = shutil.which(entry_point)
    if not binary:
        return {
            "success": False,
            "data": {},
            "error": f"{entry_point} not found in PATH",
            "returncode": -1,
        }

    full_argv = [binary] + list(argv) + ["--json"]
    if project_path:
        full_argv += ["--project", project_path]

    try:
        result = subprocess.run(
            full_argv,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "data": {},
            "error": f"timed out after {timeout}s",
            "returncode": -1,
        }
    except Exception as exc:
        return {
            "success": False,
            "data": {},
            "error": str(exc),
            "returncode": -1,
        }

    # Try to parse stdout as JSON
    data: dict = {}
    stdout = result.stdout.strip()
    if stdout:
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, dict):
                data = parsed
            else:
                data = {"result": parsed}
        except json.JSONDecodeError:
            data = {"raw_output": stdout}

    success = result.returncode == 0
    error: str | None = None
    if not success:
        error = result.stderr.strip() or f"exited with code {result.returncode}"

    return {
        "success": success,
        "data": data,
        "error": error,
        "returncode": result.returncode,
    }
