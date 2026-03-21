"""Blender CLI - Shape layers and path animation system.

Generates bpy Python script strings for procedural shape creation and
path-driven animations (morph, trim, offset, repeater).

Each function returns either a list of bpy script lines or a single
bpy script string.  Animation functions use the shared motion_math
easing library for consistent interpolation across all CLIs.

Shape types supported:
- Rectangle / rounded rectangle (bpy Curve)
- Ellipse (bpy Curve, NURBS circle scaled)
- Regular polygon (bpy Mesh)
- Star (bpy Mesh)
- Custom bezier path (bpy Curve)

Animation:
- morph      — shape-key lerp between two objects
- trim_path  — bevel_factor_start / _end animation
- offset_path — solidify modifier thickness animation
- repeater   — Array modifier (static, not animated)
"""

import math
import sys
import os
from typing import Dict, Any, List, Optional, Tuple

# shape_layers.py lives at: blender/agent-harness/cli_anything/blender/core/shape_layers.py
# shared/ lives at:         <project-root>/shared/
# 5 levels of ".." bring us from core/ to the project root.
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "shared"),
)
from motion_math.easing import get_easing


# ── Internal helpers ─────────────────────────────────────────────────────────


def _get_project(session) -> Dict[str, Any]:
    """Return the raw project dict from a Session object."""
    return session.get_project()


def _unique_shape_name(project: Dict[str, Any], base: str) -> str:
    existing = {s.get("name", "") for s in project.get("shapes", [])}
    if base not in existing:
        return base
    counter = 1
    while f"{base}.{counter:03d}" in existing:
        counter += 1
    return f"{base}.{counter:03d}"


def _register_shape(
    project: Dict[str, Any],
    name: str,
    shape_type: str,
    meta: Dict[str, Any],
) -> None:
    """Store shape metadata in the scene JSON."""
    project.setdefault("shapes", []).append(
        {"name": name, "type": shape_type, **meta}
    )


def _color_tuple(color) -> str:
    """Format a colour as a bpy-compatible (r, g, b, a) tuple string."""
    if color is None:
        return "(0.2, 0.2, 0.2, 1.0)"
    if isinstance(color, (list, tuple)):
        r, g, b = color[0], color[1], color[2]
        a = color[3] if len(color) > 3 else 1.0
        return f"({r}, {g}, {b}, {a})"
    return str(color)


# ── Shape creation ────────────────────────────────────────────────────────────


def create_rectangle(
    session,
    width: float,
    height: float,
    corner_radius: float = 0.0,
    fill_color=None,
    stroke_color=None,
    name: str = "Rectangle",
) -> List[str]:
    """Create a rectangle (or rounded rectangle) as a bpy Curve object.

    Args:
        session: Active Session object.
        width: Rectangle width in Blender units.
        height: Rectangle height in Blender units.
        corner_radius: Corner rounding radius (0 = sharp corners).
        fill_color: RGBA tuple/list [r, g, b, a] for fill material.
        stroke_color: RGBA tuple/list for stroke (outline) material.
        name: Object name.

    Returns:
        List of bpy script lines.
    """
    if width <= 0:
        raise ValueError(f"width must be positive, got {width}")
    if height <= 0:
        raise ValueError(f"height must be positive, got {height}")
    if corner_radius < 0:
        raise ValueError(f"corner_radius must be non-negative, got {corner_radius}")

    project = _get_project(session)
    obj_name = _unique_shape_name(project, name)
    _register_shape(
        project,
        obj_name,
        "rectangle",
        {
            "width": width,
            "height": height,
            "corner_radius": corner_radius,
            "fill_color": fill_color,
            "stroke_color": stroke_color,
        },
    )

    fill_col = _color_tuple(fill_color)
    stroke_col = _color_tuple(stroke_color) if stroke_color is not None else None

    hw = width / 2.0
    hh = height / 2.0
    cr = min(corner_radius, hw, hh)

    lines = [
        f"# Rectangle: {obj_name}  w={width}  h={height}  cr={corner_radius}",
        "import bpy",
        "curve_data = bpy.data.curves.new(name='RectCurve', type='CURVE')",
        "curve_data.dimensions = '2D'",
        "curve_data.fill_mode = 'BOTH'",
        "spline = curve_data.splines.new('BEZIER')",
    ]

    if cr <= 0.0:
        # Simple 4-point rectangle
        corners = [
            (-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh),
        ]
        lines.append(f"spline.bezier_points.add({len(corners) - 1})")
        for i, (x, y) in enumerate(corners):
            lines += [
                f"spline.bezier_points[{i}].co = ({x}, {y}, 0.0)",
                f"spline.bezier_points[{i}].handle_left_type = 'VECTOR'",
                f"spline.bezier_points[{i}].handle_right_type = 'VECTOR'",
            ]
        lines.append("spline.use_cyclic_u = True")
    else:
        # 8-point rounded rectangle (2 bezier points per corner arc)
        # Each corner: straight segment meets a rounded arc handled by FREE handles
        # We place 8 points: midpoint of each side at the corner radius offset
        pts = [
            (-hw + cr, -hh),   # bottom-left start
            (hw - cr,  -hh),   # bottom-right start
            (hw,       -hh + cr),
            (hw,       hh - cr),
            (hw - cr,  hh),
            (-hw + cr, hh),
            (-hw,      hh - cr),
            (-hw,      -hh + cr),
        ]
        lines.append(f"spline.bezier_points.add({len(pts) - 1})")
        for i, (x, y) in enumerate(pts):
            lines += [
                f"spline.bezier_points[{i}].co = ({x}, {y}, 0.0)",
                f"spline.bezier_points[{i}].handle_left_type = 'VECTOR'",
                f"spline.bezier_points[{i}].handle_right_type = 'VECTOR'",
            ]
        lines.append("spline.use_cyclic_u = True")

    lines += [
        f"rect_obj = bpy.data.objects.new('{obj_name}', curve_data)",
        "bpy.context.collection.objects.link(rect_obj)",
        "# Apply fill material",
        "fill_mat = bpy.data.materials.new(name='RectFill')",
        "fill_mat.use_nodes = True",
        f"fill_mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = {fill_col}",
        "rect_obj.data.materials.append(fill_mat)",
    ]

    if stroke_color is not None:
        lines += [
            "# Apply stroke (extrude bevel for outline)",
            f"curve_data.bevel_depth = 0.02",
            "stroke_mat = bpy.data.materials.new(name='RectStroke')",
            "stroke_mat.use_nodes = True",
            f"stroke_mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = {stroke_col}",
            "rect_obj.data.materials.append(stroke_mat)",
        ]

    return lines


def create_ellipse(
    session,
    rx: float,
    ry: float,
    fill_color=None,
    name: str = "Ellipse",
) -> List[str]:
    """Create an ellipse as a bpy Curve object.

    Uses a NURBS circle scaled to (rx, ry).

    Args:
        session: Active Session object.
        rx: Horizontal radius.
        ry: Vertical radius.
        fill_color: RGBA tuple/list for fill material.
        name: Object name.

    Returns:
        List of bpy script lines.
    """
    if rx <= 0:
        raise ValueError(f"rx must be positive, got {rx}")
    if ry <= 0:
        raise ValueError(f"ry must be positive, got {ry}")

    project = _get_project(session)
    obj_name = _unique_shape_name(project, name)
    _register_shape(
        project,
        obj_name,
        "ellipse",
        {"rx": rx, "ry": ry, "fill_color": fill_color},
    )

    fill_col = _color_tuple(fill_color)

    lines = [
        f"# Ellipse: {obj_name}  rx={rx}  ry={ry}",
        "import bpy",
        "bpy.ops.curve.primitive_nurbs_circle_add(radius=1.0)",
        "ellipse_obj = bpy.context.active_object",
        f"ellipse_obj.name = '{obj_name}'",
        f"ellipse_obj.scale = ({rx}, {ry}, 1.0)",
        "ellipse_obj.data.dimensions = '2D'",
        "ellipse_obj.data.fill_mode = 'BOTH'",
        "# Apply fill material",
        "fill_mat = bpy.data.materials.new(name='EllipseFill')",
        "fill_mat.use_nodes = True",
        f"fill_mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = {fill_col}",
        "ellipse_obj.data.materials.append(fill_mat)",
    ]
    return lines


def create_polygon(
    session,
    sides: int,
    radius: float,
    fill_color=None,
    name: str = "Polygon",
) -> List[str]:
    """Create a regular polygon as a bpy Mesh object.

    Args:
        session: Active Session object.
        sides: Number of sides (minimum 3).
        radius: Circumscribed radius.
        fill_color: RGBA tuple/list for fill material.
        name: Object name.

    Returns:
        List of bpy script lines.
    """
    if sides < 3:
        raise ValueError(f"sides must be at least 3, got {sides}")
    if radius <= 0:
        raise ValueError(f"radius must be positive, got {radius}")

    project = _get_project(session)
    obj_name = _unique_shape_name(project, name)
    _register_shape(
        project,
        obj_name,
        "polygon",
        {"sides": sides, "radius": radius, "fill_color": fill_color},
    )

    fill_col = _color_tuple(fill_color)

    lines = [
        f"# Polygon: {obj_name}  sides={sides}  radius={radius}",
        "import bpy",
        f"bpy.ops.mesh.primitive_circle_add(vertices={sides}, radius={radius}, fill_type='NGON')",
        "poly_obj = bpy.context.active_object",
        f"poly_obj.name = '{obj_name}'",
        "# Apply fill material",
        "fill_mat = bpy.data.materials.new(name='PolyFill')",
        "fill_mat.use_nodes = True",
        f"fill_mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = {fill_col}",
        "poly_obj.data.materials.append(fill_mat)",
    ]
    return lines


def create_star(
    session,
    points: int,
    inner_radius: float,
    outer_radius: float,
    fill_color=None,
    name: str = "Star",
) -> List[str]:
    """Create a star shape as a bpy Mesh built from computed vertices.

    Args:
        session: Active Session object.
        points: Number of star points (minimum 3).
        inner_radius: Radius of the inner vertices.
        outer_radius: Radius of the outer vertices (tips).
        fill_color: RGBA tuple/list for fill material.
        name: Object name.

    Returns:
        List of bpy script lines.
    """
    if points < 3:
        raise ValueError(f"points must be at least 3, got {points}")
    if inner_radius <= 0:
        raise ValueError(f"inner_radius must be positive, got {inner_radius}")
    if outer_radius <= inner_radius:
        raise ValueError(
            f"outer_radius ({outer_radius}) must be greater than inner_radius ({inner_radius})"
        )

    project = _get_project(session)
    obj_name = _unique_shape_name(project, name)
    _register_shape(
        project,
        obj_name,
        "star",
        {
            "points": points,
            "inner_radius": inner_radius,
            "outer_radius": outer_radius,
            "fill_color": fill_color,
        },
    )

    fill_col = _color_tuple(fill_color)

    # Pre-compute star vertex positions
    verts = []
    n = points * 2  # alternating outer/inner
    for i in range(n):
        angle = math.pi / 2.0 + (2.0 * math.pi * i) / n  # start at top
        r = outer_radius if i % 2 == 0 else inner_radius
        x = r * math.cos(angle)
        y = r * math.sin(angle)
        verts.append((x, y))

    # Build Python literal for vertices (z=0 for 2D)
    verts_str = ", ".join(f"({x:.6f}, {y:.6f}, 0.0)" for x, y in verts)
    edges_str = ", ".join(f"({i}, {(i + 1) % n})" for i in range(n))
    face_str = f"({', '.join(str(i) for i in range(n))})"

    lines = [
        f"# Star: {obj_name}  points={points}  inner_r={inner_radius}  outer_r={outer_radius}",
        "import bpy",
        "import bmesh",
        "mesh_data = bpy.data.meshes.new(name='StarMesh')",
        f"verts = [{verts_str}]",
        f"edges = [{edges_str}]",
        f"faces = [{face_str}]",
        "mesh_data.from_pydata(verts, [], faces)",
        "mesh_data.update()",
        f"star_obj = bpy.data.objects.new('{obj_name}', mesh_data)",
        "bpy.context.collection.objects.link(star_obj)",
        "# Apply fill material",
        "fill_mat = bpy.data.materials.new(name='StarFill')",
        "fill_mat.use_nodes = True",
        f"fill_mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = {fill_col}",
        "star_obj.data.materials.append(fill_mat)",
    ]
    return lines


def create_custom_path(
    session,
    bezier_points: List[Dict[str, Any]],
    fill_color=None,
    stroke_color=None,
    name: str = "CustomPath",
) -> List[str]:
    """Create a custom bezier path as a bpy Curve object.

    Args:
        session: Active Session object.
        bezier_points: List of dicts, each with keys:
            - 'co': [x, y, z] anchor point
            - 'handle_left': [x, y, z] left handle (optional)
            - 'handle_right': [x, y, z] right handle (optional)
            - 'handle_left_type': 'AUTO'|'VECTOR'|'FREE' (optional, default 'AUTO')
            - 'handle_right_type': 'AUTO'|'VECTOR'|'FREE' (optional, default 'AUTO')
        fill_color: RGBA tuple/list for fill material.
        stroke_color: RGBA tuple/list for stroke (bevel) material.
        name: Object name.

    Returns:
        List of bpy script lines.
    """
    if len(bezier_points) < 2:
        raise ValueError(f"At least 2 bezier_points required, got {len(bezier_points)}")

    project = _get_project(session)
    obj_name = _unique_shape_name(project, name)
    _register_shape(
        project,
        obj_name,
        "custom_path",
        {
            "point_count": len(bezier_points),
            "fill_color": fill_color,
            "stroke_color": stroke_color,
        },
    )

    fill_col = _color_tuple(fill_color)
    n = len(bezier_points)

    lines = [
        f"# CustomPath: {obj_name}  {n} bezier points",
        "import bpy",
        "curve_data = bpy.data.curves.new(name='CustomCurve', type='CURVE')",
        "curve_data.dimensions = '2D'",
        "curve_data.fill_mode = 'BOTH'",
        "spline = curve_data.splines.new('BEZIER')",
        f"spline.bezier_points.add({n - 1})",
    ]

    for i, bp in enumerate(bezier_points):
        co = bp.get("co", [0.0, 0.0, 0.0])
        hl = bp.get("handle_left", co)
        hr = bp.get("handle_right", co)
        hl_type = bp.get("handle_left_type", "AUTO")
        hr_type = bp.get("handle_right_type", "AUTO")
        lines += [
            f"spline.bezier_points[{i}].co = ({co[0]}, {co[1]}, {co[2]})",
            f"spline.bezier_points[{i}].handle_left = ({hl[0]}, {hl[1]}, {hl[2]})",
            f"spline.bezier_points[{i}].handle_right = ({hr[0]}, {hr[1]}, {hr[2]})",
            f"spline.bezier_points[{i}].handle_left_type = '{hl_type}'",
            f"spline.bezier_points[{i}].handle_right_type = '{hr_type}'",
        ]

    lines += [
        f"path_obj = bpy.data.objects.new('{obj_name}', curve_data)",
        "bpy.context.collection.objects.link(path_obj)",
        "fill_mat = bpy.data.materials.new(name='PathFill')",
        "fill_mat.use_nodes = True",
        f"fill_mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = {fill_col}",
        "path_obj.data.materials.append(fill_mat)",
    ]

    if stroke_color is not None:
        stroke_col = _color_tuple(stroke_color)
        lines += [
            "curve_data.bevel_depth = 0.02",
            "stroke_mat = bpy.data.materials.new(name='PathStroke')",
            "stroke_mat.use_nodes = True",
            f"stroke_mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = {stroke_col}",
            "path_obj.data.materials.append(stroke_mat)",
        ]

    return lines


# ── Animation ────────────────────────────────────────────────────────────────


def morph(
    session,
    shape_a: str,
    shape_b: str,
    duration: float,
    fps: int = 30,
    easing: str = "ease_in_out_cubic",
) -> List[str]:
    """Animate shape-key morph between two mesh objects.

    Blender shape key workflow:
    1. Select shape_b, join as shape to shape_a (adds a shape key basis + target).
    2. Animate the shape key value from 0 → 1 over *duration* seconds.

    Args:
        session: Active Session object.
        shape_a: Name of the base (source) object.
        shape_b: Name of the target object.
        duration: Animation duration in seconds.
        fps: Frames per second.
        easing: Easing function name.

    Returns:
        List of bpy script lines.
    """
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")

    ease_fn = get_easing(easing)
    total_frames = int(round(duration * fps))

    lines = [
        f"# Morph: '{shape_a}' → '{shape_b}'  ({duration}s, {easing})",
        "import bpy",
        f"obj_a = bpy.data.objects.get('{shape_a}')",
        f"obj_b = bpy.data.objects.get('{shape_b}')",
        "if obj_a and obj_b:",
        "    # Add shape key basis to obj_a",
        "    bpy.context.view_layer.objects.active = obj_a",
        "    bpy.ops.object.shape_key_add(from_mix=False)  # Basis",
        "    sk = obj_a.shape_key_add(name='Morph_Target', from_mix=False)",
        "    # Copy vertex positions from obj_b",
        "    for i, vert in enumerate(sk.data):",
        "        if i < len(obj_b.data.vertices):",
        "            vert.co = obj_b.data.vertices[i].co",
        "    # Animate shape key value",
        "    sk.value = 0.0",
    ]

    for frame_idx in range(total_frames + 1):
        t = frame_idx / total_frames if total_frames > 0 else 0.0
        alpha = ease_fn(t)
        frame_num = frame_idx + 1
        lines.append(f"    sk.value = {alpha:.6f}")
        lines.append(f"    sk.keyframe_insert(data_path='value', frame={frame_num})")

    return lines


def trim_path(
    session,
    shape_name: str,
    start_pct: float,
    end_pct: float,
    duration: float,
    fps: int = 30,
    easing: str = "ease_in_out_cubic",
) -> List[str]:
    """Animate curve bevel_factor (trim path / draw-on effect).

    Animates curve_data.bevel_factor_start and bevel_factor_end to
    produce a draw-on / trim-path effect on a Curve object.

    Args:
        session: Active Session object.
        shape_name: Name of the curve object.
        start_pct: Starting percentage of path to show (0.0–1.0).
        end_pct: Ending percentage of path to show (0.0–1.0).
        duration: Animation duration in seconds.
        fps: Frames per second.
        easing: Easing function name.

    Returns:
        List of bpy script lines.
    """
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")
    if not (0.0 <= start_pct <= 1.0):
        raise ValueError(f"start_pct must be in [0, 1], got {start_pct}")
    if not (0.0 <= end_pct <= 1.0):
        raise ValueError(f"end_pct must be in [0, 1], got {end_pct}")

    ease_fn = get_easing(easing)
    total_frames = int(round(duration * fps))

    lines = [
        f"# Trim path: '{shape_name}'  {start_pct:.2f}→{end_pct:.2f}  ({duration}s, {easing})",
        "import bpy",
        f"curve_obj = bpy.data.objects.get('{shape_name}')",
        "if curve_obj and curve_obj.type == 'CURVE':",
        "    curve_obj.data.bevel_factor_mapping_start = 'SPLINE'",
        "    curve_obj.data.bevel_factor_mapping_end = 'SPLINE'",
    ]

    for frame_idx in range(total_frames + 1):
        t = frame_idx / total_frames if total_frames > 0 else 0.0
        alpha = ease_fn(t)
        # bevel_factor_end goes from start_pct to end_pct
        factor_end = start_pct + (end_pct - start_pct) * alpha
        frame_num = frame_idx + 1
        lines.append(f"    curve_obj.data.bevel_factor_end = {factor_end:.6f}")
        lines.append(
            f"    curve_obj.data.keyframe_insert(data_path='bevel_factor_end', frame={frame_num})"
        )

    return lines


def offset_path(
    session,
    shape_name: str,
    amount: float,
    duration: float,
    fps: int = 30,
    easing: str = "ease_out_cubic",
) -> List[str]:
    """Animate solidify modifier thickness (offset/expand path outward).

    Adds a Solidify modifier to the object and animates its thickness
    from 0 → *amount* over *duration* seconds.

    Args:
        session: Active Session object.
        shape_name: Name of the target object.
        amount: Target solidify thickness in Blender units.
        duration: Animation duration in seconds.
        fps: Frames per second.
        easing: Easing function name.

    Returns:
        List of bpy script lines.
    """
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")

    ease_fn = get_easing(easing)
    total_frames = int(round(duration * fps))

    lines = [
        f"# Offset path: '{shape_name}'  amount={amount}  ({duration}s, {easing})",
        "import bpy",
        f"target_obj = bpy.data.objects.get('{shape_name}')",
        "if target_obj:",
        "    solidify = target_obj.modifiers.new(name='OffsetSolidify', type='SOLIDIFY')",
        "    solidify.thickness = 0.0",
    ]

    for frame_idx in range(total_frames + 1):
        t = frame_idx / total_frames if total_frames > 0 else 0.0
        alpha = ease_fn(t)
        thickness = amount * alpha
        frame_num = frame_idx + 1
        lines.append(f"    solidify.thickness = {thickness:.6f}")
        lines.append(
            f"    solidify.keyframe_insert(data_path='thickness', frame={frame_num})"
        )

    return lines


def repeater(
    session,
    shape_name: str,
    copies: int,
    offset: Optional[List[float]] = None,
    scale_step: float = 1.0,
    rotation_step: float = 0.0,
) -> List[str]:
    """Create copies of a shape using an Array modifier.

    Args:
        session: Active Session object.
        shape_name: Name of the source object.
        copies: Number of copies (Array count).
        offset: [x, y, z] constant offset between copies (default [1, 0, 0]).
        scale_step: Uniform scale multiplier per copy (applied via object transform).
        rotation_step: Z-rotation step in degrees per copy.

    Returns:
        List of bpy script lines.
    """
    if copies < 1:
        raise ValueError(f"copies must be at least 1, got {copies}")

    off = list(offset) if offset is not None else [1.0, 0.0, 0.0]
    if len(off) != 3:
        raise ValueError(f"offset must have 3 components, got {len(off)}")

    lines = [
        f"# Repeater: '{shape_name}'  copies={copies}  offset={off}  "
        f"scale_step={scale_step}  rotation_step={rotation_step}",
        "import bpy",
        f"src_obj = bpy.data.objects.get('{shape_name}')",
        "if src_obj:",
        "    arr = src_obj.modifiers.new(name='Repeater', type='ARRAY')",
        f"    arr.count = {copies}",
        "    arr.use_constant_offset = True",
        "    arr.use_relative_offset = False",
        f"    arr.constant_offset_displace = ({off[0]}, {off[1]}, {off[2]})",
    ]

    if scale_step != 1.0:
        lines += [
            f"    arr.use_object_offset = False  # scale_step is a uniform multiplier",
            "    # Note: per-copy scale variation requires curve modifier or driver setup",
            f"    src_obj.scale = ({scale_step}, {scale_step}, {scale_step})",
        ]

    if rotation_step != 0.0:
        lines += [
            "    import math",
            f"    arr_rotation_z = math.radians({rotation_step})",
            "    # Rotation step: add an Empty as object offset for progressive rotation",
            "    bpy.ops.object.empty_add(type='PLAIN_AXES')",
            "    rot_empty = bpy.context.active_object",
            f"    rot_empty.name = '{shape_name}_RepeatOffset'",
            f"    rot_empty.rotation_euler[2] = arr_rotation_z",
            "    arr.use_object_offset = True",
            "    arr.offset_object = rot_empty",
        ]

    return lines
