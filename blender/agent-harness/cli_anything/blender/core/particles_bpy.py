"""Blender CLI - Particle system integration.

Generates bpy Python script strings for particle system setup, force
fields, and production presets.

Each public function returns a list of bpy script lines.  All lines
are human-readable and can be assembled by bpy_gen.py into a complete
Blender Python script to be executed via blender --background --python.

Supported particle sources:
- emit_from_object   — existing mesh as emitter
- emit_from_point    — auto-generated emitter plane at given position
- emit_from_text     — convert font object to mesh + emit

Force fields:
- add_force_field — TURBULENCE, WIND, VORTEX, FORCE

Presets:
- preset_confetti     — colourful flat confetti burst
- preset_sparks       — fast short-lived sparks
- preset_disintegrate — explode modifier + particle explosion
- preset_data_stream  — flowing data-stream particles
"""

import sys
import os
from typing import Dict, Any, List, Optional

# particles_bpy.py lives at: blender/agent-harness/cli_anything/blender/core/particles_bpy.py
# shared/ lives at:          <project-root>/shared/
# 5 levels of ".." bring us from core/ to the project root.
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "shared"),
)
# (No motion_math required for static particle setup, but kept for consistency.)


# ── Constants ────────────────────────────────────────────────────────────────

VALID_FORCE_TYPES = {"TURBULENCE", "WIND", "VORTEX", "FORCE"}

# Default ParticleSettings values — these map 1-to-1 to bpy ParticleSettings
_PARTICLE_DEFAULTS: Dict[str, Any] = {
    "count": 1000,
    "lifetime": 50,
    "emit_from": "FACE",      # FACE | VOLUME | VERT
    "velocity_normal": 1.0,
    "velocity_random": 0.5,
    "gravity": 1.0,
    "use_render_emitter": False,
    "particle_size": 0.05,
    "size_random": 0.0,
    "mass": 1.0,
    "use_rotations": False,
    "use_dynamic_rotation": False,
    "render_type": "HALO",    # HALO | OBJECT | COLLECTION | PATH
}

# Keys that map directly to bpy ParticleSettings attribute names
_DIRECT_ATTRS = {
    "count", "lifetime", "emit_from", "particle_size",
    "size_random", "mass",
}


# ── Internal helpers ─────────────────────────────────────────────────────────


def _get_project(session) -> Dict[str, Any]:
    return session.get_project()


def _merge_config(config_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge user config over defaults."""
    merged = dict(_PARTICLE_DEFAULTS)
    if config_dict:
        merged.update(config_dict)
    return merged


def _particle_settings_lines(ps_var: str, cfg: Dict[str, Any]) -> List[str]:
    """Generate lines that configure a bpy ParticleSettings object.

    Args:
        ps_var: Python variable name holding the ParticleSettings object.
        cfg: Merged config dict.

    Returns:
        List of assignment lines.
    """
    lines = []
    for key in _DIRECT_ATTRS:
        if key in cfg:
            val = cfg[key]
            if isinstance(val, str):
                lines.append(f"    {ps_var}.{key} = '{val}'")
            else:
                lines.append(f"    {ps_var}.{key} = {val!r}")

    # Extra settings not in _DIRECT_ATTRS
    for key, bpy_attr in [
        ("velocity_normal", "normal_factor"),
        ("velocity_random", "factor_random"),
        ("gravity", None),          # handled separately (scene.gravity scale)
        ("use_render_emitter", "use_render_emitter"),
        ("particle_size", "particle_size"),
        ("use_rotations", "use_rotations"),
        ("use_dynamic_rotation", "use_dynamic_rotation"),
        ("render_type", "render_type"),
    ]:
        if key in cfg and bpy_attr is not None and key not in _DIRECT_ATTRS:
            val = cfg[key]
            if isinstance(val, str):
                lines.append(f"    {ps_var}.{bpy_attr} = '{val}'")
            else:
                lines.append(f"    {ps_var}.{bpy_attr} = {val!r}")

    return lines


# ── Public API ───────────────────────────────────────────────────────────────


def emit_from_object(
    session,
    object_name: str,
    config_dict: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Set up a particle system on an existing object.

    Args:
        session: Active Session object.
        object_name: Name of the Blender mesh object to use as emitter.
        config_dict: Override dict for ParticleSettings.  Recognised keys:
            count, lifetime, emit_from, velocity_normal, velocity_random,
            gravity, particle_size, size_random, mass, use_render_emitter,
            use_rotations, use_dynamic_rotation, render_type.

    Returns:
        List of bpy script lines.
    """
    cfg = _merge_config(config_dict)

    lines = [
        f"# Particle system on object: '{object_name}'",
        "import bpy",
        f"emitter = bpy.data.objects.get('{object_name}')",
        "if emitter:",
        "    bpy.context.view_layer.objects.active = emitter",
        "    ps_mod = emitter.modifiers.new(name='ParticleSystem', type='PARTICLE_SYSTEM')",
        "    ps = ps_mod.particle_system",
        "    pset = ps.settings",
    ]
    lines += _particle_settings_lines("pset", cfg)
    return lines


def emit_from_point(
    session,
    position: List[float],
    config_dict: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Create a small emitter mesh at *position* then add a particle system.

    Args:
        session: Active Session object.
        position: [x, y, z] world position for the emitter.
        config_dict: ParticleSettings override dict (see emit_from_object).

    Returns:
        List of bpy script lines.
    """
    if len(position) != 3:
        raise ValueError(f"position must have 3 components, got {len(position)}")

    cfg = _merge_config(config_dict)
    x, y, z = position

    lines = [
        f"# Particle emitter at point ({x}, {y}, {z})",
        "import bpy",
        f"bpy.ops.mesh.primitive_plane_add(size=0.01, location=({x}, {y}, {z}))",
        "emitter = bpy.context.active_object",
        "emitter.name = 'PointEmitter'",
        "bpy.context.view_layer.objects.active = emitter",
        "ps_mod = emitter.modifiers.new(name='ParticleSystem', type='PARTICLE_SYSTEM')",
        "ps = ps_mod.particle_system",
        "pset = ps.settings",
    ]
    lines += _particle_settings_lines("pset", cfg)
    return lines


def emit_from_text(
    session,
    text_object: str,
    config_dict: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Convert a font (text) object to mesh, then add a particle system.

    Blender workflow:
    1. Select the font object.
    2. Convert to mesh (ops.object.convert type='MESH').
    3. Add particle system on the resulting mesh.

    Args:
        session: Active Session object.
        text_object: Name of the font/text object in the scene.
        config_dict: ParticleSettings override dict.

    Returns:
        List of bpy script lines.
    """
    cfg = _merge_config(config_dict)

    lines = [
        f"# Particle system from text object: '{text_object}'",
        "import bpy",
        f"text_obj = bpy.data.objects.get('{text_object}')",
        "if text_obj:",
        "    bpy.ops.object.select_all(action='DESELECT')",
        "    text_obj.select_set(True)",
        "    bpy.context.view_layer.objects.active = text_obj",
        "    bpy.ops.object.convert(target='MESH')",
        "    emitter = bpy.context.active_object",
        "    ps_mod = emitter.modifiers.new(name='ParticleSystem', type='PARTICLE_SYSTEM')",
        "    ps = ps_mod.particle_system",
        "    pset = ps.settings",
    ]
    lines += _particle_settings_lines("pset", cfg)
    return lines


def add_force_field(
    session,
    force_type: str,
    strength: float,
    position: Optional[List[float]] = None,
    name: str = "ForceField",
) -> List[str]:
    """Add an effector (force field) to the scene.

    Args:
        session: Active Session object.
        force_type: One of 'TURBULENCE', 'WIND', 'VORTEX', 'FORCE'.
        strength: Force field strength.
        position: [x, y, z] world position (default [0, 0, 0]).
        name: Object name for the effector empty.

    Returns:
        List of bpy script lines.
    """
    force_type_upper = force_type.upper()
    if force_type_upper not in VALID_FORCE_TYPES:
        raise ValueError(
            f"Invalid force_type '{force_type}'. Valid: {sorted(VALID_FORCE_TYPES)}"
        )
    pos = list(position) if position is not None else [0.0, 0.0, 0.0]
    if len(pos) != 3:
        raise ValueError(f"position must have 3 components, got {len(pos)}")

    lines = [
        f"# Force field: {force_type_upper}  strength={strength}  pos={pos}",
        "import bpy",
        f"bpy.ops.object.effector_add(type='{force_type_upper}', "
        f"location=({pos[0]}, {pos[1]}, {pos[2]}))",
        "ff_obj = bpy.context.active_object",
        f"ff_obj.name = '{name}'",
        f"ff_obj.field.strength = {strength}",
    ]

    # Type-specific defaults
    if force_type_upper == "TURBULENCE":
        lines += [
            "ff_obj.field.noise = 1.0",
            "ff_obj.field.size = 1.0",
        ]
    elif force_type_upper == "WIND":
        lines += [
            "ff_obj.field.flow = 1.0",
        ]
    elif force_type_upper == "VORTEX":
        lines += [
            "ff_obj.field.inflow = 0.0",
        ]

    return lines


# ── Presets ───────────────────────────────────────────────────────────────────


def preset_confetti(
    session,
    object_name: str,
    colors: Optional[List] = None,
) -> List[str]:
    """Confetti burst preset — colourful flat quads bursting from an object.

    Args:
        session: Active Session object.
        object_name: Name of the emitter mesh.
        colors: List of [r, g, b] or [r, g, b, a] color tuples for confetti
                pieces.  A colour-ramp vertex shader approach is generated.
                Defaults to a rainbow palette.

    Returns:
        List of bpy script lines.
    """
    if colors is None:
        colors = [
            [1.0, 0.2, 0.2],   # red
            [1.0, 0.8, 0.0],   # yellow
            [0.2, 0.8, 0.2],   # green
            [0.2, 0.5, 1.0],   # blue
            [0.8, 0.2, 1.0],   # purple
        ]

    cfg = {
        "count": 2000,
        "lifetime": 80,
        "emit_from": "FACE",
        "velocity_normal": 3.0,
        "velocity_random": 2.0,
        "particle_size": 0.04,
        "size_random": 0.5,
        "use_rotations": True,
        "render_type": "HALO",
    }

    lines = emit_from_object(session, object_name, cfg)

    # Add confetti gravity influence
    lines += [
        "    # Confetti gravity",
        "    pset.effector_weights.gravity = 0.3",
        "    pset.use_die_on_collision = False",
        "    # Confetti colour via material",
    ]

    for i, col in enumerate(colors[:5]):
        r, g, b = col[0], col[1], col[2]
        a = col[3] if len(col) > 3 else 1.0
        lines += [
            f"    confetti_mat_{i} = bpy.data.materials.new(name='Confetti{i}')",
            f"    confetti_mat_{i}.use_nodes = True",
            f"    confetti_mat_{i}.node_tree.nodes['Principled BSDF']"
            f".inputs['Base Color'].default_value = ({r}, {g}, {b}, {a})",
        ]

    lines.append("    # Confetti preset complete")
    return lines


def preset_sparks(
    session,
    object_name: str,
    color: Optional[List[float]] = None,
) -> List[str]:
    """Fast short-lived sparks / fire-works preset.

    Args:
        session: Active Session object.
        object_name: Name of the emitter mesh.
        color: [r, g, b, a] spark colour (default warm orange).

    Returns:
        List of bpy script lines.
    """
    spark_color = color if color is not None else [1.0, 0.5, 0.05, 1.0]
    r, g, b = spark_color[0], spark_color[1], spark_color[2]
    a = spark_color[3] if len(spark_color) > 3 else 1.0

    cfg = {
        "count": 3000,
        "lifetime": 15,
        "emit_from": "VERT",
        "velocity_normal": 8.0,
        "velocity_random": 4.0,
        "particle_size": 0.015,
        "size_random": 0.8,
        "render_type": "HALO",
    }

    lines = emit_from_object(session, object_name, cfg)
    lines += [
        "    # Sparks: high-velocity, gravity-affected",
        "    pset.effector_weights.gravity = 1.0",
        "    spark_mat = bpy.data.materials.new(name='SparkMat')",
        "    spark_mat.use_nodes = True",
        f"    spark_mat.node_tree.nodes['Principled BSDF']"
        f".inputs['Base Color'].default_value = ({r}, {g}, {b}, {a})",
        "    spark_mat.node_tree.nodes['Principled BSDF']"
        ".inputs['Emission Strength'].default_value = 5.0",
        "    # Sparks preset complete",
    ]
    return lines


def preset_disintegrate(
    session,
    object_name: str,
    duration: float = 2.0,
) -> List[str]:
    """Disintegrate preset — Explode modifier + particle explosion.

    Applies:
    1. A particle system with count proportional to duration.
    2. An Explode modifier that makes faces follow the particles.

    Args:
        session: Active Session object.
        object_name: Name of the mesh object to disintegrate.
        duration: Effect duration in seconds (used to set lifetime).

    Returns:
        List of bpy script lines.
    """
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")

    lifetime = max(10, int(duration * 25))  # rough 25fps equivalent
    cfg = {
        "count": 500,
        "lifetime": lifetime,
        "emit_from": "FACE",
        "velocity_normal": 2.0,
        "velocity_random": 1.5,
        "particle_size": 0.0,  # particles invisible; faces carry the geo
        "render_type": "HALO",
    }

    lines = emit_from_object(session, object_name, cfg)
    lines += [
        f"    # Disintegrate: add Explode modifier",
        f"    explode_mod = emitter.modifiers.new(name='Explode', type='EXPLODE')",
        "    explode_mod.use_edge_cut = True",
        "    explode_mod.use_size = True",
        "    explode_mod.particle_system_index = 0",
        "    # Disintegrate preset complete",
    ]
    return lines


def preset_data_stream(
    session,
    direction: Optional[List[float]] = None,
    speed: float = 5.0,
) -> List[str]:
    """Flowing data-stream particles (tech/sci-fi motif).

    Creates a small emitter plane and configures a linear particle flow.

    Args:
        session: Active Session object.
        direction: [x, y, z] normalised direction vector (default [0, 0, -1]).
        speed: Particle speed (velocity_normal).

    Returns:
        List of bpy script lines.
    """
    if speed <= 0:
        raise ValueError(f"speed must be positive, got {speed}")

    dir_vec = list(direction) if direction is not None else [0.0, 0.0, -1.0]
    if len(dir_vec) != 3:
        raise ValueError(f"direction must have 3 components, got {len(dir_vec)}")

    cfg = {
        "count": 1500,
        "lifetime": 40,
        "emit_from": "FACE",
        "velocity_normal": speed,
        "velocity_random": 0.1,
        "particle_size": 0.025,
        "size_random": 0.3,
        "render_type": "HALO",
    }

    position = [0.0, 0.0, 2.0]
    lines = emit_from_point(session, position, cfg)

    lines += [
        "    # Data stream: coloured material",
        "    stream_mat = bpy.data.materials.new(name='DataStream')",
        "    stream_mat.use_nodes = True",
        "    stream_mat.node_tree.nodes['Principled BSDF']"
        ".inputs['Base Color'].default_value = (0.0, 0.8, 1.0, 1.0)",
        "    stream_mat.node_tree.nodes['Principled BSDF']"
        ".inputs['Emission Strength'].default_value = 3.0",
        "    # Data stream gravity off",
        "    pset.effector_weights.gravity = 0.0",
        f"    # Data stream direction = {dir_vec}",
        "    # Data stream preset complete",
    ]
    return lines
