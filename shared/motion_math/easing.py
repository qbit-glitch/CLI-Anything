"""Easing functions for motion graphics.

Implements:
- 30 Penner easing functions (10 families × 3 variants: in, out, in_out)
- cubic_bezier(x1, y1, x2, y2) — CSS-style bezier curve
- spring(tension, friction, mass) — damped harmonic oscillator

All Penner functions satisfy f(0) == 0 and f(1) == 1.

References:
  Robert Penner's easing equations — https://easings.net/
"""

from __future__ import annotations

import math
from typing import Callable

__all__ = [
    # Sine
    "ease_in_sine", "ease_out_sine", "ease_in_out_sine",
    # Quad
    "ease_in_quad", "ease_out_quad", "ease_in_out_quad",
    # Cubic
    "ease_in_cubic", "ease_out_cubic", "ease_in_out_cubic",
    # Quartic
    "ease_in_quart", "ease_out_quart", "ease_in_out_quart",
    # Quintic
    "ease_in_quint", "ease_out_quint", "ease_in_out_quint",
    # Exponential
    "ease_in_expo", "ease_out_expo", "ease_in_out_expo",
    # Circular
    "ease_in_circ", "ease_out_circ", "ease_in_out_circ",
    # Elastic
    "ease_in_elastic", "ease_out_elastic", "ease_in_out_elastic",
    # Back
    "ease_in_back", "ease_out_back", "ease_in_out_back",
    # Bounce
    "ease_in_bounce", "ease_out_bounce", "ease_in_out_bounce",
    # Advanced
    "cubic_bezier", "spring",
    # Registry
    "EASING_FUNCTIONS", "get_easing",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PI = math.pi
_TAU = math.tau


# ---------------------------------------------------------------------------
# Sine family
# ---------------------------------------------------------------------------

def ease_in_sine(t: float) -> float:
    return 1.0 - math.cos(t * _PI / 2.0)


def ease_out_sine(t: float) -> float:
    return math.sin(t * _PI / 2.0)


def ease_in_out_sine(t: float) -> float:
    return -(math.cos(_PI * t) - 1.0) / 2.0


# ---------------------------------------------------------------------------
# Quad family  (t²)
# ---------------------------------------------------------------------------

def ease_in_quad(t: float) -> float:
    return t * t


def ease_out_quad(t: float) -> float:
    return 1.0 - (1.0 - t) * (1.0 - t)


def ease_in_out_quad(t: float) -> float:
    if t < 0.5:
        return 2.0 * t * t
    return 1.0 - (-2.0 * t + 2.0) ** 2 / 2.0


# ---------------------------------------------------------------------------
# Cubic family  (t³)
# ---------------------------------------------------------------------------

def ease_in_cubic(t: float) -> float:
    return t * t * t


def ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


# ---------------------------------------------------------------------------
# Quartic family  (t⁴)
# ---------------------------------------------------------------------------

def ease_in_quart(t: float) -> float:
    return t * t * t * t


def ease_out_quart(t: float) -> float:
    return 1.0 - (1.0 - t) ** 4


def ease_in_out_quart(t: float) -> float:
    if t < 0.5:
        return 8.0 * t * t * t * t
    return 1.0 - (-2.0 * t + 2.0) ** 4 / 2.0


# ---------------------------------------------------------------------------
# Quintic family  (t⁵)
# ---------------------------------------------------------------------------

def ease_in_quint(t: float) -> float:
    return t * t * t * t * t


def ease_out_quint(t: float) -> float:
    return 1.0 - (1.0 - t) ** 5


def ease_in_out_quint(t: float) -> float:
    if t < 0.5:
        return 16.0 * t * t * t * t * t
    return 1.0 - (-2.0 * t + 2.0) ** 5 / 2.0


# ---------------------------------------------------------------------------
# Exponential family
# ---------------------------------------------------------------------------

def ease_in_expo(t: float) -> float:
    if t == 0.0:
        return 0.0
    return math.pow(2.0, 10.0 * t - 10.0)


def ease_out_expo(t: float) -> float:
    if t == 1.0:
        return 1.0
    return 1.0 - math.pow(2.0, -10.0 * t)


def ease_in_out_expo(t: float) -> float:
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0
    if t < 0.5:
        return math.pow(2.0, 20.0 * t - 10.0) / 2.0
    return (2.0 - math.pow(2.0, -20.0 * t + 10.0)) / 2.0


# ---------------------------------------------------------------------------
# Circular family
# ---------------------------------------------------------------------------

def ease_in_circ(t: float) -> float:
    return 1.0 - math.sqrt(1.0 - t * t)


def ease_out_circ(t: float) -> float:
    return math.sqrt(1.0 - (t - 1.0) ** 2)


def ease_in_out_circ(t: float) -> float:
    if t < 0.5:
        return (1.0 - math.sqrt(1.0 - (2.0 * t) ** 2)) / 2.0
    return (math.sqrt(1.0 - (-2.0 * t + 2.0) ** 2) + 1.0) / 2.0


# ---------------------------------------------------------------------------
# Elastic family
# ---------------------------------------------------------------------------

_ELASTIC_C4 = _TAU / 3.0
_ELASTIC_C5 = _TAU / 4.5


def ease_in_elastic(t: float) -> float:
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0
    return -math.pow(2.0, 10.0 * t - 10.0) * math.sin(
        (t * 10.0 - 10.75) * _ELASTIC_C4
    )


def ease_out_elastic(t: float) -> float:
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0
    return (
        math.pow(2.0, -10.0 * t) * math.sin((t * 10.0 - 0.75) * _ELASTIC_C4) + 1.0
    )


def ease_in_out_elastic(t: float) -> float:
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0
    if t < 0.5:
        return -(
            math.pow(2.0, 20.0 * t - 10.0)
            * math.sin((20.0 * t - 11.125) * _ELASTIC_C5)
        ) / 2.0
    return (
        math.pow(2.0, -20.0 * t + 10.0)
        * math.sin((20.0 * t - 11.125) * _ELASTIC_C5)
    ) / 2.0 + 1.0


# ---------------------------------------------------------------------------
# Back family  (overshoot)
# ---------------------------------------------------------------------------

_BACK_C1 = 1.70158
_BACK_C2 = _BACK_C1 * 1.525
_BACK_C3 = _BACK_C1 + 1.0


def ease_in_back(t: float) -> float:
    return _BACK_C3 * t * t * t - _BACK_C1 * t * t


def ease_out_back(t: float) -> float:
    t1 = t - 1.0
    return 1.0 + _BACK_C3 * t1 * t1 * t1 + _BACK_C1 * t1 * t1


def ease_in_out_back(t: float) -> float:
    if t < 0.5:
        t2 = 2.0 * t
        return (t2 * t2 * ((_BACK_C2 + 1.0) * 2.0 * t - _BACK_C2)) / 2.0
    t2 = 2.0 * t - 2.0
    return (t2 * t2 * ((_BACK_C2 + 1.0) * t2 + _BACK_C2) + 2.0) / 2.0


# ---------------------------------------------------------------------------
# Bounce family
# ---------------------------------------------------------------------------

_BOUNCE_N1 = 7.5625
_BOUNCE_D1 = 2.75


def ease_out_bounce(t: float) -> float:
    if t < 1.0 / _BOUNCE_D1:
        return _BOUNCE_N1 * t * t
    elif t < 2.0 / _BOUNCE_D1:
        t -= 1.5 / _BOUNCE_D1
        return _BOUNCE_N1 * t * t + 0.75
    elif t < 2.5 / _BOUNCE_D1:
        t -= 2.25 / _BOUNCE_D1
        return _BOUNCE_N1 * t * t + 0.9375
    else:
        t -= 2.625 / _BOUNCE_D1
        return _BOUNCE_N1 * t * t + 0.984375


def ease_in_bounce(t: float) -> float:
    return 1.0 - ease_out_bounce(1.0 - t)


def ease_in_out_bounce(t: float) -> float:
    if t < 0.5:
        return (1.0 - ease_out_bounce(1.0 - 2.0 * t)) / 2.0
    return (1.0 + ease_out_bounce(2.0 * t - 1.0)) / 2.0


# ---------------------------------------------------------------------------
# cubic_bezier — CSS-style cubic Bézier curve
# ---------------------------------------------------------------------------

def cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> Callable[[float], float]:
    """Return a callable easing function defined by two cubic Bézier control points.

    The curve always passes through (0, 0) and (1, 1); (x1, y1) and (x2, y2)
    are the interior control points. x1 and x2 must be in [0, 1].

    Uses Newton-Raphson iteration to solve for the parametric t given the x
    input, then evaluates y at that t.
    """

    def _bezier_x(t: float) -> float:
        mt = 1.0 - t
        return 3.0 * mt * mt * t * x1 + 3.0 * mt * t * t * x2 + t * t * t

    def _bezier_y(t: float) -> float:
        mt = 1.0 - t
        return 3.0 * mt * mt * t * y1 + 3.0 * mt * t * t * y2 + t * t * t

    def _bezier_dx(t: float) -> float:
        mt = 1.0 - t
        return 3.0 * mt * mt * x1 + 6.0 * mt * t * (x2 - x1) + 3.0 * t * t * (1.0 - x2)

    def _solve_t(x: float) -> float:
        """Newton-Raphson to find t such that bezier_x(t) == x."""
        if x <= 0.0:
            return 0.0
        if x >= 1.0:
            return 1.0
        # Initial guess
        t = x
        for _ in range(8):
            x_t = _bezier_x(t)
            dx = _bezier_dx(t)
            if abs(dx) < 1e-12:
                break
            t -= (x_t - x) / dx
            t = max(0.0, min(1.0, t))
        return t

    def easing(x: float) -> float:
        if x <= 0.0:
            return 0.0
        if x >= 1.0:
            return 1.0
        return _bezier_y(_solve_t(x))

    return easing


# ---------------------------------------------------------------------------
# spring — damped harmonic oscillator
# ---------------------------------------------------------------------------

def spring(
    tension: float = 170.0,
    friction: float = 26.0,
    mass: float = 1.0,
) -> Callable[[float], float]:
    """Return a callable spring easing function.

    Simulates a damped harmonic oscillator from 0 to 1 using Euler integration.
    The trajectory is pre-computed over [0, 1] at 1000 steps and queries are
    answered via linear interpolation.

    Args:
        tension: Spring stiffness (higher = faster, more oscillation).
        friction: Damping coefficient (higher = less oscillation).
        mass: Mass of the object (higher = slower).

    Returns:
        Callable mapping t ∈ [0, 1] → position (may overshoot 1).
    """
    # Simulate with small time steps until the spring settles
    # We simulate for enough time to ensure settlement, then normalize to [0, 1].
    dt = 0.001
    steps = 2000  # simulate 2 seconds at dt=0.001

    positions: list[float] = [0.0]
    velocity = 0.0
    position = 0.0
    target = 1.0

    for _ in range(steps - 1):
        spring_force = tension * (target - position)
        damping_force = friction * velocity
        acceleration = (spring_force - damping_force) / mass
        velocity += acceleration * dt
        position += velocity * dt
        positions.append(position)

    # Detect settling: find the last index where |pos - 1| > threshold
    threshold = 0.001
    settle_idx = steps - 1
    for i in range(steps - 1, -1, -1):
        if abs(positions[i] - 1.0) > threshold:
            settle_idx = i + 1
            break
    # Ensure we capture enough of the motion
    settle_idx = max(settle_idx, int(0.1 * steps))
    # Clamp to valid range
    settle_idx = min(settle_idx, steps - 1)

    # Remap the trajectory to t=[0,1]
    trajectory = positions[: settle_idx + 1]
    n = len(trajectory)

    # Force exact boundary values
    trajectory[0] = 0.0

    def easing(t: float) -> float:
        if t <= 0.0:
            return 0.0
        if t >= 1.0:
            return trajectory[-1]
        idx_f = t * (n - 1)
        idx_lo = int(idx_f)
        idx_hi = min(idx_lo + 1, n - 1)
        frac = idx_f - idx_lo
        return trajectory[idx_lo] + frac * (trajectory[idx_hi] - trajectory[idx_lo])

    return easing


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _linear(t: float) -> float:
    return t


EASING_FUNCTIONS: dict[str, Callable[[float], float]] = {
    "linear": _linear,
    # Sine
    "ease_in_sine": ease_in_sine,
    "ease_out_sine": ease_out_sine,
    "ease_in_out_sine": ease_in_out_sine,
    # Quad
    "ease_in_quad": ease_in_quad,
    "ease_out_quad": ease_out_quad,
    "ease_in_out_quad": ease_in_out_quad,
    # Cubic
    "ease_in_cubic": ease_in_cubic,
    "ease_out_cubic": ease_out_cubic,
    "ease_in_out_cubic": ease_in_out_cubic,
    # Quartic
    "ease_in_quart": ease_in_quart,
    "ease_out_quart": ease_out_quart,
    "ease_in_out_quart": ease_in_out_quart,
    # Quintic
    "ease_in_quint": ease_in_quint,
    "ease_out_quint": ease_out_quint,
    "ease_in_out_quint": ease_in_out_quint,
    # Exponential
    "ease_in_expo": ease_in_expo,
    "ease_out_expo": ease_out_expo,
    "ease_in_out_expo": ease_in_out_expo,
    # Circular
    "ease_in_circ": ease_in_circ,
    "ease_out_circ": ease_out_circ,
    "ease_in_out_circ": ease_in_out_circ,
    # Elastic
    "ease_in_elastic": ease_in_elastic,
    "ease_out_elastic": ease_out_elastic,
    "ease_in_out_elastic": ease_in_out_elastic,
    # Back
    "ease_in_back": ease_in_back,
    "ease_out_back": ease_out_back,
    "ease_in_out_back": ease_in_out_back,
    # Bounce
    "ease_in_bounce": ease_in_bounce,
    "ease_out_bounce": ease_out_bounce,
    "ease_in_out_bounce": ease_in_out_bounce,
}


def get_easing(name: str) -> Callable[[float], float]:
    """Look up an easing function by name.

    Args:
        name: One of the names in EASING_FUNCTIONS.

    Returns:
        The corresponding easing function.

    Raises:
        ValueError: If name is not found in the registry.
    """
    try:
        return EASING_FUNCTIONS[name]
    except KeyError:
        available = sorted(EASING_FUNCTIONS.keys())
        raise ValueError(
            f"Unknown easing '{name}'. Available: {available}"
        ) from None
