"""Unit tests for the Blender 3D camera animation module.

Tests verify:
- Session JSON state mutation (camera records stored correctly)
- bpy script string contents (correct ops/data_paths present)
- Easing integration (interpolated values are clamped / monotone where expected)
- Error handling (bad arguments raise ValueError)
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
from cli_anything.blender.core.camera import (
    create_camera,
    dolly,
    orbit,
    pan,
    zoom,
    rack_focus,
    crane,
    follow_path,
    shake,
    _fov_to_lens,
    _catmull_rom,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_session(cam_name: str = "Camera", location=None, **kwargs):
    """Return a Session pre-loaded with a scene and one camera."""
    sess = Session()
    proj = create_scene(name="TestScene")
    sess.set_project(proj)
    create_camera(sess, name=cam_name, location=location or [0.0, 0.0, 5.0], **kwargs)
    return sess


# ── FOV / Lens helpers ───────────────────────────────────────────────────────

class TestFovToLens:
    def test_50mm_fov(self):
        # fov ≈ 39.6° for a 50 mm lens on a 36 mm sensor
        fov = math.degrees(2 * math.atan(18 / 50))
        lens = _fov_to_lens(fov)
        assert abs(lens - 50.0) < 0.01

    def test_wide_fov_gives_short_lens(self):
        assert _fov_to_lens(90) < _fov_to_lens(40)

    def test_boundary_returns_50mm(self):
        # Degenerate values → fallback to 50 mm
        assert _fov_to_lens(0) == 50.0
        assert _fov_to_lens(180) == 50.0


class TestCatmullRom:
    def test_at_t0_returns_p1(self):
        assert _catmull_rom(0, 1, 2, 3, 0.0) == pytest.approx(1.0)

    def test_at_t1_returns_p2(self):
        assert _catmull_rom(0, 1, 2, 3, 1.0) == pytest.approx(2.0)

    def test_midpoint_of_flat_line(self):
        # All points on same value → midpoint == that value
        assert _catmull_rom(5, 5, 5, 5, 0.5) == pytest.approx(5.0)


# ── create_camera ────────────────────────────────────────────────────────────

class TestCreateCamera:
    def test_returns_result_dict(self):
        sess = Session()
        proj = create_scene()
        sess.set_project(proj)
        result = create_camera(sess)
        assert "camera" in result
        assert "script_lines" in result

    def test_camera_stored_in_scene_json(self):
        sess = Session()
        proj = create_scene()
        sess.set_project(proj)
        create_camera(sess, name="MyCam")
        cameras = sess.get_project()["cameras"]
        assert len(cameras) == 1
        assert cameras[0]["name"] == "MyCam"

    def test_first_camera_is_active(self):
        sess = Session()
        proj = create_scene()
        sess.set_project(proj)
        result = create_camera(sess, name="Cam1")
        assert result["camera"]["is_active"] is True

    def test_second_camera_not_active(self):
        sess = Session()
        proj = create_scene()
        sess.set_project(proj)
        create_camera(sess, name="Cam1")
        result = create_camera(sess, name="Cam2")
        assert result["camera"]["is_active"] is False

    def test_bpy_ops_camera_add_in_script(self):
        sess = Session()
        proj = create_scene()
        sess.set_project(proj)
        result = create_camera(sess)
        script = "\n".join(result["script_lines"])
        assert "bpy.ops.object.camera_add" in script

    def test_camera_name_in_script(self):
        sess = Session()
        proj = create_scene()
        sess.set_project(proj)
        result = create_camera(sess, name="TestCam")
        script = "\n".join(result["script_lines"])
        assert "TestCam" in script

    def test_fov_converts_to_lens(self):
        sess = Session()
        proj = create_scene()
        sess.set_project(proj)
        result = create_camera(sess, fov=60.0)
        expected_lens = _fov_to_lens(60.0)
        assert abs(result["camera"]["focal_length"] - expected_lens) < 0.01

    def test_invalid_cam_type_raises(self):
        sess = Session()
        proj = create_scene()
        sess.set_project(proj)
        with pytest.raises(ValueError, match="Invalid cam_type"):
            create_camera(sess, cam_type="INVALID")

    def test_invalid_fov_raises(self):
        sess = Session()
        proj = create_scene()
        sess.set_project(proj)
        with pytest.raises(ValueError, match="fov must be between"):
            create_camera(sess, fov=0)
        with pytest.raises(ValueError, match="fov must be between"):
            create_camera(sess, fov=180)

    def test_dof_params_in_script_when_enabled(self):
        sess = Session()
        proj = create_scene()
        sess.set_project(proj)
        result = create_camera(sess, dof_enabled=True, dof_focus_distance=5.0)
        script = "\n".join(result["script_lines"])
        assert "use_dof" in script
        assert "focus_distance" in script

    def test_orthographic_type(self):
        sess = Session()
        proj = create_scene()
        sess.set_project(proj)
        result = create_camera(sess, cam_type="orthographic")
        assert result["camera"]["type"] == "ORTHO"
        script = "\n".join(result["script_lines"])
        assert "ORTHO" in script

    def test_unique_name_on_duplicate(self):
        sess = Session()
        proj = create_scene()
        sess.set_project(proj)
        r1 = create_camera(sess, name="Cam")
        r2 = create_camera(sess, name="Cam")
        assert r1["camera"]["name"] != r2["camera"]["name"]


# ── dolly ────────────────────────────────────────────────────────────────────

class TestDolly:
    def test_returns_list_of_strings(self):
        sess = make_session()
        lines = dolly(sess, "Camera", [0, 0, 0], [10, 0, 0], duration=1.0, fps=10)
        assert isinstance(lines, list)
        assert all(isinstance(l, str) for l in lines)

    def test_keyframe_insert_in_lines(self):
        sess = make_session()
        lines = dolly(sess, "Camera", [0, 0, 0], [10, 0, 0], duration=1.0, fps=10)
        combined = "\n".join(lines)
        assert "keyframe_insert" in combined

    def test_location_in_lines(self):
        sess = make_session()
        lines = dolly(sess, "Camera", [0, 0, 0], [10, 0, 0], duration=1.0, fps=10)
        combined = "\n".join(lines)
        assert "location" in combined

    def test_correct_frame_count(self):
        sess = make_session()
        lines = dolly(sess, "Camera", [0, 0, 0], [5, 0, 0], duration=1.0, fps=5)
        # 1s × 5fps = 5 frames + 1 (frame 0→5) = 6 keyframe pairs
        kf_lines = [l for l in lines if "keyframe_insert" in l]
        assert len(kf_lines) == 6  # frames 1..6

    def test_start_and_end_positions(self):
        sess = make_session()
        lines = dolly(sess, "Camera", [1.0, 2.0, 3.0], [4.0, 5.0, 6.0],
                      duration=1.0, fps=2)
        # First location line should contain start coords
        loc_lines = [l for l in lines if "camera.location = " in l]
        first_loc = loc_lines[0]
        assert "1.000000" in first_loc
        assert "2.000000" in first_loc

    def test_animation_metadata_stored_in_json(self):
        sess = make_session()
        dolly(sess, "Camera", [0, 0, 0], [5, 0, 0], duration=2.0, fps=10)
        cam = sess.get_project()["cameras"][0]
        assert any(a["type"] == "dolly" for a in cam["animations"])

    def test_invalid_start_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="start must have 3"):
            dolly(sess, "Camera", [0, 0], [1, 0, 0], duration=1.0)

    def test_invalid_duration_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="duration must be positive"):
            dolly(sess, "Camera", [0, 0, 0], [1, 0, 0], duration=0)

    def test_unknown_camera_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="not found"):
            dolly(sess, "NoSuchCam", [0, 0, 0], [1, 0, 0], duration=1.0)


# ── orbit ────────────────────────────────────────────────────────────────────

class TestOrbit:
    def test_returns_list_of_strings(self):
        sess = make_session()
        lines = orbit(sess, "Camera", center=[0, 0, 0], radius=5.0,
                      start_angle=0, end_angle=90, duration=1.0, fps=10)
        assert isinstance(lines, list)
        assert len(lines) > 0

    def test_keyframe_insert_in_lines(self):
        sess = make_session()
        lines = orbit(sess, "Camera", [0, 0, 0], 5.0, 0, 180, 1.0, fps=5)
        combined = "\n".join(lines)
        assert "keyframe_insert" in combined

    def test_location_and_rotation_in_lines(self):
        sess = make_session()
        lines = orbit(sess, "Camera", [0, 0, 0], 5.0, 0, 360, 2.0, fps=5)
        combined = "\n".join(lines)
        assert "location" in combined
        assert "rotation_euler" in combined

    def test_radius_preserved(self):
        """Camera should stay at approximately the given radius from center."""
        sess = make_session()
        r = 7.0
        lines = orbit(sess, "Camera", [0, 0, 0], r, 0, 0, duration=0.1, fps=10)
        loc_lines = [l for l in lines if "camera.location = " in l]
        # Parse first location
        import re
        m = re.search(r"camera\.location = \(([^)]+)\)", loc_lines[0])
        assert m
        coords = [float(v.strip()) for v in m.group(1).split(",")]
        dist = math.sqrt(coords[0] ** 2 + coords[1] ** 2)
        assert abs(dist - r) < 0.01

    def test_invalid_radius_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="radius must be positive"):
            orbit(sess, "Camera", [0, 0, 0], radius=0, start_angle=0,
                  end_angle=90, duration=1.0)

    def test_animation_metadata_stored(self):
        sess = make_session()
        orbit(sess, "Camera", [0, 0, 0], 5.0, 0, 90, 1.0, fps=10)
        cam = sess.get_project()["cameras"][0]
        assert any(a["type"] == "orbit" for a in cam["animations"])


# ── pan ──────────────────────────────────────────────────────────────────────

class TestPan:
    def test_returns_list_of_strings(self):
        sess = make_session()
        lines = pan(sess, "Camera", [0, 0, 0], [5, 0, 0], duration=1.0, fps=10)
        assert isinstance(lines, list)

    def test_keyframe_insert_in_lines(self):
        sess = make_session()
        lines = pan(sess, "Camera", [0, 0, 0], [5, 0, 0], duration=1.0, fps=5)
        combined = "\n".join(lines)
        assert "keyframe_insert" in combined

    def test_rotation_euler_in_lines(self):
        sess = make_session()
        lines = pan(sess, "Camera", [1, 0, 0], [0, 1, 0], duration=1.0, fps=5)
        combined = "\n".join(lines)
        assert "rotation_euler" in combined

    def test_invalid_start_target_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="start_target must have 3"):
            pan(sess, "Camera", [0, 0], [1, 0, 0], duration=1.0)

    def test_animation_metadata_stored(self):
        sess = make_session()
        pan(sess, "Camera", [0, 0, 0], [1, 0, 0], duration=1.0, fps=5)
        cam = sess.get_project()["cameras"][0]
        assert any(a["type"] == "pan" for a in cam["animations"])


# ── zoom ─────────────────────────────────────────────────────────────────────

class TestZoom:
    def test_returns_list_of_strings(self):
        sess = make_session()
        lines = zoom(sess, "Camera", 50, 90, duration=1.0, fps=10)
        assert isinstance(lines, list)

    def test_keyframe_insert_in_lines(self):
        sess = make_session()
        lines = zoom(sess, "Camera", 50, 90, duration=1.0, fps=5)
        combined = "\n".join(lines)
        assert "keyframe_insert" in combined

    def test_lens_in_lines(self):
        sess = make_session()
        lines = zoom(sess, "Camera", 50, 90, duration=1.0, fps=5)
        combined = "\n".join(lines)
        assert "lens" in combined

    def test_first_frame_has_start_fov_lens(self):
        sess = make_session()
        lines = zoom(sess, "Camera", 40.0, 80.0, duration=1.0, fps=2)
        import re
        lens_lines = [l for l in lines if "camera.data.lens = " in l]
        m = re.search(r"camera\.data\.lens = ([0-9.]+)", lens_lines[0])
        assert m
        got_lens = float(m.group(1))
        expected = _fov_to_lens(40.0)
        assert abs(got_lens - expected) < 0.1

    def test_invalid_fov_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="start_fov must be between"):
            zoom(sess, "Camera", 0, 80, duration=1.0)
        with pytest.raises(ValueError, match="end_fov must be between"):
            zoom(sess, "Camera", 40, 200, duration=1.0)

    def test_animation_metadata_stored(self):
        sess = make_session()
        zoom(sess, "Camera", 50, 90, duration=1.0, fps=5)
        cam = sess.get_project()["cameras"][0]
        assert any(a["type"] == "zoom" for a in cam["animations"])


# ── rack_focus ───────────────────────────────────────────────────────────────

class TestRackFocus:
    def test_returns_list_of_strings(self):
        sess = make_session()
        lines = rack_focus(sess, "Camera", 2.0, 10.0, duration=1.0, fps=10)
        assert isinstance(lines, list)

    def test_keyframe_insert_in_lines(self):
        sess = make_session()
        lines = rack_focus(sess, "Camera", 2.0, 10.0, duration=1.0, fps=5)
        combined = "\n".join(lines)
        assert "keyframe_insert" in combined

    def test_focus_distance_or_dof_in_lines(self):
        sess = make_session()
        lines = rack_focus(sess, "Camera", 2.0, 10.0, duration=1.0, fps=5)
        combined = "\n".join(lines)
        # Either "focus_distance" or "dof" should appear
        assert "focus_distance" in combined or "dof" in combined

    def test_dof_enabled_in_json_after_call(self):
        sess = make_session()
        rack_focus(sess, "Camera", 2.0, 10.0, duration=1.0, fps=5)
        cam = sess.get_project()["cameras"][0]
        assert cam["dof_enabled"] is True

    def test_use_dof_in_script(self):
        sess = make_session()
        lines = rack_focus(sess, "Camera", 2.0, 10.0, duration=1.0, fps=5)
        combined = "\n".join(lines)
        assert "use_dof" in combined

    def test_invalid_start_distance_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="start_distance must be positive"):
            rack_focus(sess, "Camera", 0, 10.0, duration=1.0)

    def test_animation_metadata_stored(self):
        sess = make_session()
        rack_focus(sess, "Camera", 2.0, 10.0, duration=1.0, fps=5)
        cam = sess.get_project()["cameras"][0]
        assert any(a["type"] == "rack_focus" for a in cam["animations"])


# ── crane ────────────────────────────────────────────────────────────────────

class TestCrane:
    def test_returns_list_of_strings(self):
        sess = make_session()
        lines = crane(sess, "Camera", 0.0, 10.0, duration=1.0, fps=10)
        assert isinstance(lines, list)

    def test_keyframe_insert_in_lines(self):
        sess = make_session()
        lines = crane(sess, "Camera", 0.0, 10.0, duration=1.0, fps=5)
        combined = "\n".join(lines)
        assert "keyframe_insert" in combined

    def test_location_in_lines(self):
        sess = make_session()
        lines = crane(sess, "Camera", 0.0, 10.0, duration=1.0, fps=5)
        combined = "\n".join(lines)
        assert "location" in combined

    def test_x_y_stay_fixed(self):
        """X and Y should remain at the camera's initial position."""
        sess = make_session(location=[3.0, 4.0, 0.0])
        lines = crane(sess, "Camera", 0.0, 10.0, duration=0.5, fps=5)
        import re
        loc_lines = [l for l in lines if "camera.location = " in l]
        for line in loc_lines:
            m = re.search(r"camera\.location = \(([^)]+)\)", line)
            if m:
                coords = [float(v.strip()) for v in m.group(1).split(",")]
                assert abs(coords[0] - 3.0) < 0.001
                assert abs(coords[1] - 4.0) < 0.001

    def test_invalid_duration_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="duration must be positive"):
            crane(sess, "Camera", 0.0, 10.0, duration=-1.0)

    def test_animation_metadata_stored(self):
        sess = make_session()
        crane(sess, "Camera", 0.0, 10.0, duration=1.0, fps=5)
        cam = sess.get_project()["cameras"][0]
        assert any(a["type"] == "crane" for a in cam["animations"])


# ── follow_path ──────────────────────────────────────────────────────────────

class TestFollowPath:
    def test_returns_list_of_strings(self):
        pts = [[0, 0, 0], [5, 0, 0], [5, 5, 0]]
        sess = make_session()
        lines = follow_path(sess, "Camera", pts, duration=1.0, fps=10)
        assert isinstance(lines, list)

    def test_keyframe_insert_in_lines(self):
        pts = [[0, 0, 0], [5, 0, 0], [10, 0, 0]]
        sess = make_session()
        lines = follow_path(sess, "Camera", pts, duration=1.0, fps=5)
        combined = "\n".join(lines)
        assert "keyframe_insert" in combined

    def test_location_in_lines(self):
        pts = [[0, 0, 0], [5, 0, 0]]
        sess = make_session()
        lines = follow_path(sess, "Camera", pts, duration=1.0, fps=5)
        combined = "\n".join(lines)
        assert "location" in combined

    def test_start_point_is_first_location(self):
        pts = [[1.0, 2.0, 3.0], [10.0, 10.0, 10.0]]
        sess = make_session()
        lines = follow_path(sess, "Camera", pts, duration=1.0, fps=2)
        import re
        loc_lines = [l for l in lines if "camera.location = " in l]
        m = re.search(r"camera\.location = \(([^)]+)\)", loc_lines[0])
        assert m
        coords = [float(v.strip()) for v in m.group(1).split(",")]
        assert abs(coords[0] - 1.0) < 0.001

    def test_too_few_points_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="At least 2 path points"):
            follow_path(sess, "Camera", [[0, 0, 0]], duration=1.0)

    def test_bad_point_shape_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="must have 3 components"):
            follow_path(sess, "Camera", [[0, 0], [1, 0, 0]], duration=1.0)

    def test_animation_metadata_stored(self):
        pts = [[0, 0, 0], [5, 0, 0]]
        sess = make_session()
        follow_path(sess, "Camera", pts, duration=1.0, fps=5)
        cam = sess.get_project()["cameras"][0]
        assert any(a["type"] == "follow_path" for a in cam["animations"])


# ── shake ────────────────────────────────────────────────────────────────────

class TestShake:
    def test_returns_list_of_strings(self):
        sess = make_session()
        lines = shake(sess, "Camera", intensity=0.1, frequency=5.0,
                      decay=1.0, duration=1.0, fps=10)
        assert isinstance(lines, list)

    def test_keyframe_insert_in_lines(self):
        sess = make_session()
        lines = shake(sess, "Camera", 0.1, 5.0, 1.0, 1.0, fps=5)
        combined = "\n".join(lines)
        assert "keyframe_insert" in combined

    def test_location_in_lines(self):
        sess = make_session()
        lines = shake(sess, "Camera", 0.1, 5.0, 1.0, 1.0, fps=5)
        combined = "\n".join(lines)
        assert "location" in combined

    def test_decay_reduces_amplitude(self):
        """Later frames should have smaller offsets than early ones with decay>0."""
        sess = make_session(location=[0.0, 0.0, 0.0])
        import re
        lines = shake(sess, "Camera", intensity=1.0, frequency=1.0,
                      decay=5.0, duration=2.0, fps=10)
        loc_lines = [l for l in lines if "camera.location = " in l]
        # Parse first and last location magnitudes
        def parse_mag(line):
            m = re.search(r"camera\.location = \(([^)]+)\)", line)
            if not m:
                return None
            coords = [float(v.strip()) for v in m.group(1).split(",")]
            return math.sqrt(sum(c ** 2 for c in coords))

        first_mag = parse_mag(loc_lines[1])   # frame 2 (after start)
        last_mag = parse_mag(loc_lines[-1])
        # With decay=5 over 2s the last frame amplitude should be much smaller
        assert last_mag < first_mag or last_mag < 0.01

    def test_invalid_intensity_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="intensity must be non-negative"):
            shake(sess, "Camera", -0.1, 5.0, 1.0, 1.0)

    def test_invalid_frequency_raises(self):
        sess = make_session()
        with pytest.raises(ValueError, match="frequency must be positive"):
            shake(sess, "Camera", 0.1, 0.0, 1.0, 1.0)

    def test_animation_metadata_stored(self):
        sess = make_session()
        shake(sess, "Camera", 0.1, 5.0, 1.0, 1.0, fps=5)
        cam = sess.get_project()["cameras"][0]
        assert any(a["type"] == "shake" for a in cam["animations"])


# ── Multiple animations on same camera ───────────────────────────────────────

class TestMultipleAnimations:
    def test_multiple_animations_accumulate(self):
        sess = make_session()
        dolly(sess, "Camera", [0, 0, 0], [5, 0, 0], 1.0, fps=5)
        zoom(sess, "Camera", 50, 90, 1.0, fps=5)
        crane(sess, "Camera", 0.0, 5.0, 1.0, fps=5)
        cam = sess.get_project()["cameras"][0]
        types = [a["type"] for a in cam["animations"]]
        assert "dolly" in types
        assert "zoom" in types
        assert "crane" in types

    def test_multiple_cameras_independent(self):
        sess = Session()
        proj = create_scene()
        sess.set_project(proj)
        create_camera(sess, name="CamA")
        create_camera(sess, name="CamB")
        dolly(sess, "CamA", [0, 0, 0], [5, 0, 0], 1.0, fps=5)
        rack_focus(sess, "CamB", 1.0, 10.0, 1.0, fps=5)
        cameras = sess.get_project()["cameras"]
        cam_a = next(c for c in cameras if c["name"] == "CamA")
        cam_b = next(c for c in cameras if c["name"] == "CamB")
        assert any(a["type"] == "dolly" for a in cam_a["animations"])
        assert any(a["type"] == "rack_focus" for a in cam_b["animations"])
        # CamA should not have rack_focus
        assert not any(a["type"] == "rack_focus" for a in cam_a["animations"])
