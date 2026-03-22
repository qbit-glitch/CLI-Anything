"""Tests for introspect.py — Click tree walker and JSON Schema generation."""
from __future__ import annotations

import click
import pytest

from cli_anything.mcp_server.introspect import (
    ToolSpec,
    click_param_to_schema,
    introspect_group,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_test_cli() -> click.Group:
    """Build a minimal nested Click CLI for testing."""

    @click.group()
    def cli():
        """Root CLI."""

    @cli.group("scene")
    def scene():
        """Scene commands."""

    @scene.command("new")
    @click.option("--name", help="Scene name")
    @click.option("--fps", type=int, default=24, help="Frame rate")
    @click.option("--verbose", is_flag=True, help="Verbose output")
    @click.option("--format", type=click.Choice(["png", "jpg", "exr"]), default="png")
    def scene_new(name, fps, verbose, format):
        """Create a new scene."""

    @scene.command("delete")
    @click.argument("scene_name")
    def scene_delete(scene_name):
        """Delete a scene by name."""

    @cli.command("render")
    @click.argument("output")
    @click.option("--quality", type=float, default=1.0, help="Render quality")
    def render(output, quality):
        """Render the current scene."""

    @cli.command("export")
    @click.option("--format", type=click.Choice(["glb", "obj", "fbx"]))
    @click.option("--tags", multiple=True, help="Tags to include")
    def export(format, tags):
        """Export the scene."""

    return cli


# ---------------------------------------------------------------------------
# Test: tool discovery
# ---------------------------------------------------------------------------

class TestIntrospectGroup:
    def setup_method(self):
        self.cli = make_test_cli()
        self.specs = introspect_group(self.cli, "test", [])
        self.by_name = {s.tool_name: s for s in self.specs}

    def test_discovers_nested_commands(self):
        names = {s.tool_name for s in self.specs}
        assert "test_scene_new" in names
        assert "test_scene_delete" in names
        assert "test_render" in names
        assert "test_export" in names

    def test_does_not_emit_groups_as_tools(self):
        names = {s.tool_name for s in self.specs}
        # "scene" is a group, not a command — should not appear
        assert "test_scene" not in names

    def test_cli_argv_prefix_for_nested(self):
        spec = self.by_name["test_scene_new"]
        assert spec.cli_argv_prefix == ["scene", "new"]

    def test_cli_argv_prefix_for_top_level(self):
        spec = self.by_name["test_render"]
        assert spec.cli_argv_prefix == ["render"]

    def test_description_from_help(self):
        spec = self.by_name["test_scene_new"]
        assert "new scene" in spec.description.lower()

    def test_returns_tool_spec_instances(self):
        for s in self.specs:
            assert isinstance(s, ToolSpec)

    def test_empty_group_returns_empty(self):
        @click.group()
        def empty():
            pass
        result = introspect_group(empty, "empty", [])
        assert result == []


# ---------------------------------------------------------------------------
# Test: JSON Schema generation
# ---------------------------------------------------------------------------

class TestJsonSchema:
    def setup_method(self):
        self.cli = make_test_cli()
        self.specs = introspect_group(self.cli, "test", [])
        self.by_name = {s.tool_name: s for s in self.specs}

    def test_integer_param(self):
        spec = self.by_name["test_scene_new"]
        props = spec.parameters["properties"]
        assert props["fps"]["type"] == "integer"

    def test_integer_default(self):
        spec = self.by_name["test_scene_new"]
        assert spec.parameters["properties"]["fps"]["default"] == 24

    def test_boolean_flag(self):
        spec = self.by_name["test_scene_new"]
        assert spec.parameters["properties"]["verbose"]["type"] == "boolean"

    def test_choice_param_has_enum(self):
        spec = self.by_name["test_scene_new"]
        fmt = spec.parameters["properties"]["format"]
        assert fmt["type"] == "string"
        assert set(fmt["enum"]) == {"png", "jpg", "exr"}

    def test_float_param(self):
        spec = self.by_name["test_render"]
        assert spec.parameters["properties"]["quality"]["type"] == "number"

    def test_multiple_param_is_array(self):
        spec = self.by_name["test_export"]
        tags = spec.parameters["properties"]["tags"]
        assert tags["type"] == "array"
        assert tags["items"]["type"] == "string"

    def test_parameters_schema_has_type_object(self):
        for spec in self.specs:
            assert spec.parameters["type"] == "object"

    def test_help_text_in_description(self):
        spec = self.by_name["test_scene_new"]
        fps_prop = spec.parameters["properties"]["fps"]
        assert "description" in fps_prop
        assert "Frame rate" in fps_prop["description"]


# ---------------------------------------------------------------------------
# Test: required parameters
# ---------------------------------------------------------------------------

class TestRequiredParams:
    def setup_method(self):
        self.cli = make_test_cli()
        self.specs = introspect_group(self.cli, "test", [])
        self.by_name = {s.tool_name: s for s in self.specs}

    def test_argument_is_required(self):
        spec = self.by_name["test_render"]
        assert "output" in spec.required

    def test_argument_is_required_delete(self):
        spec = self.by_name["test_scene_delete"]
        assert "scene_name" in spec.required

    def test_option_not_required(self):
        spec = self.by_name["test_scene_new"]
        assert "name" not in spec.required
        assert "fps" not in spec.required


# ---------------------------------------------------------------------------
# Test: click_param_to_schema directly
# ---------------------------------------------------------------------------

class TestClickParamToSchema:
    def test_string_option(self):
        @click.command()
        @click.option("--name", help="A name")
        def cmd(name):
            pass
        param = cmd.params[0]
        pname, schema = click_param_to_schema(param)
        assert pname == "name"
        assert schema["type"] == "string"
        assert schema["description"] == "A name"

    def test_int_option(self):
        @click.command()
        @click.option("--count", type=int, default=5)
        def cmd(count):
            pass
        param = cmd.params[0]
        _, schema = click_param_to_schema(param)
        assert schema["type"] == "integer"
        assert schema["default"] == 5

    def test_float_option(self):
        @click.command()
        @click.option("--scale", type=float)
        def cmd(scale):
            pass
        param = cmd.params[0]
        _, schema = click_param_to_schema(param)
        assert schema["type"] == "number"

    def test_flag_option(self):
        @click.command()
        @click.option("--debug", is_flag=True)
        def cmd(debug):
            pass
        param = cmd.params[0]
        _, schema = click_param_to_schema(param)
        assert schema["type"] == "boolean"

    def test_choice_option(self):
        @click.command()
        @click.option("--mode", type=click.Choice(["a", "b", "c"]))
        def cmd(mode):
            pass
        param = cmd.params[0]
        _, schema = click_param_to_schema(param)
        assert schema["type"] == "string"
        assert schema["enum"] == ["a", "b", "c"]

    def test_multiple_option(self):
        @click.command()
        @click.option("--tag", multiple=True)
        def cmd(tag):
            pass
        param = cmd.params[0]
        _, schema = click_param_to_schema(param)
        assert schema["type"] == "array"
        assert schema["items"]["type"] == "string"

    def test_no_default_when_none(self):
        @click.command()
        @click.option("--name")
        def cmd(name):
            pass
        param = cmd.params[0]
        _, schema = click_param_to_schema(param)
        assert "default" not in schema


# ---------------------------------------------------------------------------
# Test: ToolSpec.build_argv
# ---------------------------------------------------------------------------

class TestBuildArgv:
    def _make_spec(self, prefix):
        return ToolSpec(
            tool_name="test_tool",
            description="",
            parameters={"type": "object", "properties": {}},
            required=[],
            cli_argv_prefix=prefix,
            entry_point="cli-anything-test",
        )

    def test_basic_options(self):
        spec = self._make_spec(["scene", "new"])
        argv = spec.build_argv({"name": "MyScene", "fps": 30})
        assert argv[0] == "scene"
        assert argv[1] == "new"
        assert "--name" in argv
        assert "MyScene" in argv
        assert "--fps" in argv
        assert "30" in argv

    def test_boolean_flag_true(self):
        spec = self._make_spec(["render"])
        argv = spec.build_argv({"verbose": True})
        assert "--verbose" in argv

    def test_boolean_flag_false_omitted(self):
        spec = self._make_spec(["render"])
        argv = spec.build_argv({"verbose": False})
        assert "--verbose" not in argv

    def test_none_value_omitted(self):
        spec = self._make_spec(["scene", "new"])
        argv = spec.build_argv({"name": None, "fps": 24})
        assert "--name" not in argv

    def test_list_value_repeated(self):
        spec = self._make_spec(["export"])
        argv = spec.build_argv({"tags": ["a", "b"]})
        assert argv.count("--tags") == 2
        assert "a" in argv
        assert "b" in argv

    def test_underscore_to_dash_conversion(self):
        spec = self._make_spec(["text3d", "create"])
        argv = spec.build_argv({"output_path": "/tmp/out"})
        assert "--output-path" in argv
