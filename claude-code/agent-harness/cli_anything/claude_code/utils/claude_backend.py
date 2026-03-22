"""Claude Code backend — subprocess wrapper for the `claude` binary.

Finds the claude CLI via shutil.which() and invokes it headlessly,
returning structured dicts. Raises RuntimeError with install
instructions if claude is not found.
"""

import shutil
import subprocess
import json
from typing import Optional


def _safe_command_str(argv: list) -> str:
    """Return argv as a display string with the -p prompt value redacted.

    Prevents sensitive prompt content (e.g. API keys, passwords) from being
    stored verbatim in response dicts, logs, or session history.
    """
    result = []
    i = 0
    while i < len(argv):
        if argv[i] == "-p" and i + 1 < len(argv):
            result.append("-p")
            result.append("<prompt>")
            i += 2
        else:
            result.append(argv[i])
            i += 1
    return " ".join(result)


def find_claude() -> str:
    """Find claude binary. Raises RuntimeError if not found."""
    path = shutil.which("claude")
    if not path:
        raise RuntimeError(
            "Claude Code is not installed. Install it from: https://claude.ai/code"
        )
    return path


def get_version() -> dict:
    """Get claude version string."""
    claude = find_claude()
    try:
        result = subprocess.run(
            [claude, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return {"error": "claude timed out after 10s", "returncode": -1}
    return {
        "command": f"{claude} --version",
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "version": result.stdout.strip() if result.returncode == 0 else None,
    }


def run_prompt(
    prompt: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    session_id: Optional[str] = None,
    allowed_tools: Optional[list] = None,
    disallowed_tools: Optional[list] = None,
    permission_mode: Optional[str] = None,
    append_system_prompt: Optional[str] = None,
    timeout: int = 120,
) -> dict:
    """Run a prompt non-interactively. Returns parsed JSON result.

    Builds: claude -p "..." --output-format json [options]
    If session_id: claude -r {session_id} -p "..." --output-format json
    """
    claude = find_claude()
    argv = [claude]

    # Resume existing session
    if session_id:
        argv += ["-r", session_id]

    # The prompt
    argv += ["-p", prompt]

    # Output format
    argv += ["--output-format", "json"]

    # Model override
    if model:
        argv += ["--model", model]

    # System prompt (full replacement)
    if system_prompt:
        argv += ["--system-prompt", system_prompt]

    # Append to system prompt
    if append_system_prompt:
        argv += ["--append-system-prompt", append_system_prompt]

    # Tool allowlist
    if allowed_tools:
        argv += ["--allowedTools", ",".join(allowed_tools)]

    # Tool denylist
    if disallowed_tools:
        argv += ["--disallowedTools", ",".join(disallowed_tools)]

    # Permission mode (default | acceptEdits | bypassPermissions)
    if permission_mode:
        argv += ["--permission-mode", permission_mode]

    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"claude timed out after {timeout}s", "returncode": -1}

    if result.returncode != 0:
        return {
            "error": result.stderr.strip() or result.stdout.strip(),
            "returncode": result.returncode,
            "command": _safe_command_str(argv),
        }

    stdout = result.stdout.strip()
    try:
        parsed = json.loads(stdout)
        parsed["returncode"] = result.returncode
        parsed["command"] = _safe_command_str(argv)
        return parsed
    except (json.JSONDecodeError, ValueError):
        return {
            "result": stdout,
            "returncode": result.returncode,
            "command": _safe_command_str(argv),
        }


def list_sessions() -> list:
    """List resumable sessions. Returns list of session dicts."""
    try:
        claude = find_claude()
    except RuntimeError:
        return []

    try:
        result = subprocess.run(
            [claude, "session", "list", "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return []

    if result.returncode != 0:
        return []

    stdout = result.stdout.strip()
    if not stdout:
        return []

    try:
        data = json.loads(stdout)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "sessions" in data:
            return data["sessions"]
        return []
    except (json.JSONDecodeError, ValueError):
        return []
