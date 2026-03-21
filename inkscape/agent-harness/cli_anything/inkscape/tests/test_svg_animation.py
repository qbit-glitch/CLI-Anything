"""Unit tests for Inkscape CLI - SVG animation (SMIL) module.

All tests work without PyCairo, cairosvg, or Inkscape installed.
They test the string-generation and value-interpolation logic.
"""

from __future__ import annotations

import math
import os
import re
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cli_anything.inkscape.core.svg_animation import (
    animate_attribute,
    animate_transform,
    morph_path,
    animate_stroke_dashoffset,
    render_svg_sequence,
    _interpolate_smil_value,
    _parse_smil_values,
    _build_values_string,
    _easing_to_smil,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _attr(smil: str, name: str) -> str:
    """Extract an attribute value from a SMIL element string."""
    m = re.search(
        r'\b' + re.escape(name) + r'\s*=\s*["\']([^"\']*)["\']',
        smil,
        re.IGNORECASE,
    )
    return m.group(1) if m else ""


def _make_simple_svg(width=100, height=100) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect id="box" x="10" y="10" width="30" height="30" opacity="0.0" fill="blue"/>
  <circle id="dot" cx="50" cy="50" r="20" fill="red"/>
  <path id="line" d="M 0 50 L 100 50" stroke="black" stroke-width="2"/>
</svg>"""


# ---------------------------------------------------------------------------
# animate_attribute()
# ---------------------------------------------------------------------------

class TestAnimateAttribute:
    def test_returns_animate_element(self):
        result = animate_attribute("box", "opacity", [0, 1], 2.0)
        assert "<animate" in result

    def test_contains_attr_name(self):
        result = animate_attribute("box", "opacity", [0, 1], 2.0)
        assert 'attributeName="opacity"' in result

    def test_contains_duration(self):
        result = animate_attribute("myEl", "width", [10, 100], 3.0)
        assert 'dur="3.0s"' in result

    def test_contains_href(self):
        result = animate_attribute("myEl", "opacity", [0, 1], 1.0)
        assert "#myEl" in result

    def test_linear_calc_mode(self):
        result = animate_attribute("el", "opacity", [0, 1], 1.0, easing="linear")
        assert 'calcMode="linear"' in result

    def test_values_string_for_list(self):
        result = animate_attribute("el", "opacity", [0, 0.5, 1], 2.0)
        assert "values=" in result

    def test_two_values_with_spline_easing(self):
        result = animate_attribute("el", "opacity", [0, 1], 2.0, easing="ease-in")
        # Should use spline calcMode and produce intermediate keyframe values
        assert 'calcMode="spline"' in result
        assert "keySplines=" in result

    def test_repeat_count(self):
        result = animate_attribute("el", "r", [5, 20], 1.0, repeat_count="3")
        assert 'repeatCount="3"' in result

    def test_begin_attribute(self):
        result = animate_attribute("el", "opacity", [0, 1], 1.0, begin="0.5s")
        assert 'begin="0.5s"' in result

    def test_string_values_in_list(self):
        # e.g. animating fill color names
        result = animate_attribute("el", "fill", ["red", "blue", "green"], 3.0)
        assert "red" in result
        assert "blue" in result

    def test_closes_element(self):
        result = animate_attribute("el", "opacity", [0, 1], 1.0)
        assert result.strip().endswith("/>")

    def test_single_value(self):
        result = animate_attribute("el", "opacity", [1], 1.0)
        assert "<animate" in result


# ---------------------------------------------------------------------------
# animate_transform()
# ---------------------------------------------------------------------------

class TestAnimateTransform:
    def test_returns_animate_transform_element(self):
        result = animate_transform("box", "rotate", "0", "360", 2.0)
        assert "<animateTransform" in result

    def test_contains_type_rotate(self):
        result = animate_transform("box", "rotate", "0 50 50", "360 50 50", 2.0)
        assert 'type="rotate"' in result

    def test_contains_type_scale(self):
        result = animate_transform("box", "scale", "1", "2", 1.5)
        assert 'type="scale"' in result

    def test_contains_type_translate(self):
        result = animate_transform("box", "translate", "0 0", "100 50", 3.0)
        assert 'type="translate"' in result

    def test_contains_from_to(self):
        result = animate_transform("box", "rotate", "0", "180", 1.0)
        assert 'from="0"' in result
        assert 'to="180"' in result

    def test_contains_duration(self):
        result = animate_transform("box", "scale", "1", "3", 4.0)
        assert 'dur="4.0s"' in result

    def test_contains_href(self):
        result = animate_transform("myBox", "rotate", "0", "360", 1.0)
        assert "#myBox" in result

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Invalid transform_type"):
            animate_transform("el", "shear", "0", "1", 1.0)

    def test_additive_sum(self):
        result = animate_transform("el", "translate", "0 0", "10 0", 1.0, additive="sum")
        assert 'additive="sum"' in result

    def test_closes_element(self):
        result = animate_transform("el", "scale", "1", "2", 1.0)
        assert result.strip().endswith("/>")

    def test_spline_easing_adds_keysplines(self):
        result = animate_transform("el", "rotate", "0", "360", 2.0, easing="ease-in-out")
        assert 'calcMode="spline"' in result
        assert "keySplines=" in result


# ---------------------------------------------------------------------------
# morph_path()
# ---------------------------------------------------------------------------

class TestMorphPath:
    def test_returns_animate_element(self):
        result = morph_path("M 0 0 L 10 10", "M 10 0 L 0 10", 2.0)
        assert "<animate" in result

    def test_contains_attr_d(self):
        result = morph_path("M 0 0", "M 10 10", 1.0)
        assert 'attributeName="d"' in result

    def test_contains_both_paths_in_values(self):
        path_a = "M 0 0 L 100 100"
        path_b = "M 0 100 L 100 0"
        result = morph_path(path_a, path_b, 2.0)
        assert path_a in result
        assert path_b in result

    def test_semicolon_separator(self):
        result = morph_path("M 0 0", "M 10 10", 1.0)
        # Values should contain a semicolon between the two path strings
        values_match = re.search(r'values="([^"]*)"', result)
        assert values_match
        assert ";" in values_match.group(1)

    def test_duration(self):
        result = morph_path("M 0 0", "M 5 5", 3.5)
        assert 'dur="3.5s"' in result

    def test_repeat_count(self):
        result = morph_path("M 0 0", "M 5 5", 1.0, repeat_count="2")
        assert 'repeatCount="2"' in result

    def test_default_element_id(self):
        result = morph_path("M 0 0", "M 5 5", 1.0)
        assert "#path" in result

    def test_custom_element_id(self):
        result = morph_path("M 0 0", "M 5 5", 1.0, element_id="myPath")
        assert "#myPath" in result

    def test_linear_easing(self):
        result = morph_path("M 0 0", "M 5 5", 1.0, easing="linear")
        assert 'calcMode="linear"' in result

    def test_closes_element(self):
        result = morph_path("M 0 0", "M 5 5", 1.0)
        assert result.strip().endswith("/>")


# ---------------------------------------------------------------------------
# animate_stroke_dashoffset()
# ---------------------------------------------------------------------------

class TestAnimateStrokeDashoffset:
    def test_returns_string(self):
        result = animate_stroke_dashoffset("line", 2.0)
        assert isinstance(result, str)

    def test_contains_dashoffset(self):
        result = animate_stroke_dashoffset("line", 2.0)
        assert "stroke-dashoffset" in result

    def test_contains_set_dasharray(self):
        result = animate_stroke_dashoffset("line", 2.0)
        assert "stroke-dasharray" in result

    def test_contains_path_id(self):
        result = animate_stroke_dashoffset("myLine", 2.0)
        assert "#myLine" in result

    def test_default_path_length(self):
        result = animate_stroke_dashoffset("line", 1.0)
        assert "1000" in result  # default path_length

    def test_custom_path_length(self):
        result = animate_stroke_dashoffset("line", 1.0, path_length=500.0)
        assert "500.0" in result

    def test_duration(self):
        result = animate_stroke_dashoffset("line", 3.5)
        assert '3.5s' in result

    def test_values_go_from_length_to_zero(self):
        result = animate_stroke_dashoffset("line", 1.0, path_length=200.0)
        # The animate element should animate from 200 → 0
        assert "200.0;0" in result

    def test_repeat_count(self):
        result = animate_stroke_dashoffset("line", 1.0, repeat_count="indefinite")
        assert 'repeatCount="indefinite"' in result

    def test_closes_element(self):
        result = animate_stroke_dashoffset("line", 1.0)
        assert result.strip().endswith("/>")


# ---------------------------------------------------------------------------
# render_svg_sequence()
# ---------------------------------------------------------------------------

class TestRenderSvgSequence:
    def _make_animated_svg(self) -> str:
        return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink"
     width="100" height="100" viewBox="0 0 100 100">
  <rect id="box" x="10" y="10" width="30" height="30" opacity="0" fill="blue"/>
  <animate xlink:href="#box" attributeName="opacity" values="0;1" dur="1s"
           repeatCount="1" calcMode="linear"/>
</svg>"""

    def test_returns_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svg = self._make_animated_svg()
            result = render_svg_sequence(svg, 5, 25, tmpdir)
            assert isinstance(result, dict)

    def test_result_has_frame_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svg = self._make_animated_svg()
            result = render_svg_sequence(svg, 3, 24, tmpdir)
            assert result["frame_count"] == 3

    def test_result_has_output_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svg = self._make_animated_svg()
            result = render_svg_sequence(svg, 2, 24, tmpdir)
            assert "output_dir" in result
            assert os.path.isdir(result["output_dir"])

    def test_result_has_fps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_svg_sequence(self._make_animated_svg(), 4, 30, tmpdir)
            assert result["fps"] == 30

    def test_result_has_frames_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_svg_sequence(self._make_animated_svg(), 4, 24, tmpdir)
            assert "frames" in result
            assert len(result["frames"]) == 4

    def test_result_has_renderer_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_svg_sequence(self._make_animated_svg(), 2, 24, tmpdir)
            assert "renderer" in result

    def test_output_files_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_svg_sequence(self._make_animated_svg(), 3, 24, tmpdir)
            for f in result["frames"]:
                assert os.path.isfile(f), f"Frame file not found: {f}"

    def test_duration_calculation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = render_svg_sequence(self._make_animated_svg(), 24, 24, tmpdir)
            assert result["duration"] == pytest.approx(1.0)

    def test_creates_output_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = os.path.join(tmpdir, "frames", "output")
            result = render_svg_sequence(self._make_animated_svg(), 2, 24, new_dir)
            assert os.path.isdir(new_dir)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestInterpolateSMILValue:
    def test_empty_list_returns_none(self):
        assert _interpolate_smil_value([], 0.5) is None

    def test_single_value_returns_it(self):
        assert _interpolate_smil_value([42.0], 0.5) == 42.0

    def test_two_values_at_start(self):
        assert _interpolate_smil_value([0.0, 1.0], 0.0) == pytest.approx(0.0)

    def test_two_values_at_end(self):
        assert _interpolate_smil_value([0.0, 1.0], 1.0) == pytest.approx(1.0)

    def test_two_values_midpoint(self):
        assert _interpolate_smil_value([0.0, 2.0], 0.5) == pytest.approx(1.0)

    def test_three_values_quarter(self):
        v = _interpolate_smil_value([0.0, 1.0, 2.0], 0.25)
        assert 0.0 <= v <= 1.0


class TestParseSmilValues:
    def test_parses_numbers(self):
        result = _parse_smil_values("0;0.5;1")
        assert result == [0.0, 0.5, 1.0]

    def test_parses_strings(self):
        result = _parse_smil_values("red;blue")
        assert result == ["red", "blue"]

    def test_single_value(self):
        result = _parse_smil_values("42")
        assert result == [42.0]


class TestBuildValuesString:
    def test_joins_with_semicolons(self):
        assert _build_values_string([0, 0.5, 1]) == "0;0.5;1"

    def test_string_values(self):
        assert _build_values_string(["red", "blue"]) == "red;blue"


class TestEasingToSmil:
    def test_linear(self):
        mode, splines = _easing_to_smil("linear")
        assert mode == "linear"
        assert splines is None

    def test_ease(self):
        mode, splines = _easing_to_smil("ease")
        assert mode == "spline"
        assert splines is not None

    def test_ease_in(self):
        mode, splines = _easing_to_smil("ease-in")
        assert mode == "spline"

    def test_penner_cubic(self):
        mode, splines = _easing_to_smil("ease_in_cubic")
        assert mode == "spline"
        assert splines is not None

    def test_unknown_falls_back_to_linear(self):
        mode, splines = _easing_to_smil("bogus_easing")
        assert mode == "linear"
        assert splines is None

    def test_case_insensitive(self):
        mode1, _ = _easing_to_smil("Linear")
        mode2, _ = _easing_to_smil("LINEAR")
        assert mode1 == "linear"
        assert mode2 == "linear"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
