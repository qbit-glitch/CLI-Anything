"""Unit tests for Shotcut CLI sync import module.

Tests cover JSON and CSV parsing, marker import, auto-format detection,
and sync marker listing.
"""

import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cli_anything.shotcut.core.session import Session
from cli_anything.shotcut.core import project as proj_mod
from cli_anything.shotcut.core import timeline as tl_mod
from cli_anything.shotcut.core.sync import (
    import_audio_sync,
    _parse_sync_file,
    _parse_json_sync,
    _parse_csv_sync,
    create_markers_from_sync,
    list_sync_markers,
)


# -- Helpers -----------------------------------------------------------------

def _make_session():
    """Create a new session with a blank project."""
    s = Session()
    proj_mod.new_project(s, "hd1080p30")
    return s


def _make_json_sync_file(markers=None):
    """Create a temporary JSON sync file."""
    if markers is None:
        markers = [
            {"time": "00:00:02.500", "time_seconds": 2.5,
             "label": "Intro", "type": "point", "duration": 0.0},
            {"time": "00:00:05.000", "time_seconds": 5.0,
             "label": "Verse 1", "type": "range", "duration": 5.0,
             "end_time": "00:00:10.000", "end_seconds": 10.0},
            {"time": "00:00:15.000", "time_seconds": 15.0,
             "label": "Bridge", "type": "point", "duration": 0.0},
        ]
    data = {
        "format": "audacity-sync",
        "version": "1.0",
        "project_name": "Test Project",
        "markers": markers,
    }
    f = tempfile.NamedTemporaryFile(suffix=".json", mode="w",
                                     delete=False, encoding="utf-8")
    json.dump(data, f, indent=2)
    f.close()
    return f.name


def _make_csv_sync_file():
    """Create a temporary CSV sync file in Audacity label format."""
    content = (
        "2.500000\t2.500000\tIntro\n"
        "5.000000\t10.000000\tVerse 1\n"
        "15.000000\t15.000000\tBridge\n"
        "20.000000\t35.500000\tChorus\n"
    )
    f = tempfile.NamedTemporaryFile(suffix=".csv", mode="w",
                                     delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


# -- _parse_json_sync Tests -------------------------------------------------

class TestParseJsonSync:
    def test_parse_wrapped_format(self):
        data = json.dumps({
            "format": "audacity-sync",
            "markers": [
                {"time_seconds": 2.5, "label": "Intro",
                 "type": "point", "duration": 0.0},
                {"time_seconds": 5.0, "label": "Verse",
                 "type": "range", "duration": 5.0},
            ],
        })
        markers = _parse_json_sync(data)
        assert len(markers) == 2
        assert markers[0]["label"] == "Intro"
        assert markers[0]["type"] == "point"
        assert markers[0]["time_seconds"] == 2.5
        assert markers[1]["label"] == "Verse"
        assert markers[1]["type"] == "range"
        assert markers[1]["duration"] == 5.0

    def test_parse_list_format(self):
        data = json.dumps([
            {"time_seconds": 1.0, "label": "A", "type": "point", "duration": 0.0},
        ])
        markers = _parse_json_sync(data)
        assert len(markers) == 1
        assert markers[0]["label"] == "A"

    def test_parse_empty_markers(self):
        data = json.dumps({"markers": []})
        markers = _parse_json_sync(data)
        assert markers == []

    def test_parse_invalid_json_format(self):
        data = json.dumps({"not_markers": "bad"})
        with pytest.raises(ValueError, match="markers"):
            _parse_json_sync(data)

    def test_parse_defaults_for_missing_fields(self):
        data = json.dumps({"markers": [{"time_seconds": 3.0}]})
        markers = _parse_json_sync(data)
        assert len(markers) == 1
        assert markers[0]["label"] == ""
        assert markers[0]["type"] == "point"
        assert markers[0]["duration"] == 0.0


# -- _parse_csv_sync Tests --------------------------------------------------

class TestParseCsvSync:
    def test_parse_tab_separated(self):
        content = "2.500000\t2.500000\tIntro\n5.000000\t10.000000\tVerse 1\n"
        markers = _parse_csv_sync(content)
        assert len(markers) == 2

        assert markers[0]["time_seconds"] == 2.5
        assert markers[0]["label"] == "Intro"
        assert markers[0]["type"] == "point"
        assert markers[0]["duration"] == 0.0

        assert markers[1]["time_seconds"] == 5.0
        assert markers[1]["label"] == "Verse 1"
        assert markers[1]["type"] == "range"
        assert markers[1]["duration"] == 5.0

    def test_parse_comma_separated_fallback(self):
        content = "1.0,2.0,Test\n"
        markers = _parse_csv_sync(content)
        assert len(markers) == 1
        assert markers[0]["time_seconds"] == 1.0
        assert markers[0]["duration"] == 1.0
        assert markers[0]["label"] == "Test"

    def test_parse_empty_content(self):
        markers = _parse_csv_sync("")
        assert markers == []

    def test_parse_skips_comments(self):
        content = "# header\n1.0\t2.0\tTest\n"
        markers = _parse_csv_sync(content)
        assert len(markers) == 1

    def test_parse_no_label(self):
        content = "3.0\t5.0\n"
        markers = _parse_csv_sync(content)
        assert len(markers) == 1
        assert markers[0]["label"] == ""

    def test_parse_skips_bad_lines(self):
        content = "not_a_number\tbad\n1.0\t2.0\tOK\n"
        markers = _parse_csv_sync(content)
        assert len(markers) == 1
        assert markers[0]["label"] == "OK"


# -- Auto-detect format Tests -----------------------------------------------

class TestAutoDetectFormat:
    def test_detect_json(self):
        path = _make_json_sync_file()
        try:
            markers = _parse_sync_file(path, "auto")
            assert len(markers) == 3
            assert markers[0]["label"] == "Intro"
        finally:
            os.unlink(path)

    def test_detect_csv(self):
        path = _make_csv_sync_file()
        try:
            markers = _parse_sync_file(path, "auto")
            assert len(markers) == 4
            assert markers[0]["label"] == "Intro"
        finally:
            os.unlink(path)

    def test_explicit_json_format(self):
        path = _make_json_sync_file()
        try:
            markers = _parse_sync_file(path, "json")
            assert len(markers) == 3
        finally:
            os.unlink(path)

    def test_explicit_csv_format(self):
        path = _make_csv_sync_file()
        try:
            markers = _parse_sync_file(path, "csv")
            assert len(markers) == 4
        finally:
            os.unlink(path)

    def test_unknown_format_raises(self):
        path = _make_json_sync_file()
        try:
            with pytest.raises(ValueError, match="Unknown sync format"):
                _parse_sync_file(path, "xyz")
        finally:
            os.unlink(path)


# -- Import markers only (no audio) Tests -----------------------------------

class TestImportMarkersOnly:
    def test_import_json_markers(self):
        s = _make_session()
        path = _make_json_sync_file()
        try:
            result = import_audio_sync(s, path)
            assert result["markers_imported"] == 3
            assert result["clips_added"] == 0
        finally:
            os.unlink(path)

    def test_import_csv_markers(self):
        s = _make_session()
        path = _make_csv_sync_file()
        try:
            result = import_audio_sync(s, path, format="csv")
            assert result["markers_imported"] == 4
            assert result["clips_added"] == 0
        finally:
            os.unlink(path)

    def test_import_creates_tractor_properties(self):
        s = _make_session()
        path = _make_json_sync_file()
        try:
            import_audio_sync(s, path)
            markers = list_sync_markers(s)
            assert len(markers) == 3
            assert markers[0]["text"] == "Intro"
            assert markers[0]["type"] == "point"
            assert markers[1]["text"] == "Verse 1"
            assert markers[1]["type"] == "range"
        finally:
            os.unlink(path)

    def test_import_nonexistent_file_raises(self):
        s = _make_session()
        with pytest.raises(FileNotFoundError):
            import_audio_sync(s, "/nonexistent/sync.json")

    def test_import_is_checkpointed(self):
        s = _make_session()
        path = _make_json_sync_file()
        try:
            import_audio_sync(s, path)
            assert s.is_modified
            # Should be undoable
            assert s.undo()
        finally:
            os.unlink(path)


# -- create_markers_from_sync Tests -----------------------------------------

class TestCreateMarkersFromSync:
    def test_create_point_markers(self):
        s = _make_session()
        markers = [
            {"time_seconds": 1.0, "label": "A", "type": "point", "duration": 0.0},
            {"time_seconds": 5.0, "label": "B", "type": "point", "duration": 0.0},
        ]
        result = create_markers_from_sync(s, markers)
        assert result["markers_created"] == 2

    def test_create_range_markers(self):
        s = _make_session()
        markers = [
            {"time_seconds": 2.0, "label": "Section",
             "type": "range", "duration": 3.0},
        ]
        result = create_markers_from_sync(s, markers)
        assert result["markers_created"] == 1

        # Verify stored properties
        listed = list_sync_markers(s)
        assert len(listed) == 1
        m = listed[0]
        assert m["text"] == "Section"
        assert m["type"] == "range"
        assert "end" in m
        assert "duration" in m

    def test_create_empty_markers(self):
        s = _make_session()
        result = create_markers_from_sync(s, [])
        assert result["markers_created"] == 0

    def test_no_project_raises(self):
        s = Session()
        with pytest.raises(RuntimeError, match="No project is open"):
            create_markers_from_sync(s, [])

    def test_incremental_marker_creation(self):
        s = _make_session()
        markers1 = [
            {"time_seconds": 1.0, "label": "First", "type": "point", "duration": 0.0},
        ]
        markers2 = [
            {"time_seconds": 5.0, "label": "Second", "type": "point", "duration": 0.0},
        ]
        create_markers_from_sync(s, markers1)
        create_markers_from_sync(s, markers2)

        listed = list_sync_markers(s)
        assert len(listed) == 2
        assert listed[0]["text"] == "First"
        assert listed[1]["text"] == "Second"


# -- list_sync_markers Tests ------------------------------------------------

class TestListSyncMarkers:
    def test_list_empty(self):
        s = _make_session()
        markers = list_sync_markers(s)
        assert markers == []

    def test_list_after_import(self):
        s = _make_session()
        path = _make_json_sync_file()
        try:
            import_audio_sync(s, path)
            markers = list_sync_markers(s)
            assert len(markers) == 3

            # Check structure of each marker
            for m in markers:
                assert "index" in m
                assert "text" in m
                assert "start" in m
                assert "type" in m
        finally:
            os.unlink(path)

    def test_list_range_marker_has_end(self):
        s = _make_session()
        path = _make_json_sync_file()
        try:
            import_audio_sync(s, path)
            markers = list_sync_markers(s)
            # Find the range marker
            range_markers = [m for m in markers if m["type"] == "range"]
            assert len(range_markers) == 1
            assert "end" in range_markers[0]
            assert "duration" in range_markers[0]
        finally:
            os.unlink(path)

    def test_list_no_project_raises(self):
        s = Session()
        with pytest.raises(RuntimeError, match="No project is open"):
            list_sync_markers(s)


# -- Integration: Audacity export -> Shotcut import --------------------------

class TestSyncIntegration:
    def test_json_roundtrip(self):
        """Test that Audacity JSON export can be imported by Shotcut."""
        # Simulate Audacity export
        markers_data = {
            "format": "audacity-sync",
            "version": "1.0",
            "project_name": "Podcast Episode 1",
            "markers": [
                {"time": "00:00:00.000", "time_seconds": 0.0,
                 "label": "Start", "type": "point", "duration": 0.0},
                {"time": "00:00:05.000", "time_seconds": 5.0,
                 "label": "Intro Music", "type": "range", "duration": 10.0,
                 "end_time": "00:00:15.000", "end_seconds": 15.0},
                {"time": "00:00:30.000", "time_seconds": 30.0,
                 "label": "Main Content", "type": "range", "duration": 120.0,
                 "end_time": "00:02:30.000", "end_seconds": 150.0},
            ],
        }

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w",
                                          delete=False) as f:
            json.dump(markers_data, f, indent=2)
            path = f.name

        try:
            # Import into Shotcut
            s = _make_session()
            result = import_audio_sync(s, path)
            assert result["markers_imported"] == 3

            # Verify markers
            markers = list_sync_markers(s)
            assert len(markers) == 3
            assert markers[0]["text"] == "Start"
            assert markers[1]["text"] == "Intro Music"
            assert markers[2]["text"] == "Main Content"
        finally:
            os.unlink(path)

    def test_csv_roundtrip(self):
        """Test that Audacity CSV export can be imported by Shotcut."""
        csv_content = (
            "0.000000\t0.000000\tStart\n"
            "5.000000\t15.000000\tIntro Music\n"
            "30.000000\t150.000000\tMain Content\n"
        )
        with tempfile.NamedTemporaryFile(suffix=".csv", mode="w",
                                          delete=False) as f:
            f.write(csv_content)
            path = f.name

        try:
            s = _make_session()
            result = import_audio_sync(s, path, format="csv")
            assert result["markers_imported"] == 3

            markers = list_sync_markers(s)
            assert len(markers) == 3
            assert markers[1]["type"] == "range"
        finally:
            os.unlink(path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
