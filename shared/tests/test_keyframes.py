"""Tests for the KeyframeTrack interpolation engine.

Covers:
- Linear interpolation
- Eased interpolation (string name)
- Multi-keyframe tracks (multiple segments)
- Before-first and after-last hold behaviour
- bake() output length and values
- remove() keyframe
- Callable easing (cubic_bezier)
- evaluate_batch() with numpy
"""

from __future__ import annotations

import math
import pytest

from motion_math.keyframes import Keyframe, KeyframeTrack
from motion_math.easing import cubic_bezier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def approx(v, rel=1e-6):
    """pytest.approx wrapper with tighter default tolerance."""
    return pytest.approx(v, rel=rel)


# ---------------------------------------------------------------------------
# Linear interpolation
# ---------------------------------------------------------------------------

class TestLinearInterpolation:
    def test_at_start(self):
        track = KeyframeTrack()
        track.add(0.0, 0.0, "linear")
        track.add(1.0, 100.0, "linear")
        assert track.evaluate(0.0) == approx(0.0)

    def test_at_midpoint(self):
        track = KeyframeTrack()
        track.add(0.0, 0.0, "linear")
        track.add(1.0, 100.0, "linear")
        assert track.evaluate(0.5) == approx(50.0)

    def test_at_end(self):
        track = KeyframeTrack()
        track.add(0.0, 0.0, "linear")
        track.add(1.0, 100.0, "linear")
        assert track.evaluate(1.0) == approx(100.0)

    def test_quarter_point(self):
        track = KeyframeTrack()
        track.add(0.0, 0.0, "linear")
        track.add(1.0, 100.0, "linear")
        assert track.evaluate(0.25) == approx(25.0)

    def test_three_quarter_point(self):
        track = KeyframeTrack()
        track.add(0.0, 0.0, "linear")
        track.add(1.0, 100.0, "linear")
        assert track.evaluate(0.75) == approx(75.0)


# ---------------------------------------------------------------------------
# Eased interpolation (string name)
# ---------------------------------------------------------------------------

class TestEasedInterpolation:
    def test_ease_in_quad_at_half(self):
        """ease_in_quad(0.5) == 0.25, so value should be 25.0 (0 to 100)."""
        track = KeyframeTrack()
        track.add(0.0, 0.0, "linear")
        track.add(1.0, 100.0, "ease_in_quad")
        # progress=0.5, ease_in_quad(0.5)=0.25 → value=25.0
        assert track.evaluate(0.5) == approx(25.0)

    def test_ease_out_cubic_at_half(self):
        """ease_out_cubic(0.5) == 1 - 0.5^3 = 0.875, so value ≈ 87.5."""
        track = KeyframeTrack()
        track.add(0.0, 0.0, "linear")
        track.add(1.0, 100.0, "ease_out_cubic")
        assert track.evaluate(0.5) == approx(87.5)

    def test_easing_at_boundaries(self):
        """Easing should produce exact endpoint values regardless of function."""
        for ease_name in ["ease_in_quad", "ease_out_cubic", "ease_in_out_sine"]:
            track = KeyframeTrack()
            track.add(0.0, 10.0, "linear")
            track.add(2.0, 50.0, ease_name)
            assert track.evaluate(0.0) == approx(10.0), f"Start failed for {ease_name}"
            assert track.evaluate(2.0) == approx(50.0), f"End failed for {ease_name}"

    def test_unknown_easing_raises(self):
        track = KeyframeTrack()
        track.add(0.0, 0.0)
        track.add(1.0, 1.0, "not_a_real_easing_function")
        with pytest.raises(ValueError):
            track.evaluate(0.5)


# ---------------------------------------------------------------------------
# Multi-keyframe (3 keyframes, two segments)
# ---------------------------------------------------------------------------

class TestMultiKeyframe:
    def setup_method(self):
        """Track: 0→0, 1→100, 2→50 (all linear)."""
        self.track = KeyframeTrack()
        self.track.add(0.0, 0.0, "linear")
        self.track.add(1.0, 100.0, "linear")
        self.track.add(2.0, 50.0, "linear")

    def test_first_segment_midpoint(self):
        assert self.track.evaluate(0.5) == approx(50.0)

    def test_first_segment_end(self):
        assert self.track.evaluate(1.0) == approx(100.0)

    def test_second_segment_midpoint(self):
        # 1.0→100, 2.0→50; midpoint at 1.5 → 75.0
        assert self.track.evaluate(1.5) == approx(75.0)

    def test_second_segment_end(self):
        assert self.track.evaluate(2.0) == approx(50.0)

    def test_keyframes_sorted_property(self):
        """keyframes property returns sorted list of Keyframe objects."""
        kfs = self.track.keyframes
        times = [kf.time for kf in kfs]
        assert times == sorted(times)
        assert len(kfs) == 3

    def test_keyframes_is_copy(self):
        """Mutating the returned list does not affect the track."""
        kfs = self.track.keyframes
        kfs.clear()
        assert len(self.track.keyframes) == 3


# ---------------------------------------------------------------------------
# Hold behaviour (before first / after last)
# ---------------------------------------------------------------------------

class TestHoldBehaviour:
    def setup_method(self):
        self.track = KeyframeTrack()
        self.track.add(1.0, 42.0, "linear")
        self.track.add(3.0, 99.0, "linear")

    def test_before_first_holds_first_value(self):
        assert self.track.evaluate(0.0) == approx(42.0)
        assert self.track.evaluate(-5.0) == approx(42.0)
        assert self.track.evaluate(0.9999) == approx(42.0)

    def test_after_last_holds_last_value(self):
        assert self.track.evaluate(3.0) == approx(99.0)
        assert self.track.evaluate(5.0) == approx(99.0)
        assert self.track.evaluate(100.0) == approx(99.0)

    def test_single_keyframe_always_holds(self):
        track = KeyframeTrack()
        track.add(0.5, 7.0)
        assert track.evaluate(0.0) == approx(7.0)
        assert track.evaluate(0.5) == approx(7.0)
        assert track.evaluate(1.0) == approx(7.0)


# ---------------------------------------------------------------------------
# add() — replace existing keyframe
# ---------------------------------------------------------------------------

class TestAddReplace:
    def test_replace_at_exact_time(self):
        track = KeyframeTrack()
        track.add(0.0, 10.0)
        track.add(1.0, 20.0)
        track.add(0.0, 99.0)  # replace
        assert len(track.keyframes) == 2
        assert track.evaluate(0.0) == approx(99.0)

    def test_replace_within_tolerance(self):
        track = KeyframeTrack()
        track.add(0.0, 10.0)
        track.add(1.0, 20.0)
        track.add(1e-10, 55.0)  # within 1e-9 tolerance
        assert len(track.keyframes) == 2

    def test_no_replace_outside_tolerance(self):
        track = KeyframeTrack()
        track.add(0.0, 10.0)
        track.add(1.0, 20.0)
        track.add(2e-9, 55.0)  # outside 1e-9 tolerance
        assert len(track.keyframes) == 3


# ---------------------------------------------------------------------------
# remove() keyframe
# ---------------------------------------------------------------------------

class TestRemoveKeyframe:
    def test_remove_existing(self):
        track = KeyframeTrack()
        track.add(0.0, 0.0)
        track.add(1.0, 100.0)
        track.add(2.0, 50.0)
        track.remove(1.0)
        assert len(track.keyframes) == 2
        times = [kf.time for kf in track.keyframes]
        assert 1.0 not in times

    def test_remove_within_tolerance(self):
        track = KeyframeTrack()
        track.add(0.0, 0.0)
        track.add(1.0, 100.0)
        track.remove(1.0 + 5e-10)  # within tolerance
        assert len(track.keyframes) == 1

    def test_remove_nonexistent_raises(self):
        track = KeyframeTrack()
        track.add(0.0, 0.0)
        with pytest.raises((KeyError, ValueError)):
            track.remove(99.0)

    def test_remove_all_and_empty_track(self):
        track = KeyframeTrack()
        track.add(0.5, 5.0)
        track.remove(0.5)
        assert len(track.keyframes) == 0


# ---------------------------------------------------------------------------
# bake()
# ---------------------------------------------------------------------------

class TestBake:
    def test_bake_length_30fps_1s(self):
        """bake(30, 1.0) should return 31 values (frames 0..30 inclusive)."""
        track = KeyframeTrack()
        track.add(0.0, 0.0, "linear")
        track.add(1.0, 30.0, "linear")
        result = track.bake(30, 1.0)
        assert len(result) == 31

    def test_bake_values_linear(self):
        """Values should match evaluate() at each frame time."""
        track = KeyframeTrack()
        track.add(0.0, 0.0, "linear")
        track.add(1.0, 30.0, "linear")
        result = track.bake(30, 1.0)
        # frame 0 → t=0.0 → 0.0
        assert result[0] == approx(0.0)
        # frame 15 → t=0.5 → 15.0
        assert result[15] == approx(15.0)
        # frame 30 → t=1.0 → 30.0
        assert result[30] == approx(30.0)

    def test_bake_length_24fps_2s(self):
        """bake(24, 2.0) → int(2.0 * 24) + 1 = 49 values."""
        track = KeyframeTrack()
        track.add(0.0, 0.0)
        track.add(2.0, 48.0)
        result = track.bake(24, 2.0)
        assert len(result) == 49

    def test_bake_returns_list(self):
        track = KeyframeTrack()
        track.add(0.0, 1.0)
        track.add(1.0, 2.0)
        result = track.bake(10, 1.0)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Callable easing (cubic_bezier)
# ---------------------------------------------------------------------------

class TestCallableEasing:
    def test_callable_applied(self):
        """Using cubic_bezier as easing callable."""
        ease_fn = cubic_bezier(0.42, 0.0, 0.58, 1.0)  # ease-in-out
        track = KeyframeTrack()
        track.add(0.0, 0.0, "linear")
        track.add(1.0, 100.0, ease_fn)
        # At midpoint, ease-in-out is symmetric so value ≈ 50
        val = track.evaluate(0.5)
        assert 45.0 < val < 55.0  # loose check — it's symmetric but not exact linear

    def test_callable_endpoints(self):
        """Callable easing must produce exact endpoint values."""
        ease_fn = cubic_bezier(0.25, 0.1, 0.25, 1.0)
        track = KeyframeTrack()
        track.add(0.0, 5.0, "linear")
        track.add(2.0, 15.0, ease_fn)
        assert track.evaluate(0.0) == approx(5.0)
        assert track.evaluate(2.0) == approx(15.0)

    def test_lambda_easing(self):
        """A plain lambda works as an easing callable."""
        track = KeyframeTrack()
        track.add(0.0, 0.0, "linear")
        track.add(1.0, 100.0, lambda t: t * t)  # same as ease_in_quad
        assert track.evaluate(0.5) == approx(25.0)


# ---------------------------------------------------------------------------
# evaluate_batch()
# ---------------------------------------------------------------------------

class TestEvaluateBatch:
    def test_batch_matches_scalar(self):
        """evaluate_batch results must match individual evaluate() calls."""
        track = KeyframeTrack()
        track.add(0.0, 0.0, "linear")
        track.add(1.0, 100.0, "linear")
        import numpy as np
        times = np.linspace(0.0, 1.0, 11)
        batch = track.evaluate_batch(times)
        for i, t in enumerate(times):
            assert float(batch[i]) == approx(float(track.evaluate(t)))

    def test_batch_returns_array_or_list(self):
        """evaluate_batch returns numpy array if available, else list."""
        track = KeyframeTrack()
        track.add(0.0, 0.0)
        track.add(1.0, 1.0)
        try:
            import numpy as np
            times = np.array([0.0, 0.5, 1.0])
            result = track.evaluate_batch(times)
            assert hasattr(result, '__len__')
        except ImportError:
            result = track.evaluate_batch([0.0, 0.5, 1.0])
            assert isinstance(result, list)

    def test_batch_length(self):
        track = KeyframeTrack()
        track.add(0.0, 0.0)
        track.add(1.0, 10.0)
        try:
            import numpy as np
            times = np.linspace(0.0, 1.0, 50)
        except ImportError:
            times = [i / 49.0 for i in range(50)]
        result = track.evaluate_batch(times)
        assert len(result) == 50

    def test_batch_eased(self):
        """Batch evaluation respects easing functions."""
        track = KeyframeTrack()
        track.add(0.0, 0.0, "linear")
        track.add(1.0, 100.0, "ease_in_quad")
        try:
            import numpy as np
            times = np.array([0.0, 0.5, 1.0])
        except ImportError:
            times = [0.0, 0.5, 1.0]
        result = track.evaluate_batch(times)
        assert float(result[0]) == approx(0.0)
        assert float(result[1]) == approx(25.0)
        assert float(result[2]) == approx(100.0)


# ---------------------------------------------------------------------------
# Keyframe dataclass
# ---------------------------------------------------------------------------

class TestKeyframeDataclass:
    def test_keyframe_fields(self):
        kf = Keyframe(time=1.0, value=42.0, easing="linear")
        assert kf.time == 1.0
        assert kf.value == 42.0
        assert kf.easing == "linear"

    def test_keyframe_callable_easing(self):
        fn = lambda t: t
        kf = Keyframe(time=0.5, value=10.0, easing=fn)
        assert callable(kf.easing)

    def test_default_easing_is_linear(self):
        """KeyframeTrack.add() defaults to 'linear'."""
        track = KeyframeTrack()
        track.add(0.0, 0.0)
        track.add(1.0, 10.0)
        kfs = track.keyframes
        assert kfs[0].easing == "linear"
        assert kfs[1].easing == "linear"
