"""Inkscape CLI - SVG SMIL animation utilities.

Provides functions for generating SMIL animation elements (animate,
animateTransform) and for rendering animated SVG to PNG frame sequences.
"""

from __future__ import annotations

import math
import os
import re
import sys
import tempfile
from typing import List, Optional

# ---------------------------------------------------------------------------
# Shared motion_math easings (optional)
# ---------------------------------------------------------------------------

def _load_shared_easings():
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        candidate = os.path.join(here, "shared", "motion_math")
        if os.path.isdir(candidate):
            parent = os.path.dirname(candidate)
            if parent not in sys.path:
                sys.path.insert(0, parent)
            try:
                from motion_math.easing import EASING_FUNCTIONS
                return EASING_FUNCTIONS
            except ImportError:
                pass
        here = os.path.dirname(here)
    return None


_SHARED_EASINGS = _load_shared_easings()

# ---------------------------------------------------------------------------
# SMIL easing → calcMode / keySplines mapping
# ---------------------------------------------------------------------------

_SMIL_CALC_MODE = {
    "linear": ("linear", None),
    "discrete": ("discrete", None),
    "paced": ("paced", None),
    # CSS-style aliases
    "ease": ("spline", "0.25 0.1 0.25 1"),
    "ease-in": ("spline", "0.42 0 1 1"),
    "ease-out": ("spline", "0 0 0.58 1"),
    "ease-in-out": ("spline", "0.42 0 0.58 1"),
}


def _easing_to_smil(easing: str) -> tuple[str, Optional[str]]:
    """Convert an easing name to (calcMode, keySplines_or_None)."""
    lower = easing.lower().strip()
    if lower in _SMIL_CALC_MODE:
        return _SMIL_CALC_MODE[lower]
    # Penner easings that map to common cubic-bezier curves
    _penner_map = {
        "ease_in_quad":     "0.55 0.085 0.68 0.53",
        "ease_out_quad":    "0.25 0.46 0.45 0.94",
        "ease_in_out_quad": "0.455 0.03 0.515 0.955",
        "ease_in_cubic":    "0.55 0.055 0.675 0.19",
        "ease_out_cubic":   "0.215 0.61 0.355 1",
        "ease_in_out_cubic": "0.645 0.045 0.355 1",
        "ease_in_quart":    "0.895 0.03 0.685 0.22",
        "ease_out_quart":   "0.165 0.84 0.44 1",
        "ease_in_out_quart": "0.77 0 0.175 1",
        "ease_in_sine":     "0.47 0 0.745 0.715",
        "ease_out_sine":    "0.39 0.575 0.565 1",
        "ease_in_out_sine": "0.445 0.05 0.55 0.95",
        "ease_in_expo":     "0.95 0.05 0.795 0.035",
        "ease_out_expo":    "0.19 1 0.22 1",
        "ease_in_out_expo": "1 0 0 1",
        "ease_in_circ":     "0.6 0.04 0.98 0.335",
        "ease_out_circ":    "0.075 0.82 0.165 1",
        "ease_in_out_circ": "0.785 0.135 0.15 0.86",
    }
    if lower in _penner_map:
        return ("spline", _penner_map[lower])
    # Fall back to linear for anything unrecognized
    return ("linear", None)


# ---------------------------------------------------------------------------
# Value list builder with easing-based interpolation
# ---------------------------------------------------------------------------

def _build_values_string(values: list) -> str:
    """Join a list of values (numbers or strings) into SMIL 'values' format."""
    return ";".join(str(v) for v in values)


def _interpolated_values(start, end, steps: int, easing: str) -> list:
    """Generate a list of interpolated values with easing applied.

    Args:
        start: Starting numeric value.
        end: Ending numeric value.
        steps: Number of keyframe stops (including start and end).
        easing: Easing name.

    Returns:
        List of floats.
    """
    if steps < 2:
        return [start, end]

    fn = None
    if _SHARED_EASINGS:
        fn = _SHARED_EASINGS.get(easing.lower())
    if fn is None:
        fn = lambda t: t  # linear

    result = []
    for i in range(steps):
        t = i / (steps - 1)
        eased = fn(t)
        result.append(start + (end - start) * eased)
    return result


# ---------------------------------------------------------------------------
# Core SMIL element generators
# ---------------------------------------------------------------------------

def animate_attribute(
    element_id: str,
    attr_name: str,
    values: list,
    duration: float,
    easing: str = "linear",
    repeat_count: str = "indefinite",
    begin: str = "0s",
) -> str:
    """Generate a SMIL <animate> element string.

    Args:
        element_id: Target element ID (used for xlink:href).
        attr_name: The SVG attribute to animate (e.g. "opacity").
        values: List of keyframe values. If two numeric values are given,
                intermediate stops are auto-generated with easing applied.
        duration: Animation duration in seconds.
        easing: Easing name (linear, ease, ease_in_cubic, etc.).
        repeat_count: SMIL repeatCount (default "indefinite").
        begin: SMIL begin time (default "0s").

    Returns:
        SMIL <animate> element as a string.
    """
    calc_mode, key_splines = _easing_to_smil(easing)

    # For numeric 2-value pairs with spline easing, add intermediate stops
    if (
        len(values) == 2
        and calc_mode == "spline"
        and all(isinstance(v, (int, float)) for v in values)
    ):
        intermediate = _interpolated_values(values[0], values[1], 5, easing)
        values_str = _build_values_string([round(v, 6) for v in intermediate])
        # Repeat key_splines for N-1 segments
        n_segments = len(intermediate) - 1
        splines_str = ";".join([key_splines] * n_segments)
        key_times = ";".join([str(round(i / (len(intermediate) - 1), 6))
                               for i in range(len(intermediate))])
    else:
        values_str = _build_values_string(values)
        splines_str = None
        key_times = None

    parts = [
        f'<animate',
        f'  xlink:href="#{element_id}"',
        f'  attributeName="{attr_name}"',
        f'  values="{values_str}"',
        f'  dur="{duration}s"',
        f'  begin="{begin}"',
        f'  repeatCount="{repeat_count}"',
        f'  calcMode="{calc_mode}"',
    ]
    if key_times:
        parts.append(f'  keyTimes="{key_times}"')
    if splines_str:
        parts.append(f'  keySplines="{splines_str}"')
    parts.append('/>')

    return "\n".join(parts)


def animate_transform(
    element_id: str,
    transform_type: str,
    from_val: str,
    to_val: str,
    duration: float,
    easing: str = "linear",
    repeat_count: str = "indefinite",
    begin: str = "0s",
    additive: str = "replace",
) -> str:
    """Generate a SMIL <animateTransform> element.

    Args:
        element_id: Target element ID.
        transform_type: "rotate", "scale", or "translate".
        from_val: Starting value string (e.g. "0 50 50" for rotate).
        to_val: Ending value string.
        duration: Duration in seconds.
        easing: Easing name.
        repeat_count: SMIL repeatCount.
        begin: SMIL begin time.
        additive: "replace" or "sum".

    Returns:
        SMIL <animateTransform> element string.
    """
    valid_types = {"rotate", "scale", "translate", "skewX", "skewY"}
    if transform_type not in valid_types:
        raise ValueError(
            f"Invalid transform_type '{transform_type}'. "
            f"Valid: {sorted(valid_types)}"
        )

    calc_mode, key_splines = _easing_to_smil(easing)

    parts = [
        f'<animateTransform',
        f'  xlink:href="#{element_id}"',
        f'  attributeName="transform"',
        f'  attributeType="XML"',
        f'  type="{transform_type}"',
        f'  from="{from_val}"',
        f'  to="{to_val}"',
        f'  dur="{duration}s"',
        f'  begin="{begin}"',
        f'  repeatCount="{repeat_count}"',
        f'  additive="{additive}"',
        f'  calcMode="{calc_mode}"',
    ]
    if key_splines:
        parts.append(f'  keySplines="{key_splines}"')
        parts.append(f'  keyTimes="0;1"')
    parts.append('/>')

    return "\n".join(parts)


def morph_path(
    path_a_d: str,
    path_b_d: str,
    duration: float,
    easing: str = "linear",
    repeat_count: str = "indefinite",
    begin: str = "0s",
    element_id: str = "path",
) -> str:
    """Generate SMIL path morphing animation.

    Both paths must have the same number and types of path commands for
    valid browser rendering. This function does not validate compatibility —
    it trusts the caller.

    Args:
        path_a_d: SVG 'd' attribute string for start shape.
        path_b_d: SVG 'd' attribute string for end shape.
        duration: Animation duration in seconds.
        easing: Easing name.
        repeat_count: SMIL repeatCount.
        begin: SMIL begin time.
        element_id: Target element ID.

    Returns:
        SMIL <animate> element string for path morphing.
    """
    calc_mode, key_splines = _easing_to_smil(easing)

    # Path values separated by semicolons
    values_str = f"{path_a_d};{path_b_d}"

    parts = [
        f'<animate',
        f'  xlink:href="#{element_id}"',
        f'  attributeName="d"',
        f'  values="{values_str}"',
        f'  dur="{duration}s"',
        f'  begin="{begin}"',
        f'  repeatCount="{repeat_count}"',
        f'  calcMode="{calc_mode}"',
    ]
    if key_splines:
        parts.append(f'  keySplines="{key_splines}"')
        parts.append('  keyTimes="0;1"')
    parts.append('/>')

    return "\n".join(parts)


def animate_stroke_dashoffset(
    path_id: str,
    duration: float,
    path_length: Optional[float] = None,
    repeat_count: str = "1",
    begin: str = "0s",
    easing: str = "linear",
) -> str:
    """Line drawing effect — animate stroke-dashoffset from full to 0.

    To use this, the target element must have:
        stroke-dasharray: <path_length>
        stroke-dashoffset: <path_length>  (initial)

    Animating dashoffset from path_length → 0 makes the stroke appear to
    draw itself.

    Args:
        path_id: Target SVG element ID.
        duration: Duration in seconds.
        path_length: Total path length. Defaults to 1000 (a safe large value
                     when the actual length is unknown).
        repeat_count: Default "1" (plays once). Use "indefinite" to loop.
        begin: SMIL begin time.
        easing: Easing name.

    Returns:
        Two SMIL elements: one to set up dasharray, one to animate dashoffset.
    """
    if path_length is None:
        path_length = 1000.0

    calc_mode, key_splines = _easing_to_smil(easing)

    # animate the dashoffset
    parts = [
        f'<animate',
        f'  xlink:href="#{path_id}"',
        f'  attributeName="stroke-dashoffset"',
        f'  values="{path_length};0"',
        f'  dur="{duration}s"',
        f'  begin="{begin}"',
        f'  repeatCount="{repeat_count}"',
        f'  calcMode="{calc_mode}"',
    ]
    if key_splines:
        parts.append(f'  keySplines="{key_splines}"')
        parts.append('  keyTimes="0;1"')
    parts.append('/>')

    # Also emit the dasharray setter as a <set> element (applied immediately)
    set_dasharray = (
        f'<set xlink:href="#{path_id}" attributeName="stroke-dasharray" '
        f'to="{path_length}" />'
    )

    return set_dasharray + "\n" + "\n".join(parts)


# ---------------------------------------------------------------------------
# Frame sequence renderer
# ---------------------------------------------------------------------------

def _interpolate_smil_value(value_list: list, t: float):
    """Linearly interpolate within a list of numeric values at position t [0,1]."""
    if not value_list:
        return None
    if len(value_list) == 1:
        return value_list[0]
    n = len(value_list) - 1
    scaled = t * n
    idx = int(scaled)
    frac = scaled - idx
    if idx >= n:
        return value_list[n]
    a = value_list[idx]
    b = value_list[idx + 1]
    try:
        return a + (b - a) * frac
    except TypeError:
        return a if frac < 0.5 else b


def _parse_smil_values(values_str: str) -> list:
    """Parse SMIL 'values' attribute into list (numeric or string)."""
    parts = values_str.split(";")
    result = []
    for p in parts:
        p = p.strip()
        try:
            result.append(float(p))
        except ValueError:
            result.append(p)
    return result


def _find_animate_elements(svg_content: str) -> list[dict]:
    """Extract basic animate element info from SVG source."""
    pattern = re.compile(
        r'<animate\b([^>]*/?>)',
        re.DOTALL | re.IGNORECASE,
    )
    results = []
    for m in pattern.finditer(svg_content):
        attrs_str = m.group(1)
        def _attr(name):
            am = re.search(
                r'\b' + re.escape(name) + r'\s*=\s*["\']([^"\']*)["\']',
                attrs_str, re.IGNORECASE
            )
            return am.group(1) if am else None

        href = _attr("xlink:href") or _attr("href")
        if href and href.startswith("#"):
            href = href[1:]
        results.append({
            "element_id": href,
            "attr_name": _attr("attributeName"),
            "values": _parse_smil_values(_attr("values") or ""),
            "dur": _attr("dur"),
        })
    return results


def _update_svg_attribute(svg: str, element_id: str, attr_name: str, value) -> str:
    """Crudely update an attribute on an element with a given id in SVG source."""
    # Find element with matching id
    id_pat = re.compile(
        r'(<(?:path|rect|circle|ellipse|polygon|polyline|line|g|text)\b[^>]*?\bid\s*=\s*["\']'
        + re.escape(element_id) + r'["\'][^>]*?)(/?>)',
        re.DOTALL | re.IGNORECASE,
    )

    def _replace_element(m):
        elem = m.group(1)
        close = m.group(2)
        attr_name_lower = attr_name.lower()
        attr_pat = re.compile(
            r'\b' + re.escape(attr_name) + r'\s*=\s*["\'][^"\']*["\']',
            re.IGNORECASE,
        )
        new_attr = f'{attr_name}="{value}"'
        if attr_pat.search(elem):
            elem = attr_pat.sub(new_attr, elem)
        else:
            elem = elem.rstrip() + f' {new_attr}'
        return elem + close

    return id_pat.sub(_replace_element, svg)


def render_svg_sequence(
    svg_content: str,
    frame_count: int,
    fps: int,
    output_dir: str,
) -> dict:
    """Render an animated SVG to a PNG frame sequence.

    For each frame: interpolate animated values, update SVG attributes,
    render to PNG using Cairo (cairosvg) or Inkscape CLI (inkscape --export-png)
    or fall back to writing the SVG file only.

    Args:
        svg_content: Full SVG XML string.
        frame_count: Number of frames to render.
        fps: Frames per second.
        output_dir: Directory for output PNG files.

    Returns:
        Dict with output_dir, frame_count, fps, frames (list of paths), renderer.
    """
    os.makedirs(output_dir, exist_ok=True)
    duration = frame_count / fps

    # Detect animate elements
    animations = _find_animate_elements(svg_content)

    # Detect available renderer
    renderer_used = "svg_only"
    try:
        import cairosvg
        renderer_used = "cairosvg"
    except ImportError:
        pass

    frames = []
    for frame_num in range(frame_count):
        t = frame_num / max(frame_count - 1, 1)  # 0.0 to 1.0

        # Apply interpolated values to a copy of the SVG
        current_svg = svg_content
        for anim in animations:
            if not anim["element_id"] or not anim["attr_name"]:
                continue
            interpolated = _interpolate_smil_value(anim["values"], t)
            if interpolated is not None:
                current_svg = _update_svg_attribute(
                    current_svg, anim["element_id"], anim["attr_name"], interpolated
                )

        # Remove SMIL animation elements from the per-frame SVG
        current_svg = re.sub(
            r'<animate\b[^>]*/?>',
            '',
            current_svg,
            flags=re.DOTALL | re.IGNORECASE,
        )
        current_svg = re.sub(
            r'<animateTransform\b[^>]*/?>',
            '',
            current_svg,
            flags=re.DOTALL | re.IGNORECASE,
        )
        current_svg = re.sub(
            r'<set\b[^>]*/?>',
            '',
            current_svg,
            flags=re.DOTALL | re.IGNORECASE,
        )

        png_path = os.path.join(output_dir, f"frame_{frame_num:04d}.png")

        if renderer_used == "cairosvg":
            import cairosvg
            cairosvg.svg2png(bytestring=current_svg.encode("utf-8"), write_to=png_path)
        else:
            # Try inkscape CLI
            svg_tmp = os.path.join(output_dir, f"_frame_{frame_num:04d}.svg")
            with open(svg_tmp, "w", encoding="utf-8") as f:
                f.write(current_svg)

            inkscape_ok = False
            import subprocess
            for inkscape_cmd in ["inkscape", "/usr/bin/inkscape", "/usr/local/bin/inkscape"]:
                try:
                    result = subprocess.run(
                        [inkscape_cmd, svg_tmp, f"--export-png={png_path}"],
                        capture_output=True, timeout=10,
                    )
                    if result.returncode == 0 and os.path.isfile(png_path):
                        inkscape_ok = True
                        renderer_used = "inkscape_cli"
                        break
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass

            # Try Inkscape 1.x syntax
            if not inkscape_ok:
                for inkscape_cmd in ["inkscape", "/usr/bin/inkscape"]:
                    try:
                        result = subprocess.run(
                            [inkscape_cmd, "--export-type=png",
                             f"--export-filename={png_path}", svg_tmp],
                            capture_output=True, timeout=10,
                        )
                        if result.returncode == 0 and os.path.isfile(png_path):
                            inkscape_ok = True
                            renderer_used = "inkscape_cli"
                            break
                    except (FileNotFoundError, subprocess.TimeoutExpired):
                        pass

            if not inkscape_ok:
                # Save SVG only (no PNG)
                renderer_used = "svg_only"
                png_path = svg_tmp  # report SVG path instead

        frames.append(os.path.abspath(png_path))

    return {
        "output_dir": os.path.abspath(output_dir),
        "frame_count": frame_count,
        "fps": fps,
        "duration": duration,
        "frames": frames,
        "renderer": renderer_used,
    }
