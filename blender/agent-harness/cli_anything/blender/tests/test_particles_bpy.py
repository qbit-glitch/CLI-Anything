"""Tests for blender/core/particles_bpy.py

Verifies that each function generates bpy script lines containing the
correct Blender API calls.  A lightweight MockSession is used so the
tests run without a live Blender instance.
"""

import sys
import os
import unittest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", ".."),
)

from cli_anything.blender.core.particles_bpy import (
    emit_from_object,
    emit_from_point,
    emit_from_text,
    add_force_field,
    preset_confetti,
    preset_sparks,
    preset_disintegrate,
    preset_data_stream,
)


# ── Mock Session ─────────────────────────────────────────────────────────────


class MockSession:
    def __init__(self):
        self._project = {}

    def get_project(self):
        return self._project


# ── Helpers ──────────────────────────────────────────────────────────────────


def lines_contain(lines, *fragments):
    joined = "\n".join(lines)
    return all(frag in joined for frag in fragments)


# ── TestEmitFromObject ───────────────────────────────────────────────────────


class TestEmitFromObject(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = emit_from_object(self.sess, "Cube")
        self.assertIsInstance(lines, list)
        self.assertGreater(len(lines), 0)

    def test_particle_system_modifier(self):
        lines = emit_from_object(self.sess, "Cube")
        self.assertTrue(lines_contain(lines, "PARTICLE_SYSTEM"))

    def test_object_lookup(self):
        lines = emit_from_object(self.sess, "MySphere")
        self.assertTrue(lines_contain(lines, "bpy.data.objects.get('MySphere')"))

    def test_active_object_set(self):
        lines = emit_from_object(self.sess, "Cube")
        self.assertTrue(lines_contain(lines, "view_layer.objects.active = emitter"))

    def test_particle_settings_object(self):
        lines = emit_from_object(self.sess, "Cube")
        self.assertTrue(lines_contain(lines, "ps.settings"))

    def test_default_count_applied(self):
        lines = emit_from_object(self.sess, "Cube")
        self.assertTrue(lines_contain(lines, "pset.count = 1000"))

    def test_custom_config_count(self):
        lines = emit_from_object(self.sess, "Cube", {"count": 500})
        self.assertTrue(lines_contain(lines, "pset.count = 500"))

    def test_custom_config_lifetime(self):
        lines = emit_from_object(self.sess, "Cube", {"lifetime": 30})
        self.assertTrue(lines_contain(lines, "pset.lifetime = 30"))

    def test_emit_from_setting(self):
        lines = emit_from_object(self.sess, "Cube", {"emit_from": "VERT"})
        self.assertTrue(lines_contain(lines, "pset.emit_from = 'VERT'"))

    def test_import_bpy(self):
        lines = emit_from_object(self.sess, "Cube")
        self.assertTrue(lines_contain(lines, "import bpy"))


# ── TestEmitFromPoint ────────────────────────────────────────────────────────


class TestEmitFromPoint(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = emit_from_point(self.sess, [0.0, 0.0, 0.0])
        self.assertIsInstance(lines, list)

    def test_plane_created_at_position(self):
        lines = emit_from_point(self.sess, [1.0, 2.0, 3.0])
        self.assertTrue(lines_contain(lines, "primitive_plane_add"))
        self.assertTrue(lines_contain(lines, "(1.0, 2.0, 3.0)"))

    def test_particle_system_added(self):
        lines = emit_from_point(self.sess, [0.0, 0.0, 0.0])
        self.assertTrue(lines_contain(lines, "PARTICLE_SYSTEM"))

    def test_pset_configured(self):
        lines = emit_from_point(self.sess, [0.0, 0.0, 0.0], {"count": 200})
        self.assertTrue(lines_contain(lines, "pset.count = 200"))

    def test_invalid_position_length(self):
        with self.assertRaises(ValueError):
            emit_from_point(self.sess, [0.0, 0.0])

    def test_emitter_named(self):
        lines = emit_from_point(self.sess, [0.0, 0.0, 0.0])
        self.assertTrue(lines_contain(lines, "emitter.name = 'PointEmitter'"))


# ── TestEmitFromText ─────────────────────────────────────────────────────────


class TestEmitFromText(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = emit_from_text(self.sess, "MyText")
        self.assertIsInstance(lines, list)

    def test_text_object_lookup(self):
        lines = emit_from_text(self.sess, "MyText")
        self.assertTrue(lines_contain(lines, "bpy.data.objects.get('MyText')"))

    def test_convert_to_mesh(self):
        lines = emit_from_text(self.sess, "MyText")
        self.assertTrue(lines_contain(lines, "bpy.ops.object.convert(target='MESH')"))

    def test_particle_system_after_convert(self):
        lines = emit_from_text(self.sess, "MyText")
        self.assertTrue(lines_contain(lines, "PARTICLE_SYSTEM"))

    def test_select_all_deselect(self):
        lines = emit_from_text(self.sess, "MyText")
        self.assertTrue(lines_contain(lines, "select_all(action='DESELECT')"))

    def test_pset_count(self):
        lines = emit_from_text(self.sess, "MyText", {"count": 750})
        self.assertTrue(lines_contain(lines, "pset.count = 750"))


# ── TestAddForceField ────────────────────────────────────────────────────────


class TestAddForceField(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = add_force_field(self.sess, "TURBULENCE", 3.0)
        self.assertIsInstance(lines, list)

    def test_effector_add(self):
        lines = add_force_field(self.sess, "TURBULENCE", 3.0)
        self.assertTrue(lines_contain(lines, "effector_add"))

    def test_turbulence_type(self):
        lines = add_force_field(self.sess, "TURBULENCE", 2.0)
        self.assertTrue(lines_contain(lines, "type='TURBULENCE'"))

    def test_wind_type(self):
        lines = add_force_field(self.sess, "WIND", 1.0)
        self.assertTrue(lines_contain(lines, "type='WIND'"))

    def test_vortex_type(self):
        lines = add_force_field(self.sess, "VORTEX", 5.0)
        self.assertTrue(lines_contain(lines, "type='VORTEX'"))

    def test_force_type(self):
        lines = add_force_field(self.sess, "FORCE", 1.5)
        self.assertTrue(lines_contain(lines, "type='FORCE'"))

    def test_strength_set(self):
        lines = add_force_field(self.sess, "WIND", 7.5)
        self.assertTrue(lines_contain(lines, "ff_obj.field.strength = 7.5"))

    def test_position_applied(self):
        lines = add_force_field(self.sess, "FORCE", 1.0, position=[2.0, 3.0, 4.0])
        self.assertTrue(lines_contain(lines, "(2.0, 3.0, 4.0)"))

    def test_name_applied(self):
        lines = add_force_field(self.sess, "WIND", 1.0, name="MyWind")
        self.assertTrue(lines_contain(lines, "ff_obj.name = 'MyWind'"))

    def test_turbulence_noise_set(self):
        lines = add_force_field(self.sess, "TURBULENCE", 1.0)
        self.assertTrue(lines_contain(lines, "ff_obj.field.noise"))

    def test_invalid_force_type(self):
        with self.assertRaises(ValueError):
            add_force_field(self.sess, "GRAVITY", 1.0)

    def test_case_insensitive(self):
        lines = add_force_field(self.sess, "wind", 1.0)
        self.assertTrue(lines_contain(lines, "type='WIND'"))

    def test_invalid_position_length(self):
        with self.assertRaises(ValueError):
            add_force_field(self.sess, "FORCE", 1.0, position=[0.0, 0.0])


# ── TestPresetConfetti ───────────────────────────────────────────────────────


class TestPresetConfetti(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = preset_confetti(self.sess, "Cube")
        self.assertIsInstance(lines, list)

    def test_particle_system_present(self):
        lines = preset_confetti(self.sess, "Cube")
        self.assertTrue(lines_contain(lines, "PARTICLE_SYSTEM"))

    def test_high_count(self):
        lines = preset_confetti(self.sess, "Cube")
        self.assertTrue(lines_contain(lines, "pset.count = 2000"))

    def test_gravity_reduced(self):
        lines = preset_confetti(self.sess, "Cube")
        self.assertTrue(lines_contain(lines, "gravity = 0.3"))

    def test_colour_materials_created(self):
        lines = preset_confetti(self.sess, "Cube")
        self.assertTrue(lines_contain(lines, "bpy.data.materials.new"))

    def test_custom_colors_respected(self):
        custom = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        lines = preset_confetti(self.sess, "Cube", colors=custom)
        self.assertTrue(lines_contain(lines, "1.0, 0.0, 0.0"))

    def test_default_colors_rainbow(self):
        lines = preset_confetti(self.sess, "Cube")
        # Should have multiple confetti materials
        confetti_lines = [l for l in lines if "Confetti" in l]
        self.assertGreater(len(confetti_lines), 0)


# ── TestPresetSparks ─────────────────────────────────────────────────────────


class TestPresetSparks(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = preset_sparks(self.sess, "Sphere")
        self.assertIsInstance(lines, list)

    def test_particle_system(self):
        lines = preset_sparks(self.sess, "Sphere")
        self.assertTrue(lines_contain(lines, "PARTICLE_SYSTEM"))

    def test_high_count(self):
        lines = preset_sparks(self.sess, "Sphere")
        self.assertTrue(lines_contain(lines, "pset.count = 3000"))

    def test_short_lifetime(self):
        lines = preset_sparks(self.sess, "Sphere")
        self.assertTrue(lines_contain(lines, "pset.lifetime = 15"))

    def test_emission_strength(self):
        lines = preset_sparks(self.sess, "Sphere")
        self.assertTrue(lines_contain(lines, "Emission Strength"))

    def test_spark_material_created(self):
        lines = preset_sparks(self.sess, "Sphere")
        self.assertTrue(lines_contain(lines, "SparkMat"))

    def test_custom_color(self):
        lines = preset_sparks(self.sess, "Sphere", color=[0.0, 0.5, 1.0, 1.0])
        self.assertTrue(lines_contain(lines, "0.0, 0.5, 1.0, 1.0"))

    def test_gravity_full(self):
        lines = preset_sparks(self.sess, "Sphere")
        self.assertTrue(lines_contain(lines, "gravity = 1.0"))


# ── TestPresetDisintegrate ───────────────────────────────────────────────────


class TestPresetDisintegrate(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = preset_disintegrate(self.sess, "Cube")
        self.assertIsInstance(lines, list)

    def test_particle_system(self):
        lines = preset_disintegrate(self.sess, "Cube")
        self.assertTrue(lines_contain(lines, "PARTICLE_SYSTEM"))

    def test_explode_modifier(self):
        lines = preset_disintegrate(self.sess, "Cube")
        self.assertTrue(lines_contain(lines, "EXPLODE"))

    def test_explode_modifier_name(self):
        lines = preset_disintegrate(self.sess, "Cube")
        self.assertTrue(lines_contain(lines, "name='Explode'"))

    def test_edge_cut_enabled(self):
        lines = preset_disintegrate(self.sess, "Cube")
        self.assertTrue(lines_contain(lines, "use_edge_cut = True"))

    def test_invalid_duration(self):
        with self.assertRaises(ValueError):
            preset_disintegrate(self.sess, "Cube", duration=0.0)

    def test_particle_system_index(self):
        lines = preset_disintegrate(self.sess, "Cube")
        self.assertTrue(lines_contain(lines, "particle_system_index = 0"))

    def test_duration_affects_lifetime(self):
        lines_short = preset_disintegrate(self.sess, "Cube", duration=1.0)
        lines_long = preset_disintegrate(self.sess, "Cube", duration=5.0)
        # Longer duration should produce a higher lifetime value
        joined_short = "\n".join(lines_short)
        joined_long = "\n".join(lines_long)
        # Both should contain lifetime assignment
        self.assertIn("pset.lifetime", joined_short)
        self.assertIn("pset.lifetime", joined_long)


# ── TestPresetDataStream ─────────────────────────────────────────────────────


class TestPresetDataStream(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = preset_data_stream(self.sess)
        self.assertIsInstance(lines, list)

    def test_particle_system(self):
        lines = preset_data_stream(self.sess)
        self.assertTrue(lines_contain(lines, "PARTICLE_SYSTEM"))

    def test_emitter_plane_created(self):
        lines = preset_data_stream(self.sess)
        self.assertTrue(lines_contain(lines, "primitive_plane_add"))

    def test_stream_material(self):
        lines = preset_data_stream(self.sess)
        self.assertTrue(lines_contain(lines, "DataStream"))

    def test_gravity_off(self):
        lines = preset_data_stream(self.sess)
        self.assertTrue(lines_contain(lines, "gravity = 0.0"))

    def test_emission_glow(self):
        lines = preset_data_stream(self.sess)
        self.assertTrue(lines_contain(lines, "Emission Strength"))

    def test_custom_speed(self):
        lines = preset_data_stream(self.sess, speed=10.0)
        self.assertTrue(lines_contain(lines, "pset.normal_factor = 10.0"))

    def test_custom_direction(self):
        lines = preset_data_stream(self.sess, direction=[1.0, 0.0, 0.0])
        self.assertTrue(lines_contain(lines, "[1.0, 0.0, 0.0]"))

    def test_invalid_speed(self):
        with self.assertRaises(ValueError):
            preset_data_stream(self.sess, speed=0.0)

    def test_invalid_direction_length(self):
        with self.assertRaises(ValueError):
            preset_data_stream(self.sess, direction=[0.0, 1.0])


# ── Entry Point ───────────────────────────────────────────────────────────────


if __name__ == "__main__":
    unittest.main()
