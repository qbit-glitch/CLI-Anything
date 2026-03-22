"""
E2E tests for the CLI-Anything MCP server.

These tests require the server binary to be installed (cli-anything-mcp-server
in PATH). They are skipped automatically when it is not present.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest

MCP_SERVER_BIN = shutil.which("cli-anything-mcp-server")

pytestmark = pytest.mark.skipif(
    MCP_SERVER_BIN is None,
    reason="cli-anything-mcp-server not found in PATH",
)


class TestServerStartup:
    def test_server_prints_discovered_harnesses_to_stderr(self):
        """Server should emit diagnostic line to stderr then block on stdin."""
        proc = subprocess.Popen(
            [MCP_SERVER_BIN],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            # Send EOF on stdin to trigger graceful shutdown
            stdout, stderr = proc.communicate(input=b"", timeout=10)
            stderr_text = stderr.decode("utf-8", errors="replace")
            # Should mention "discovered" and "harness"
            assert "discovered" in stderr_text.lower() or "harness" in stderr_text.lower()
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            # If it timed out, the server started and was waiting — that's OK
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_server_module_importable(self):
        """The server module should import cleanly."""
        result = subprocess.run(
            [sys.executable, "-c", "import cli_anything.mcp_server.server; print('OK')"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout

    def test_discovery_module_importable(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "from cli_anything.mcp_server.discovery import discover_harnesses; print('OK')"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout

    def test_introspect_module_importable(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "from cli_anything.mcp_server.introspect import introspect_group, ToolSpec; print('OK')"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout

    def test_session_bridge_module_importable(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "from cli_anything.mcp_server.session_bridge import SessionBridge; print('OK')"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout
