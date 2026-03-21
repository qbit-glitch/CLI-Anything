"""Advanced compositing: masking, alpha channels, and track mattes.

Provides shape masks (rectangle, ellipse), gradient masks, animated mask
parameters, and track matte compositing between tracks.
"""

from typing import Optional
from lxml import etree

from ..utils import mlt_xml
from .session import Session
from . import filters as filt_mod
from . import keyframes as kf_mod


# ---------------------------------------------------------------------------
# Mask type definitions
# ---------------------------------------------------------------------------

MASK_TYPES = {
    "rectangle": {
        "service": "frei0r.alphaspot",
        "description": "Rectangular alpha mask",
        "params": {
            "shape": "0",
            "position_x": "0.5",
            "position_y": "0.5",
            "size_x": "0.5",
            "size_y": "0.5",
        },
    },
    "ellipse": {
        "service": "frei0r.alphaspot",
        "description": "Elliptical alpha mask",
        "params": {
            "shape": "1",
            "position_x": "0.5",
            "position_y": "0.5",
            "size_x": "0.5",
            "size_y": "0.5",
        },
    },
    "gradient_horizontal": {
        "service": "frei0r.alphagrad",
        "description": "Horizontal gradient alpha mask",
        "params": {
            "position": "0.5",
            "tilt": "0",
            "min": "0.0",
            "max": "1.0",
        },
    },
    "gradient_vertical": {
        "service": "frei0r.alphagrad",
        "description": "Vertical gradient alpha mask",
        "params": {
            "position": "0.5",
            "tilt": "0.25",
            "min": "0.0",
            "max": "1.0",
        },
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_mask_types() -> list[dict]:
    """Return available mask types with their descriptions and parameters."""
    result = []
    for name, info in sorted(MASK_TYPES.items()):
        result.append({
            "name": name,
            "service": info["service"],
            "description": info["description"],
            "params": list(info["params"].keys()),
        })
    return result


def add_mask(session: Session, mask_type: str,
             track_index: Optional[int] = None,
             clip_index: Optional[int] = None,
             params: Optional[dict] = None,
             feather: float = 0.0,
             invert: bool = False) -> dict:
    """Add an alpha-mask filter to a clip, track, or globally.

    Args:
        session: Active session
        mask_type: One of MASK_TYPES keys
        track_index: Target track (None = global)
        clip_index: Target clip on the track (None = whole track)
        params: Overrides for the mask's default properties
        feather: Edge feather amount (0.0 = hard edge)
        invert: If True, invert the alpha mask
    """
    if mask_type not in MASK_TYPES:
        available = ", ".join(sorted(MASK_TYPES.keys()))
        raise ValueError(
            f"Unknown mask type: {mask_type!r}. Available: {available}"
        )

    session.checkpoint()

    info = MASK_TYPES[mask_type]
    service = info["service"]

    # Build properties: start with defaults, apply overrides
    props = dict(info["params"])
    if params:
        props.update(params)

    # Optional feather and invert
    if feather != 0.0:
        props["feather"] = str(feather)
    if invert:
        props["invert"] = "1"

    target = filt_mod._resolve_target(session, track_index, clip_index)
    filt = mlt_xml.add_filter_to_element(target, service, props)

    # Determine filter index (position among all filters on target)
    filters_on_target = target.findall("filter")
    filter_index = list(filters_on_target).index(filt)

    target_desc = "global"
    if track_index is not None and clip_index is not None:
        target_desc = f"track {track_index}, clip {clip_index}"
    elif track_index is not None:
        target_desc = f"track {track_index}"

    return {
        "action": "add_mask",
        "mask_type": mask_type,
        "service": service,
        "filter_id": filt.get("id"),
        "filter_index": filter_index,
        "target": target_desc,
        "params": props,
    }


def set_mask_param(session: Session, filter_index: int,
                   param: str, value: str,
                   track_index: Optional[int] = None,
                   clip_index: Optional[int] = None) -> dict:
    """Set a property on an existing mask filter.

    Args:
        session: Active session
        filter_index: Index of the mask filter on the target element
        param: Property name to set
        value: New property value
        track_index: Target track (None = global)
        clip_index: Target clip (None = track-level)
    """
    session.checkpoint()
    target = filt_mod._resolve_target(session, track_index, clip_index)

    filters = target.findall("filter")
    if filter_index < 0 or filter_index >= len(filters):
        raise IndexError(
            f"Filter index {filter_index} out of range (0-{len(filters) - 1})"
        )

    filt = filters[filter_index]
    old_value = mlt_xml.get_property(filt, param)
    mlt_xml.set_property(filt, param, value)

    return {
        "action": "set_mask_param",
        "filter_index": filter_index,
        "param": param,
        "old_value": old_value,
        "new_value": value,
    }


def animate_mask(session: Session, filter_index: int,
                 param: str, keyframes: list[dict],
                 track_index: Optional[int] = None,
                 clip_index: Optional[int] = None) -> dict:
    """Animate a mask parameter over time using keyframes.

    Args:
        session: Active session
        filter_index: Index of the mask filter
        param: The property to animate (e.g. "position_x")
        keyframes: List of dicts with keys ``time``, ``value``,
            and optional ``easing``
        track_index: Target track (None = global)
        clip_index: Target clip (None = track-level)
    """
    session.checkpoint()
    target = filt_mod._resolve_target(session, track_index, clip_index)

    filters = target.findall("filter")
    if filter_index < 0 or filter_index >= len(filters):
        raise IndexError(
            f"Filter index {filter_index} out of range (0-{len(filters) - 1})"
        )

    filt = filters[filter_index]

    # Read existing keyframes from the property
    current = mlt_xml.get_property(filt, param, "")
    existing_kfs = kf_mod.parse_mlt_keyframe_string(current) if current and "=" in current else []

    applied = []
    for kf in keyframes:
        time_val = kf["time"]
        value_val = kf["value"]
        easing = kf.get("easing", "linear")

        # Replace or append
        replaced = False
        for ekf in existing_kfs:
            if kf_mod._compare_time(ekf["time"], time_val) == 0:
                ekf["value"] = value_val
                ekf["easing"] = easing
                replaced = True
                break
        if not replaced:
            existing_kfs.append({"time": time_val, "value": value_val, "easing": easing})

        applied.append({"time": time_val, "value": value_val, "easing": easing})

    # Sort and write back
    existing_kfs.sort(key=lambda k: kf_mod._tc_to_seconds(k["time"]))
    mlt_xml.set_property(filt, param, kf_mod.generate_mlt_keyframe_string(existing_kfs))

    return {
        "action": "animate_mask",
        "filter_index": filter_index,
        "param": param,
        "keyframes_applied": len(applied),
        "keyframes": applied,
    }


def add_track_matte(session: Session, source_track: int,
                    target_track: int) -> dict:
    """Add a track-matte transition between two tracks.

    Uses ``frei0r.alphatop`` to composite *target_track* through the
    alpha channel produced by *source_track*.

    Args:
        session: Active session
        source_track: Track index providing the matte (alpha)
        target_track: Track index to apply the matte to
    """
    session.checkpoint()
    tractor = session.get_main_tractor()
    tracks = mlt_xml.get_tractor_tracks(tractor)

    for idx, label in [(source_track, "source"), (target_track, "target")]:
        if idx < 0 or idx >= len(tracks):
            raise IndexError(
                f"{label.capitalize()} track index {idx} out of range "
                f"(0-{len(tracks) - 1})"
            )

    trans = etree.SubElement(tractor, "transition")
    trans.set("id", mlt_xml.new_id("transition"))
    mlt_xml.set_property(trans, "mlt_service", "frei0r.alphatop")
    mlt_xml.set_property(trans, "a_track", str(source_track))
    mlt_xml.set_property(trans, "b_track", str(target_track))
    mlt_xml.set_property(trans, "always_active", "1")

    return {
        "action": "add_track_matte",
        "transition_id": trans.get("id"),
        "source_track": source_track,
        "target_track": target_track,
        "service": "frei0r.alphatop",
    }


def list_masks(session: Session,
               track_index: Optional[int] = None,
               clip_index: Optional[int] = None) -> list[dict]:
    """List all alpha-type mask filters on a target element.

    Identifies filters whose MLT service is one of the known alpha
    services (``frei0r.alphaspot``, ``frei0r.alphagrad``).
    """
    _ALPHA_SERVICES = {"frei0r.alphaspot", "frei0r.alphagrad"}

    target = filt_mod._resolve_target(session, track_index, clip_index)
    filters = target.findall("filter")

    result = []
    for i, filt in enumerate(filters):
        service = mlt_xml.get_property(filt, "mlt_service", "")
        if service not in _ALPHA_SERVICES:
            continue

        props = {}
        for prop in filt.findall("property"):
            name = prop.get("name", "")
            if name and name != "mlt_service":
                props[name] = prop.text or ""

        # Determine mask type
        mask_type = _identify_mask_type(service, props)

        result.append({
            "index": i,
            "id": filt.get("id"),
            "service": service,
            "mask_type": mask_type,
            "params": props,
        })

    return result


def remove_mask(session: Session, filter_index: int,
                track_index: Optional[int] = None,
                clip_index: Optional[int] = None) -> dict:
    """Remove a mask filter by index from a target element.

    Args:
        session: Active session
        filter_index: Index of the filter among all filters on the target
        track_index: Target track (None = global)
        clip_index: Target clip (None = track-level)
    """
    session.checkpoint()
    target = filt_mod._resolve_target(session, track_index, clip_index)

    filters = target.findall("filter")
    if filter_index < 0 or filter_index >= len(filters):
        raise IndexError(
            f"Filter index {filter_index} out of range (0-{len(filters) - 1})"
        )

    filt = filters[filter_index]
    filter_id = filt.get("id")
    service = mlt_xml.get_property(filt, "mlt_service", "")
    target.remove(filt)

    return {
        "action": "remove_mask",
        "filter_index": filter_index,
        "filter_id": filter_id,
        "service": service,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _identify_mask_type(service: str, props: dict) -> str:
    """Try to identify which MASK_TYPES entry a filter corresponds to."""
    if service == "frei0r.alphaspot":
        shape = props.get("shape", "0")
        if shape == "1":
            return "ellipse"
        return "rectangle"
    elif service == "frei0r.alphagrad":
        tilt = props.get("tilt", "0")
        try:
            if float(tilt) >= 0.2:
                return "gradient_vertical"
        except ValueError:
            pass
        return "gradient_horizontal"
    return "unknown"
