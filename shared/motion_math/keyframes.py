"""Keyframe interpolation engine for motion graphics.

Provides a ``KeyframeTrack`` that stores time→value pairs with per-keyframe
easing functions and interpolates between them.

Easing is applied on the *destination* keyframe (the one being approached),
mirroring how professional NLEs and animation tools work.

Examples::

    from motion_math.keyframes import KeyframeTrack

    track = KeyframeTrack()
    track.add(0.0, 0.0, "linear")
    track.add(1.0, 100.0, "ease_out_cubic")
    print(track.evaluate(0.5))   # ~87.5
    print(track.bake(30, 1.0))   # list of 31 floats
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Callable, Union

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False

from .easing import get_easing

__all__ = ["Keyframe", "KeyframeTrack"]

# Tolerance for treating two times as the same keyframe.
_TIME_TOL = 1e-9


# ---------------------------------------------------------------------------
# Keyframe dataclass
# ---------------------------------------------------------------------------

@dataclass
class Keyframe:
    """A single keyframe with a time, value, and easing function.

    Attributes:
        time:   Position on the timeline in seconds.
        value:  Numeric value at this keyframe.
        easing: Either a string name resolvable via ``get_easing()`` or any
                callable ``f(t: float) -> float`` where t ∈ [0, 1].
    """
    time: float
    value: float
    easing: Union[str, Callable[[float], float]] = "linear"


# ---------------------------------------------------------------------------
# KeyframeTrack
# ---------------------------------------------------------------------------

class KeyframeTrack:
    """Ordered collection of keyframes with interpolation.

    Keyframes are kept sorted by time.  Querying at any time ``t`` finds the
    surrounding pair and interpolates using the *destination* keyframe's easing
    function.

    Hold behaviour:
    - Before the first keyframe → returns the first keyframe's value.
    - After the last keyframe  → returns the last keyframe's value.
    - Empty track              → returns 0.0.
    """

    def __init__(self) -> None:
        # Parallel lists kept in sorted order by time.
        self._times: list[float] = []
        self._kfs: list[Keyframe] = []

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, time: float, value: float, easing: Union[str, Callable] = "linear") -> None:
        """Add a keyframe, replacing any existing one within *_TIME_TOL*.

        Args:
            time:   Timeline position in seconds.
            value:  Value at this keyframe.
            easing: Easing function name or callable.  Defaults to ``"linear"``.
        """
        new_kf = Keyframe(time=time, value=value, easing=easing)

        # Check for existing keyframe within tolerance.
        idx = self._find_near(time)
        if idx is not None:
            self._kfs[idx] = new_kf
            self._times[idx] = time
            return

        # Insert in sorted position.
        pos = bisect.bisect_left(self._times, time)
        self._times.insert(pos, time)
        self._kfs.insert(pos, new_kf)

    def remove(self, time: float) -> None:
        """Remove the keyframe nearest to *time* if within *_TIME_TOL*.

        Raises:
            KeyError: If no keyframe exists within *_TIME_TOL* of *time*.
        """
        idx = self._find_near(time)
        if idx is None:
            raise KeyError(f"No keyframe within tolerance of t={time!r}")
        del self._times[idx]
        del self._kfs[idx]

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, t: float) -> float:
        """Interpolate the track at time *t*.

        Args:
            t: Time in seconds.

        Returns:
            Interpolated float value.
        """
        n = len(self._kfs)
        if n == 0:
            return 0.0
        if n == 1:
            return self._kfs[0].value

        # Hold before first keyframe.
        if t <= self._times[0]:
            return self._kfs[0].value

        # Hold after last keyframe.
        if t >= self._times[-1]:
            return self._kfs[-1].value

        # Find the segment: times[lo] <= t < times[hi]
        hi = bisect.bisect_right(self._times, t)
        lo = hi - 1

        kf_lo = self._kfs[lo]
        kf_hi = self._kfs[hi]

        dt = self._times[hi] - self._times[lo]
        if dt == 0.0:
            return kf_hi.value

        # Raw linear progress [0, 1].
        progress = (t - self._times[lo]) / dt

        # Apply easing from the destination (hi) keyframe.
        ease_fn = self._resolve_easing(kf_hi.easing)
        eased = ease_fn(progress)

        return kf_lo.value + eased * (kf_hi.value - kf_lo.value)

    def evaluate_batch(self, times) -> "Union[list[float], np.ndarray]":
        """Evaluate at multiple time points.

        Args:
            times: Sequence or numpy array of time values.

        Returns:
            numpy array if numpy is available, otherwise a plain list.
        """
        if _NUMPY:
            times_arr = np.asarray(times, dtype=float)
            result = np.empty(len(times_arr), dtype=float)
            for i, t in enumerate(times_arr):
                result[i] = self.evaluate(float(t))
            return result
        else:
            return [self.evaluate(float(t)) for t in times]

    def bake(self, fps: float, duration: float) -> list[float]:
        """Pre-compute the track at every frame.

        Args:
            fps:      Frames per second.
            duration: Total duration in seconds.

        Returns:
            List of ``int(duration * fps) + 1`` float values, one per frame
            from frame 0 to the final frame (inclusive).
        """
        frame_count = int(duration * fps) + 1
        return [self.evaluate(i / fps) for i in range(frame_count)]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def keyframes(self) -> list[Keyframe]:
        """Return a sorted shallow copy of all keyframes."""
        return list(self._kfs)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_near(self, time: float) -> "int | None":
        """Return the index of the keyframe within *_TIME_TOL* of *time*, or None."""
        # bisect gives the insertion point; check the immediate neighbours.
        pos = bisect.bisect_left(self._times, time)
        for idx in (pos - 1, pos):
            if 0 <= idx < len(self._times):
                if abs(self._times[idx] - time) <= _TIME_TOL:
                    return idx
        return None

    @staticmethod
    def _resolve_easing(easing: Union[str, Callable]) -> Callable[[float], float]:
        """Return a callable easing function from a name or callable."""
        if callable(easing):
            return easing
        return get_easing(easing)  # raises ValueError for unknown names
