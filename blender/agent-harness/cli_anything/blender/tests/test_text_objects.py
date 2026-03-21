"""Unit tests for Blender CLI text object support.

Tests cover text object creation, bpy script generation, default values,
custom parameters, and animation of text objects.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cli_anything.blender.core.scene import create_scene
from cli_anything.blender.core.objects import (
    add_text_object, list_objects, get_object, TEXT_DEFAULTS,
)
from cli_anything.blender.core.animation import add_keyframe
from cli_anything.blender.utils.bpy_gen import generate_full_script


class TestAddTextObject:
    """Tests for add_text_object() in core/objects.py."""

    def _make_scene(self):
        return create_scene()

    def test_add_text_object_basic(self):
        """Adding a text object returns the correct structure."""
        proj = self._make_scene()
        obj = add_text_object(proj, body="Hello World")
        assert obj["type"] == "FONT"
        assert obj["mesh_type"] == "text"
        assert obj["text_params"]["body"] == "Hello World"
        assert len(proj["objects"]) == 1

    def test_add_text_object_defaults(self):
        """Default values match TEXT_DEFAULTS."""
        proj = self._make_scene()
        obj = add_text_object(proj)
        assert obj["text_params"]["body"] == TEXT_DEFAULTS["body"]
        assert obj["text_params"]["size"] == TEXT_DEFAULTS["font_size"]
        assert obj["text_params"]["extrude"] == TEXT_DEFAULTS["extrude"]
        assert obj["text_params"]["align_x"] == TEXT_DEFAULTS["align_x"]

    def test_add_text_object_default_transforms(self):
        """Default location, rotation, and scale."""
        proj = self._make_scene()
        obj = add_text_object(proj)
        assert obj["location"] == [0.0, 0.0, 0.0]
        assert obj["rotation"] == [0.0, 0.0, 0.0]
        assert obj["scale"] == [1.0, 1.0, 1.0]

    def test_add_text_object_custom_name(self):
        """Custom name is preserved."""
        proj = self._make_scene()
        obj = add_text_object(proj, body="Title", name="MyTitle")
        assert obj["name"] == "MyTitle"

    def test_add_text_object_auto_name(self):
        """Auto-generated name defaults to 'Text'."""
        proj = self._make_scene()
        obj = add_text_object(proj)
        assert obj["name"] == "Text"

    def test_add_text_object_unique_names(self):
        """Multiple text objects get unique names."""
        proj = self._make_scene()
        obj1 = add_text_object(proj)
        obj2 = add_text_object(proj)
        assert obj1["name"] != obj2["name"]
        assert obj1["name"] == "Text"
        assert obj2["name"] == "Text.001"

    def test_add_text_object_unique_ids(self):
        """Each text object gets a unique id."""
        proj = self._make_scene()
        obj1 = add_text_object(proj)
        obj2 = add_text_object(proj)
        assert obj1["id"] != obj2["id"]

    def test_add_text_object_custom_location(self):
        """Custom location is preserved."""
        proj = self._make_scene()
        obj = add_text_object(proj, location=[1.0, 2.0, 3.0])
        assert obj["location"] == [1.0, 2.0, 3.0]

    def test_add_text_object_custom_font_size(self):
        """Custom font_size maps to text_params.size."""
        proj = self._make_scene()
        obj = add_text_object(proj, font_size=2.5)
        assert obj["text_params"]["size"] == 2.5

    def test_add_text_object_custom_extrude(self):
        """Custom extrude value is stored."""
        proj = self._make_scene()
        obj = add_text_object(proj, extrude=0.3)
        assert obj["text_params"]["extrude"] == 0.3

    def test_add_text_object_align_left(self):
        """Alignment LEFT is valid."""
        proj = self._make_scene()
        obj = add_text_object(proj, align_x="LEFT")
        assert obj["text_params"]["align_x"] == "LEFT"

    def test_add_text_object_align_right(self):
        """Alignment RIGHT is valid."""
        proj = self._make_scene()
        obj = add_text_object(proj, align_x="RIGHT")
        assert obj["text_params"]["align_x"] == "RIGHT"

    def test_add_text_object_invalid_align(self):
        """Invalid alignment raises ValueError."""
        proj = self._make_scene()
        with pytest.raises(ValueError, match="Invalid align_x"):
            add_text_object(proj, align_x="JUSTIFY")

    def test_add_text_object_invalid_location(self):
        """Location with wrong number of components raises ValueError."""
        proj = self._make_scene()
        with pytest.raises(ValueError, match="3 components"):
            add_text_object(proj, location=[1.0, 2.0])

    def test_add_text_object_added_to_collection(self):
        """Text object is added to the default collection."""
        proj = self._make_scene()
        obj = add_text_object(proj)
        assert obj["id"] in proj["collections"][0]["objects"]

    def test_add_text_object_has_standard_fields(self):
        """Text object has all the standard object fields."""
        proj = self._make_scene()
        obj = add_text_object(proj)
        for field in ("id", "name", "type", "mesh_type", "location",
                       "rotation", "scale", "visible", "material",
                       "modifiers", "keyframes", "parent"):
            assert field in obj, f"Missing field: {field}"

    def test_add_text_object_appears_in_list(self):
        """Text object appears in list_objects."""
        proj = self._make_scene()
        add_text_object(proj, body="Listed")
        objects = list_objects(proj)
        assert len(objects) == 1
        assert objects[0]["type"] == "FONT"
        assert objects[0]["mesh_type"] == "text"

    def test_add_text_object_case_insensitive_align(self):
        """Alignment string is case-insensitive."""
        proj = self._make_scene()
        obj = add_text_object(proj, align_x="left")
        assert obj["text_params"]["align_x"] == "LEFT"


class TestTextBpyGeneration:
    """Tests for text object bpy script generation."""

    def _make_scene_with_text(self, **kwargs):
        proj = create_scene()
        add_text_object(proj, **kwargs)
        return proj

    def test_text_in_bpy_script(self):
        """Text object generates bpy.ops.object.text_add."""
        proj = self._make_scene_with_text(body="Hello")
        script = generate_full_script(proj, "/tmp/render.png")
        assert "bpy.ops.object.text_add" in script

    def test_text_body_in_script(self):
        """Text body content appears in script."""
        proj = self._make_scene_with_text(body="Hello World")
        script = generate_full_script(proj, "/tmp/render.png")
        assert "obj.data.body = 'Hello World'" in script

    def test_text_size_in_script(self):
        """Font size appears in script."""
        proj = self._make_scene_with_text(font_size=3.0)
        script = generate_full_script(proj, "/tmp/render.png")
        assert "obj.data.size = 3.0" in script

    def test_text_extrude_in_script(self):
        """Extrude value appears in script."""
        proj = self._make_scene_with_text(extrude=0.5)
        script = generate_full_script(proj, "/tmp/render.png")
        assert "obj.data.extrude = 0.5" in script

    def test_text_align_in_script(self):
        """Alignment value appears in script."""
        proj = self._make_scene_with_text(align_x="RIGHT")
        script = generate_full_script(proj, "/tmp/render.png")
        assert "obj.data.align_x = 'RIGHT'" in script

    def test_text_name_in_script(self):
        """Object name is set in script."""
        proj = self._make_scene_with_text(name="Title", body="Hello")
        script = generate_full_script(proj, "/tmp/render.png")
        assert "obj.name = 'Title'" in script

    def test_text_location_in_script(self):
        """Location is passed to text_add."""
        proj = self._make_scene_with_text(location=[1.0, 2.0, 3.0])
        script = generate_full_script(proj, "/tmp/render.png")
        assert "text_add(location=(1.0, 2.0, 3.0))" in script

    def test_text_default_values_in_script(self):
        """Default size, extrude, and alignment appear in script."""
        proj = self._make_scene_with_text()
        script = generate_full_script(proj, "/tmp/render.png")
        assert "obj.data.size = 1.0" in script
        assert "obj.data.extrude = 0.0" in script
        assert "obj.data.align_x = 'CENTER'" in script

    def test_multiple_text_objects_in_script(self):
        """Multiple text objects each generate their own bpy code."""
        proj = create_scene()
        add_text_object(proj, body="First", name="Text1")
        add_text_object(proj, body="Second", name="Text2")
        script = generate_full_script(proj, "/tmp/render.png")
        assert "obj.data.body = 'First'" in script
        assert "obj.data.body = 'Second'" in script
        assert script.count("bpy.ops.object.text_add") == 2


class TestTextAnimation:
    """Tests for animating text objects with keyframes."""

    def _make_scene_with_text(self):
        proj = create_scene()
        add_text_object(proj, body="Animated", name="AnimText")
        return proj

    def test_text_object_keyframe_location(self):
        """Text object can have location keyframes."""
        proj = self._make_scene_with_text()
        kf = add_keyframe(proj, 0, 1, "location", [0, 0, 0])
        assert kf["frame"] == 1
        assert kf["property"] == "location"
        assert kf["value"] == [0.0, 0.0, 0.0]
        assert len(proj["objects"][0]["keyframes"]) == 1

    def test_text_object_keyframe_multiple(self):
        """Text object supports multiple keyframes."""
        proj = self._make_scene_with_text()
        add_keyframe(proj, 0, 1, "location", [0, 0, 0])
        add_keyframe(proj, 0, 30, "location", [5, 5, 0])
        assert len(proj["objects"][0]["keyframes"]) == 2

    def test_text_object_keyframe_rotation(self):
        """Text object can have rotation keyframes."""
        proj = self._make_scene_with_text()
        kf = add_keyframe(proj, 0, 10, "rotation", [0, 0, 90])
        assert kf["property"] == "rotation"

    def test_text_object_keyframe_scale(self):
        """Text object can have scale keyframes."""
        proj = self._make_scene_with_text()
        kf = add_keyframe(proj, 0, 20, "scale", [2, 2, 2])
        assert kf["value"] == [2.0, 2.0, 2.0]

    def test_text_object_keyframes_in_bpy_script(self):
        """Text object keyframes appear in generated bpy script."""
        proj = self._make_scene_with_text()
        add_keyframe(proj, 0, 1, "location", [0, 0, 0])
        add_keyframe(proj, 0, 30, "location", [5, 5, 0])
        script = generate_full_script(proj, "/tmp/render.png")
        assert "keyframe_insert" in script
        assert "AnimText" in script
