"""Blender CLI - Per-character 3D text animation system.

Generates bpy Python script strings for per-character font object creation and
8 animation presets (typewriter, wave, cascade, bounce, scale_pop, spiral_in,
extrude_in, rotate_3d).

Each character is an independent bpy.ops.object.text_add object so it can be
individually positioned, rotated, scaled, and extruded.

Relies on shared/motion_math for CharacterAnimator decomposition and stagger
timing, then translates resulting KeyframeTracks into bpy keyframe_insert calls.
"""

import math
import sys
import os
from typing import Any, Dict, List, Optional

# text_3d.py lives at: blender/agent-harness/cli_anything/blender/core/text_3d.py
# shared/  lives at:  <project-root>/shared/
# 5 levels of ".." bring us from core/ to the project root.
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "shared"),
)
from motion_math.easing import get_easing
from motion_math.text_animator import CharacterAnimator, CharInfo
from motion_math.keyframes import KeyframeTrack


# ── Internal helpers ──────────────────────────────────────────────────────────


def _get_project(session) -> Dict[str, Any]:
    return session.get_project()


def _char_obj_name(name_prefix: str, index: int) -> str:
    """Return the bpy object name for a character at *index*."""
    return f"{name_prefix}_{index:03d}"


def _script_header(text: str, font_path: Optional[str], size: float,
                   extrude: float, name_prefix: str) -> List[str]:
    """Return common preamble lines for any text_3d script."""
    lines = [
        f"# Per-character 3D text: {text!r}",
        "import bpy",
        "import math",
    ]
    if font_path:
        lines.append(f"_font_path = {font_path!r}")
    else:
        lines.append("_font_path = None")
    lines += [
        f"_name_prefix = {name_prefix!r}",
        f"_size = {size}",
        f"_extrude = {extrude}",
        "",
    ]
    return lines


def _create_char_lines(
    char: str,
    name: str,
    x: float,
    y: float,
    z: float,
    size: float,
    extrude: float,
    font_path: Optional[str],
) -> List[str]:
    """Return bpy lines that create a single character text object."""
    safe_char = char.replace("'", "\\'").replace("\\", "\\\\")
    lines = [
        f"# Character: {safe_char!r}  name={name!r}",
        f"bpy.ops.object.text_add(location=({x:.6f}, {y:.6f}, {z:.6f}))",
        f"obj_{name} = bpy.context.active_object",
        f"obj_{name}.name = {name!r}",
        f"obj_{name}.data.body = {char!r}",
        f"obj_{name}.data.size = {size}",
        f"obj_{name}.data.extrude = {extrude}",
        f"obj_{name}.data.align_x = 'CENTER'",
    ]
    if font_path:
        lines += [
            f"_fnt = bpy.data.fonts.load({font_path!r})",
            f"obj_{name}.data.font = _fnt",
        ]
    return lines


# ── Public API ────────────────────────────────────────────────────────────────


def explode_text(
    session,
    text: str,
    font_path: Optional[str] = None,
    size: float = 1.0,
    extrude: float = 0.0,
    name_prefix: str = "char",
    char_spacing: float = 1.0,
) -> Dict[str, Any]:
    """Create individual text objects per character.

    Each non-newline character in *text* becomes its own bpy FONT object
    placed at an x-offset derived from its position in the string.  Objects
    are named ``{name_prefix}_{index:03d}`` so they are easy to retrieve.

    Args:
        session:      Active Session object.
        text:         Source string (newlines increment the y position).
        font_path:    Optional path to a .ttf font file.
        size:         Font size in Blender units.
        extrude:      Extrusion depth (0 = flat).
        name_prefix:  Prefix for generated object names.
        char_spacing: Horizontal spacing multiplier per character (default 1.0).

    Returns:
        Dict with keys:
          ``chars``        — list of char metadata dicts
          ``script_lines`` — bpy script lines to create all objects
    """
    if not text:
        raise ValueError("text must not be empty")
    if size <= 0:
        raise ValueError(f"size must be positive, got {size}")

    project = _get_project(session)

    chars_info = CharacterAnimator.decompose(text, char_width=char_spacing)

    lines = _script_header(text, font_path, size, extrude, name_prefix)

    char_records = []
    for ci in chars_info:
        name = _char_obj_name(name_prefix, ci.index)
        x = ci.x_offset
        y = -ci.line * size * 1.2  # line spacing = 1.2× size
        z = 0.0
        lines += _create_char_lines(ci.char, name, x, y, z, size, extrude, font_path)
        char_records.append({
            "name": name,
            "char": ci.char,
            "index": ci.index,
            "position": [x, y, z],
            "line": ci.line,
        })

    # Store in project JSON
    if "text3d_objects" not in project:
        project["text3d_objects"] = []
    project["text3d_objects"].append({
        "text": text,
        "name_prefix": name_prefix,
        "chars": char_records,
    })

    return {"chars": char_records, "script_lines": lines}


# ── Animation presets ─────────────────────────────────────────────────────────


def animate_typewriter(
    session,
    text: str,
    speed: float = 0.05,
    fps: int = 30,
    name_prefix: str = "char",
) -> List[str]:
    """Typewriter effect: characters appear one by one (scale 0 → 1).

    Each character starts invisible (scale 0) and instantly scales to 1 at
    its stagger frame, giving a sharp typewriter pop-in effect.

    Args:
        session:     Active Session object.
        text:        Source string matching a previously exploded text.
        speed:       Time between successive character appearances (seconds).
        fps:         Frames per second.
        name_prefix: Object name prefix used in explode_text.

    Returns:
        List of bpy script lines.
    """
    chars = CharacterAnimator.decompose(text)
    if not chars:
        return []

    base = KeyframeTrack()
    base.add(0.0, 0.0, "linear")
    base.add(speed, 1.0, "linear")

    tracks = CharacterAnimator.stagger(chars, base, delay_per_char=speed,
                                       order="left_to_right")

    lines = [f"# Typewriter animation: {text!r} speed={speed}s fps={fps}"]
    total_frames = int(round((len(chars) * speed + speed) * fps)) + 1

    for ci in chars:
        name = _char_obj_name(name_prefix, ci.index)
        obj_var = f"obj_{name}"
        lines += [
            f"{obj_var} = bpy.data.objects.get({name!r})",
            f"if {obj_var}:",
        ]
        track = tracks.get(ci.index)
        if track is None:
            continue
        for frame_idx in range(total_frames):
            t = frame_idx / fps
            val = track.evaluate(t)
            val = max(0.0, min(1.0, val))
            frame_num = frame_idx + 1
            lines.append(
                f"    {obj_var}.scale = ({val:.6f}, {val:.6f}, {val:.6f})"
            )
            lines.append(
                f"    {obj_var}.keyframe_insert(data_path='scale', frame={frame_num})"
            )

    return lines


def animate_wave(
    session,
    text: str,
    amplitude: float = 0.5,
    frequency: float = 2.0,
    duration: float = 2.0,
    fps: int = 30,
    name_prefix: str = "char",
) -> List[str]:
    """Sine vertical offset wave: characters oscillate up and down.

    Each character's phase is offset by its index so they form a travelling
    wave rather than all moving in sync.

    Args:
        session:     Active Session object.
        text:        Source string.
        amplitude:   Peak vertical offset in Blender units.
        frequency:   Wave frequency in Hz.
        duration:    Total animation duration in seconds.
        fps:         Frames per second.
        name_prefix: Object name prefix.

    Returns:
        List of bpy script lines.
    """
    chars = CharacterAnimator.decompose(text)
    if not chars:
        return []

    n = len(chars)
    phase_per_unit = 2.0 * math.pi * frequency / max(n, 1)
    total_frames = int(round(duration * fps)) + 1

    lines = [
        f"# Wave animation: {text!r} amp={amplitude} freq={frequency}Hz "
        f"dur={duration}s fps={fps}",
    ]

    for ci in chars:
        name = _char_obj_name(name_prefix, ci.index)
        obj_var = f"obj_{name}"
        phase_offset = ci.index * phase_per_unit
        lines += [
            f"{obj_var} = bpy.data.objects.get({name!r})",
            f"if {obj_var}:",
        ]
        for frame_idx in range(total_frames):
            t = frame_idx / fps
            y_off = amplitude * math.sin(2.0 * math.pi * frequency * t + phase_offset)
            frame_num = frame_idx + 1
            # We only animate the Z offset (vertical in 3D view)
            lines.append(
                f"    {obj_var}.location.z = {y_off:.6f}"
            )
            lines.append(
                f"    {obj_var}.keyframe_insert(data_path='location', index=2, frame={frame_num})"
            )

    return lines


def animate_cascade(
    session,
    text: str,
    duration: float = 0.3,
    delay: float = 0.05,
    direction: str = "left",
    fps: int = 30,
    name_prefix: str = "char",
) -> List[str]:
    """Slide + scale cascade in.

    Characters slide in from the side and scale from 0 to 1 with ease_out_cubic.

    Args:
        session:     Active Session object.
        text:        Source string.
        duration:    Per-character animation duration in seconds.
        delay:       Stagger delay between characters in seconds.
        direction:   Slide-in direction — 'left', 'right', 'top', 'bottom'.
        fps:         Frames per second.
        name_prefix: Object name prefix.

    Returns:
        List of bpy script lines.
    """
    valid_dirs = {"left", "right", "top", "bottom"}
    if direction not in valid_dirs:
        raise ValueError(f"direction must be one of {sorted(valid_dirs)}, got {direction!r}")

    chars = CharacterAnimator.decompose(text)
    if not chars:
        return []

    ease_fn = get_easing("ease_out_cubic")

    # Slide offsets: (dx, dy, dz) at t=0 → 0 at t=1
    slide_map = {
        "left":   (-2.0, 0.0, 0.0),
        "right":  (2.0,  0.0, 0.0),
        "top":    (0.0,  0.0, 2.0),
        "bottom": (0.0,  0.0, -2.0),
    }
    dx0, dy0, dz0 = slide_map[direction]

    total_anim_time = len(chars) * delay + duration
    total_frames = int(round(total_anim_time * fps)) + 1

    lines = [
        f"# Cascade animation: {text!r} dir={direction} dur={duration}s "
        f"delay={delay}s fps={fps}",
    ]

    for ci in chars:
        name = _char_obj_name(name_prefix, ci.index)
        obj_var = f"obj_{name}"
        start_time = ci.index * delay
        lines += [
            f"{obj_var} = bpy.data.objects.get({name!r})",
            f"if {obj_var}:",
        ]
        for frame_idx in range(total_frames):
            t = frame_idx / fps
            # local t within this character's animation window
            local_t = (t - start_time) / duration if duration > 0 else 1.0
            local_t = max(0.0, min(1.0, local_t))
            alpha = ease_fn(local_t)

            dx = dx0 * (1.0 - alpha)
            dy = dy0 * (1.0 - alpha)
            dz = dz0 * (1.0 - alpha)
            scale = alpha

            frame_num = frame_idx + 1
            lines.append(
                f"    {obj_var}.location.x = {ci.x_offset:.6f} + {dx:.6f}"
            )
            lines.append(
                f"    {obj_var}.location.z = {dz:.6f}"
            )
            lines.append(
                f"    {obj_var}.scale = ({scale:.6f}, {scale:.6f}, {scale:.6f})"
            )
            lines.append(
                f"    {obj_var}.keyframe_insert(data_path='location', frame={frame_num})"
            )
            lines.append(
                f"    {obj_var}.keyframe_insert(data_path='scale', frame={frame_num})"
            )

    return lines


def animate_bounce(
    session,
    text: str,
    duration: float = 0.6,
    delay: float = 0.04,
    fps: int = 30,
    name_prefix: str = "char",
) -> List[str]:
    """Drop with bounce easing.

    Each character drops from above and bounces into place using ease_out_bounce.

    Args:
        session:     Active Session object.
        text:        Source string.
        duration:    Per-character animation duration in seconds.
        delay:       Stagger delay between characters.
        fps:         Frames per second.
        name_prefix: Object name prefix.

    Returns:
        List of bpy script lines.
    """
    chars = CharacterAnimator.decompose(text)
    if not chars:
        return []

    ease_fn = get_easing("ease_out_bounce")
    drop_height = 3.0  # Blender units above final position

    total_anim_time = len(chars) * delay + duration
    total_frames = int(round(total_anim_time * fps)) + 1

    lines = [
        f"# Bounce animation: {text!r} dur={duration}s delay={delay}s fps={fps}",
    ]

    for ci in chars:
        name = _char_obj_name(name_prefix, ci.index)
        obj_var = f"obj_{name}"
        start_time = ci.index * delay
        lines += [
            f"{obj_var} = bpy.data.objects.get({name!r})",
            f"if {obj_var}:",
        ]
        for frame_idx in range(total_frames):
            t = frame_idx / fps
            local_t = (t - start_time) / duration if duration > 0 else 1.0
            local_t = max(0.0, min(1.0, local_t))
            alpha = ease_fn(local_t)
            z_off = drop_height * (1.0 - alpha)
            frame_num = frame_idx + 1
            lines.append(f"    {obj_var}.location.z = {z_off:.6f}")
            lines.append(
                f"    {obj_var}.keyframe_insert(data_path='location', index=2, frame={frame_num})"
            )

    return lines


def animate_scale_pop(
    session,
    text: str,
    duration: float = 0.4,
    delay: float = 0.05,
    fps: int = 30,
    name_prefix: str = "char",
) -> List[str]:
    """Scale with overshoot (ease_out_back).

    Each character pops in from scale 0 to 1 with a momentary overshoot above 1.

    Args:
        session:     Active Session object.
        text:        Source string.
        duration:    Per-character animation duration in seconds.
        delay:       Stagger delay between characters.
        fps:         Frames per second.
        name_prefix: Object name prefix.

    Returns:
        List of bpy script lines.
    """
    chars = CharacterAnimator.decompose(text)
    if not chars:
        return []

    ease_fn = get_easing("ease_out_back")

    total_anim_time = len(chars) * delay + duration
    total_frames = int(round(total_anim_time * fps)) + 1

    lines = [
        f"# Scale-pop animation: {text!r} dur={duration}s delay={delay}s fps={fps}",
    ]

    for ci in chars:
        name = _char_obj_name(name_prefix, ci.index)
        obj_var = f"obj_{name}"
        start_time = ci.index * delay
        lines += [
            f"{obj_var} = bpy.data.objects.get({name!r})",
            f"if {obj_var}:",
        ]
        for frame_idx in range(total_frames):
            t = frame_idx / fps
            local_t = (t - start_time) / duration if duration > 0 else 1.0
            local_t = max(0.0, min(1.0, local_t))
            scale = ease_fn(local_t)
            # Don't clamp below 0 during overshoot
            frame_num = frame_idx + 1
            lines.append(
                f"    {obj_var}.scale = ({scale:.6f}, {scale:.6f}, {scale:.6f})"
            )
            lines.append(
                f"    {obj_var}.keyframe_insert(data_path='scale', frame={frame_num})"
            )

    return lines


def animate_spiral_in(
    session,
    text: str,
    radius: float = 3.0,
    rotations: float = 1.0,
    duration: float = 1.0,
    delay: float = 0.06,
    fps: int = 30,
    name_prefix: str = "char",
) -> List[str]:
    """Characters spiral in from a circular orbit to their final position.

    Each character starts at *radius* distance from its landing position,
    rotating *rotations* full turns as it moves inward.

    Args:
        session:     Active Session object.
        text:        Source string.
        radius:      Starting orbit radius in Blender units.
        rotations:   Number of full rotations during the spiral.
        duration:    Per-character animation duration in seconds.
        delay:       Stagger delay between characters.
        fps:         Frames per second.
        name_prefix: Object name prefix.

    Returns:
        List of bpy script lines.
    """
    chars = CharacterAnimator.decompose(text)
    if not chars:
        return []

    ease_fn = get_easing("ease_in_out_cubic")
    total_anim_time = len(chars) * delay + duration
    total_frames = int(round(total_anim_time * fps)) + 1

    lines = [
        f"# Spiral-in animation: {text!r} r={radius} rot={rotations} "
        f"dur={duration}s delay={delay}s fps={fps}",
    ]

    for ci in chars:
        name = _char_obj_name(name_prefix, ci.index)
        obj_var = f"obj_{name}"
        start_time = ci.index * delay
        # Starting angle differs per character so they don't all clump
        start_angle = (ci.index / max(len(chars), 1)) * 2.0 * math.pi
        lines += [
            f"{obj_var} = bpy.data.objects.get({name!r})",
            f"if {obj_var}:",
        ]
        for frame_idx in range(total_frames):
            t = frame_idx / fps
            local_t = (t - start_time) / duration if duration > 0 else 1.0
            local_t = max(0.0, min(1.0, local_t))
            alpha = ease_fn(local_t)

            # Radius shrinks from *radius* to 0
            r = radius * (1.0 - alpha)
            angle = start_angle + rotations * 2.0 * math.pi * local_t
            dx = r * math.cos(angle)
            dz = r * math.sin(angle)
            rot_z = -angle  # rotate the character to face forward

            frame_num = frame_idx + 1
            lines.append(
                f"    {obj_var}.location.x = {ci.x_offset:.6f} + {dx:.6f}"
            )
            lines.append(
                f"    {obj_var}.location.z = {dz:.6f}"
            )
            lines.append(
                f"    {obj_var}.rotation_euler[2] = {rot_z:.6f}"
            )
            lines.append(
                f"    {obj_var}.keyframe_insert(data_path='location', frame={frame_num})"
            )
            lines.append(
                f"    {obj_var}.keyframe_insert(data_path='rotation_euler', frame={frame_num})"
            )

    return lines


def animate_extrude_in(
    session,
    text: str,
    max_depth: float = 0.3,
    duration: float = 0.5,
    delay: float = 0.04,
    fps: int = 30,
    name_prefix: str = "char",
) -> List[str]:
    """Characters grow from flat (extrude=0) to *max_depth*.

    Animates the ``data.extrude`` property of each character object using
    ease_out_cubic easing.

    Args:
        session:     Active Session object.
        text:        Source string.
        max_depth:   Final extrusion depth.
        duration:    Per-character animation duration in seconds.
        delay:       Stagger delay between characters.
        fps:         Frames per second.
        name_prefix: Object name prefix.

    Returns:
        List of bpy script lines.
    """
    chars = CharacterAnimator.decompose(text)
    if not chars:
        return []

    ease_fn = get_easing("ease_out_cubic")
    total_anim_time = len(chars) * delay + duration
    total_frames = int(round(total_anim_time * fps)) + 1

    lines = [
        f"# Extrude-in animation: {text!r} max_depth={max_depth} "
        f"dur={duration}s delay={delay}s fps={fps}",
    ]

    for ci in chars:
        name = _char_obj_name(name_prefix, ci.index)
        obj_var = f"obj_{name}"
        start_time = ci.index * delay
        lines += [
            f"{obj_var} = bpy.data.objects.get({name!r})",
            f"if {obj_var}:",
        ]
        for frame_idx in range(total_frames):
            t = frame_idx / fps
            local_t = (t - start_time) / duration if duration > 0 else 1.0
            local_t = max(0.0, min(1.0, local_t))
            depth = max_depth * ease_fn(local_t)
            frame_num = frame_idx + 1
            lines.append(f"    {obj_var}.data.extrude = {depth:.6f}")
            lines.append(
                f"    {obj_var}.data.keyframe_insert(data_path='extrude', frame={frame_num})"
            )

    return lines


def animate_rotate_3d(
    session,
    text: str,
    axis: str = "x",
    angle: float = 360.0,
    duration: float = 0.5,
    delay: float = 0.05,
    fps: int = 30,
    name_prefix: str = "char",
) -> List[str]:
    """Characters flip/rotate in 3D around a specified axis.

    Each character rotates from *angle* degrees to 0 (i.e. it spins to its
    rest orientation) using ease_out_back for a snappy feel.

    Args:
        session:     Active Session object.
        text:        Source string.
        axis:        Rotation axis — 'x', 'y', or 'z'.
        angle:       Starting rotation in degrees (counts down to 0).
        duration:    Per-character animation duration in seconds.
        delay:       Stagger delay between characters.
        fps:         Frames per second.
        name_prefix: Object name prefix.

    Returns:
        List of bpy script lines.
    """
    axis_lower = axis.lower()
    axis_map = {"x": 0, "y": 1, "z": 2}
    if axis_lower not in axis_map:
        raise ValueError(f"axis must be 'x', 'y', or 'z', got {axis!r}")

    axis_idx = axis_map[axis_lower]
    chars = CharacterAnimator.decompose(text)
    if not chars:
        return []

    ease_fn = get_easing("ease_out_back")
    start_rad = math.radians(angle)
    total_anim_time = len(chars) * delay + duration
    total_frames = int(round(total_anim_time * fps)) + 1

    lines = [
        f"# Rotate-3D animation: {text!r} axis={axis} angle={angle}deg "
        f"dur={duration}s delay={delay}s fps={fps}",
    ]

    for ci in chars:
        name = _char_obj_name(name_prefix, ci.index)
        obj_var = f"obj_{name}"
        start_time = ci.index * delay
        lines += [
            f"{obj_var} = bpy.data.objects.get({name!r})",
            f"if {obj_var}:",
        ]
        for frame_idx in range(total_frames):
            t = frame_idx / fps
            local_t = (t - start_time) / duration if duration > 0 else 1.0
            local_t = max(0.0, min(1.0, local_t))
            alpha = ease_fn(local_t)
            rot = start_rad * (1.0 - alpha)  # from start_rad → 0
            frame_num = frame_idx + 1
            lines.append(
                f"    {obj_var}.rotation_euler[{axis_idx}] = {rot:.6f}"
            )
            lines.append(
                f"    {obj_var}.keyframe_insert(data_path='rotation_euler', "
                f"index={axis_idx}, frame={frame_num})"
            )

    return lines
