"""Tests for Kdenlive expression baking (expressions_mlt.py)
and new 30+ easing support in keyframes.py."""

import os
import sys
import math
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cli_anything.kdenlive.core.expressions_mlt import (
    bake_expression,
    bake_expression_frames,
)
from cli_anything.kdenlive.core.keyframes import (
    EASING_TYPES,
    EASING_FUNCTIONS,
    interpolate_value,
    add_keyframe,
    keyframes_to_mlt_string,
    _apply_easing,
    _bake_segment,
)
from cli_anything.kdenlive.core.project import create_project
from cli_anything.kdenlive.core.timeline import add_track, add_clip_to_track
from cli_anything.kdenlive.core.bin import import_clip
from cli_anything.kdenlive.core.filters import add_filter


# ============================================================================
# Helpers
# ============================================================================

def _make_project_with_filter(filter_name="brightness", params=None):
    proj = create_project(name="test")
    add_track(proj, track_type="video", name="V1")
    clip = import_clip(proj, "/fake/video.mp4", name="test_clip", duration=10.0)
    add_clip_to_track(proj, track_id=0, clip_id=clip["id"],
                      position=0.0, in_point=0.0, out_point=10.0)
    add_filter(proj, track_id=0, clip_index=0, filter_name=filter_name,
               params=params)
    return proj


# ============================================================================
# New 30+ easing tests for keyframes.py
# ============================================================================

class TestSharedEasingsKdenlive:
    def test_easing_types_has_30_plus(self):
        assert len(EASING_TYPES) >= 30

    def test_legacy_names_present(self):
        for name in ("linear", "ease_in", "ease_out", "ease_in_out", "hold"):
            assert name in EASING_TYPES, f"Missing legacy easing: {name}"

    def test_penner_families_present(self):
        families = ["sine", "quad", "cubic", "quart", "quint",
                    "expo", "circ", "elastic", "back", "bounce"]
        variants = ["ease_in", "ease_out", "ease_in_out"]
        for family in families:
            for variant in variants:
                name = f"{variant}_{family}"
                assert name in EASING_TYPES, f"Missing easing: {name}"

    def test_all_shared_easings_endpoints(self):
        """All Penner easings must satisfy f(0)≈0 and f(1)≈1."""
        for name, fn in EASING_FUNCTIONS.items():
            if name in ("ease_in", "ease_out", "ease_in_out", "hold"):
                continue
            result_0 = fn(0.0)
            result_1 = fn(1.0)
            assert abs(result_0) < 0.01, f"{name}(0) = {result_0}"
            assert abs(result_1 - 1.0) < 0.01, f"{name}(1) = {result_1}"

    def test_apply_easing_ease_in_cubic(self):
        t = 0.25
        result = _apply_easing("ease_in_cubic", t)
        assert result < t

    def test_apply_easing_ease_out_cubic(self):
        t = 0.25
        result = _apply_easing("ease_out_cubic", t)
        assert result > t

    def test_apply_easing_ease_out_bounce_endpoint(self):
        assert abs(_apply_easing("ease_out_bounce", 1.0) - 1.0) < 0.01

    def test_apply_easing_ease_in_back_overshoot(self):
        """ease_in_back should go below 0 at some midpoint."""
        min_val = min(_apply_easing("ease_in_back", t / 100) for t in range(1, 50))
        assert min_val < 0.0, "ease_in_back should go below 0"

    def test_apply_easing_hold(self):
        assert _apply_easing("hold", 0.0) == 0.0
        assert _apply_easing("hold", 0.99) == 0.0
        assert _apply_easing("hold", 1.0) == 1.0

    def test_apply_easing_legacy_ease_in(self):
        """Legacy 'ease_in' should behave as quadratic."""
        for t in [0.0, 0.5, 1.0]:
            result = _apply_easing("ease_in", t)
            expected = _apply_easing("ease_in_quad", t)
            assert abs(result - expected) < 1e-10

    def test_apply_easing_legacy_ease_out(self):
        for t in [0.0, 0.5, 1.0]:
            assert abs(_apply_easing("ease_out", t) - _apply_easing("ease_out_quad", t)) < 1e-10

    def test_add_keyframe_ease_in_elastic(self):
        proj = _make_project_with_filter("brightness")
        result = add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "0.5",
                              easing="ease_in_elastic")
        assert result["easing"] == "ease_in_elastic"

    def test_add_keyframe_ease_out_bounce(self):
        proj = _make_project_with_filter("brightness")
        result = add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "0.5",
                              easing="ease_out_bounce")
        assert result["easing"] == "ease_out_bounce"

    def test_add_keyframe_ease_in_back(self):
        proj = _make_project_with_filter("brightness")
        result = add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "0.5",
                              easing="ease_in_back")
        assert result["easing"] == "ease_in_back"

    def test_invalid_easing_still_raises(self):
        proj = _make_project_with_filter("brightness")
        with pytest.raises(ValueError, match="Invalid easing"):
            add_keyframe(proj, 0, 0, 0, "00:00:01.000", "level", "1.0",
                         easing="bounce")  # bare "bounce" is invalid

    def test_interpolate_ease_in_cubic(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "ease_in_cubic"},
            {"time": "00:00:01.000", "value": "1", "easing": "linear"},
        ]
        result = interpolate_value(kfs, "00:00:00.500")
        assert result < 0.5, f"ease_in_cubic should start slow; got {result}"

    def test_interpolate_ease_out_bounce_at_end(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "ease_out_bounce"},
            {"time": "00:00:01.000", "value": "1", "easing": "linear"},
        ]
        result = interpolate_value(kfs, "00:00:01.000")
        assert abs(result - 1.0) < 0.01

    def test_keyframes_to_mlt_string_complex_bakes(self):
        """Complex easing should produce more than 2 sample points."""
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "ease_out_bounce"},
            {"time": "00:00:01.000", "value": "1", "easing": "linear"},
        ]
        mlt_str = keyframes_to_mlt_string(kfs)
        parts = [p for p in mlt_str.split(";") if p]
        assert len(parts) > 2, f"Expected baked keyframes, got: {mlt_str[:100]}"

    def test_bake_segment_count(self):
        """_bake_segment for 1s at 30fps should give ~30 samples (excluding endpoint)."""
        baked = _bake_segment("00:00:00.000", "0", "ease_in_cubic",
                              "00:00:01.000", "1")
        assert len(baked) >= 25


# ============================================================================
# bake_expression tests
# ============================================================================

class TestKdenliveBakeExpression:
    def test_returns_string(self):
        result = bake_expression("1.0", fps=25, duration=0.1)
        assert isinstance(result, str)

    def test_constant_value(self):
        result = bake_expression("0.5", fps=10, duration=0.1)
        parts = result.split(";")
        for part in parts:
            val = float(part.split("=")[1])
            assert abs(val - 0.5) < 1e-5

    def test_frame_count(self):
        """For duration=1s at fps=25, should produce 26 entries (0..25)."""
        result = bake_expression("frame", fps=25, duration=1.0)
        parts = [p for p in result.split(";") if p]
        assert len(parts) == 26  # frames 0 through 25 inclusive

    def test_time_increases(self):
        result = bake_expression("time", fps=10, duration=0.5)
        parts = [p for p in result.split(";") if p]
        values = [float(p.split("=")[1]) for p in parts]
        assert values[0] == pytest.approx(0.0, abs=1e-5)
        assert values[-1] == pytest.approx(0.5, abs=1e-5)

    def test_sine_varies(self):
        result = bake_expression("sin(time * 6.28)", fps=25, duration=1.0)
        parts = [p for p in result.split(";") if p]
        values = [float(p.split("=")[1]) for p in parts]
        assert max(values) - min(values) > 0.1

    def test_timecode_format(self):
        result = bake_expression("1.0", fps=10, duration=0.1)
        parts = [p for p in result.split(";") if p]
        for part in parts:
            assert "=" in part
            tc, val = part.split("=", 1)
            assert ":" in tc

    def test_fps_variable(self):
        result = bake_expression("fps", fps=25, duration=0.1)
        parts = [p for p in result.split(";") if p]
        values = [float(p.split("=")[1]) for p in parts]
        assert all(abs(v - 25.0) < 1e-5 for v in values)

    def test_invalid_expression_raises(self):
        with pytest.raises((ValueError, SyntaxError)):
            bake_expression("__import__('os')", fps=25, duration=0.1)

    def test_pi_constant(self):
        result = bake_expression("pi", fps=10, duration=0.1)
        parts = [p for p in result.split(";") if p]
        values = [float(p.split("=")[1]) for p in parts]
        assert all(abs(v - math.pi) < 1e-5 for v in values)

    def test_clamp_helper(self):
        result = bake_expression("clamp(time * 2, 0, 0.5)", fps=10, duration=1.0)
        parts = [p for p in result.split(";") if p]
        values = [float(p.split("=")[1]) for p in parts]
        assert all(0.0 <= v <= 0.5 + 1e-5 for v in values)


# ============================================================================
# bake_expression_frames tests
# ============================================================================

class TestKdenliveBakeExpressionFrames:
    def test_returns_list(self):
        result = bake_expression_frames("1.0", fps=25, duration=0.1)
        assert isinstance(result, list)

    def test_dict_structure(self):
        result = bake_expression_frames("time", fps=25, duration=0.2)
        assert len(result) > 0
        entry = result[0]
        for key in ("frame", "time", "timecode", "value"):
            assert key in entry

    def test_frame_zero(self):
        result = bake_expression_frames("time", fps=25, duration=0.2)
        assert result[0]["frame"] == 0
        assert result[0]["time"] == pytest.approx(0.0, abs=1e-9)

    def test_last_frame(self):
        fps, duration = 25, 0.2
        result = bake_expression_frames("time", fps=fps, duration=duration)
        expected_last = int(round(duration * fps))
        assert result[-1]["frame"] == expected_last

    def test_values_match_expression(self):
        result = bake_expression_frames("frame * 3", fps=10, duration=0.3)
        for entry in result:
            assert abs(entry["value"] - entry["frame"] * 3) < 1e-5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
