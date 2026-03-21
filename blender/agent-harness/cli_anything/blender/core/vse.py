"""Blender CLI - Video Sequence Editor (VSE) module.

Manages VSE strips, transitions, and effects in the project JSON.
Data is stored in project["vse"]["strips"].
"""

from typing import Dict, Any, List, Optional


# Strip type registry
STRIP_TYPES = {
    "movie": {"description": "Video file", "bpy_type": "MOVIE"},
    "image": {"description": "Image file or sequence", "bpy_type": "IMAGE"},
    "sound": {"description": "Audio file", "bpy_type": "SOUND"},
    "color": {"description": "Solid color strip", "bpy_type": "COLOR"},
    "text": {"description": "Text overlay strip", "bpy_type": "TEXT"},
    "adjustment": {"description": "Adjustment layer", "bpy_type": "ADJUSTMENT"},
}

# Transition registry
VSE_TRANSITIONS = {
    "cross": {"description": "Cross dissolve", "bpy_type": "CROSS"},
    "gamma_cross": {"description": "Gamma-corrected cross dissolve", "bpy_type": "GAMMA_CROSS"},
    "wipe": {"description": "Wipe transition", "bpy_type": "WIPE"},
}

# Effect registry
VSE_EFFECTS = {
    "transform": {"description": "Scale, rotate, translate", "bpy_type": "TRANSFORM"},
    "speed": {"description": "Speed control", "bpy_type": "SPEED"},
    "glow": {"description": "Glow/bloom effect", "bpy_type": "GLOW"},
    "gaussian_blur": {"description": "Gaussian blur", "bpy_type": "GAUSSIAN_BLUR"},
    "color_balance": {"description": "Color balance (lift/gamma/gain)", "bpy_type": "COLOR_BALANCE"},
}


def _ensure_vse(project: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure the VSE section exists in the project."""
    if "vse" not in project:
        project["vse"] = {"strips": [], "next_id": 1}
    if "next_id" not in project["vse"]:
        project["vse"]["next_id"] = 1
    return project["vse"]


def _next_id(vse: Dict[str, Any]) -> int:
    """Get and increment the next strip ID."""
    strip_id = vse["next_id"]
    vse["next_id"] = strip_id + 1
    return strip_id


def add_strip(
    project: Dict[str, Any],
    strip_type: str,
    channel: int,
    frame_start: int,
    source: Optional[str] = None,
    frame_end: Optional[int] = None,
    name: Optional[str] = None,
    color: Optional[List[float]] = None,
    text: Optional[str] = None,
    font_size: Optional[int] = None,
) -> Dict[str, Any]:
    """Add a VSE strip to the project.

    Args:
        project: The scene dict
        strip_type: Type of strip (movie, image, sound, color, text, adjustment)
        channel: Track number (1-based)
        frame_start: Start frame for the strip
        source: File path for movie/image/sound strips
        frame_end: End frame (defaults to frame_start + 100)
        name: Strip name (auto-generated if not provided)
        color: RGB color for color strips [R, G, B] (0.0-1.0)
        text: Text content for text strips
        font_size: Font size for text strips

    Returns:
        The new strip dict
    """
    if strip_type not in STRIP_TYPES:
        raise ValueError(
            f"Unknown strip type: '{strip_type}'. Valid: {list(STRIP_TYPES.keys())}"
        )

    if channel < 1:
        raise ValueError(f"Channel must be >= 1, got {channel}")

    if frame_start < 0:
        raise ValueError(f"frame_start must be non-negative: {frame_start}")

    if frame_end is None:
        frame_end = frame_start + 100

    if frame_end <= frame_start:
        raise ValueError(
            f"frame_end ({frame_end}) must be > frame_start ({frame_start})"
        )

    # Validate source for file-based strips
    if strip_type in ("movie", "image", "sound") and not source:
        raise ValueError(f"'{strip_type}' strip requires a source file path")

    # Validate color for color strips
    if strip_type == "color":
        if color is None:
            color = [1.0, 1.0, 1.0]
        if len(color) != 3:
            raise ValueError("Color must have 3 components [R, G, B]")
        for c in color:
            if not 0.0 <= c <= 1.0:
                raise ValueError(f"Color components must be 0.0-1.0, got {c}")

    # Validate text for text strips
    if strip_type == "text" and not text:
        text = "Text"

    vse = _ensure_vse(project)
    strip_id = _next_id(vse)

    if name is None:
        name = f"{strip_type.capitalize()}_{strip_id}"

    strip = {
        "id": strip_id,
        "type": strip_type,
        "channel": channel,
        "frame_start": frame_start,
        "frame_end": frame_end,
        "name": name,
        "source": source,
        "color": color,
        "text": text,
        "font_size": font_size if font_size is not None else (48 if strip_type == "text" else None),
        "blend_type": "REPLACE",
        "opacity": 1.0,
        "mute": False,
        "effects": [],
    }

    vse["strips"].append(strip)
    return strip


def remove_strip(project: Dict[str, Any], strip_index: int) -> Dict[str, Any]:
    """Remove a VSE strip by index.

    Args:
        project: The scene dict
        strip_index: Index of the strip to remove

    Returns:
        The removed strip dict
    """
    vse = _ensure_vse(project)
    strips = vse["strips"]

    if not strips:
        raise ValueError("No strips in the sequence editor")

    if strip_index < 0 or strip_index >= len(strips):
        raise IndexError(
            f"Strip index {strip_index} out of range (0-{len(strips)-1})"
        )

    removed = strips.pop(strip_index)
    return removed


def move_strip(
    project: Dict[str, Any],
    strip_index: int,
    channel: Optional[int] = None,
    frame_start: Optional[int] = None,
) -> Dict[str, Any]:
    """Move a VSE strip to a new channel and/or frame.

    Args:
        project: The scene dict
        strip_index: Index of the strip to move
        channel: New channel number (1-based)
        frame_start: New start frame

    Returns:
        The updated strip dict
    """
    vse = _ensure_vse(project)
    strips = vse["strips"]

    if strip_index < 0 or strip_index >= len(strips):
        raise IndexError(
            f"Strip index {strip_index} out of range (0-{len(strips)-1})"
        )

    strip = strips[strip_index]

    if channel is not None:
        if channel < 1:
            raise ValueError(f"Channel must be >= 1, got {channel}")
        strip["channel"] = channel

    if frame_start is not None:
        if frame_start < 0:
            raise ValueError(f"frame_start must be non-negative: {frame_start}")
        duration = strip["frame_end"] - strip["frame_start"]
        strip["frame_start"] = frame_start
        strip["frame_end"] = frame_start + duration

    return strip


def set_strip_property(
    project: Dict[str, Any],
    strip_index: int,
    prop: str,
    value: Any,
) -> Dict[str, Any]:
    """Set a property on a VSE strip.

    Args:
        project: The scene dict
        strip_index: Index of the strip
        prop: Property name (blend_type, opacity, mute, name, color, text, font_size)
        value: New value

    Returns:
        The updated strip dict
    """
    valid_props = ["blend_type", "opacity", "mute", "name", "color", "text", "font_size"]

    if prop not in valid_props:
        raise ValueError(
            f"Unknown strip property: '{prop}'. Valid: {valid_props}"
        )

    vse = _ensure_vse(project)
    strips = vse["strips"]

    if strip_index < 0 or strip_index >= len(strips):
        raise IndexError(
            f"Strip index {strip_index} out of range (0-{len(strips)-1})"
        )

    strip = strips[strip_index]

    if prop == "opacity":
        value = float(value)
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Opacity must be 0.0-1.0, got {value}")
        strip["opacity"] = value
    elif prop == "mute":
        if isinstance(value, str):
            value = value.lower() in ("true", "1", "yes")
        strip["mute"] = bool(value)
    elif prop == "blend_type":
        valid_blend = [
            "REPLACE", "CROSS", "ADD", "SUBTRACT", "MULTIPLY",
            "ALPHA_OVER", "ALPHA_UNDER", "OVER_DROP",
        ]
        value = str(value).upper()
        if value not in valid_blend:
            raise ValueError(
                f"Invalid blend type: '{value}'. Valid: {valid_blend}"
            )
        strip["blend_type"] = value
    elif prop == "name":
        strip["name"] = str(value)
    elif prop == "color":
        if isinstance(value, str):
            value = [float(x) for x in value.split(",")]
        if len(value) != 3:
            raise ValueError("Color must have 3 components [R, G, B]")
        for c in value:
            if not 0.0 <= c <= 1.0:
                raise ValueError(f"Color components must be 0.0-1.0, got {c}")
        strip["color"] = value
    elif prop == "text":
        strip["text"] = str(value)
    elif prop == "font_size":
        value = int(value)
        if value < 1:
            raise ValueError(f"Font size must be positive, got {value}")
        strip["font_size"] = value

    return strip


def add_transition(
    project: Dict[str, Any],
    transition_type: str,
    strip_a_index: int,
    strip_b_index: int,
    duration_frames: int = 30,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Add a transition between two strips.

    Args:
        project: The scene dict
        transition_type: Type of transition (cross, gamma_cross, wipe)
        strip_a_index: Index of the first strip
        strip_b_index: Index of the second strip
        duration_frames: Transition duration in frames
        params: Additional transition parameters

    Returns:
        The new transition strip dict
    """
    if transition_type not in VSE_TRANSITIONS:
        raise ValueError(
            f"Unknown transition type: '{transition_type}'. "
            f"Valid: {list(VSE_TRANSITIONS.keys())}"
        )

    vse = _ensure_vse(project)
    strips = vse["strips"]

    if strip_a_index < 0 or strip_a_index >= len(strips):
        raise IndexError(
            f"Strip A index {strip_a_index} out of range (0-{len(strips)-1})"
        )
    if strip_b_index < 0 or strip_b_index >= len(strips):
        raise IndexError(
            f"Strip B index {strip_b_index} out of range (0-{len(strips)-1})"
        )

    if duration_frames < 1:
        raise ValueError(f"Duration must be >= 1 frame, got {duration_frames}")

    strip_a = strips[strip_a_index]
    strip_b = strips[strip_b_index]

    # Transition sits between the two strips
    trans_channel = max(strip_a["channel"], strip_b["channel"]) + 1
    trans_start = strip_b["frame_start"]
    trans_end = trans_start + duration_frames

    strip_id = _next_id(vse)
    transition = {
        "id": strip_id,
        "type": "transition",
        "transition_type": transition_type,
        "bpy_type": VSE_TRANSITIONS[transition_type]["bpy_type"],
        "channel": trans_channel,
        "frame_start": trans_start,
        "frame_end": trans_end,
        "name": f"{transition_type}_{strip_id}",
        "strip_a": strip_a["id"],
        "strip_b": strip_b["id"],
        "duration_frames": duration_frames,
        "params": params or {},
        "blend_type": "REPLACE",
        "opacity": 1.0,
        "mute": False,
        "effects": [],
    }

    vse["strips"].append(transition)
    return transition


def add_effect(
    project: Dict[str, Any],
    strip_index: int,
    effect_type: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Add an effect to a VSE strip.

    Args:
        project: The scene dict
        strip_index: Index of the strip to add the effect to
        effect_type: Type of effect (transform, speed, glow, gaussian_blur, color_balance)
        params: Effect parameters

    Returns:
        The new effect dict
    """
    if effect_type not in VSE_EFFECTS:
        raise ValueError(
            f"Unknown effect type: '{effect_type}'. "
            f"Valid: {list(VSE_EFFECTS.keys())}"
        )

    vse = _ensure_vse(project)
    strips = vse["strips"]

    if strip_index < 0 or strip_index >= len(strips):
        raise IndexError(
            f"Strip index {strip_index} out of range (0-{len(strips)-1})"
        )

    strip = strips[strip_index]

    effect = {
        "type": effect_type,
        "bpy_type": VSE_EFFECTS[effect_type]["bpy_type"],
        "params": params or {},
    }

    strip["effects"].append(effect)
    return effect


def list_strips(project: Dict[str, Any]) -> List[Dict[str, Any]]:
    """List all VSE strips.

    Args:
        project: The scene dict

    Returns:
        List of strip summary dicts
    """
    vse = project.get("vse", {})
    strips = vse.get("strips", [])

    result = []
    for i, strip in enumerate(strips):
        summary = {
            "index": i,
            "id": strip["id"],
            "type": strip["type"],
            "name": strip["name"],
            "channel": strip["channel"],
            "frame_start": strip["frame_start"],
            "frame_end": strip["frame_end"],
            "mute": strip.get("mute", False),
        }
        if strip["type"] == "transition":
            summary["transition_type"] = strip.get("transition_type")
        result.append(summary)

    return result


def list_strip_types() -> List[Dict[str, Any]]:
    """List all available strip types.

    Returns:
        List of strip type info dicts
    """
    result = []
    for name, info in STRIP_TYPES.items():
        result.append({
            "name": name,
            "description": info["description"],
            "bpy_type": info["bpy_type"],
        })
    return result


def list_transitions() -> List[Dict[str, Any]]:
    """List all available transitions.

    Returns:
        List of transition info dicts
    """
    result = []
    for name, info in VSE_TRANSITIONS.items():
        result.append({
            "name": name,
            "description": info["description"],
            "bpy_type": info["bpy_type"],
        })
    return result


def list_effects() -> List[Dict[str, Any]]:
    """List all available effects.

    Returns:
        List of effect info dicts
    """
    result = []
    for name, info in VSE_EFFECTS.items():
        result.append({
            "name": name,
            "description": info["description"],
            "bpy_type": info["bpy_type"],
        })
    return result
