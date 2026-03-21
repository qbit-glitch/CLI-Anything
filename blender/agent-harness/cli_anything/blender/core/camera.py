"""Blender CLI - 3D camera animation system.

Generates bpy Python script strings for camera setup and animated moves.
Each animation function returns a list of bpy script lines that can be
assembled by bpy_gen.py into a complete Blender Python script.

Relies on shared/motion_math for easing and keyframe interpolation.
"""

import math
import sys
import os
from typing import Dict, Any, List, Optional, Tuple

# Import shared motion_math library
# camera.py lives at: blender/agent-harness/cli_anything/blender/core/camera.py
# shared/  lives at:  <project-root>/shared/
# 5 levels of ".." bring us from core/ to the project root.
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "shared"),
)
from motion_math.easing import get_easing
from motion_math.keyframes import KeyframeTrack


# ── Camera types ────────────────────────────────────────────────────────────

CAMERA_TYPES = ["perspective", "orthographic", "panoramic"]
_BPY_CAM_TYPE = {
    "perspective": "PERSP",
    "orthographic": "ORTHO",
    "panoramic": "PANO",
}

# FOV to focal-length conversion uses a 36 mm sensor width (full-frame).
_SENSOR_WIDTH_MM = 36.0


def _fov_to_lens(fov_deg: float) -> float:
    """Convert vertical FOV in degrees to focal length in mm (full-frame sensor)."""
    fov_rad = math.radians(fov_deg)
    if fov_rad <= 0 or fov_rad >= math.pi:
        return 50.0
    return _SENSOR_WIDTH_MM / (2.0 * math.tan(fov_rad / 2.0))


def _next_camera_id(project: Dict[str, Any]) -> int:
    cameras = project.get("cameras", [])
    existing = [c.get("id", 0) for c in cameras]
    return max(existing, default=-1) + 1


def _unique_camera_name(project: Dict[str, Any], base: str) -> str:
    cameras = project.get("cameras", [])
    existing = {c.get("name", "") for c in cameras}
    if base not in existing:
        return base
    counter = 1
    while f"{base}.{counter:03d}" in existing:
        counter += 1
    return f"{base}.{counter:03d}"


def _find_camera(project: Dict[str, Any], camera_name: str) -> Dict[str, Any]:
    """Return the camera dict for *camera_name*, raising ValueError if missing."""
    for cam in project.get("cameras", []):
        if cam.get("name") == camera_name:
            return cam
    raise ValueError(
        f"Camera '{camera_name}' not found in scene. "
        f"Available: {[c.get('name') for c in project.get('cameras', [])]}"
    )


# ── Public API ───────────────────────────────────────────────────────────────


def create_camera(
    session,
    cam_type: str = "perspective",
    fov: float = 50.0,
    name: str = "Camera",
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Add a camera to the scene.

    Stores camera configuration in the session's scene JSON and returns a
    result dict containing both the camera metadata and the bpy script lines
    needed to create it in Blender.

    Args:
        session: Active Session object (holds the scene JSON project dict).
        cam_type: One of 'perspective', 'orthographic', 'panoramic'.
        fov: Vertical field-of-view in degrees (converted to focal length).
        name: Camera name.
        location: [x, y, z] world position (default [0, 0, 5]).
        rotation: [x, y, z] Euler rotation in degrees (default [0, 0, 0]).
        **kwargs: Extra camera properties forwarded into the JSON record
                  (e.g. clip_start, clip_end, sensor_width, dof_enabled,
                   dof_focus_distance, dof_aperture).

    Returns:
        Dict with keys 'camera' (JSON record) and 'script_lines' (list of str).
    """
    cam_type_lower = cam_type.lower()
    if cam_type_lower not in CAMERA_TYPES:
        raise ValueError(
            f"Invalid cam_type '{cam_type}'. Valid: {CAMERA_TYPES}"
        )
    if fov <= 0 or fov >= 180:
        raise ValueError(f"fov must be between 0 and 180 degrees, got {fov}")

    project = session.get_project()
    cam_name = _unique_camera_name(project, name)
    bpy_type = _BPY_CAM_TYPE[cam_type_lower]
    focal_length = _fov_to_lens(fov)

    loc = list(location) if location else [0.0, 0.0, 5.0]
    rot = list(rotation) if rotation else [0.0, 0.0, 0.0]

    cam_record = {
        "id": _next_camera_id(project),
        "name": cam_name,
        "type": bpy_type,
        "cam_type": cam_type_lower,
        "fov": fov,
        "focal_length": focal_length,
        "sensor_width": kwargs.get("sensor_width", _SENSOR_WIDTH_MM),
        "clip_start": kwargs.get("clip_start", 0.1),
        "clip_end": kwargs.get("clip_end", 1000.0),
        "location": loc,
        "rotation": rot,
        "is_active": kwargs.get("is_active", False),
        "dof_enabled": kwargs.get("dof_enabled", False),
        "dof_focus_distance": kwargs.get("dof_focus_distance", 10.0),
        "dof_aperture": kwargs.get("dof_aperture", 2.8),
        "animations": [],
    }

    if "cameras" not in project:
        project["cameras"] = []

    # First camera in scene becomes active automatically
    if not project["cameras"]:
        cam_record["is_active"] = True

    project["cameras"].append(cam_record)

    # Generate bpy script lines
    lines = [
        f"# Camera: {cam_name}",
        f"bpy.ops.object.camera_add(location=({loc[0]}, {loc[1]}, {loc[2]}))",
        "camera = bpy.context.active_object",
        f"camera.name = '{cam_name}'",
        f"camera.rotation_euler = ("
        f"math.radians({rot[0]}), math.radians({rot[1]}), math.radians({rot[2]}))",
        f"camera.data.type = '{bpy_type}'",
        f"camera.data.lens = {focal_length:.4f}",
        f"camera.data.sensor_width = {cam_record['sensor_width']}",
        f"camera.data.clip_start = {cam_record['clip_start']}",
        f"camera.data.clip_end = {cam_record['clip_end']}",
    ]

    if cam_record["dof_enabled"]:
        lines += [
            "camera.data.dof.use_dof = True",
            f"camera.data.dof.focus_distance = {cam_record['dof_focus_distance']}",
            f"camera.data.dof.aperture_fstop = {cam_record['dof_aperture']}",
        ]

    if cam_record["is_active"]:
        lines.append("bpy.context.scene.camera = camera")

    return {"camera": cam_record, "script_lines": lines}


def dolly(
    session,
    camera_name: str,
    start: List[float],
    end: List[float],
    duration: float,
    fps: int = 30,
    easing: str = "ease_in_out_cubic",
) -> List[str]:
    """Animate camera position from *start* to *end* over *duration* seconds.

    Stores animation metadata in the camera's JSON record and returns bpy
    script lines that insert location keyframes at every frame.

    Args:
        session: Active Session object.
        camera_name: Name of the camera to animate.
        start: [x, y, z] start position.
        end: [x, y, z] end position.
        duration: Animation duration in seconds.
        fps: Frames per second.
        easing: Easing function name (from motion_math).

    Returns:
        List of bpy script lines (str).
    """
    if len(start) != 3:
        raise ValueError(f"start must have 3 components, got {len(start)}")
    if len(end) != 3:
        raise ValueError(f"end must have 3 components, got {len(end)}")
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")

    project = session.get_project()
    cam = _find_camera(project, camera_name)

    ease_fn = get_easing(easing)
    total_frames = int(round(duration * fps))

    # Record animation metadata in JSON
    cam.setdefault("animations", []).append({
        "type": "dolly",
        "start": list(start),
        "end": list(end),
        "duration": duration,
        "fps": fps,
        "easing": easing,
    })

    lines = [
        f"# Dolly: {camera_name} {start} → {end} ({duration}s, {easing})",
        f"camera = bpy.data.objects.get('{camera_name}')",
        "if camera:",
    ]

    for frame_idx in range(total_frames + 1):
        t = frame_idx / total_frames if total_frames > 0 else 0.0
        alpha = ease_fn(t)
        x = start[0] + (end[0] - start[0]) * alpha
        y = start[1] + (end[1] - start[1]) * alpha
        z = start[2] + (end[2] - start[2]) * alpha
        frame_num = frame_idx + 1
        lines.append(f"    camera.location = ({x:.6f}, {y:.6f}, {z:.6f})")
        lines.append(f"    camera.keyframe_insert(data_path='location', frame={frame_num})")

    return lines


def orbit(
    session,
    camera_name: str,
    center: List[float],
    radius: float,
    start_angle: float,
    end_angle: float,
    duration: float,
    fps: int = 30,
    easing: str = "ease_in_out_sine",
) -> List[str]:
    """Orbit camera around *center* from *start_angle* to *end_angle*.

    The camera is kept at a constant height (z = center[2]) and always points
    toward *center*.  Angles are measured in degrees in the XY plane.

    Args:
        session: Active Session object.
        camera_name: Name of the camera to animate.
        center: [x, y, z] orbit pivot point.
        radius: Orbit radius (distance from center).
        start_angle: Starting angle in degrees (0 = +X axis).
        end_angle: Ending angle in degrees.
        duration: Animation duration in seconds.
        fps: Frames per second.
        easing: Easing function name.

    Returns:
        List of bpy script lines (str).
    """
    if len(center) != 3:
        raise ValueError(f"center must have 3 components, got {len(center)}")
    if radius <= 0:
        raise ValueError(f"radius must be positive, got {radius}")
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")

    project = session.get_project()
    cam = _find_camera(project, camera_name)

    ease_fn = get_easing(easing)
    total_frames = int(round(duration * fps))
    cx, cy, cz = center[0], center[1], center[2]

    cam.setdefault("animations", []).append({
        "type": "orbit",
        "center": list(center),
        "radius": radius,
        "start_angle": start_angle,
        "end_angle": end_angle,
        "duration": duration,
        "fps": fps,
        "easing": easing,
    })

    lines = [
        f"# Orbit: {camera_name} around {center} r={radius} "
        f"{start_angle}°→{end_angle}° ({duration}s, {easing})",
        f"camera = bpy.data.objects.get('{camera_name}')",
        "if camera:",
    ]

    for frame_idx in range(total_frames + 1):
        t = frame_idx / total_frames if total_frames > 0 else 0.0
        alpha = ease_fn(t)
        angle_deg = start_angle + (end_angle - start_angle) * alpha
        angle_rad = math.radians(angle_deg)
        x = cx + radius * math.cos(angle_rad)
        y = cy + radius * math.sin(angle_rad)
        z = cz

        # Camera looks at center: compute Euler rotation
        dx = cx - x
        dy = cy - y
        # atan2 gives yaw; camera in Blender looks down -Z in local space, so
        # rotation_z = atan2(dy, dx) + pi/2 to face center when yaw is applied
        rot_z = math.atan2(dy, dx) + math.pi / 2.0
        frame_num = frame_idx + 1
        lines.append(f"    camera.location = ({x:.6f}, {y:.6f}, {z:.6f})")
        lines.append(f"    camera.keyframe_insert(data_path='location', frame={frame_num})")
        lines.append(
            f"    camera.rotation_euler = (math.radians(90.0), 0.0, {rot_z:.6f})"
        )
        lines.append(
            f"    camera.keyframe_insert(data_path='rotation_euler', frame={frame_num})"
        )

    return lines


def pan(
    session,
    camera_name: str,
    start_target: List[float],
    end_target: List[float],
    duration: float,
    fps: int = 30,
    easing: str = "linear",
) -> List[str]:
    """Animate camera look-at target from *start_target* to *end_target*.

    The camera position stays fixed at its current location.  A constraint-free
    approach is used: the camera's rotation_euler is computed from the direction
    vector to the interpolated look-at point.

    Args:
        session: Active Session object.
        camera_name: Name of the camera to animate.
        start_target: [x, y, z] initial look-at point.
        end_target: [x, y, z] final look-at point.
        duration: Animation duration in seconds.
        fps: Frames per second.
        easing: Easing function name.

    Returns:
        List of bpy script lines (str).
    """
    if len(start_target) != 3:
        raise ValueError(f"start_target must have 3 components, got {len(start_target)}")
    if len(end_target) != 3:
        raise ValueError(f"end_target must have 3 components, got {len(end_target)}")
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")

    project = session.get_project()
    cam = _find_camera(project, camera_name)

    ease_fn = get_easing(easing)
    total_frames = int(round(duration * fps))
    cam_loc = cam.get("location", [0.0, 0.0, 5.0])

    cam.setdefault("animations", []).append({
        "type": "pan",
        "start_target": list(start_target),
        "end_target": list(end_target),
        "duration": duration,
        "fps": fps,
        "easing": easing,
    })

    lines = [
        f"# Pan: {camera_name} target {start_target} → {end_target} ({duration}s, {easing})",
        f"camera = bpy.data.objects.get('{camera_name}')",
        "if camera:",
    ]

    for frame_idx in range(total_frames + 1):
        t = frame_idx / total_frames if total_frames > 0 else 0.0
        alpha = ease_fn(t)
        tx = start_target[0] + (end_target[0] - start_target[0]) * alpha
        ty = start_target[1] + (end_target[1] - start_target[1]) * alpha
        tz = start_target[2] + (end_target[2] - start_target[2]) * alpha
        # Direction from camera to target
        dx = tx - cam_loc[0]
        dy = ty - cam_loc[1]
        dz = tz - cam_loc[2]
        dist_xy = math.sqrt(dx * dx + dy * dy)
        # pitch (X rotation): look down = positive pitch in Blender
        pitch = math.atan2(-dz, dist_xy) if dist_xy > 1e-9 else 0.0
        # yaw (Z rotation)
        yaw = math.atan2(dy, dx) + math.pi / 2.0
        frame_num = frame_idx + 1
        lines.append(
            f"    camera.rotation_euler = ({pitch:.6f}, 0.0, {yaw:.6f})"
        )
        lines.append(
            f"    camera.keyframe_insert(data_path='rotation_euler', frame={frame_num})"
        )

    return lines


def zoom(
    session,
    camera_name: str,
    start_fov: float,
    end_fov: float,
    duration: float,
    fps: int = 30,
    easing: str = "ease_out_quad",
) -> List[str]:
    """Animate camera field-of-view (lens focal length).

    Args:
        session: Active Session object.
        camera_name: Name of the camera to animate.
        start_fov: Starting vertical FOV in degrees.
        end_fov: Ending vertical FOV in degrees.
        duration: Animation duration in seconds.
        fps: Frames per second.
        easing: Easing function name.

    Returns:
        List of bpy script lines (str).
    """
    if start_fov <= 0 or start_fov >= 180:
        raise ValueError(f"start_fov must be between 0 and 180, got {start_fov}")
    if end_fov <= 0 or end_fov >= 180:
        raise ValueError(f"end_fov must be between 0 and 180, got {end_fov}")
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")

    project = session.get_project()
    cam = _find_camera(project, camera_name)

    ease_fn = get_easing(easing)
    total_frames = int(round(duration * fps))

    cam.setdefault("animations", []).append({
        "type": "zoom",
        "start_fov": start_fov,
        "end_fov": end_fov,
        "duration": duration,
        "fps": fps,
        "easing": easing,
    })

    lines = [
        f"# Zoom: {camera_name} FOV {start_fov}°→{end_fov}° ({duration}s, {easing})",
        f"camera = bpy.data.objects.get('{camera_name}')",
        "if camera:",
    ]

    for frame_idx in range(total_frames + 1):
        t = frame_idx / total_frames if total_frames > 0 else 0.0
        alpha = ease_fn(t)
        current_fov = start_fov + (end_fov - start_fov) * alpha
        lens = _fov_to_lens(current_fov)
        frame_num = frame_idx + 1
        lines.append(f"    camera.data.lens = {lens:.4f}")
        lines.append(
            f"    camera.data.keyframe_insert(data_path='lens', frame={frame_num})"
        )

    return lines


def rack_focus(
    session,
    camera_name: str,
    start_distance: float,
    end_distance: float,
    duration: float,
    fps: int = 30,
    easing: str = "ease_in_out_sine",
) -> List[str]:
    """Animate depth-of-field focus distance.

    Automatically enables DoF on the camera if it is not already enabled.

    Args:
        session: Active Session object.
        camera_name: Name of the camera to animate.
        start_distance: Starting focus distance in Blender units.
        end_distance: Ending focus distance in Blender units.
        duration: Animation duration in seconds.
        fps: Frames per second.
        easing: Easing function name.

    Returns:
        List of bpy script lines (str).
    """
    if start_distance <= 0:
        raise ValueError(f"start_distance must be positive, got {start_distance}")
    if end_distance <= 0:
        raise ValueError(f"end_distance must be positive, got {end_distance}")
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")

    project = session.get_project()
    cam = _find_camera(project, camera_name)

    ease_fn = get_easing(easing)
    total_frames = int(round(duration * fps))

    # Enable DoF in the JSON record
    cam["dof_enabled"] = True

    cam.setdefault("animations", []).append({
        "type": "rack_focus",
        "start_distance": start_distance,
        "end_distance": end_distance,
        "duration": duration,
        "fps": fps,
        "easing": easing,
    })

    lines = [
        f"# Rack focus: {camera_name} {start_distance}→{end_distance} units "
        f"({duration}s, {easing})",
        f"camera = bpy.data.objects.get('{camera_name}')",
        "if camera:",
        "    camera.data.dof.use_dof = True",
    ]

    for frame_idx in range(total_frames + 1):
        t = frame_idx / total_frames if total_frames > 0 else 0.0
        alpha = ease_fn(t)
        dist = start_distance + (end_distance - start_distance) * alpha
        frame_num = frame_idx + 1
        lines.append(f"    camera.data.dof.focus_distance = {dist:.6f}")
        lines.append(
            f"    camera.data.dof.keyframe_insert("
            f"data_path='focus_distance', frame={frame_num})"
        )

    return lines


def crane(
    session,
    camera_name: str,
    start_height: float,
    end_height: float,
    duration: float,
    fps: int = 30,
    easing: str = "ease_out_cubic",
) -> List[str]:
    """Animate camera height (Z position) — crane / jib move.

    X and Y positions are held at their current values; only Z is animated.

    Args:
        session: Active Session object.
        camera_name: Name of the camera to animate.
        start_height: Starting Z position in Blender units.
        end_height: Ending Z position in Blender units.
        duration: Animation duration in seconds.
        fps: Frames per second.
        easing: Easing function name.

    Returns:
        List of bpy script lines (str).
    """
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")

    project = session.get_project()
    cam = _find_camera(project, camera_name)

    ease_fn = get_easing(easing)
    total_frames = int(round(duration * fps))
    cam_loc = cam.get("location", [0.0, 0.0, 5.0])
    x, y = cam_loc[0], cam_loc[1]

    cam.setdefault("animations", []).append({
        "type": "crane",
        "start_height": start_height,
        "end_height": end_height,
        "duration": duration,
        "fps": fps,
        "easing": easing,
    })

    lines = [
        f"# Crane: {camera_name} height {start_height}→{end_height} "
        f"({duration}s, {easing})",
        f"camera = bpy.data.objects.get('{camera_name}')",
        "if camera:",
    ]

    for frame_idx in range(total_frames + 1):
        t = frame_idx / total_frames if total_frames > 0 else 0.0
        alpha = ease_fn(t)
        z = start_height + (end_height - start_height) * alpha
        frame_num = frame_idx + 1
        lines.append(f"    camera.location = ({x:.6f}, {y:.6f}, {z:.6f})")
        lines.append(f"    camera.keyframe_insert(data_path='location', frame={frame_num})")

    return lines


def follow_path(
    session,
    camera_name: str,
    points: List[List[float]],
    duration: float,
    fps: int = 30,
    easing: str = "linear",
) -> List[str]:
    """Animate camera along a bezier path defined by control points.

    The path is built as a Catmull-Rom spline through the given points.
    Each point is a [x, y, z] list; at least 2 points are required.

    Args:
        session: Active Session object.
        camera_name: Name of the camera to animate.
        points: List of [x, y, z] control points.
        duration: Animation duration in seconds.
        fps: Frames per second.
        easing: Easing function name (applied to overall path parameter t).

    Returns:
        List of bpy script lines (str).
    """
    if len(points) < 2:
        raise ValueError(f"At least 2 path points required, got {len(points)}")
    for i, p in enumerate(points):
        if len(p) != 3:
            raise ValueError(f"Point {i} must have 3 components, got {len(p)}")
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")

    project = session.get_project()
    cam = _find_camera(project, camera_name)

    ease_fn = get_easing(easing)
    total_frames = int(round(duration * fps))

    cam.setdefault("animations", []).append({
        "type": "follow_path",
        "points": [list(p) for p in points],
        "duration": duration,
        "fps": fps,
        "easing": easing,
    })

    lines = [
        f"# Follow path: {camera_name} {len(points)} points ({duration}s, {easing})",
        f"camera = bpy.data.objects.get('{camera_name}')",
        "if camera:",
    ]

    n_segments = len(points) - 1

    for frame_idx in range(total_frames + 1):
        t = frame_idx / total_frames if total_frames > 0 else 0.0
        alpha = ease_fn(t)
        # Map [0,1] alpha onto segment index and local t
        seg_float = alpha * n_segments
        seg_idx = min(int(seg_float), n_segments - 1)
        local_t = seg_float - seg_idx

        # Catmull-Rom: use 4 control points p0..p3
        p1 = points[seg_idx]
        p2 = points[seg_idx + 1]
        p0 = points[max(seg_idx - 1, 0)]
        p3 = points[min(seg_idx + 2, len(points) - 1)]

        x = _catmull_rom(p0[0], p1[0], p2[0], p3[0], local_t)
        y = _catmull_rom(p0[1], p1[1], p2[1], p3[1], local_t)
        z = _catmull_rom(p0[2], p1[2], p2[2], p3[2], local_t)

        frame_num = frame_idx + 1
        lines.append(f"    camera.location = ({x:.6f}, {y:.6f}, {z:.6f})")
        lines.append(f"    camera.keyframe_insert(data_path='location', frame={frame_num})")

    return lines


def shake(
    session,
    camera_name: str,
    intensity: float,
    frequency: float,
    decay: float,
    duration: float,
    fps: int = 30,
) -> List[str]:
    """Add procedural camera shake with exponential decay.

    Uses a deterministic pseudo-random offset per frame, decayed by an
    exponential envelope.  The result is layered on top of the camera's
    current position; existing location keyframes should be set before calling
    this.

    Args:
        session: Active Session object.
        camera_name: Name of the camera to animate.
        intensity: Peak shake amplitude in Blender units.
        frequency: Shake frequency in Hz (oscillations per second).
        decay: Exponential decay constant (higher = faster decay).
        duration: Animation duration in seconds.
        fps: Frames per second.

    Returns:
        List of bpy script lines (str).
    """
    if intensity < 0:
        raise ValueError(f"intensity must be non-negative, got {intensity}")
    if frequency <= 0:
        raise ValueError(f"frequency must be positive, got {frequency}")
    if decay < 0:
        raise ValueError(f"decay must be non-negative, got {decay}")
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")

    project = session.get_project()
    cam = _find_camera(project, camera_name)

    total_frames = int(round(duration * fps))
    cam_loc = cam.get("location", [0.0, 0.0, 5.0])

    cam.setdefault("animations", []).append({
        "type": "shake",
        "intensity": intensity,
        "frequency": frequency,
        "decay": decay,
        "duration": duration,
        "fps": fps,
    })

    lines = [
        f"# Shake: {camera_name} intensity={intensity} freq={frequency}Hz "
        f"decay={decay} ({duration}s)",
        f"camera = bpy.data.objects.get('{camera_name}')",
        "if camera:",
    ]

    # Use deterministic pseudo-random offsets seeded per camera name
    seed = sum(ord(c) for c in camera_name)
    for frame_idx in range(total_frames + 1):
        t = frame_idx / fps
        envelope = intensity * math.exp(-decay * t)
        # Pseudo-random phase offsets using sin/cos combinations
        noise_x = math.sin(frequency * 2 * math.pi * t + seed * 0.1) * math.sin(
            frequency * 3.7 * math.pi * t + seed * 0.3
        )
        noise_y = math.cos(frequency * 2 * math.pi * t + seed * 0.2) * math.cos(
            frequency * 2.9 * math.pi * t + seed * 0.5
        )
        noise_z = math.sin(frequency * 1.3 * math.pi * t + seed * 0.7) * 0.3

        x = cam_loc[0] + envelope * noise_x
        y = cam_loc[1] + envelope * noise_y
        z = cam_loc[2] + envelope * noise_z
        frame_num = frame_idx + 1
        lines.append(f"    camera.location = ({x:.6f}, {y:.6f}, {z:.6f})")
        lines.append(f"    camera.keyframe_insert(data_path='location', frame={frame_num})")

    return lines


# ── Internal helpers ─────────────────────────────────────────────────────────


def _catmull_rom(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    """Evaluate a Catmull-Rom spline segment at parameter t ∈ [0, 1]."""
    return 0.5 * (
        (2 * p1)
        + (-p0 + p2) * t
        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
        + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t
    )
