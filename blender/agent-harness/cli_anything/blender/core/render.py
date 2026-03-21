"""Blender CLI - Render settings and export module.

Handles render configuration, preset management, and bpy script generation
for actual Blender rendering.
"""

import os
import json
from typing import Dict, Any, Optional, List
from datetime import datetime


# Render presets
RENDER_PRESETS = {
    "cycles_default": {
        "engine": "CYCLES",
        "samples": 128,
        "use_denoising": True,
        "resolution_percentage": 100,
    },
    "cycles_high": {
        "engine": "CYCLES",
        "samples": 512,
        "use_denoising": True,
        "resolution_percentage": 100,
    },
    "cycles_preview": {
        "engine": "CYCLES",
        "samples": 32,
        "use_denoising": True,
        "resolution_percentage": 50,
    },
    "eevee_default": {
        "engine": "EEVEE",
        "samples": 64,
        "use_denoising": False,
        "resolution_percentage": 100,
    },
    "eevee_high": {
        "engine": "EEVEE",
        "samples": 256,
        "use_denoising": False,
        "resolution_percentage": 100,
    },
    "eevee_preview": {
        "engine": "EEVEE",
        "samples": 16,
        "use_denoising": False,
        "resolution_percentage": 50,
    },
    "workbench": {
        "engine": "WORKBENCH",
        "samples": 1,
        "use_denoising": False,
        "resolution_percentage": 100,
    },
}

# Valid render settings
VALID_ENGINES = ["CYCLES", "EEVEE", "WORKBENCH"]
VALID_OUTPUT_FORMATS = ["PNG", "JPEG", "BMP", "TIFF", "OPEN_EXR", "HDR", "FFMPEG"]


def set_render_settings(
    project: Dict[str, Any],
    engine: Optional[str] = None,
    resolution_x: Optional[int] = None,
    resolution_y: Optional[int] = None,
    resolution_percentage: Optional[int] = None,
    samples: Optional[int] = None,
    use_denoising: Optional[bool] = None,
    film_transparent: Optional[bool] = None,
    output_format: Optional[str] = None,
    output_path: Optional[str] = None,
    preset: Optional[str] = None,
) -> Dict[str, Any]:
    """Configure render settings.

    Args:
        project: The scene dict
        engine: Render engine (CYCLES, EEVEE, WORKBENCH)
        resolution_x: Horizontal resolution in pixels
        resolution_y: Vertical resolution in pixels
        resolution_percentage: Resolution scale percentage (1-100)
        samples: Number of render samples
        use_denoising: Enable denoising
        film_transparent: Transparent film background
        output_format: Output format (PNG, JPEG, etc.)
        output_path: Output file path
        preset: Apply a render preset

    Returns:
        Dict with updated render settings
    """
    render = project.get("render", {})

    # Apply preset first, then individual overrides
    if preset:
        if preset not in RENDER_PRESETS:
            raise ValueError(
                f"Unknown render preset: {preset}. Available: {list(RENDER_PRESETS.keys())}"
            )
        for k, v in RENDER_PRESETS[preset].items():
            render[k] = v

    if engine is not None:
        if engine not in VALID_ENGINES:
            raise ValueError(f"Invalid engine: {engine}. Valid: {VALID_ENGINES}")
        render["engine"] = engine

    if resolution_x is not None:
        if resolution_x < 1:
            raise ValueError(f"Resolution X must be positive: {resolution_x}")
        render["resolution_x"] = resolution_x

    if resolution_y is not None:
        if resolution_y < 1:
            raise ValueError(f"Resolution Y must be positive: {resolution_y}")
        render["resolution_y"] = resolution_y

    if resolution_percentage is not None:
        if not 1 <= resolution_percentage <= 100:
            raise ValueError(f"Resolution percentage must be 1-100: {resolution_percentage}")
        render["resolution_percentage"] = resolution_percentage

    if samples is not None:
        if samples < 1:
            raise ValueError(f"Samples must be positive: {samples}")
        render["samples"] = samples

    if use_denoising is not None:
        render["use_denoising"] = bool(use_denoising)

    if film_transparent is not None:
        render["film_transparent"] = bool(film_transparent)

    if output_format is not None:
        if output_format not in VALID_OUTPUT_FORMATS:
            raise ValueError(f"Invalid format: {output_format}. Valid: {VALID_OUTPUT_FORMATS}")
        render["output_format"] = output_format

    if output_path is not None:
        render["output_path"] = output_path

    project["render"] = render
    return render


def get_render_settings(project: Dict[str, Any]) -> Dict[str, Any]:
    """Get current render settings."""
    render = project.get("render", {})
    res_x = render.get("resolution_x", 1920)
    res_y = render.get("resolution_y", 1080)
    pct = render.get("resolution_percentage", 100)
    return {
        "engine": render.get("engine", "CYCLES"),
        "resolution": f"{res_x}x{res_y}",
        "effective_resolution": f"{res_x * pct // 100}x{res_y * pct // 100}",
        "resolution_percentage": pct,
        "samples": render.get("samples", 128),
        "use_denoising": render.get("use_denoising", True),
        "film_transparent": render.get("film_transparent", False),
        "output_format": render.get("output_format", "PNG"),
        "output_path": render.get("output_path", "./render/"),
    }


def list_render_presets() -> List[Dict[str, Any]]:
    """List available render presets."""
    result = []
    for name, p in RENDER_PRESETS.items():
        result.append({
            "name": name,
            "engine": p["engine"],
            "samples": p["samples"],
            "use_denoising": p["use_denoising"],
            "resolution_percentage": p["resolution_percentage"],
        })
    return result


def render_scene(
    project: Dict[str, Any],
    output_path: str,
    frame: Optional[int] = None,
    animation: bool = False,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Render the scene by generating a bpy script.

    Since we cannot call Blender directly in all environments, this generates
    a Python script that can be run with `blender --background --python script.py`.

    Args:
        project: The scene dict
        output_path: Output file or directory path
        frame: Specific frame to render (None = current frame)
        animation: If True, render the full animation range
        overwrite: Allow overwriting existing files

    Returns:
        Dict with render info and script path
    """
    if os.path.exists(output_path) and not overwrite and not animation:
        raise FileExistsError(f"Output file exists: {output_path}. Use --overwrite.")

    render_settings = project.get("render", {})
    scene_settings = project.get("scene", {})

    # Determine output directory for the script
    script_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(script_dir, exist_ok=True)

    script_path = os.path.join(script_dir, "_render_script.py")
    script_content = generate_bpy_script(project, output_path, frame=frame, animation=animation)

    with open(script_path, "w") as f:
        f.write(script_content)

    result = {
        "script_path": os.path.abspath(script_path),
        "output_path": os.path.abspath(output_path),
        "engine": render_settings.get("engine", "CYCLES"),
        "resolution": f"{render_settings.get('resolution_x', 1920)}x{render_settings.get('resolution_y', 1080)}",
        "samples": render_settings.get("samples", 128),
        "format": render_settings.get("output_format", "PNG"),
        "animation": animation,
        "command": f"blender --background --python {os.path.abspath(script_path)}",
    }

    if animation:
        result["frame_range"] = f"{scene_settings.get('frame_start', 1)}-{scene_settings.get('frame_end', 250)}"
    else:
        result["frame"] = frame or scene_settings.get("frame_current", 1)

    return result


def generate_bpy_script(
    project: Dict[str, Any],
    output_path: str,
    frame: Optional[int] = None,
    animation: bool = False,
) -> str:
    """Generate a Blender Python (bpy) script from the scene JSON.

    This creates a complete bpy script that reconstructs the entire scene
    and renders it.

    Args:
        project: The scene dict
        output_path: Render output path
        frame: Specific frame to render
        animation: Render full animation

    Returns:
        The bpy script as a string
    """
    from cli_anything.blender.utils.bpy_gen import generate_full_script
    return generate_full_script(project, output_path, frame=frame, animation=animation)


# ── Professional render quality settings ────────────────────────────────────


def set_motion_blur(
    session,
    enable: bool = True,
    shutter_speed: float = 0.5,
    samples: int = 16,
) -> List[str]:
    """Enable or disable motion blur with configurable shutter speed.

    Stores the setting in the session project JSON and returns bpy script lines
    that apply the setting to the scene's render properties.

    Args:
        session:       Active Session object.
        enable:        True to enable motion blur, False to disable.
        shutter_speed: Camera shutter speed in frames (0.0–1.0).
        samples:       Number of motion blur samples (Cycles only).

    Returns:
        List of bpy script lines.
    """
    if shutter_speed < 0.0 or shutter_speed > 1.0:
        raise ValueError(f"shutter_speed must be between 0.0 and 1.0, got {shutter_speed}")
    if samples < 1:
        raise ValueError(f"samples must be positive, got {samples}")

    project = session.get_project()
    project.setdefault("render", {})
    project["render"]["motion_blur"] = {
        "enable": enable,
        "shutter_speed": shutter_speed,
        "samples": samples,
    }

    lines = [
        f"# Motion blur: enable={enable} shutter={shutter_speed} samples={samples}",
        f"bpy.context.scene.render.use_motion_blur = {enable}",
        f"bpy.context.scene.render.motion_blur_shutter = {shutter_speed}",
        f"bpy.context.scene.cycles.motion_blur_position = 'CENTER'",
    ]
    if enable:
        lines.append(f"bpy.context.scene.cycles.motion_blur_shutter = {shutter_speed}")
    return lines


def set_ambient_occlusion(
    session,
    enable: bool = True,
    distance: float = 1.0,
    factor: float = 1.0,
) -> List[str]:
    """Enable or disable Ambient Occlusion (EEVEE).

    Args:
        session:  Active Session object.
        enable:   True to enable AO, False to disable.
        distance: AO distance in Blender units.
        factor:   AO factor/intensity (0–1).

    Returns:
        List of bpy script lines.
    """
    if distance <= 0:
        raise ValueError(f"distance must be positive, got {distance}")
    if factor < 0:
        raise ValueError(f"factor must be non-negative, got {factor}")

    project = session.get_project()
    project.setdefault("render", {})
    project["render"]["ambient_occlusion"] = {
        "enable": enable,
        "distance": distance,
        "factor": factor,
    }

    return [
        f"# Ambient occlusion: enable={enable} distance={distance} factor={factor}",
        f"bpy.context.scene.eevee.use_gtao = {enable}",
        f"bpy.context.scene.eevee.gtao_distance = {distance}",
        f"bpy.context.scene.eevee.gtao_factor = {factor}",
    ]


def set_hdri_lighting(
    session,
    hdri_path: str,
    rotation: float = 0.0,
    strength: float = 1.0,
) -> List[str]:
    """Set up HDRI environment lighting using a world texture node tree.

    Creates a World shader node tree with an Environment Texture node,
    a Background node, and a Mapping node for rotation control.

    Args:
        session:   Active Session object.
        hdri_path: File path to the .hdr or .exr HDRI image.
        rotation:  Horizontal rotation of the HDRI in degrees.
        strength:  Light strength / intensity multiplier.

    Returns:
        List of bpy script lines.
    """
    if strength < 0:
        raise ValueError(f"strength must be non-negative, got {strength}")

    project = session.get_project()
    project.setdefault("render", {})
    project["render"]["hdri"] = {
        "path": hdri_path,
        "rotation": rotation,
        "strength": strength,
    }

    rot_rad = rotation * 3.141592653589793 / 180.0

    return [
        f"# HDRI lighting: {hdri_path!r} rot={rotation}deg strength={strength}",
        "world = bpy.context.scene.world",
        "world.use_nodes = True",
        "world_nodes = world.node_tree.nodes",
        "world_links = world.node_tree.links",
        "world_nodes.clear()",
        "env_node = world_nodes.new('ShaderNodeTexEnvironment')",
        f"env_node.image = bpy.data.images.load({hdri_path!r})",
        "bg_node = world_nodes.new('ShaderNodeBackground')",
        f"bg_node.inputs['Strength'].default_value = {strength}",
        "map_node = world_nodes.new('ShaderNodeMapping')",
        f"map_node.inputs['Rotation'].default_value = (0, 0, {rot_rad:.6f})",
        "coord_node = world_nodes.new('ShaderNodeTexCoord')",
        "out_node = world_nodes.new('ShaderNodeOutputWorld')",
        "world_links.new(coord_node.outputs['Generated'], map_node.inputs['Vector'])",
        "world_links.new(map_node.outputs['Vector'], env_node.inputs['Vector'])",
        "world_links.new(env_node.outputs['Color'], bg_node.inputs['Color'])",
        "world_links.new(bg_node.outputs['Background'], out_node.inputs['Surface'])",
    ]


def set_transparent_background(
    session,
    enable: bool = True,
) -> List[str]:
    """Enable or disable transparent (alpha) film background.

    When enabled, the render output will have a transparent background
    (useful for compositing).

    Args:
        session: Active Session object.
        enable:  True to make the background transparent.

    Returns:
        List of bpy script lines.
    """
    project = session.get_project()
    project.setdefault("render", {})
    project["render"]["film_transparent"] = enable

    return [
        f"# Transparent background: {enable}",
        f"bpy.context.scene.render.film_transparent = {enable}",
    ]


def set_film_exposure(
    session,
    value: float = 0.0,
) -> List[str]:
    """Set the film exposure (EV compensation).

    Adjusts the Cycles film exposure setting which maps to overall render
    brightness.  Value is in EV units: 0.0 = no change, +1.0 = one stop brighter.

    Args:
        session: Active Session object.
        value:   Exposure value in EV units.

    Returns:
        List of bpy script lines.
    """
    project = session.get_project()
    project.setdefault("render", {})
    project["render"]["film_exposure"] = value

    return [
        f"# Film exposure: {value} EV",
        f"bpy.context.scene.cycles.film_exposure = {value}",
    ]


def set_color_management(
    session,
    view_transform: str = "Filmic",
    look: str = "None",
) -> List[str]:
    """Configure scene color management (ACES/Filmic/sRGB etc.).

    Controls the OpenColorIO-based color management pipeline.

    Args:
        session:        Active Session object.
        view_transform: Display transform name, e.g. 'Filmic', 'Standard', 'Raw'.
        look:           OCIO look, e.g. 'None', 'Filmic - High Contrast'.

    Returns:
        List of bpy script lines.
    """
    project = session.get_project()
    project.setdefault("render", {})
    project["render"]["color_management"] = {
        "view_transform": view_transform,
        "look": look,
    }

    return [
        f"# Color management: view_transform={view_transform!r} look={look!r}",
        "cm = bpy.context.scene.view_settings",
        f"cm.view_transform = {view_transform!r}",
        f"cm.look = {look!r}",
    ]


def set_denoising(
    session,
    enable: bool = True,
) -> List[str]:
    """Enable or disable the render denoiser.

    For Cycles: uses the built-in AI denoiser (OptiX/OpenImageDenoise).
    For EEVEE: no-op (EEVEE has no denoiser).

    Args:
        session: Active Session object.
        enable:  True to enable denoising.

    Returns:
        List of bpy script lines.
    """
    project = session.get_project()
    project.setdefault("render", {})
    project["render"]["use_denoising"] = enable

    return [
        f"# Denoising: {enable}",
        f"bpy.context.scene.cycles.use_denoising = {enable}",
        f"bpy.context.scene.render.use_sequencer = True",
    ]
