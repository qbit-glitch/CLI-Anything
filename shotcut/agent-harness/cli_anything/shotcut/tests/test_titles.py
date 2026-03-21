"""Tests for the Shotcut title/text animation module."""

import os
import sys
import tempfile
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cli_anything.shotcut.core.session import Session
from cli_anything.shotcut.core import project as proj_mod
from cli_anything.shotcut.core import timeline as tl_mod
from cli_anything.shotcut.core import filters as filt_mod
from cli_anything.shotcut.core import keyframes as kf_mod
from cli_anything.shotcut.core import titles as title_mod
from cli_anything.shotcut.utils.mlt_xml import get_property


# ============================================================================
# Helpers
# ============================================================================

def _make_session_with_clip():
    """Create a session with a video track and a clip for testing."""
    s = Session()
    proj_mod.new_project(s, "hd1080p30")
    tl_mod.add_track(s, "video")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"dummy")
        tmpfile = f.name

    tl_mod.add_clip(s, tmpfile, 1,
                    in_point="00:00:00.000", out_point="00:00:05.000")
    return s, tmpfile


# ============================================================================
# Geometry helpers
# ============================================================================

class TestGeometryHelpers:
    def test_parse_geometry_basic(self):
        result = title_mod._parse_geometry("0/0:1920x1080:100")
        assert result == {"x": 0, "y": 0, "w": 1920, "h": 1080, "opacity": 100}

    def test_parse_geometry_with_offset(self):
        result = title_mod._parse_geometry("100/200:640x480:50")
        assert result["x"] == 100
        assert result["y"] == 200
        assert result["w"] == 640
        assert result["h"] == 480
        assert result["opacity"] == 50

    def test_parse_geometry_negative_coords(self):
        result = title_mod._parse_geometry("-100/-200:1920x1080:100")
        assert result["x"] == -100
        assert result["y"] == -200

    def test_parse_geometry_no_opacity(self):
        result = title_mod._parse_geometry("0/0:1920x1080")
        assert result["opacity"] == 100  # default

    def test_parse_geometry_invalid_empty(self):
        with pytest.raises(ValueError):
            title_mod._parse_geometry("")

    def test_parse_geometry_invalid_no_colon(self):
        with pytest.raises(ValueError):
            title_mod._parse_geometry("invalid")

    def test_build_geometry_basic(self):
        result = title_mod._build_geometry(0, 0, 1920, 1080, 100)
        assert result == "0/0:1920x1080:100"

    def test_build_geometry_with_values(self):
        result = title_mod._build_geometry(100, 200, 640, 480, 50)
        assert result == "100/200:640x480:50"

    def test_geometry_roundtrip(self):
        original = "100/200:640x480:75"
        parsed = title_mod._parse_geometry(original)
        rebuilt = title_mod._build_geometry(**parsed)
        assert rebuilt == original

    def test_geometry_roundtrip_zero_origin(self):
        original = "0/0:1920x1080:100"
        parsed = title_mod._parse_geometry(original)
        rebuilt = title_mod._build_geometry(**parsed)
        assert rebuilt == original


# ============================================================================
# List / get presets
# ============================================================================

class TestPresets:
    def test_list_presets(self):
        result = title_mod.list_presets()
        assert isinstance(result, list)
        assert len(result) == 9
        names = [p["name"] for p in result]
        assert "typewriter" in names
        assert "fade_in" in names
        assert "fade_out" in names
        assert "slide_left" in names
        assert "slide_right" in names
        assert "slide_up" in names
        assert "slide_down" in names
        assert "scale_in" in names
        assert "bounce" in names

    def test_list_presets_have_required_fields(self):
        result = title_mod.list_presets()
        for preset in result:
            assert "name" in preset
            assert "description" in preset
            assert "params" in preset
            assert "default_duration" in preset
            assert isinstance(preset["params"], list)
            assert isinstance(preset["default_duration"], float)

    def test_get_preset_info(self):
        info = title_mod.get_preset_info("typewriter")
        assert info["name"] == "typewriter"
        assert "description" in info
        assert info["params"] == ["argument"]
        assert info["default_duration"] == 2.0

    def test_get_preset_info_fade_in(self):
        info = title_mod.get_preset_info("fade_in")
        assert info["params"] == ["geometry"]
        assert info["default_duration"] == 1.0

    def test_get_preset_info_bounce(self):
        info = title_mod.get_preset_info("bounce")
        assert info["params"] == ["geometry"]
        assert info["default_duration"] == 1.5

    def test_get_preset_info_invalid(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            title_mod.get_preset_info("nonexistent_preset")


# ============================================================================
# Add title
# ============================================================================

class TestAddTitle:
    def test_add_title_basic(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = title_mod.add_title(s, "Hello World",
                                         track_index=1, clip_index=0)
            assert result["action"] == "add_title"
            assert result["text"] == "Hello World"
            assert result["service"] == "dynamictext"
            assert result["filter_index"] >= 0

            # Verify the filter was actually added
            filters = filt_mod.list_filters(s, track_index=1, clip_index=0)
            assert len(filters) >= 1
            # Find the dynamictext filter
            dt_filters = [f for f in filters if f["service"] == "dynamictext"]
            assert len(dt_filters) == 1
            assert dt_filters[0]["params"]["argument"] == "Hello World"
        finally:
            os.unlink(tmpfile)

    def test_add_title_with_custom_params(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = title_mod.add_title(
                s, "Custom Title",
                track_index=1, clip_index=0,
                font="Serif", size=72,
                color="#ff0000ff",
                halign="left", valign="top",
                geometry="100/100:800x600:80",
            )
            assert result["font"] == "Serif"
            assert result["size"] == 72
            assert result["color"] == "#ff0000ff"
            assert result["halign"] == "left"
            assert result["valign"] == "top"
            assert result["geometry"] == "100/100:800x600:80"

            # Verify params on the actual filter
            filters = filt_mod.list_filters(s, track_index=1, clip_index=0)
            dt_filters = [f for f in filters if f["service"] == "dynamictext"]
            assert len(dt_filters) == 1
            params = dt_filters[0]["params"]
            assert params["family"] == "Serif"
            assert params["size"] == "72"
            assert params["fgcolour"] == "#ff0000ff"
        finally:
            os.unlink(tmpfile)

    def test_add_title_default_geometry(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = title_mod.add_title(s, "Default Geo",
                                         track_index=1, clip_index=0)
            assert result["geometry"] == "0/0:1920x1080:100"
        finally:
            os.unlink(tmpfile)

    def test_add_multiple_titles(self):
        s, tmpfile = _make_session_with_clip()
        try:
            title_mod.add_title(s, "Title 1", track_index=1, clip_index=0)
            title_mod.add_title(s, "Title 2", track_index=1, clip_index=0)

            filters = filt_mod.list_filters(s, track_index=1, clip_index=0)
            dt_filters = [f for f in filters if f["service"] == "dynamictext"]
            assert len(dt_filters) == 2
        finally:
            os.unlink(tmpfile)


# ============================================================================
# Animate title — each preset
# ============================================================================

class TestAnimateTitle:
    def _add_title_and_get_index(self, s, text="Test Text"):
        """Helper to add a title and return its filter index."""
        result = title_mod.add_title(s, text,
                                     track_index=1, clip_index=0)
        return result["filter_index"]

    def test_animate_fade_in(self):
        s, tmpfile = _make_session_with_clip()
        try:
            fi = self._add_title_and_get_index(s)
            result = title_mod.animate_title(
                s, track_index=1, clip_index=0,
                filter_index=fi, preset="fade_in",
            )
            assert result["action"] == "animate_title"
            assert result["preset"] == "fade_in"
            assert result["keyframes_added"] == 2
            assert result["animated_params"] == ["geometry"]
            # First keyframe should have opacity 0, last should have 100
            kfs = result["keyframes"]
            assert "0" in kfs[0]["value"]  # opacity 0 at start
            assert "100" in kfs[1]["value"]  # opacity 100 at end
        finally:
            os.unlink(tmpfile)

    def test_animate_fade_out(self):
        s, tmpfile = _make_session_with_clip()
        try:
            fi = self._add_title_and_get_index(s)
            result = title_mod.animate_title(
                s, track_index=1, clip_index=0,
                filter_index=fi, preset="fade_out",
            )
            assert result["keyframes_added"] == 2
            assert result["animated_params"] == ["geometry"]
            kfs = result["keyframes"]
            # Fade out: start at 100, end at 0
            assert "100" in kfs[0]["value"]
            assert ":0" in kfs[1]["value"]
        finally:
            os.unlink(tmpfile)

    def test_animate_slide_left(self):
        s, tmpfile = _make_session_with_clip()
        try:
            fi = self._add_title_and_get_index(s)
            result = title_mod.animate_title(
                s, track_index=1, clip_index=0,
                filter_index=fi, preset="slide_left",
            )
            assert result["keyframes_added"] == 2
            assert result["animated_params"] == ["geometry"]
            # Start should be off-screen right (x = 1920)
            kfs = result["keyframes"]
            start_geo = title_mod._parse_geometry(kfs[0]["value"])
            assert start_geo["x"] > 0  # off-screen right
        finally:
            os.unlink(tmpfile)

    def test_animate_slide_right(self):
        s, tmpfile = _make_session_with_clip()
        try:
            fi = self._add_title_and_get_index(s)
            result = title_mod.animate_title(
                s, track_index=1, clip_index=0,
                filter_index=fi, preset="slide_right",
            )
            assert result["keyframes_added"] == 2
            kfs = result["keyframes"]
            start_geo = title_mod._parse_geometry(kfs[0]["value"])
            assert start_geo["x"] < 0  # off-screen left
        finally:
            os.unlink(tmpfile)

    def test_animate_slide_up(self):
        s, tmpfile = _make_session_with_clip()
        try:
            fi = self._add_title_and_get_index(s)
            result = title_mod.animate_title(
                s, track_index=1, clip_index=0,
                filter_index=fi, preset="slide_up",
            )
            assert result["keyframes_added"] == 2
            kfs = result["keyframes"]
            start_geo = title_mod._parse_geometry(kfs[0]["value"])
            assert start_geo["y"] > 0  # off-screen bottom
        finally:
            os.unlink(tmpfile)

    def test_animate_slide_down(self):
        s, tmpfile = _make_session_with_clip()
        try:
            fi = self._add_title_and_get_index(s)
            result = title_mod.animate_title(
                s, track_index=1, clip_index=0,
                filter_index=fi, preset="slide_down",
            )
            assert result["keyframes_added"] == 2
            kfs = result["keyframes"]
            start_geo = title_mod._parse_geometry(kfs[0]["value"])
            assert start_geo["y"] < 0  # off-screen top
        finally:
            os.unlink(tmpfile)

    def test_animate_scale_in(self):
        s, tmpfile = _make_session_with_clip()
        try:
            fi = self._add_title_and_get_index(s)
            result = title_mod.animate_title(
                s, track_index=1, clip_index=0,
                filter_index=fi, preset="scale_in",
            )
            assert result["keyframes_added"] == 2
            kfs = result["keyframes"]
            start_geo = title_mod._parse_geometry(kfs[0]["value"])
            end_geo = title_mod._parse_geometry(kfs[1]["value"])
            # Start should be smaller than end
            assert start_geo["w"] < end_geo["w"]
            assert start_geo["h"] < end_geo["h"]
        finally:
            os.unlink(tmpfile)

    def test_animate_bounce(self):
        s, tmpfile = _make_session_with_clip()
        try:
            fi = self._add_title_and_get_index(s)
            result = title_mod.animate_title(
                s, track_index=1, clip_index=0,
                filter_index=fi, preset="bounce",
            )
            # Bounce has 4 keyframes: start, overshoot, bounce-back, settle
            assert result["keyframes_added"] == 4
            assert result["animated_params"] == ["geometry"]
            # All should use ease_out easing
            for kf in result["keyframes"]:
                assert kf["easing"] == "ease_out"
        finally:
            os.unlink(tmpfile)

    def test_animate_typewriter(self):
        s, tmpfile = _make_session_with_clip()
        try:
            fi = self._add_title_and_get_index(s, "Hello")
            result = title_mod.animate_title(
                s, track_index=1, clip_index=0,
                filter_index=fi, preset="typewriter",
            )
            assert result["animated_params"] == ["argument"]
            # Should have len("Hello") + 1 keyframes (empty + each char)
            assert result["keyframes_added"] == 6  # "", "H", "He", "Hel", "Hell", "Hello"
            # Check progressive text reveal
            kfs = result["keyframes"]
            assert kfs[0]["value"] == ""
            assert kfs[1]["value"] == "H"
            assert kfs[2]["value"] == "He"
            assert kfs[3]["value"] == "Hel"
            assert kfs[4]["value"] == "Hell"
            assert kfs[5]["value"] == "Hello"
            # All should use hold easing
            for kf in kfs:
                assert kf["easing"] == "hold"
        finally:
            os.unlink(tmpfile)

    def test_animate_with_custom_duration(self):
        s, tmpfile = _make_session_with_clip()
        try:
            fi = self._add_title_and_get_index(s)
            result = title_mod.animate_title(
                s, track_index=1, clip_index=0,
                filter_index=fi, preset="fade_in",
                duration=3.0,
            )
            assert result["duration"] == 3.0
        finally:
            os.unlink(tmpfile)

    def test_animate_with_start_time(self):
        s, tmpfile = _make_session_with_clip()
        try:
            fi = self._add_title_and_get_index(s)
            result = title_mod.animate_title(
                s, track_index=1, clip_index=0,
                filter_index=fi, preset="fade_in",
                start_time="30",
            )
            kfs = result["keyframes"]
            assert kfs[0]["time"] == "30"  # starts at frame 30
        finally:
            os.unlink(tmpfile)

    def test_animate_invalid_preset(self):
        s, tmpfile = _make_session_with_clip()
        try:
            fi = self._add_title_and_get_index(s)
            with pytest.raises(ValueError, match="Unknown preset"):
                title_mod.animate_title(
                    s, track_index=1, clip_index=0,
                    filter_index=fi, preset="nonexistent",
                )
        finally:
            os.unlink(tmpfile)

    def test_animate_invalid_filter_index(self):
        s, tmpfile = _make_session_with_clip()
        try:
            with pytest.raises(IndexError):
                title_mod.animate_title(
                    s, track_index=1, clip_index=0,
                    filter_index=99, preset="fade_in",
                )
        finally:
            os.unlink(tmpfile)


# ============================================================================
# Keyframes module
# ============================================================================

class TestKeyframes:
    def test_parse_mlt_keyframe_string(self):
        result = kf_mod.parse_mlt_keyframe_string("0=0;30=100;60=50")
        assert len(result) == 3
        assert result[0] == {"time": "0", "value": "0", "easing": "linear"}
        assert result[1] == {"time": "30", "value": "100", "easing": "linear"}
        assert result[2] == {"time": "60", "value": "50", "easing": "linear"}

    def test_parse_keyframe_with_easing(self):
        result = kf_mod.parse_mlt_keyframe_string("0~=0;30|=100")
        assert result[0]["easing"] == "ease_in_out"
        assert result[1]["easing"] == "hold"

    def test_parse_empty_string(self):
        assert kf_mod.parse_mlt_keyframe_string("") == []
        assert kf_mod.parse_mlt_keyframe_string("   ") == []

    def test_generate_mlt_keyframe_string(self):
        kfs = [
            {"time": "0", "value": "0"},
            {"time": "30", "value": "100"},
        ]
        result = kf_mod.generate_mlt_keyframe_string(kfs)
        assert result == "0=0;30=100"

    def test_generate_with_easing(self):
        kfs = [
            {"time": "0", "value": "0", "easing": "ease_in_out"},
            {"time": "30", "value": "100", "easing": "hold"},
        ]
        result = kf_mod.generate_mlt_keyframe_string(kfs)
        assert result == "0~=0;30|=100"

    def test_generate_empty(self):
        assert kf_mod.generate_mlt_keyframe_string([]) == ""

    def test_parse_generate_roundtrip(self):
        original = "0=0;30=100;60=50"
        parsed = kf_mod.parse_mlt_keyframe_string(original)
        rebuilt = kf_mod.generate_mlt_keyframe_string(parsed)
        assert rebuilt == original

    def test_add_keyframe(self):
        s, tmpfile = _make_session_with_clip()
        try:
            filt_mod.add_filter(s, "brightness", track_index=1, clip_index=0)
            result = kf_mod.add_keyframe(
                s, time="0", param="level", value="0",
                easing="linear",
                track_index=1, clip_index=0, filter_index=0,
            )
            assert result["action"] == "add_keyframe"
            assert result["param"] == "level"
            assert result["keyframe_count"] == 1
        finally:
            os.unlink(tmpfile)

    def test_add_multiple_keyframes(self):
        s, tmpfile = _make_session_with_clip()
        try:
            filt_mod.add_filter(s, "brightness", track_index=1, clip_index=0)
            kf_mod.add_keyframe(s, "0", "level", "0",
                                track_index=1, clip_index=0, filter_index=0)
            result = kf_mod.add_keyframe(s, "30", "level", "1.0",
                                          track_index=1, clip_index=0, filter_index=0)
            assert result["keyframe_count"] == 2
            assert "00:00:00.000=0" in result["keyframe_string"]
            assert "00:00:30.000=1.0" in result["keyframe_string"]
        finally:
            os.unlink(tmpfile)

    def test_add_keyframe_invalid_easing(self):
        s, tmpfile = _make_session_with_clip()
        try:
            filt_mod.add_filter(s, "brightness", track_index=1, clip_index=0)
            with pytest.raises(ValueError, match="Invalid easing"):
                kf_mod.add_keyframe(
                    s, "0", "level", "0", easing="invalid",
                    track_index=1, clip_index=0, filter_index=0,
                )
        finally:
            os.unlink(tmpfile)

    def test_easing_types(self):
        assert "linear" in kf_mod.EASING_TYPES
        assert "ease_in" in kf_mod.EASING_TYPES
        assert "ease_out" in kf_mod.EASING_TYPES
        assert "ease_in_out" in kf_mod.EASING_TYPES
        assert "hold" in kf_mod.EASING_TYPES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
