#!/usr/bin/env python3
"""Blender CLI — A stateful command-line interface for 3D scene editing.

This CLI provides full 3D scene management capabilities using a JSON
scene description format, with bpy script generation for actual rendering.

Usage:
    # One-shot commands
    python3 -m cli.blender_cli scene new --name "MyScene"
    python3 -m cli.blender_cli object add cube --name "MyCube"
    python3 -m cli.blender_cli material create --name "Red" --color 1,0,0,1

    # Interactive REPL
    python3 -m cli.blender_cli repl
"""

import sys
import os
import json
import click
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli_anything.blender.core.session import Session
from cli_anything.blender.core import scene as scene_mod
from cli_anything.blender.core import objects as obj_mod
from cli_anything.blender.core import materials as mat_mod
from cli_anything.blender.core import modifiers as mod_mod
from cli_anything.blender.core import lighting as light_mod
from cli_anything.blender.core import animation as anim_mod
from cli_anything.blender.core import render as render_mod
from cli_anything.blender.core import camera as camera_mod
from cli_anything.blender.core import shape_layers as shape_mod
from cli_anything.blender.core import particles_bpy as particles_mod
from cli_anything.blender.core import compositor as compositor_mod

# Global session state
_session: Optional[Session] = None
_json_output = False
_repl_mode = False


def get_session() -> Session:
    global _session
    if _session is None:
        _session = Session()
    return _session


def output(data, message: str = ""):
    if _json_output:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        if message:
            click.echo(message)
        if isinstance(data, dict):
            _print_dict(data)
        elif isinstance(data, list):
            _print_list(data)
        else:
            click.echo(str(data))


def _print_dict(d: dict, indent: int = 0):
    prefix = "  " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            click.echo(f"{prefix}{k}:")
            _print_dict(v, indent + 1)
        elif isinstance(v, list):
            click.echo(f"{prefix}{k}:")
            _print_list(v, indent + 1)
        else:
            click.echo(f"{prefix}{k}: {v}")


def _print_list(items: list, indent: int = 0):
    prefix = "  " * indent
    for i, item in enumerate(items):
        if isinstance(item, dict):
            click.echo(f"{prefix}[{i}]")
            _print_dict(item, indent + 1)
        else:
            click.echo(f"{prefix}- {item}")


def handle_error(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError as e:
            if _json_output:
                click.echo(json.dumps({"error": str(e), "type": "file_not_found"}))
            else:
                click.echo(f"Error: {e}", err=True)
            if not _repl_mode:
                sys.exit(1)
        except (ValueError, IndexError, RuntimeError) as e:
            if _json_output:
                click.echo(json.dumps({"error": str(e), "type": type(e).__name__}))
            else:
                click.echo(f"Error: {e}", err=True)
            if not _repl_mode:
                sys.exit(1)
        except FileExistsError as e:
            if _json_output:
                click.echo(json.dumps({"error": str(e), "type": "file_exists"}))
            else:
                click.echo(f"Error: {e}", err=True)
            if not _repl_mode:
                sys.exit(1)
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


# ── Main CLI Group ──────────────────────────────────────────────
@click.group(invoke_without_command=True)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
@click.option("--project", "project_path", type=str, default=None,
              help="Path to .blend-cli.json project file")
@click.pass_context
def cli(ctx, use_json, project_path):
    """Blender CLI — Stateful 3D scene editing from the command line.

    Run without a subcommand to enter interactive REPL mode.
    """
    global _json_output
    _json_output = use_json

    if project_path:
        sess = get_session()
        if not sess.has_project():
            proj = scene_mod.open_scene(project_path)
            sess.set_project(proj, project_path)

    if ctx.invoked_subcommand is None:
        ctx.invoke(repl, project_path=None)


# ── Scene Commands ──────────────────────────────────────────────
@cli.group()
def scene():
    """Scene management commands."""
    pass


@scene.command("new")
@click.option("--name", "-n", default="untitled", help="Scene name")
@click.option("--profile", "-p", type=str, default=None, help="Scene profile")
@click.option("--resolution-x", "-rx", type=int, default=1920, help="Horizontal resolution")
@click.option("--resolution-y", "-ry", type=int, default=1080, help="Vertical resolution")
@click.option("--engine", type=click.Choice(["CYCLES", "EEVEE", "WORKBENCH"]), default="CYCLES")
@click.option("--samples", type=int, default=128, help="Render samples")
@click.option("--fps", type=int, default=24, help="Frames per second")
@click.option("--output", "-o", type=str, default=None, help="Save path")
@handle_error
def scene_new(name, profile, resolution_x, resolution_y, engine, samples, fps, output):
    """Create a new scene."""
    proj = scene_mod.create_scene(
        name=name, profile=profile, resolution_x=resolution_x,
        resolution_y=resolution_y, engine=engine, samples=samples, fps=fps,
    )
    sess = get_session()
    sess.set_project(proj, output)
    if output:
        scene_mod.save_scene(proj, output)
    output_data = scene_mod.get_scene_info(proj)
    globals()["output"](output_data, f"Created scene: {name}")


@scene.command("open")
@click.argument("path")
@handle_error
def scene_open(path):
    """Open an existing scene."""
    proj = scene_mod.open_scene(path)
    sess = get_session()
    sess.set_project(proj, path)
    info = scene_mod.get_scene_info(proj)
    output(info, f"Opened: {path}")


@scene.command("save")
@click.argument("path", required=False)
@handle_error
def scene_save(path):
    """Save the current scene."""
    sess = get_session()
    saved = sess.save_session(path)
    output({"saved": saved}, f"Saved to: {saved}")


@scene.command("info")
@handle_error
def scene_info():
    """Show scene information."""
    sess = get_session()
    info = scene_mod.get_scene_info(sess.get_project())
    output(info)


@scene.command("profiles")
@handle_error
def scene_profiles():
    """List available scene profiles."""
    profiles = scene_mod.list_profiles()
    output(profiles, "Available profiles:")


@scene.command("json")
@handle_error
def scene_json():
    """Print raw scene JSON."""
    sess = get_session()
    click.echo(json.dumps(sess.get_project(), indent=2, default=str))


# ── Object Commands ─────────────────────────────────────────────
@cli.group("object")
def object_group():
    """3D object management commands."""
    pass


@object_group.command("add")
@click.argument("mesh_type", type=click.Choice(
    ["cube", "sphere", "cylinder", "cone", "plane", "torus", "monkey", "empty"]))
@click.option("--name", "-n", default=None, help="Object name")
@click.option("--location", "-l", default=None, help="Location x,y,z")
@click.option("--rotation", "-r", default=None, help="Rotation x,y,z (degrees)")
@click.option("--scale", "-s", default=None, help="Scale x,y,z")
@click.option("--param", "-p", multiple=True, help="Mesh parameter: key=value")
@click.option("--collection", "-c", default=None, help="Target collection")
@handle_error
def object_add(mesh_type, name, location, rotation, scale, param, collection):
    """Add a 3D primitive object."""
    loc = [float(x) for x in location.split(",")] if location else None
    rot = [float(x) for x in rotation.split(",")] if rotation else None
    scl = [float(x) for x in scale.split(",")] if scale else None

    params = {}
    for p in param:
        if "=" not in p:
            raise ValueError(f"Invalid param format: '{p}'. Use key=value.")
        k, v = p.split("=", 1)
        try:
            v = float(v) if "." in v else int(v)
        except ValueError:
            pass
        params[k] = v

    sess = get_session()
    sess.snapshot(f"Add object: {mesh_type}")
    proj = sess.get_project()
    obj = obj_mod.add_object(
        proj, mesh_type=mesh_type, name=name, location=loc,
        rotation=rot, scale=scl, mesh_params=params if params else None,
        collection=collection,
    )
    output(obj, f"Added {mesh_type}: {obj['name']}")


@object_group.command("add-text")
@click.argument("body")
@click.option("--name", "-n", default=None, help="Object name")
@click.option("--location", "-l", default=None, help="Location x,y,z")
@click.option("--size", type=float, default=1.0, help="Font size")
@click.option("--extrude", type=float, default=0.0, help="Extrusion depth")
@click.option("--align", type=click.Choice(["LEFT", "CENTER", "RIGHT"]), default="CENTER",
              help="Horizontal alignment")
@handle_error
def object_add_text(body, name, location, size, extrude, align):
    """Add a text object to the scene."""
    loc = [float(x) for x in location.split(",")] if location else None

    sess = get_session()
    sess.snapshot(f"Add text object: {body}")
    proj = sess.get_project()
    obj = obj_mod.add_text_object(
        proj, body=body, name=name, location=loc,
        font_size=size, extrude=extrude, align_x=align,
    )
    output(obj, f"Added text: {obj['name']}")


@object_group.command("remove")
@click.argument("index", type=int)
@handle_error
def object_remove(index):
    """Remove an object by index."""
    sess = get_session()
    sess.snapshot(f"Remove object {index}")
    removed = obj_mod.remove_object(sess.get_project(), index)
    output(removed, f"Removed object {index}: {removed.get('name', '')}")


@object_group.command("duplicate")
@click.argument("index", type=int)
@handle_error
def object_duplicate(index):
    """Duplicate an object."""
    sess = get_session()
    sess.snapshot(f"Duplicate object {index}")
    dup = obj_mod.duplicate_object(sess.get_project(), index)
    output(dup, f"Duplicated object {index}")


@object_group.command("transform")
@click.argument("index", type=int)
@click.option("--translate", "-t", default=None, help="Translate dx,dy,dz")
@click.option("--rotate", "-r", default=None, help="Rotate rx,ry,rz (degrees)")
@click.option("--scale", "-s", default=None, help="Scale sx,sy,sz (multiplier)")
@handle_error
def object_transform(index, translate, rotate, scale):
    """Transform an object (translate, rotate, scale)."""
    trans = [float(x) for x in translate.split(",")] if translate else None
    rot = [float(x) for x in rotate.split(",")] if rotate else None
    scl = [float(x) for x in scale.split(",")] if scale else None

    sess = get_session()
    sess.snapshot(f"Transform object {index}")
    obj = obj_mod.transform_object(sess.get_project(), index,
                                    translate=trans, rotate=rot, scale=scl)
    output(obj, f"Transformed object {index}: {obj['name']}")


@object_group.command("set")
@click.argument("index", type=int)
@click.argument("prop")
@click.argument("value")
@handle_error
def object_set(index, prop, value):
    """Set an object property (name, visible, location, rotation, scale, parent)."""
    sess = get_session()
    sess.snapshot(f"Set object {index} {prop}={value}")
    # Handle vector properties
    if prop in ("location", "rotation", "scale"):
        value = [float(x) for x in value.split(",")]
    obj_mod.set_object_property(sess.get_project(), index, prop, value)
    output({"object": index, "property": prop, "value": value},
           f"Set object {index} {prop} = {value}")


@object_group.command("list")
@handle_error
def object_list():
    """List all objects."""
    sess = get_session()
    objects = obj_mod.list_objects(sess.get_project())
    output(objects, "Objects:")


@object_group.command("get")
@click.argument("index", type=int)
@handle_error
def object_get(index):
    """Get detailed info about an object."""
    sess = get_session()
    obj = obj_mod.get_object(sess.get_project(), index)
    output(obj)


# ── Material Commands ───────────────────────────────────────────
@cli.group()
def material():
    """Material management commands."""
    pass


@material.command("create")
@click.option("--name", "-n", default="Material", help="Material name")
@click.option("--color", "-c", default=None, help="Base color R,G,B,A (0.0-1.0)")
@click.option("--metallic", type=float, default=0.0, help="Metallic factor")
@click.option("--roughness", type=float, default=0.5, help="Roughness factor")
@click.option("--specular", type=float, default=0.5, help="Specular factor")
@handle_error
def material_create(name, color, metallic, roughness, specular):
    """Create a new material."""
    col = [float(x) for x in color.split(",")] if color else None
    sess = get_session()
    sess.snapshot(f"Create material: {name}")
    mat = mat_mod.create_material(
        sess.get_project(), name=name, color=col,
        metallic=metallic, roughness=roughness, specular=specular,
    )
    output(mat, f"Created material: {mat['name']}")


@material.command("assign")
@click.argument("material_index", type=int)
@click.argument("object_index", type=int)
@handle_error
def material_assign(material_index, object_index):
    """Assign a material to an object."""
    sess = get_session()
    sess.snapshot(f"Assign material {material_index} to object {object_index}")
    result = mat_mod.assign_material(sess.get_project(), material_index, object_index)
    output(result, f"Assigned {result['material']} to {result['object']}")


@material.command("set")
@click.argument("index", type=int)
@click.argument("prop")
@click.argument("value")
@handle_error
def material_set(index, prop, value):
    """Set a material property (color, metallic, roughness, specular, alpha, etc.)."""
    # Handle color properties
    if prop in ("color", "emission_color"):
        value = [float(x) for x in value.split(",")]
    elif prop == "use_backface_culling":
        pass  # handled by set_material_property
    else:
        try:
            value = float(value)
        except ValueError:
            pass
    sess = get_session()
    sess.snapshot(f"Set material {index} {prop}")
    mat_mod.set_material_property(sess.get_project(), index, prop, value)
    output({"material": index, "property": prop, "value": value},
           f"Set material {index} {prop}")


@material.command("list")
@handle_error
def material_list():
    """List all materials."""
    sess = get_session()
    materials = mat_mod.list_materials(sess.get_project())
    output(materials, "Materials:")


@material.command("get")
@click.argument("index", type=int)
@handle_error
def material_get(index):
    """Get detailed info about a material."""
    sess = get_session()
    mat = mat_mod.get_material(sess.get_project(), index)
    output(mat)


# ── Modifier Commands ───────────────────────────────────────────
@cli.group("modifier")
def modifier_group():
    """Modifier management commands."""
    pass


@modifier_group.command("list-available")
@click.option("--category", "-c", type=str, default=None,
              help="Filter by category: generate, deform")
@handle_error
def modifier_list_available(category):
    """List all available modifiers."""
    modifiers = mod_mod.list_available(category)
    output(modifiers, "Available modifiers:")


@modifier_group.command("info")
@click.argument("name")
@handle_error
def modifier_info(name):
    """Show details about a modifier."""
    info = mod_mod.get_modifier_info(name)
    output(info)


@modifier_group.command("add")
@click.argument("modifier_type")
@click.option("--object", "-o", "object_index", type=int, default=0, help="Object index")
@click.option("--name", "-n", default=None, help="Custom modifier name")
@click.option("--param", "-p", multiple=True, help="Parameter: key=value")
@handle_error
def modifier_add(modifier_type, object_index, name, param):
    """Add a modifier to an object."""
    params = {}
    for p in param:
        if "=" not in p:
            raise ValueError(f"Invalid param format: '{p}'. Use key=value.")
        k, v = p.split("=", 1)
        try:
            v = float(v) if "." in v else int(v)
        except ValueError:
            pass
        params[k] = v

    sess = get_session()
    sess.snapshot(f"Add modifier {modifier_type} to object {object_index}")
    result = mod_mod.add_modifier(
        sess.get_project(), modifier_type, object_index, name=name, params=params,
    )
    output(result, f"Added modifier: {result['name']}")


@modifier_group.command("remove")
@click.argument("modifier_index", type=int)
@click.option("--object", "-o", "object_index", type=int, default=0)
@handle_error
def modifier_remove(modifier_index, object_index):
    """Remove a modifier by index."""
    sess = get_session()
    sess.snapshot(f"Remove modifier {modifier_index} from object {object_index}")
    result = mod_mod.remove_modifier(sess.get_project(), modifier_index, object_index)
    output(result, f"Removed modifier {modifier_index}")


@modifier_group.command("set")
@click.argument("modifier_index", type=int)
@click.argument("param")
@click.argument("value")
@click.option("--object", "-o", "object_index", type=int, default=0)
@handle_error
def modifier_set(modifier_index, param, value, object_index):
    """Set a modifier parameter."""
    try:
        value = float(value) if "." in str(value) else int(value)
    except ValueError:
        pass
    sess = get_session()
    sess.snapshot(f"Set modifier {modifier_index} {param}={value}")
    mod_mod.set_modifier_param(sess.get_project(), modifier_index, param, value, object_index)
    output({"modifier": modifier_index, "param": param, "value": value},
           f"Set modifier {modifier_index} {param} = {value}")


@modifier_group.command("list")
@click.option("--object", "-o", "object_index", type=int, default=0)
@handle_error
def modifier_list(object_index):
    """List modifiers on an object."""
    sess = get_session()
    modifiers = mod_mod.list_modifiers(sess.get_project(), object_index)
    output(modifiers, f"Modifiers on object {object_index}:")


# ── Camera Commands ─────────────────────────────────────────────
@cli.group()
def camera():
    """Camera management commands."""
    pass


@camera.command("add")
@click.option("--name", "-n", default=None, help="Camera name")
@click.option("--location", "-l", default=None, help="Location x,y,z")
@click.option("--rotation", "-r", default=None, help="Rotation x,y,z (degrees)")
@click.option("--type", "camera_type", type=click.Choice(["PERSP", "ORTHO", "PANO"]),
              default="PERSP")
@click.option("--focal-length", "-f", type=float, default=50.0, help="Focal length (mm)")
@click.option("--active", is_flag=True, help="Set as active camera")
@handle_error
def camera_add(name, location, rotation, camera_type, focal_length, active):
    """Add a camera to the scene."""
    loc = [float(x) for x in location.split(",")] if location else None
    rot = [float(x) for x in rotation.split(",")] if rotation else None

    sess = get_session()
    sess.snapshot("Add camera")
    cam = light_mod.add_camera(
        sess.get_project(), name=name, location=loc, rotation=rot,
        camera_type=camera_type, focal_length=focal_length, set_active=active,
    )
    output(cam, f"Added camera: {cam['name']}")


@camera.command("set")
@click.argument("index", type=int)
@click.argument("prop")
@click.argument("value")
@handle_error
def camera_set(index, prop, value):
    """Set a camera property."""
    # Handle vector properties
    if prop in ("location", "rotation"):
        value = [float(x) for x in value.split(",")]
    sess = get_session()
    sess.snapshot(f"Set camera {index} {prop}")
    light_mod.set_camera(sess.get_project(), index, prop, value)
    output({"camera": index, "property": prop, "value": value},
           f"Set camera {index} {prop}")


@camera.command("set-active")
@click.argument("index", type=int)
@handle_error
def camera_set_active(index):
    """Set the active camera."""
    sess = get_session()
    sess.snapshot(f"Set active camera {index}")
    result = light_mod.set_active_camera(sess.get_project(), index)
    output(result, f"Active camera: {result['active_camera']}")


@camera.command("list")
@handle_error
def camera_list():
    """List all cameras."""
    sess = get_session()
    cameras = light_mod.list_cameras(sess.get_project())
    output(cameras, "Cameras:")


@camera.command("create")
@click.option("--name", "-n", default="Camera", help="Camera name")
@click.option("--type", "cam_type",
              type=click.Choice(["perspective", "orthographic", "panoramic"]),
              default="perspective", help="Camera type")
@click.option("--fov", type=float, default=50.0, help="Vertical FOV in degrees")
@click.option("--location", "-l", default=None, help="Location x,y,z")
@click.option("--rotation", "-r", default=None, help="Rotation x,y,z (degrees)")
@handle_error
def camera_create(name, cam_type, fov, location, rotation):
    """Create a 3D camera with animated-move support."""
    loc = [float(x) for x in location.split(",")] if location else None
    rot = [float(x) for x in rotation.split(",")] if rotation else None
    sess = get_session()
    sess.snapshot(f"Create camera: {name}")
    result = camera_mod.create_camera(
        sess, cam_type=cam_type, fov=fov, name=name,
        location=loc, rotation=rot,
    )
    output(result["camera"], f"Created camera: {result['camera']['name']}")


@camera.command("dolly")
@click.argument("camera_name")
@click.option("--start", "-s", required=True, help="Start position x,y,z")
@click.option("--end", "-e", required=True, help="End position x,y,z")
@click.option("--duration", "-d", type=float, required=True, help="Duration in seconds")
@click.option("--fps", type=int, default=30, help="Frames per second")
@click.option("--easing", default="ease_in_out_cubic", help="Easing function name")
@handle_error
def camera_dolly(camera_name, start, end, duration, fps, easing):
    """Animate camera position (dolly move)."""
    start_v = [float(x) for x in start.split(",")]
    end_v = [float(x) for x in end.split(",")]
    sess = get_session()
    sess.snapshot(f"Camera dolly: {camera_name}")
    lines = camera_mod.dolly(sess, camera_name, start_v, end_v, duration, fps, easing)
    output({"camera": camera_name, "keyframes": len([l for l in lines if "keyframe_insert" in l])},
           f"Dolly: {len(lines)} script lines generated")


@camera.command("orbit")
@click.argument("camera_name")
@click.option("--center", "-c", required=True, help="Orbit center x,y,z")
@click.option("--radius", "-r", type=float, required=True, help="Orbit radius")
@click.option("--start-angle", type=float, default=0.0, help="Start angle (degrees)")
@click.option("--end-angle", type=float, default=360.0, help="End angle (degrees)")
@click.option("--duration", "-d", type=float, required=True, help="Duration in seconds")
@click.option("--fps", type=int, default=30, help="Frames per second")
@click.option("--easing", default="ease_in_out_sine", help="Easing function name")
@handle_error
def camera_orbit(camera_name, center, radius, start_angle, end_angle, duration, fps, easing):
    """Orbit camera around a center point."""
    center_v = [float(x) for x in center.split(",")]
    sess = get_session()
    sess.snapshot(f"Camera orbit: {camera_name}")
    lines = camera_mod.orbit(
        sess, camera_name, center_v, radius, start_angle, end_angle, duration, fps, easing,
    )
    output({"camera": camera_name, "keyframes": len([l for l in lines if "keyframe_insert" in l])},
           f"Orbit: {len(lines)} script lines generated")


@camera.command("pan")
@click.argument("camera_name")
@click.option("--start-target", required=True, help="Start look-at point x,y,z")
@click.option("--end-target", required=True, help="End look-at point x,y,z")
@click.option("--duration", "-d", type=float, required=True, help="Duration in seconds")
@click.option("--fps", type=int, default=30, help="Frames per second")
@click.option("--easing", default="linear", help="Easing function name")
@handle_error
def camera_pan(camera_name, start_target, end_target, duration, fps, easing):
    """Pan camera from one look-at target to another."""
    start_v = [float(x) for x in start_target.split(",")]
    end_v = [float(x) for x in end_target.split(",")]
    sess = get_session()
    sess.snapshot(f"Camera pan: {camera_name}")
    lines = camera_mod.pan(sess, camera_name, start_v, end_v, duration, fps, easing)
    output({"camera": camera_name, "keyframes": len([l for l in lines if "keyframe_insert" in l])},
           f"Pan: {len(lines)} script lines generated")


@camera.command("zoom")
@click.argument("camera_name")
@click.option("--start-fov", type=float, required=True, help="Start FOV in degrees")
@click.option("--end-fov", type=float, required=True, help="End FOV in degrees")
@click.option("--duration", "-d", type=float, required=True, help="Duration in seconds")
@click.option("--fps", type=int, default=30, help="Frames per second")
@click.option("--easing", default="ease_out_quad", help="Easing function name")
@handle_error
def camera_zoom(camera_name, start_fov, end_fov, duration, fps, easing):
    """Animate camera field-of-view (zoom)."""
    sess = get_session()
    sess.snapshot(f"Camera zoom: {camera_name}")
    lines = camera_mod.zoom(sess, camera_name, start_fov, end_fov, duration, fps, easing)
    output({"camera": camera_name, "keyframes": len([l for l in lines if "keyframe_insert" in l])},
           f"Zoom: {len(lines)} script lines generated")


@camera.command("rack-focus")
@click.argument("camera_name")
@click.option("--start-distance", type=float, required=True, help="Start focus distance")
@click.option("--end-distance", type=float, required=True, help="End focus distance")
@click.option("--duration", "-d", type=float, required=True, help="Duration in seconds")
@click.option("--fps", type=int, default=30, help="Frames per second")
@click.option("--easing", default="ease_in_out_sine", help="Easing function name")
@handle_error
def camera_rack_focus(camera_name, start_distance, end_distance, duration, fps, easing):
    """Animate depth-of-field focus distance (rack focus)."""
    sess = get_session()
    sess.snapshot(f"Camera rack focus: {camera_name}")
    lines = camera_mod.rack_focus(
        sess, camera_name, start_distance, end_distance, duration, fps, easing,
    )
    output({"camera": camera_name, "keyframes": len([l for l in lines if "keyframe_insert" in l])},
           f"Rack focus: {len(lines)} script lines generated")


@camera.command("crane")
@click.argument("camera_name")
@click.option("--start-height", type=float, required=True, help="Start height (Z)")
@click.option("--end-height", type=float, required=True, help="End height (Z)")
@click.option("--duration", "-d", type=float, required=True, help="Duration in seconds")
@click.option("--fps", type=int, default=30, help="Frames per second")
@click.option("--easing", default="ease_out_cubic", help="Easing function name")
@handle_error
def camera_crane(camera_name, start_height, end_height, duration, fps, easing):
    """Animate camera height (crane / jib move)."""
    sess = get_session()
    sess.snapshot(f"Camera crane: {camera_name}")
    lines = camera_mod.crane(
        sess, camera_name, start_height, end_height, duration, fps, easing,
    )
    output({"camera": camera_name, "keyframes": len([l for l in lines if "keyframe_insert" in l])},
           f"Crane: {len(lines)} script lines generated")


@camera.command("follow-path")
@click.argument("camera_name")
@click.option("--point", "-p", multiple=True, required=True,
              help="Path point x,y,z (repeat for each point)")
@click.option("--duration", "-d", type=float, required=True, help="Duration in seconds")
@click.option("--fps", type=int, default=30, help="Frames per second")
@click.option("--easing", default="linear", help="Easing function name")
@handle_error
def camera_follow_path(camera_name, point, duration, fps, easing):
    """Animate camera along a bezier path."""
    points = [[float(x) for x in p.split(",")] for p in point]
    sess = get_session()
    sess.snapshot(f"Camera follow path: {camera_name}")
    lines = camera_mod.follow_path(sess, camera_name, points, duration, fps, easing)
    output({"camera": camera_name, "keyframes": len([l for l in lines if "keyframe_insert" in l])},
           f"Follow path: {len(lines)} script lines generated")


@camera.command("shake")
@click.argument("camera_name")
@click.option("--intensity", type=float, required=True, help="Peak shake amplitude")
@click.option("--frequency", type=float, required=True, help="Shake frequency (Hz)")
@click.option("--decay", type=float, required=True, help="Exponential decay constant")
@click.option("--duration", "-d", type=float, required=True, help="Duration in seconds")
@click.option("--fps", type=int, default=30, help="Frames per second")
@handle_error
def camera_shake(camera_name, intensity, frequency, decay, duration, fps):
    """Add procedural camera shake with exponential decay."""
    sess = get_session()
    sess.snapshot(f"Camera shake: {camera_name}")
    lines = camera_mod.shake(sess, camera_name, intensity, frequency, decay, duration, fps)
    output({"camera": camera_name, "keyframes": len([l for l in lines if "keyframe_insert" in l])},
           f"Shake: {len(lines)} script lines generated")


# ── Shape Commands ──────────────────────────────────────────────
@cli.group("shape")
def shape_group():
    """Shape layer creation and path animation commands."""
    pass


@shape_group.command("rectangle")
@click.option("--width", "-w", type=float, required=True, help="Width")
@click.option("--height", "-h", type=float, required=True, help="Height")
@click.option("--corner-radius", "-cr", type=float, default=0.0, help="Corner radius")
@click.option("--fill", "-f", default=None, help="Fill color R,G,B,A")
@click.option("--stroke", "-s", default=None, help="Stroke color R,G,B,A")
@click.option("--name", "-n", default="Rectangle", help="Object name")
@handle_error
def shape_rectangle(width, height, corner_radius, fill, stroke, name):
    """Create a rectangle shape."""
    fill_col = [float(x) for x in fill.split(",")] if fill else None
    stroke_col = [float(x) for x in stroke.split(",")] if stroke else None
    sess = get_session()
    sess.snapshot(f"Create rectangle: {name}")
    lines = shape_mod.create_rectangle(
        sess, width, height, corner_radius=corner_radius,
        fill_color=fill_col, stroke_color=stroke_col, name=name,
    )
    output({"name": name, "script_lines": len(lines)}, f"Rectangle '{name}': {len(lines)} script lines")


@shape_group.command("ellipse")
@click.option("--rx", type=float, required=True, help="Horizontal radius")
@click.option("--ry", type=float, required=True, help="Vertical radius")
@click.option("--fill", "-f", default=None, help="Fill color R,G,B,A")
@click.option("--name", "-n", default="Ellipse", help="Object name")
@handle_error
def shape_ellipse(rx, ry, fill, name):
    """Create an ellipse shape."""
    fill_col = [float(x) for x in fill.split(",")] if fill else None
    sess = get_session()
    sess.snapshot(f"Create ellipse: {name}")
    lines = shape_mod.create_ellipse(sess, rx, ry, fill_color=fill_col, name=name)
    output({"name": name, "script_lines": len(lines)}, f"Ellipse '{name}': {len(lines)} script lines")


@shape_group.command("polygon")
@click.option("--sides", type=int, required=True, help="Number of sides")
@click.option("--radius", "-r", type=float, required=True, help="Circumscribed radius")
@click.option("--fill", "-f", default=None, help="Fill color R,G,B,A")
@click.option("--name", "-n", default="Polygon", help="Object name")
@handle_error
def shape_polygon(sides, radius, fill, name):
    """Create a regular polygon shape."""
    fill_col = [float(x) for x in fill.split(",")] if fill else None
    sess = get_session()
    sess.snapshot(f"Create polygon: {name}")
    lines = shape_mod.create_polygon(sess, sides, radius, fill_color=fill_col, name=name)
    output({"name": name, "script_lines": len(lines)}, f"Polygon '{name}': {len(lines)} script lines")


@shape_group.command("star")
@click.option("--points", "-p", type=int, required=True, help="Number of star points")
@click.option("--inner-radius", type=float, required=True, help="Inner radius")
@click.option("--outer-radius", type=float, required=True, help="Outer radius")
@click.option("--fill", "-f", default=None, help="Fill color R,G,B,A")
@click.option("--name", "-n", default="Star", help="Object name")
@handle_error
def shape_star(points, inner_radius, outer_radius, fill, name):
    """Create a star shape."""
    fill_col = [float(x) for x in fill.split(",")] if fill else None
    sess = get_session()
    sess.snapshot(f"Create star: {name}")
    lines = shape_mod.create_star(
        sess, points, inner_radius, outer_radius, fill_color=fill_col, name=name,
    )
    output({"name": name, "script_lines": len(lines)}, f"Star '{name}': {len(lines)} script lines")


@shape_group.command("morph")
@click.argument("shape_a")
@click.argument("shape_b")
@click.option("--duration", "-d", type=float, required=True, help="Duration in seconds")
@click.option("--fps", type=int, default=30, help="Frames per second")
@click.option("--easing", default="ease_in_out_cubic", help="Easing function name")
@handle_error
def shape_morph(shape_a, shape_b, duration, fps, easing):
    """Animate shape-key morph between two objects."""
    sess = get_session()
    sess.snapshot(f"Morph: {shape_a} → {shape_b}")
    lines = shape_mod.morph(sess, shape_a, shape_b, duration, fps, easing)
    output({"shape_a": shape_a, "shape_b": shape_b,
            "keyframes": len([l for l in lines if "keyframe_insert" in l])},
           f"Morph: {len(lines)} script lines generated")


@shape_group.command("trim-path")
@click.argument("shape_name")
@click.option("--start-pct", type=float, default=0.0, help="Start percentage (0-1)")
@click.option("--end-pct", type=float, default=1.0, help="End percentage (0-1)")
@click.option("--duration", "-d", type=float, required=True, help="Duration in seconds")
@click.option("--fps", type=int, default=30, help="Frames per second")
@click.option("--easing", default="ease_in_out_cubic", help="Easing function name")
@handle_error
def shape_trim_path(shape_name, start_pct, end_pct, duration, fps, easing):
    """Animate curve trim path (draw-on effect)."""
    sess = get_session()
    sess.snapshot(f"Trim path: {shape_name}")
    lines = shape_mod.trim_path(sess, shape_name, start_pct, end_pct, duration, fps, easing)
    output({"shape": shape_name, "keyframes": len([l for l in lines if "keyframe_insert" in l])},
           f"Trim path: {len(lines)} script lines generated")


@shape_group.command("offset-path")
@click.argument("shape_name")
@click.option("--amount", "-a", type=float, required=True, help="Solidify thickness target")
@click.option("--duration", "-d", type=float, required=True, help="Duration in seconds")
@click.option("--fps", type=int, default=30, help="Frames per second")
@click.option("--easing", default="ease_out_cubic", help="Easing function name")
@handle_error
def shape_offset_path(shape_name, amount, duration, fps, easing):
    """Animate solidify modifier thickness (offset path)."""
    sess = get_session()
    sess.snapshot(f"Offset path: {shape_name}")
    lines = shape_mod.offset_path(sess, shape_name, amount, duration, fps, easing)
    output({"shape": shape_name, "keyframes": len([l for l in lines if "keyframe_insert" in l])},
           f"Offset path: {len(lines)} script lines generated")


@shape_group.command("repeater")
@click.argument("shape_name")
@click.option("--copies", "-c", type=int, required=True, help="Number of copies")
@click.option("--offset", "-o", default=None, help="Offset x,y,z per copy")
@click.option("--scale-step", type=float, default=1.0, help="Scale multiplier per copy")
@click.option("--rotation-step", type=float, default=0.0, help="Z rotation step (degrees)")
@handle_error
def shape_repeater(shape_name, copies, offset, scale_step, rotation_step):
    """Create copies via Array modifier."""
    off = [float(x) for x in offset.split(",")] if offset else None
    sess = get_session()
    sess.snapshot(f"Repeater: {shape_name} x{copies}")
    lines = shape_mod.repeater(sess, shape_name, copies, offset=off,
                                scale_step=scale_step, rotation_step=rotation_step)
    output({"shape": shape_name, "copies": copies, "script_lines": len(lines)},
           f"Repeater: {len(lines)} script lines generated")


# ── Particles Commands ──────────────────────────────────────────
@cli.group("particles")
def particles_group():
    """Particle system integration commands."""
    pass


@particles_group.command("emit-object")
@click.argument("object_name")
@click.option("--count", type=int, default=None, help="Particle count")
@click.option("--lifetime", type=int, default=None, help="Particle lifetime (frames)")
@click.option("--emit-from", type=click.Choice(["FACE", "VOLUME", "VERT"]), default=None)
@handle_error
def particles_emit_object(object_name, count, lifetime, emit_from):
    """Add a particle system to an existing object."""
    cfg = {}
    if count is not None:
        cfg["count"] = count
    if lifetime is not None:
        cfg["lifetime"] = lifetime
    if emit_from is not None:
        cfg["emit_from"] = emit_from
    sess = get_session()
    sess.snapshot(f"Particle system on: {object_name}")
    lines = particles_mod.emit_from_object(sess, object_name, cfg or None)
    output({"object": object_name, "script_lines": len(lines)},
           f"Particles on '{object_name}': {len(lines)} script lines")


@particles_group.command("emit-point")
@click.option("--position", "-p", required=True, help="Position x,y,z")
@click.option("--count", type=int, default=None, help="Particle count")
@click.option("--lifetime", type=int, default=None, help="Particle lifetime (frames)")
@handle_error
def particles_emit_point(position, count, lifetime):
    """Create an emitter at a world position."""
    pos = [float(x) for x in position.split(",")]
    cfg = {}
    if count is not None:
        cfg["count"] = count
    if lifetime is not None:
        cfg["lifetime"] = lifetime
    sess = get_session()
    sess.snapshot(f"Point emitter at {pos}")
    lines = particles_mod.emit_from_point(sess, pos, cfg or None)
    output({"position": pos, "script_lines": len(lines)},
           f"Point emitter: {len(lines)} script lines")


@particles_group.command("emit-text")
@click.argument("text_object")
@click.option("--count", type=int, default=None, help="Particle count")
@handle_error
def particles_emit_text(text_object, count):
    """Convert a text object to mesh and add particles."""
    cfg = {}
    if count is not None:
        cfg["count"] = count
    sess = get_session()
    sess.snapshot(f"Text particle emitter: {text_object}")
    lines = particles_mod.emit_from_text(sess, text_object, cfg or None)
    output({"text_object": text_object, "script_lines": len(lines)},
           f"Text emitter '{text_object}': {len(lines)} script lines")


@particles_group.command("force-field")
@click.option("--type", "force_type",
              type=click.Choice(["TURBULENCE", "WIND", "VORTEX", "FORCE"]),
              required=True, help="Force field type")
@click.option("--strength", "-s", type=float, required=True, help="Force strength")
@click.option("--position", "-p", default=None, help="Position x,y,z")
@click.option("--name", "-n", default="ForceField", help="Object name")
@handle_error
def particles_force_field(force_type, strength, position, name):
    """Add a force field effector."""
    pos = [float(x) for x in position.split(",")] if position else None
    sess = get_session()
    sess.snapshot(f"Force field: {force_type}")
    lines = particles_mod.add_force_field(sess, force_type, strength, position=pos, name=name)
    output({"type": force_type, "strength": strength, "script_lines": len(lines)},
           f"Force field '{force_type}': {len(lines)} script lines")


@particles_group.command("preset-confetti")
@click.argument("object_name")
@handle_error
def particles_preset_confetti(object_name):
    """Apply confetti burst preset."""
    sess = get_session()
    sess.snapshot(f"Confetti on: {object_name}")
    lines = particles_mod.preset_confetti(sess, object_name)
    output({"object": object_name, "script_lines": len(lines)},
           f"Confetti preset: {len(lines)} script lines")


@particles_group.command("preset-sparks")
@click.argument("object_name")
@click.option("--color", "-c", default=None, help="Spark color R,G,B,A")
@handle_error
def particles_preset_sparks(object_name, color):
    """Apply sparks preset."""
    col = [float(x) for x in color.split(",")] if color else None
    sess = get_session()
    sess.snapshot(f"Sparks on: {object_name}")
    lines = particles_mod.preset_sparks(sess, object_name, color=col)
    output({"object": object_name, "script_lines": len(lines)},
           f"Sparks preset: {len(lines)} script lines")


@particles_group.command("preset-disintegrate")
@click.argument("object_name")
@click.option("--duration", "-d", type=float, default=2.0, help="Effect duration (seconds)")
@handle_error
def particles_preset_disintegrate(object_name, duration):
    """Apply disintegrate preset (Explode modifier)."""
    sess = get_session()
    sess.snapshot(f"Disintegrate: {object_name}")
    lines = particles_mod.preset_disintegrate(sess, object_name, duration=duration)
    output({"object": object_name, "script_lines": len(lines)},
           f"Disintegrate preset: {len(lines)} script lines")


@particles_group.command("preset-data-stream")
@click.option("--direction", "-d", default=None, help="Direction x,y,z")
@click.option("--speed", "-s", type=float, default=5.0, help="Particle speed")
@handle_error
def particles_preset_data_stream(direction, speed):
    """Apply data-stream flowing particles preset."""
    dir_vec = [float(x) for x in direction.split(",")] if direction else None
    sess = get_session()
    sess.snapshot("Data stream particles")
    lines = particles_mod.preset_data_stream(sess, direction=dir_vec, speed=speed)
    output({"script_lines": len(lines)}, f"Data stream preset: {len(lines)} script lines")


# ── Compositor Commands ─────────────────────────────────────────
@cli.group("compositor")
def compositor_group():
    """Node compositor post-processing commands."""
    pass


@compositor_group.command("glow")
@click.option("--threshold", type=float, default=0.5, help="Brightness threshold")
@click.option("--intensity", type=float, default=1.0, help="Glow intensity")
@click.option("--size", type=int, default=9, help="Glow size")
@click.option("--quality", type=click.Choice(["LOW", "MEDIUM", "HIGH"]), default="MEDIUM")
@handle_error
def compositor_glow(threshold, intensity, size, quality):
    """Add FOG_GLOW glare effect."""
    sess = get_session()
    lines = compositor_mod.glow(sess, threshold=threshold, intensity=intensity,
                                 size=size, quality=quality)
    output({"effect": "glow", "script_lines": len(lines)},
           f"Glow: {len(lines)} script lines")


@compositor_group.command("color-grade")
@click.option("--lift", default=None, help="Lift R,G,B")
@click.option("--gamma", default=None, help="Gamma R,G,B")
@click.option("--gain", default=None, help="Gain R,G,B")
@click.option("--saturation", type=float, default=1.0, help="Saturation multiplier")
@handle_error
def compositor_color_grade(lift, gamma, gain, saturation):
    """Add color grading (Color Balance + Hue Saturation)."""
    lift_v  = [float(x) for x in lift.split(",")]  if lift  else None
    gamma_v = [float(x) for x in gamma.split(",")] if gamma else None
    gain_v  = [float(x) for x in gain.split(",")]  if gain  else None
    sess = get_session()
    lines = compositor_mod.color_grade(sess, lift=lift_v, gamma=gamma_v,
                                        gain=gain_v, saturation=saturation)
    output({"effect": "color_grade", "script_lines": len(lines)},
           f"Color grade: {len(lines)} script lines")


@compositor_group.command("chromatic-aberration")
@click.option("--dispersion", type=float, default=0.01, help="Dispersion amount")
@handle_error
def compositor_chromatic_aberration(dispersion):
    """Add chromatic aberration effect."""
    sess = get_session()
    lines = compositor_mod.chromatic_aberration(sess, dispersion=dispersion)
    output({"effect": "chromatic_aberration", "script_lines": len(lines)},
           f"Chromatic aberration: {len(lines)} script lines")


@compositor_group.command("lens-distortion")
@click.option("--distortion", type=float, default=0.1, help="Distortion amount")
@click.option("--dispersion", type=float, default=0.0, help="Chromatic dispersion")
@handle_error
def compositor_lens_distortion(distortion, dispersion):
    """Add lens distortion effect."""
    sess = get_session()
    lines = compositor_mod.lens_distortion(sess, distortion=distortion, dispersion=dispersion)
    output({"effect": "lens_distortion", "script_lines": len(lines)},
           f"Lens distortion: {len(lines)} script lines")


@compositor_group.command("vignette")
@click.option("--intensity", type=float, default=0.5, help="Vignette darkness")
@click.option("--softness", type=float, default=0.3, help="Edge softness")
@handle_error
def compositor_vignette(intensity, softness):
    """Add vignette effect."""
    sess = get_session()
    lines = compositor_mod.vignette(sess, intensity=intensity, softness=softness)
    output({"effect": "vignette", "script_lines": len(lines)},
           f"Vignette: {len(lines)} script lines")


@compositor_group.command("film-grain")
@click.option("--intensity", type=float, default=0.1, help="Grain intensity")
@click.option("--size", type=float, default=1.0, help="Grain size")
@handle_error
def compositor_film_grain(intensity, size):
    """Add film grain effect."""
    sess = get_session()
    lines = compositor_mod.film_grain(sess, intensity=intensity, size=size)
    output({"effect": "film_grain", "script_lines": len(lines)},
           f"Film grain: {len(lines)} script lines")


@compositor_group.command("motion-blur")
@click.option("--samples", type=int, default=32, help="Blur samples")
@click.option("--speed-factor", type=float, default=1.0, help="Speed scale factor")
@handle_error
def compositor_motion_blur(samples, speed_factor):
    """Add motion blur (Vector Blur node)."""
    sess = get_session()
    lines = compositor_mod.motion_blur(sess, samples=samples, speed_factor=speed_factor)
    output({"effect": "motion_blur", "script_lines": len(lines)},
           f"Motion blur: {len(lines)} script lines")


@compositor_group.command("depth-of-field")
@click.option("--f-stop", type=float, default=2.8, help="Aperture f-stop")
@click.option("--max-blur", type=float, default=16.0, help="Maximum blur radius (px)")
@handle_error
def compositor_depth_of_field(f_stop, max_blur):
    """Add depth-of-field blur (Defocus node)."""
    sess = get_session()
    lines = compositor_mod.depth_of_field(sess, f_stop=f_stop, max_blur=max_blur)
    output({"effect": "depth_of_field", "script_lines": len(lines)},
           f"Depth of field: {len(lines)} script lines")


@compositor_group.command("bloom")
@click.option("--threshold", type=float, default=0.8, help="Bloom threshold")
@click.option("--radius", type=int, default=9, help="Bloom radius")
@click.option("--intensity", type=float, default=1.0, help="Bloom intensity")
@handle_error
def compositor_bloom(threshold, radius, intensity):
    """Add bloom effect (Glare GHOSTS node)."""
    sess = get_session()
    lines = compositor_mod.bloom(sess, threshold=threshold, radius=radius, intensity=intensity)
    output({"effect": "bloom", "script_lines": len(lines)},
           f"Bloom: {len(lines)} script lines")


@compositor_group.command("sharpen")
@click.option("--factor", type=float, default=0.5, help="Sharpen strength")
@handle_error
def compositor_sharpen(factor):
    """Add sharpening (Filter SHARPEN node)."""
    sess = get_session()
    lines = compositor_mod.sharpen(sess, factor=factor)
    output({"effect": "sharpen", "script_lines": len(lines)},
           f"Sharpen: {len(lines)} script lines")


@compositor_group.command("apply-chain")
@click.option("--effect", "-e", multiple=True, required=True,
              help="Effect type: glow,bloom,vignette,sharpen,film_grain,motion_blur,etc.")
@handle_error
def compositor_apply_chain(effect):
    """Chain multiple compositor effects in sequence."""
    effects_list = [{"type": e.strip()} for e in effect]
    sess = get_session()
    lines = compositor_mod.apply_chain(sess, effects_list)
    output({"effects": [e["type"] for e in effects_list], "script_lines": len(lines)},
           f"Effect chain ({len(effects_list)} effects): {len(lines)} script lines")


# ── Light Commands ──────────────────────────────────────────────
@cli.group()
def light():
    """Light management commands."""
    pass


@light.command("add")
@click.argument("light_type", type=click.Choice(["point", "sun", "spot", "area"]))
@click.option("--name", "-n", default=None, help="Light name")
@click.option("--location", "-l", default=None, help="Location x,y,z")
@click.option("--rotation", "-r", default=None, help="Rotation x,y,z (degrees)")
@click.option("--color", "-c", default=None, help="Color R,G,B (0.0-1.0)")
@click.option("--power", "-w", type=float, default=None, help="Power/energy")
@handle_error
def light_add(light_type, name, location, rotation, color, power):
    """Add a light to the scene."""
    loc = [float(x) for x in location.split(",")] if location else None
    rot = [float(x) for x in rotation.split(",")] if rotation else None
    col = [float(x) for x in color.split(",")] if color else None

    sess = get_session()
    sess.snapshot(f"Add light: {light_type}")
    lt = light_mod.add_light(
        sess.get_project(), light_type=light_type.upper(), name=name,
        location=loc, rotation=rot, color=col, power=power,
    )
    output(lt, f"Added {light_type} light: {lt['name']}")


@light.command("set")
@click.argument("index", type=int)
@click.argument("prop")
@click.argument("value")
@handle_error
def light_set(index, prop, value):
    """Set a light property."""
    # Handle vector/color properties
    if prop in ("location", "rotation", "color"):
        value = [float(x) for x in value.split(",")]
    sess = get_session()
    sess.snapshot(f"Set light {index} {prop}")
    light_mod.set_light(sess.get_project(), index, prop, value)
    output({"light": index, "property": prop, "value": value},
           f"Set light {index} {prop}")


@light.command("list")
@handle_error
def light_list():
    """List all lights."""
    sess = get_session()
    lights = light_mod.list_lights(sess.get_project())
    output(lights, "Lights:")


# ── Animation Commands ──────────────────────────────────────────
@cli.group()
def animation():
    """Animation and keyframe commands."""
    pass


@animation.command("keyframe")
@click.argument("object_index", type=int)
@click.argument("frame", type=int)
@click.argument("prop")
@click.argument("value")
@click.option("--interpolation", "-i", type=click.Choice(["CONSTANT", "LINEAR", "BEZIER"]),
              default="BEZIER")
@handle_error
def animation_keyframe(object_index, frame, prop, value, interpolation):
    """Set a keyframe on an object."""
    # Handle vector values
    if prop in ("location", "rotation", "scale"):
        value = [float(x) for x in value.split(",")]
    sess = get_session()
    sess.snapshot(f"Add keyframe at frame {frame}")
    result = anim_mod.add_keyframe(
        sess.get_project(), object_index, frame, prop, value, interpolation,
    )
    output(result, f"Keyframe set at frame {frame}")


@animation.command("remove-keyframe")
@click.argument("object_index", type=int)
@click.argument("frame", type=int)
@click.option("--prop", "-p", default=None, help="Property (remove all at frame if not specified)")
@handle_error
def animation_remove_keyframe(object_index, frame, prop):
    """Remove a keyframe from an object."""
    sess = get_session()
    sess.snapshot(f"Remove keyframe at frame {frame}")
    removed = anim_mod.remove_keyframe(sess.get_project(), object_index, frame, prop)
    output(removed, f"Removed {len(removed)} keyframe(s) at frame {frame}")


@animation.command("frame-range")
@click.argument("start", type=int)
@click.argument("end", type=int)
@handle_error
def animation_frame_range(start, end):
    """Set the animation frame range."""
    sess = get_session()
    sess.snapshot("Set frame range")
    result = anim_mod.set_frame_range(sess.get_project(), start, end)
    output(result, f"Frame range: {start}-{end}")


@animation.command("fps")
@click.argument("fps", type=int)
@handle_error
def animation_fps(fps):
    """Set the animation FPS."""
    sess = get_session()
    result = anim_mod.set_fps(sess.get_project(), fps)
    output(result, f"FPS set to {fps}")


@animation.command("list-keyframes")
@click.argument("object_index", type=int)
@click.option("--prop", "-p", default=None, help="Filter by property")
@handle_error
def animation_list_keyframes(object_index, prop):
    """List keyframes for an object."""
    sess = get_session()
    keyframes = anim_mod.list_keyframes(sess.get_project(), object_index, prop)
    output(keyframes, f"Keyframes for object {object_index}:")


# ── Render Commands ─────────────────────────────────────────────
@cli.group("render")
def render_group():
    """Render settings and output commands."""
    pass


@render_group.command("settings")
@click.option("--engine", type=click.Choice(["CYCLES", "EEVEE", "WORKBENCH"]), default=None)
@click.option("--resolution-x", "-rx", type=int, default=None)
@click.option("--resolution-y", "-ry", type=int, default=None)
@click.option("--resolution-percentage", type=int, default=None)
@click.option("--samples", type=int, default=None)
@click.option("--denoising/--no-denoising", default=None)
@click.option("--transparent/--no-transparent", default=None)
@click.option("--format", "output_format", default=None)
@click.option("--output-path", default=None)
@click.option("--preset", default=None, help="Apply render preset")
@handle_error
def render_settings(engine, resolution_x, resolution_y, resolution_percentage,
                    samples, denoising, transparent, output_format, output_path, preset):
    """Configure render settings."""
    sess = get_session()
    sess.snapshot("Update render settings")
    result = render_mod.set_render_settings(
        sess.get_project(),
        engine=engine,
        resolution_x=resolution_x,
        resolution_y=resolution_y,
        resolution_percentage=resolution_percentage,
        samples=samples,
        use_denoising=denoising,
        film_transparent=transparent,
        output_format=output_format,
        output_path=output_path,
        preset=preset,
    )
    output(result, "Render settings updated")


@render_group.command("info")
@handle_error
def render_info():
    """Show current render settings."""
    sess = get_session()
    info = render_mod.get_render_settings(sess.get_project())
    output(info)


@render_group.command("presets")
@handle_error
def render_presets():
    """List available render presets."""
    presets = render_mod.list_render_presets()
    output(presets, "Render presets:")


@render_group.command("execute")
@click.argument("output_path")
@click.option("--frame", "-f", type=int, default=None, help="Specific frame to render")
@click.option("--animation", "-a", is_flag=True, help="Render full animation")
@click.option("--overwrite", is_flag=True, help="Overwrite existing file")
@handle_error
def render_execute(output_path, frame, animation, overwrite):
    """Render the scene (generates bpy script)."""
    sess = get_session()
    result = render_mod.render_scene(
        sess.get_project(), output_path,
        frame=frame, animation=animation, overwrite=overwrite,
    )
    output(result, f"Render script generated: {result['script_path']}")


@render_group.command("script")
@click.argument("output_path")
@click.option("--frame", "-f", type=int, default=None)
@click.option("--animation", "-a", is_flag=True)
@handle_error
def render_script(output_path, frame, animation):
    """Generate bpy script without rendering."""
    sess = get_session()
    script = render_mod.generate_bpy_script(
        sess.get_project(), output_path, frame=frame, animation=animation,
    )
    click.echo(script)


# ── Session Commands ────────────────────────────────────────────
@cli.group()
def session():
    """Session management commands."""
    pass


@session.command("status")
@handle_error
def session_status():
    """Show session status."""
    sess = get_session()
    output(sess.status())


@session.command("undo")
@handle_error
def session_undo():
    """Undo the last operation."""
    sess = get_session()
    desc = sess.undo()
    output({"undone": desc}, f"Undone: {desc}")


@session.command("redo")
@handle_error
def session_redo():
    """Redo the last undone operation."""
    sess = get_session()
    desc = sess.redo()
    output({"redone": desc}, f"Redone: {desc}")


@session.command("history")
@handle_error
def session_history():
    """Show undo history."""
    sess = get_session()
    history = sess.list_history()
    output(history, "Undo history:")


# ── REPL ────────────────────────────────────────────────────────
@cli.command()
@click.option("--project", "project_path", type=str, default=None)
@handle_error
def repl(project_path):
    """Start interactive REPL session."""
    from cli_anything.blender.utils.repl_skin import ReplSkin

    global _repl_mode
    _repl_mode = True

    skin = ReplSkin("blender", version="1.0.0")

    if project_path:
        sess = get_session()
        proj = scene_mod.open_scene(project_path)
        sess.set_project(proj, project_path)

    skin.print_banner()

    pt_session = skin.create_prompt_session()

    _repl_commands = {
        "scene":       "new|open|save|info|profiles|json",
        "object":      "add|add-text|remove|duplicate|transform|set|list|get",
        "material":    "create|assign|set|list|get",
        "modifier":    "list-available|info|add|remove|set|list",
        "camera":      "add|set|set-active|list|create|dolly|orbit|pan|zoom|rack-focus|crane|follow-path|shake",
        "shape":       "rectangle|ellipse|polygon|star|morph|trim-path|offset-path|repeater",
        "particles":   "emit-object|emit-point|emit-text|force-field|preset-confetti|preset-sparks|preset-disintegrate|preset-data-stream",
        "compositor":  "glow|color-grade|chromatic-aberration|lens-distortion|vignette|film-grain|motion-blur|depth-of-field|bloom|sharpen|apply-chain",
        "light":       "add|set|list",
        "animation":   "keyframe|remove-keyframe|frame-range|fps|list-keyframes",
        "render":      "settings|info|presets|execute|script",
        "session":     "status|undo|redo|history",
        "help":        "show this help",
        "quit":        "exit REPL",
    }

    while True:
        try:
            sess = get_session()
            project_name = ""
            modified = False
            if sess.has_project():
                if sess.project_path:
                    project_name = os.path.basename(sess.project_path)
                else:
                    info = sess.get_project()
                    project_name = info.get("scene", {}).get("name", info.get("name", ""))
                modified = sess._modified

            line = skin.get_input(pt_session, project_name=project_name, modified=modified).strip()
            if not line:
                continue
            if line.lower() in ("quit", "exit", "q"):
                skin.print_goodbye()
                break
            if line.lower() == "help":
                skin.help(_repl_commands)
                continue

            # Parse and execute command
            args = line.split()
            try:
                cli.main(args, standalone_mode=False)
            except SystemExit:
                pass
            except click.exceptions.UsageError as e:
                skin.warning(f"Usage error: {e}")
            except Exception as e:
                skin.error(str(e))

        except (EOFError, KeyboardInterrupt):
            skin.print_goodbye()
            break

    _repl_mode = False


# ── Entry Point ─────────────────────────────────────────────────
def main():
    cli()


if __name__ == "__main__":
    main()
