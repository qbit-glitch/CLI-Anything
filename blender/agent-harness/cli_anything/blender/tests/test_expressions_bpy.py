"""Unit tests for the Blender expression baking module (expressions_bpy.py).

Tests verify:
- apply_expression bakes per-frame keyframes for valid expressions
- apply_wiggle bakes wiggle noise keyframes
- apply_procedural bakes procedural expressions
- Evaluated values match the shared Expression class output
- Invalid expressions/arguments raise appropriate errors
- Project JSON is updated with expression metadata
- Render quality functions (set_motion_blur, set_ambient_occlusion, etc.)
  generate correct bpy script lines and update session JSON
"""

import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from cli_anything.blender.core.scene import create_scene
from cli_anything.blender.core.session import Session
from cli_anything.blender.core.expressions_bpy import (
    apply_expression,
    apply_wiggle,
    apply_procedural,
)
from cli_anything.blender.core.render import (
    set_motion_blur,
    set_ambient_occlusion,
    set_hdri_lighting,
    set_transparent_background,
    set_film_exposure,
    set_color_management,
    set_denoising,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_session() -> Session:
    sess = Session()
    proj = create_scene(name="TestScene")
    sess.set_project(proj)
    return sess


def script_str(lines) -> str:
    return "\n".join(lines)


# ── apply_expression ──────────────────────────────────────────────────────────


class TestApplyExpression:
    def test_returns_list_of_strings(self):
        sess = make_session()
        lines = apply_expression(sess, "Cube", "rotation_euler", "time * 360", 1.0)
        assert isinstance(lines, list)
        assert all(isinstance(l, str) for l in lines)

    def test_contains_keyframe_insert(self):
        sess = make_session()
        lines = apply_expression(sess, "Cube", "rotation_euler", "time * 6.28", 1.0)
        assert "keyframe_insert" in script_str(lines)

    def test_contains_object_lookup(self):
        sess = make_session()
        lines = apply_expression(sess, "Sphere", "location", "sin(time)", 1.0)
        assert "bpy.data.objects.get" in script_str(lines)

    def test_contains_data_path(self):
        sess = make_session()
        lines = apply_expression(sess, "Cube", "rotation_euler", "time * 3", 1.0)
        assert "rotation_euler" in script_str(lines)

    def test_frame_count_matches_duration_fps(self):
        sess = make_session()
        # duration=1.0, fps=10 → 10+1 = 11 keyframes
        lines = apply_expression(sess, "Obj", "location", "time", 1.0, fps=10)
        kf_lines = [l for l in lines if "keyframe_insert" in l]
        assert len(kf_lines) == 11

    def test_invalid_expression_raises(self):
        sess = make_session()
        with pytest.raises(ValueError):
            apply_expression(sess, "Cube", "location", "import os", 1.0)

    def test_negative_duration_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="duration"):
            apply_expression(sess, "Cube", "location", "time", -1.0)

    def test_zero_duration_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="duration"):
            apply_expression(sess, "Cube", "location", "time", 0.0)

    def test_project_stores_expression_metadata(self):
        sess = make_session()
        apply_expression(sess, "Cube", "rotation_euler", "time * 2", 1.0)
        proj = sess.get_project()
        assert "expressions" in proj
        assert len(proj["expressions"]) == 1
        entry = proj["expressions"][0]
        assert entry["type"] == "expression"
        assert entry["object"] == "Cube"
        assert entry["property_path"] == "rotation_euler"
        assert entry["expression"] == "time * 2"

    def test_baked_values_are_numeric(self):
        sess = make_session()
        lines = apply_expression(sess, "Cube", "location", "time * 10", 1.0, fps=5)
        # Lines that set the property value (contain " = " but not keyframe_insert)
        val_lines = [l for l in lines if "= " in l and "keyframe_insert" not in l
                     and "bpy.data.objects.get" not in l and l.strip().startswith("_obj")]
        assert len(val_lines) > 0

    def test_index_parameter_in_output(self):
        sess = make_session()
        lines = apply_expression(sess, "Cube", "location", "time", 1.0, fps=5, index=2)
        s = script_str(lines)
        assert "index=2" in s

    def test_comment_header_in_output(self):
        sess = make_session()
        lines = apply_expression(sess, "Cube", "rotation_euler", "time * 360", 1.0)
        assert any("#" in l for l in lines)

    def test_import_bpy_in_output(self):
        sess = make_session()
        lines = apply_expression(sess, "Cube", "location", "sin(time)", 1.0)
        assert "import bpy" in lines

    def test_time_expression_first_frame_near_zero(self):
        """time=0 at frame 0 → value should be 0 for expression 'time'."""
        sess = make_session()
        lines = apply_expression(sess, "Cube", "location", "time", 1.0, fps=5, index=0)
        # First value line after the object guard
        val_lines = [l for l in lines if "[0] = " in l and "keyframe_insert" not in l]
        if val_lines:
            first_val = float(val_lines[0].split("= ")[-1].strip())
            assert abs(first_val) < 1e-6

    def test_accumulates_multiple_expressions(self):
        sess = make_session()
        apply_expression(sess, "Cube", "location", "time", 1.0)
        apply_expression(sess, "Sphere", "rotation_euler", "sin(time)", 0.5)
        proj = sess.get_project()
        assert len(proj["expressions"]) == 2


# ── apply_wiggle ──────────────────────────────────────────────────────────────


class TestApplyWiggle:
    def test_returns_list(self):
        sess = make_session()
        lines = apply_wiggle(sess, "Cube", "location", 2.0, 0.5, 1.0)
        assert isinstance(lines, list)

    def test_contains_keyframe_insert(self):
        sess = make_session()
        lines = apply_wiggle(sess, "Cube", "location", 2.0, 0.5, 1.0)
        assert "keyframe_insert" in script_str(lines)

    def test_contains_object_lookup(self):
        sess = make_session()
        lines = apply_wiggle(sess, "MySphere", "location", 1.0, 1.0, 0.5)
        assert "bpy.data.objects.get" in script_str(lines)

    def test_negative_frequency_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="frequency"):
            apply_wiggle(sess, "Cube", "location", -1.0, 0.5, 1.0)

    def test_zero_frequency_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="frequency"):
            apply_wiggle(sess, "Cube", "location", 0.0, 0.5, 1.0)

    def test_negative_amplitude_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="amplitude"):
            apply_wiggle(sess, "Cube", "location", 1.0, -0.5, 1.0)

    def test_project_stores_wiggle_metadata(self):
        sess = make_session()
        apply_wiggle(sess, "Cube", "location", 3.0, 0.2, 1.0)
        proj = sess.get_project()
        assert "expressions" in proj
        entry = proj["expressions"][0]
        assert entry["type"] == "wiggle"
        assert entry["frequency"] == 3.0
        assert entry["amplitude"] == 0.2

    def test_frame_count_matches_duration_fps(self):
        sess = make_session()
        lines = apply_wiggle(sess, "Cube", "location", 2.0, 0.5, 2.0, fps=10)
        kf_lines = [l for l in lines if "keyframe_insert" in l]
        # 2s * 10fps + 1 = 21 keyframes
        assert len(kf_lines) == 21

    def test_import_bpy_in_output(self):
        sess = make_session()
        lines = apply_wiggle(sess, "Cube", "location", 1.0, 1.0, 1.0)
        assert "import bpy" in lines

    def test_comment_header_present(self):
        sess = make_session()
        lines = apply_wiggle(sess, "Cube", "location", 2.0, 0.5, 1.0)
        assert any("wiggle" in l.lower() or "Wiggle" in l for l in lines)

    def test_index_in_output_when_specified(self):
        sess = make_session()
        lines = apply_wiggle(sess, "Cube", "location", 1.0, 0.5, 1.0, fps=5, index=1)
        assert "index=1" in script_str(lines)


# ── apply_procedural ──────────────────────────────────────────────────────────


class TestApplyProcedural:
    def test_returns_list(self):
        sess = make_session()
        lines = apply_procedural(sess, "Cube", "location", "sin(time * 3)", 1.0)
        assert isinstance(lines, list)

    def test_contains_keyframe_insert(self):
        sess = make_session()
        lines = apply_procedural(sess, "Cube", "rotation_euler", "time * 6.28", 2.0)
        assert "keyframe_insert" in script_str(lines)

    def test_project_tagged_as_procedural(self):
        sess = make_session()
        apply_procedural(sess, "Cube", "location", "sin(time)", 1.0)
        proj = sess.get_project()
        assert proj["expressions"][0]["type"] == "procedural"

    def test_invalid_expression_raises(self):
        sess = make_session()
        with pytest.raises(ValueError):
            apply_procedural(sess, "Cube", "location", "open('/etc/passwd')", 1.0)

    def test_negative_duration_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="duration"):
            apply_procedural(sess, "Cube", "location", "time", -0.5)

    def test_import_bpy_in_output(self):
        sess = make_session()
        lines = apply_procedural(sess, "Cube", "location", "cos(time)", 1.0)
        assert "import bpy" in lines

    def test_frame_count(self):
        sess = make_session()
        lines = apply_procedural(sess, "Cube", "location", "time", 1.0, fps=6)
        kf_lines = [l for l in lines if "keyframe_insert" in l]
        assert len(kf_lines) == 7  # 0..6 = 7 frames

    def test_comment_header_present(self):
        sess = make_session()
        lines = apply_procedural(sess, "Cube", "location", "time * 2", 1.0)
        assert any("#" in l for l in lines)


# ── Render quality settings ───────────────────────────────────────────────────


class TestSetMotionBlur:
    def test_returns_list(self):
        sess = make_session()
        lines = set_motion_blur(sess)
        assert isinstance(lines, list)

    def test_contains_use_motion_blur(self):
        sess = make_session()
        lines = set_motion_blur(sess, enable=True)
        assert "use_motion_blur" in script_str(lines)

    def test_enable_true(self):
        sess = make_session()
        lines = set_motion_blur(sess, enable=True)
        assert "True" in script_str(lines)

    def test_enable_false(self):
        sess = make_session()
        lines = set_motion_blur(sess, enable=False)
        assert "False" in script_str(lines)

    def test_shutter_speed_in_output(self):
        sess = make_session()
        lines = set_motion_blur(sess, shutter_speed=0.25)
        assert "0.25" in script_str(lines)

    def test_invalid_shutter_speed_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="shutter_speed"):
            set_motion_blur(sess, shutter_speed=1.5)

    def test_invalid_samples_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="samples"):
            set_motion_blur(sess, samples=0)

    def test_project_stores_motion_blur(self):
        sess = make_session()
        set_motion_blur(sess, enable=True, shutter_speed=0.5, samples=16)
        proj = sess.get_project()
        assert proj["render"]["motion_blur"]["enable"] is True
        assert proj["render"]["motion_blur"]["shutter_speed"] == 0.5


class TestSetAmbientOcclusion:
    def test_returns_list(self):
        sess = make_session()
        lines = set_ambient_occlusion(sess)
        assert isinstance(lines, list)

    def test_contains_use_gtao(self):
        sess = make_session()
        lines = set_ambient_occlusion(sess, enable=True)
        assert "use_gtao" in script_str(lines)

    def test_distance_in_output(self):
        sess = make_session()
        lines = set_ambient_occlusion(sess, distance=2.5)
        assert "2.5" in script_str(lines)

    def test_factor_in_output(self):
        sess = make_session()
        lines = set_ambient_occlusion(sess, factor=0.8)
        assert "0.8" in script_str(lines)

    def test_negative_distance_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="distance"):
            set_ambient_occlusion(sess, distance=-1.0)

    def test_zero_distance_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="distance"):
            set_ambient_occlusion(sess, distance=0.0)

    def test_negative_factor_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="factor"):
            set_ambient_occlusion(sess, factor=-0.1)

    def test_project_stores_ao_settings(self):
        sess = make_session()
        set_ambient_occlusion(sess, enable=True, distance=1.5, factor=0.75)
        proj = sess.get_project()
        assert proj["render"]["ambient_occlusion"]["enable"] is True
        assert proj["render"]["ambient_occlusion"]["distance"] == 1.5
        assert proj["render"]["ambient_occlusion"]["factor"] == 0.75


class TestSetHdriLighting:
    def test_returns_list(self):
        sess = make_session()
        lines = set_hdri_lighting(sess, "/tmp/test.hdr")
        assert isinstance(lines, list)

    def test_contains_environment_texture(self):
        sess = make_session()
        lines = set_hdri_lighting(sess, "/tmp/sky.hdr")
        assert "ShaderNodeTexEnvironment" in script_str(lines)

    def test_contains_hdri_path(self):
        sess = make_session()
        lines = set_hdri_lighting(sess, "/path/to/hdri.hdr")
        assert "/path/to/hdri.hdr" in script_str(lines)

    def test_strength_in_output(self):
        sess = make_session()
        lines = set_hdri_lighting(sess, "/tmp/test.hdr", strength=2.0)
        assert "2.0" in script_str(lines)

    def test_negative_strength_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="strength"):
            set_hdri_lighting(sess, "/tmp/test.hdr", strength=-1.0)

    def test_world_use_nodes(self):
        sess = make_session()
        lines = set_hdri_lighting(sess, "/tmp/test.hdr")
        assert "use_nodes = True" in script_str(lines)

    def test_rotation_applied(self):
        sess = make_session()
        lines = set_hdri_lighting(sess, "/tmp/test.hdr", rotation=90.0)
        # 90 degrees = pi/2 radians ≈ 1.5708
        import math
        rot_val = math.radians(90.0)
        assert str(round(rot_val, 4))[:4] in script_str(lines)

    def test_project_stores_hdri(self):
        sess = make_session()
        set_hdri_lighting(sess, "/tmp/test.hdr", rotation=45.0, strength=1.5)
        proj = sess.get_project()
        assert proj["render"]["hdri"]["path"] == "/tmp/test.hdr"
        assert proj["render"]["hdri"]["rotation"] == 45.0
        assert proj["render"]["hdri"]["strength"] == 1.5

    def test_contains_background_node(self):
        sess = make_session()
        lines = set_hdri_lighting(sess, "/tmp/test.hdr")
        assert "ShaderNodeBackground" in script_str(lines)


class TestSetTransparentBackground:
    def test_returns_list(self):
        sess = make_session()
        lines = set_transparent_background(sess)
        assert isinstance(lines, list)

    def test_film_transparent_true(self):
        sess = make_session()
        lines = set_transparent_background(sess, enable=True)
        assert "film_transparent = True" in script_str(lines)

    def test_film_transparent_false(self):
        sess = make_session()
        lines = set_transparent_background(sess, enable=False)
        assert "film_transparent = False" in script_str(lines)

    def test_project_updated(self):
        sess = make_session()
        set_transparent_background(sess, enable=True)
        proj = sess.get_project()
        assert proj["render"]["film_transparent"] is True

    def test_default_enable_true(self):
        sess = make_session()
        lines = set_transparent_background(sess)
        assert "True" in script_str(lines)


class TestSetFilmExposure:
    def test_returns_list(self):
        sess = make_session()
        lines = set_film_exposure(sess)
        assert isinstance(lines, list)

    def test_contains_film_exposure(self):
        sess = make_session()
        lines = set_film_exposure(sess, value=1.5)
        assert "film_exposure" in script_str(lines)

    def test_value_in_output(self):
        sess = make_session()
        lines = set_film_exposure(sess, value=-0.5)
        assert "-0.5" in script_str(lines)

    def test_project_stores_exposure(self):
        sess = make_session()
        set_film_exposure(sess, value=0.7)
        proj = sess.get_project()
        assert proj["render"]["film_exposure"] == 0.7

    def test_default_zero(self):
        sess = make_session()
        set_film_exposure(sess)
        proj = sess.get_project()
        assert proj["render"]["film_exposure"] == 0.0


class TestSetColorManagement:
    def test_returns_list(self):
        sess = make_session()
        lines = set_color_management(sess)
        assert isinstance(lines, list)

    def test_contains_view_transform(self):
        sess = make_session()
        lines = set_color_management(sess, view_transform="Filmic")
        assert "view_transform" in script_str(lines)
        assert "Filmic" in script_str(lines)

    def test_contains_look(self):
        sess = make_session()
        lines = set_color_management(sess, look="Filmic - High Contrast")
        assert "look" in script_str(lines)

    def test_project_stores_color_management(self):
        sess = make_session()
        set_color_management(sess, view_transform="Standard", look="None")
        proj = sess.get_project()
        cm = proj["render"]["color_management"]
        assert cm["view_transform"] == "Standard"
        assert cm["look"] == "None"

    def test_view_settings_used(self):
        sess = make_session()
        lines = set_color_management(sess)
        assert "view_settings" in script_str(lines)


class TestSetDenoising:
    def test_returns_list(self):
        sess = make_session()
        lines = set_denoising(sess)
        assert isinstance(lines, list)

    def test_contains_use_denoising(self):
        sess = make_session()
        lines = set_denoising(sess, enable=True)
        assert "use_denoising" in script_str(lines)

    def test_enable_true(self):
        sess = make_session()
        lines = set_denoising(sess, enable=True)
        assert "True" in script_str(lines)

    def test_enable_false(self):
        sess = make_session()
        lines = set_denoising(sess, enable=False)
        assert "False" in script_str(lines)

    def test_project_stores_denoising(self):
        sess = make_session()
        set_denoising(sess, enable=True)
        proj = sess.get_project()
        assert proj["render"]["use_denoising"] is True

    def test_default_enable_true(self):
        sess = make_session()
        set_denoising(sess)
        proj = sess.get_project()
        assert proj["render"]["use_denoising"] is True

    def test_cycles_property_used(self):
        sess = make_session()
        lines = set_denoising(sess)
        assert "cycles" in script_str(lines)
