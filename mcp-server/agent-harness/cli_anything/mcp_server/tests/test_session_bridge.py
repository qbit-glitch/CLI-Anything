"""Tests for session_bridge.py — session lifecycle management."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_bridge(tmp_path: Path):
    """Create a SessionBridge that writes to tmp_path."""
    from cli_anything.mcp_server.session_bridge import SessionBridge
    sessions_dir = tmp_path / "sessions"
    index_file = tmp_path / "sessions.json"
    bridge = SessionBridge(session_dir=sessions_dir, index_file=index_file)
    return bridge, sessions_dir, index_file


class TestNewSession:
    def test_returns_uuid_string(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        sid = bridge.new_session("blender")
        assert isinstance(sid, str)
        assert len(sid) == 36  # UUID format: 8-4-4-4-12

    def test_uuid_has_correct_format(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        sid = bridge.new_session("gimp")
        parts = sid.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8

    def test_different_sessions_have_unique_ids(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        sid1 = bridge.new_session("blender")
        sid2 = bridge.new_session("blender")
        assert sid1 != sid2

    def test_custom_project_path(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        custom = str(tmp_path / "my_project.json")
        sid = bridge.new_session("blender", project_path=custom)
        assert bridge.get_project_path(sid) == custom

    def test_auto_generated_project_path_contains_session_id(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        sid = bridge.new_session("blender")
        project_path = bridge.get_project_path(sid)
        assert sid in project_path

    def test_persists_to_index_file(self, tmp_path):
        bridge, _, index_file = _make_bridge(tmp_path)
        bridge.new_session("blender")
        assert index_file.exists()
        data = json.loads(index_file.read_text())
        assert len(data) == 1


class TestGetProjectPath:
    def test_returns_path_for_known_session(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        sid = bridge.new_session("blender")
        path = bridge.get_project_path(sid)
        assert isinstance(path, str)
        assert len(path) > 0

    def test_unknown_session_raises_key_error(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        with pytest.raises(KeyError):
            bridge.get_project_path("nonexistent-session-id")

    def test_deleted_session_raises_key_error(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        sid = bridge.new_session("blender")
        bridge.delete_session(sid)
        with pytest.raises(KeyError):
            bridge.get_project_path(sid)


class TestDeleteSession:
    def test_removes_from_list(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        sid = bridge.new_session("blender")
        bridge.delete_session(sid)
        sessions = bridge.list_sessions()
        assert not any(s["session_id"] == sid for s in sessions)

    def test_delete_nonexistent_is_noop(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        # Should not raise
        bridge.delete_session("does-not-exist")

    def test_deletes_project_file_if_exists(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        sid = bridge.new_session("blender")
        proj_path = Path(bridge.get_project_path(sid))
        proj_path.write_text("{}")  # create the file
        bridge.delete_session(sid)
        assert not proj_path.exists()


class TestListSessions:
    def test_empty_initially(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        assert bridge.list_sessions() == []

    def test_lists_created_sessions(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        bridge.new_session("blender")
        bridge.new_session("gimp")
        sessions = bridge.list_sessions()
        assert len(sessions) == 2

    def test_session_dict_has_required_keys(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        bridge.new_session("blender")
        s = bridge.list_sessions()[0]
        assert "session_id" in s
        assert "harness" in s
        assert "project_path" in s
        assert "created_at" in s

    def test_harness_name_correct(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        bridge.new_session("inkscape")
        s = bridge.list_sessions()[0]
        assert s["harness"] == "inkscape"


class TestCleanupStale:
    def test_removes_old_sessions(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        sid = bridge.new_session("blender")
        # Back-date the session to 25 hours ago
        bridge._sessions[sid].created_at = time.time() - 25 * 3600
        bridge._save()
        removed = bridge.cleanup_stale(max_age_hours=24)
        assert removed == 1
        assert bridge.list_sessions() == []

    def test_keeps_fresh_sessions(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        bridge.new_session("blender")
        removed = bridge.cleanup_stale(max_age_hours=24)
        assert removed == 0
        assert len(bridge.list_sessions()) == 1

    def test_returns_count_removed(self, tmp_path):
        bridge, _, _ = _make_bridge(tmp_path)
        for _ in range(3):
            sid = bridge.new_session("blender")
            bridge._sessions[sid].created_at = time.time() - 48 * 3600
        bridge._save()
        removed = bridge.cleanup_stale(max_age_hours=24)
        assert removed == 3


class TestPersistence:
    def test_sessions_persist_across_instances(self, tmp_path):
        """A new SessionBridge instance loads sessions saved by a previous one."""
        from cli_anything.mcp_server.session_bridge import SessionBridge
        sessions_dir = tmp_path / "sessions"
        index_file = tmp_path / "sessions.json"

        b1 = SessionBridge(session_dir=sessions_dir, index_file=index_file)
        sid = b1.new_session("blender")
        path1 = b1.get_project_path(sid)

        # New instance pointing at same dirs should reload from disk
        b2 = SessionBridge(session_dir=sessions_dir, index_file=index_file)
        path2 = b2.get_project_path(sid)
        assert path1 == path2
