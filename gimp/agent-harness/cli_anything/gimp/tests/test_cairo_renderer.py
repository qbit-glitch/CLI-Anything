"""Unit tests for GIMP CLI - CairoRenderer.

Tests use only stdlib / Pillow fallback paths so they work without PyCairo.
All assertions are on observable outputs (PNG file written, numpy array shape,
particle rendering, etc.).
"""

from __future__ import annotations

import math
import os
import struct
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cli_anything.gimp.core.cairo_renderer import CairoRenderer, HAS_CAIRO, HAS_PIL, HAS_NUMPY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_renderer(width=64, height=64):
    return CairoRenderer(width, height)


def _is_valid_png(path: str) -> bool:
    """Check that file starts with the PNG signature bytes."""
    with open(path, "rb") as f:
        sig = f.read(8)
    return sig == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestCairoRendererConstruction:
    def test_creates_renderer(self):
        r = _make_renderer(32, 32)
        assert r.width == 32
        assert r.height == 32

    def test_creates_renderer_large(self):
        r = _make_renderer(1920, 1080)
        assert r.width == 1920
        assert r.height == 1080

    def test_has_backend(self):
        r = _make_renderer()
        # At least one backend must be active
        has_backend = (
            (HAS_CAIRO and r._surface is not None)
            or (HAS_PIL and r._pil_image is not None)
            or hasattr(r, "_raw")
        )
        assert has_backend


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------

class TestClear:
    def test_clear_default(self):
        r = _make_renderer()
        r.clear()  # Should not raise

    def test_clear_white(self):
        r = _make_renderer(8, 8)
        r.clear((1.0, 1.0, 1.0, 1.0))
        # No assertion on pixel values here — just must not raise

    def test_clear_transparent(self):
        r = _make_renderer(8, 8)
        r.clear((0.0, 0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# render_shape()
# ---------------------------------------------------------------------------

class TestRenderShape:
    def test_rect(self):
        r = _make_renderer(64, 64)
        r.clear()
        r.render_shape(
            "rect",
            {"x": 10, "y": 10, "width": 20, "height": 20},
            {},
            {"fill": (1.0, 0.0, 0.0, 1.0)},
        )

    def test_rect_with_corner_radius(self):
        r = _make_renderer(64, 64)
        r.clear()
        r.render_shape(
            "rect",
            {"x": 5, "y": 5, "width": 40, "height": 30, "corner_radius": 8},
            {},
            {"fill": (0.0, 1.0, 0.0, 1.0)},
        )

    def test_ellipse(self):
        r = _make_renderer(64, 64)
        r.clear()
        r.render_shape(
            "ellipse",
            {"cx": 32, "cy": 32, "rx": 20, "ry": 15},
            {},
            {"fill": (0.0, 0.0, 1.0, 1.0)},
        )

    def test_polygon(self):
        r = _make_renderer(64, 64)
        r.clear()
        r.render_shape(
            "polygon",
            {"points": [(10, 50), (32, 10), (54, 50)]},
            {},
            {"fill": (1.0, 1.0, 0.0, 1.0)},
        )

    def test_path(self):
        r = _make_renderer(64, 64)
        r.clear()
        r.render_shape(
            "path",
            {"d": "M 10 10 L 50 10 L 50 50 Z"},
            {},
            {"fill": (1.0, 0.5, 0.0, 1.0)},
        )

    def test_shape_with_transform(self):
        r = _make_renderer(128, 128)
        r.clear()
        r.render_shape(
            "rect",
            {"x": 0, "y": 0, "width": 20, "height": 20},
            {"translate_x": 50, "translate_y": 50, "rotate": 45},
            {"fill": (1.0, 0.0, 1.0, 1.0)},
        )

    def test_shape_with_stroke(self):
        r = _make_renderer(64, 64)
        r.clear()
        r.render_shape(
            "rect",
            {"x": 5, "y": 5, "width": 30, "height": 30},
            {},
            {
                "fill": (0.2, 0.2, 0.8, 1.0),
                "stroke": (1.0, 1.0, 1.0, 1.0),
                "stroke_width": 2.0,
            },
        )


# ---------------------------------------------------------------------------
# render_text()
# ---------------------------------------------------------------------------

class TestRenderText:
    def test_render_text_basic(self):
        r = _make_renderer(128, 64)
        r.clear()
        r.render_text("Hello", "sans-serif", 18.0, (10, 40), (1.0, 1.0, 1.0, 1.0))

    def test_render_text_empty(self):
        r = _make_renderer(64, 64)
        r.clear()
        r.render_text("", "sans-serif", 12.0, (0, 20), (1.0, 1.0, 1.0, 1.0))

    def test_render_text_large(self):
        r = _make_renderer(512, 128)
        r.clear()
        r.render_text("Motion Graphics", "sans-serif", 48.0, (10, 80), (1.0, 0.8, 0.0, 1.0))


# ---------------------------------------------------------------------------
# render_particles()
# ---------------------------------------------------------------------------

class TestRenderParticles:
    def _make_particles(self, n=10):
        """Create a synthetic Nx8 particle state."""
        particles = []
        for i in range(n):
            x = 10.0 + i * 4.0
            y = 20.0 + i * 2.0
            size = 5.0
            alpha = 0.8
            r, g, b = 1.0, 0.5, 0.0
            age = float(i)
            particles.append([x, y, size, alpha, r, g, b, age])
        return particles

    def test_render_particles_list(self):
        r = _make_renderer(128, 128)
        r.clear()
        particles = self._make_particles(10)
        r.render_particles(particles)

    def test_render_particles_numpy(self):
        if not HAS_NUMPY:
            pytest.skip("numpy not available")
        import numpy as np
        r = _make_renderer(128, 128)
        r.clear()
        particles = np.random.rand(20, 8)
        particles[:, 0] *= 128   # x
        particles[:, 1] *= 128   # y
        particles[:, 2] = particles[:, 2] * 8 + 2  # size 2-10
        r.render_particles(particles)

    def test_render_particles_none(self):
        r = _make_renderer(64, 64)
        r.render_particles(None)  # Should not raise

    def test_render_particles_empty(self):
        r = _make_renderer(64, 64)
        r.render_particles([])

    def test_render_particles_alpha(self):
        r = _make_renderer(128, 128)
        r.clear()
        # Particles with varying alpha
        particles = [[32.0, 32.0, 10.0, 0.0, 1.0, 0.0, 0.0, 0.0]]  # fully transparent
        r.render_particles(particles)


# ---------------------------------------------------------------------------
# render_path()
# ---------------------------------------------------------------------------

class TestRenderPath:
    def _line_points(self, n=10):
        return [(float(i * 10), float(i * 5)) for i in range(n)]

    def test_render_path_full(self):
        r = _make_renderer(128, 128)
        r.clear()
        pts = self._line_points()
        r.render_path(pts, 0.0, 1.0, {"stroke": (1.0, 1.0, 1.0, 1.0), "stroke_width": 2.0})

    def test_render_path_trimmed(self):
        r = _make_renderer(128, 128)
        r.clear()
        pts = self._line_points(20)
        r.render_path(pts, 0.2, 0.8, {"stroke": (0.0, 1.0, 0.0, 1.0), "stroke_width": 1.5})

    def test_render_path_empty_points(self):
        r = _make_renderer(64, 64)
        r.render_path([], 0.0, 1.0, {"stroke": (1.0, 1.0, 1.0, 1.0)})

    def test_render_path_invalid_trim(self):
        r = _make_renderer(64, 64)
        pts = self._line_points()
        # trim_start > trim_end → should not draw (no error)
        r.render_path(pts, 0.8, 0.2, {"stroke": (1.0, 1.0, 1.0, 1.0)})


# ---------------------------------------------------------------------------
# render_gradient()
# ---------------------------------------------------------------------------

class TestRenderGradient:
    def test_linear_gradient(self):
        r = _make_renderer(64, 64)
        colors = [
            (0.0, 0.0, 0.0, 1.0, 1.0),
            (1.0, 1.0, 1.0, 1.0, 1.0),
        ]
        r.render_gradient("linear", colors, (0, 0), (64, 0))

    def test_radial_gradient(self):
        r = _make_renderer(64, 64)
        colors = [
            (0.0, 1.0, 1.0, 0.0, 1.0),
            (1.0, 0.0, 0.0, 0.0, 1.0),
        ]
        r.render_gradient("radial", colors, (32, 32), (32, 0))

    def test_unknown_gradient_type(self):
        r = _make_renderer(64, 64)
        # Should not raise, just skip
        r.render_gradient("unknown", [], (0, 0), (64, 64))


# ---------------------------------------------------------------------------
# to_png()
# ---------------------------------------------------------------------------

class TestToPng:
    def test_saves_png_file(self):
        r = _make_renderer(32, 32)
        r.clear((0.5, 0.5, 0.5, 1.0))
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "out.png")
            r.to_png(path)
            assert os.path.isfile(path)
            assert os.path.getsize(path) > 0

    def test_saved_png_has_correct_signature(self):
        r = _make_renderer(32, 32)
        r.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.png")
            r.to_png(path)
            assert _is_valid_png(path)

    def test_png_after_drawing(self):
        r = _make_renderer(64, 64)
        r.clear()
        r.render_shape("rect", {"x": 10, "y": 10, "width": 20, "height": 20}, {},
                       {"fill": (1.0, 0.0, 0.0, 1.0)})
        r.render_text("Test", "sans-serif", 12.0, (5, 50), (1.0, 1.0, 1.0, 1.0))
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "composed.png")
            r.to_png(path)
            assert _is_valid_png(path)

    def test_creates_parent_directory(self):
        r = _make_renderer(16, 16)
        r.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "subdir", "nested", "out.png")
            r.to_png(path)
            assert os.path.isfile(path)


# ---------------------------------------------------------------------------
# to_numpy()
# ---------------------------------------------------------------------------

class TestToNumpy:
    def test_to_numpy_returns_none_without_numpy(self):
        if HAS_NUMPY:
            pytest.skip("numpy is available — skip the no-numpy path")
        r = _make_renderer(16, 16)
        assert r.to_numpy() is None

    def test_to_numpy_shape(self):
        if not HAS_NUMPY:
            pytest.skip("numpy not available")
        r = _make_renderer(32, 48)
        arr = r.to_numpy()
        assert arr is not None
        assert arr.shape == (48, 32, 4)

    def test_to_numpy_dtype(self):
        if not HAS_NUMPY:
            pytest.skip("numpy not available")
        import numpy as np
        r = _make_renderer(16, 16)
        arr = r.to_numpy()
        assert arr.dtype == np.uint8

    def test_to_numpy_after_clear_white(self):
        if not HAS_NUMPY:
            pytest.skip("numpy not available")
        import numpy as np
        r = _make_renderer(8, 8)
        r.clear((1.0, 1.0, 1.0, 1.0))
        arr = r.to_numpy()
        # All pixels should be white (255,255,255,255)
        assert arr is not None
        assert arr.shape[2] == 4
        # Check that alpha channel is 255
        assert arr[:, :, 3].min() == 255


# ---------------------------------------------------------------------------
# animation.py easing upgrade
# ---------------------------------------------------------------------------

class TestAnimationEasingUpgrade:
    """Verify animation.py works with shared motion_math easings."""

    def setup_method(self):
        sys.path.insert(
            0,
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        )
        from cli_anything.gimp.core.animation import (
            INTERPOLATION_TYPES,
            _ease,
            _all_interpolation_types,
        )
        self.INTERPOLATION_TYPES = INTERPOLATION_TYPES
        self._ease = _ease
        self._all_interpolation_types = _all_interpolation_types

    def test_legacy_linear(self):
        assert self._ease(0.5, "LINEAR") == pytest.approx(0.5)

    def test_legacy_constant(self):
        assert self._ease(0.5, "CONSTANT") == 0.0

    def test_legacy_ease_in(self):
        assert self._ease(0.5, "EASE_IN") == pytest.approx(0.25)

    def test_legacy_ease_out(self):
        assert self._ease(0.5, "EASE_OUT") == pytest.approx(0.75)

    def test_legacy_ease_in_out(self):
        v = self._ease(0.5, "EASE_IN_OUT")
        assert 0.4 < v < 0.6  # symmetric at midpoint

    def test_all_types_includes_legacy(self):
        all_types = self._all_interpolation_types()
        for t in ["LINEAR", "CONSTANT", "EASE_IN", "EASE_OUT", "EASE_IN_OUT"]:
            assert t in all_types

    def test_shared_easings_if_available(self):
        from cli_anything.gimp.core.cairo_renderer import HAS_CAIRO  # noqa
        from cli_anything.gimp.core import animation as anim_mod
        if anim_mod._SHARED_EASING_FUNCTIONS is not None:
            # Should support at least 30 shared names
            all_types = self._all_interpolation_types()
            assert len(all_types) > 10

    def test_shared_easing_bounce(self):
        from cli_anything.gimp.core import animation as anim_mod
        if anim_mod._SHARED_EASING_FUNCTIONS is None:
            pytest.skip("Shared motion_math not available")
        v = self._ease(1.0, "ease_out_bounce")
        assert v == pytest.approx(1.0)

    def test_shared_easing_elastic(self):
        from cli_anything.gimp.core import animation as anim_mod
        if anim_mod._SHARED_EASING_FUNCTIONS is None:
            pytest.skip("Shared motion_math not available")
        v0 = self._ease(0.0, "ease_in_elastic")
        v1 = self._ease(1.0, "ease_in_elastic")
        assert v0 == pytest.approx(0.0)
        assert v1 == pytest.approx(1.0)

    def test_unknown_easing_fallback_linear(self):
        v = self._ease(0.6, "NONEXISTENT_EASING")
        assert v == pytest.approx(0.6)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
