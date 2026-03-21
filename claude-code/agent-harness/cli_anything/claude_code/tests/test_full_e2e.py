"""End-to-end tests for Claude Code CLI harness.

All tests in this module require the `claude` binary to be installed.
They are skipped automatically when claude is not found.
"""

import shutil
import pytest

pytestmark = pytest.mark.skipif(
    not shutil.which("claude"),
    reason="claude binary not installed — skipping E2E tests",
)


class TestBackendE2E:

    def test_find_claude(self):
        from cli_anything.claude_code.utils.claude_backend import find_claude
        path = find_claude()
        assert path is not None
        assert "claude" in path.lower()

    def test_get_version(self):
        from cli_anything.claude_code.utils.claude_backend import get_version
        result = get_version()
        assert "version" in result
        assert result["returncode"] == 0
        assert result["version"] is not None

    def test_list_sessions(self):
        from cli_anything.claude_code.utils.claude_backend import list_sessions
        sessions = list_sessions()
        # May be empty list — just check it's a list
        assert isinstance(sessions, list)

    def test_run_prompt_basic(self):
        from cli_anything.claude_code.utils.claude_backend import run_prompt
        result = run_prompt(
            prompt="Reply with exactly: PONG",
            model="claude-haiku-3-5",
            timeout=60,
        )
        assert isinstance(result, dict)
        assert result.get("returncode") == 0 or "error" not in result

    def test_run_prompt_with_system(self):
        from cli_anything.claude_code.utils.claude_backend import run_prompt
        result = run_prompt(
            prompt="What is your role?",
            model="claude-haiku-3-5",
            system_prompt="You are a helpful test assistant. Keep answers to one sentence.",
            timeout=60,
        )
        assert isinstance(result, dict)

    def test_run_prompt_invalid_model(self):
        from cli_anything.claude_code.utils.claude_backend import run_prompt
        result = run_prompt(
            prompt="Hello",
            model="claude-nonexistent-model",
            timeout=30,
        )
        # Should return error dict, not raise
        assert isinstance(result, dict)


class TestCliE2E:

    def test_cli_help(self):
        """CLI --help should exit 0 and list all command groups."""
        from click.testing import CliRunner
        from cli_anything.claude_code.claude_code_cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "session" in result.output
        assert "prompt" in result.output
        assert "mcp" in result.output
        assert "agent" in result.output

    def test_session_new_e2e(self):
        from click.testing import CliRunner
        from cli_anything.claude_code.claude_code_cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["session", "new", "--model", "claude-haiku-3-5"])
        assert result.exit_code == 0

    def test_prompt_e2e(self):
        from click.testing import CliRunner
        from cli_anything.claude_code.claude_code_cli import cli
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(cli, ["--json", "prompt", "Reply with: OK"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert isinstance(data, dict)
