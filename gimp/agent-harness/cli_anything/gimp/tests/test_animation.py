"""Unit tests for GIMP CLI animation / frame sequence module.

Tests use synthetic data only — no real images or external dependencies
beyond Pillow (used by the render pipeline).
"""

import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cli_anything.gimp.core.project import create_project
from cli_anything.gimp.core.layers import add_layer
from cli_anything.gimp.core.filters import add_filter
from cli_anything.gimp.core.animation import (
    INTERPOLATION_TYPES,
    set_animation_settings,
    get_animation_settings,
    add_animation_keyframe,
    remove_animation_keyframe,
    list_animation_keyframes,
    generate_frame_sequence,
    _interpolate_at_frame,
    _apply_interpolated_values,
)


# ── Helpers ──────────────────────────────────────────────────────

def _make_project_with_layer():
    """Create a small 100x100 project with one solid red layer."""
    proj = create_project(width=100, height=100, color_mode="RGBA")
    add_layer(proj, name="BG", layer_type="solid", fill="#ff0000", opacity=1.0)
    return proj


def _make_project_with_filter():
    """Create a project with one solid layer that has a brightness filter."""
    proj = _make_project_with_layer()
    add_filter(proj, "brightness", 0, {"factor": 1.0})
    return proj


# ── Animation Settings Tests ────────────────────────────────────

class TestAnimationSettings:
    def test_set_settings(self):
        proj = _make_project_with_layer()
        settings = set_animation_settings(proj, frame_count=60, fps=30)
        assert settings["frame_count"] == 60
        assert settings["fps"] == 30
        assert settings["duration"] == 60 / 30

    def test_set_settings_stored_in_project(self):
        proj = _make_project_with_layer()
        set_animation_settings(proj, frame_count=10, fps=12)
        assert proj["animation"]["settings"]["frame_count"] == 10
        assert proj["animation"]["settings"]["fps"] == 12

    def test_get_settings_defaults(self):
        proj = _make_project_with_layer()
        settings = get_animation_settings(proj)
        assert settings["frame_count"] == 30
        assert settings["fps"] == 24

    def test_get_settings_after_set(self):
        proj = _make_project_with_layer()
        set_animation_settings(proj, frame_count=48, fps=24)
        settings = get_animation_settings(proj)
        assert settings["frame_count"] == 48
        assert settings["fps"] == 24
        assert settings["duration"] == 48 / 24

    def test_set_settings_invalid_frame_count(self):
        proj = _make_project_with_layer()
        with pytest.raises(ValueError, match="frame_count"):
            set_animation_settings(proj, frame_count=0)

    def test_set_settings_invalid_fps(self):
        proj = _make_project_with_layer()
        with pytest.raises(ValueError, match="fps"):
            set_animation_settings(proj, fps=0)


# ── Keyframe Add/Replace Tests ──────────────────────────────────

class TestAddKeyframe:
    def test_add_layer_property_keyframe(self):
        proj = _make_project_with_layer()
        kf = add_animation_keyframe(proj, frame=0, layer_index=0, param="opacity", value=0.0)
        assert kf["frame"] == 0
        assert kf["layer_index"] == 0
        assert kf["param"] == "opacity"
        assert kf["value"] == 0.0
        assert kf["filter_index"] == -1
        assert kf["interpolation"] == "LINEAR"

    def test_add_filter_param_keyframe(self):
        proj = _make_project_with_filter()
        kf = add_animation_keyframe(
            proj, frame=10, layer_index=0, param="factor",
            value=2.0, filter_index=0, interpolation="EASE_IN",
        )
        assert kf["filter_index"] == 0
        assert kf["param"] == "factor"
        assert kf["value"] == 2.0
        assert kf["interpolation"] == "EASE_IN"

    def test_add_multiple_keyframes(self):
        proj = _make_project_with_layer()
        add_animation_keyframe(proj, frame=0, layer_index=0, param="opacity", value=0.0)
        add_animation_keyframe(proj, frame=10, layer_index=0, param="opacity", value=1.0)
        kfs = proj["animation"]["keyframes"]
        assert len(kfs) == 2

    def test_duplicate_keyframe_replaces(self):
        proj = _make_project_with_layer()
        add_animation_keyframe(proj, frame=5, layer_index=0, param="opacity", value=0.5)
        add_animation_keyframe(proj, frame=5, layer_index=0, param="opacity", value=0.8)
        kfs = proj["animation"]["keyframes"]
        assert len(kfs) == 1
        assert kfs[0]["value"] == 0.8

    def test_invalid_interpolation_raises(self):
        proj = _make_project_with_layer()
        with pytest.raises(ValueError, match="Invalid interpolation"):
            add_animation_keyframe(
                proj, frame=0, layer_index=0, param="opacity",
                value=1.0, interpolation="CUBIC",
            )

    def test_nonexistent_layer_raises(self):
        proj = _make_project_with_layer()
        with pytest.raises(IndexError, match="Layer index"):
            add_animation_keyframe(proj, frame=0, layer_index=5, param="opacity", value=1.0)

    def test_invalid_layer_property_raises(self):
        proj = _make_project_with_layer()
        with pytest.raises(ValueError, match="Unknown layer property"):
            add_animation_keyframe(
                proj, frame=0, layer_index=0, param="bogus_prop", value=1.0,
            )

    def test_nonexistent_filter_index_raises(self):
        proj = _make_project_with_layer()  # No filters on layer
        with pytest.raises(IndexError, match="Filter index"):
            add_animation_keyframe(
                proj, frame=0, layer_index=0, param="factor",
                value=1.0, filter_index=0,
            )

    def test_add_offset_keyframes(self):
        proj = _make_project_with_layer()
        kf = add_animation_keyframe(proj, frame=0, layer_index=0, param="offset_x", value=0)
        assert kf["param"] == "offset_x"
        kf2 = add_animation_keyframe(proj, frame=0, layer_index=0, param="offset_y", value=50)
        assert kf2["param"] == "offset_y"


# ── Keyframe Remove Tests ───────────────────────────────────────

class TestRemoveKeyframe:
    def test_remove_existing(self):
        proj = _make_project_with_layer()
        add_animation_keyframe(proj, frame=0, layer_index=0, param="opacity", value=1.0)
        result = remove_animation_keyframe(proj, frame=0, layer_index=0, param="opacity")
        assert result["removed"] is True
        assert len(proj["animation"]["keyframes"]) == 0

    def test_remove_nonexistent_raises(self):
        proj = _make_project_with_layer()
        with pytest.raises(ValueError, match="Keyframe not found"):
            remove_animation_keyframe(proj, frame=0, layer_index=0, param="opacity")

    def test_remove_keeps_others(self):
        proj = _make_project_with_layer()
        add_animation_keyframe(proj, frame=0, layer_index=0, param="opacity", value=0.0)
        add_animation_keyframe(proj, frame=10, layer_index=0, param="opacity", value=1.0)
        remove_animation_keyframe(proj, frame=0, layer_index=0, param="opacity")
        kfs = proj["animation"]["keyframes"]
        assert len(kfs) == 1
        assert kfs[0]["frame"] == 10


# ── Keyframe List Tests ─────────────────────────────────────────

class TestListKeyframes:
    def test_list_all(self):
        proj = _make_project_with_layer()
        add_animation_keyframe(proj, frame=10, layer_index=0, param="opacity", value=1.0)
        add_animation_keyframe(proj, frame=0, layer_index=0, param="opacity", value=0.0)
        kfs = list_animation_keyframes(proj)
        assert len(kfs) == 2
        # Should be sorted by frame
        assert kfs[0]["frame"] == 0
        assert kfs[1]["frame"] == 10

    def test_list_filter_by_layer(self):
        proj = create_project(width=100, height=100, color_mode="RGBA")
        add_layer(proj, name="L0", layer_type="solid", fill="#ff0000")
        add_layer(proj, name="L1", layer_type="solid", fill="#00ff00")
        add_animation_keyframe(proj, frame=0, layer_index=0, param="opacity", value=0.0)
        add_animation_keyframe(proj, frame=0, layer_index=1, param="opacity", value=1.0)
        kfs = list_animation_keyframes(proj, layer_index=0)
        assert len(kfs) == 1
        assert kfs[0]["layer_index"] == 0

    def test_list_filter_by_param(self):
        proj = _make_project_with_layer()
        add_animation_keyframe(proj, frame=0, layer_index=0, param="opacity", value=0.0)
        add_animation_keyframe(proj, frame=0, layer_index=0, param="offset_x", value=10)
        kfs = list_animation_keyframes(proj, param="opacity")
        assert len(kfs) == 1
        assert kfs[0]["param"] == "opacity"

    def test_list_filter_by_layer_and_param(self):
        proj = create_project(width=100, height=100, color_mode="RGBA")
        add_layer(proj, name="L0", layer_type="solid", fill="#ff0000")
        add_layer(proj, name="L1", layer_type="solid", fill="#00ff00")
        add_animation_keyframe(proj, frame=0, layer_index=0, param="opacity", value=0.0)
        add_animation_keyframe(proj, frame=0, layer_index=0, param="offset_x", value=10)
        add_animation_keyframe(proj, frame=0, layer_index=1, param="opacity", value=1.0)
        kfs = list_animation_keyframes(proj, layer_index=0, param="opacity")
        assert len(kfs) == 1

    def test_list_empty_project(self):
        proj = _make_project_with_layer()
        kfs = list_animation_keyframes(proj)
        assert kfs == []


# ── Interpolation Tests ─────────────────────────────────────────

class TestInterpolation:
    def _make_kfs(self, interpolation="LINEAR"):
        """Create two keyframes: value 0 at frame 0, value 10 at frame 10."""
        return [
            {"frame": 0, "value": 0.0, "interpolation": interpolation,
             "layer_index": 0, "filter_index": -1, "param": "opacity"},
            {"frame": 10, "value": 10.0, "interpolation": "LINEAR",
             "layer_index": 0, "filter_index": -1, "param": "opacity"},
        ]

    def test_linear_midpoint(self):
        kfs = self._make_kfs("LINEAR")
        val = _interpolate_at_frame(kfs, 5)
        assert val == pytest.approx(5.0)

    def test_linear_quarter(self):
        kfs = self._make_kfs("LINEAR")
        val = _interpolate_at_frame(kfs, 2)
        assert val == pytest.approx(2.0)

    def test_constant_holds_left_value(self):
        kfs = self._make_kfs("CONSTANT")
        # CONSTANT holds at the left keyframe's value until the next keyframe
        val = _interpolate_at_frame(kfs, 5)
        assert val == pytest.approx(0.0)

    def test_constant_at_right_boundary(self):
        kfs = self._make_kfs("CONSTANT")
        val = _interpolate_at_frame(kfs, 10)
        assert val == pytest.approx(10.0)

    def test_ease_in_slower_start(self):
        kfs = self._make_kfs("EASE_IN")
        val = _interpolate_at_frame(kfs, 5)
        # EASE_IN: t^2, so at t=0.5, eased_t = 0.25
        assert val == pytest.approx(2.5)

    def test_ease_out(self):
        kfs = self._make_kfs("EASE_OUT")
        val = _interpolate_at_frame(kfs, 5)
        # EASE_OUT: 1-(1-t)^2, at t=0.5, eased_t = 0.75
        assert val == pytest.approx(7.5)

    def test_ease_in_out_midpoint(self):
        kfs = self._make_kfs("EASE_IN_OUT")
        val = _interpolate_at_frame(kfs, 5)
        # EASE_IN_OUT: at t=0.5, 2*(0.5)^2 = 0.5 (transitions)
        assert val == pytest.approx(5.0)

    def test_before_first_keyframe(self):
        kfs = self._make_kfs("LINEAR")
        val = _interpolate_at_frame(kfs, -5)
        assert val == pytest.approx(0.0)

    def test_after_last_keyframe(self):
        kfs = self._make_kfs("LINEAR")
        val = _interpolate_at_frame(kfs, 20)
        assert val == pytest.approx(10.0)

    def test_exact_keyframe_value(self):
        kfs = self._make_kfs("LINEAR")
        val = _interpolate_at_frame(kfs, 0)
        assert val == pytest.approx(0.0)
        val = _interpolate_at_frame(kfs, 10)
        assert val == pytest.approx(10.0)

    def test_three_keyframes(self):
        kfs = [
            {"frame": 0, "value": 0.0, "interpolation": "LINEAR",
             "layer_index": 0, "filter_index": -1, "param": "opacity"},
            {"frame": 10, "value": 10.0, "interpolation": "LINEAR",
             "layer_index": 0, "filter_index": -1, "param": "opacity"},
            {"frame": 20, "value": 5.0, "interpolation": "LINEAR",
             "layer_index": 0, "filter_index": -1, "param": "opacity"},
        ]
        assert _interpolate_at_frame(kfs, 5) == pytest.approx(5.0)
        assert _interpolate_at_frame(kfs, 15) == pytest.approx(7.5)

    def test_empty_keyframes_raises(self):
        with pytest.raises(ValueError, match="No keyframes"):
            _interpolate_at_frame([], 0)


# ── Apply Interpolated Values Tests ─────────────────────────────

class TestApplyInterpolatedValues:
    def test_apply_opacity(self):
        proj = _make_project_with_layer()
        kfs = [
            {"frame": 0, "layer_index": 0, "filter_index": -1,
             "param": "opacity", "value": 0.0, "interpolation": "LINEAR"},
            {"frame": 10, "layer_index": 0, "filter_index": -1,
             "param": "opacity", "value": 1.0, "interpolation": "LINEAR"},
        ]
        result = _apply_interpolated_values(proj, 5, kfs)
        assert result["layers"][0]["opacity"] == pytest.approx(0.5)
        # Original should be unchanged
        assert proj["layers"][0]["opacity"] == 1.0

    def test_apply_offset(self):
        proj = _make_project_with_layer()
        kfs = [
            {"frame": 0, "layer_index": 0, "filter_index": -1,
             "param": "offset_x", "value": 0, "interpolation": "LINEAR"},
            {"frame": 10, "layer_index": 0, "filter_index": -1,
             "param": "offset_x", "value": 100, "interpolation": "LINEAR"},
        ]
        result = _apply_interpolated_values(proj, 5, kfs)
        assert result["layers"][0]["offset_x"] == 50

    def test_apply_filter_param(self):
        proj = _make_project_with_filter()
        kfs = [
            {"frame": 0, "layer_index": 0, "filter_index": 0,
             "param": "factor", "value": 1.0, "interpolation": "LINEAR"},
            {"frame": 10, "layer_index": 0, "filter_index": 0,
             "param": "factor", "value": 2.0, "interpolation": "LINEAR"},
        ]
        result = _apply_interpolated_values(proj, 5, kfs)
        assert result["layers"][0]["filters"][0]["params"]["factor"] == pytest.approx(1.5)

    def test_apply_clamps_opacity(self):
        proj = _make_project_with_layer()
        kfs = [
            {"frame": 0, "layer_index": 0, "filter_index": -1,
             "param": "opacity", "value": -0.5, "interpolation": "LINEAR"},
        ]
        result = _apply_interpolated_values(proj, 0, kfs)
        assert result["layers"][0]["opacity"] == 0.0

    def test_does_not_mutate_original(self):
        proj = _make_project_with_layer()
        kfs = [
            {"frame": 0, "layer_index": 0, "filter_index": -1,
             "param": "opacity", "value": 0.0, "interpolation": "LINEAR"},
        ]
        _apply_interpolated_values(proj, 0, kfs)
        assert proj["layers"][0]["opacity"] == 1.0


# ── Frame Sequence Generation Tests ─────────────────────────────

class TestGenerateFrameSequence:
    def test_generate_basic_sequence(self, tmp_path):
        """Generate 5 frames with opacity 0 -> 1, verify PNG files created."""
        proj = create_project(width=50, height=50, color_mode="RGBA")
        add_layer(proj, name="BG", layer_type="solid", fill="#ff0000", opacity=1.0)
        set_animation_settings(proj, frame_count=5, fps=24)
        add_animation_keyframe(proj, frame=0, layer_index=0, param="opacity", value=0.0)
        add_animation_keyframe(proj, frame=4, layer_index=0, param="opacity", value=1.0)

        out_dir = str(tmp_path / "frames")
        result = generate_frame_sequence(proj, out_dir)

        assert result["frame_count"] == 5
        assert len(result["frames"]) == 5
        assert result["output_dir"] == os.path.abspath(out_dir)

        for frame_path in result["frames"]:
            assert os.path.exists(frame_path)
            assert os.path.getsize(frame_path) > 0

    def test_generate_with_range(self, tmp_path):
        """Generate only frames 2-4 out of a 10-frame project."""
        proj = create_project(width=50, height=50, color_mode="RGBA")
        add_layer(proj, name="BG", layer_type="solid", fill="#0000ff", opacity=1.0)
        set_animation_settings(proj, frame_count=10, fps=24)
        add_animation_keyframe(proj, frame=0, layer_index=0, param="opacity", value=0.0)
        add_animation_keyframe(proj, frame=9, layer_index=0, param="opacity", value=1.0)

        out_dir = str(tmp_path / "frames")
        result = generate_frame_sequence(proj, out_dir, frame_start=2, frame_end=5)

        assert result["frame_count"] == 3
        assert len(result["frames"]) == 3
        # Verify filenames follow the pattern
        basenames = [os.path.basename(p) for p in result["frames"]]
        assert "frame_0002.png" in basenames
        assert "frame_0003.png" in basenames
        assert "frame_0004.png" in basenames

    def test_generate_with_filter_animation(self, tmp_path):
        """Animate a brightness filter factor from 0.5 to 2.0 over 3 frames."""
        proj = create_project(width=50, height=50, color_mode="RGBA")
        add_layer(proj, name="BG", layer_type="solid", fill="#888888")
        add_filter(proj, "brightness", 0, {"factor": 1.0})
        set_animation_settings(proj, frame_count=3, fps=24)
        add_animation_keyframe(
            proj, frame=0, layer_index=0, param="factor",
            value=0.5, filter_index=0,
        )
        add_animation_keyframe(
            proj, frame=2, layer_index=0, param="factor",
            value=2.0, filter_index=0,
        )

        out_dir = str(tmp_path / "frames")
        result = generate_frame_sequence(proj, out_dir)

        assert result["frame_count"] == 3
        for path in result["frames"]:
            assert os.path.exists(path)

    def test_generate_no_keyframes(self, tmp_path):
        """Generating frames with no keyframes still renders each frame identically."""
        proj = create_project(width=50, height=50, color_mode="RGBA")
        add_layer(proj, name="BG", layer_type="solid", fill="#ff0000")
        set_animation_settings(proj, frame_count=2, fps=24)

        out_dir = str(tmp_path / "frames")
        result = generate_frame_sequence(proj, out_dir)
        assert result["frame_count"] == 2

    def test_generate_custom_filename_pattern(self, tmp_path):
        """Use a custom filename pattern."""
        proj = create_project(width=50, height=50, color_mode="RGBA")
        add_layer(proj, name="BG", layer_type="solid", fill="#ff0000")
        set_animation_settings(proj, frame_count=2, fps=24)

        out_dir = str(tmp_path / "frames")
        result = generate_frame_sequence(
            proj, out_dir, filename_pattern="img_{:06d}.png",
        )
        basenames = [os.path.basename(p) for p in result["frames"]]
        assert "img_000000.png" in basenames
        assert "img_000001.png" in basenames

    def test_generate_creates_output_dir(self, tmp_path):
        """Output directory is created automatically if it does not exist."""
        proj = create_project(width=50, height=50, color_mode="RGBA")
        add_layer(proj, name="BG", layer_type="solid", fill="#ff0000")
        set_animation_settings(proj, frame_count=1, fps=24)

        out_dir = str(tmp_path / "nested" / "deep" / "frames")
        result = generate_frame_sequence(proj, out_dir)
        assert os.path.isdir(out_dir)
        assert result["frame_count"] == 1
