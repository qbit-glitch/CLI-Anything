"""Kdenlive CLI — Keyframe animation for filter parameters.

Kdenlive uses a JSON project format where filter params are stored as scalars.
When a parameter is keyframed, we transform the scalar to a keyframed dict:

    {"keyframed": True, "keyframes": [{"time": "00:00:00.000", "value": "0.5", "easing": "linear"}, ...]}

During MLT XML export, keyframed params are emitted as MLT keyframe strings:
    "00:00:00.000=0.5;00:00:01.000=1.0"

For complex easings (not linear/ease_in_out/hold), values are baked as
densely-sampled MLT keyframe strings during export.
"""

import os
import sys
from typing import Any, Dict, List, Optional

from ..utils.mlt_xml import timecode_to_seconds, seconds_to_timecode

# ---------------------------------------------------------------------------
# Shared motion_math easing import
# ---------------------------------------------------------------------------

_SHARED_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../../../../shared")
)
if _SHARED_PATH not in sys.path:
    sys.path.insert(0, _SHARED_PATH)

from motion_math.easing import get_easing  # noqa: E402
from motion_math.easing import EASING_FUNCTIONS as _SHARED_EASING_FUNCTIONS  # noqa: E402


# ---------------------------------------------------------------------------
# EASING_TYPES — all 30+ shared names plus "hold" special case + legacy aliases
# ---------------------------------------------------------------------------

_HOLD = "hold"

# Legacy quadratic aliases for backward compatibility
_LEGACY_ALIASES: dict[str, str] = {
    "ease_in": "ease_in_quad",
    "ease_out": "ease_out_quad",
    "ease_in_out": "ease_in_out_quad",
}

# Build the full list: shared names + hold + legacy aliases
EASING_TYPES: List[str] = list(_SHARED_EASING_FUNCTIONS.keys()) + [_HOLD]
for _alias in _LEGACY_ALIASES:
    if _alias not in EASING_TYPES:
        EASING_TYPES.append(_alias)


# ---------------------------------------------------------------------------
# Easing functions dict (backward-compatible)
# ---------------------------------------------------------------------------

def _ease_linear(t: float) -> float:
    return t


def _ease_in_quad(t: float) -> float:
    return t * t


def _ease_out_quad(t: float) -> float:
    return 1.0 - (1.0 - t) * (1.0 - t)


def _ease_in_out_quad(t: float) -> float:
    if t < 0.5:
        return 2.0 * t * t
    return 1.0 - (-2.0 * t + 2.0) ** 2 / 2.0


def _ease_hold(t: float) -> float:
    return 0.0 if t < 1.0 else 1.0


EASING_FUNCTIONS: dict = {
    "linear": _ease_linear,
    "ease_in": _ease_in_quad,       # legacy alias
    "ease_out": _ease_out_quad,     # legacy alias
    "ease_in_out": _ease_in_out_quad,  # legacy alias
    "hold": _ease_hold,
}
for _name, _fn in _SHARED_EASING_FUNCTIONS.items():
    if _name not in EASING_FUNCTIONS:
        EASING_FUNCTIONS[_name] = _fn


# ---------------------------------------------------------------------------
# Internal easing evaluation
# ---------------------------------------------------------------------------

def _apply_easing(name: str, t: float) -> float:
    """Apply a named easing to t in [0, 1]."""
    if name == _HOLD:
        return _ease_hold(t)
    canonical = _LEGACY_ALIASES.get(name, name)
    if canonical in _SHARED_EASING_FUNCTIONS:
        return _SHARED_EASING_FUNCTIONS[canonical](t)
    return EASING_FUNCTIONS.get(name, _ease_linear)(t)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_clip_filter(
    project: Dict[str, Any],
    track_id: int,
    clip_index: int,
    filter_index: int,
) -> dict:
    """Locate a filter dict on a clip."""
    tracks = project.get("tracks", [])
    track = None
    for t in tracks:
        if t["id"] == track_id:
            track = t
            break
    if track is None:
        raise ValueError(f"Track not found: {track_id}")

    clips = track.get("clips", [])
    if clip_index < 0 or clip_index >= len(clips):
        raise IndexError(
            f"Clip index {clip_index} out of range (0-{len(clips) - 1})"
        )

    filters = clips[clip_index].get("filters", [])
    if filter_index < 0 or filter_index >= len(filters):
        raise IndexError(
            f"Filter index {filter_index} out of range (0-{len(filters) - 1})"
        )
    return filters[filter_index]


def _normalize_time(time: str) -> str:
    """Normalize a time value to HH:MM:SS.mmm format."""
    try:
        secs = float(time)
        return seconds_to_timecode(secs)
    except ValueError:
        timecode_to_seconds(time)
        return time


def _compare_time(a: str, b: str) -> int:
    """Compare two timecodes. Returns -1, 0, or 1."""
    sa = timecode_to_seconds(a)
    sb = timecode_to_seconds(b)
    if sa < sb:
        return -1
    elif sa > sb:
        return 1
    return 0


def _is_keyframed(value: Any) -> bool:
    """Check if a param value is a keyframed dict."""
    return isinstance(value, dict) and value.get("keyframed") is True


# ---------------------------------------------------------------------------
# MLT keyframe string conversion (for export)
# ---------------------------------------------------------------------------

def _bake_segment(
    time_str: str, value_str: str, easing: str,
    next_time_str: str, next_value_str: str,
    fps: int = 30,
) -> list:
    """Bake a complex-easing segment into densely-sampled MLT keyframe strings.

    Returns list of "TC=value" strings for [t0, t1) (endpoint excluded).
    """
    try:
        v0 = float(value_str)
        v1 = float(next_value_str)
        t0 = timecode_to_seconds(time_str)
        t1 = timecode_to_seconds(next_time_str)
        duration = t1 - t0
        if duration <= 0:
            return [f"{time_str}={value_str}"]
        num_samples = max(2, int(duration * fps) + 1)
        result = []
        for s_idx in range(num_samples - 1):
            progress = s_idx / (num_samples - 1)
            eased = _apply_easing(easing, progress)
            sample_val = v0 + (v1 - v0) * eased
            sample_tc = seconds_to_timecode(t0 + progress * duration)
            result.append(f"{sample_tc}={sample_val:.6f}")
        return result
    except (ValueError, TypeError):
        return [f"{time_str}={value_str}"]


def keyframes_to_mlt_string(keyframes: List[dict]) -> str:
    """Convert keyframe list to MLT keyframe string for XML export.

    For complex easings (not linear/ease_in_out/hold), the segment is baked
    into densely-sampled linear MLT keyframe strings at 30fps.

    Args:
        keyframes: [{"time": str, "value": str, "easing": str}, ...]

    Returns:
        MLT string like "00:00:00.000=0;00:00:01.000=1"
    """
    if not keyframes:
        return ""

    _MLT_NATIVE = {"linear", "ease_in_out", _HOLD}

    parts = []
    for i, kf in enumerate(keyframes):
        time_str = kf["time"]
        value_str = str(kf["value"])
        easing = kf.get("easing", "linear")
        is_last = (i == len(keyframes) - 1)

        if easing in _MLT_NATIVE or is_last:
            if easing == "ease_in_out":
                parts.append(f"{time_str}~={value_str}")
            elif easing == _HOLD:
                parts.append(f"{time_str}|={value_str}")
            else:
                parts.append(f"{time_str}={value_str}")
        else:
            next_kf = keyframes[i + 1]
            try:
                float(value_str)
                float(next_kf["value"])
                baked = _bake_segment(
                    time_str, value_str, easing,
                    next_kf["time"], str(next_kf["value"]),
                )
                parts.extend(baked)
            except (ValueError, TypeError):
                parts.append(f"{time_str}={value_str}")

    return ";".join(parts)


# ---------------------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------------------

def interpolate_value(keyframes: List[dict], time: str) -> Optional[float]:
    """Calculate the interpolated value at a given time.

    Uses the easing function of the first keyframe in each pair.
    Returns None if no keyframes or value is non-numeric.
    """
    if not keyframes:
        return None

    t_sec = timecode_to_seconds(time)
    kf_times = [timecode_to_seconds(kf["time"]) for kf in keyframes]

    if t_sec <= kf_times[0]:
        try:
            return float(keyframes[0]["value"])
        except (ValueError, TypeError):
            return None

    if t_sec >= kf_times[-1]:
        try:
            return float(keyframes[-1]["value"])
        except (ValueError, TypeError):
            return None

    for i in range(len(keyframes) - 1):
        if kf_times[i] <= t_sec <= kf_times[i + 1]:
            try:
                v0 = float(keyframes[i]["value"])
                v1 = float(keyframes[i + 1]["value"])
            except (ValueError, TypeError):
                return None

            if kf_times[i + 1] == kf_times[i]:
                return v1

            progress = (t_sec - kf_times[i]) / (kf_times[i + 1] - kf_times[i])
            easing = keyframes[i].get("easing", "linear")
            eased = _apply_easing(easing, progress)
            return v0 + (v1 - v0) * eased

    return None


# ---------------------------------------------------------------------------
# Core keyframe operations
# ---------------------------------------------------------------------------

def add_keyframe(
    project: Dict[str, Any],
    track_id: int,
    clip_index: int,
    filter_index: int,
    time: str,
    param: str,
    value: str,
    easing: str = "linear",
) -> dict:
    """Add a keyframe to a filter parameter.

    If the parameter is currently a scalar, transforms it into a keyframed
    dict. If it's already keyframed, inserts/replaces the keyframe at the
    given time.
    """
    if easing not in EASING_TYPES:
        raise ValueError(f"Invalid easing: {easing!r}. Valid: {EASING_TYPES}")

    time = _normalize_time(time)
    filt = _resolve_clip_filter(project, track_id, clip_index, filter_index)
    params = filt.get("params", {})

    current = params.get(param)

    if _is_keyframed(current):
        keyframes = current["keyframes"]
    elif current is not None:
        keyframes = [{"time": "00:00:00.000", "value": str(current), "easing": "linear"}]
    else:
        keyframes = []

    replaced = False
    for kf in keyframes:
        if _compare_time(kf["time"], time) == 0:
            kf["value"] = value
            kf["easing"] = easing
            replaced = True
            break

    if not replaced:
        keyframes.append({"time": time, "value": value, "easing": easing})

    keyframes.sort(key=lambda k: timecode_to_seconds(k["time"]))

    params[param] = {"keyframed": True, "keyframes": keyframes}
    filt["params"] = params

    return {
        "action": "add_keyframe",
        "time": time,
        "param": param,
        "value": value,
        "easing": easing,
        "keyframe_count": len(keyframes),
    }


def remove_keyframe(
    project: Dict[str, Any],
    track_id: int,
    clip_index: int,
    filter_index: int,
    time: str,
    param: str,
) -> dict:
    """Remove a keyframe at a specific time."""
    time = _normalize_time(time)
    filt = _resolve_clip_filter(project, track_id, clip_index, filter_index)
    params = filt.get("params", {})

    current = params.get(param)
    if not _is_keyframed(current):
        raise ValueError(f"Parameter {param!r} is not keyframed")

    keyframes = current["keyframes"]
    original_count = len(keyframes)
    keyframes = [kf for kf in keyframes if _compare_time(kf["time"], time) != 0]

    if len(keyframes) == original_count:
        raise ValueError(f"No keyframe found at time {time!r} for param {param!r}")

    if keyframes:
        params[param] = {"keyframed": True, "keyframes": keyframes}
    else:
        params[param] = ""
    filt["params"] = params

    return {
        "action": "remove_keyframe",
        "time": time,
        "param": param,
        "remaining": len(keyframes),
    }


def list_keyframes(
    project: Dict[str, Any],
    track_id: int,
    clip_index: int,
    filter_index: int,
    param: str,
) -> List[dict]:
    """List all keyframes for a parameter."""
    filt = _resolve_clip_filter(project, track_id, clip_index, filter_index)
    params = filt.get("params", {})

    current = params.get(param)
    if not _is_keyframed(current):
        return []

    result = []
    for i, kf in enumerate(current["keyframes"]):
        result.append({
            "index": i,
            "time": kf["time"],
            "value": kf["value"],
            "easing": kf.get("easing", "linear"),
        })
    return result


def clear_keyframes(
    project: Dict[str, Any],
    track_id: int,
    clip_index: int,
    filter_index: int,
    param: str,
) -> dict:
    """Remove all keyframes, reverting parameter to its last value."""
    filt = _resolve_clip_filter(project, track_id, clip_index, filter_index)
    params = filt.get("params", {})

    current = params.get(param)
    if not _is_keyframed(current):
        return {
            "action": "clear_keyframes",
            "param": param,
            "static_value": str(current) if current is not None else "",
            "removed_count": 0,
        }

    keyframes = current["keyframes"]
    static_value = keyframes[-1]["value"] if keyframes else ""
    removed_count = len(keyframes)

    try:
        params[param] = float(static_value)
        if params[param] == int(params[param]):
            params[param] = int(params[param])
    except (ValueError, TypeError):
        params[param] = static_value

    filt["params"] = params

    return {
        "action": "clear_keyframes",
        "param": param,
        "static_value": static_value,
        "removed_count": removed_count,
    }
