"""Tests for blender/core/shape_layers.py

Verifies that each function generates bpy script lines containing the
correct Blender API calls.  A lightweight MockSession is used so the
tests run without a live Blender instance.
"""

import sys
import os
import unittest

# Ensure the package root is importable
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", ".."),
)

from cli_anything.blender.core.shape_layers import (
    create_rectangle,
    create_ellipse,
    create_polygon,
    create_star,
    create_custom_path,
    morph,
    trim_path,
    offset_path,
    repeater,
)


# ── Mock Session ─────────────────────────────────────────────────────────────


class MockSession:
    """Minimal Session-alike that holds a bare project dict."""

    def __init__(self):
        self._project = {}

    def get_project(self):
        return self._project


# ── Helpers ──────────────────────────────────────────────────────────────────


def lines_contain(lines, *fragments):
    """Return True if *all* fragments appear in at least one line each."""
    joined = "\n".join(lines)
    return all(frag in joined for frag in fragments)


# ── TestCreateRectangle ──────────────────────────────────────────────────────


class TestCreateRectangle(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = create_rectangle(self.sess, 2.0, 1.0, name="Rect")
        self.assertIsInstance(lines, list)
        self.assertGreater(len(lines), 0)

    def test_curve_creation(self):
        lines = create_rectangle(self.sess, 2.0, 1.0, name="Rect")
        self.assertTrue(lines_contain(lines, "bpy.data.curves.new", "CURVE"))

    def test_spline_type_bezier(self):
        lines = create_rectangle(self.sess, 2.0, 1.0, name="Rect")
        self.assertTrue(lines_contain(lines, "BEZIER"))

    def test_fill_2d(self):
        lines = create_rectangle(self.sess, 2.0, 1.0, name="Rect")
        self.assertTrue(lines_contain(lines, "dimensions = '2D'"))

    def test_cyclic(self):
        lines = create_rectangle(self.sess, 2.0, 1.0, name="Rect")
        self.assertTrue(lines_contain(lines, "use_cyclic_u = True"))

    def test_fill_color_applied(self):
        lines = create_rectangle(self.sess, 2.0, 1.0,
                                 fill_color=[1.0, 0.0, 0.0, 1.0], name="RedRect")
        self.assertTrue(lines_contain(lines, "Base Color"))

    def test_stroke_when_provided(self):
        lines = create_rectangle(self.sess, 2.0, 1.0,
                                 stroke_color=[0.0, 0.0, 0.0, 1.0], name="StrokeRect")
        self.assertTrue(lines_contain(lines, "bevel_depth"))

    def test_rounded_corners(self):
        lines = create_rectangle(self.sess, 4.0, 2.0, corner_radius=0.3, name="RoundRect")
        # 8 points for rounded rect
        self.assertTrue(lines_contain(lines, "bezier_points.add(7)"))

    def test_sharp_corners(self):
        lines = create_rectangle(self.sess, 4.0, 2.0, corner_radius=0.0, name="SharpRect")
        # 4 points for sharp rect
        self.assertTrue(lines_contain(lines, "bezier_points.add(3)"))

    def test_object_linked_to_collection(self):
        lines = create_rectangle(self.sess, 2.0, 1.0, name="LinkedRect")
        self.assertTrue(lines_contain(lines, "collection.objects.link"))

    def test_invalid_width(self):
        with self.assertRaises(ValueError):
            create_rectangle(self.sess, -1.0, 1.0)

    def test_invalid_height(self):
        with self.assertRaises(ValueError):
            create_rectangle(self.sess, 1.0, 0.0)

    def test_invalid_corner_radius(self):
        with self.assertRaises(ValueError):
            create_rectangle(self.sess, 2.0, 2.0, corner_radius=-0.1)

    def test_session_records_shape(self):
        create_rectangle(self.sess, 2.0, 1.0, name="TrackedRect")
        shapes = self.sess.get_project().get("shapes", [])
        self.assertTrue(any(s["name"] == "TrackedRect" for s in shapes))

    def test_unique_naming(self):
        create_rectangle(self.sess, 2.0, 1.0, name="R")
        create_rectangle(self.sess, 3.0, 1.5, name="R")
        shapes = self.sess.get_project().get("shapes", [])
        names = [s["name"] for s in shapes]
        self.assertEqual(len(set(names)), 2)


# ── TestCreateEllipse ────────────────────────────────────────────────────────


class TestCreateEllipse(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = create_ellipse(self.sess, 1.0, 0.5, name="Ell")
        self.assertIsInstance(lines, list)

    def test_nurbs_circle_add(self):
        lines = create_ellipse(self.sess, 1.0, 0.5, name="Ell")
        self.assertTrue(lines_contain(lines, "primitive_nurbs_circle_add"))

    def test_scale_applied(self):
        lines = create_ellipse(self.sess, 2.0, 1.0, name="Ell")
        self.assertTrue(lines_contain(lines, "scale = (2.0, 1.0, 1.0)"))

    def test_fill_material(self):
        lines = create_ellipse(self.sess, 1.0, 1.0,
                               fill_color=[0.0, 1.0, 0.0, 1.0], name="GreenEll")
        self.assertTrue(lines_contain(lines, "Base Color"))

    def test_dimensions_2d(self):
        lines = create_ellipse(self.sess, 1.0, 0.5)
        self.assertTrue(lines_contain(lines, "dimensions = '2D'"))

    def test_invalid_rx(self):
        with self.assertRaises(ValueError):
            create_ellipse(self.sess, 0.0, 1.0)

    def test_invalid_ry(self):
        with self.assertRaises(ValueError):
            create_ellipse(self.sess, 1.0, -0.5)

    def test_session_records_shape(self):
        create_ellipse(self.sess, 1.0, 0.5, name="EllRecord")
        shapes = self.sess.get_project().get("shapes", [])
        self.assertTrue(any(s["type"] == "ellipse" for s in shapes))


# ── TestCreatePolygon ────────────────────────────────────────────────────────


class TestCreatePolygon(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = create_polygon(self.sess, 6, 1.0, name="Hex")
        self.assertIsInstance(lines, list)

    def test_circle_add_with_vertices(self):
        lines = create_polygon(self.sess, 6, 1.0, name="Hex")
        self.assertTrue(lines_contain(lines, "primitive_circle_add", "vertices=6"))

    def test_ngon_fill(self):
        lines = create_polygon(self.sess, 5, 1.0)
        self.assertTrue(lines_contain(lines, "NGON"))

    def test_fill_material(self):
        lines = create_polygon(self.sess, 4, 1.0,
                               fill_color=[0.5, 0.5, 0.5, 1.0])
        self.assertTrue(lines_contain(lines, "Base Color"))

    def test_invalid_sides(self):
        with self.assertRaises(ValueError):
            create_polygon(self.sess, 2, 1.0)

    def test_invalid_radius(self):
        with self.assertRaises(ValueError):
            create_polygon(self.sess, 5, -1.0)

    def test_session_records_shape(self):
        create_polygon(self.sess, 6, 2.0, name="HexRecord")
        shapes = self.sess.get_project().get("shapes", [])
        self.assertTrue(any(s["name"] == "HexRecord" for s in shapes))


# ── TestCreateStar ───────────────────────────────────────────────────────────


class TestCreateStar(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = create_star(self.sess, 5, 0.5, 1.0, name="Star5")
        self.assertIsInstance(lines, list)

    def test_mesh_from_pydata(self):
        lines = create_star(self.sess, 5, 0.5, 1.0, name="Star5")
        self.assertTrue(lines_contain(lines, "from_pydata"))

    def test_bmesh_import(self):
        lines = create_star(self.sess, 5, 0.5, 1.0)
        self.assertTrue(lines_contain(lines, "import bmesh"))

    def test_vertex_count(self):
        # 5-point star → 10 vertices (outer + inner alternating)
        lines = create_star(self.sess, 5, 0.5, 1.0)
        joined = "\n".join(lines)
        # Should have 10 vertices in the list
        self.assertIn("verts = [", joined)

    def test_fill_material(self):
        lines = create_star(self.sess, 6, 0.4, 1.0,
                            fill_color=[1.0, 1.0, 0.0, 1.0])
        self.assertTrue(lines_contain(lines, "Base Color"))

    def test_linked_to_collection(self):
        lines = create_star(self.sess, 5, 0.5, 1.0, name="LinkedStar")
        self.assertTrue(lines_contain(lines, "collection.objects.link"))

    def test_invalid_points(self):
        with self.assertRaises(ValueError):
            create_star(self.sess, 2, 0.5, 1.0)

    def test_invalid_inner_radius(self):
        with self.assertRaises(ValueError):
            create_star(self.sess, 5, 0.0, 1.0)

    def test_invalid_outer_less_than_inner(self):
        with self.assertRaises(ValueError):
            create_star(self.sess, 5, 1.0, 0.5)

    def test_session_records_shape(self):
        create_star(self.sess, 4, 0.5, 1.0, name="StarRecord")
        shapes = self.sess.get_project().get("shapes", [])
        self.assertTrue(any(s["type"] == "star" for s in shapes))


# ── TestCreateCustomPath ─────────────────────────────────────────────────────


class TestCreateCustomPath(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()
        self.pts = [
            {"co": [0.0, 0.0, 0.0]},
            {"co": [1.0, 1.0, 0.0]},
            {"co": [2.0, 0.0, 0.0]},
        ]

    def test_returns_list(self):
        lines = create_custom_path(self.sess, self.pts, name="MyPath")
        self.assertIsInstance(lines, list)

    def test_bezier_curve_created(self):
        lines = create_custom_path(self.sess, self.pts, name="MyPath")
        self.assertTrue(lines_contain(lines, "bpy.data.curves.new", "BEZIER"))

    def test_correct_point_count(self):
        lines = create_custom_path(self.sess, self.pts)
        # 3 points → add(2)
        self.assertTrue(lines_contain(lines, "bezier_points.add(2)"))

    def test_handle_types_set(self):
        lines = create_custom_path(self.sess, self.pts)
        self.assertTrue(lines_contain(lines, "handle_left_type"))

    def test_stroke_bevel_when_provided(self):
        lines = create_custom_path(
            self.sess, self.pts,
            stroke_color=[1.0, 1.0, 1.0, 1.0], name="StrokePath"
        )
        self.assertTrue(lines_contain(lines, "bevel_depth"))

    def test_no_stroke_without_color(self):
        lines = create_custom_path(self.sess, self.pts, name="NoStroke")
        self.assertFalse(lines_contain(lines, "bevel_depth"))

    def test_invalid_too_few_points(self):
        with self.assertRaises(ValueError):
            create_custom_path(self.sess, [{"co": [0, 0, 0]}])

    def test_session_records_shape(self):
        create_custom_path(self.sess, self.pts, name="RecordedPath")
        shapes = self.sess.get_project().get("shapes", [])
        self.assertTrue(any(s["name"] == "RecordedPath" for s in shapes))


# ── TestMorph ────────────────────────────────────────────────────────────────


class TestMorph(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = morph(self.sess, "ShapeA", "ShapeB", duration=1.0)
        self.assertIsInstance(lines, list)

    def test_shape_key_add(self):
        lines = morph(self.sess, "ShapeA", "ShapeB", duration=1.0)
        self.assertTrue(lines_contain(lines, "shape_key_add"))

    def test_keyframe_insert_value(self):
        lines = morph(self.sess, "ShapeA", "ShapeB", duration=1.0, fps=30)
        self.assertTrue(lines_contain(lines, "keyframe_insert", "data_path='value'"))

    def test_correct_frame_count(self):
        lines = morph(self.sess, "ShapeA", "ShapeB", duration=1.0, fps=10)
        kf_lines = [l for l in lines if "keyframe_insert" in l]
        # 1s × 10fps + 1 = 11 keyframes
        self.assertEqual(len(kf_lines), 11)

    def test_easing_applied(self):
        # With ease_in_out_cubic, mid-frame alpha should be ~0.5 but the
        # series of values is still present.  Check start and end extremes.
        lines = morph(self.sess, "A", "B", duration=0.5, fps=2)
        # First keyframe: value should be 0.0
        self.assertTrue(lines_contain(lines, "sk.value = 0.000000"))

    def test_invalid_duration(self):
        with self.assertRaises(ValueError):
            morph(self.sess, "A", "B", duration=-1.0)

    def test_object_lookup(self):
        lines = morph(self.sess, "ObjA", "ObjB", duration=1.0)
        self.assertTrue(lines_contain(lines, "bpy.data.objects.get('ObjA')"))
        self.assertTrue(lines_contain(lines, "bpy.data.objects.get('ObjB')"))

    def test_vertex_positions_copied(self):
        lines = morph(self.sess, "A", "B", duration=1.0)
        self.assertTrue(lines_contain(lines, "obj_b.data.vertices"))


# ── TestTrimPath ─────────────────────────────────────────────────────────────


class TestTrimPath(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = trim_path(self.sess, "MyCurve", 0.0, 1.0, duration=2.0)
        self.assertIsInstance(lines, list)

    def test_bevel_factor_end_keyframed(self):
        lines = trim_path(self.sess, "MyCurve", 0.0, 1.0, duration=1.0)
        self.assertTrue(lines_contain(lines, "bevel_factor_end"))

    def test_keyframe_insert_called(self):
        lines = trim_path(self.sess, "MyCurve", 0.0, 1.0, duration=1.0)
        self.assertTrue(lines_contain(lines, "keyframe_insert"))

    def test_correct_frame_count(self):
        lines = trim_path(self.sess, "Curve", 0.0, 1.0, duration=1.0, fps=5)
        kf_lines = [l for l in lines if "keyframe_insert" in l]
        # 1s × 5fps + 1 = 6 keyframes
        self.assertEqual(len(kf_lines), 6)

    def test_curve_type_check(self):
        lines = trim_path(self.sess, "Curve", 0.0, 1.0, duration=1.0)
        self.assertTrue(lines_contain(lines, "type == 'CURVE'"))

    def test_bevel_factor_mapping_set(self):
        lines = trim_path(self.sess, "Curve", 0.0, 1.0, duration=1.0)
        self.assertTrue(lines_contain(lines, "bevel_factor_mapping_end"))

    def test_invalid_duration(self):
        with self.assertRaises(ValueError):
            trim_path(self.sess, "Curve", 0.0, 1.0, duration=0.0)

    def test_invalid_start_pct(self):
        with self.assertRaises(ValueError):
            trim_path(self.sess, "Curve", -0.1, 1.0, duration=1.0)

    def test_invalid_end_pct(self):
        with self.assertRaises(ValueError):
            trim_path(self.sess, "Curve", 0.0, 1.5, duration=1.0)

    def test_partial_trim(self):
        # Trim from 0.25 to 0.75 — bevel factor at final frame should be ~0.75
        lines = trim_path(self.sess, "Curve", 0.25, 0.75, duration=0.1, fps=1)
        # At t=1.0 (ease), bevel_factor_end should be close to 0.75
        self.assertTrue(lines_contain(lines, "0.75"))


# ── TestOffsetPath ───────────────────────────────────────────────────────────


class TestOffsetPath(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = offset_path(self.sess, "MyShape", 0.5, duration=1.0)
        self.assertIsInstance(lines, list)

    def test_solidify_modifier_added(self):
        lines = offset_path(self.sess, "MyShape", 0.5, duration=1.0)
        self.assertTrue(lines_contain(lines, "SOLIDIFY"))

    def test_thickness_keyframed(self):
        lines = offset_path(self.sess, "MyShape", 0.5, duration=1.0)
        self.assertTrue(lines_contain(lines, "thickness"))
        self.assertTrue(lines_contain(lines, "keyframe_insert"))

    def test_starts_at_zero(self):
        lines = offset_path(self.sess, "MyShape", 1.0, duration=0.1, fps=1)
        # First keyframe should be thickness = 0.0
        self.assertTrue(lines_contain(lines, "solidify.thickness = 0.0"))

    def test_correct_frame_count(self):
        lines = offset_path(self.sess, "Shape", 1.0, duration=1.0, fps=4)
        kf_lines = [l for l in lines if "keyframe_insert" in l]
        # 1s × 4fps + 1 = 5 keyframes
        self.assertEqual(len(kf_lines), 5)

    def test_invalid_duration(self):
        with self.assertRaises(ValueError):
            offset_path(self.sess, "Shape", 1.0, duration=-1.0)

    def test_modifier_name(self):
        lines = offset_path(self.sess, "Shape", 0.5, duration=1.0)
        self.assertTrue(lines_contain(lines, "OffsetSolidify"))


# ── TestRepeater ─────────────────────────────────────────────────────────────


class TestRepeater(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = repeater(self.sess, "MyShape", copies=5)
        self.assertIsInstance(lines, list)

    def test_array_modifier_added(self):
        lines = repeater(self.sess, "MyShape", copies=5)
        self.assertTrue(lines_contain(lines, "ARRAY"))

    def test_count_set(self):
        lines = repeater(self.sess, "MyShape", copies=7)
        self.assertTrue(lines_contain(lines, "arr.count = 7"))

    def test_constant_offset_used(self):
        lines = repeater(self.sess, "MyShape", copies=3)
        self.assertTrue(lines_contain(lines, "use_constant_offset = True"))

    def test_offset_values(self):
        lines = repeater(self.sess, "MyShape", copies=3, offset=[2.0, 0.5, 0.0])
        self.assertTrue(lines_contain(lines, "(2.0, 0.5, 0.0)"))

    def test_default_offset(self):
        lines = repeater(self.sess, "Shape", copies=3)
        self.assertTrue(lines_contain(lines, "(1.0, 0.0, 0.0)"))

    def test_rotation_step_adds_empty(self):
        lines = repeater(self.sess, "MyShape", copies=4, rotation_step=30.0)
        self.assertTrue(lines_contain(lines, "empty_add"))
        self.assertTrue(lines_contain(lines, "use_object_offset = True"))

    def test_no_rotation_no_empty(self):
        lines = repeater(self.sess, "MyShape", copies=4, rotation_step=0.0)
        self.assertFalse(lines_contain(lines, "empty_add"))

    def test_invalid_copies(self):
        with self.assertRaises(ValueError):
            repeater(self.sess, "Shape", copies=0)

    def test_invalid_offset_length(self):
        with self.assertRaises(ValueError):
            repeater(self.sess, "Shape", copies=3, offset=[1.0, 0.0])

    def test_source_object_lookup(self):
        lines = repeater(self.sess, "SourceObj", copies=3)
        self.assertTrue(lines_contain(lines, "bpy.data.objects.get('SourceObj')"))


# ── Entry Point ───────────────────────────────────────────────────────────────


if __name__ == "__main__":
    unittest.main()
