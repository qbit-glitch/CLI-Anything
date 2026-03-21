"""Blender CLI - Node compositor for post-processing effects.

Generates bpy Python script strings that build a compositor node tree.

Each effect function:
1. Enables scene.use_nodes = True
2. Gets scene.node_tree
3. Clears all default links
4. Creates effect nodes with the specified settings
5. Links: Render Layers → effect chain → Composite output

apply_chain() chains multiple effects in sequence by threading the
output of each effect into the next one's input.

All functions return a list of bpy script lines.

Supported effects:
- glow              — Glare node (FOG_GLOW)
- color_grade       — Color Balance + Hue Saturation Value nodes
- chromatic_aberration — Lens Distortion node
- lens_distortion   — Lens Distortion node
- vignette          — Ellipse Mask + Mix nodes
- film_grain        — Noise Texture + Mix node
- motion_blur       — Vector Blur node
- depth_of_field    — Defocus node
- bloom             — Glare node (BLOOM / GHOSTS)
- sharpen           — Filter node (SHARPEN)
- apply_chain       — chain multiple effects in sequence
"""

import sys
import os
from typing import Dict, Any, List, Optional

# compositor.py lives at: blender/agent-harness/cli_anything/blender/core/compositor.py
# shared/ lives at:       <project-root>/shared/
# 5 levels of ".." bring us from core/ to the project root.
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "shared"),
)
# (No motion_math needed for static compositor — retained for future keyframe use.)


# ── Internal helpers ─────────────────────────────────────────────────────────


def _compositor_header(scene_var: str = "scene") -> List[str]:
    """Return the standard compositor setup preamble."""
    return [
        "import bpy",
        f"{scene_var} = bpy.context.scene",
        f"{scene_var}.use_nodes = True",
        f"tree = {scene_var}.node_tree",
        "nodes = tree.nodes",
        "links = tree.links",
        "# Clear existing nodes",
        "nodes.clear()",
        "# Render Layers node",
        "rl = nodes.new('CompositorNodeRLayers')",
        "rl.location = (-400, 0)",
        "# Composite output node",
        "comp = nodes.new('CompositorNodeComposite')",
        "comp.location = (600, 0)",
    ]


def _link_to_composite(effect_node_var: str, output_socket: int = 0) -> List[str]:
    """Link the effect node's primary output to the Composite node."""
    return [
        f"links.new({effect_node_var}.outputs[{output_socket}], comp.inputs[0])",
    ]


def _link_rl_to_node(effect_node_var: str, input_socket: int = 0) -> List[str]:
    """Link Render Layers image output to an effect node input."""
    return [
        f"links.new(rl.outputs[0], {effect_node_var}.inputs[{input_socket}])",
    ]


# ── Effect functions ─────────────────────────────────────────────────────────


def glow(
    session,
    threshold: float = 0.5,
    intensity: float = 1.0,
    size: int = 9,
    quality: str = "MEDIUM",
) -> List[str]:
    """Add a FOG_GLOW glare effect to the compositor.

    Args:
        session: Active Session object.
        threshold: Brightness threshold above which glow applies (0.0–1.0).
        intensity: Glow intensity (mix strength).
        size: Quality/radius of glow (8 levels, Blender glare size 8–9).
        quality: 'LOW', 'MEDIUM', or 'HIGH'.

    Returns:
        List of bpy script lines.
    """
    lines = _compositor_header()
    lines += [
        f"# Glow (FOG_GLOW) — threshold={threshold} intensity={intensity}",
        "glare = nodes.new('CompositorNodeGlare')",
        "glare.location = (0, 0)",
        "glare.glare_type = 'FOG_GLOW'",
        f"glare.threshold = {threshold}",
        f"glare.quality = '{quality}'",
        f"glare.size = {size}",
        f"glare.mix = {intensity - 1.0:.4f}",  # bpy: mix=-1→no glow, 0→blend, 1→full
    ]
    lines += _link_rl_to_node("glare")
    lines += _link_to_composite("glare")
    return lines


def color_grade(
    session,
    lift: Optional[List[float]] = None,
    gamma: Optional[List[float]] = None,
    gain: Optional[List[float]] = None,
    saturation: float = 1.0,
) -> List[str]:
    """Add Color Balance + Hue Saturation nodes for color grading.

    Args:
        session: Active Session object.
        lift:  [r, g, b] lift (shadows) values (default [1, 1, 1]).
        gamma: [r, g, b] gamma (midtones) values (default [1, 1, 1]).
        gain:  [r, g, b] gain (highlights) values (default [1, 1, 1]).
        saturation: Global saturation multiplier (1.0 = unchanged).

    Returns:
        List of bpy script lines.
    """
    lift_v  = list(lift)  if lift  is not None else [1.0, 1.0, 1.0]
    gamma_v = list(gamma) if gamma is not None else [1.0, 1.0, 1.0]
    gain_v  = list(gain)  if gain  is not None else [1.0, 1.0, 1.0]

    lines = _compositor_header()
    lines += [
        "# Color Balance node",
        "cb = nodes.new('CompositorNodeColorBalance')",
        "cb.location = (-100, 0)",
        "cb.correction_method = 'LIFT_GAMMA_GAIN'",
        f"cb.lift = ({lift_v[0]}, {lift_v[1]}, {lift_v[2]}, 1.0)",
        f"cb.gamma = ({gamma_v[0]}, {gamma_v[1]}, {gamma_v[2]}, 1.0)",
        f"cb.gain = ({gain_v[0]}, {gain_v[1]}, {gain_v[2]}, 1.0)",
        "# Hue Saturation Value node",
        "hue_sat = nodes.new('CompositorNodeHueSat')",
        "hue_sat.location = (200, 0)",
        "hue_sat.inputs['Hue'].default_value = 0.5",
        f"hue_sat.inputs['Saturation'].default_value = {saturation}",
        "hue_sat.inputs['Value'].default_value = 1.0",
    ]
    lines += _link_rl_to_node("cb")
    lines += [
        "links.new(cb.outputs[0], hue_sat.inputs['Image'])",
    ]
    lines += _link_to_composite("hue_sat")
    return lines


def chromatic_aberration(
    session,
    dispersion: float = 0.01,
) -> List[str]:
    """Add chromatic aberration via the Lens Distortion node.

    Args:
        session: Active Session object.
        dispersion: Dispersion amount (0.0–1.0; small values ≈ 0.01 look natural).

    Returns:
        List of bpy script lines.
    """
    lines = _compositor_header()
    lines += [
        f"# Chromatic Aberration (Lens Distortion) — dispersion={dispersion}",
        "lens_dist = nodes.new('CompositorNodeLensdist')",
        "lens_dist.location = (0, 0)",
        "lens_dist.use_fit = True",
        "lens_dist.use_jitter = False",
        f"lens_dist.inputs['Dispersion'].default_value = {dispersion}",
        "lens_dist.inputs['Distort'].default_value = 0.0",
    ]
    lines += _link_rl_to_node("lens_dist")
    lines += _link_to_composite("lens_dist")
    return lines


def lens_distortion(
    session,
    distortion: float = 0.1,
    dispersion: float = 0.0,
) -> List[str]:
    """Add barrel/pin-cushion lens distortion.

    Args:
        session: Active Session object.
        distortion: Distortion amount (-1.0 pin-cushion → 1.0 barrel).
        dispersion: Chromatic dispersion amount (0.0 = none).

    Returns:
        List of bpy script lines.
    """
    lines = _compositor_header()
    lines += [
        f"# Lens Distortion — distortion={distortion} dispersion={dispersion}",
        "lens_dist = nodes.new('CompositorNodeLensdist')",
        "lens_dist.location = (0, 0)",
        "lens_dist.use_fit = True",
        "lens_dist.use_jitter = False",
        f"lens_dist.inputs['Distort'].default_value = {distortion}",
        f"lens_dist.inputs['Dispersion'].default_value = {dispersion}",
    ]
    lines += _link_rl_to_node("lens_dist")
    lines += _link_to_composite("lens_dist")
    return lines


def vignette(
    session,
    intensity: float = 0.5,
    softness: float = 0.3,
) -> List[str]:
    """Add vignette effect using Ellipse Mask + Mix nodes.

    The ellipse mask is inverted and blended over the image to darken edges.

    Args:
        session: Active Session object.
        intensity: Vignette darkness (0.0 = none, 1.0 = full black edges).
        softness: Softness / falloff of the vignette edge (0.0–1.0).

    Returns:
        List of bpy script lines.
    """
    lines = _compositor_header()
    lines += [
        f"# Vignette — intensity={intensity} softness={softness}",
        "ellipse = nodes.new('CompositorNodeEllipseMask')",
        "ellipse.location = (-200, -200)",
        "ellipse.width = 1.0",
        "ellipse.height = 0.8",
        f"ellipse.mask_type = 'ADD'",
        "# Blur the mask for soft edges",
        "blur = nodes.new('CompositorNodeBlur')",
        "blur.location = (0, -200)",
        "blur.filter_type = 'GAUSS'",
        f"blur.size_x = {int(softness * 100)}",
        f"blur.size_y = {int(softness * 100)}",
        "# Invert mask (bright centre, dark edges → dark centre after invert)",
        "invert = nodes.new('CompositorNodeInvert')",
        "invert.location = (200, -200)",
        "# Mix node: multiply image by inverted mask",
        "mix = nodes.new('CompositorNodeMixRGB')",
        "mix.location = (400, 0)",
        "mix.blend_type = 'MULTIPLY'",
        f"mix.inputs[0].default_value = {intensity}",
        "links.new(ellipse.outputs[0], blur.inputs[0])",
        "links.new(blur.outputs[0], invert.inputs[1])",
    ]
    lines += _link_rl_to_node("mix", input_socket=1)
    lines += [
        "links.new(invert.outputs[0], mix.inputs[2])",
    ]
    lines += _link_to_composite("mix")
    return lines


def film_grain(
    session,
    intensity: float = 0.1,
    size: float = 1.0,
) -> List[str]:
    """Add film grain via a Noise Texture + Mix node.

    Args:
        session: Active Session object.
        intensity: Grain visibility (0.0–1.0 mix factor).
        size: Noise texture scale (higher = coarser grain).

    Returns:
        List of bpy script lines.
    """
    lines = _compositor_header()
    lines += [
        f"# Film Grain — intensity={intensity} size={size}",
        "noise = nodes.new('CompositorNodeTexture')",
        "noise.location = (-200, -200)",
        "# Use a noise texture for grain",
        "grain_tex = bpy.data.textures.new(name='FilmGrain', type='NOISE')",
        f"grain_tex.noise_scale = {size}",
        "noise.texture = grain_tex",
        "# Mix grain over image",
        "mix = nodes.new('CompositorNodeMixRGB')",
        "mix.location = (200, 0)",
        "mix.blend_type = 'OVERLAY'",
        f"mix.inputs[0].default_value = {intensity}",
    ]
    lines += _link_rl_to_node("mix", input_socket=1)
    lines += [
        "links.new(noise.outputs[1], mix.inputs[2])",
    ]
    lines += _link_to_composite("mix")
    return lines


def motion_blur(
    session,
    samples: int = 32,
    speed_factor: float = 1.0,
) -> List[str]:
    """Add motion blur via the Vector Blur node.

    Requires the render to output a Vector pass; this is enabled by
    setting scene.view_layers[0].use_pass_vector = True.

    Args:
        session: Active Session object.
        samples: Number of blur samples (higher = smoother but slower).
        speed_factor: Scale factor applied to the motion vector magnitude.

    Returns:
        List of bpy script lines.
    """
    lines = _compositor_header()
    lines += [
        f"# Motion Blur (Vector Blur) — samples={samples} speed={speed_factor}",
        "# Enable Vector pass",
        "bpy.context.scene.view_layers[0].use_pass_vector = True",
        "vec_blur = nodes.new('CompositorNodeVecBlur')",
        "vec_blur.location = (0, 0)",
        f"vec_blur.samples = {samples}",
        f"vec_blur.factor = {speed_factor}",
        "vec_blur.use_curved = True",
    ]
    lines += _link_rl_to_node("vec_blur")
    lines += [
        "# Connect speed (Vector pass) to vec_blur",
        "links.new(rl.outputs['Vector'], vec_blur.inputs['Speed'])",
    ]
    lines += _link_to_composite("vec_blur")
    return lines


def depth_of_field(
    session,
    f_stop: float = 2.8,
    max_blur: float = 16.0,
) -> List[str]:
    """Add depth of field blur via the Defocus node.

    Requires a depth pass (Z buffer).

    Args:
        session: Active Session object.
        f_stop: Aperture f-stop (lower = shallower DoF, more blur).
        max_blur: Maximum blur radius in pixels.

    Returns:
        List of bpy script lines.
    """
    lines = _compositor_header()
    lines += [
        f"# Depth of Field (Defocus) — f_stop={f_stop} max_blur={max_blur}",
        "defocus = nodes.new('CompositorNodeDefocus')",
        "defocus.location = (0, 0)",
        f"defocus.f_stop = {f_stop}",
        f"defocus.blur_max = {max_blur}",
        "defocus.use_zbuffer = True",
        "defocus.use_preview = False",
    ]
    lines += _link_rl_to_node("defocus")
    lines += [
        "# Connect Z buffer to defocus depth input",
        "links.new(rl.outputs['Depth'], defocus.inputs[1])",
    ]
    lines += _link_to_composite("defocus")
    return lines


def bloom(
    session,
    threshold: float = 0.8,
    radius: int = 9,
    intensity: float = 1.0,
) -> List[str]:
    """Add bloom effect via the Glare node (GHOSTS / STREAKS type).

    Blender's Glare node does not have a dedicated 'BLOOM' type; we use
    'GHOSTS' which produces a wide diffuse bloom-like halo.

    Args:
        session: Active Session object.
        threshold: Brightness threshold for bloom (0.0–1.0).
        radius: Bloom radius / size (Blender glare size 6–9).
        intensity: Bloom intensity (mix factor).

    Returns:
        List of bpy script lines.
    """
    lines = _compositor_header()
    lines += [
        f"# Bloom (Glare/GHOSTS) — threshold={threshold} radius={radius} intensity={intensity}",
        "bloom_node = nodes.new('CompositorNodeGlare')",
        "bloom_node.location = (0, 0)",
        "bloom_node.glare_type = 'GHOSTS'",
        f"bloom_node.threshold = {threshold}",
        f"bloom_node.size = {radius}",
        f"bloom_node.mix = {intensity - 1.0:.4f}",
        "bloom_node.quality = 'HIGH'",
    ]
    lines += _link_rl_to_node("bloom_node")
    lines += _link_to_composite("bloom_node")
    return lines


def sharpen(
    session,
    factor: float = 0.5,
) -> List[str]:
    """Add sharpening via a Filter node (SHARPEN type).

    Args:
        session: Active Session object.
        factor: Sharpen strength (mix factor between original and sharpened).

    Returns:
        List of bpy script lines.
    """
    lines = _compositor_header()
    lines += [
        f"# Sharpen (Filter node) — factor={factor}",
        "sharpen_filter = nodes.new('CompositorNodeFilter')",
        "sharpen_filter.location = (-100, 0)",
        "sharpen_filter.filter_type = 'SHARPEN'",
        "# Mix node: blend original with sharpened",
        "mix = nodes.new('CompositorNodeMixRGB')",
        "mix.location = (200, 0)",
        "mix.blend_type = 'MIX'",
        f"mix.inputs[0].default_value = {factor}",
    ]
    lines += _link_rl_to_node("sharpen_filter")
    lines += _link_rl_to_node("mix", input_socket=1)
    lines += [
        "links.new(sharpen_filter.outputs[0], mix.inputs[2])",
    ]
    lines += _link_to_composite("mix")
    return lines


# ── apply_chain ───────────────────────────────────────────────────────────────


def apply_chain(
    session,
    effects_list: List[Dict[str, Any]],
) -> List[str]:
    """Chain multiple compositor effects in sequence.

    Each effect in *effects_list* is a dict:
        {
            "type": "<effect_name>",
            "<param>": <value>,
            ...
        }

    Supported types: glow, color_grade, chromatic_aberration,
    lens_distortion, vignette, film_grain, motion_blur, depth_of_field,
    bloom, sharpen.

    The chain is assembled as:
        Render Layers → effect_0 → effect_1 → ... → Composite

    This function generates a SINGLE compositor setup for the whole chain:
    nodes are re-used from individual effect scripts with renamed variables.

    Args:
        session: Active Session object.
        effects_list: Ordered list of effect dicts.

    Returns:
        List of bpy script lines implementing the full chain.
    """
    if not effects_list:
        raise ValueError("effects_list must contain at least one effect")

    _EFFECT_MAP = {
        "glow": glow,
        "color_grade": color_grade,
        "chromatic_aberration": chromatic_aberration,
        "lens_distortion": lens_distortion,
        "vignette": vignette,
        "film_grain": film_grain,
        "motion_blur": motion_blur,
        "depth_of_field": depth_of_field,
        "bloom": bloom,
        "sharpen": sharpen,
    }

    for eff in effects_list:
        eff_type = eff.get("type", "")
        if eff_type not in _EFFECT_MAP:
            raise ValueError(
                f"Unknown effect type '{eff_type}'. Valid: {sorted(_EFFECT_MAP.keys())}"
            )

    # Build chain: generate each effect's node tree individually, then assemble.
    # For the chain script we emit one header, then one block per effect.
    lines = _compositor_header()
    lines += [
        "# === Effect chain ===",
        f"# {len(effects_list)} effect(s): "
        + " → ".join(e.get("type", "?") for e in effects_list),
    ]

    # We build a per-effect node by inserting individual effect node creation
    # lines (without the header/composite links) and threading outputs.
    # Each effect generates a node referenced by a unique variable name.
    effect_node_vars = []

    for idx, eff in enumerate(effects_list):
        eff_type = eff.get("type", "")
        params = {k: v for k, v in eff.items() if k != "type"}
        node_var = f"effect_{idx}"

        lines += [f"# Effect {idx}: {eff_type}"]

        # For each effect we emit a simplified inline node setup
        # rather than calling the full function (which re-emits the header).
        if eff_type == "glow":
            threshold = params.get("threshold", 0.5)
            intensity = params.get("intensity", 1.0)
            size      = params.get("size", 9)
            quality   = params.get("quality", "MEDIUM")
            lines += [
                f"{node_var} = nodes.new('CompositorNodeGlare')",
                f"{node_var}.location = ({idx * 200}, 0)",
                f"{node_var}.glare_type = 'FOG_GLOW'",
                f"{node_var}.threshold = {threshold}",
                f"{node_var}.quality = '{quality}'",
                f"{node_var}.size = {size}",
                f"{node_var}.mix = {intensity - 1.0:.4f}",
            ]

        elif eff_type == "color_grade":
            lift_v  = list(params.get("lift",  [1.0, 1.0, 1.0]))
            gamma_v = list(params.get("gamma", [1.0, 1.0, 1.0]))
            gain_v  = list(params.get("gain",  [1.0, 1.0, 1.0]))
            sat     = params.get("saturation", 1.0)
            cb_var  = f"cb_{idx}"
            lines += [
                f"{cb_var} = nodes.new('CompositorNodeColorBalance')",
                f"{cb_var}.location = ({idx * 200 - 100}, 0)",
                f"{cb_var}.correction_method = 'LIFT_GAMMA_GAIN'",
                f"{cb_var}.lift = ({lift_v[0]}, {lift_v[1]}, {lift_v[2]}, 1.0)",
                f"{cb_var}.gamma = ({gamma_v[0]}, {gamma_v[1]}, {gamma_v[2]}, 1.0)",
                f"{cb_var}.gain = ({gain_v[0]}, {gain_v[1]}, {gain_v[2]}, 1.0)",
                f"{node_var} = nodes.new('CompositorNodeHueSat')",
                f"{node_var}.location = ({idx * 200 + 100}, 0)",
                f"{node_var}.inputs['Saturation'].default_value = {sat}",
            ]
            # Internal link: cb → hue_sat
            effect_node_vars.append(cb_var)
            lines += [f"links.new({cb_var}.outputs[0], {node_var}.inputs['Image'])"]

        elif eff_type in ("chromatic_aberration", "lens_distortion"):
            dist = params.get("distortion", 0.0 if eff_type == "chromatic_aberration" else 0.1)
            disp = params.get("dispersion", params.get("dispersion", 0.01))
            lines += [
                f"{node_var} = nodes.new('CompositorNodeLensdist')",
                f"{node_var}.location = ({idx * 200}, 0)",
                f"{node_var}.use_fit = True",
                f"{node_var}.inputs['Distort'].default_value = {dist}",
                f"{node_var}.inputs['Dispersion'].default_value = {disp}",
            ]

        elif eff_type == "vignette":
            intensity = params.get("intensity", 0.5)
            softness  = params.get("softness", 0.3)
            ell_var   = f"ell_{idx}"
            blur_var  = f"blur_{idx}"
            inv_var   = f"inv_{idx}"
            lines += [
                f"{ell_var} = nodes.new('CompositorNodeEllipseMask')",
                f"{blur_var} = nodes.new('CompositorNodeBlur')",
                f"{blur_var}.size_x = {int(softness * 100)}",
                f"{blur_var}.size_y = {int(softness * 100)}",
                f"{inv_var} = nodes.new('CompositorNodeInvert')",
                f"{node_var} = nodes.new('CompositorNodeMixRGB')",
                f"{node_var}.location = ({idx * 200 + 200}, 0)",
                f"{node_var}.blend_type = 'MULTIPLY'",
                f"{node_var}.inputs[0].default_value = {intensity}",
                f"links.new({ell_var}.outputs[0], {blur_var}.inputs[0])",
                f"links.new({blur_var}.outputs[0], {inv_var}.inputs[1])",
                f"links.new({inv_var}.outputs[0], {node_var}.inputs[2])",
            ]

        elif eff_type == "film_grain":
            intensity = params.get("intensity", 0.1)
            size      = params.get("size", 1.0)
            lines += [
                f"grain_tex_{idx} = bpy.data.textures.new(name='FilmGrain{idx}', type='NOISE')",
                f"grain_tex_{idx}.noise_scale = {size}",
                f"noise_{idx} = nodes.new('CompositorNodeTexture')",
                f"noise_{idx}.texture = grain_tex_{idx}",
                f"{node_var} = nodes.new('CompositorNodeMixRGB')",
                f"{node_var}.location = ({idx * 200 + 200}, 0)",
                f"{node_var}.blend_type = 'OVERLAY'",
                f"{node_var}.inputs[0].default_value = {intensity}",
                f"links.new(noise_{idx}.outputs[1], {node_var}.inputs[2])",
            ]

        elif eff_type == "motion_blur":
            samples      = params.get("samples", 32)
            speed_factor = params.get("speed_factor", 1.0)
            lines += [
                "bpy.context.scene.view_layers[0].use_pass_vector = True",
                f"{node_var} = nodes.new('CompositorNodeVecBlur')",
                f"{node_var}.location = ({idx * 200}, 0)",
                f"{node_var}.samples = {samples}",
                f"{node_var}.factor = {speed_factor}",
                f"{node_var}.use_curved = True",
                f"links.new(rl.outputs['Vector'], {node_var}.inputs['Speed'])",
            ]

        elif eff_type == "depth_of_field":
            f_stop   = params.get("f_stop", 2.8)
            max_blur = params.get("max_blur", 16.0)
            lines += [
                f"{node_var} = nodes.new('CompositorNodeDefocus')",
                f"{node_var}.location = ({idx * 200}, 0)",
                f"{node_var}.f_stop = {f_stop}",
                f"{node_var}.blur_max = {max_blur}",
                f"{node_var}.use_zbuffer = True",
                f"links.new(rl.outputs['Depth'], {node_var}.inputs[1])",
            ]

        elif eff_type == "bloom":
            threshold = params.get("threshold", 0.8)
            radius    = params.get("radius", 9)
            intensity = params.get("intensity", 1.0)
            lines += [
                f"{node_var} = nodes.new('CompositorNodeGlare')",
                f"{node_var}.location = ({idx * 200}, 0)",
                f"{node_var}.glare_type = 'GHOSTS'",
                f"{node_var}.threshold = {threshold}",
                f"{node_var}.size = {radius}",
                f"{node_var}.mix = {intensity - 1.0:.4f}",
                f"{node_var}.quality = 'HIGH'",
            ]

        elif eff_type == "sharpen":
            factor    = params.get("factor", 0.5)
            sf_var    = f"sf_{idx}"
            lines += [
                f"{sf_var} = nodes.new('CompositorNodeFilter')",
                f"{sf_var}.location = ({idx * 200 - 100}, 0)",
                f"{sf_var}.filter_type = 'SHARPEN'",
                f"{node_var} = nodes.new('CompositorNodeMixRGB')",
                f"{node_var}.location = ({idx * 200 + 100}, 0)",
                f"{node_var}.blend_type = 'MIX'",
                f"{node_var}.inputs[0].default_value = {factor}",
                f"links.new({sf_var}.outputs[0], {node_var}.inputs[2])",
            ]

        effect_node_vars.append(node_var)

    # Thread the chain: rl → effect_0 → effect_1 → ... → comp
    if effect_node_vars:
        # First node from rl
        lines.append(f"links.new(rl.outputs[0], {effect_node_vars[0]}.inputs[0])")
        # Each subsequent node from previous output
        for i in range(1, len(effect_node_vars)):
            prev = effect_node_vars[i - 1]
            curr = effect_node_vars[i]
            lines.append(f"links.new({prev}.outputs[0], {curr}.inputs[0])")
        # Final to composite
        lines.append(f"links.new({effect_node_vars[-1]}.outputs[0], comp.inputs[0])")

    lines.append("# apply_chain complete")
    return lines
