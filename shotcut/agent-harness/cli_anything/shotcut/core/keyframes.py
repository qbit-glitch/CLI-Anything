"""Keyframe animation: animate filter parameters over time with easing.

MLT natively supports keyframe syntax in property values:
    "00:00:00.000=0;00:00:01.000=1"    (linear interpolation)
    "00:00:00.000=0~=0.5;00:00:01.000=1"  (smooth/bezier)
    "00:00:00.000=0|=0;00:00:01.000=1"    (hold/constant)

This module provides a high-level API for creating, parsing, and manipulating
keyframe strings on any filter parameter.

For complex easings not natively supported by MLT (i.e. not linear,
ease_in_out, or hold), segments are baked into densely-sampled linear MLT
keyframe strings (at 30fps) so MLT can play them back via linear interpolation.
"""

import os
import sys
from typing import Any, Optional

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

from ..utils import mlt_xml
from .session import Session


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
EASING_TYPES: list[str] = list(_SHARED_EASING_FUNCTIONS.keys()) + [_HOLD]
for _alias in _LEGACY_ALIASES:
    if _alias not in EASING_TYPES:
        EASING_TYPES.append(_alias)


# ---------------------------------------------------------------------------
# Private legacy easing functions (kept for backward compatibility — imported
# by existing tests).
# ---------------------------------------------------------------------------

def _ease_linear(t: float) -> float:
    return t


def _ease_in(t: float) -> float:
    """Quadratic ease in (legacy alias for ease_in_quad)."""
    return t * t


def _ease_out(t: float) -> float:
    """Quadratic ease out (legacy alias for ease_out_quad)."""
    return t * (2 - t)


def _ease_in_out(t: float) -> float:
    """Quadratic ease in-out (legacy alias for ease_in_out_quad)."""
    if t < 0.5:
        return 2 * t * t
    return -1 + (4 - 2 * t) * t


def _ease_hold(t: float) -> float:
    """Step function — holds at 0 until t=1, then jumps."""
    return 0.0 if t < 1.0 else 1.0


# ---------------------------------------------------------------------------
# Public EASING_FUNCTIONS dict (backward-compatible — adds shared functions)
# ---------------------------------------------------------------------------

EASING_FUNCTIONS: dict[str, Any] = {
    "linear": _ease_linear,
    "ease_in": _ease_in,
    "ease_out": _ease_out,
    "ease_in_out": _ease_in_out,
    "hold": _ease_hold,
}
for _name, _fn in _SHARED_EASING_FUNCTIONS.items():
    if _name not in EASING_FUNCTIONS:
        EASING_FUNCTIONS[_name] = _fn


# ---------------------------------------------------------------------------
# Internal easing evaluation
# ---------------------------------------------------------------------------

def _apply_easing(name: str, t: float) -> float:
    """Apply a named easing function to t in [0, 1].

    Handles:
    - "hold": step function
    - legacy aliases (ease_in, ease_out, ease_in_out) → quadratic
    - all 30+ shared Penner easings via motion_math
    """
    if name == _HOLD:
        return _ease_hold(t)
    # Resolve legacy aliases to canonical shared names
    canonical = _LEGACY_ALIASES.get(name, name)
    if canonical in _SHARED_EASING_FUNCTIONS:
        return _SHARED_EASING_FUNCTIONS[canonical](t)
    # Fallback to local EASING_FUNCTIONS dict
    return EASING_FUNCTIONS.get(name, _ease_linear)(t)


# ---------------------------------------------------------------------------
# MLT keyframe string parsing / generation
# ---------------------------------------------------------------------------

def parse_mlt_keyframe_string(kf_string: str) -> list[dict]:
    """Parse an MLT keyframe string into a list of keyframe dicts.

    Supported formats:
        "00:00:00.000=0.5;00:00:01.000=1.0"      (linear)
        "00:00:00.000=0.5~=0;00:00:01.000=1.0"    (smooth)
        "00:00:00.000=0.5|=0;00:00:01.000=1.0"    (hold)

    Returns:
        [{"time": str, "value": str, "easing": str}, ...]
    """
    if not kf_string or "=" not in kf_string:
        return []

    keyframes = []
    parts = kf_string.split(";")
    for part in parts:
        part = part.strip()
        if not part:
            continue

        easing = "linear"
        if "~=" in part:
            easing = "ease_in_out"
            part = part.replace("~=", "=", 1)
        elif "|=" in part:
            easing = _HOLD
            part = part.replace("|=", "=", 1)

        eq_idx = part.index("=")
        time_str = part[:eq_idx].strip()
        value_str = part[eq_idx + 1:].strip()

        keyframes.append({
            "time": time_str,
            "value": value_str,
            "easing": easing,
        })

    return keyframes


def _bake_segment(
    time_str: str, value_str: str, easing: str,
    next_time_str: str, next_value_str: str,
    fps: int = 30,
) -> list[str]:
    """Bake a complex-easing segment into densely-sampled MLT keyframe strings.

    Returns a list of "TC=value" strings covering [t0, t1).
    The endpoint t1 is NOT included (the caller emits it separately).
    """
    try:
        v0 = float(value_str)
        v1 = float(next_value_str)
        t0 = _tc_to_seconds(time_str)
        t1 = _tc_to_seconds(next_time_str)
        duration = t1 - t0
        if duration <= 0:
            return [f"{time_str}={value_str}"]

        num_samples = max(2, int(duration * fps) + 1)
        result = []
        for s_idx in range(num_samples - 1):  # Exclude endpoint
            progress = s_idx / (num_samples - 1)
            eased = _apply_easing(easing, progress)
            sample_val = v0 + (v1 - v0) * eased
            sample_tc = _seconds_to_tc(t0 + progress * duration)
            result.append(f"{sample_tc}={sample_val:.6f}")
        return result
    except (ValueError, TypeError):
        return [f"{time_str}={value_str}"]


def generate_mlt_keyframe_string(keyframes: list[dict]) -> str:
    """Convert a list of keyframe dicts to an MLT keyframe string.

    For complex easings not natively representable in MLT (anything other
    than linear/ease_in_out/hold), the segment is baked into densely-sampled
    linear MLT keyframe strings at 30fps.

    Args:
        keyframes: [{"time": str, "value": str, "easing": str}, ...]

    Returns:
        MLT keyframe string like "00:00:00.000=0;00:00:01.000=1"
    """
    if not keyframes:
        return ""

    # Easings MLT handles natively
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
            # Complex easing: bake this segment into sampled linear points
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
# Timecode helpers
# ---------------------------------------------------------------------------

def _tc_to_seconds(tc: str) -> float:
    """Convert HH:MM:SS.mmm timecode to seconds."""
    try:
        return float(tc)
    except ValueError:
        pass

    parts = tc.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return float(h) * 3600 + float(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return float(m) * 60 + float(s)
    raise ValueError(f"Invalid timecode: {tc!r}")


def _seconds_to_tc(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.mmm timecode."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    ms = int(round((s - int(s)) * 1000))
    return f"{h:02d}:{m:02d}:{int(s):02d}.{ms:03d}"


def _compare_time(a: str, b: str) -> int:
    """Compare two timecodes. Returns -1, 0, or 1."""
    sa = _tc_to_seconds(a)
    sb = _tc_to_seconds(b)
    if sa < sb:
        return -1
    elif sa > sb:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------------------

def interpolate_value(keyframes: list[dict], time: str) -> Optional[float]:
    """Calculate the interpolated value at a given time.

    Uses the easing function of the *first* keyframe in each pair to
    determine the curve between the two points.

    Returns None if no keyframes exist or value is non-numeric.
    """
    if not keyframes:
        return None

    t_sec = _tc_to_seconds(time)
    kf_times = [_tc_to_seconds(kf["time"]) for kf in keyframes]

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
# Core keyframe operations on filter parameters
# ---------------------------------------------------------------------------

def _resolve_filter(session: Session, filter_index: int,
                    track_index: Optional[int] = None,
                    clip_index: Optional[int] = None):
    """Locate the filter element by index on the given target."""
    from .filters import _resolve_target
    target = _resolve_target(session, track_index, clip_index)
    filters = target.findall("filter")
    if filter_index < 0 or filter_index >= len(filters):
        raise IndexError(
            f"Filter index {filter_index} out of range (0-{len(filters) - 1})"
        )
    return filters[filter_index]


def add_keyframe(
    session: Session,
    time: str,
    param: str,
    value: str,
    easing: str = "linear",
    track_index: Optional[int] = None,
    clip_index: Optional[int] = None,
    filter_index: int = 0,
) -> dict:
    """Add a keyframe point to a filter parameter.

    Reads the existing property value, parses it as a keyframe string (or
    treats it as the initial static value), inserts the new point, and
    re-serializes to MLT format.

    Args:
        session: Active session
        time: Timecode "HH:MM:SS.mmm" or seconds
        param: MLT property name (e.g. "level", "transition.geometry")
        value: Value at this time
        easing: Easing to next keyframe (any of the 30+ shared easings or "hold")
        track_index: Target track (None = global)
        clip_index: Target clip (None = track-level)
        filter_index: Index of the filter on the target
    """
    if easing not in EASING_TYPES:
        raise ValueError(f"Invalid easing: {easing!r}. Valid: {EASING_TYPES}")

    # Normalize time to HH:MM:SS.mmm
    try:
        secs = float(time)
        time = _seconds_to_tc(secs)
    except ValueError:
        _tc_to_seconds(time)

    session.checkpoint()
    filt = _resolve_filter(session, filter_index, track_index, clip_index)

    current = mlt_xml.get_property(filt, param, "")

    parsed = parse_mlt_keyframe_string(current) if current else []
    if parsed:
        keyframes = parsed
    elif current:
        keyframes = [{"time": "00:00:00.000", "value": current, "easing": "linear"}]
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

    keyframes.sort(key=lambda k: _tc_to_seconds(k["time"]))

    new_str = generate_mlt_keyframe_string(keyframes)
    mlt_xml.set_property(filt, param, new_str)

    return {
        "action": "add_keyframe",
        "time": time,
        "param": param,
        "value": value,
        "easing": easing,
        "keyframe_count": len(keyframes),
        "keyframe_string": new_str,
    }


def remove_keyframe(
    session: Session,
    time: str,
    param: str,
    track_index: Optional[int] = None,
    clip_index: Optional[int] = None,
    filter_index: int = 0,
) -> dict:
    """Remove a keyframe at a specific time from a parameter."""
    try:
        secs = float(time)
        time = _seconds_to_tc(secs)
    except ValueError:
        _tc_to_seconds(time)

    session.checkpoint()
    filt = _resolve_filter(session, filter_index, track_index, clip_index)
    current = mlt_xml.get_property(filt, param, "")
    keyframes = parse_mlt_keyframe_string(current)

    original_count = len(keyframes)
    keyframes = [kf for kf in keyframes if _compare_time(kf["time"], time) != 0]

    if len(keyframes) == original_count:
        raise ValueError(f"No keyframe found at time {time!r} for param {param!r}")

    new_str = generate_mlt_keyframe_string(keyframes) if keyframes else ""
    mlt_xml.set_property(filt, param, new_str)

    return {
        "action": "remove_keyframe",
        "time": time,
        "param": param,
        "remaining": len(keyframes),
    }


def list_keyframes(
    session: Session,
    param: str,
    track_index: Optional[int] = None,
    clip_index: Optional[int] = None,
    filter_index: int = 0,
) -> list[dict]:
    """List all keyframes for a parameter."""
    filt = _resolve_filter(session, filter_index, track_index, clip_index)
    current = mlt_xml.get_property(filt, param, "")
    keyframes = parse_mlt_keyframe_string(current)

    result = []
    for i, kf in enumerate(keyframes):
        result.append({
            "index": i,
            "time": kf["time"],
            "value": kf["value"],
            "easing": kf.get("easing", "linear"),
        })
    return result


def clear_keyframes(
    session: Session,
    param: str,
    track_index: Optional[int] = None,
    clip_index: Optional[int] = None,
    filter_index: int = 0,
) -> dict:
    """Remove all keyframes, setting the parameter to its last value."""
    session.checkpoint()
    filt = _resolve_filter(session, filter_index, track_index, clip_index)
    current = mlt_xml.get_property(filt, param, "")
    keyframes = parse_mlt_keyframe_string(current)

    static_value = keyframes[-1]["value"] if keyframes else ""
    mlt_xml.set_property(filt, param, static_value)

    return {
        "action": "clear_keyframes",
        "param": param,
        "static_value": static_value,
        "removed_count": len(keyframes),
    }
