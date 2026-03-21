"""Unit tests for Blender CLI VSE (Video Sequence Editor) module.

Tests use synthetic data only — no real video files or Blender installation.
"""

import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cli_anything.blender.core.scene import create_scene
from cli_anything.blender.core.vse import (
    add_strip, remove_strip, move_strip, set_strip_property,
    add_transition, add_effect, list_strips, list_strip_types,
    list_transitions, list_effects,
    STRIP_TYPES, VSE_TRANSITIONS, VSE_EFFECTS,
)
from cli_anything.blender.utils.bpy_gen import generate_full_script


# ── Add Strip Tests ──────────────────────────────────────────────

class TestAddStrip:
    def _make_scene(self):
        return create_scene()

    def test_add_movie_strip(self):
        proj = self._make_scene()
        strip = add_strip(proj, "movie", 1, 1, source="/path/to/video.mp4")
        assert strip["type"] == "movie"
        assert strip["channel"] == 1
        assert strip["frame_start"] == 1
        assert strip["frame_end"] == 101  # default: start + 100
        assert strip["source"] == "/path/to/video.mp4"
        assert strip["blend_type"] == "REPLACE"
        assert strip["opacity"] == 1.0
        assert strip["mute"] is False
        assert len(proj["vse"]["strips"]) == 1

    def test_add_image_strip(self):
        proj = self._make_scene()
        strip = add_strip(proj, "image", 2, 10, source="/path/to/image.png",
                          frame_end=60, name="MyImage")
        assert strip["type"] == "image"
        assert strip["channel"] == 2
        assert strip["frame_start"] == 10
        assert strip["frame_end"] == 60
        assert strip["name"] == "MyImage"
        assert strip["source"] == "/path/to/image.png"

    def test_add_sound_strip(self):
        proj = self._make_scene()
        strip = add_strip(proj, "sound", 3, 1, source="/path/to/audio.wav")
        assert strip["type"] == "sound"
        assert strip["source"] == "/path/to/audio.wav"

    def test_add_color_strip(self):
        proj = self._make_scene()
        strip = add_strip(proj, "color", 1, 1, frame_end=50, color=[1.0, 0.0, 0.0])
        assert strip["type"] == "color"
        assert strip["color"] == [1.0, 0.0, 0.0]
        assert strip["frame_end"] == 50

    def test_add_color_strip_default_color(self):
        proj = self._make_scene()
        strip = add_strip(proj, "color", 1, 1, frame_end=50)
        assert strip["color"] == [1.0, 1.0, 1.0]

    def test_add_text_strip(self):
        proj = self._make_scene()
        strip = add_strip(proj, "text", 4, 1, frame_end=100,
                          text="Hello World", font_size=72)
        assert strip["type"] == "text"
        assert strip["text"] == "Hello World"
        assert strip["font_size"] == 72

    def test_add_text_strip_default_text(self):
        proj = self._make_scene()
        strip = add_strip(proj, "text", 1, 1, frame_end=50)
        assert strip["text"] == "Text"
        assert strip["font_size"] == 48  # default font size

    def test_add_adjustment_strip(self):
        proj = self._make_scene()
        strip = add_strip(proj, "adjustment", 5, 1, frame_end=200)
        assert strip["type"] == "adjustment"

    def test_add_strip_auto_name(self):
        proj = self._make_scene()
        strip = add_strip(proj, "color", 1, 1, frame_end=50)
        assert "Color" in strip["name"]

    def test_add_strip_unique_ids(self):
        proj = self._make_scene()
        s1 = add_strip(proj, "color", 1, 1, frame_end=50)
        s2 = add_strip(proj, "color", 2, 1, frame_end=50)
        assert s1["id"] != s2["id"]

    def test_add_strip_invalid_type(self):
        proj = self._make_scene()
        with pytest.raises(ValueError, match="Unknown strip type"):
            add_strip(proj, "invalid_type", 1, 1)

    def test_add_strip_invalid_channel(self):
        proj = self._make_scene()
        with pytest.raises(ValueError, match="Channel must be >= 1"):
            add_strip(proj, "color", 0, 1, frame_end=50)

    def test_add_strip_negative_frame_start(self):
        proj = self._make_scene()
        with pytest.raises(ValueError, match="non-negative"):
            add_strip(proj, "color", 1, -1, frame_end=50)

    def test_add_strip_frame_end_before_start(self):
        proj = self._make_scene()
        with pytest.raises(ValueError, match="must be > frame_start"):
            add_strip(proj, "color", 1, 100, frame_end=50)

    def test_add_movie_strip_no_source(self):
        proj = self._make_scene()
        with pytest.raises(ValueError, match="requires a source"):
            add_strip(proj, "movie", 1, 1)

    def test_add_sound_strip_no_source(self):
        proj = self._make_scene()
        with pytest.raises(ValueError, match="requires a source"):
            add_strip(proj, "sound", 1, 1)

    def test_add_image_strip_no_source(self):
        proj = self._make_scene()
        with pytest.raises(ValueError, match="requires a source"):
            add_strip(proj, "image", 1, 1)

    def test_add_color_strip_invalid_color(self):
        proj = self._make_scene()
        with pytest.raises(ValueError, match="0.0-1.0"):
            add_strip(proj, "color", 1, 1, frame_end=50, color=[2.0, 0.0, 0.0])

    def test_add_color_strip_wrong_color_components(self):
        proj = self._make_scene()
        with pytest.raises(ValueError, match="3 components"):
            add_strip(proj, "color", 1, 1, frame_end=50, color=[1.0, 0.0])

    def test_add_multiple_strips(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        add_strip(proj, "color", 2, 1, frame_end=50)
        add_strip(proj, "text", 3, 1, frame_end=50, text="Title")
        assert len(proj["vse"]["strips"]) == 3


# ── Remove Strip Tests ──────────────────────────────────────────

class TestRemoveStrip:
    def _make_scene(self):
        return create_scene()

    def test_remove_strip(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50, name="First")
        add_strip(proj, "color", 2, 1, frame_end=50, name="Second")
        removed = remove_strip(proj, 0)
        assert removed["name"] == "First"
        assert len(proj["vse"]["strips"]) == 1
        assert proj["vse"]["strips"][0]["name"] == "Second"

    def test_remove_strip_empty(self):
        proj = self._make_scene()
        with pytest.raises(ValueError, match="No strips"):
            remove_strip(proj, 0)

    def test_remove_strip_invalid_index(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        with pytest.raises(IndexError):
            remove_strip(proj, 5)

    def test_remove_strip_negative_index(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        with pytest.raises(IndexError):
            remove_strip(proj, -1)


# ── Move Strip Tests ────────────────────────────────────────────

class TestMoveStrip:
    def _make_scene(self):
        return create_scene()

    def test_move_strip_channel(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        strip = move_strip(proj, 0, channel=3)
        assert strip["channel"] == 3

    def test_move_strip_frame(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 10, frame_end=60)
        strip = move_strip(proj, 0, frame_start=100)
        assert strip["frame_start"] == 100
        assert strip["frame_end"] == 150  # preserves duration (50 frames)

    def test_move_strip_both(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 10, frame_end=60)
        strip = move_strip(proj, 0, channel=5, frame_start=200)
        assert strip["channel"] == 5
        assert strip["frame_start"] == 200

    def test_move_strip_invalid_index(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        with pytest.raises(IndexError):
            move_strip(proj, 5, channel=2)

    def test_move_strip_invalid_channel(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        with pytest.raises(ValueError, match="Channel must be >= 1"):
            move_strip(proj, 0, channel=0)

    def test_move_strip_negative_frame(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        with pytest.raises(ValueError, match="non-negative"):
            move_strip(proj, 0, frame_start=-10)


# ── Set Strip Property Tests ────────────────────────────────────

class TestSetStripProperty:
    def _make_scene(self):
        return create_scene()

    def test_set_opacity(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        strip = set_strip_property(proj, 0, "opacity", 0.5)
        assert strip["opacity"] == 0.5

    def test_set_opacity_out_of_range(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        with pytest.raises(ValueError, match="0.0-1.0"):
            set_strip_property(proj, 0, "opacity", 1.5)

    def test_set_blend_type(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        strip = set_strip_property(proj, 0, "blend_type", "ADD")
        assert strip["blend_type"] == "ADD"

    def test_set_blend_type_invalid(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        with pytest.raises(ValueError, match="Invalid blend type"):
            set_strip_property(proj, 0, "blend_type", "BOGUS")

    def test_set_mute(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        strip = set_strip_property(proj, 0, "mute", True)
        assert strip["mute"] is True

    def test_set_mute_string(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        strip = set_strip_property(proj, 0, "mute", "true")
        assert strip["mute"] is True

    def test_set_name(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        strip = set_strip_property(proj, 0, "name", "MyStrip")
        assert strip["name"] == "MyStrip"

    def test_set_color(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        strip = set_strip_property(proj, 0, "color", [0.5, 0.5, 0.5])
        assert strip["color"] == [0.5, 0.5, 0.5]

    def test_set_text(self):
        proj = self._make_scene()
        add_strip(proj, "text", 1, 1, frame_end=50, text="Old")
        strip = set_strip_property(proj, 0, "text", "New Text")
        assert strip["text"] == "New Text"

    def test_set_font_size(self):
        proj = self._make_scene()
        add_strip(proj, "text", 1, 1, frame_end=50, text="Hello")
        strip = set_strip_property(proj, 0, "font_size", 96)
        assert strip["font_size"] == 96

    def test_set_font_size_invalid(self):
        proj = self._make_scene()
        add_strip(proj, "text", 1, 1, frame_end=50, text="Hello")
        with pytest.raises(ValueError, match="positive"):
            set_strip_property(proj, 0, "font_size", 0)

    def test_set_invalid_property(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        with pytest.raises(ValueError, match="Unknown strip property"):
            set_strip_property(proj, 0, "bogus", "value")

    def test_set_property_invalid_index(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        with pytest.raises(IndexError):
            set_strip_property(proj, 5, "opacity", 0.5)


# ── Transition Tests ────────────────────────────────────────────

class TestTransitions:
    def _make_scene_with_strips(self):
        proj = create_scene()
        add_strip(proj, "color", 1, 1, frame_end=100, name="StripA")
        add_strip(proj, "color", 2, 80, frame_end=200, name="StripB")
        return proj

    def test_add_cross_transition(self):
        proj = self._make_scene_with_strips()
        trans = add_transition(proj, "cross", 0, 1, duration_frames=20)
        assert trans["type"] == "transition"
        assert trans["transition_type"] == "cross"
        assert trans["bpy_type"] == "CROSS"
        assert trans["duration_frames"] == 20
        assert len(proj["vse"]["strips"]) == 3

    def test_add_gamma_cross_transition(self):
        proj = self._make_scene_with_strips()
        trans = add_transition(proj, "gamma_cross", 0, 1)
        assert trans["transition_type"] == "gamma_cross"
        assert trans["bpy_type"] == "GAMMA_CROSS"

    def test_add_wipe_transition(self):
        proj = self._make_scene_with_strips()
        trans = add_transition(proj, "wipe", 0, 1)
        assert trans["transition_type"] == "wipe"
        assert trans["bpy_type"] == "WIPE"

    def test_transition_references_strips(self):
        proj = self._make_scene_with_strips()
        strip_a_id = proj["vse"]["strips"][0]["id"]
        strip_b_id = proj["vse"]["strips"][1]["id"]
        trans = add_transition(proj, "cross", 0, 1)
        assert trans["strip_a"] == strip_a_id
        assert trans["strip_b"] == strip_b_id

    def test_transition_invalid_type(self):
        proj = self._make_scene_with_strips()
        with pytest.raises(ValueError, match="Unknown transition type"):
            add_transition(proj, "bogus", 0, 1)

    def test_transition_invalid_strip_a_index(self):
        proj = self._make_scene_with_strips()
        with pytest.raises(IndexError):
            add_transition(proj, "cross", 10, 1)

    def test_transition_invalid_strip_b_index(self):
        proj = self._make_scene_with_strips()
        with pytest.raises(IndexError):
            add_transition(proj, "cross", 0, 10)

    def test_transition_invalid_duration(self):
        proj = self._make_scene_with_strips()
        with pytest.raises(ValueError, match="Duration must be >= 1"):
            add_transition(proj, "cross", 0, 1, duration_frames=0)

    def test_transition_auto_channel(self):
        proj = self._make_scene_with_strips()
        trans = add_transition(proj, "cross", 0, 1)
        # Should be above the highest channel of the two strips
        max_channel = max(
            proj["vse"]["strips"][0]["channel"],
            proj["vse"]["strips"][1]["channel"],
        )
        assert trans["channel"] == max_channel + 1


# ── Effect Tests ────────────────────────────────────────────────

class TestEffects:
    def _make_scene_with_strip(self):
        proj = create_scene()
        add_strip(proj, "color", 1, 1, frame_end=100, name="Target")
        return proj

    def test_add_transform_effect(self):
        proj = self._make_scene_with_strip()
        effect = add_effect(proj, 0, "transform", params={"scale_x": 1.5})
        assert effect["type"] == "transform"
        assert effect["bpy_type"] == "TRANSFORM"
        assert effect["params"]["scale_x"] == 1.5
        assert len(proj["vse"]["strips"][0]["effects"]) == 1

    def test_add_speed_effect(self):
        proj = self._make_scene_with_strip()
        effect = add_effect(proj, 0, "speed")
        assert effect["type"] == "speed"
        assert effect["bpy_type"] == "SPEED"

    def test_add_glow_effect(self):
        proj = self._make_scene_with_strip()
        effect = add_effect(proj, 0, "glow", params={"threshold": 0.5})
        assert effect["type"] == "glow"
        assert effect["params"]["threshold"] == 0.5

    def test_add_gaussian_blur_effect(self):
        proj = self._make_scene_with_strip()
        effect = add_effect(proj, 0, "gaussian_blur", params={"size_x": 10})
        assert effect["type"] == "gaussian_blur"
        assert effect["bpy_type"] == "GAUSSIAN_BLUR"

    def test_add_color_balance_effect(self):
        proj = self._make_scene_with_strip()
        effect = add_effect(proj, 0, "color_balance")
        assert effect["type"] == "color_balance"
        assert effect["bpy_type"] == "COLOR_BALANCE"

    def test_add_multiple_effects(self):
        proj = self._make_scene_with_strip()
        add_effect(proj, 0, "transform")
        add_effect(proj, 0, "glow")
        assert len(proj["vse"]["strips"][0]["effects"]) == 2

    def test_add_effect_no_params(self):
        proj = self._make_scene_with_strip()
        effect = add_effect(proj, 0, "speed")
        assert effect["params"] == {}

    def test_add_effect_invalid_type(self):
        proj = self._make_scene_with_strip()
        with pytest.raises(ValueError, match="Unknown effect type"):
            add_effect(proj, 0, "nonexistent")

    def test_add_effect_invalid_index(self):
        proj = self._make_scene_with_strip()
        with pytest.raises(IndexError):
            add_effect(proj, 5, "transform")


# ── List Tests ──────────────────────────────────────────────────

class TestListOperations:
    def _make_scene(self):
        return create_scene()

    def test_list_strips_empty(self):
        proj = self._make_scene()
        result = list_strips(proj)
        assert result == []

    def test_list_strips(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50, name="A")
        add_strip(proj, "movie", 2, 10, source="/video.mp4", name="B")
        result = list_strips(proj)
        assert len(result) == 2
        assert result[0]["name"] == "A"
        assert result[0]["index"] == 0
        assert result[1]["name"] == "B"
        assert result[1]["index"] == 1

    def test_list_strips_includes_transitions(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=100, name="A")
        add_strip(proj, "color", 2, 80, frame_end=200, name="B")
        add_transition(proj, "cross", 0, 1)
        result = list_strips(proj)
        assert len(result) == 3
        assert result[2]["type"] == "transition"
        assert result[2]["transition_type"] == "cross"

    def test_list_strip_types(self):
        types = list_strip_types()
        assert len(types) == len(STRIP_TYPES)
        names = [t["name"] for t in types]
        assert "movie" in names
        assert "color" in names
        assert "text" in names
        assert "sound" in names
        assert "image" in names
        assert "adjustment" in names

    def test_list_strip_types_have_bpy_type(self):
        types = list_strip_types()
        for t in types:
            assert "bpy_type" in t
            assert t["bpy_type"]

    def test_list_transitions(self):
        transitions = list_transitions()
        assert len(transitions) == len(VSE_TRANSITIONS)
        names = [t["name"] for t in transitions]
        assert "cross" in names
        assert "gamma_cross" in names
        assert "wipe" in names

    def test_list_effects(self):
        effects = list_effects()
        assert len(effects) == len(VSE_EFFECTS)
        names = [e["name"] for e in effects]
        assert "transform" in names
        assert "speed" in names
        assert "glow" in names
        assert "gaussian_blur" in names
        assert "color_balance" in names


# ── BPY Script Generation Tests ─────────────────────────────────

class TestBpyGenVSE:
    def _make_scene(self):
        return create_scene()

    def test_gen_vse_empty(self):
        proj = self._make_scene()
        script = generate_full_script(proj, "/tmp/render.png")
        assert "VSE Strips" in script
        assert "(none)" in script

    def test_gen_vse_color_strip(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50, name="RedBG",
                  color=[1.0, 0.0, 0.0])
        script = generate_full_script(proj, "/tmp/render.png")
        assert "sequence_editor_create" in script
        assert "new_effect" in script
        assert "'COLOR'" in script
        assert "RedBG" in script
        assert ".color = (1.0, 0.0, 0.0)" in script

    def test_gen_vse_text_strip(self):
        proj = self._make_scene()
        add_strip(proj, "text", 2, 1, frame_end=100, name="Title",
                  text="Hello World", font_size=72)
        script = generate_full_script(proj, "/tmp/render.png")
        assert "'TEXT'" in script
        assert "Hello World" in script
        assert "font_size = 72" in script

    def test_gen_vse_movie_strip(self):
        proj = self._make_scene()
        add_strip(proj, "movie", 1, 1, source="/path/to/video.mp4", name="Clip")
        script = generate_full_script(proj, "/tmp/render.png")
        assert "new_movie" in script
        assert "/path/to/video.mp4" in script

    def test_gen_vse_sound_strip(self):
        proj = self._make_scene()
        add_strip(proj, "sound", 3, 1, source="/path/to/audio.wav", name="Audio")
        script = generate_full_script(proj, "/tmp/render.png")
        assert "new_sound" in script
        assert "/path/to/audio.wav" in script

    def test_gen_vse_image_strip(self):
        proj = self._make_scene()
        add_strip(proj, "image", 1, 1, source="/path/to/image.png", name="Photo")
        script = generate_full_script(proj, "/tmp/render.png")
        assert "new_image" in script
        assert "/path/to/image.png" in script

    def test_gen_vse_adjustment_strip(self):
        proj = self._make_scene()
        add_strip(proj, "adjustment", 5, 1, frame_end=200, name="Adj")
        script = generate_full_script(proj, "/tmp/render.png")
        assert "'ADJUSTMENT'" in script

    def test_gen_vse_blend_type(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50, name="Overlay")
        set_strip_property(proj, 0, "blend_type", "ADD")
        script = generate_full_script(proj, "/tmp/render.png")
        assert "blend_type = 'ADD'" in script

    def test_gen_vse_opacity(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50, name="Faded")
        set_strip_property(proj, 0, "opacity", 0.5)
        script = generate_full_script(proj, "/tmp/render.png")
        assert "blend_alpha = 0.5" in script

    def test_gen_vse_mute(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50, name="Muted")
        set_strip_property(proj, 0, "mute", True)
        script = generate_full_script(proj, "/tmp/render.png")
        assert "mute = True" in script

    def test_gen_vse_transition(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=100, name="A")
        add_strip(proj, "color", 2, 80, frame_end=200, name="B")
        add_transition(proj, "cross", 0, 1, duration_frames=20)
        script = generate_full_script(proj, "/tmp/render.png")
        assert "'CROSS'" in script

    def test_gen_vse_effect(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=100, name="Base")
        add_effect(proj, 0, "glow", params={"threshold": 0.8})
        script = generate_full_script(proj, "/tmp/render.png")
        assert "'GLOW'" in script
        assert "threshold = 0.8" in script

    def test_gen_vse_is_valid_python(self):
        """Verify that generated VSE code is syntactically valid Python."""
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50, name="BG",
                  color=[0.2, 0.3, 0.4])
        add_strip(proj, "text", 2, 10, frame_end=90, name="Title",
                  text="Test", font_size=64)
        add_strip(proj, "movie", 3, 1, source="/video.mp4", name="Clip")
        add_effect(proj, 0, "gaussian_blur", params={"size_x": 5})
        script = generate_full_script(proj, "/tmp/render.png")
        # Should parse as valid Python (no SyntaxError)
        compile(script, "<test>", "exec")

    def test_gen_vse_script_has_import_bpy(self):
        proj = self._make_scene()
        add_strip(proj, "color", 1, 1, frame_end=50)
        script = generate_full_script(proj, "/tmp/render.png")
        assert "import bpy" in script
