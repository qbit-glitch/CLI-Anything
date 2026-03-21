"""Tests for the keyframe animation system."""

import os
import tempfile

import pytest

from cli_anything.shotcut.core.keyframes import (
    parse_mlt_keyframe_string,
    generate_mlt_keyframe_string,
    interpolate_value,
    add_keyframe,
    remove_keyframe,
    list_keyframes,
    clear_keyframes,
    _tc_to_seconds,
    _seconds_to_tc,
    _ease_linear,
    _ease_in,
    _ease_out,
    _ease_in_out,
    _ease_hold,
    _apply_easing,
    _bake_segment,
    EASING_TYPES,
    EASING_FUNCTIONS,
)
from cli_anything.shotcut.core.session import Session
from cli_anything.shotcut.core import filters as filt_mod

# Track temp files for cleanup
_temp_files = []


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_session_with_filter(filter_name="brightness", params=None):
    """Create a session with a project and a filter on track 0, clip 0."""
    session = Session()
    session.new_project()
    from cli_anything.shotcut.core import timeline as tl_mod
    tl_mod.add_track(session, track_type="video", name="V1")
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"dummy")
        tmpfile = f.name
    _temp_files.append(tmpfile)
    tl_mod.add_clip(session, tmpfile, track_index=0)
    filt_mod.add_filter(session, filter_name, track_index=0, clip_index=0,
                        params=params)
    return session


@pytest.fixture(autouse=True, scope="session")
def cleanup_temp_files():
    """Clean up temp files after all tests."""
    yield
    for f in _temp_files:
        try:
            os.unlink(f)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Timecode conversion
# ---------------------------------------------------------------------------

class TestTimecodeConversion:
    def test_tc_to_seconds_full(self):
        assert _tc_to_seconds("00:00:01.000") == 1.0

    def test_tc_to_seconds_minutes(self):
        assert _tc_to_seconds("00:01:30.000") == 90.0

    def test_tc_to_seconds_hours(self):
        assert _tc_to_seconds("01:00:00.000") == 3600.0

    def test_tc_to_seconds_milliseconds(self):
        assert abs(_tc_to_seconds("00:00:00.500") - 0.5) < 0.001

    def test_tc_to_seconds_plain_float(self):
        assert _tc_to_seconds("2.5") == 2.5

    def test_seconds_to_tc(self):
        assert _seconds_to_tc(1.0) == "00:00:01.000"

    def test_seconds_to_tc_complex(self):
        assert _seconds_to_tc(3661.5) == "01:01:01.500"

    def test_roundtrip(self):
        for secs in [0.0, 0.5, 1.0, 59.999, 3600.0, 7261.123]:
            tc = _seconds_to_tc(secs)
            back = _tc_to_seconds(tc)
            assert abs(back - secs) < 0.002, f"Roundtrip failed: {secs} -> {tc} -> {back}"


# ---------------------------------------------------------------------------
# Parse / Generate
# ---------------------------------------------------------------------------

class TestParseGenerate:
    def test_parse_simple_linear(self):
        kfs = parse_mlt_keyframe_string("00:00:00.000=0;00:00:01.000=1")
        assert len(kfs) == 2
        assert kfs[0] == {"time": "00:00:00.000", "value": "0", "easing": "linear"}
        assert kfs[1] == {"time": "00:00:01.000", "value": "1", "easing": "linear"}

    def test_parse_smooth_easing(self):
        kfs = parse_mlt_keyframe_string("00:00:00.000~=0;00:00:01.000=1")
        assert kfs[0]["easing"] == "ease_in_out"
        assert kfs[1]["easing"] == "linear"

    def test_parse_hold_easing(self):
        kfs = parse_mlt_keyframe_string("00:00:00.000|=0;00:00:01.000=1")
        assert kfs[0]["easing"] == "hold"

    def test_parse_empty(self):
        assert parse_mlt_keyframe_string("") == []
        assert parse_mlt_keyframe_string("1.0") == []

    def test_parse_geometry_value(self):
        """Geometry values contain colons — ensure they survive parsing."""
        kfs = parse_mlt_keyframe_string(
            "00:00:00.000=0%/0%:100%x100%:100;00:00:01.000=50%/50%:50%x50%:80"
        )
        assert len(kfs) == 2
        assert kfs[0]["value"] == "0%/0%:100%x100%:100"
        assert kfs[1]["value"] == "50%/50%:50%x50%:80"

    def test_generate_linear(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "linear"},
            {"time": "00:00:01.000", "value": "1", "easing": "linear"},
        ]
        result = generate_mlt_keyframe_string(kfs)
        assert result == "00:00:00.000=0;00:00:01.000=1"

    def test_generate_with_easing(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "ease_in_out"},
            {"time": "00:00:01.000", "value": "1", "easing": "hold"},
        ]
        result = generate_mlt_keyframe_string(kfs)
        assert result == "00:00:00.000~=0;00:00:01.000|=1"

    def test_roundtrip(self):
        original = "00:00:00.000=0;00:00:00.500~=0.5;00:00:01.000|=1"
        kfs = parse_mlt_keyframe_string(original)
        regenerated = generate_mlt_keyframe_string(kfs)
        assert regenerated == original

    def test_generate_empty(self):
        assert generate_mlt_keyframe_string([]) == ""

    def test_parse_multipoint(self):
        kfs = parse_mlt_keyframe_string(
            "00:00:00.000=0;00:00:01.000=0.5;00:00:02.000=1;00:00:03.000=0"
        )
        assert len(kfs) == 4
        assert kfs[2]["value"] == "1"


# ---------------------------------------------------------------------------
# Easing functions
# ---------------------------------------------------------------------------

class TestEasingFunctions:
    def test_linear_endpoints(self):
        assert _ease_linear(0.0) == 0.0
        assert _ease_linear(1.0) == 1.0

    def test_linear_midpoint(self):
        assert _ease_linear(0.5) == 0.5

    def test_ease_in_starts_slow(self):
        assert _ease_in(0.25) < 0.25

    def test_ease_in_endpoints(self):
        assert _ease_in(0.0) == 0.0
        assert _ease_in(1.0) == 1.0

    def test_ease_out_starts_fast(self):
        assert _ease_out(0.25) > 0.25

    def test_ease_out_endpoints(self):
        assert _ease_out(0.0) == 0.0
        assert _ease_out(1.0) == 1.0

    def test_ease_in_out_symmetric(self):
        assert abs(_ease_in_out(0.5) - 0.5) < 0.001

    def test_ease_in_out_endpoints(self):
        assert _ease_in_out(0.0) == 0.0
        assert _ease_in_out(1.0) == 1.0

    def test_hold_stays_zero(self):
        assert _ease_hold(0.0) == 0.0
        assert _ease_hold(0.5) == 0.0
        assert _ease_hold(0.99) == 0.0
        assert _ease_hold(1.0) == 1.0


# ---------------------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------------------

class TestInterpolation:
    def test_linear_midpoint(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "linear"},
            {"time": "00:00:01.000", "value": "1", "easing": "linear"},
        ]
        result = interpolate_value(kfs, "00:00:00.500")
        assert abs(result - 0.5) < 0.001

    def test_before_first(self):
        kfs = [
            {"time": "00:00:01.000", "value": "5", "easing": "linear"},
            {"time": "00:00:02.000", "value": "10", "easing": "linear"},
        ]
        assert interpolate_value(kfs, "00:00:00.000") == 5.0

    def test_after_last(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "linear"},
            {"time": "00:00:01.000", "value": "10", "easing": "linear"},
        ]
        assert interpolate_value(kfs, "00:00:05.000") == 10.0

    def test_ease_in_slower_start(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "ease_in"},
            {"time": "00:00:01.000", "value": "1", "easing": "linear"},
        ]
        result = interpolate_value(kfs, "00:00:00.500")
        assert result < 0.5  # ease_in is slower at start

    def test_hold_no_interpolation(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "hold"},
            {"time": "00:00:01.000", "value": "1", "easing": "linear"},
        ]
        result = interpolate_value(kfs, "00:00:00.500")
        assert result == 0.0  # holds at start value

    def test_multipoint(self):
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "linear"},
            {"time": "00:00:01.000", "value": "10", "easing": "linear"},
            {"time": "00:00:02.000", "value": "5", "easing": "linear"},
        ]
        assert abs(interpolate_value(kfs, "00:00:00.500") - 5.0) < 0.001
        assert abs(interpolate_value(kfs, "00:00:01.500") - 7.5) < 0.001

    def test_empty_keyframes(self):
        assert interpolate_value([], "00:00:00.000") is None

    def test_single_keyframe(self):
        kfs = [{"time": "00:00:00.000", "value": "42", "easing": "linear"}]
        assert interpolate_value(kfs, "00:00:00.000") == 42.0
        assert interpolate_value(kfs, "00:00:05.000") == 42.0


# ---------------------------------------------------------------------------
# Session-based keyframe operations
# ---------------------------------------------------------------------------

class TestKeyframeOperations:
    def test_add_keyframe_to_filter(self):
        session = _make_session_with_filter("brightness", {"level": "1.0"})
        result = add_keyframe(session, "00:00:00.000", "level", "0",
                              track_index=0, clip_index=0, filter_index=0)
        assert result["action"] == "add_keyframe"
        assert result["keyframe_count"] >= 1

    def test_add_multiple_keyframes(self):
        session = _make_session_with_filter("brightness", {"level": "1.0"})
        add_keyframe(session, "00:00:00.000", "level", "0",
                     track_index=0, clip_index=0, filter_index=0)
        add_keyframe(session, "00:00:01.000", "level", "1",
                     track_index=0, clip_index=0, filter_index=0)
        kfs = list_keyframes(session, "level",
                             track_index=0, clip_index=0, filter_index=0)
        assert len(kfs) >= 2

    def test_keyframes_sorted_by_time(self):
        session = _make_session_with_filter("brightness", {"level": "1.0"})
        add_keyframe(session, "00:00:02.000", "level", "1",
                     track_index=0, clip_index=0, filter_index=0)
        add_keyframe(session, "00:00:00.000", "level", "0",
                     track_index=0, clip_index=0, filter_index=0)
        add_keyframe(session, "00:00:01.000", "level", "0.5",
                     track_index=0, clip_index=0, filter_index=0)
        kfs = list_keyframes(session, "level",
                             track_index=0, clip_index=0, filter_index=0)
        times = [kf["time"] for kf in kfs]
        assert times == sorted(times, key=_tc_to_seconds)

    def test_duplicate_time_replaces(self):
        session = _make_session_with_filter("brightness", {"level": "1.0"})
        add_keyframe(session, "00:00:00.000", "level", "0",
                     track_index=0, clip_index=0, filter_index=0)
        add_keyframe(session, "00:00:00.000", "level", "0.5",
                     track_index=0, clip_index=0, filter_index=0)
        kfs = list_keyframes(session, "level",
                             track_index=0, clip_index=0, filter_index=0)
        # Find the keyframe at 00:00:00.000
        at_zero = [kf for kf in kfs if kf["time"] == "00:00:00.000"]
        assert len(at_zero) == 1
        assert at_zero[0]["value"] == "0.5"

    def test_add_keyframe_with_easing(self):
        session = _make_session_with_filter("brightness", {"level": "1.0"})
        result = add_keyframe(session, "00:00:00.000", "level", "0",
                              easing="ease_in_out",
                              track_index=0, clip_index=0, filter_index=0)
        assert "~=" in result["keyframe_string"]

    def test_add_keyframe_with_seconds(self):
        """Numeric seconds should be converted to timecode."""
        session = _make_session_with_filter("brightness", {"level": "1.0"})
        result = add_keyframe(session, "1.5", "level", "0.5",
                              track_index=0, clip_index=0, filter_index=0)
        assert "00:00:01.500" in result["keyframe_string"]

    def test_invalid_easing_raises(self):
        session = _make_session_with_filter("brightness")
        with pytest.raises(ValueError, match="Invalid easing"):
            add_keyframe(session, "0", "level", "1", easing="bounce",
                         track_index=0, clip_index=0, filter_index=0)

    def test_remove_keyframe(self):
        session = _make_session_with_filter("brightness")
        add_keyframe(session, "00:00:00.000", "level", "0",
                     track_index=0, clip_index=0, filter_index=0)
        add_keyframe(session, "00:00:01.000", "level", "1",
                     track_index=0, clip_index=0, filter_index=0)
        result = remove_keyframe(session, "00:00:00.000", "level",
                                 track_index=0, clip_index=0, filter_index=0)
        assert result["remaining"] == 1

    def test_remove_nonexistent_raises(self):
        session = _make_session_with_filter("brightness")
        add_keyframe(session, "00:00:00.000", "level", "0",
                     track_index=0, clip_index=0, filter_index=0)
        with pytest.raises(ValueError, match="No keyframe found"):
            remove_keyframe(session, "00:00:05.000", "level",
                            track_index=0, clip_index=0, filter_index=0)

    def test_list_keyframes_empty(self):
        session = _make_session_with_filter("brightness", {"level": "1.0"})
        kfs = list_keyframes(session, "level",
                             track_index=0, clip_index=0, filter_index=0)
        # Static value → no keyframes parsed
        assert len(kfs) == 0

    def test_clear_keyframes(self):
        session = _make_session_with_filter("brightness")
        add_keyframe(session, "00:00:00.000", "level", "0",
                     track_index=0, clip_index=0, filter_index=0)
        add_keyframe(session, "00:00:01.000", "level", "1",
                     track_index=0, clip_index=0, filter_index=0)
        result = clear_keyframes(session, "level",
                                 track_index=0, clip_index=0, filter_index=0)
        assert result["static_value"] == "1"
        assert result["removed_count"] >= 2
        # Verify no keyframes remain
        kfs = list_keyframes(session, "level",
                             track_index=0, clip_index=0, filter_index=0)
        assert len(kfs) == 0

    def test_invalid_filter_index_raises(self):
        session = _make_session_with_filter("brightness")
        with pytest.raises(IndexError):
            add_keyframe(session, "0", "level", "1",
                         track_index=0, clip_index=0, filter_index=99)

    def test_undo_restores_keyframes(self):
        session = _make_session_with_filter("brightness", {"level": "1.0"})
        add_keyframe(session, "00:00:00.000", "level", "0",
                     track_index=0, clip_index=0, filter_index=0)
        add_keyframe(session, "00:00:01.000", "level", "1",
                     track_index=0, clip_index=0, filter_index=0)
        kfs_before = list_keyframes(session, "level",
                                    track_index=0, clip_index=0, filter_index=0)
        # Add another keyframe
        add_keyframe(session, "00:00:02.000", "level", "0.5",
                     track_index=0, clip_index=0, filter_index=0)
        # Undo should restore previous state
        session.undo()
        kfs_after = list_keyframes(session, "level",
                                   track_index=0, clip_index=0, filter_index=0)
        assert len(kfs_after) == len(kfs_before)


# ---------------------------------------------------------------------------
# New 30+ easing tests
# ---------------------------------------------------------------------------

class TestSharedEasings:
    """Tests for the 30+ shared Penner easing functions."""

    def test_easing_types_has_30_plus(self):
        """EASING_TYPES should have 30+ entries."""
        assert len(EASING_TYPES) >= 30

    def test_legacy_names_present(self):
        """Legacy names must remain in EASING_TYPES for backward compat."""
        for name in ("linear", "ease_in", "ease_out", "ease_in_out", "hold"):
            assert name in EASING_TYPES, f"Missing legacy easing: {name}"

    def test_penner_families_present(self):
        """All 10 Penner families × 3 variants must be present."""
        families = ["sine", "quad", "cubic", "quart", "quint",
                    "expo", "circ", "elastic", "back", "bounce"]
        variants = ["ease_in", "ease_out", "ease_in_out"]
        for family in families:
            for variant in variants:
                name = f"{variant}_{family}"
                assert name in EASING_TYPES, f"Missing easing: {name}"

    def test_all_shared_easings_endpoints(self):
        """All Penner easings must satisfy f(0)=0 and f(1)=1 at endpoints."""
        # Some overshoot (back, elastic) return non-[0,1] at midpoints
        # but all should return 0 at t=0 and 1 at t=1.
        skip_f1_check = {
            # spring easing not in this list (it's not in EASING_FUNCTIONS)
        }
        for name, fn in EASING_FUNCTIONS.items():
            if name in ("ease_in", "ease_out", "ease_in_out", "hold"):
                continue  # legacy aliases already tested separately
            if name == "linear":
                assert fn(0.0) == 0.0 and fn(1.0) == 1.0
                continue
            result_0 = fn(0.0)
            result_1 = fn(1.0)
            assert abs(result_0) < 0.01, f"{name}(0) = {result_0}, expected ~0"
            assert abs(result_1 - 1.0) < 0.01, f"{name}(1) = {result_1}, expected ~1"

    def test_apply_easing_ease_in_cubic(self):
        """ease_in_cubic should be slower at start than linear."""
        t = 0.25
        result = _apply_easing("ease_in_cubic", t)
        assert result < t, f"ease_in_cubic(0.25) = {result}, expected < 0.25"

    def test_apply_easing_ease_out_cubic(self):
        """ease_out_cubic should be faster at start than linear."""
        t = 0.25
        result = _apply_easing("ease_out_cubic", t)
        assert result > t, f"ease_out_cubic(0.25) = {result}, expected > 0.25"

    def test_apply_easing_ease_out_bounce(self):
        """ease_out_bounce should reach 1.0 at t=1."""
        assert abs(_apply_easing("ease_out_bounce", 1.0) - 1.0) < 0.01

    def test_apply_easing_ease_in_elastic_endpoints(self):
        """ease_in_elastic(0) = 0, ease_in_elastic(1) = 1."""
        assert abs(_apply_easing("ease_in_elastic", 0.0)) < 0.01
        assert abs(_apply_easing("ease_in_elastic", 1.0) - 1.0) < 0.01

    def test_apply_easing_ease_out_back_overshoot(self):
        """ease_out_back should overshoot 1.0 at some midpoint."""
        max_val = max(_apply_easing("ease_out_back", t / 100) for t in range(1, 100))
        assert max_val > 1.0, "ease_out_back should overshoot"

    def test_apply_easing_legacy_aliases(self):
        """Legacy aliases should map to their quadratic equivalents."""
        for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
            assert _apply_easing("ease_in", t) == _ease_in(t)
            assert _apply_easing("ease_out", t) == _ease_out(t)
            assert _apply_easing("ease_in_out", t) == _ease_in_out(t)

    def test_apply_easing_hold(self):
        """Hold easing must be a step function."""
        assert _apply_easing("hold", 0.0) == 0.0
        assert _apply_easing("hold", 0.999) == 0.0
        assert _apply_easing("hold", 1.0) == 1.0

    def test_add_keyframe_ease_in_cubic(self):
        """Should accept 'ease_in_cubic' as a valid easing."""
        session = _make_session_with_filter("brightness", {"level": "0"})
        result = add_keyframe(session, "00:00:00.000", "level", "0",
                              easing="ease_in_cubic",
                              track_index=0, clip_index=0, filter_index=0)
        assert result["easing"] == "ease_in_cubic"

    def test_add_keyframe_ease_out_bounce(self):
        """Should accept 'ease_out_bounce' as a valid easing."""
        session = _make_session_with_filter("brightness", {"level": "0"})
        result = add_keyframe(session, "00:00:00.000", "level", "0",
                              easing="ease_out_bounce",
                              track_index=0, clip_index=0, filter_index=0)
        assert result["easing"] == "ease_out_bounce"

    def test_add_keyframe_ease_in_back(self):
        """Should accept 'ease_in_back' as a valid easing."""
        session = _make_session_with_filter("brightness", {"level": "0"})
        result = add_keyframe(session, "00:00:00.000", "level", "0",
                              easing="ease_in_back",
                              track_index=0, clip_index=0, filter_index=0)
        assert result["easing"] == "ease_in_back"

    def test_baked_complex_easing_is_dense(self):
        """generate_mlt_keyframe_string with complex easing should bake to many samples."""
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "ease_out_bounce"},
            {"time": "00:00:01.000", "value": "1", "easing": "linear"},
        ]
        kf_str = generate_mlt_keyframe_string(kfs)
        entries = [s for s in kf_str.split(";") if s]
        assert len(entries) > 2, f"Expected baked keyframes, got: {kf_str[:100]}"

    def test_bake_segment_produces_correct_count(self):
        """_bake_segment for 1 second at 30fps should give ~29 sample points."""
        baked = _bake_segment("00:00:00.000", "0", "ease_out_cubic",
                              "00:00:01.000", "1")
        # num_samples = int(1 * 30) + 1 = 31, excluding endpoint = 30 points
        assert len(baked) >= 25  # Allow for rounding variance

    def test_interpolate_value_ease_in_cubic(self):
        """interpolate_value with ease_in_cubic should start slow."""
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "ease_in_cubic"},
            {"time": "00:00:01.000", "value": "1", "easing": "linear"},
        ]
        result = interpolate_value(kfs, "00:00:00.500")
        assert result < 0.5, f"ease_in_cubic should start slow; got {result}"

    def test_interpolate_value_ease_out_bounce_at_end(self):
        """interpolate_value with ease_out_bounce should reach 1 at t=1."""
        kfs = [
            {"time": "00:00:00.000", "value": "0", "easing": "ease_out_bounce"},
            {"time": "00:00:01.000", "value": "1", "easing": "linear"},
        ]
        result = interpolate_value(kfs, "00:00:01.000")
        assert abs(result - 1.0) < 0.01
