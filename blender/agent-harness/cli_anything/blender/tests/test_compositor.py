"""Tests for blender/core/compositor.py

Verifies that each compositor function generates bpy script lines
containing the correct node type names and settings.
A lightweight MockSession is used so tests run without Blender.
"""

import sys
import os
import unittest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", ".."),
)

from cli_anything.blender.core.compositor import (
    glow,
    color_grade,
    chromatic_aberration,
    lens_distortion,
    vignette,
    film_grain,
    motion_blur,
    depth_of_field,
    bloom,
    sharpen,
    apply_chain,
)


# ── Mock Session ─────────────────────────────────────────────────────────────


class MockSession:
    def __init__(self):
        self._project = {}

    def get_project(self):
        return self._project


# ── Helpers ──────────────────────────────────────────────────────────────────


def lines_contain(lines, *fragments):
    joined = "\n".join(lines)
    return all(frag in joined for frag in fragments)


def line_count_containing(lines, fragment):
    return sum(1 for l in lines if fragment in l)


# ── TestCompositorCommon ─────────────────────────────────────────────────────


class TestCompositorCommon(unittest.TestCase):
    """Tests that all compositor functions share the same preamble."""

    def setUp(self):
        self.sess = MockSession()

    def _check_preamble(self, func, *args, **kwargs):
        lines = func(self.sess, *args, **kwargs)
        self.assertTrue(lines_contain(lines, "import bpy"), f"Missing 'import bpy' in {func.__name__}")
        self.assertTrue(lines_contain(lines, "use_nodes = True"), f"Missing use_nodes in {func.__name__}")
        self.assertTrue(lines_contain(lines, "node_tree"), f"Missing node_tree in {func.__name__}")
        self.assertTrue(lines_contain(lines, "nodes.clear()"), f"Missing nodes.clear() in {func.__name__}")
        self.assertTrue(lines_contain(lines, "CompositorNodeRLayers"), f"Missing RLayers in {func.__name__}")
        self.assertTrue(lines_contain(lines, "CompositorNodeComposite"), f"Missing Composite in {func.__name__}")

    def test_glow_preamble(self):
        self._check_preamble(glow)

    def test_color_grade_preamble(self):
        self._check_preamble(color_grade)

    def test_chromatic_aberration_preamble(self):
        self._check_preamble(chromatic_aberration)

    def test_lens_distortion_preamble(self):
        self._check_preamble(lens_distortion)

    def test_vignette_preamble(self):
        self._check_preamble(vignette)

    def test_film_grain_preamble(self):
        self._check_preamble(film_grain)

    def test_motion_blur_preamble(self):
        self._check_preamble(motion_blur)

    def test_depth_of_field_preamble(self):
        self._check_preamble(depth_of_field)

    def test_bloom_preamble(self):
        self._check_preamble(bloom)

    def test_sharpen_preamble(self):
        self._check_preamble(sharpen)


# ── TestGlow ─────────────────────────────────────────────────────────────────


class TestGlow(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = glow(self.sess)
        self.assertIsInstance(lines, list)

    def test_glare_node_created(self):
        lines = glow(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeGlare"))

    def test_fog_glow_type(self):
        lines = glow(self.sess)
        self.assertTrue(lines_contain(lines, "glare_type = 'FOG_GLOW'"))

    def test_threshold_applied(self):
        lines = glow(self.sess, threshold=0.7)
        self.assertTrue(lines_contain(lines, "threshold = 0.7"))

    def test_size_applied(self):
        lines = glow(self.sess, size=7)
        self.assertTrue(lines_contain(lines, "size = 7"))

    def test_quality_applied(self):
        lines = glow(self.sess, quality="HIGH")
        self.assertTrue(lines_contain(lines, "quality = 'HIGH'"))

    def test_linked_to_composite(self):
        lines = glow(self.sess)
        self.assertTrue(lines_contain(lines, "comp.inputs[0]"))

    def test_linked_from_rl(self):
        lines = glow(self.sess)
        self.assertTrue(lines_contain(lines, "rl.outputs[0]"))


# ── TestColorGrade ───────────────────────────────────────────────────────────


class TestColorGrade(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = color_grade(self.sess)
        self.assertIsInstance(lines, list)

    def test_color_balance_node(self):
        lines = color_grade(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeColorBalance"))

    def test_hue_saturation_node(self):
        lines = color_grade(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeHueSat"))

    def test_lift_applied(self):
        lines = color_grade(self.sess, lift=[0.9, 0.9, 1.1])
        self.assertTrue(lines_contain(lines, "0.9, 0.9, 1.1"))

    def test_gamma_applied(self):
        lines = color_grade(self.sess, gamma=[1.0, 0.95, 1.05])
        self.assertTrue(lines_contain(lines, "1.0, 0.95, 1.05"))

    def test_gain_applied(self):
        lines = color_grade(self.sess, gain=[1.1, 1.0, 0.9])
        self.assertTrue(lines_contain(lines, "1.1, 1.0, 0.9"))

    def test_saturation_applied(self):
        lines = color_grade(self.sess, saturation=1.3)
        self.assertTrue(lines_contain(lines, "Saturation'].default_value = 1.3"))

    def test_lift_gamma_gain_method(self):
        lines = color_grade(self.sess)
        self.assertTrue(lines_contain(lines, "LIFT_GAMMA_GAIN"))

    def test_linked_to_composite(self):
        lines = color_grade(self.sess)
        self.assertTrue(lines_contain(lines, "comp.inputs[0]"))


# ── TestChromaticAberration ───────────────────────────────────────────────────


class TestChromaticAberration(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = chromatic_aberration(self.sess)
        self.assertIsInstance(lines, list)

    def test_lens_dist_node(self):
        lines = chromatic_aberration(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeLensdist"))

    def test_dispersion_set(self):
        lines = chromatic_aberration(self.sess, dispersion=0.05)
        self.assertTrue(lines_contain(lines, "Dispersion'].default_value = 0.05"))

    def test_distortion_zero(self):
        lines = chromatic_aberration(self.sess)
        self.assertTrue(lines_contain(lines, "Distort'].default_value = 0.0"))

    def test_use_fit(self):
        lines = chromatic_aberration(self.sess)
        self.assertTrue(lines_contain(lines, "use_fit = True"))

    def test_linked_to_composite(self):
        lines = chromatic_aberration(self.sess)
        self.assertTrue(lines_contain(lines, "comp.inputs[0]"))


# ── TestLensDistortion ───────────────────────────────────────────────────────


class TestLensDistortion(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = lens_distortion(self.sess)
        self.assertIsInstance(lines, list)

    def test_lens_dist_node(self):
        lines = lens_distortion(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeLensdist"))

    def test_distortion_applied(self):
        lines = lens_distortion(self.sess, distortion=0.3)
        self.assertTrue(lines_contain(lines, "Distort'].default_value = 0.3"))

    def test_dispersion_applied(self):
        lines = lens_distortion(self.sess, dispersion=0.02)
        self.assertTrue(lines_contain(lines, "Dispersion'].default_value = 0.02"))

    def test_linked_to_composite(self):
        lines = lens_distortion(self.sess)
        self.assertTrue(lines_contain(lines, "comp.inputs[0]"))


# ── TestVignette ─────────────────────────────────────────────────────────────


class TestVignette(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = vignette(self.sess)
        self.assertIsInstance(lines, list)

    def test_ellipse_mask_node(self):
        lines = vignette(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeEllipseMask"))

    def test_mix_node(self):
        lines = vignette(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeMixRGB"))

    def test_blur_node(self):
        lines = vignette(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeBlur"))

    def test_invert_node(self):
        lines = vignette(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeInvert"))

    def test_multiply_blend(self):
        lines = vignette(self.sess)
        self.assertTrue(lines_contain(lines, "MULTIPLY"))

    def test_intensity_applied(self):
        lines = vignette(self.sess, intensity=0.8)
        self.assertTrue(lines_contain(lines, "0.8"))

    def test_linked_to_composite(self):
        lines = vignette(self.sess)
        self.assertTrue(lines_contain(lines, "comp.inputs[0]"))


# ── TestFilmGrain ─────────────────────────────────────────────────────────────


class TestFilmGrain(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = film_grain(self.sess)
        self.assertIsInstance(lines, list)

    def test_texture_node(self):
        lines = film_grain(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeTexture"))

    def test_noise_texture_created(self):
        lines = film_grain(self.sess)
        self.assertTrue(lines_contain(lines, "type='NOISE'"))

    def test_mix_node(self):
        lines = film_grain(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeMixRGB"))

    def test_overlay_blend(self):
        lines = film_grain(self.sess)
        self.assertTrue(lines_contain(lines, "OVERLAY"))

    def test_intensity_applied(self):
        lines = film_grain(self.sess, intensity=0.2)
        self.assertTrue(lines_contain(lines, "0.2"))

    def test_size_applied(self):
        lines = film_grain(self.sess, size=2.0)
        self.assertTrue(lines_contain(lines, "noise_scale = 2.0"))

    def test_linked_to_composite(self):
        lines = film_grain(self.sess)
        self.assertTrue(lines_contain(lines, "comp.inputs[0]"))


# ── TestMotionBlur ────────────────────────────────────────────────────────────


class TestMotionBlur(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = motion_blur(self.sess)
        self.assertIsInstance(lines, list)

    def test_vec_blur_node(self):
        lines = motion_blur(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeVecBlur"))

    def test_samples_set(self):
        lines = motion_blur(self.sess, samples=64)
        self.assertTrue(lines_contain(lines, "vec_blur.samples = 64"))

    def test_factor_set(self):
        lines = motion_blur(self.sess, speed_factor=2.0)
        self.assertTrue(lines_contain(lines, "vec_blur.factor = 2.0"))

    def test_vector_pass_enabled(self):
        lines = motion_blur(self.sess)
        self.assertTrue(lines_contain(lines, "use_pass_vector = True"))

    def test_vector_linked(self):
        lines = motion_blur(self.sess)
        self.assertTrue(lines_contain(lines, "rl.outputs['Vector']"))

    def test_linked_to_composite(self):
        lines = motion_blur(self.sess)
        self.assertTrue(lines_contain(lines, "comp.inputs[0]"))


# ── TestDepthOfField ─────────────────────────────────────────────────────────


class TestDepthOfField(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = depth_of_field(self.sess)
        self.assertIsInstance(lines, list)

    def test_defocus_node(self):
        lines = depth_of_field(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeDefocus"))

    def test_f_stop_set(self):
        lines = depth_of_field(self.sess, f_stop=5.6)
        self.assertTrue(lines_contain(lines, "defocus.f_stop = 5.6"))

    def test_max_blur_set(self):
        lines = depth_of_field(self.sess, max_blur=32.0)
        self.assertTrue(lines_contain(lines, "defocus.blur_max = 32.0"))

    def test_zbuffer_used(self):
        lines = depth_of_field(self.sess)
        self.assertTrue(lines_contain(lines, "use_zbuffer = True"))

    def test_depth_pass_linked(self):
        lines = depth_of_field(self.sess)
        self.assertTrue(lines_contain(lines, "rl.outputs['Depth']"))

    def test_linked_to_composite(self):
        lines = depth_of_field(self.sess)
        self.assertTrue(lines_contain(lines, "comp.inputs[0]"))


# ── TestBloom ────────────────────────────────────────────────────────────────


class TestBloom(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = bloom(self.sess)
        self.assertIsInstance(lines, list)

    def test_glare_node_created(self):
        lines = bloom(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeGlare"))

    def test_ghosts_type(self):
        lines = bloom(self.sess)
        self.assertTrue(lines_contain(lines, "glare_type = 'GHOSTS'"))

    def test_threshold_applied(self):
        lines = bloom(self.sess, threshold=0.6)
        self.assertTrue(lines_contain(lines, "threshold = 0.6"))

    def test_radius_applied(self):
        lines = bloom(self.sess, radius=7)
        self.assertTrue(lines_contain(lines, "size = 7"))

    def test_linked_to_composite(self):
        lines = bloom(self.sess)
        self.assertTrue(lines_contain(lines, "comp.inputs[0]"))


# ── TestSharpen ───────────────────────────────────────────────────────────────


class TestSharpen(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        lines = sharpen(self.sess)
        self.assertIsInstance(lines, list)

    def test_filter_node_created(self):
        lines = sharpen(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeFilter"))

    def test_sharpen_filter_type(self):
        lines = sharpen(self.sess)
        self.assertTrue(lines_contain(lines, "filter_type = 'SHARPEN'"))

    def test_mix_node_present(self):
        lines = sharpen(self.sess)
        self.assertTrue(lines_contain(lines, "CompositorNodeMixRGB"))

    def test_factor_applied(self):
        lines = sharpen(self.sess, factor=0.8)
        self.assertTrue(lines_contain(lines, "0.8"))

    def test_linked_to_composite(self):
        lines = sharpen(self.sess)
        self.assertTrue(lines_contain(lines, "comp.inputs[0]"))


# ── TestApplyChain ────────────────────────────────────────────────────────────


class TestApplyChain(unittest.TestCase):

    def setUp(self):
        self.sess = MockSession()

    def test_returns_list(self):
        chain = [{"type": "glow", "threshold": 0.5}]
        lines = apply_chain(self.sess, chain)
        self.assertIsInstance(lines, list)

    def test_single_effect_glow(self):
        chain = [{"type": "glow"}]
        lines = apply_chain(self.sess, chain)
        self.assertTrue(lines_contain(lines, "CompositorNodeGlare"))

    def test_single_effect_color_grade(self):
        chain = [{"type": "color_grade", "saturation": 1.2}]
        lines = apply_chain(self.sess, chain)
        self.assertTrue(lines_contain(lines, "CompositorNodeColorBalance"))
        self.assertTrue(lines_contain(lines, "CompositorNodeHueSat"))

    def test_two_effect_chain(self):
        chain = [
            {"type": "glow", "threshold": 0.5},
            {"type": "sharpen", "factor": 0.3},
        ]
        lines = apply_chain(self.sess, chain)
        self.assertTrue(lines_contain(lines, "CompositorNodeGlare"))
        self.assertTrue(lines_contain(lines, "CompositorNodeFilter"))

    def test_three_effect_chain(self):
        chain = [
            {"type": "glow"},
            {"type": "vignette"},
            {"type": "film_grain"},
        ]
        lines = apply_chain(self.sess, chain)
        self.assertTrue(lines_contain(lines, "CompositorNodeGlare"))
        self.assertTrue(lines_contain(lines, "CompositorNodeEllipseMask"))
        self.assertTrue(lines_contain(lines, "CompositorNodeTexture"))

    def test_chain_links_between_effects(self):
        chain = [
            {"type": "glow"},
            {"type": "bloom"},
        ]
        lines = apply_chain(self.sess, chain)
        # There should be links threading effects together
        link_lines = [l for l in lines if "links.new" in l]
        self.assertGreater(len(link_lines), 2)

    def test_final_link_to_composite(self):
        chain = [{"type": "glow"}, {"type": "sharpen"}]
        lines = apply_chain(self.sess, chain)
        self.assertTrue(lines_contain(lines, "comp.inputs[0]"))

    def test_rl_linked_to_first_effect(self):
        chain = [{"type": "glow"}]
        lines = apply_chain(self.sess, chain)
        self.assertTrue(lines_contain(lines, "rl.outputs[0]"))

    def test_invalid_empty_chain(self):
        with self.assertRaises(ValueError):
            apply_chain(self.sess, [])

    def test_invalid_effect_type(self):
        with self.assertRaises(ValueError):
            apply_chain(self.sess, [{"type": "unknown_effect"}])

    def test_chain_comment_shows_effects(self):
        chain = [{"type": "glow"}, {"type": "bloom"}]
        lines = apply_chain(self.sess, chain)
        # Should mention both effect types somewhere
        self.assertTrue(lines_contain(lines, "glow"))
        self.assertTrue(lines_contain(lines, "bloom"))

    def test_chromatic_aberration_in_chain(self):
        chain = [{"type": "chromatic_aberration", "dispersion": 0.02}]
        lines = apply_chain(self.sess, chain)
        self.assertTrue(lines_contain(lines, "CompositorNodeLensdist"))

    def test_lens_distortion_in_chain(self):
        chain = [{"type": "lens_distortion", "distortion": 0.2}]
        lines = apply_chain(self.sess, chain)
        self.assertTrue(lines_contain(lines, "CompositorNodeLensdist"))

    def test_motion_blur_in_chain(self):
        chain = [{"type": "motion_blur", "samples": 16}]
        lines = apply_chain(self.sess, chain)
        self.assertTrue(lines_contain(lines, "CompositorNodeVecBlur"))

    def test_depth_of_field_in_chain(self):
        chain = [{"type": "depth_of_field", "f_stop": 4.0}]
        lines = apply_chain(self.sess, chain)
        self.assertTrue(lines_contain(lines, "CompositorNodeDefocus"))

    def test_all_ten_effects_chain(self):
        chain = [
            {"type": "glow"},
            {"type": "color_grade"},
            {"type": "chromatic_aberration"},
            {"type": "lens_distortion"},
            {"type": "vignette"},
            {"type": "film_grain"},
            {"type": "motion_blur"},
            {"type": "depth_of_field"},
            {"type": "bloom"},
            {"type": "sharpen"},
        ]
        lines = apply_chain(self.sess, chain)
        self.assertTrue(lines_contain(lines, "CompositorNodeGlare"))
        self.assertTrue(lines_contain(lines, "CompositorNodeColorBalance"))
        self.assertTrue(lines_contain(lines, "CompositorNodeLensdist"))
        self.assertTrue(lines_contain(lines, "CompositorNodeEllipseMask"))
        self.assertTrue(lines_contain(lines, "CompositorNodeTexture"))
        self.assertTrue(lines_contain(lines, "CompositorNodeVecBlur"))
        self.assertTrue(lines_contain(lines, "CompositorNodeDefocus"))
        self.assertTrue(lines_contain(lines, "CompositorNodeFilter"))
        self.assertTrue(lines_contain(lines, "comp.inputs[0]"))


# ── Entry Point ───────────────────────────────────────────────────────────────


if __name__ == "__main__":
    unittest.main()
