"""Unit tests for the Blender per-character 3D text animation module.

Tests verify:
- explode_text creates correct character metadata and bpy script lines
- Each animation preset produces valid script with expected bpy operations
- Per-character keyframe_insert calls appear in output
- Error handling for invalid arguments
"""

import math
import os
import sys

import pytest

# Ensure the agent-harness package root is on the path
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from cli_anything.blender.core.scene import create_scene
from cli_anything.blender.core.session import Session
from cli_anything.blender.core.text_3d import (
    explode_text,
    animate_typewriter,
    animate_wave,
    animate_cascade,
    animate_bounce,
    animate_scale_pop,
    animate_spiral_in,
    animate_extrude_in,
    animate_rotate_3d,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_session() -> Session:
    """Return a Session pre-loaded with a blank scene."""
    sess = Session()
    proj = create_scene(name="TestScene")
    sess.set_project(proj)
    return sess


def script_str(lines) -> str:
    """Join a list of bpy script lines into a single string for searching."""
    return "\n".join(lines)


# ── explode_text ──────────────────────────────────────────────────────────────


class TestExplodeText:
    def test_returns_dict_with_chars_and_script(self):
        sess = make_session()
        result = explode_text(sess, "Hi")
        assert isinstance(result, dict)
        assert "chars" in result
        assert "script_lines" in result

    def test_char_count_matches_text_length(self):
        sess = make_session()
        result = explode_text(sess, "Hello")
        assert len(result["chars"]) == 5

    def test_newline_not_in_chars(self):
        sess = make_session()
        result = explode_text(sess, "Hi\nThere")
        # 'Hi' = 2, 'There' = 5 → 7 chars total, no newline
        assert len(result["chars"]) == 7

    def test_char_names_use_prefix(self):
        sess = make_session()
        result = explode_text(sess, "AB", name_prefix="letter")
        names = [c["name"] for c in result["chars"]]
        assert names[0].startswith("letter_")
        assert names[1].startswith("letter_")

    def test_char_positions_increase_along_x(self):
        sess = make_session()
        result = explode_text(sess, "ABC")
        xs = [c["position"][0] for c in result["chars"]]
        assert xs[0] < xs[1] < xs[2]

    def test_newline_increments_y(self):
        sess = make_session()
        result = explode_text(sess, "A\nB")
        chars = result["chars"]
        # 'A' on line 0, 'B' on line 1 → B has a lower y (negative offset)
        y_a = chars[0]["position"][1]
        y_b = chars[1]["position"][1]
        assert y_b < y_a

    def test_script_contains_text_add(self):
        sess = make_session()
        result = explode_text(sess, "Hi")
        assert "text_add" in script_str(result["script_lines"])

    def test_script_has_name_assignment(self):
        sess = make_session()
        result = explode_text(sess, "A", name_prefix="ch")
        assert ".name = " in script_str(result["script_lines"])

    def test_script_has_body_assignment(self):
        sess = make_session()
        result = explode_text(sess, "Z")
        assert ".data.body = " in script_str(result["script_lines"])

    def test_script_has_size_assignment(self):
        sess = make_session()
        result = explode_text(sess, "X", size=2.5)
        assert "data.size = 2.5" in script_str(result["script_lines"])

    def test_script_has_extrude_assignment(self):
        sess = make_session()
        result = explode_text(sess, "Y", extrude=0.2)
        assert "data.extrude = 0.2" in script_str(result["script_lines"])

    def test_font_path_in_script(self):
        sess = make_session()
        result = explode_text(sess, "T", font_path="/usr/share/fonts/test.ttf")
        assert "fonts.load" in script_str(result["script_lines"])

    def test_empty_text_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="empty"):
            explode_text(sess, "")

    def test_negative_size_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="size"):
            explode_text(sess, "A", size=-1.0)

    def test_project_stores_text3d_objects(self):
        sess = make_session()
        explode_text(sess, "Hi", name_prefix="t")
        proj = sess.get_project()
        assert "text3d_objects" in proj
        assert len(proj["text3d_objects"]) == 1

    def test_one_text_add_per_character(self):
        sess = make_session()
        result = explode_text(sess, "ABC")
        text_add_count = script_str(result["script_lines"]).count("text_add")
        assert text_add_count == 3

    def test_spaces_are_included(self):
        sess = make_session()
        result = explode_text(sess, "A B")
        assert len(result["chars"]) == 3

    def test_default_char_metadata_fields(self):
        sess = make_session()
        result = explode_text(sess, "Q")
        c = result["chars"][0]
        assert "name" in c
        assert "char" in c
        assert "index" in c
        assert "position" in c
        assert "line" in c


# ── animate_typewriter ────────────────────────────────────────────────────────


class TestAnimateTypewriter:
    def test_returns_list_of_strings(self):
        sess = make_session()
        explode_text(sess, "Hi")
        lines = animate_typewriter(sess, "Hi")
        assert isinstance(lines, list)
        assert all(isinstance(l, str) for l in lines)

    def test_contains_keyframe_insert(self):
        sess = make_session()
        explode_text(sess, "AB")
        lines = animate_typewriter(sess, "AB")
        assert "keyframe_insert" in script_str(lines)

    def test_contains_scale_data_path(self):
        sess = make_session()
        explode_text(sess, "AB")
        lines = animate_typewriter(sess, "AB")
        assert "scale" in script_str(lines)

    def test_empty_text_returns_empty(self):
        sess = make_session()
        lines = animate_typewriter(sess, "")
        assert lines == []

    def test_each_char_has_object_lookup(self):
        sess = make_session()
        explode_text(sess, "Hi")
        lines = animate_typewriter(sess, "Hi")
        count = script_str(lines).count("bpy.data.objects.get")
        assert count == 2

    def test_scale_values_between_0_and_1(self):
        sess = make_session()
        explode_text(sess, "A", name_prefix="ch")
        lines = animate_typewriter(sess, "A", name_prefix="ch")
        # Grab all scale = (x, y, z) lines
        scale_lines = [l for l in lines if ".scale = " in l]
        assert len(scale_lines) > 0
        for sl in scale_lines:
            # Extract numeric value; format is (x, x, x)
            import re
            vals = re.findall(r'[\d.]+', sl.split("=")[1])
            if vals:
                v = float(vals[0])
                assert 0.0 <= v <= 1.0

    def test_comment_header_present(self):
        sess = make_session()
        explode_text(sess, "Test")
        lines = animate_typewriter(sess, "Test")
        assert any("Typewriter" in l or "typewriter" in l for l in lines)

    def test_multiple_chars_multiple_lookups(self):
        sess = make_session()
        explode_text(sess, "Hello")
        lines = animate_typewriter(sess, "Hello")
        count = script_str(lines).count("bpy.data.objects.get")
        assert count == 5


# ── animate_wave ──────────────────────────────────────────────────────────────


class TestAnimateWave:
    def test_returns_list(self):
        sess = make_session()
        explode_text(sess, "Wave")
        lines = animate_wave(sess, "Wave")
        assert isinstance(lines, list)

    def test_contains_keyframe_insert(self):
        sess = make_session()
        explode_text(sess, "Wave")
        lines = animate_wave(sess, "Wave")
        assert "keyframe_insert" in script_str(lines)

    def test_contains_location_z(self):
        sess = make_session()
        explode_text(sess, "AB")
        lines = animate_wave(sess, "AB")
        s = script_str(lines)
        assert "location.z" in s

    def test_empty_text_returns_empty(self):
        sess = make_session()
        lines = animate_wave(sess, "")
        assert lines == []

    def test_comment_header(self):
        sess = make_session()
        explode_text(sess, "W")
        lines = animate_wave(sess, "W")
        assert any("Wave" in l or "wave" in l for l in lines)

    def test_index_2_used_for_z(self):
        sess = make_session()
        explode_text(sess, "AB")
        lines = animate_wave(sess, "AB")
        assert "index=2" in script_str(lines)

    def test_per_char_different_phase(self):
        # Two-char wave → two separate object lookups
        sess = make_session()
        explode_text(sess, "AB")
        lines = animate_wave(sess, "AB", amplitude=1.0, frequency=1.0, duration=1.0)
        assert script_str(lines).count("bpy.data.objects.get") == 2


# ── animate_cascade ───────────────────────────────────────────────────────────


class TestAnimateCascade:
    def test_returns_list(self):
        sess = make_session()
        explode_text(sess, "Go")
        lines = animate_cascade(sess, "Go")
        assert isinstance(lines, list)

    def test_contains_keyframe_insert(self):
        sess = make_session()
        explode_text(sess, "Go")
        lines = animate_cascade(sess, "Go")
        assert "keyframe_insert" in script_str(lines)

    def test_contains_scale(self):
        sess = make_session()
        explode_text(sess, "Go")
        lines = animate_cascade(sess, "Go")
        assert "scale" in script_str(lines)

    def test_invalid_direction_raises(self):
        sess = make_session()
        explode_text(sess, "X")
        with pytest.raises(ValueError, match="direction"):
            animate_cascade(sess, "X", direction="diagonal")

    def test_valid_directions(self):
        for d in ("left", "right", "top", "bottom"):
            sess = make_session()
            explode_text(sess, "X")
            lines = animate_cascade(sess, "X", direction=d)
            assert "keyframe_insert" in script_str(lines)

    def test_empty_text_returns_empty(self):
        sess = make_session()
        lines = animate_cascade(sess, "")
        assert lines == []


# ── animate_bounce ────────────────────────────────────────────────────────────


class TestAnimateBounce:
    def test_returns_list(self):
        sess = make_session()
        explode_text(sess, "Boo")
        lines = animate_bounce(sess, "Boo")
        assert isinstance(lines, list)

    def test_contains_keyframe_insert(self):
        sess = make_session()
        explode_text(sess, "Boo")
        lines = animate_bounce(sess, "Boo")
        assert "keyframe_insert" in script_str(lines)

    def test_contains_location_z(self):
        sess = make_session()
        explode_text(sess, "B")
        lines = animate_bounce(sess, "B")
        assert "location.z" in script_str(lines)

    def test_empty_text_returns_empty(self):
        sess = make_session()
        lines = animate_bounce(sess, "")
        assert lines == []

    def test_comment_header(self):
        sess = make_session()
        explode_text(sess, "B")
        lines = animate_bounce(sess, "B")
        assert any("Bounce" in l or "bounce" in l for l in lines)


# ── animate_scale_pop ─────────────────────────────────────────────────────────


class TestAnimateScalePop:
    def test_returns_list(self):
        sess = make_session()
        explode_text(sess, "Pop")
        lines = animate_scale_pop(sess, "Pop")
        assert isinstance(lines, list)

    def test_contains_keyframe_insert(self):
        sess = make_session()
        explode_text(sess, "Pop")
        lines = animate_scale_pop(sess, "Pop")
        assert "keyframe_insert" in script_str(lines)

    def test_scale_data_path(self):
        sess = make_session()
        explode_text(sess, "P")
        lines = animate_scale_pop(sess, "P")
        assert "scale" in script_str(lines)

    def test_empty_text_returns_empty(self):
        sess = make_session()
        lines = animate_scale_pop(sess, "")
        assert lines == []

    def test_comment_header(self):
        sess = make_session()
        explode_text(sess, "P")
        lines = animate_scale_pop(sess, "P")
        assert any("Scale" in l or "scale" in l or "pop" in l.lower() for l in lines)

    def test_per_char_object_lookup(self):
        sess = make_session()
        explode_text(sess, "XY")
        lines = animate_scale_pop(sess, "XY")
        assert script_str(lines).count("bpy.data.objects.get") == 2


# ── animate_spiral_in ─────────────────────────────────────────────────────────


class TestAnimateSpiralIn:
    def test_returns_list(self):
        sess = make_session()
        explode_text(sess, "Spin")
        lines = animate_spiral_in(sess, "Spin")
        assert isinstance(lines, list)

    def test_contains_keyframe_insert(self):
        sess = make_session()
        explode_text(sess, "Spin")
        lines = animate_spiral_in(sess, "Spin")
        assert "keyframe_insert" in script_str(lines)

    def test_contains_rotation(self):
        sess = make_session()
        explode_text(sess, "S")
        lines = animate_spiral_in(sess, "S")
        assert "rotation_euler" in script_str(lines)

    def test_contains_location(self):
        sess = make_session()
        explode_text(sess, "S")
        lines = animate_spiral_in(sess, "S")
        assert "location" in script_str(lines)

    def test_empty_text_returns_empty(self):
        sess = make_session()
        lines = animate_spiral_in(sess, "")
        assert lines == []

    def test_comment_header(self):
        sess = make_session()
        explode_text(sess, "S")
        lines = animate_spiral_in(sess, "S")
        assert any("Spiral" in l or "spiral" in l for l in lines)


# ── animate_extrude_in ────────────────────────────────────────────────────────


class TestAnimateExtrudeIn:
    def test_returns_list(self):
        sess = make_session()
        explode_text(sess, "Ext")
        lines = animate_extrude_in(sess, "Ext")
        assert isinstance(lines, list)

    def test_contains_keyframe_insert(self):
        sess = make_session()
        explode_text(sess, "Ext")
        lines = animate_extrude_in(sess, "Ext")
        assert "keyframe_insert" in script_str(lines)

    def test_animates_extrude_property(self):
        sess = make_session()
        explode_text(sess, "E")
        lines = animate_extrude_in(sess, "E")
        assert "extrude" in script_str(lines)

    def test_empty_text_returns_empty(self):
        sess = make_session()
        lines = animate_extrude_in(sess, "")
        assert lines == []

    def test_comment_header(self):
        sess = make_session()
        explode_text(sess, "E")
        lines = animate_extrude_in(sess, "E")
        assert any("Extrude" in l or "extrude" in l for l in lines)

    def test_extrude_values_bounded(self):
        sess = make_session()
        explode_text(sess, "A", name_prefix="ch")
        lines = animate_extrude_in(sess, "A", max_depth=0.5, name_prefix="ch")
        extrude_lines = [l for l in lines if ".data.extrude = " in l]
        assert len(extrude_lines) > 0
        for el in extrude_lines:
            val = float(el.split("= ")[-1].strip())
            assert 0.0 <= val <= 0.5 + 1e-6


# ── animate_rotate_3d ─────────────────────────────────────────────────────────


class TestAnimateRotate3D:
    def test_returns_list(self):
        sess = make_session()
        explode_text(sess, "Rot")
        lines = animate_rotate_3d(sess, "Rot")
        assert isinstance(lines, list)

    def test_contains_keyframe_insert(self):
        sess = make_session()
        explode_text(sess, "Rot")
        lines = animate_rotate_3d(sess, "Rot")
        assert "keyframe_insert" in script_str(lines)

    def test_contains_rotation_euler(self):
        sess = make_session()
        explode_text(sess, "R")
        lines = animate_rotate_3d(sess, "R")
        assert "rotation_euler" in script_str(lines)

    def test_empty_text_returns_empty(self):
        sess = make_session()
        lines = animate_rotate_3d(sess, "")
        assert lines == []

    def test_invalid_axis_raises(self):
        sess = make_session()
        explode_text(sess, "A")
        with pytest.raises(ValueError, match="axis"):
            animate_rotate_3d(sess, "A", axis="w")

    def test_valid_axes(self):
        for ax in ("x", "y", "z", "X", "Y", "Z"):
            sess = make_session()
            explode_text(sess, "A")
            lines = animate_rotate_3d(sess, "A", axis=ax)
            assert "keyframe_insert" in script_str(lines)

    def test_correct_axis_index_x(self):
        sess = make_session()
        explode_text(sess, "A")
        lines = animate_rotate_3d(sess, "A", axis="x")
        assert "index=0" in script_str(lines)

    def test_correct_axis_index_y(self):
        sess = make_session()
        explode_text(sess, "A")
        lines = animate_rotate_3d(sess, "A", axis="y")
        assert "index=1" in script_str(lines)

    def test_correct_axis_index_z(self):
        sess = make_session()
        explode_text(sess, "A")
        lines = animate_rotate_3d(sess, "A", axis="z")
        assert "index=2" in script_str(lines)

    def test_comment_header(self):
        sess = make_session()
        explode_text(sess, "R")
        lines = animate_rotate_3d(sess, "R")
        assert any("Rotate" in l or "rotate" in l or "3D" in l for l in lines)

    def test_per_char_keyframe_inserts(self):
        sess = make_session()
        explode_text(sess, "ABC")
        lines = animate_rotate_3d(sess, "ABC")
        assert script_str(lines).count("bpy.data.objects.get") == 3
