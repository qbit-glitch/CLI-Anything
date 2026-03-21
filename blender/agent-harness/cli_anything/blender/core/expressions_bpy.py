"""Blender CLI - Expression-driven property animation via baked keyframes.

Translates the shared Expression/wiggle syntax into bpy keyframe_insert calls
baked at every frame so the animation can be rendered without Blender drivers.

Supported workflows:
- apply_expression  — arbitrary safe expression e.g. "time * 360"
- apply_wiggle      — convenience wrapper for wiggle(freq, amp) expressions
- apply_procedural  — synonym for apply_expression with metadata tagging

Each function returns a list of bpy script lines that can be assembled by
bpy_gen.py into a complete Blender Python script.
"""

import math
import sys
import os
from typing import Any, Dict, List, Optional

# expressions_bpy.py lives at: blender/agent-harness/cli_anything/blender/core/
# shared/ lives at:            <project-root>/shared/
# 5 levels of ".." bring us from core/ to the project root.
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "shared"),
)
from motion_math.expressions import Expression


# ── Internal helpers ──────────────────────────────────────────────────────────


def _get_project(session) -> Dict[str, Any]:
    return session.get_project()


def _sanitize_var(name: str) -> str:
    """Convert an object name to a safe Python variable suffix."""
    return "".join(c if c.isalnum() else "_" for c in name)


def _bake_expression(
    expr: Expression,
    object_name: str,
    property_path: str,
    total_frames: int,
    fps: int,
    index: Optional[int] = None,
) -> List[str]:
    """Generate per-frame keyframe_insert lines for *expr*.

    Args:
        expr:          Compiled Expression object.
        object_name:   Blender object name.
        property_path: bpy data_path string, e.g. 'location' or 'rotation_euler'.
        total_frames:  Total number of frames to bake.
        fps:           Frames per second.
        index:         Optional array index (e.g. 0=X, 1=Y, 2=Z).

    Returns:
        List of bpy script lines.
    """
    var = _sanitize_var(object_name)
    idx_suffix = f", index={index}" if index is not None else ""
    idx_assign = f"[{index}]" if index is not None else ""

    lines = [
        f"_obj_{var} = bpy.data.objects.get({object_name!r})",
        f"if _obj_{var}:",
    ]

    for frame_idx in range(total_frames + 1):
        t = frame_idx / fps
        frame = frame_idx + 1
        value = expr.evaluate(time=t, frame=frame_idx, fps=float(fps))
        lines.append(f"    _obj_{var}.{property_path}{idx_assign} = {value:.8f}")
        lines.append(
            f"    _obj_{var}.keyframe_insert("
            f"data_path={property_path!r}{idx_suffix}, frame={frame})"
        )

    return lines


# ── Public API ────────────────────────────────────────────────────────────────


def apply_expression(
    session,
    object_name: str,
    property_path: str,
    expression_str: str,
    duration: float,
    fps: int = 30,
    index: Optional[int] = None,
) -> List[str]:
    """Generate bpy script that bakes an expression to per-frame keyframes.

    For simple expressions like "time * 360" or "sin(time * 2) * 0.5":
    evaluates the expression at every frame using the shared Expression class
    and emits keyframe_insert calls.

    Args:
        session:         Active Session object.
        object_name:     Name of the Blender object to animate.
        property_path:   bpy data_path, e.g. ``'rotation_euler'``, ``'location'``.
        expression_str:  Safe expression string (see shared/motion_math/expressions.py).
        duration:        Animation duration in seconds.
        fps:             Frames per second.
        index:           Optional component index (0=X, 1=Y, 2=Z).

    Returns:
        List of bpy script lines.

    Raises:
        ValueError: If expression_str is invalid.
    """
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")

    expr = Expression(expression_str)  # validates and compiles
    total_frames = int(round(duration * fps))

    project = _get_project(session)
    # Record in project JSON
    project.setdefault("expressions", []).append({
        "type": "expression",
        "object": object_name,
        "property_path": property_path,
        "expression": expression_str,
        "duration": duration,
        "fps": fps,
        "index": index,
    })

    lines = [
        f"# Expression bake: {object_name!r} {property_path!r} = {expression_str!r} "
        f"({duration}s @ {fps}fps)",
        "import bpy",
        "import math",
    ]
    lines += _bake_expression(expr, object_name, property_path, total_frames, fps, index)
    return lines


def apply_wiggle(
    session,
    object_name: str,
    property_path: str,
    frequency: float,
    amplitude: float,
    duration: float,
    fps: int = 30,
    index: Optional[int] = None,
) -> List[str]:
    """Procedural wiggle noise on a property using shared wiggle() function.

    Convenience wrapper that builds the expression ``"wiggle(freq, amp)"``
    and bakes it to keyframes.

    Args:
        session:       Active Session object.
        object_name:   Blender object name.
        property_path: bpy data_path string.
        frequency:     Wiggle frequency in Hz.
        amplitude:     Wiggle amplitude (peak deviation from 0).
        duration:      Animation duration in seconds.
        fps:           Frames per second.
        index:         Optional component index.

    Returns:
        List of bpy script lines.
    """
    if frequency <= 0:
        raise ValueError(f"frequency must be positive, got {frequency}")
    if amplitude < 0:
        raise ValueError(f"amplitude must be non-negative, got {amplitude}")

    expression_str = f"wiggle({frequency}, {amplitude})"

    project = _get_project(session)
    project.setdefault("expressions", []).append({
        "type": "wiggle",
        "object": object_name,
        "property_path": property_path,
        "frequency": frequency,
        "amplitude": amplitude,
        "duration": duration,
        "fps": fps,
        "index": index,
    })

    expr = Expression(expression_str)
    total_frames = int(round(duration * fps))

    lines = [
        f"# Wiggle bake: {object_name!r} {property_path!r} "
        f"freq={frequency} amp={amplitude} ({duration}s @ {fps}fps)",
        "import bpy",
        "import math",
    ]
    lines += _bake_expression(expr, object_name, property_path, total_frames, fps, index)
    return lines


def apply_procedural(
    session,
    object_name: str,
    property_path: str,
    expression: str,
    duration: float,
    fps: int = 30,
    index: Optional[int] = None,
) -> List[str]:
    """Alias for apply_expression tagged as 'procedural' in the project JSON.

    Intended for expressions that describe a fully procedural motion (no
    start/end targets), such as looping rotations or oscillating positions.

    Args:
        session:       Active Session object.
        object_name:   Blender object name.
        property_path: bpy data_path string.
        expression:    Safe expression string.
        duration:      Animation duration in seconds.
        fps:           Frames per second.
        index:         Optional component index.

    Returns:
        List of bpy script lines.
    """
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")

    expr_obj = Expression(expression)
    total_frames = int(round(duration * fps))

    project = _get_project(session)
    project.setdefault("expressions", []).append({
        "type": "procedural",
        "object": object_name,
        "property_path": property_path,
        "expression": expression,
        "duration": duration,
        "fps": fps,
        "index": index,
    })

    lines = [
        f"# Procedural bake: {object_name!r} {property_path!r} = {expression!r} "
        f"({duration}s @ {fps}fps)",
        "import bpy",
        "import math",
    ]
    lines += _bake_expression(expr_obj, object_name, property_path, total_frames, fps, index)
    return lines
