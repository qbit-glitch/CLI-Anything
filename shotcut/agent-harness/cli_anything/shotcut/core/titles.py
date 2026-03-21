"""Text/title animation for Shotcut MLT projects.

Provides title presets (typewriter, fade, slide, scale, bounce), a function
to add dynamictext filters, animate them with keyframes, and per-character
animation using staggered dynamictext filters backed by shared CharacterAnimator.
"""

import os
import sys
from typing import Optional

from .session import Session
from . import filters as filt_mod
from . import keyframes as kf_mod

# ---------------------------------------------------------------------------
# Shared motion_math imports
# ---------------------------------------------------------------------------

_SHARED_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../../../../shared")
)
if _SHARED_PATH not in sys.path:
    sys.path.insert(0, _SHARED_PATH)

from motion_math.text_animator import CharacterAnimator  # noqa: E402
from motion_math.keyframes import KeyframeTrack  # noqa: E402


# ============================================================================
# Geometry helpers
# ============================================================================

def _parse_geometry(geo_str: str) -> dict:
    """Parse an MLT geometry string into its components.

    Format: "x/y:wxh:opacity"
    Examples: "0/0:1920x1080:100", "960/0:1920x1080:0"

    Returns:
        dict with keys: x, y, w, h, opacity
    """
    if not geo_str or ":" not in geo_str:
        raise ValueError(f"Invalid geometry string: {geo_str!r}")

    parts = geo_str.split(":")
    if len(parts) < 2:
        raise ValueError(f"Invalid geometry string: {geo_str!r}")

    # Parse x/y
    pos_part = parts[0]
    if "/" not in pos_part:
        raise ValueError(f"Invalid position in geometry: {pos_part!r}")
    x_str, y_str = pos_part.split("/", 1)

    # Parse wxh
    size_part = parts[1]
    if "x" not in size_part:
        raise ValueError(f"Invalid size in geometry: {size_part!r}")
    w_str, h_str = size_part.split("x", 1)

    # Parse opacity (optional, default 100)
    opacity_str = parts[2] if len(parts) > 2 else "100"

    return {
        "x": int(x_str),
        "y": int(y_str),
        "w": int(w_str),
        "h": int(h_str),
        "opacity": int(opacity_str),
    }


def _build_geometry(x: int, y: int, w: int, h: int, opacity: int = 100) -> str:
    """Build an MLT geometry string from components.

    Returns:
        String in format "x/y:wxh:opacity"
    """
    return f"{x}/{y}:{w}x{h}:{opacity}"


# ============================================================================
# Title presets
# ============================================================================

TITLE_PRESETS = {
    "typewriter": {
        "description": "Text appears character by character (keyframed argument length)",
        "params": ["argument"],
        "default_duration": 2.0,
    },
    "fade_in": {
        "description": "Text fades in from transparent to fully visible",
        "params": ["geometry"],
        "default_duration": 1.0,
    },
    "fade_out": {
        "description": "Text fades out from fully visible to transparent",
        "params": ["geometry"],
        "default_duration": 1.0,
    },
    "slide_left": {
        "description": "Text slides in from off-screen right to center",
        "params": ["geometry"],
        "default_duration": 1.0,
    },
    "slide_right": {
        "description": "Text slides in from off-screen left to center",
        "params": ["geometry"],
        "default_duration": 1.0,
    },
    "slide_up": {
        "description": "Text slides in from off-screen bottom to center",
        "params": ["geometry"],
        "default_duration": 1.0,
    },
    "slide_down": {
        "description": "Text slides in from off-screen top to center",
        "params": ["geometry"],
        "default_duration": 1.0,
    },
    "scale_in": {
        "description": "Text starts small and scales to full size",
        "params": ["geometry"],
        "default_duration": 1.0,
    },
    "bounce": {
        "description": "Text overshoots then settles into position (uses ease_out)",
        "params": ["geometry"],
        "default_duration": 1.5,
    },
}


def list_presets() -> list[dict]:
    """List all available title animation presets.

    Returns:
        List of dicts with keys: name, description, params, default_duration
    """
    result = []
    for name, info in sorted(TITLE_PRESETS.items()):
        result.append({
            "name": name,
            "description": info["description"],
            "params": info["params"],
            "default_duration": info["default_duration"],
        })
    return result


def get_preset_info(name: str) -> dict:
    """Get detailed info about a title animation preset.

    Args:
        name: Preset name

    Returns:
        Dict with preset info including name, description, params, default_duration

    Raises:
        ValueError: If preset name is unknown
    """
    if name not in TITLE_PRESETS:
        available = ", ".join(sorted(TITLE_PRESETS.keys()))
        raise ValueError(f"Unknown preset: {name!r}. Available: {available}")
    info = dict(TITLE_PRESETS[name])
    info["name"] = name
    return info


# ============================================================================
# Add title
# ============================================================================

def add_title(session: Session, text: str,
              track_index: int, clip_index: int,
              font: str = "Sans", size: int = 48,
              color: str = "#ffffffff",
              halign: str = "center", valign: str = "middle",
              geometry: str = "0/0:1920x1080:100") -> dict:
    """Add a dynamictext title filter to a clip.

    Args:
        session: Active session
        text: The text to display
        track_index: Track index
        clip_index: Clip index on the track
        font: Font family name
        size: Font size
        color: Text color as #AARRGGBB
        halign: Horizontal alignment (left, center, right)
        valign: Vertical alignment (top, middle, bottom)
        geometry: Position/size as "x/y:wxh:opacity"

    Returns:
        Dict with action info including the filter index
    """
    params = {
        "argument": text,
        "geometry": geometry,
        "family": font,
        "size": str(size),
        "fgcolour": color,
        "halign": halign,
        "valign": valign,
    }

    result = filt_mod.add_filter(
        session, "dynamictext",
        track_index=track_index,
        clip_index=clip_index,
        params=params,
    )

    # Determine the filter index (it's the last one added)
    from ..utils import mlt_xml
    target = filt_mod._resolve_target(session, track_index, clip_index)
    filters = target.findall("filter")
    filter_index = len(filters) - 1

    return {
        "action": "add_title",
        "text": text,
        "filter_id": result["filter_id"],
        "filter_index": filter_index,
        "service": "dynamictext",
        "target": result["target"],
        "geometry": geometry,
        "font": font,
        "size": size,
        "color": color,
        "halign": halign,
        "valign": valign,
    }


# ============================================================================
# Animate title
# ============================================================================

def animate_title(session: Session,
                  track_index: int, clip_index: int,
                  filter_index: int, preset: str,
                  start_time: str = "0", duration: Optional[float] = None) -> dict:
    """Apply an animation preset to a title filter using keyframes.

    Args:
        session: Active session
        track_index: Track index
        clip_index: Clip index
        filter_index: Index of the dynamictext filter on the clip
        preset: Name of the animation preset
        start_time: Start time as frame number or timecode
        duration: Duration in seconds (None = use preset default)

    Returns:
        Dict with action info

    Raises:
        ValueError: If preset is unknown
    """
    if preset not in TITLE_PRESETS:
        available = ", ".join(sorted(TITLE_PRESETS.keys()))
        raise ValueError(f"Unknown preset: {preset!r}. Available: {available}")

    preset_info = TITLE_PRESETS[preset]
    if duration is None:
        duration = preset_info["default_duration"]

    # Calculate end time frame from start and duration
    # Use 30fps as default for frame calculation
    fps = 30
    try:
        start_frame = int(start_time)
    except ValueError:
        start_frame = 0
    end_frame = start_frame + int(duration * fps)

    # Read current geometry from the filter to use as base
    from ..utils import mlt_xml
    target = filt_mod._resolve_target(session, track_index, clip_index)
    filters = target.findall("filter")
    if filter_index < 0 or filter_index >= len(filters):
        raise IndexError(
            f"Filter index {filter_index} out of range (0-{len(filters)-1})")

    filt = filters[filter_index]
    current_geo = mlt_xml.get_property(filt, "geometry", "0/0:1920x1080:100")
    current_text = mlt_xml.get_property(filt, "argument", "")

    try:
        geo = _parse_geometry(current_geo)
    except ValueError:
        geo = {"x": 0, "y": 0, "w": 1920, "h": 1080, "opacity": 100}

    keyframes_added = []

    if preset == "typewriter":
        _animate_typewriter(session, track_index, clip_index, filter_index,
                            current_text, start_frame, end_frame,
                            keyframes_added)
    elif preset == "fade_in":
        _animate_fade_in(session, track_index, clip_index, filter_index,
                         geo, start_frame, end_frame, keyframes_added)
    elif preset == "fade_out":
        _animate_fade_out(session, track_index, clip_index, filter_index,
                          geo, start_frame, end_frame, keyframes_added)
    elif preset == "slide_left":
        _animate_slide(session, track_index, clip_index, filter_index,
                       geo, "left", start_frame, end_frame, keyframes_added)
    elif preset == "slide_right":
        _animate_slide(session, track_index, clip_index, filter_index,
                       geo, "right", start_frame, end_frame, keyframes_added)
    elif preset == "slide_up":
        _animate_slide(session, track_index, clip_index, filter_index,
                       geo, "up", start_frame, end_frame, keyframes_added)
    elif preset == "slide_down":
        _animate_slide(session, track_index, clip_index, filter_index,
                       geo, "down", start_frame, end_frame, keyframes_added)
    elif preset == "scale_in":
        _animate_scale_in(session, track_index, clip_index, filter_index,
                          geo, start_frame, end_frame, keyframes_added)
    elif preset == "bounce":
        _animate_bounce(session, track_index, clip_index, filter_index,
                        geo, start_frame, end_frame, keyframes_added)

    return {
        "action": "animate_title",
        "preset": preset,
        "start_time": str(start_frame),
        "duration": duration,
        "keyframes_added": len(keyframes_added),
        "animated_params": preset_info["params"],
        "keyframes": keyframes_added,
    }


# ============================================================================
# Preset animation implementations
# ============================================================================

def _animate_typewriter(session, track_index, clip_index, filter_index,
                        text, start_frame, end_frame, keyframes_added):
    """Typewriter effect: text appears character by character."""
    if not text:
        return

    total_chars = len(text)
    total_frames = end_frame - start_frame
    if total_frames <= 0:
        total_frames = 1

    for i in range(total_chars + 1):
        frame = start_frame + int(i * total_frames / total_chars) if total_chars > 0 else start_frame
        partial_text = text[:i]
        result = kf_mod.add_keyframe(
            session, str(frame), "argument", partial_text,
            easing="hold",
            track_index=track_index, clip_index=clip_index,
            filter_index=filter_index,
        )
        keyframes_added.append({
            "time": str(frame), "param": "argument",
            "value": partial_text, "easing": "hold",
        })


def _animate_fade_in(session, track_index, clip_index, filter_index,
                     geo, start_frame, end_frame, keyframes_added):
    """Fade in: opacity 0 -> 100."""
    start_geo = _build_geometry(geo["x"], geo["y"], geo["w"], geo["h"], 0)
    end_geo = _build_geometry(geo["x"], geo["y"], geo["w"], geo["h"], 100)

    kf_mod.add_keyframe(
        session, str(start_frame), "geometry", start_geo,
        easing="linear",
        track_index=track_index, clip_index=clip_index,
        filter_index=filter_index,
    )
    keyframes_added.append({
        "time": str(start_frame), "param": "geometry",
        "value": start_geo, "easing": "linear",
    })

    kf_mod.add_keyframe(
        session, str(end_frame), "geometry", end_geo,
        easing="linear",
        track_index=track_index, clip_index=clip_index,
        filter_index=filter_index,
    )
    keyframes_added.append({
        "time": str(end_frame), "param": "geometry",
        "value": end_geo, "easing": "linear",
    })


def _animate_fade_out(session, track_index, clip_index, filter_index,
                      geo, start_frame, end_frame, keyframes_added):
    """Fade out: opacity 100 -> 0."""
    start_geo = _build_geometry(geo["x"], geo["y"], geo["w"], geo["h"], 100)
    end_geo = _build_geometry(geo["x"], geo["y"], geo["w"], geo["h"], 0)

    kf_mod.add_keyframe(
        session, str(start_frame), "geometry", start_geo,
        easing="linear",
        track_index=track_index, clip_index=clip_index,
        filter_index=filter_index,
    )
    keyframes_added.append({
        "time": str(start_frame), "param": "geometry",
        "value": start_geo, "easing": "linear",
    })

    kf_mod.add_keyframe(
        session, str(end_frame), "geometry", end_geo,
        easing="linear",
        track_index=track_index, clip_index=clip_index,
        filter_index=filter_index,
    )
    keyframes_added.append({
        "time": str(end_frame), "param": "geometry",
        "value": end_geo, "easing": "linear",
    })


def _animate_slide(session, track_index, clip_index, filter_index,
                   geo, direction, start_frame, end_frame, keyframes_added):
    """Slide animation from off-screen to final position."""
    final_x = geo["x"]
    final_y = geo["y"]
    w = geo["w"]
    h = geo["h"]
    opacity = geo["opacity"]

    if direction == "left":
        # Start from off-screen right, slide to center
        start_x = w  # off-screen right (one full width to the right)
        start_y = final_y
    elif direction == "right":
        # Start from off-screen left, slide to center
        start_x = -w  # off-screen left
        start_y = final_y
    elif direction == "up":
        # Start from off-screen bottom, slide up
        start_x = final_x
        start_y = h  # off-screen bottom
    elif direction == "down":
        # Start from off-screen top, slide down
        start_x = final_x
        start_y = -h  # off-screen top
    else:
        start_x = final_x
        start_y = final_y

    start_geo = _build_geometry(start_x, start_y, w, h, opacity)
    end_geo = _build_geometry(final_x, final_y, w, h, opacity)

    kf_mod.add_keyframe(
        session, str(start_frame), "geometry", start_geo,
        easing="linear",
        track_index=track_index, clip_index=clip_index,
        filter_index=filter_index,
    )
    keyframes_added.append({
        "time": str(start_frame), "param": "geometry",
        "value": start_geo, "easing": "linear",
    })

    kf_mod.add_keyframe(
        session, str(end_frame), "geometry", end_geo,
        easing="linear",
        track_index=track_index, clip_index=clip_index,
        filter_index=filter_index,
    )
    keyframes_added.append({
        "time": str(end_frame), "param": "geometry",
        "value": end_geo, "easing": "linear",
    })


def _animate_scale_in(session, track_index, clip_index, filter_index,
                      geo, start_frame, end_frame, keyframes_added):
    """Scale in: starts small at center, grows to full size."""
    final_x = geo["x"]
    final_y = geo["y"]
    w = geo["w"]
    h = geo["h"]
    opacity = geo["opacity"]

    # Start at 10% size, centered
    small_w = w // 10
    small_h = h // 10
    center_x = final_x + (w - small_w) // 2
    center_y = final_y + (h - small_h) // 2

    start_geo = _build_geometry(center_x, center_y, small_w, small_h, opacity)
    end_geo = _build_geometry(final_x, final_y, w, h, opacity)

    kf_mod.add_keyframe(
        session, str(start_frame), "geometry", start_geo,
        easing="linear",
        track_index=track_index, clip_index=clip_index,
        filter_index=filter_index,
    )
    keyframes_added.append({
        "time": str(start_frame), "param": "geometry",
        "value": start_geo, "easing": "linear",
    })

    kf_mod.add_keyframe(
        session, str(end_frame), "geometry", end_geo,
        easing="linear",
        track_index=track_index, clip_index=clip_index,
        filter_index=filter_index,
    )
    keyframes_added.append({
        "time": str(end_frame), "param": "geometry",
        "value": end_geo, "easing": "linear",
    })


def _animate_bounce(session, track_index, clip_index, filter_index,
                    geo, start_frame, end_frame, keyframes_added):
    """Bounce: overshoots position then settles. Uses ease_out easing."""
    final_x = geo["x"]
    final_y = geo["y"]
    w = geo["w"]
    h = geo["h"]
    opacity = geo["opacity"]

    total_frames = end_frame - start_frame

    # Start off-screen top
    start_y = -h
    # Overshoot past final position
    overshoot_y = final_y + h // 10
    # Mid-bounce
    mid_frame = start_frame + int(total_frames * 0.6)
    # Settle
    settle_frame = start_frame + int(total_frames * 0.8)

    # Keyframe 1: start off-screen
    geo_start = _build_geometry(final_x, start_y, w, h, opacity)
    kf_mod.add_keyframe(
        session, str(start_frame), "geometry", geo_start,
        easing="ease_out",
        track_index=track_index, clip_index=clip_index,
        filter_index=filter_index,
    )
    keyframes_added.append({
        "time": str(start_frame), "param": "geometry",
        "value": geo_start, "easing": "ease_out",
    })

    # Keyframe 2: overshoot
    geo_overshoot = _build_geometry(final_x, overshoot_y, w, h, opacity)
    kf_mod.add_keyframe(
        session, str(mid_frame), "geometry", geo_overshoot,
        easing="ease_out",
        track_index=track_index, clip_index=clip_index,
        filter_index=filter_index,
    )
    keyframes_added.append({
        "time": str(mid_frame), "param": "geometry",
        "value": geo_overshoot, "easing": "ease_out",
    })

    # Keyframe 3: small bounce back
    geo_bounce = _build_geometry(final_x, final_y - h // 20, w, h, opacity)
    kf_mod.add_keyframe(
        session, str(settle_frame), "geometry", geo_bounce,
        easing="ease_out",
        track_index=track_index, clip_index=clip_index,
        filter_index=filter_index,
    )
    keyframes_added.append({
        "time": str(settle_frame), "param": "geometry",
        "value": geo_bounce, "easing": "ease_out",
    })

    # Keyframe 4: final position
    geo_final = _build_geometry(final_x, final_y, w, h, opacity)
    kf_mod.add_keyframe(
        session, str(end_frame), "geometry", geo_final,
        easing="ease_out",
        track_index=track_index, clip_index=clip_index,
        filter_index=filter_index,
    )
    keyframes_added.append({
        "time": str(end_frame), "param": "geometry",
        "value": geo_final, "easing": "ease_out",
    })


# ============================================================================
# Per-character text animation
# ============================================================================

# Available presets for per-character animation
PER_CHAR_PRESETS = {
    "typewriter":  "Characters appear in sequence (opacity 0→1, stagger left_to_right)",
    "cascade":     "Characters cascade in with ease_out_cubic and stagger",
    "scale_pop":   "Characters pop in with ease_out_back overshoot and stagger",
    "bounce_in":   "Characters bounce in with ease_out_bounce and stagger",
    "wave":        "Characters oscillate in a sine wave (continuous)",
    "random_fade": "Characters fade in at random times within the duration",
}


def list_per_char_presets() -> list[dict]:
    """List all available per-character animation presets.

    Returns:
        List of dicts with keys: name, description
    """
    return [{"name": k, "description": v}
            for k, v in sorted(PER_CHAR_PRESETS.items())]


def apply_per_char_animation(
    session: Session,
    clip_index: int,
    text: str,
    track_index: int = 0,
    preset: str = "typewriter",
    duration: Optional[float] = None,
    delay: float = 0.05,
    fps: int = 30,
    font: str = "Sans",
    size: int = 48,
    color: str = "#ffffffff",
    geometry: str = "0/0:1920x1080:100",
) -> dict:
    """Apply per-character text animation by generating staggered dynamictext filters.

    Each character gets its own dynamictext filter on the clip.  The character's
    opacity is driven by geometry keyframes derived from the shared
    CharacterAnimator, which handles stagger timing and presets.

    Args:
        session:     Active session.
        clip_index:  Clip index on the target track.
        text:        The text string to animate.
        track_index: Track index.
        preset:      Per-character animation preset (see PER_CHAR_PRESETS).
        duration:    Total animation duration in seconds (None = auto based on
                     char count and delay).
        delay:       Stagger delay between consecutive characters (seconds).
        fps:         Frames per second for keyframe timing.
        font:        Font family name.
        size:        Font size.
        color:       Text color as #AARRGGBB.
        geometry:    Base geometry string "x/y:wxh:opacity" for all characters.

    Returns:
        Dict with:
            action: "apply_per_char_animation"
            text: the input text
            preset: the preset used
            char_count: number of characters animated
            filter_count: number of dynamictext filters added
            filter_indices: list of filter indices added
            duration: total animation duration
    """
    if preset not in PER_CHAR_PRESETS:
        available = ", ".join(sorted(PER_CHAR_PRESETS.keys()))
        raise ValueError(f"Unknown per-char preset: {preset!r}. Available: {available}")

    if not text:
        return {
            "action": "apply_per_char_animation",
            "text": text,
            "preset": preset,
            "char_count": 0,
            "filter_count": 0,
            "filter_indices": [],
            "duration": 0.0,
        }

    chars = CharacterAnimator.decompose(text)
    n_chars = len(chars)

    # Auto-compute duration if not specified
    if duration is None:
        duration = n_chars * delay + 0.5  # stagger total + settle time

    # Compute per-character KeyframeTracks using the selected preset
    if preset == "typewriter":
        char_tracks = CharacterAnimator.preset_typewriter(
            text, char_duration=delay
        )
    elif preset == "cascade":
        char_tracks = CharacterAnimator.preset_cascade_in(
            text, duration=0.3, delay=delay
        )
    elif preset == "scale_pop":
        char_tracks = CharacterAnimator.preset_scale_pop(
            text, duration=0.4, delay=delay
        )
    elif preset == "bounce_in":
        char_tracks = CharacterAnimator.preset_bounce_in(
            text, duration=0.6, delay=delay
        )
    elif preset == "wave":
        char_tracks = CharacterAnimator.preset_wave(
            text, amplitude=10.0, frequency=2.0, duration=duration, fps=float(fps)
        )
    elif preset == "random_fade":
        char_tracks = CharacterAnimator.preset_random_fade(
            text, total_duration=duration, char_duration=0.3
        )
    else:
        char_tracks = CharacterAnimator.preset_typewriter(text, char_duration=delay)

    # Parse the base geometry
    try:
        base_geo = _parse_geometry(geometry)
    except ValueError:
        base_geo = {"x": 0, "y": 0, "w": 1920, "h": 1080, "opacity": 100}

    filter_indices = []
    session.checkpoint()

    for char_info in chars:
        char_char = char_info.char
        char_idx = char_info.index
        track = char_tracks.get(char_idx)

        # Add a dynamictext filter for this character
        char_params = {
            "argument": char_char,
            "family": font,
            "size": str(size),
            "fgcolour": color,
            "halign": "center",
            "valign": "middle",
            "geometry": geometry,
        }
        add_result = filt_mod.add_filter(
            session, "dynamictext",
            track_index=track_index,
            clip_index=clip_index,
            params=char_params,
        )

        # Determine the filter index
        from ..utils import mlt_xml
        target = filt_mod._resolve_target(session, track_index, clip_index)
        filter_elems = target.findall("filter")
        fi = len(filter_elems) - 1
        filter_indices.append(fi)

        if track is None:
            continue

        # Apply opacity keyframes from the CharacterAnimator track
        # The track gives us opacity values in [0, 1] which we map to geometry opacity [0, 100]
        kf_list = track.keyframes
        from cli_anything.shotcut.core.keyframes import EASING_TYPES
        for kf in kf_list:
            t_secs = kf.time
            # Clamp opacity to [0, 1]
            opacity_01 = max(0.0, min(1.0, float(kf.value)))
            opacity_pct = int(round(opacity_01 * 100))
            geo_str = _build_geometry(
                base_geo["x"], base_geo["y"],
                base_geo["w"], base_geo["h"],
                opacity_pct,
            )
            # kf.easing may be a string or callable; resolve to string
            easing_name = kf.easing if isinstance(kf.easing, str) else "linear"
            # Fall back to "linear" if easing isn't in EASING_TYPES
            if easing_name not in EASING_TYPES:
                easing_name = "linear"
            kf_mod.add_keyframe(
                session, str(t_secs), "geometry", geo_str,
                easing=easing_name,
                track_index=track_index,
                clip_index=clip_index,
                filter_index=fi,
            )

    return {
        "action": "apply_per_char_animation",
        "text": text,
        "preset": preset,
        "char_count": n_chars,
        "filter_count": len(filter_indices),
        "filter_indices": filter_indices,
        "duration": duration,
    }
