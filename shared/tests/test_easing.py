"""Tests for shared/motion_math/easing.py

TDD: Write tests first, then implement.
"""
import math
import pytest
from motion_math.easing import (
    # Sine
    ease_in_sine, ease_out_sine, ease_in_out_sine,
    # Quad
    ease_in_quad, ease_out_quad, ease_in_out_quad,
    # Cubic
    ease_in_cubic, ease_out_cubic, ease_in_out_cubic,
    # Quartic
    ease_in_quart, ease_out_quart, ease_in_out_quart,
    # Quintic
    ease_in_quint, ease_out_quint, ease_in_out_quint,
    # Exponential
    ease_in_expo, ease_out_expo, ease_in_out_expo,
    # Circular
    ease_in_circ, ease_out_circ, ease_in_out_circ,
    # Elastic
    ease_in_elastic, ease_out_elastic, ease_in_out_elastic,
    # Back
    ease_in_back, ease_out_back, ease_in_out_back,
    # Bounce
    ease_in_bounce, ease_out_bounce, ease_in_out_bounce,
    # Advanced
    cubic_bezier, spring,
    # Registry
    EASING_FUNCTIONS, get_easing,
)

# All 30 Penner functions
ALL_30 = [
    ease_in_sine, ease_out_sine, ease_in_out_sine,
    ease_in_quad, ease_out_quad, ease_in_out_quad,
    ease_in_cubic, ease_out_cubic, ease_in_out_cubic,
    ease_in_quart, ease_out_quart, ease_in_out_quart,
    ease_in_quint, ease_out_quint, ease_in_out_quint,
    ease_in_expo, ease_out_expo, ease_in_out_expo,
    ease_in_circ, ease_out_circ, ease_in_out_circ,
    ease_in_elastic, ease_out_elastic, ease_in_out_elastic,
    ease_in_back, ease_out_back, ease_in_out_back,
    ease_in_bounce, ease_out_bounce, ease_in_out_bounce,
]

ALL_30_NAMES = [
    "ease_in_sine", "ease_out_sine", "ease_in_out_sine",
    "ease_in_quad", "ease_out_quad", "ease_in_out_quad",
    "ease_in_cubic", "ease_out_cubic", "ease_in_out_cubic",
    "ease_in_quart", "ease_out_quart", "ease_in_out_quart",
    "ease_in_quint", "ease_out_quint", "ease_in_out_quint",
    "ease_in_expo", "ease_out_expo", "ease_in_out_expo",
    "ease_in_circ", "ease_out_circ", "ease_in_out_circ",
    "ease_in_elastic", "ease_out_elastic", "ease_in_out_elastic",
    "ease_in_back", "ease_out_back", "ease_in_out_back",
    "ease_in_bounce", "ease_out_bounce", "ease_in_out_bounce",
]


class TestPennerBoundaryConditions:
    """All 30 Penner easing functions must satisfy f(0)≈0, f(1)≈1."""

    @pytest.mark.parametrize("fn", ALL_30, ids=[fn.__name__ for fn in ALL_30])
    def test_f0_equals_0(self, fn):
        result = fn(0.0)
        assert abs(result) < 1e-9, f"{fn.__name__}(0) = {result}, expected 0"

    @pytest.mark.parametrize("fn", ALL_30, ids=[fn.__name__ for fn in ALL_30])
    def test_f1_equals_1(self, fn):
        result = fn(1.0)
        assert abs(result - 1.0) < 1e-9, f"{fn.__name__}(1) = {result}, expected 1"


class TestPennerMidpoint:
    """ease_in_out functions should be near 0.5 at t=0.5 (symmetry)."""

    IN_OUT_FUNS = [
        ease_in_out_sine, ease_in_out_quad, ease_in_out_cubic,
        ease_in_out_quart, ease_in_out_quint, ease_in_out_expo,
        ease_in_out_circ, ease_in_out_back, ease_in_out_bounce,
    ]

    @pytest.mark.parametrize(
        "fn",
        IN_OUT_FUNS,
        ids=[fn.__name__ for fn in IN_OUT_FUNS],
    )
    def test_midpoint_near_half(self, fn):
        result = fn(0.5)
        assert abs(result - 0.5) < 0.01, (
            f"{fn.__name__}(0.5) = {result}, expected ~0.5"
        )


class TestPennerKnownValues:
    """Spot-check specific well-known values from Penner formulas."""

    def test_ease_in_quad_half(self):
        assert abs(ease_in_quad(0.5) - 0.25) < 1e-9

    def test_ease_out_quad_half(self):
        assert abs(ease_out_quad(0.5) - 0.75) < 1e-9

    def test_ease_in_cubic_half(self):
        assert abs(ease_in_cubic(0.5) - 0.125) < 1e-9

    def test_ease_out_cubic_half(self):
        assert abs(ease_out_cubic(0.5) - 0.875) < 1e-9

    def test_ease_in_quart_half(self):
        assert abs(ease_in_quart(0.5) - 0.0625) < 1e-9

    def test_ease_out_quart_half(self):
        assert abs(ease_out_quart(0.5) - 0.9375) < 1e-9

    def test_ease_in_quint_half(self):
        assert abs(ease_in_quint(0.5) - 0.03125) < 1e-9

    def test_ease_out_quint_half(self):
        assert abs(ease_out_quint(0.5) - 0.96875) < 1e-9

    def test_ease_in_sine_quarter(self):
        # ease_in_sine(0.5) = 1 - cos(pi/4) = 1 - sqrt(2)/2
        expected = 1.0 - math.cos(math.pi * 0.5 / 2.0)
        assert abs(ease_in_sine(0.5) - expected) < 1e-9

    def test_ease_out_sine_quarter(self):
        # ease_out_sine(0.5) = sin(pi/4) = sqrt(2)/2
        expected = math.sin(math.pi * 0.5 / 2.0)
        assert abs(ease_out_sine(0.5) - expected) < 1e-9


class TestEaseInMonotonicity:
    """Simple ease_in functions (no overshoot) must be monotonically increasing."""

    # ease_in_bounce is intentionally excluded: bounce is non-monotone by design
    # (it has local dips that simulate a physical bounce).
    SIMPLE_EASE_IN = [
        ease_in_sine, ease_in_quad, ease_in_cubic,
        ease_in_quart, ease_in_quint, ease_in_circ,
    ]

    @pytest.mark.parametrize(
        "fn",
        SIMPLE_EASE_IN,
        ids=[fn.__name__ for fn in SIMPLE_EASE_IN],
    )
    def test_monotonically_increasing(self, fn):
        ts = [i / 100 for i in range(101)]
        values = [fn(t) for t in ts]
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1] - 1e-9, (
                f"{fn.__name__} not monotonic at t={ts[i]}: "
                f"{values[i-1]} -> {values[i]}"
            )


class TestCubicBezier:
    """Tests for cubic_bezier(x1, y1, x2, y2) -> callable."""

    def test_linear_bezier(self):
        """Linear bezier (0,0,1,1) should give f(t) ≈ t."""
        linear = cubic_bezier(0.0, 0.0, 1.0, 1.0)
        for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
            assert abs(linear(t) - t) < 1e-3, (
                f"linear bezier({t}) = {linear(t)}, expected {t}"
            )

    def test_boundary_conditions(self):
        """Any bezier must satisfy f(0)=0, f(1)=1."""
        ease = cubic_bezier(0.25, 0.1, 0.25, 1.0)
        assert abs(ease(0.0)) < 1e-9
        assert abs(ease(1.0) - 1.0) < 1e-9

    def test_css_ease(self):
        """CSS 'ease' is cubic_bezier(0.25, 0.1, 0.25, 1.0).
        At t=0.5 it should be notably above 0.5 (ease-in-out style)."""
        css_ease = cubic_bezier(0.25, 0.1, 0.25, 1.0)
        mid = css_ease(0.5)
        # CSS ease is faster at start, so at t=0.5 result should be > 0.5
        assert mid > 0.5, f"CSS ease at 0.5 = {mid}, expected > 0.5"

    def test_overshoot_bezier(self):
        """Bezier with y > 1 control points can overshoot."""
        overshoot = cubic_bezier(0.42, 0.0, 0.58, 1.5)
        # Should still have correct boundaries
        assert abs(overshoot(0.0)) < 1e-9
        assert abs(overshoot(1.0) - 1.0) < 1e-9
        # At some point in the middle it should exceed 1
        values = [overshoot(t / 100) for t in range(101)]
        assert max(values) > 1.0, "Expected overshoot above 1.0"

    def test_monotonicity_standard(self):
        """Standard bezier (x controls only, no y overshoot) should be monotone."""
        ease_in_out = cubic_bezier(0.42, 0.0, 0.58, 1.0)
        values = [ease_in_out(t / 100) for t in range(101)]
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1] - 1e-6, (
                f"cubic_bezier not monotone at index {i}: "
                f"{values[i-1]:.4f} -> {values[i]:.4f}"
            )


class TestSpring:
    """Tests for spring(tension, friction, mass) -> callable."""

    def test_boundary_conditions(self):
        """Spring must start at 0 and settle near 1."""
        fn = spring(tension=170, friction=26, mass=1.0)
        assert abs(fn(0.0)) < 0.05, f"spring(0) = {fn(0.0)}, expected ~0"
        assert abs(fn(1.0) - 1.0) < 0.05, f"spring(1) = {fn(1.0)}, expected ~1"

    def test_overshoot_low_friction(self):
        """With very low friction, spring should overshoot 1.0 somewhere."""
        fn = spring(tension=300, friction=10, mass=1.0)
        values = [fn(t / 100) for t in range(101)]
        assert max(values) > 1.0, "Expected spring overshoot with low friction"

    def test_critically_damped_no_overshoot(self):
        """High friction (overdamped) spring should not overshoot significantly."""
        fn = spring(tension=200, friction=60, mass=1.0)
        values = [fn(t / 100) for t in range(101)]
        max_val = max(values)
        assert max_val <= 1.05, (
            f"Overdamped spring should not overshoot: max={max_val}"
        )

    def test_monotone_rising_overdamped(self):
        """Overdamped spring should be mostly monotone (may have tiny numerical noise)."""
        fn = spring(tension=200, friction=60, mass=1.0)
        values = [fn(t / 200) for t in range(201)]
        # Allow 2% tolerance
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1] - 0.02, (
                f"Overdamped spring not monotone at index {i}: "
                f"{values[i-1]:.4f} -> {values[i]:.4f}"
            )

    def test_settles_near_1(self):
        """At t=1 spring should have settled close to 1."""
        fn = spring(tension=170, friction=26, mass=1.0)
        end = fn(1.0)
        assert abs(end - 1.0) < 0.02, f"spring(1.0) = {end}, expected ~1.0"


class TestGetEasing:
    """Tests for get_easing(name) and EASING_FUNCTIONS registry."""

    def test_lookup_by_name(self):
        fn = get_easing("ease_in_quad")
        assert callable(fn)
        assert abs(fn(0.5) - 0.25) < 1e-9

    def test_lookup_linear(self):
        fn = get_easing("linear")
        assert callable(fn)
        assert abs(fn(0.5) - 0.5) < 1e-9
        assert abs(fn(0.0)) < 1e-9
        assert abs(fn(1.0) - 1.0) < 1e-9

    def test_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown easing"):
            get_easing("not_a_real_easing")

    def test_all_30_in_registry(self):
        for name in ALL_30_NAMES:
            assert name in EASING_FUNCTIONS, f"'{name}' missing from EASING_FUNCTIONS"

    def test_registry_has_31_plus_entries(self):
        # 30 Penner + at least "linear"
        assert len(EASING_FUNCTIONS) >= 31

    def test_all_registry_functions_callable(self):
        for name, fn in EASING_FUNCTIONS.items():
            assert callable(fn), f"EASING_FUNCTIONS['{name}'] is not callable"

    def test_all_registry_functions_boundary(self):
        """All named functions in registry satisfy f(0)=0, f(1)=1."""
        for name, fn in EASING_FUNCTIONS.items():
            v0 = fn(0.0)
            v1 = fn(1.0)
            assert abs(v0) < 1e-9, f"{name}(0) = {v0}"
            assert abs(v1 - 1.0) < 1e-9, f"{name}(1) = {v1}"
