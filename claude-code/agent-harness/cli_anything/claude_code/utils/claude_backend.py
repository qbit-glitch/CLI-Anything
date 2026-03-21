"""Claude Code backend — subprocess wrapper for the `claude` binary.

Finds the claude CLI via shutil.which() and invokes it headlessly,
returning structured dicts. Raises RuntimeError with install
instructions if claude is not found.
"""

import shutil
import subprocess
import json
from typing import Optional


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
    result = subprocess.run(
        [claude, "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
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

    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        return {
            "error": result.stderr.strip() or result.stdout.strip(),
            "returncode": result.returncode,
            "command": " ".join(argv),
        }

    stdout = result.stdout.strip()
    try:
        parsed = json.loads(stdout)
        parsed["returncode"] = result.returncode
        parsed["command"] = " ".join(argv)
        return parsed
    except (json.JSONDecodeError, ValueError):
        return {
            "result": stdout,
            "returncode": result.returncode,
            "command": " ".join(argv),
        }


def list_sessions() -> list:
    """List resumable sessions. Returns list of session dicts."""
    try:
        claude = find_claude()
    except RuntimeError:
        return []

    result = subprocess.run(
        [claude, "session", "list", "--output-format", "json"],
        capture_output=True,
        text=True,
        timeout=15,
    )

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
