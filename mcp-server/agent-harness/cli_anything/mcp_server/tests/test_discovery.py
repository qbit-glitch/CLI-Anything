"""Tests for discovery.py — harness scanning via entry_points."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cli_anything.mcp_server.discovery import discover_harnesses, HarnessInfo


def _make_ep(name: str, value: str) -> MagicMock:
    ep = MagicMock()
    ep.name = name
    ep.value = value
    return ep


class TestDiscoverHarnesses:
    def test_discovers_cli_anything_entry_point(self):
        mock_ep = _make_ep("cli-anything-blender", "cli_anything.blender.blender_cli:main")
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            result = discover_harnesses()
        assert len(result) == 1
        h = result[0]
        assert h.name == "blender"
        assert h.entry_point == "cli-anything-blender"
        assert h.cli_module == "cli_anything.blender.blender_cli"
        assert h.cli_attr == "main"

    def test_excludes_non_cli_anything_entry_points(self):
        eps = [
            _make_ep("pytest", "pytest:main"),
            _make_ep("pip", "pip._internal.cli.main:main"),
            _make_ep("cli-anything-blender", "cli_anything.blender.blender_cli:main"),
        ]
        with patch("importlib.metadata.entry_points", return_value=eps):
            result = discover_harnesses()
        assert len(result) == 1
        assert result[0].name == "blender"

    def test_excludes_mcp_server_itself(self):
        eps = [
            _make_ep("cli-anything-mcp-server", "cli_anything.mcp_server.server:main"),
            _make_ep("cli-anything-blender", "cli_anything.blender.blender_cli:main"),
        ]
        with patch("importlib.metadata.entry_points", return_value=eps):
            result = discover_harnesses()
        names = [h.name for h in result]
        assert "mcp-server" not in names
        assert "blender" in names

    def test_multiple_harnesses_discovered(self):
        eps = [
            _make_ep("cli-anything-blender", "cli_anything.blender.blender_cli:main"),
            _make_ep("cli-anything-gimp", "cli_anything.gimp.gimp_cli:main"),
            _make_ep("cli-anything-shotcut", "cli_anything.shotcut.shotcut_cli:main"),
        ]
        with patch("importlib.metadata.entry_points", return_value=eps):
            result = discover_harnesses()
        assert len(result) == 3
        names = {h.name for h in result}
        assert names == {"blender", "gimp", "shotcut"}

    def test_entry_point_without_colon_skipped(self):
        ep = _make_ep("cli-anything-bad", "no_colon_here")
        with patch("importlib.metadata.entry_points", return_value=[ep]):
            result = discover_harnesses()
        assert len(result) == 0

    def test_empty_entry_points_returns_empty(self):
        with patch("importlib.metadata.entry_points", return_value=[]):
            result = discover_harnesses()
        assert result == []

    def test_harness_info_is_dataclass(self):
        eps = [_make_ep("cli-anything-gimp", "cli_anything.gimp.gimp_cli:main")]
        with patch("importlib.metadata.entry_points", return_value=eps):
            result = discover_harnesses()
        assert isinstance(result[0], HarnessInfo)

    def test_skill_md_path_is_none_when_module_not_importable(self):
        ep = _make_ep("cli-anything-fake", "cli_anything.fake.fake_cli:main")
        with patch("importlib.metadata.entry_points", return_value=[ep]):
            result = discover_harnesses()
        # Module doesn't exist, so skill_md_path should be None (no crash)
        assert result[0].skill_md_path is None

    def test_mcp_prefix_variants_excluded(self):
        """All cli-anything-mcp* variants should be excluded."""
        eps = [
            _make_ep("cli-anything-mcp-server", "cli_anything.mcp_server.server:main"),
            _make_ep("cli-anything-mcp-proxy", "cli_anything.mcp_proxy.proxy:main"),
            _make_ep("cli-anything-blender", "cli_anything.blender.blender_cli:main"),
        ]
        with patch("importlib.metadata.entry_points", return_value=eps):
            result = discover_harnesses()
        assert len(result) == 1
        assert result[0].name == "blender"
