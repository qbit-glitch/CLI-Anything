"""GIMP CLI - Frame sequence generation module.

This module provides keyframe-based animation support for batch-rendering
image sequences with interpolated parameter changes, suitable for video
production workflows.

Animatable properties:
  - Layer properties (filter_index=-1): opacity, offset_x, offset_y
  - Filter parameters (filter_index>=0): any numeric param from the filter registry
"""

import os
import copy
import math
import sys
from typing import Dict, Any, List, Optional

# ---------------------------------------------------------------------------
# Shared motion_math easings — injected at runtime via sys.path
# ---------------------------------------------------------------------------

def _load_shared_easings():
    """Try to import EASING_FUNCTIONS from shared/motion_math."""
    candidates = []
    # Walk up from this file looking for shared/motion_math
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        candidate = os.path.join(here, "shared", "motion_math")
        candidates.append(candidate)
        here = os.path.dirname(here)
    for path in candidates:
        if os.path.isdir(path):
            parent = os.path.dirname(path)
            if parent not in sys.path:
                sys.path.insert(0, parent)
            try:
                from motion_math.easing import EASING_FUNCTIONS, get_easing
                return EASING_FUNCTIONS, get_easing
            except ImportError:
                pass
    return None, None


_SHARED_EASING_FUNCTIONS, _shared_get_easing = _load_shared_easings()

# Legacy 5-type list preserved for backward compatibility with add_animation_keyframe validation.
# Extended types (30+ Penner easings) are also accepted when shared module is available.
INTERPOLATION_TYPES = ["LINEAR", "CONSTANT", "EASE_IN", "EASE_OUT", "EASE_IN_OUT"]

# Full set of accepted interpolation names (legacy + shared)
def _all_interpolation_types() -> list:
    """Return the complete list of valid interpolation type names."""
    types = list(INTERPOLATION_TYPES)
    if _SHARED_EASING_FUNCTIONS:
        for k in _SHARED_EASING_FUNCTIONS:
            upper = k.upper()
            if upper not in types:
                types.append(upper)
            if k not in types:
                types.append(k)
    return types

# Layer properties that can be keyframed (filter_index == -1)
_LAYER_PROPERTIES = {"opacity", "offset_x", "offset_y"}


def set_animation_settings(project: dict, frame_count: int = 30, fps: int = 24) -> dict:
    """Store animation settings in the project.

    Args:
        project: The project dict.
        frame_count: Total number of frames in the sequence.
        fps: Frames per second (metadata for downstream tools).

    Returns:
        The settings dict stored in project["animation"]["settings"].
    """
    if frame_count < 1:
        raise ValueError(f"frame_count must be >= 1, got {frame_count}")
    if fps < 1:
        raise ValueError(f"fps must be >= 1, got {fps}")

    if "animation" not in project:
        project["animation"] = {"settings": {}, "keyframes": []}

    settings = {
        "frame_count": frame_count,
        "fps": fps,
        "duration": frame_count / fps,
    }
    project["animation"]["settings"] = settings
    return settings


def get_animation_settings(project: dict) -> dict:
    """Get animation settings, returning defaults if not set.

    Returns:
        A dict with frame_count, fps, and duration.
    """
    defaults = {"frame_count": 30, "fps": 24, "duration": 30 / 24}
    anim = project.get("animation", {})
    settings = anim.get("settings", {})
    return {
        "frame_count": settings.get("frame_count", defaults["frame_count"]),
        "fps": settings.get("fps", defaults["fps"]),
        "duration": settings.get("duration", defaults["duration"]),
    }


def add_animation_keyframe(
    project: dict,
    frame: int,
    layer_index: int,
    param: str,
    value,
    filter_index: int = -1,
    interpolation: str = "LINEAR",
) -> dict:
    """Add a keyframe for frame sequence generation.

    Args:
        project: The project dict.
        frame: Frame number (0-based).
        layer_index: Index of the target layer.
        param: Parameter name (e.g. "opacity", "factor", "radius").
        value: The parameter value at this frame.
        filter_index: -1 for layer property, >=0 for a filter's param.
        interpolation: Easing type (LINEAR, CONSTANT, EASE_IN, EASE_OUT, EASE_IN_OUT).

    Returns:
        The keyframe dict that was added or replaced.

    Raises:
        ValueError: If interpolation type is invalid or param is not a known layer property.
        IndexError: If layer_index or filter_index is out of range.
    """
    valid_types = _all_interpolation_types()
    if interpolation not in valid_types:
        raise ValueError(
            f"Invalid interpolation type '{interpolation}'. "
            f"Valid legacy types: {INTERPOLATION_TYPES}. "
            f"Also accepts any shared motion_math easing name."
        )

    layers = project.get("layers", [])
    if layer_index < 0 or layer_index >= len(layers):
        raise IndexError(f"Layer index {layer_index} out of range (0-{len(layers) - 1})")

    layer = layers[layer_index]

    if filter_index == -1:
        if param not in _LAYER_PROPERTIES:
            raise ValueError(
                f"Unknown layer property '{param}'. "
                f"Animatable layer properties: {sorted(_LAYER_PROPERTIES)}"
            )
    else:
        filters = layer.get("filters", [])
        if filter_index < 0 or filter_index >= len(filters):
            raise IndexError(
                f"Filter index {filter_index} out of range "
                f"(0-{len(filters) - 1})"
            )

    if "animation" not in project:
        project["animation"] = {"settings": {}, "keyframes": []}
    if "keyframes" not in project["animation"]:
        project["animation"]["keyframes"] = []

    keyframe = {
        "frame": frame,
        "layer_index": layer_index,
        "filter_index": filter_index,
        "param": param,
        "value": value,
        "interpolation": interpolation,
    }

    # Replace existing keyframe at same frame/layer/param/filter
    kfs = project["animation"]["keyframes"]
    for i, kf in enumerate(kfs):
        if (
            kf["frame"] == frame
            and kf["layer_index"] == layer_index
            and kf["param"] == param
            and kf["filter_index"] == filter_index
        ):
            kfs[i] = keyframe
            return keyframe

    kfs.append(keyframe)
    return keyframe


def remove_animation_keyframe(
    project: dict,
    frame: int,
    layer_index: int,
    param: str,
    filter_index: int = -1,
) -> dict:
    """Remove a specific keyframe.

    Returns:
        {"removed": True} on success.

    Raises:
        ValueError: If the keyframe is not found.
    """
    kfs = project.get("animation", {}).get("keyframes", [])
    for i, kf in enumerate(kfs):
        if (
            kf["frame"] == frame
            and kf["layer_index"] == layer_index
            and kf["param"] == param
            and kf["filter_index"] == filter_index
        ):
            kfs.pop(i)
            return {"removed": True}
    raise ValueError(
        f"Keyframe not found: frame={frame}, layer={layer_index}, "
        f"param={param}, filter={filter_index}"
    )


def list_animation_keyframes(
    project: dict,
    layer_index: int = None,
    param: str = None,
) -> list:
    """List keyframes, optionally filtered by layer and/or param.

    Args:
        project: The project dict.
        layer_index: If set, only return keyframes for this layer.
        param: If set, only return keyframes for this parameter name.

    Returns:
        A list of keyframe dicts sorted by frame number.
    """
    kfs = project.get("animation", {}).get("keyframes", [])
    result = []
    for kf in kfs:
        if layer_index is not None and kf["layer_index"] != layer_index:
            continue
        if param is not None and kf["param"] != param:
            continue
        result.append(kf)
    result.sort(key=lambda k: k["frame"])
    return result


def generate_frame_sequence(
    project: dict,
    output_dir: str,
    frame_start: int = 0,
    frame_end: int = None,
    filename_pattern: str = "frame_{:04d}.png",
    preset: str = "png",
) -> dict:
    """Generate a frame sequence by interpolating keyframed parameters.

    For each frame in [frame_start, frame_end):
      1. Deep-copy the project
      2. Interpolate all keyframed params at this frame
      3. Apply interpolated values to layers/filters
      4. Render the frame via export.render()
      5. Save to output_dir/frame_NNNN.png

    Args:
        project: The project dict (must have layers and animation data).
        output_dir: Directory to write frame images into.
        frame_start: First frame to render (inclusive, 0-based).
        frame_end: Last frame to render (exclusive). Defaults to settings frame_count.
        filename_pattern: Python format pattern for filenames.
        preset: Export preset name (default "png").

    Returns:
        {"output_dir": str, "frame_count": int, "frames": [list of file paths]}
    """
    from cli_anything.gimp.core.export import render

    settings = get_animation_settings(project)
    if frame_end is None:
        frame_end = settings["frame_count"]

    all_keyframes = project.get("animation", {}).get("keyframes", [])

    os.makedirs(output_dir, exist_ok=True)

    frames = []
    for frame_num in range(frame_start, frame_end):
        frame_proj = _apply_interpolated_values(project, frame_num, all_keyframes)
        filename = filename_pattern.format(frame_num)
        frame_path = os.path.join(output_dir, filename)
        render(frame_proj, frame_path, preset=preset, overwrite=True)
        frames.append(os.path.abspath(frame_path))

    return {
        "output_dir": os.path.abspath(output_dir),
        "frame_count": len(frames),
        "frames": frames,
    }


def _interpolate_at_frame(keyframes: list, frame: int) -> float:
    """Interpolate a parameter value at a given frame from surrounding keyframes.

    Uses the interpolation type of the left (preceding) keyframe to determine
    the easing curve between it and the next keyframe.

    If the frame is before all keyframes, returns the first keyframe's value.
    If the frame is after all keyframes, returns the last keyframe's value.
    If the frame matches a keyframe exactly, returns that keyframe's value.

    Args:
        keyframes: List of keyframe dicts for a single param, sorted by frame.
        frame: The frame number to interpolate at.

    Returns:
        The interpolated numeric value.
    """
    if not keyframes:
        raise ValueError("No keyframes to interpolate from")

    # Sort by frame (should already be sorted, but be safe)
    kfs = sorted(keyframes, key=lambda k: k["frame"])

    # Before all keyframes
    if frame <= kfs[0]["frame"]:
        return kfs[0]["value"]

    # After all keyframes
    if frame >= kfs[-1]["frame"]:
        return kfs[-1]["value"]

    # Find surrounding keyframes
    for i in range(len(kfs) - 1):
        left = kfs[i]
        right = kfs[i + 1]
        if left["frame"] <= frame <= right["frame"]:
            if left["frame"] == frame:
                return left["value"]
            if right["frame"] == frame:
                return right["value"]

            # Compute normalized t in [0, 1]
            span = right["frame"] - left["frame"]
            t = (frame - left["frame"]) / span

            interp = left.get("interpolation", "LINEAR")
            t = _ease(t, interp)

            v0 = left["value"]
            v1 = right["value"]
            return v0 + (v1 - v0) * t

    # Fallback (should not reach here)
    return kfs[-1]["value"]


def _ease(t: float, interpolation: str) -> float:
    """Apply an easing function to a normalized parameter t in [0, 1].

    Supports the 5 legacy INTERPOLATION_TYPES plus all 30+ Penner easing
    names from shared/motion_math when that module is importable.

    Args:
        t: Progress value between 0.0 and 1.0.
        interpolation: Easing name (case-insensitive for legacy names).

    Returns:
        The eased t value.
    """
    # Legacy types (backward-compatible)
    upper = interpolation.upper()
    if upper == "CONSTANT":
        return 0.0  # Hold at left value until next keyframe
    if upper == "LINEAR":
        return t
    if upper == "EASE_IN":
        return t * t
    if upper == "EASE_OUT":
        return 1.0 - (1.0 - t) * (1.0 - t)
    if upper == "EASE_IN_OUT":
        if t < 0.5:
            return 2.0 * t * t
        else:
            return 1.0 - 2.0 * (1.0 - t) * (1.0 - t)

    # Try shared motion_math easings (lowercase canonical names)
    if _SHARED_EASING_FUNCTIONS is not None:
        lower = interpolation.lower()
        fn = _SHARED_EASING_FUNCTIONS.get(lower)
        if fn is not None:
            return fn(t)

    # Unknown — fall back to linear
    return t


def _apply_interpolated_values(
    project: dict,
    frame: int,
    all_keyframes: list,
) -> dict:
    """Return a modified deep copy of the project with all params set to
    their interpolated values at the given frame.

    Groups keyframes by (layer_index, filter_index, param), interpolates
    each group, and writes the result into the copied project's layers.
    """
    proj = copy.deepcopy(project)

    # Group keyframes by (layer_index, filter_index, param)
    groups: Dict[tuple, list] = {}
    for kf in all_keyframes:
        key = (kf["layer_index"], kf["filter_index"], kf["param"])
        groups.setdefault(key, []).append(kf)

    layers = proj.get("layers", [])

    for (layer_idx, filt_idx, param), kfs in groups.items():
        if layer_idx < 0 or layer_idx >= len(layers):
            continue

        value = _interpolate_at_frame(kfs, frame)
        layer = layers[layer_idx]

        if filt_idx == -1:
            # Layer property
            if param == "opacity":
                layer["opacity"] = max(0.0, min(1.0, float(value)))
            elif param == "offset_x":
                layer["offset_x"] = int(round(value))
            elif param == "offset_y":
                layer["offset_y"] = int(round(value))
        else:
            # Filter parameter
            filters = layer.get("filters", [])
            if 0 <= filt_idx < len(filters):
                filters[filt_idx]["params"][param] = value

    return proj
