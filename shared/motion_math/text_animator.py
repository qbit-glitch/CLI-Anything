"""Per-character text decomposition and stagger animation engine.

Provides:
- CharInfo: dataclass describing a single character's position metadata
- CharacterAnimator: static-method class for decomposing text and building
  per-character KeyframeTracks with staggered timing and presets

Typical usage::

    from motion_math.text_animator import CharacterAnimator

    # Typewriter effect
    tracks = CharacterAnimator.preset_typewriter("Hello World")
    for char_idx, track in sorted(tracks.items()):
        opacity_at_1s = track.evaluate(1.0)

    # Custom stagger
    chars = CharacterAnimator.decompose("Motion")
    base = KeyframeTrack()
    base.add(0.0, 0.0, "ease_out_cubic")
    base.add(0.4, 1.0, "ease_out_cubic")
    tracks = CharacterAnimator.stagger(chars, base, delay_per_char=0.05,
                                       order="center_out")
"""

from __future__ import annotations

import math
import random as _random_module
from dataclasses import dataclass, field
from typing import Sequence

from .keyframes import KeyframeTrack

__all__ = ["CharInfo", "CharacterAnimator"]


# ---------------------------------------------------------------------------
# CharInfo dataclass
# ---------------------------------------------------------------------------

@dataclass
class CharInfo:
    """Metadata for a single character in a decomposed text string.

    Attributes:
        char:     The character (may be a space; never a newline).
        index:    Zero-based position in the decomposed character list.
        x_offset: Horizontal offset from the start of the current line,
                  in ``char_width`` units.
        width:    Width allocated for this character (same as ``char_width``
                  passed to :meth:`CharacterAnimator.decompose`).
        line:     Zero-based line number (increments on ``\\n`` in source).
    """
    char: str
    index: int
    x_offset: float
    width: float
    line: int = 0


# ---------------------------------------------------------------------------
# CharacterAnimator
# ---------------------------------------------------------------------------

class CharacterAnimator:
    """Static-method factory for per-character animation tracks.

    All methods are ``@staticmethod`` — no instantiation required.
    """

    # ------------------------------------------------------------------
    # decompose
    # ------------------------------------------------------------------

    @staticmethod
    def decompose(text: str, char_width: float = 1.0) -> list[CharInfo]:
        """Break *text* into positioned :class:`CharInfo` objects.

        Newlines increment the line counter and reset the x-offset.
        Newline characters themselves are **not** included in the output.
        Spaces are treated as ordinary characters.

        Args:
            text:       Source string (may contain ``\\n``).
            char_width: Width allocated to each character.

        Returns:
            Ordered list of :class:`CharInfo`, one per non-newline character.
        """
        result: list[CharInfo] = []
        current_line = 0
        current_x = 0.0
        index = 0

        for ch in text:
            if ch == "\n":
                current_line += 1
                current_x = 0.0
            else:
                result.append(
                    CharInfo(
                        char=ch,
                        index=index,
                        x_offset=current_x,
                        width=char_width,
                        line=current_line,
                    )
                )
                current_x += char_width
                index += 1

        return result

    # ------------------------------------------------------------------
    # stagger
    # ------------------------------------------------------------------

    @staticmethod
    def stagger(
        chars: Sequence[CharInfo],
        base_track: KeyframeTrack,
        delay_per_char: float,
        order: str = "left_to_right",
    ) -> dict[int, KeyframeTrack]:
        """Create per-character :class:`KeyframeTrack` objects with staggered timing.

        Each output track is a time-shifted copy of *base_track*.  Keyframes
        in *base_track* are shifted by ``rank * delay_per_char`` seconds, where
        *rank* is determined by *order*.

        Supported orders:

        - ``"left_to_right"``  — char 0 first, last char last
        - ``"right_to_left"``  — last char first, char 0 last
        - ``"center_out"``     — centre character first, edges last; chars
          equidistant from the centre share the same rank and start together
        - ``"random"``         — random permutation of ranks (seeded for
          reproducibility within a single call via a fixed seed)

        Args:
            chars:          List of :class:`CharInfo` from :meth:`decompose`.
            base_track:     Template :class:`KeyframeTrack` to shift.
            delay_per_char: Seconds between consecutive stagger ranks.
            order:          One of the order strings listed above.

        Returns:
            ``dict[char_index → KeyframeTrack]``, one entry per character.

        Raises:
            ValueError: If *order* is not one of the recognised values.
        """
        n = len(chars)
        if n == 0:
            return {}

        valid_orders = {"left_to_right", "right_to_left", "center_out", "random"}
        if order not in valid_orders:
            raise ValueError(
                f"Unknown stagger order {order!r}. "
                f"Valid orders: {sorted(valid_orders)}"
            )

        # --- compute rank (0 = earliest) for each char index ---
        indices = [c.index for c in chars]

        if order == "left_to_right":
            rank = {idx: pos for pos, idx in enumerate(indices)}

        elif order == "right_to_left":
            rank = {idx: (n - 1 - pos) for pos, idx in enumerate(indices)}

        elif order == "center_out":
            center = (n - 1) / 2.0
            # distance from centre; chars closer to centre get lower rank.
            # Equidistant chars share the same rank so they start simultaneously.
            distances = [round(abs(pos - center) * 2) for pos in range(n)]
            unique_dists = sorted(set(distances))
            dist_to_rank = {d: r for r, d in enumerate(unique_dists)}
            rank = {idx: dist_to_rank[distances[pos]] for pos, idx in enumerate(indices)}

        else:  # random
            rng = _random_module.Random(42)
            shuffled = list(range(n))
            rng.shuffle(shuffled)
            rank = {idx: shuffled[pos] for pos, idx in enumerate(indices)}

        # --- build time-shifted KeyframeTracks ---
        result: dict[int, KeyframeTrack] = {}
        for c in chars:
            offset = rank[c.index] * delay_per_char
            new_track = CharacterAnimator._shift_track(base_track, offset)
            result[c.index] = new_track

        return result

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    @staticmethod
    def preset_typewriter(
        text: str,
        char_duration: float = 0.05,
    ) -> dict[int, KeyframeTrack]:
        """Typewriter effect: each character fades in (opacity 0 → 1) in sequence.

        Characters appear left-to-right, each spending ``char_duration`` seconds
        transitioning from invisible to fully opaque.

        Args:
            text:          Source string (may contain newlines).
            char_duration: Fade-in duration per character in seconds.

        Returns:
            ``dict[char_index → KeyframeTrack]`` (opacity values 0–1).
        """
        chars = CharacterAnimator.decompose(text)
        if not chars:
            return {}

        base = KeyframeTrack()
        base.add(0.0, 0.0, "linear")
        base.add(char_duration, 1.0, "linear")

        return CharacterAnimator.stagger(
            chars, base, delay_per_char=char_duration, order="left_to_right"
        )

    @staticmethod
    def preset_wave(
        text: str,
        amplitude: float = 10.0,
        frequency: float = 2.0,
        duration: float = 2.0,
        fps: float = 30.0,
    ) -> dict[int, KeyframeTrack]:
        """Sine-wave y-offset animation.  Each character oscillates vertically.

        The phase of each character is offset by its x_offset so they form a
        travelling wave rather than all moving in sync.

        Args:
            text:      Source string.
            amplitude: Peak y-offset in pixels (or units).
            frequency: Wave frequency in Hz.
            duration:  Total animation duration in seconds.
            fps:       Frames per second for keyframe baking.

        Returns:
            ``dict[char_index → KeyframeTrack]`` (y-offset values).
        """
        chars = CharacterAnimator.decompose(text)
        if not chars:
            return {}

        result: dict[int, KeyframeTrack] = {}
        frame_count = int(duration * fps) + 1
        phase_per_unit = 2.0 * math.pi * frequency / max(len(chars), 1)

        for c in chars:
            track = KeyframeTrack()
            phase_offset = c.index * phase_per_unit
            for frame in range(frame_count):
                t = frame / fps
                y = amplitude * math.sin(2.0 * math.pi * frequency * t + phase_offset)
                easing = "linear" if frame > 0 else "linear"
                track.add(t, y, easing)
            result[c.index] = track

        return result

    @staticmethod
    def preset_cascade_in(
        text: str,
        duration: float = 0.3,
        delay: float = 0.05,
    ) -> dict[int, KeyframeTrack]:
        """Cascade-in: each char scales/fades from 0 → 1 with ease_out_cubic.

        Args:
            text:     Source string.
            duration: Animation duration per character.
            delay:    Stagger delay between consecutive characters.

        Returns:
            ``dict[char_index → KeyframeTrack]`` (scale/opacity 0–1).
        """
        chars = CharacterAnimator.decompose(text)
        if not chars:
            return {}

        base = KeyframeTrack()
        base.add(0.0, 0.0, "linear")
        base.add(duration, 1.0, "ease_out_cubic")

        return CharacterAnimator.stagger(
            chars, base, delay_per_char=delay, order="left_to_right"
        )

    @staticmethod
    def preset_scale_pop(
        text: str,
        duration: float = 0.4,
        delay: float = 0.05,
    ) -> dict[int, KeyframeTrack]:
        """Scale-pop: each char pops from 0 → 1 with ease_out_back (overshoot).

        Args:
            text:     Source string.
            duration: Animation duration per character.
            delay:    Stagger delay between consecutive characters.

        Returns:
            ``dict[char_index → KeyframeTrack]`` (scale 0–1, may briefly exceed 1).
        """
        chars = CharacterAnimator.decompose(text)
        if not chars:
            return {}

        base = KeyframeTrack()
        base.add(0.0, 0.0, "linear")
        base.add(duration, 1.0, "ease_out_back")

        return CharacterAnimator.stagger(
            chars, base, delay_per_char=delay, order="left_to_right"
        )

    @staticmethod
    def preset_bounce_in(
        text: str,
        duration: float = 0.6,
        delay: float = 0.04,
    ) -> dict[int, KeyframeTrack]:
        """Bounce-in: each char drops in with an ease_out_bounce.

        Args:
            text:     Source string.
            duration: Animation duration per character.
            delay:    Stagger delay between consecutive characters.

        Returns:
            ``dict[char_index → KeyframeTrack]`` (scale/position 0–1).
        """
        chars = CharacterAnimator.decompose(text)
        if not chars:
            return {}

        base = KeyframeTrack()
        base.add(0.0, 0.0, "linear")
        base.add(duration, 1.0, "ease_out_bounce")

        return CharacterAnimator.stagger(
            chars, base, delay_per_char=delay, order="left_to_right"
        )

    @staticmethod
    def preset_random_fade(
        text: str,
        total_duration: float = 1.0,
        char_duration: float = 0.3,
    ) -> dict[int, KeyframeTrack]:
        """Random-fade: each char fades in at a random time within *total_duration*.

        Start times are chosen from a uniform random distribution seeded
        deterministically (seed=0) for reproducibility.

        Args:
            text:           Source string.
            total_duration: Time window over which start times are spread.
            char_duration:  Fade-in duration per character.

        Returns:
            ``dict[char_index → KeyframeTrack]`` (opacity 0–1).
        """
        chars = CharacterAnimator.decompose(text)
        if not chars:
            return {}

        rng = _random_module.Random(0)
        result: dict[int, KeyframeTrack] = {}

        for c in chars:
            start = rng.uniform(0.0, total_duration)
            track = KeyframeTrack()
            track.add(start, 0.0, "linear")
            track.add(start + char_duration, 1.0, "linear")
            result[c.index] = track

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _shift_track(track: KeyframeTrack, offset: float) -> KeyframeTrack:
        """Return a new KeyframeTrack with all keyframe times shifted by *offset*.

        Args:
            track:  Source :class:`KeyframeTrack`.
            offset: Time offset in seconds (positive = shift later).

        Returns:
            New :class:`KeyframeTrack` with shifted keyframes.
        """
        new_track = KeyframeTrack()
        for kf in track.keyframes:
            new_track.add(kf.time + offset, kf.value, kf.easing)
        return new_track
