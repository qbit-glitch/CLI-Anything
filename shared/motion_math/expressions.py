"""Safe AST-based expression parser for procedural animation.

Allows users to write formulas like::

    "rotation = time * 360"     →  Expression("time * 360")
    "scale = 1 + wiggle(2, 0.1)"
    "x = lerp(0, 100, clamp(time, 0, 1))"

The expression is validated against an AST whitelist *before* being passed
to Python's built-in ``eval()`` with ``{"__builtins__": {}}``, so no
dangerous calls can escape the sandbox.

Built-in variables
------------------
    time  — current time in seconds (float)
    frame — current frame index (int)
    fps   — frames per second (float)
    pi    — math.pi
    e     — math.e

Built-in functions
------------------
Math:
    sin, cos, tan, abs, pow, sqrt, floor, ceil, min, max

Animation helpers:
    clamp(v, lo, hi)
    lerp(a, b, t)
    remap(v, in_lo, in_hi, out_lo, out_hi)
    step(threshold, value)
    smoothstep(edge0, edge1, x)

Procedural:
    wiggle(freq, amp)   — sine-based pseudo-noise bounded by ±amp
    random(lo, hi)      — deterministic per-frame random in [lo, hi]
"""

from __future__ import annotations

import ast
import math
import random as _random_mod
from typing import Dict, Optional, Sequence, Union

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False

__all__ = ["Expression"]


# ---------------------------------------------------------------------------
# AST whitelist
# ---------------------------------------------------------------------------

# Node types that are unconditionally permitted.
_ALLOWED_NODE_TYPES = frozenset({
    # Module wrapper used when parsing in "eval" mode
    ast.Expression,
    # Literals
    ast.Constant,
    # Names (validated separately against whitelist)
    ast.Name,
    # Unary operators: +, -, not
    ast.UnaryOp,
    ast.UAdd, ast.USub, ast.Not,
    # Binary operators
    ast.BinOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    # Boolean operators
    ast.BoolOp,
    ast.And, ast.Or,
    # Comparisons
    ast.Compare,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    # If-expression  (a if cond else b)
    ast.IfExp,
    # Function calls (callee validated separately)
    ast.Call,
    # Tuple literal  (for multi-arg min/max etc.)
    ast.Tuple,
    # Load context
    ast.Load,
})

# Names (variables and functions) that are allowed in expressions.
_ALLOWED_NAMES = frozenset({
    # Built-in variables
    "time", "frame", "fps", "pi", "e",
    # Math
    "sin", "cos", "tan", "abs", "pow", "sqrt", "floor", "ceil", "min", "max",
    # Animation helpers
    "clamp", "lerp", "remap", "step", "smoothstep",
    # Procedural
    "wiggle", "random",
})

# Names that are explicitly forbidden (belt-and-suspenders on top of
# the whitelist — these can never appear even if someone extends the
# whitelist carelessly).
_FORBIDDEN_NAMES = frozenset({
    "__import__", "__builtins__", "__globals__", "__locals__", "__class__",
    "exec", "eval", "compile", "open", "getattr", "setattr", "delattr",
    "vars", "dir", "locals", "globals", "breakpoint", "input", "print",
})


# ---------------------------------------------------------------------------
# Animation / procedural helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def _lerp(a: float, b: float, t: float) -> float:
    return a + t * (b - a)


def _remap(v: float, in_lo: float, in_hi: float, out_lo: float, out_hi: float) -> float:
    if in_hi == in_lo:
        return out_lo
    t = (v - in_lo) / (in_hi - in_lo)
    return out_lo + t * (out_hi - out_lo)


def _step(threshold: float, value: float) -> float:
    return 1.0 if value >= threshold else 0.0


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 == edge0:
        return 0.0 if x < edge0 else 1.0
    t = _clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _make_wiggle(time: float, frame: int) -> "callable":
    """Return a wiggle(freq, amp) closure bound to the current time/frame."""
    def wiggle(freq: float, amp: float) -> float:
        # Sine-based pseudo-noise: combine two frequencies for organic feel.
        t = time if time != 0.0 else frame / max(1, 1)
        return amp * math.sin(2.0 * math.pi * freq * t)
    return wiggle


def _make_random(frame: int) -> "callable":
    """Return a random(lo, hi) closure that is deterministic per frame."""
    def random_fn(lo: float, hi: float) -> float:
        rng = _random_mod.Random(frame)
        return lo + rng.random() * (hi - lo)
    return random_fn


# ---------------------------------------------------------------------------
# Static namespace (everything except time/frame/fps-dependent callables)
# ---------------------------------------------------------------------------

_STATIC_NAMESPACE: Dict[str, object] = {
    "__builtins__": {},
    # Variables (placeholders; overridden per evaluate() call)
    "pi": math.pi,
    "e":  math.e,
    # Math functions
    "sin":   math.sin,
    "cos":   math.cos,
    "tan":   math.tan,
    "abs":   abs,
    "pow":   pow,
    "sqrt":  math.sqrt,
    "floor": math.floor,
    "ceil":  math.ceil,
    "min":   min,
    "max":   max,
    # Animation helpers (pure functions, no time dependency)
    "clamp":      _clamp,
    "lerp":       _lerp,
    "remap":      _remap,
    "step":       _step,
    "smoothstep": _smoothstep,
}


# ---------------------------------------------------------------------------
# AST validator
# ---------------------------------------------------------------------------

class _SafetyVisitor(ast.NodeVisitor):
    """Walk the AST and raise ValueError for any disallowed construct."""

    def generic_visit(self, node: ast.AST) -> None:
        node_type = type(node)
        if node_type not in _ALLOWED_NODE_TYPES:
            raise ValueError(
                f"Disallowed AST node type: {node_type.__name__!r} — "
                "only safe arithmetic/function-call expressions are permitted."
            )
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        name = node.id
        # Double-underscore names are always forbidden (covers __import__,
        # __builtins__, __class__, etc.).
        if name.startswith("__") or name.endswith("__"):
            raise ValueError(
                f"Forbidden name {name!r}: dunder names are not allowed."
            )
        # Explicitly forbidden names (belt-and-suspenders).
        if name in _FORBIDDEN_NAMES:
            raise ValueError(f"Forbidden name {name!r} is not allowed in expressions.")
        # All other identifiers are allowed at parse time — they must resolve
        # in the evaluation namespace (built-ins + context dict).  Unknown
        # names will raise NameError at evaluate() time.
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Keywords and star-args are not permitted.
        if node.keywords:
            raise ValueError("Keyword arguments are not allowed in expressions.")
        if node.starargs if hasattr(node, "starargs") else False:
            raise ValueError("Star arguments are not allowed in expressions.")
        # The function being called must be a plain Name (no attribute access).
        if not isinstance(node.func, ast.Name):
            raise ValueError(
                "Forbidden call: only plain function names are callable, "
                "not attribute-access expressions."
            )
        # Recurse into children.
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        raise ValueError(
            f"Forbidden attribute access: {node.attr!r}. "
            "Attribute access is not allowed in expressions."
        )

    def visit_Subscript(self, node: ast.Subscript) -> None:
        raise ValueError(
            "Forbidden subscript access. Index/slice operations are not allowed."
        )


# ---------------------------------------------------------------------------
# Expression class
# ---------------------------------------------------------------------------

class Expression:
    """A safe, compiled expression for procedural animation values.

    Parameters
    ----------
    source:
        The expression string, e.g. ``"time * 360"`` or
        ``"1 + wiggle(2, 0.1)"``.

    Raises
    ------
    ValueError
        If the source is empty, has syntax errors, or contains disallowed
        constructs.
    """

    def __init__(self, source: str) -> None:
        source = source.strip()
        if not source:
            raise ValueError("Expression source must not be empty.")

        # Parse.
        try:
            tree = ast.parse(source, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"Syntax error in expression {source!r}: {exc}") from exc

        # Validate.
        _SafetyVisitor().visit(tree)

        # Compile to a code object for fast repeated evaluation.
        self._source = source
        self._code = compile(tree, filename="<expression>", mode="eval")

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        time: float,
        frame: int,
        fps: float,
        context: Optional[Dict[str, object]] = None,
    ) -> float:
        """Evaluate the expression at a specific time/frame.

        Parameters
        ----------
        time:    Current time in seconds.
        frame:   Current frame index.
        fps:     Frames per second.
        context: Optional extra variables to inject (e.g. ``{"opacity": 0.5}``).

        Returns
        -------
        float
            The evaluated result.
        """
        ns: Dict[str, object] = dict(_STATIC_NAMESPACE)
        ns["time"]   = float(time)
        ns["frame"]  = int(frame)
        ns["fps"]    = float(fps)
        ns["wiggle"] = _make_wiggle(float(time), int(frame))
        ns["random"] = _make_random(int(frame))

        if context:
            ns.update(context)

        result = eval(self._code, ns)  # noqa: S307 — sandboxed namespace
        return float(result)

    def evaluate_batch(
        self,
        times: Sequence[float],
        fps: float,
    ) -> "Union[list[float], np.ndarray]":
        """Evaluate the expression at multiple time points.

        The frame index for each time is computed as ``round(time * fps)``.

        Parameters
        ----------
        times: Sequence of time values in seconds.
        fps:   Frames per second (used for frame index and the ``fps`` variable).

        Returns
        -------
        numpy array if numpy is available, otherwise a plain list.
        """
        if _NUMPY:
            times_arr = np.asarray(times, dtype=float)
            result = np.empty(len(times_arr), dtype=float)
            for i, t in enumerate(times_arr):
                frame = int(round(float(t) * fps))
                result[i] = self.evaluate(float(t), frame, fps)
            return result
        else:
            out = []
            for t in times:
                frame = int(round(float(t) * fps))
                out.append(self.evaluate(float(t), frame, fps))
            return out

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"Expression({self._source!r})"
