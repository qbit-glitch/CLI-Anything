"""Tests for resources.py — MCP Resource registration."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli_anything.mcp_server.resources import register_resources
from cli_anything.mcp_server.discovery import HarnessInfo


def _make_harness(name: str, skill_path: str | None = None) -> HarnessInfo:
    return HarnessInfo(
        name=name,
        entry_point=f"cli-anything-{name}",
        cli_module=f"cli_anything.{name}.{name}_cli",
        cli_attr="main",
        skill_md_path=skill_path,
    )


class TestRegisterResources:
    def test_registers_skill_resource_for_harness_with_skill_md(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# Test Skill")

        harness = _make_harness("blender", str(skill_file))
        mcp = MagicMock()
        registered_uris = []

        def mock_resource(uri, **kwargs):
            registered_uris.append(uri)
            def decorator(fn):
                return fn
            return decorator

        mcp.resource = mock_resource
        register_resources(mcp, [harness], str(tmp_path / "registry.json"))
        assert "skill://blender" in registered_uris

    def test_skips_skill_resource_when_no_skill_md(self, tmp_path):
        harness = _make_harness("blender", skill_path=None)
        mcp = MagicMock()
        registered_uris = []

        def mock_resource(uri, **kwargs):
            registered_uris.append(uri)
            def decorator(fn):
                return fn
            return decorator

        mcp.resource = mock_resource
        register_resources(mcp, [harness], str(tmp_path / "registry.json"))
        assert "skill://blender" not in registered_uris

    def test_skips_skill_resource_when_file_missing(self, tmp_path):
        harness = _make_harness("blender", str(tmp_path / "nonexistent.md"))
        mcp = MagicMock()
        registered_uris = []

        def mock_resource(uri, **kwargs):
            registered_uris.append(uri)
            def decorator(fn):
                return fn
            return decorator

        mcp.resource = mock_resource
        register_resources(mcp, [harness], str(tmp_path / "registry.json"))
        assert "skill://blender" not in registered_uris

    def test_always_registers_registry_all(self, tmp_path):
        mcp = MagicMock()
        registered_uris = []

        def mock_resource(uri, **kwargs):
            registered_uris.append(uri)
            def decorator(fn):
                return fn
            return decorator

        mcp.resource = mock_resource
        register_resources(mcp, [], str(tmp_path / "registry.json"))
        assert "registry://all" in registered_uris

    def test_always_registers_harness_list(self, tmp_path):
        mcp = MagicMock()
        registered_uris = []

        def mock_resource(uri, **kwargs):
            registered_uris.append(uri)
            def decorator(fn):
                return fn
            return decorator

        mcp.resource = mock_resource
        register_resources(mcp, [], str(tmp_path / "registry.json"))
        assert "harness://list" in registered_uris

    def test_skill_reader_returns_file_content(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# My Skill Content")
        harness = _make_harness("blender", str(skill_file))

        readers = {}
        mcp = MagicMock()

        def mock_resource(uri, **kwargs):
            def decorator(fn):
                readers[uri] = fn
                return fn
            return decorator

        mcp.resource = mock_resource
        register_resources(mcp, [harness], str(tmp_path / "registry.json"))
        content = readers["skill://blender"]()
        assert content == "# My Skill Content"

    def test_registry_reader_returns_file_content(self, tmp_path):
        reg_file = tmp_path / "registry.json"
        reg_file.write_text('{"clis": []}')

        readers = {}
        mcp = MagicMock()

        def mock_resource(uri, **kwargs):
            def decorator(fn):
                readers[uri] = fn
                return fn
            return decorator

        mcp.resource = mock_resource
        register_resources(mcp, [], str(reg_file))
        content = readers["registry://all"]()
        assert '"clis"' in content

    def test_registry_reader_handles_missing_file(self, tmp_path):
        readers = {}
        mcp = MagicMock()

        def mock_resource(uri, **kwargs):
            def decorator(fn):
                readers[uri] = fn
                return fn
            return decorator

        mcp.resource = mock_resource
        register_resources(mcp, [], str(tmp_path / "nonexistent.json"))
        content = readers["registry://all"]()
        parsed = json.loads(content)
        assert "error" in parsed

    def test_harness_list_reader_returns_json(self, tmp_path):
        h1 = _make_harness("blender")
        h2 = _make_harness("gimp")

        readers = {}
        mcp = MagicMock()

        def mock_resource(uri, **kwargs):
            def decorator(fn):
                readers[uri] = fn
                return fn
            return decorator

        mcp.resource = mock_resource
        register_resources(mcp, [h1, h2], str(tmp_path / "registry.json"))
        content = readers["harness://list"]()
        parsed = json.loads(content)
        names = [h["name"] for h in parsed]
        assert "blender" in names
        assert "gimp" in names

    def test_multiple_harnesses_register_multiple_skills(self, tmp_path):
        skill1 = tmp_path / "skill1.md"
        skill1.write_text("# Blender")
        skill2 = tmp_path / "skill2.md"
        skill2.write_text("# GIMP")

        h1 = _make_harness("blender", str(skill1))
        h2 = _make_harness("gimp", str(skill2))

        registered_uris = []
        mcp = MagicMock()

        def mock_resource(uri, **kwargs):
            registered_uris.append(uri)
            def decorator(fn):
                return fn
            return decorator

        mcp.resource = mock_resource
        register_resources(mcp, [h1, h2], str(tmp_path / "registry.json"))
        assert "skill://blender" in registered_uris
        assert "skill://gimp" in registered_uris
