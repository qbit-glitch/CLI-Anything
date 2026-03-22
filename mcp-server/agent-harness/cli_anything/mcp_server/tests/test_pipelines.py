"""Tests for pipelines.py — composite multi-CLI pipeline tools."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from cli_anything.mcp_server.session_bridge import SessionBridge
from cli_anything.mcp_server.pipelines import register_pipelines


def _make_bridge_mock():
    """Create a mock SessionBridge with predictable session IDs."""
    bridge = MagicMock(spec=SessionBridge)
    _counter = {"n": 0}

    def new_session(harness, project_path=None):
        _counter["n"] += 1
        return f"mock-session-{_counter['n']:03d}"

    def get_project_path(sid):
        return f"/mock/projects/{sid}.json"

    bridge.new_session.side_effect = new_session
    bridge.get_project_path.side_effect = get_project_path
    return bridge


def _make_runner_mock(success=True, data=None):
    runner = MagicMock()
    runner.run_cli_tool.return_value = {
        "success": success,
        "data": data or {},
        "error": None,
        "returncode": 0,
    }
    return runner


class TestRegisterPipelines:
    def _collect_tools(self, bridge, runner):
        """Register pipelines on a collecting mock and return tool functions."""
        tools = {}
        mcp = MagicMock()

        def mock_tool(**kwargs):
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn
            return decorator

        mcp.tool = mock_tool
        register_pipelines(mcp, bridge, runner)
        return tools

    def test_registers_image_to_3d_animation(self):
        bridge = _make_bridge_mock()
        runner = _make_runner_mock()
        tools = self._collect_tools(bridge, runner)
        assert "pipeline_image_to_3d_animation" in tools

    def test_registers_text_to_video(self):
        bridge = _make_bridge_mock()
        runner = _make_runner_mock()
        tools = self._collect_tools(bridge, runner)
        assert "pipeline_text_to_video" in tools

    def test_image_to_3d_calls_image3d_first(self):
        bridge = _make_bridge_mock()
        runner = _make_runner_mock(data={"output_path": "/tmp/mesh.glb"})
        tools = self._collect_tools(bridge, runner)

        tools["pipeline_image_to_3d_animation"](
            image_path="/tmp/photo.jpg",
            output_dir="/tmp/out",
        )

        first_call = runner.run_cli_tool.call_args_list[0]
        assert first_call[0][0] == "cli-anything-image3d"
        assert "generate" in first_call[0][1]

    def test_image_to_3d_calls_blender_import_second(self):
        bridge = _make_bridge_mock()
        runner = _make_runner_mock(data={"output_path": "/tmp/mesh.glb"})
        tools = self._collect_tools(bridge, runner)

        tools["pipeline_image_to_3d_animation"](
            image_path="/tmp/photo.jpg",
            output_dir="/tmp/out",
        )

        second_call = runner.run_cli_tool.call_args_list[1]
        assert second_call[0][0] == "cli-anything-blender"
        assert "import-mesh" in second_call[0][1]

    def test_image_to_3d_stops_on_image3d_failure(self):
        bridge = _make_bridge_mock()
        runner = MagicMock()
        runner.run_cli_tool.return_value = {
            "success": False,
            "data": {},
            "error": "image3d failed",
            "returncode": 1,
        }
        tools = self._collect_tools(bridge, runner)

        result = tools["pipeline_image_to_3d_animation"](
            image_path="/tmp/photo.jpg",
            output_dir="/tmp/out",
        )

        assert result["success"] is False
        assert result["step"] == "image3d"
        # Should only have been called once (image3d step)
        assert runner.run_cli_tool.call_count == 1

    def test_image_to_3d_returns_session_id(self):
        bridge = _make_bridge_mock()
        runner = _make_runner_mock(data={"output_path": "/tmp/mesh.glb"})
        tools = self._collect_tools(bridge, runner)

        result = tools["pipeline_image_to_3d_animation"](
            image_path="/tmp/photo.jpg",
            output_dir="/tmp/out",
        )

        assert "session_id" in result

    def test_image_to_3d_returns_results_dict(self):
        bridge = _make_bridge_mock()
        runner = _make_runner_mock(data={"output_path": "/tmp/mesh.glb"})
        tools = self._collect_tools(bridge, runner)

        result = tools["pipeline_image_to_3d_animation"](
            image_path="/tmp/photo.jpg",
            output_dir="/tmp/out",
        )

        assert "results" in result
        assert "image3d" in result["results"]

    def test_text_to_video_calls_blender_text3d(self):
        bridge = _make_bridge_mock()
        runner = _make_runner_mock()
        tools = self._collect_tools(bridge, runner)

        tools["pipeline_text_to_video"](
            text="Hello World",
            output_path="/tmp/out.mp4",
        )

        first_call = runner.run_cli_tool.call_args_list[0]
        assert first_call[0][0] == "cli-anything-blender"
        argv = first_call[0][1]
        assert "text3d" in argv or "create" in argv

    def test_text_to_video_stops_on_blender_failure(self):
        bridge = _make_bridge_mock()
        runner = MagicMock()
        runner.run_cli_tool.return_value = {
            "success": False,
            "data": {},
            "error": "blender not found",
            "returncode": 1,
        }
        tools = self._collect_tools(bridge, runner)

        result = tools["pipeline_text_to_video"](
            text="Hello",
            output_path="/tmp/out.mp4",
        )

        assert result["success"] is False

    def test_text_to_video_returns_session_id(self):
        bridge = _make_bridge_mock()
        runner = _make_runner_mock()
        tools = self._collect_tools(bridge, runner)

        result = tools["pipeline_text_to_video"](
            text="Hello",
            output_path="/tmp/out.mp4",
        )

        assert "session_id" in result

    def test_image_to_3d_creates_two_sessions(self):
        bridge = _make_bridge_mock()
        runner = _make_runner_mock(data={"output_path": "/tmp/mesh.glb"})
        tools = self._collect_tools(bridge, runner)

        tools["pipeline_image_to_3d_animation"](
            image_path="/tmp/photo.jpg",
            output_dir="/tmp/out",
        )

        # image3d session + blender session
        assert bridge.new_session.call_count == 2
        harness_calls = [c[0][0] for c in bridge.new_session.call_args_list]
        assert "image3d" in harness_calls
        assert "blender" in harness_calls
