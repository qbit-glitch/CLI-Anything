"""Tests for the Kdenlive keyframe animation system."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cli_anything.kdenlive.core.project import create_project
from cli_anything.kdenlive.core.timeline import add_track, add_clip_to_track
from cli_anything.kdenlive.core.bin import import_clip
from cli_anything.kdenlive.core.filters import add_filter
from cli_anything.kdenlive.core.keyframes import (
    add_keyframe,
    remove_keyframe,
    list_keyframes,
    clear_keyframes,
    interpolate_value,
    keyframes_to_mlt_string,
    EASING_TYPES,
    _is_keyframed,
)
from cli_anything.kdenlive.utils.mlt_xml import build_mlt_xml


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_project_with_filter(filter_name="brightness", params=None):
    """Create a project with a track, clip, and filter."""
    proj = create_project(name="test")
    add_track(proj, track_type="video", name="V1")
    clip = import_clip(proj, "/fake/video.mp4", name="test_clip", duration=10.0)
    add_clip_to_track(proj, track_id=0, clip_id=clip["id"],
                      position=0.0, in_point=0.0, out_point=10.0)
    add_filter(proj, track_id=0, clip_index=0, filter_name=filter_name,
               params=params)
    return proj


# ---------------------------------------------------------------------------
# Scalar-to-keyframed transformation
# ---------------------------------------------------------------------------

class TestScalarToKeyframed:
    def test_add_keyframe_transforms_scalar(self):
        proj = _make_project_with_filter("brightness")
        result = add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "0.5")
        assert result["action"] == "add_keyframe"
        assert result["keyframe_count"] == 2  # original scalar at 0 + new

        filt = proj["tracks"][0]["clips"][0]["filters"][0]
        assert _is_keyframed(filt["params"]["level"])

    def test_first_keyframe_no_prior_scalar(self):
        """Adding keyframe to a param that has default value."""
        proj = _make_project_with_filter("brightness")
        # level defaults to 1.0; adding at t=0 should transform
        result = add_keyframe(proj, 0, 0, 0, "00:00:00.000", "level", "0.0")
        kfs = list_keyframes(proj, 0, 0, 0, "level")
        # Two keyframes: original default at 00:00:00.000 replaced + our new
        assert len(kfs) >= 1

    def test_clear_reverts_to_scalar(self):
        proj = _make_project_with_filter("brightness")
        add_keyframe(proj, 0, 0, 0, "00:00:00.000", "level", "0")
        add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "1")

        result = clear_keyframes(proj, 0, 0, 0, "level")
        assert result["removed_count"] == 2
        assert result["static_value"] == "1"

        filt = proj["tracks"][0]["clips"][0]["filters"][0]
        assert not _is_keyframed(filt["params"]["level"])


# ---------------------------------------------------------------------------
# Add / Remove / List
# ---------------------------------------------------------------------------

class TestKeyframeOperations:
    def test_add_keyframe(self):
        proj = _make_project_with_filter("brightness")
        result = add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "0.5")
        assert result["time"] == "00:00:01.000"
        assert result["value"] == "0.5"
        assert result["easing"] == "linear"

    def test_add_multiple_keyframes(self):
        proj = _make_project_with_filter("brightness")
        add_keyframe(proj, 0, 0, 0, "00:00:00.000", "level", "0")
        add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "0.5")
        add_keyframe(proj, 0, 0, 0, "00:00:02.000", "level", "1.0")

        kfs = list_keyframes(proj, 0, 0, 0, "level")
        assert len(kfs) == 3

    def test_keyframes_sorted_by_time(self):
        proj = _make_project_with_filter("brightness")
        add_keyframe(proj, 0, 0, 0, "00:00:02.000", "level", "1.0")
        add_keyframe(proj, 0, 0, 0, "00:00:00.000", "level", "0")
        add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "0.5")

        kfs = list_keyframes(proj, 0, 0, 0, "level")
        times = [kf["time"] for kf in kfs]
        assert times == ["00:00:00.000", "00:00:01.000", "00:00:02.000"]

    def test_duplicate_time_replaces(self):
        proj = _make_project_with_filter("brightness")
        add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "0.5")
        add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "0.8")

        kfs = list_keyframes(proj, 0, 0, 0, "level")
        at_1s = [kf for kf in kfs if kf["time"] == "00:00:01.000"]
        assert len(at_1s) == 1
        assert at_1s[0]["value"] == "0.8"

    def test_add_with_easing(self):
        proj = _make_project_with_filter("brightness")
        result = add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "1.0",
                              easing="ease_in_out")
        assert result["easing"] == "ease_in_out"

    def test_add_with_seconds(self):
        proj = _make_project_with_filter("brightness")
        result = add_keyframe(proj, 0, 0, 0, "1.5", "level", "0.5")
        assert result["time"] == "00:00:01.500"

    def test_invalid_easing_raises(self):
        proj = _make_project_with_filter("brightness")
        with pytest.raises(ValueError, match="Invalid easing"):
            add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "1.0",
                         easing="bounce")

    def test_remove_keyframe(self):
        proj = _make_project_with_filter("brightness")
        add_keyframe(proj, 0, 0, 0, "00:00:00.000", "level", "0")
        add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "1")

        result = remove_keyframe(proj, 0, 0, 0, "00:00:01.000", "level")
        assert result["remaining"] >= 1

    def test_remove_nonexistent_raises(self):
        proj = _make_project_with_filter("brightness")
        add_keyframe(proj, 0, 0, 0, "00:00:00.000", "level", "0")

        with pytest.raises(ValueError, match="No keyframe found"):
            remove_keyframe(proj, 0, 0, 0, "00:00:05.000", "level")

    def test_remove_from_non_keyframed_raises(self):
        proj = _make_project_with_filter("brightness")
        with pytest.raises(ValueError, match="not keyframed"):
            remove_keyframe(proj, 0, 0, 0, "00:00:01.000", "level")

    def test_list_keyframes_empty(self):
        proj = _make_project_with_filter("brightness")
        kfs = list_keyframes(proj, 0, 0, 0, "level")
        assert kfs == []

    def test_list_nonexistent_param(self):
        proj = _make_project_with_filter("brightness")
        kfs = list_keyframes(proj, 0, 0, 0, "nonexistent")
        assert kfs == []

    def test_invalid_filter_index_raises(self):
        proj = _make_project_with_filter("brightness")
        with pytest.raises(IndexError):
            add_keyframe(proj, 0, 0, 99, "00:00:01.000", "level", "1.0")

    def test_invalid_track_raises(self):
        proj = _make_project_with_filter("brightness")
        with pytest.raises(ValueError, match="Track not found"):
            add_keyframe(proj, 999, 0, 0, "00:00:01.000", "level", "1.0")

    def test_invalid_clip_index_raises(self):
        proj = _make_project_with_filter("brightness")
        with pytest.raises(IndexError):
            add_keyframe(proj, 0, 99, 0, "00:00:01.000", "level", "1.0")


# ---------------------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------------------

class TestInterpolation:
    def test_linear_midpoint(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "linear"},
            {"time": "00:00:02.000", "value": "1", "easing": "linear"},
        ]
        val = interpolate_value(kfs, "00:00:01.000")
        assert abs(val - 0.5) < 0.01

    def test_before_first(self):
        kfs = [
            {"time": "00:00:01.000", "value": "5", "easing": "linear"},
            {"time": "00:00:02.000", "value": "10", "easing": "linear"},
        ]
        val = interpolate_value(kfs, "00:00:00.000")
        assert val == 5.0

    def test_after_last(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "linear"},
            {"time": "00:00:01.000", "value": "1", "easing": "linear"},
        ]
        val = interpolate_value(kfs, "00:00:05.000")
        assert val == 1.0

    def test_ease_in_slower_start(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "ease_in"},
            {"time": "00:00:02.000", "value": "1", "easing": "linear"},
        ]
        val = interpolate_value(kfs, "00:00:01.000")
        assert val < 0.5  # Ease in is slower at start

    def test_hold_no_interpolation(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "hold"},
            {"time": "00:00:02.000", "value": "1", "easing": "linear"},
        ]
        val = interpolate_value(kfs, "00:00:01.000")
        assert val == 0.0  # Hold stays at first value

    def test_empty_returns_none(self):
        assert interpolate_value([], "00:00:01.000") is None

    def test_single_keyframe(self):
        kfs = [{"time": "00:00:00.000", "value": "42", "easing": "linear"}]
        val = interpolate_value(kfs, "00:00:01.000")
        assert val == 42.0


# ---------------------------------------------------------------------------
# MLT export string
# ---------------------------------------------------------------------------

class TestMLTExport:
    def test_keyframes_to_mlt_string_linear(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "linear"},
            {"time": "00:00:01.000", "value": "1", "easing": "linear"},
        ]
        s = keyframes_to_mlt_string(kfs)
        assert s == "00:00:00.000=0;00:00:01.000=1"

    def test_keyframes_to_mlt_string_easing(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "ease_in_out"},
            {"time": "00:00:01.000", "value": "1", "easing": "hold"},
        ]
        s = keyframes_to_mlt_string(kfs)
        assert "~=" in s  # ease_in_out
        assert "|=" in s  # hold

    def test_keyframes_to_mlt_string_empty(self):
        assert keyframes_to_mlt_string([]) == ""

    def test_build_mlt_xml_emits_keyframe_string(self):
        """Keyframed params should appear as MLT keyframe strings in XML."""
        proj = _make_project_with_filter("brightness")
        add_keyframe(proj, 0, 0, 0, "00:00:00.000", "level", "0")
        add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "1")

        xml = build_mlt_xml(proj)
        # Should contain MLT keyframe format
        assert "00:00:00.000=0" in xml
        assert "00:00:01.000=1" in xml

    def test_build_mlt_xml_scalar_unchanged(self):
        """Non-keyframed params should remain as scalars in XML."""
        proj = _make_project_with_filter("brightness")
        xml = build_mlt_xml(proj)
        assert "1.0" in xml  # Default brightness level

    def test_build_mlt_xml_easing_in_string(self):
        """Easing markers should appear in MLT XML output."""
        proj = _make_project_with_filter("brightness")
        add_keyframe(proj, 0, 0, 0, "00:00:00.000", "level", "0", easing="ease_in_out")
        add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "1", easing="hold")

        xml = build_mlt_xml(proj)
        assert "~=" in xml
        assert "|=" in xml


# ---------------------------------------------------------------------------
# Filter validation with keyframed params
# ---------------------------------------------------------------------------

class TestFilterValidation:
    def test_keyframed_param_passes_validation(self):
        """Adding a filter with a pre-keyframed param should work."""
        proj = create_project(name="test")
        add_track(proj, track_type="video", name="V1")
        clip = import_clip(proj, "/fake/video.mp4", name="test_clip", duration=10.0)
        add_clip_to_track(proj, track_id=0, clip_id=clip["id"],
                          position=0.0, in_point=0.0, out_point=10.0)

        # Add filter, then add keyframes — the keyframed dict should survive
        add_filter(proj, 0, 0, "brightness")
        add_keyframe(proj, 0, 0, 0, "00:00:00.000", "level", "0")
        add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "1")

        kfs = list_keyframes(proj, 0, 0, 0, "level")
        assert len(kfs) >= 2


# ---------------------------------------------------------------------------
# Session undo integration
# ---------------------------------------------------------------------------

class TestSessionIntegration:
    def test_undo_restores_before_keyframe(self):
        from cli_anything.kdenlive.core.session import Session

        proj = _make_project_with_filter("brightness")
        sess = Session()
        sess.set_project(proj)

        sess.snapshot("Before keyframe")
        add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "0.5")

        kfs = list_keyframes(proj, 0, 0, 0, "level")
        assert len(kfs) > 0

        sess.undo()
        proj = sess.get_project()
        kfs = list_keyframes(proj, 0, 0, 0, "level")
        assert len(kfs) == 0
