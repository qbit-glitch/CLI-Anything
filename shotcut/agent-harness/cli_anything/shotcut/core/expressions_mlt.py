"""Expression baking for MLT/Shotcut keyframe strings.

Uses the shared Expression class to evaluate a formula at every frame and
encode the results as a dense MLT keyframe string.

Example usage::

    from cli_anything.shotcut.core.expressions_mlt import bake_expression

    # Sinusoidal opacity
    kf_str = bake_expression("0.5 + 0.5 * sin(time * 6.28)", fps=30, duration=2.0)
    # → "00:00:00.000=0.500000;00:00:00.033=0.591179;..."
"""

import os
import sys
from typing import Optional, Dict

# ---------------------------------------------------------------------------
# Shared motion_math import
# ---------------------------------------------------------------------------

_SHARED_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../../../../shared")
)
if _SHARED_PATH not in sys.path:
    sys.path.insert(0, _SHARED_PATH)

from motion_math.expressions import Expression  # noqa: E402

from .keyframes import _seconds_to_tc  # noqa: E402


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def bake_expression(
    expression_str: str,
    fps: int,
    duration: float,
    context: Optional[Dict[str, object]] = None,
) -> str:
    """Evaluate a shared Expression at every frame and encode as MLT keyframe string.

    Args:
        expression_str: Formula string (e.g. "0.5 + 0.5 * sin(time * 6.28)").
                        Uses the motion_math Expression sandbox: variables
                        ``time`` (seconds), ``frame`` (int), ``fps``, ``pi``,
                        ``e``, and helpers: sin, cos, tan, abs, pow, sqrt,
                        floor, ceil, min, max, clamp, lerp, remap, step,
                        smoothstep, wiggle, random.
        fps:            Frames per second for the timeline.
        duration:       Total duration to bake in seconds.
        context:        Optional extra variables injected into each evaluation.

    Returns:
        MLT keyframe string with one sample per frame, e.g.:
        ``"00:00:00.000=0.500000;00:00:00.033=0.591179;..."``

    Raises:
        ValueError: If the expression has syntax errors or disallowed constructs.
    """
    expr = Expression(expression_str)
    total_frames = max(1, int(round(duration * fps)))
    parts = []

    for frame in range(total_frames + 1):
        time = frame / fps
        value = expr.evaluate(time=time, frame=frame, fps=float(fps),
                              context=context)
        tc = _seconds_to_tc(time)
        parts.append(f"{tc}={value:.6f}")

    return ";".join(parts)


def bake_expression_frames(
    expression_str: str,
    fps: int,
    duration: float,
    context: Optional[Dict[str, object]] = None,
) -> list[dict]:
    """Evaluate a shared Expression at every frame and return as a list of dicts.

    Useful when you need structured access to frame values rather than the
    raw MLT string.

    Args:
        expression_str: Formula string.
        fps:            Frames per second.
        duration:       Total duration in seconds.
        context:        Optional extra variables.

    Returns:
        List of {"frame": int, "time": float, "timecode": str, "value": float}.
    """
    expr = Expression(expression_str)
    total_frames = max(1, int(round(duration * fps)))
    result = []

    for frame in range(total_frames + 1):
        time = frame / fps
        value = expr.evaluate(time=time, frame=frame, fps=float(fps),
                              context=context)
        result.append({
            "frame": frame,
            "time": time,
            "timecode": _seconds_to_tc(time),
            "value": value,
        })

    return result
