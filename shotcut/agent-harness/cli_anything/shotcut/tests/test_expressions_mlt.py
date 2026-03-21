"""Tests for Shotcut expression baking (expressions_mlt.py) and
per-character title animation (titles.py: apply_per_char_animation)."""

import os
import sys
import math
import tempfile
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cli_anything.shotcut.core.expressions_mlt import (
    bake_expression,
    bake_expression_frames,
)
from cli_anything.shotcut.core.session import Session
from cli_anything.shotcut.core import project as proj_mod
from cli_anything.shotcut.core import timeline as tl_mod
from cli_anything.shotcut.core import filters as filt_mod
from cli_anything.shotcut.core import titles as title_mod


# ============================================================================
# Helpers
# ============================================================================

def _make_session_with_clip():
    """Create a session with a video track and a clip."""
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
# bake_expression — basic functionality
# ============================================================================

class TestBakeExpression:
    def test_returns_string(self):
        result = bake_expression("1.0", fps=30, duration=0.1)
        assert isinstance(result, str)

    def test_constant_expression(self):
        """Constant expression should produce uniform values."""
        result = bake_expression("0.5", fps=10, duration=0.1)
        # All values should be 0.500000
        parts = result.split(";")
        for part in parts:
            val = float(part.split("=")[1])
            assert abs(val - 0.5) < 1e-5

    def test_linear_time(self):
        """time expression should increase linearly."""
        fps = 10
        duration = 1.0
        result = bake_expression("time", fps=fps, duration=duration)
        parts = result.split(";")
        values = [float(p.split("=")[1]) for p in parts if "=" in p]
        # First value should be 0, last should be duration
        assert abs(values[0]) < 1e-5
        assert abs(values[-1] - duration) < 1e-5
        # Should be monotonically increasing
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]

    def test_frame_count(self):
        """For duration=1s at fps=10, should produce 11 entries (0..10 frames)."""
        result = bake_expression("frame", fps=10, duration=1.0)
        parts = [p for p in result.split(";") if p]
        assert len(parts) == 11  # frames 0 through 10 inclusive

    def test_sine_expression(self):
        """sin(time * 2 * pi) should complete one cycle."""
        fps = 30
        duration = 1.0
        result = bake_expression("sin(time * 6.28318)", fps=fps, duration=duration)
        parts = [p for p in result.split(";") if p]
        values = [float(p.split("=")[1]) for p in parts]
        # Should start near 0
        assert abs(values[0]) < 0.01
        # Should have variation (not constant)
        assert max(values) - min(values) > 0.1

    def test_wiggle_expression(self):
        """wiggle(freq, amp) should vary across frames."""
        result = bake_expression("wiggle(2, 0.5)", fps=30, duration=1.0)
        parts = [p for p in result.split(";") if p]
        values = [float(p.split("=")[1]) for p in parts]
        # Wiggle should produce variation
        assert max(values) - min(values) > 0.0

    def test_clamp_expression(self):
        """clamp should restrict values to [lo, hi]."""
        result = bake_expression("clamp(time * 2, 0, 0.5)", fps=10, duration=1.0)
        parts = [p for p in result.split(";") if p]
        values = [float(p.split("=")[1]) for p in parts]
        assert all(0.0 <= v <= 0.5 + 1e-5 for v in values)

    def test_timecode_format_in_string(self):
        """Each entry should have the HH:MM:SS.mmm=value format."""
        result = bake_expression("1.0", fps=10, duration=0.1)
        parts = [p for p in result.split(";") if p]
        for part in parts:
            # Should match timecode=value
            assert "=" in part
            tc, val = part.split("=", 1)
            assert ":" in tc, f"Expected timecode format, got {tc!r}"

    def test_context_injection(self):
        """Custom context variables should be available in expressions."""
        # 'clamp' and other names are built-in; we inject a custom value
        # via context — but Expression only supports the whitelisted names.
        # Instead, test that fps variable works (it's built-in)
        result = bake_expression("fps", fps=24, duration=0.1)
        parts = [p for p in result.split(";") if p]
        values = [float(p.split("=")[1]) for p in parts]
        assert all(abs(v - 24.0) < 1e-5 for v in values)

    def test_invalid_expression_raises(self):
        """An invalid expression should raise ValueError."""
        with pytest.raises((ValueError, SyntaxError)):
            bake_expression("import os", fps=30, duration=0.1)

    def test_pi_available(self):
        """pi constant should be available."""
        result = bake_expression("pi", fps=10, duration=0.1)
        parts = [p for p in result.split(";") if p]
        values = [float(p.split("=")[1]) for p in parts]
        assert all(abs(v - math.pi) < 1e-5 for v in values)


# ============================================================================
# bake_expression_frames — structured output
# ============================================================================

class TestBakeExpressionFrames:
    def test_returns_list(self):
        result = bake_expression_frames("1.0", fps=10, duration=0.1)
        assert isinstance(result, list)

    def test_frame_dict_structure(self):
        result = bake_expression_frames("time", fps=10, duration=0.5)
        assert len(result) > 0
        entry = result[0]
        assert "frame" in entry
        assert "time" in entry
        assert "timecode" in entry
        assert "value" in entry

    def test_frame_indices_correct(self):
        fps = 10
        duration = 0.5
        result = bake_expression_frames("frame", fps=fps, duration=duration)
        frames = [r["frame"] for r in result]
        assert frames[0] == 0
        assert frames[-1] == int(round(duration * fps))

    def test_times_correct(self):
        fps = 10
        duration = 0.3
        result = bake_expression_frames("time", fps=fps, duration=duration)
        for entry in result:
            expected_time = entry["frame"] / fps
            assert abs(entry["time"] - expected_time) < 1e-9

    def test_values_match_expression(self):
        result = bake_expression_frames("frame * 2", fps=10, duration=0.3)
        for entry in result:
            assert abs(entry["value"] - entry["frame"] * 2) < 1e-5


# ============================================================================
# apply_per_char_animation
# ============================================================================

class TestPerCharAnimation:
    def test_returns_correct_structure(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = title_mod.apply_per_char_animation(
                s, clip_index=0, text="Hi",
                track_index=1, preset="typewriter",
            )
            assert result["action"] == "apply_per_char_animation"
            assert result["text"] == "Hi"
            assert result["preset"] == "typewriter"
            assert result["char_count"] == 2
        finally:
            os.unlink(tmpfile)

    def test_n_filters_equals_n_chars(self):
        """Each character should get its own dynamictext filter."""
        s, tmpfile = _make_session_with_clip()
        try:
            text = "Hello"
            result = title_mod.apply_per_char_animation(
                s, clip_index=0, text=text,
                track_index=1, preset="typewriter",
            )
            assert result["filter_count"] == len(text)
            # Verify filters are actually on the clip
            filters = filt_mod.list_filters(s, track_index=1, clip_index=0)
            dt_filters = [f for f in filters if f["service"] == "dynamictext"]
            assert len(dt_filters) == len(text)
        finally:
            os.unlink(tmpfile)

    def test_each_filter_has_single_char(self):
        """Each dynamictext filter argument should be a single character."""
        s, tmpfile = _make_session_with_clip()
        try:
            text = "ABC"
            result = title_mod.apply_per_char_animation(
                s, clip_index=0, text=text,
                track_index=1, preset="typewriter",
            )
            filters = filt_mod.list_filters(s, track_index=1, clip_index=0)
            dt_filters = [f for f in filters if f["service"] == "dynamictext"]
            chars = [f["params"]["argument"] for f in dt_filters]
            # Each filter should have exactly one character
            assert all(len(c) == 1 for c in chars)
            # Together they should spell the text
            assert sorted(chars) == sorted(list(text))
        finally:
            os.unlink(tmpfile)

    def test_cascade_preset(self):
        """cascade preset should work without errors."""
        s, tmpfile = _make_session_with_clip()
        try:
            result = title_mod.apply_per_char_animation(
                s, clip_index=0, text="OK",
                track_index=1, preset="cascade",
            )
            assert result["filter_count"] == 2
        finally:
            os.unlink(tmpfile)

    def test_scale_pop_preset(self):
        """scale_pop preset should work without errors."""
        s, tmpfile = _make_session_with_clip()
        try:
            result = title_mod.apply_per_char_animation(
                s, clip_index=0, text="AB",
                track_index=1, preset="scale_pop",
            )
            assert result["filter_count"] == 2
        finally:
            os.unlink(tmpfile)

    def test_bounce_in_preset(self):
        """bounce_in preset should work without errors."""
        s, tmpfile = _make_session_with_clip()
        try:
            result = title_mod.apply_per_char_animation(
                s, clip_index=0, text="XY",
                track_index=1, preset="bounce_in",
            )
            assert result["filter_count"] == 2
        finally:
            os.unlink(tmpfile)

    def test_wave_preset(self):
        """wave preset should work without errors."""
        s, tmpfile = _make_session_with_clip()
        try:
            result = title_mod.apply_per_char_animation(
                s, clip_index=0, text="MN",
                track_index=1, preset="wave",
            )
            assert result["filter_count"] == 2
        finally:
            os.unlink(tmpfile)

    def test_random_fade_preset(self):
        """random_fade preset should work without errors."""
        s, tmpfile = _make_session_with_clip()
        try:
            result = title_mod.apply_per_char_animation(
                s, clip_index=0, text="PQ",
                track_index=1, preset="random_fade",
            )
            assert result["filter_count"] == 2
        finally:
            os.unlink(tmpfile)

    def test_invalid_preset_raises(self):
        """An invalid preset should raise ValueError."""
        s, tmpfile = _make_session_with_clip()
        try:
            with pytest.raises(ValueError, match="Unknown per-char preset"):
                title_mod.apply_per_char_animation(
                    s, clip_index=0, text="Hi",
                    track_index=1, preset="nonexistent",
                )
        finally:
            os.unlink(tmpfile)

    def test_empty_text(self):
        """Empty text should return 0 filters without error."""
        s, tmpfile = _make_session_with_clip()
        try:
            result = title_mod.apply_per_char_animation(
                s, clip_index=0, text="",
                track_index=1, preset="typewriter",
            )
            assert result["filter_count"] == 0
            assert result["char_count"] == 0
        finally:
            os.unlink(tmpfile)

    def test_duration_auto(self):
        """Auto-duration should be computed from char count and delay."""
        s, tmpfile = _make_session_with_clip()
        try:
            text = "Test"
            delay = 0.05
            result = title_mod.apply_per_char_animation(
                s, clip_index=0, text=text,
                track_index=1, preset="typewriter",
                delay=delay,
            )
            expected_duration = len(text) * delay + 0.5
            assert abs(result["duration"] - expected_duration) < 0.01
        finally:
            os.unlink(tmpfile)

    def test_custom_duration(self):
        """Explicit duration should override auto-duration."""
        s, tmpfile = _make_session_with_clip()
        try:
            result = title_mod.apply_per_char_animation(
                s, clip_index=0, text="Hi",
                track_index=1, preset="typewriter",
                duration=3.0,
            )
            assert result["duration"] == 3.0
        finally:
            os.unlink(tmpfile)

    def test_list_per_char_presets(self):
        """list_per_char_presets should return all preset names."""
        presets = title_mod.list_per_char_presets()
        names = [p["name"] for p in presets]
        for preset_name in ("typewriter", "cascade", "scale_pop",
                            "bounce_in", "wave", "random_fade"):
            assert preset_name in names

    def test_filter_indices_correct_count(self):
        """filter_indices should have one entry per character."""
        s, tmpfile = _make_session_with_clip()
        try:
            text = "XYZ"
            result = title_mod.apply_per_char_animation(
                s, clip_index=0, text=text,
                track_index=1, preset="typewriter",
            )
            assert len(result["filter_indices"]) == len(text)
        finally:
            os.unlink(tmpfile)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
