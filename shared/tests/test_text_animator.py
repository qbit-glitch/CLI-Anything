"""Tests for shared/motion_math/text_animator.py.

TDD: tests written before implementation.

Coverage:
- CharInfo dataclass
- CharacterAnimator.decompose
- CharacterAnimator.stagger (left_to_right, right_to_left, center_out, random)
- Presets: typewriter, wave, cascade_in, scale_pop, bounce_in, random_fade
"""

from __future__ import annotations

import pytest
from motion_math.text_animator import CharInfo, CharacterAnimator
from motion_math.keyframes import KeyframeTrack


# ---------------------------------------------------------------------------
# CharInfo dataclass
# ---------------------------------------------------------------------------

class TestCharInfo:
    def test_required_fields(self):
        ci = CharInfo(char="A", index=0, x_offset=0.0, width=1.0)
        assert ci.char == "A"
        assert ci.index == 0
        assert ci.x_offset == 0.0
        assert ci.width == 1.0

    def test_default_line(self):
        ci = CharInfo(char="B", index=1, x_offset=1.0, width=1.0)
        assert ci.line == 0

    def test_explicit_line(self):
        ci = CharInfo(char="C", index=2, x_offset=0.0, width=1.0, line=1)
        assert ci.line == 1


# ---------------------------------------------------------------------------
# CharacterAnimator.decompose
# ---------------------------------------------------------------------------

class TestDecompose:
    def test_simple_text_count(self):
        """5-char string produces 5 CharInfo objects."""
        chars = CharacterAnimator.decompose("Hello")
        assert len(chars) == 5

    def test_simple_text_chars(self):
        chars = CharacterAnimator.decompose("Hello")
        assert [c.char for c in chars] == list("Hello")

    def test_offsets_increase(self):
        """x_offset increases monotonically for single-line text."""
        chars = CharacterAnimator.decompose("abc", char_width=1.0)
        offsets = [c.x_offset for c in chars]
        assert offsets == [0.0, 1.0, 2.0]

    def test_custom_char_width(self):
        chars = CharacterAnimator.decompose("ab", char_width=2.5)
        assert chars[0].x_offset == pytest.approx(0.0)
        assert chars[1].x_offset == pytest.approx(2.5)

    def test_indices_sequential(self):
        chars = CharacterAnimator.decompose("xyz")
        assert [c.index for c in chars] == [0, 1, 2]

    def test_width_stored(self):
        chars = CharacterAnimator.decompose("abc", char_width=1.5)
        for c in chars:
            assert c.width == pytest.approx(1.5)

    def test_space_included(self):
        """Spaces are included as regular characters in output."""
        chars = CharacterAnimator.decompose("a b")
        assert len(chars) == 3
        assert chars[1].char == " "

    def test_space_offset(self):
        chars = CharacterAnimator.decompose("a b", char_width=1.0)
        assert chars[1].x_offset == pytest.approx(1.0)
        assert chars[2].x_offset == pytest.approx(2.0)

    def test_multiline_line_numbers(self):
        """Newlines increment line counter; chars after newline are on next line."""
        chars = CharacterAnimator.decompose("ab\ncd")
        # 'a', 'b' on line 0; 'c', 'd' on line 1
        assert chars[0].line == 0
        assert chars[1].line == 0
        assert chars[2].line == 1
        assert chars[3].line == 1

    def test_multiline_newline_not_in_output(self):
        """Newline characters themselves are NOT included in the output."""
        chars = CharacterAnimator.decompose("a\nb")
        assert len(chars) == 2
        assert all(c.char != "\n" for c in chars)

    def test_multiline_x_resets(self):
        """After a newline, x_offset resets to 0."""
        chars = CharacterAnimator.decompose("ab\ncd", char_width=1.0)
        # 'c' should be at x=0 (start of new line)
        assert chars[2].x_offset == pytest.approx(0.0)
        assert chars[3].x_offset == pytest.approx(1.0)

    def test_empty_string(self):
        chars = CharacterAnimator.decompose("")
        assert chars == []

    def test_single_char(self):
        chars = CharacterAnimator.decompose("X")
        assert len(chars) == 1
        assert chars[0].char == "X"
        assert chars[0].index == 0
        assert chars[0].x_offset == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# CharacterAnimator.stagger
# ---------------------------------------------------------------------------

class TestStagger:
    def _make_base_track(self) -> KeyframeTrack:
        """A simple opacity track: 0 → 1 over 0.3 seconds."""
        t = KeyframeTrack()
        t.add(0.0, 0.0, "linear")
        t.add(0.3, 1.0, "linear")
        return t

    def test_returns_dict(self):
        chars = CharacterAnimator.decompose("abc")
        base = self._make_base_track()
        result = CharacterAnimator.stagger(chars, base, delay_per_char=0.05)
        assert isinstance(result, dict)

    def test_keys_are_char_indices(self):
        chars = CharacterAnimator.decompose("abc")
        base = self._make_base_track()
        result = CharacterAnimator.stagger(chars, base, delay_per_char=0.05)
        assert set(result.keys()) == {0, 1, 2}

    def test_values_are_keyframe_tracks(self):
        chars = CharacterAnimator.decompose("ab")
        base = self._make_base_track()
        result = CharacterAnimator.stagger(chars, base, delay_per_char=0.05)
        for v in result.values():
            assert isinstance(v, KeyframeTrack)

    # --- left_to_right ---

    def test_left_to_right_first_ahead_of_second(self):
        """In left_to_right, char 0 starts animating before char 1."""
        chars = CharacterAnimator.decompose("ab")
        base = self._make_base_track()
        result = CharacterAnimator.stagger(
            chars, base, delay_per_char=0.1, order="left_to_right"
        )
        # At t=0.1, char 0 should have started (positive value), char 1 just starts
        val_0_early = result[0].evaluate(0.05)
        val_1_early = result[1].evaluate(0.05)
        assert val_0_early > val_1_early

    def test_left_to_right_delays_accumulate(self):
        """Each subsequent char starts delay_per_char seconds later."""
        chars = CharacterAnimator.decompose("abcd")
        base = self._make_base_track()
        delay = 0.1
        result = CharacterAnimator.stagger(
            chars, base, delay_per_char=delay, order="left_to_right"
        )
        # Char i should evaluate to 0 at t = i*delay - epsilon (before it starts)
        for i in range(4):
            t_before_start = i * delay - 0.001
            if t_before_start > 0:
                assert result[i].evaluate(t_before_start) == pytest.approx(0.0, abs=1e-6)

    # --- right_to_left ---

    def test_right_to_left_last_char_starts_first(self):
        """In right_to_left, the last char starts first."""
        chars = CharacterAnimator.decompose("abcd")
        base = self._make_base_track()
        result = CharacterAnimator.stagger(
            chars, base, delay_per_char=0.1, order="right_to_left"
        )
        # At t=0.05, the last char should have a higher value than the first
        val_first = result[0].evaluate(0.05)
        val_last = result[len(chars) - 1].evaluate(0.05)
        assert val_last > val_first

    # --- center_out ---

    def test_center_out_center_char_starts_first(self):
        """In center_out, the center character starts animating earliest."""
        text = "abcde"  # 5 chars, center is index 2
        chars = CharacterAnimator.decompose(text)
        base = self._make_base_track()
        result = CharacterAnimator.stagger(
            chars, base, delay_per_char=0.1, order="center_out"
        )
        # At t=0.05, center char (index 2) should be ahead of edge chars
        val_center = result[2].evaluate(0.05)
        val_edge_left = result[0].evaluate(0.05)
        val_edge_right = result[4].evaluate(0.05)
        assert val_center > val_edge_left
        assert val_center > val_edge_right

    def test_center_out_symmetric(self):
        """Chars equidistant from center have equal delays."""
        text = "abcde"  # 5 chars, center=2; chars 1 and 3 are equidistant
        chars = CharacterAnimator.decompose(text)
        base = self._make_base_track()
        result = CharacterAnimator.stagger(
            chars, base, delay_per_char=0.1, order="center_out"
        )
        # Evaluate both at t=0.2 — should be equal (or very close)
        val_left = result[1].evaluate(0.2)
        val_right = result[3].evaluate(0.2)
        assert val_left == pytest.approx(val_right, abs=1e-6)

    # --- random ---

    def test_random_returns_all_chars(self):
        chars = CharacterAnimator.decompose("hello")
        base = self._make_base_track()
        result = CharacterAnimator.stagger(
            chars, base, delay_per_char=0.05, order="random"
        )
        assert set(result.keys()) == {0, 1, 2, 3, 4}

    def test_invalid_order_raises(self):
        chars = CharacterAnimator.decompose("ab")
        base = self._make_base_track()
        with pytest.raises(ValueError):
            CharacterAnimator.stagger(chars, base, delay_per_char=0.1, order="diagonal")


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

class TestPresetTypewriter:
    def test_returns_dict(self):
        result = CharacterAnimator.preset_typewriter("Hi")
        assert isinstance(result, dict)

    def test_keys_match_char_count(self):
        result = CharacterAnimator.preset_typewriter("Hello")
        assert set(result.keys()) == {0, 1, 2, 3, 4}

    def test_first_char_visible_early(self):
        """The first char should be fully visible (opacity=1) before the last char is."""
        result = CharacterAnimator.preset_typewriter("Hello", char_duration=0.05)
        # At t = 0.06, char 0 should be done (opacity ~1), char 4 not yet started
        val_first = result[0].evaluate(0.06)
        val_last = result[4].evaluate(0.06)
        assert val_first > val_last

    def test_last_char_visible_late(self):
        """The last char should reach full opacity after the first."""
        result = CharacterAnimator.preset_typewriter("Hello", char_duration=0.05)
        # At t = total_time (all chars done + buffer), last char should be ~1
        n = 5
        total = n * 0.05 + 0.1  # enough time for all chars
        val_last = result[4].evaluate(total)
        assert val_last == pytest.approx(1.0, abs=1e-6)

    def test_values_are_keyframe_tracks(self):
        result = CharacterAnimator.preset_typewriter("Hi")
        for v in result.values():
            assert isinstance(v, KeyframeTrack)


class TestPresetWave:
    def test_returns_dict(self):
        result = CharacterAnimator.preset_wave("abc")
        assert isinstance(result, dict)

    def test_keys_match_char_count(self):
        result = CharacterAnimator.preset_wave("Hello")
        assert set(result.keys()) == {0, 1, 2, 3, 4}

    def test_values_are_keyframe_tracks(self):
        result = CharacterAnimator.preset_wave("Hi")
        for v in result.values():
            assert isinstance(v, KeyframeTrack)

    def test_y_offset_oscillates(self):
        """The wave should produce both positive and negative (or zero) y-offsets."""
        result = CharacterAnimator.preset_wave("A", amplitude=10, frequency=1, duration=2.0, fps=30)
        track = result[0]
        values = [track.evaluate(t) for t in [i / 30 for i in range(61)]]
        assert max(values) > 0
        assert min(values) < max(values)  # not all same value


class TestPresetCascadeIn:
    def test_returns_dict(self):
        result = CharacterAnimator.preset_cascade_in("abc")
        assert isinstance(result, dict)

    def test_keys_match_char_count(self):
        result = CharacterAnimator.preset_cascade_in("Hello")
        assert set(result.keys()) == {0, 1, 2, 3, 4}

    def test_values_are_keyframe_tracks(self):
        result = CharacterAnimator.preset_cascade_in("Hi")
        for v in result.values():
            assert isinstance(v, KeyframeTrack)

    def test_first_char_leads(self):
        """First char should complete before last char starts."""
        result = CharacterAnimator.preset_cascade_in("Hello", duration=0.3, delay=0.1)
        # After char 0 finishes (t=0.3), char 4 hasn't started (delay=4*0.1=0.4)
        val_first_done = result[0].evaluate(0.35)
        val_last_start = result[4].evaluate(0.35)
        assert val_first_done > val_last_start


class TestPresetScalePop:
    def test_returns_dict(self):
        result = CharacterAnimator.preset_scale_pop("abc")
        assert isinstance(result, dict)

    def test_keys_match(self):
        result = CharacterAnimator.preset_scale_pop("Hi")
        assert set(result.keys()) == {0, 1}

    def test_values_are_keyframe_tracks(self):
        result = CharacterAnimator.preset_scale_pop("Hi")
        for v in result.values():
            assert isinstance(v, KeyframeTrack)

    def test_scale_reaches_one(self):
        """At full animation time, all chars should reach scale 1."""
        text = "Hi"
        duration = 0.4
        delay = 0.05
        result = CharacterAnimator.preset_scale_pop(text, duration=duration, delay=delay)
        # After last char finishes: t = (n-1)*delay + duration + buffer
        t_end = (len(text) - 1) * delay + duration + 0.1
        for track in result.values():
            assert track.evaluate(t_end) == pytest.approx(1.0, abs=1e-6)


class TestPresetBounceIn:
    def test_returns_dict(self):
        result = CharacterAnimator.preset_bounce_in("abc")
        assert isinstance(result, dict)

    def test_keys_match(self):
        result = CharacterAnimator.preset_bounce_in("Hi")
        assert set(result.keys()) == {0, 1}

    def test_values_are_keyframe_tracks(self):
        result = CharacterAnimator.preset_bounce_in("Hi")
        for v in result.values():
            assert isinstance(v, KeyframeTrack)

    def test_reaches_one(self):
        """After full animation, chars reach scale/opacity 1."""
        text = "Hi"
        duration = 0.6
        delay = 0.04
        result = CharacterAnimator.preset_bounce_in(text, duration=duration, delay=delay)
        t_end = (len(text) - 1) * delay + duration + 0.1
        for track in result.values():
            assert track.evaluate(t_end) == pytest.approx(1.0, abs=1e-6)


class TestPresetRandomFade:
    def test_returns_dict(self):
        result = CharacterAnimator.preset_random_fade("abc")
        assert isinstance(result, dict)

    def test_keys_match(self):
        result = CharacterAnimator.preset_random_fade("Hello")
        assert set(result.keys()) == {0, 1, 2, 3, 4}

    def test_values_are_keyframe_tracks(self):
        result = CharacterAnimator.preset_random_fade("Hi")
        for v in result.values():
            assert isinstance(v, KeyframeTrack)

    def test_all_visible_at_end(self):
        """All chars should be fully visible by total_duration + char_duration."""
        text = "Hello"
        total_duration = 1.0
        char_duration = 0.3
        result = CharacterAnimator.preset_random_fade(
            text, total_duration=total_duration, char_duration=char_duration
        )
        t_end = total_duration + char_duration + 0.1
        for track in result.values():
            assert track.evaluate(t_end) == pytest.approx(1.0, abs=1e-6)

    def test_not_all_same_start(self):
        """Random fade should give different start times (not all identical)."""
        text = "Hello World"
        result = CharacterAnimator.preset_random_fade(text, total_duration=2.0, char_duration=0.3)
        # Check that different chars have different first keyframe times
        first_kf_times = [result[i].keyframes[0].time for i in range(len(text.replace(" ", "")) + text.count(" "))]
        # Not all the same
        assert len(set(first_kf_times)) > 1


# ---------------------------------------------------------------------------
# Integration: decompose + stagger round-trip
# ---------------------------------------------------------------------------

class TestDecomposeStaggerIntegration:
    def test_full_pipeline(self):
        """decompose → stagger should produce one track per character."""
        text = "Motion"
        chars = CharacterAnimator.decompose(text)
        base = KeyframeTrack()
        base.add(0.0, 0.0, "linear")
        base.add(0.5, 1.0, "ease_out_cubic")
        result = CharacterAnimator.stagger(chars, base, delay_per_char=0.05)
        assert len(result) == len(text)
        # All chars eventually reach 1.0
        t_end = (len(text) - 1) * 0.05 + 0.6
        for i in range(len(text)):
            assert result[i].evaluate(t_end) == pytest.approx(1.0, abs=1e-6)

    def test_preset_typewriter_then_stagger(self):
        """preset_typewriter produces staggered opacity tracks for multiline text."""
        text = "Hi\nThere"
        result = CharacterAnimator.preset_typewriter(text, char_duration=0.05)
        # "Hi\nThere" → H, i, T, h, e, r, e = 7 chars (no newline)
        assert len(result) == 7
