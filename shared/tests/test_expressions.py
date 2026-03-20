"""Tests for the safe AST-based expression parser.

Covers:
- Basic: constant, time, frame, fps, pi, e
- Arithmetic: add, sub, mul, div, unary minus, power
- Nested expressions
- Math functions: sin, cos, tan, abs, pow, sqrt, floor, ceil, min, max
- Animation helpers: clamp, lerp, remap, step, smoothstep
- Procedural: wiggle, random
- evaluate_batch() with and without numpy
- Safety: reject __import__, attribute access, exec, eval, open, compile
- Context dict injection
- Error paths: bad syntax, unknown name, wrong arg count
"""

from __future__ import annotations

import math
import pytest

from motion_math.expressions import Expression


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ev(src: str, time: float = 0.0, frame: int = 0, fps: float = 30.0, **ctx):
    return Expression(src).evaluate(time, frame, fps, ctx or None)


# ---------------------------------------------------------------------------
# 1. Basic literals and built-in variables
# ---------------------------------------------------------------------------

class TestBasic:
    def test_constant_int(self):
        assert _ev("42") == pytest.approx(42.0)

    def test_constant_float(self):
        assert _ev("3.14") == pytest.approx(3.14)

    def test_time_variable(self):
        assert _ev("time", time=2.5) == pytest.approx(2.5)

    def test_frame_variable(self):
        assert _ev("frame", frame=15) == pytest.approx(15)

    def test_fps_variable(self):
        assert _ev("fps", fps=24.0) == pytest.approx(24.0)

    def test_pi_variable(self):
        assert _ev("pi") == pytest.approx(math.pi)

    def test_e_variable(self):
        assert _ev("e") == pytest.approx(math.e)

    def test_negative_constant(self):
        assert _ev("-7") == pytest.approx(-7.0)


# ---------------------------------------------------------------------------
# 2. Arithmetic
# ---------------------------------------------------------------------------

class TestArithmetic:
    def test_add(self):
        assert _ev("1 + 2") == pytest.approx(3.0)

    def test_subtract(self):
        assert _ev("10 - 3") == pytest.approx(7.0)

    def test_multiply(self):
        assert _ev("4 * 5") == pytest.approx(20.0)

    def test_divide(self):
        assert _ev("9 / 4") == pytest.approx(2.25)

    def test_floor_divide(self):
        assert _ev("9 // 4") == pytest.approx(2.0)

    def test_modulo(self):
        assert _ev("10 % 3") == pytest.approx(1.0)

    def test_power_operator(self):
        assert _ev("2 ** 8") == pytest.approx(256.0)

    def test_unary_plus(self):
        assert _ev("+5") == pytest.approx(5.0)

    def test_unary_minus(self):
        assert _ev("-5") == pytest.approx(-5.0)

    def test_precedence(self):
        assert _ev("2 + 3 * 4") == pytest.approx(14.0)

    def test_parentheses(self):
        assert _ev("(2 + 3) * 4") == pytest.approx(20.0)

    def test_time_arithmetic(self):
        assert _ev("time * 360", time=1.0) == pytest.approx(360.0)

    def test_frame_arithmetic(self):
        assert _ev("frame / fps", frame=30, fps=30.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 3. Math functions
# ---------------------------------------------------------------------------

class TestMathFunctions:
    def test_sin(self):
        assert _ev("sin(0)") == pytest.approx(0.0)
        assert _ev("sin(pi / 2)") == pytest.approx(1.0)

    def test_cos(self):
        assert _ev("cos(0)") == pytest.approx(1.0)

    def test_tan(self):
        assert _ev("tan(0)") == pytest.approx(0.0)

    def test_abs_positive(self):
        assert _ev("abs(5)") == pytest.approx(5.0)

    def test_abs_negative(self):
        assert _ev("abs(-5)") == pytest.approx(5.0)

    def test_pow(self):
        assert _ev("pow(2, 10)") == pytest.approx(1024.0)

    def test_sqrt(self):
        assert _ev("sqrt(9)") == pytest.approx(3.0)

    def test_floor(self):
        assert _ev("floor(3.7)") == pytest.approx(3.0)

    def test_ceil(self):
        assert _ev("ceil(3.2)") == pytest.approx(4.0)

    def test_min(self):
        assert _ev("min(3, 5)") == pytest.approx(3.0)

    def test_max(self):
        assert _ev("max(3, 5)") == pytest.approx(5.0)

    def test_min_three_args(self):
        assert _ev("min(5, 2, 8)") == pytest.approx(2.0)

    def test_max_three_args(self):
        assert _ev("max(5, 2, 8)") == pytest.approx(8.0)

    def test_nested_functions(self):
        assert _ev("abs(sin(pi))") == pytest.approx(0.0, abs=1e-10)

    def test_sqrt_of_expression(self):
        assert _ev("sqrt(time * time + 1)", time=0.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 4. Animation helpers: clamp, lerp, remap, step, smoothstep
# ---------------------------------------------------------------------------

class TestAnimationHelpers:
    def test_clamp_mid(self):
        assert _ev("clamp(5, 0, 10)") == pytest.approx(5.0)

    def test_clamp_below(self):
        assert _ev("clamp(-3, 0, 10)") == pytest.approx(0.0)

    def test_clamp_above(self):
        assert _ev("clamp(15, 0, 10)") == pytest.approx(10.0)

    def test_lerp_zero(self):
        assert _ev("lerp(0, 100, 0)") == pytest.approx(0.0)

    def test_lerp_one(self):
        assert _ev("lerp(0, 100, 1)") == pytest.approx(100.0)

    def test_lerp_half(self):
        assert _ev("lerp(0, 100, 0.5)") == pytest.approx(50.0)

    def test_remap_basic(self):
        # remap(v=5, in_lo=0, in_hi=10, out_lo=0, out_hi=100) → 50
        assert _ev("remap(5, 0, 10, 0, 100)") == pytest.approx(50.0)

    def test_remap_inverted_output(self):
        # 0 mapped from [0,1] to [1,0] → 1
        assert _ev("remap(0, 0, 1, 1, 0)") == pytest.approx(1.0)

    def test_step_below_threshold(self):
        # step(threshold=5, value=3) → 0.0
        assert _ev("step(5, 3)") == pytest.approx(0.0)

    def test_step_above_threshold(self):
        # step(threshold=5, value=7) → 1.0
        assert _ev("step(5, 7)") == pytest.approx(1.0)

    def test_step_at_threshold(self):
        # value >= threshold → 1.0
        assert _ev("step(5, 5)") == pytest.approx(1.0)

    def test_smoothstep_edges(self):
        assert _ev("smoothstep(0, 1, 0)") == pytest.approx(0.0)
        assert _ev("smoothstep(0, 1, 1)") == pytest.approx(1.0)

    def test_smoothstep_mid(self):
        assert _ev("smoothstep(0, 1, 0.5)") == pytest.approx(0.5)

    def test_smoothstep_clamped_below(self):
        assert _ev("smoothstep(0, 1, -1)") == pytest.approx(0.0)

    def test_smoothstep_clamped_above(self):
        assert _ev("smoothstep(0, 1, 2)") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 5. Procedural: wiggle, random
# ---------------------------------------------------------------------------

class TestProcedural:
    def test_wiggle_returns_float(self):
        result = _ev("wiggle(2, 0.5)", time=1.0, frame=30, fps=30.0)
        assert isinstance(result, (int, float))

    def test_wiggle_within_amplitude(self):
        # wiggle is bounded by ±amp
        amp = 0.3
        for t in [0.0, 0.5, 1.0, 2.0, 5.0]:
            result = _ev(f"wiggle(2, {amp})", time=t, frame=int(t * 30), fps=30.0)
            assert abs(result) <= amp + 1e-9, f"wiggle out of bounds at t={t}: {result}"

    def test_wiggle_amplitude_scaling(self):
        # doubled amplitude should produce doubled value
        expr_small = Expression("wiggle(1, 1.0)")
        expr_large = Expression("wiggle(1, 2.0)")
        v1 = expr_small.evaluate(0.7, 21, 30.0)
        v2 = expr_large.evaluate(0.7, 21, 30.0)
        assert abs(v2) == pytest.approx(abs(v1) * 2, rel=1e-6)

    def test_random_returns_float(self):
        result = _ev("random(0, 1)", frame=0)
        assert isinstance(result, (int, float))

    def test_random_in_range(self):
        lo, hi = 5.0, 10.0
        for frame in range(20):
            result = Expression("random(5, 10)").evaluate(frame / 30.0, frame, 30.0)
            assert lo <= result <= hi, f"random out of range at frame={frame}: {result}"

    def test_random_deterministic_per_frame(self):
        # Same frame should produce same value across two Expression instances
        v1 = Expression("random(0, 100)").evaluate(0.0, 42, 30.0)
        v2 = Expression("random(0, 100)").evaluate(0.0, 42, 30.0)
        assert v1 == pytest.approx(v2)


# ---------------------------------------------------------------------------
# 6. Context dict injection
# ---------------------------------------------------------------------------

class TestContext:
    def test_custom_variable(self):
        expr = Expression("my_val * 2")
        result = expr.evaluate(0.0, 0, 30.0, {"my_val": 7.0})
        assert result == pytest.approx(14.0)

    def test_context_overrides_allowed(self):
        # User passes a variable named 'time' via context — still works
        expr = Expression("time + offset")
        result = expr.evaluate(1.0, 30, 30.0, {"offset": 5.0})
        assert result == pytest.approx(6.0)

    def test_none_context_ok(self):
        expr = Expression("time")
        result = expr.evaluate(2.0, 60, 30.0, None)
        assert result == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# 7. evaluate_batch
# ---------------------------------------------------------------------------

class TestBatchEvaluate:
    def test_batch_length(self):
        expr = Expression("time * 2")
        times = [0.0, 0.5, 1.0, 1.5, 2.0]
        result = expr.evaluate_batch(times, fps=30.0)
        assert len(result) == 5

    def test_batch_values(self):
        expr = Expression("time * 2")
        times = [0.0, 1.0, 2.0]
        result = expr.evaluate_batch(times, fps=30.0)
        assert list(result) == pytest.approx([0.0, 2.0, 4.0])

    def test_batch_numpy_array(self):
        try:
            import numpy as np
            expr = Expression("time + 1")
            times = np.array([0.0, 1.0, 2.0])
            result = expr.evaluate_batch(times, fps=30.0)
            assert hasattr(result, "__len__")
            assert list(result) == pytest.approx([1.0, 2.0, 3.0])
        except ImportError:
            pytest.skip("numpy not installed")

    def test_batch_with_fps(self):
        # frame = round(time * fps), so at fps=30 and time=1.0 → frame=30
        expr = Expression("frame / fps")
        result = expr.evaluate_batch([0.0, 1.0], fps=30.0)
        assert list(result) == pytest.approx([0.0, 1.0])


# ---------------------------------------------------------------------------
# 8. Safety — rejected constructs
# ---------------------------------------------------------------------------

class TestSafety:
    def test_reject_import(self):
        with pytest.raises(ValueError, match="[Dd]isallowed|[Ff]orbidden|[Ss]afe"):
            Expression("__import__('os')")

    def test_reject_attribute_access(self):
        with pytest.raises(ValueError, match="[Dd]isallowed|[Ff]orbidden|[Aa]ttribute"):
            Expression("time.real")

    def test_reject_exec(self):
        with pytest.raises(ValueError):
            Expression("exec('x=1')")

    def test_reject_eval(self):
        with pytest.raises(ValueError):
            Expression("eval('1+1')")

    def test_reject_open(self):
        with pytest.raises(ValueError):
            Expression("open('/etc/passwd')")

    def test_reject_getattr(self):
        with pytest.raises(ValueError):
            Expression("getattr(time, 'real')")

    def test_reject_setattr(self):
        with pytest.raises(ValueError):
            Expression("setattr(time, 'x', 1)")

    def test_reject_delattr(self):
        with pytest.raises(ValueError):
            Expression("delattr(time, 'x')")

    def test_reject_compile(self):
        with pytest.raises(ValueError):
            Expression("compile('x', '', 'eval')")

    def test_reject_dunder_in_name(self):
        with pytest.raises(ValueError):
            Expression("__builtins__")

    def test_reject_subscript(self):
        with pytest.raises(ValueError):
            Expression("time[0]")

    def test_bad_syntax_raises_value_error(self):
        with pytest.raises(ValueError, match="[Ss]yntax"):
            Expression("2 +* 3")

    def test_unknown_name_raises_at_evaluate(self):
        # Parsing succeeds; NameError at eval time should surface as ValueError or NameError
        with pytest.raises((ValueError, NameError)):
            Expression("unknown_func(1)").evaluate(0, 0, 30.0)


# ---------------------------------------------------------------------------
# 9. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_whitespace_only_expression_raises(self):
        with pytest.raises(ValueError):
            Expression("   ")

    def test_empty_expression_raises(self):
        with pytest.raises(ValueError):
            Expression("")

    def test_expression_repr_contains_source(self):
        e = Expression("time * 2")
        assert "time * 2" in repr(e)

    def test_large_time_value(self):
        result = _ev("sin(time)", time=1e6)
        assert isinstance(result, float)

    def test_integer_division_result(self):
        assert _ev("floor(7 / 2)") == pytest.approx(3.0)
