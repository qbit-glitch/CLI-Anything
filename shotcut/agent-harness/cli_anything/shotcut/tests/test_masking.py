"""Tests for the advanced compositing / masking module."""

import os
import sys
import tempfile
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cli_anything.shotcut.core.session import Session
from cli_anything.shotcut.core import project as proj_mod
from cli_anything.shotcut.core import timeline as tl_mod
from cli_anything.shotcut.core import masking as mask_mod
from cli_anything.shotcut.utils.mlt_xml import get_property


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_with_clip():
    """Create a session with one video track and a dummy clip."""
    s = Session()
    proj_mod.new_project(s, "hd1080p30")
    tl_mod.add_track(s, "video")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"dummy")
        tmpfile = f.name

    tl_mod.add_clip(s, tmpfile, 1,
                    in_point="00:00:00.000", out_point="00:00:05.000")
    return s, tmpfile


def _make_session_with_two_tracks():
    """Create a session with two video tracks and clips on each."""
    s = Session()
    proj_mod.new_project(s, "hd1080p30")
    tl_mod.add_track(s, "video")
    tl_mod.add_track(s, "video")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"dummy")
        tmpfile = f.name

    tl_mod.add_clip(s, tmpfile, 1,
                    in_point="00:00:00.000", out_point="00:00:05.000")
    tl_mod.add_clip(s, tmpfile, 2,
                    in_point="00:00:00.000", out_point="00:00:05.000")
    return s, tmpfile


# ============================================================================
# list_mask_types
# ============================================================================

class TestListMaskTypes:
    def test_returns_all_types(self):
        result = mask_mod.list_mask_types()
        names = [m["name"] for m in result]
        assert "rectangle" in names
        assert "ellipse" in names
        assert "gradient_horizontal" in names
        assert "gradient_vertical" in names

    def test_entries_have_expected_keys(self):
        for entry in mask_mod.list_mask_types():
            assert "name" in entry
            assert "service" in entry
            assert "description" in entry
            assert "params" in entry


# ============================================================================
# add_mask — each type
# ============================================================================

class TestAddMask:
    def test_add_rectangle_mask(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = mask_mod.add_mask(s, "rectangle",
                                       track_index=1, clip_index=0)
            assert result["action"] == "add_mask"
            assert result["mask_type"] == "rectangle"
            assert result["service"] == "frei0r.alphaspot"
            assert result["params"]["shape"] == "0"
        finally:
            os.unlink(tmpfile)

    def test_add_ellipse_mask(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = mask_mod.add_mask(s, "ellipse",
                                       track_index=1, clip_index=0)
            assert result["mask_type"] == "ellipse"
            assert result["params"]["shape"] == "1"
        finally:
            os.unlink(tmpfile)

    def test_add_gradient_horizontal_mask(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = mask_mod.add_mask(s, "gradient_horizontal",
                                       track_index=1, clip_index=0)
            assert result["mask_type"] == "gradient_horizontal"
            assert result["service"] == "frei0r.alphagrad"
            assert result["params"]["tilt"] == "0"
        finally:
            os.unlink(tmpfile)

    def test_add_gradient_vertical_mask(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = mask_mod.add_mask(s, "gradient_vertical",
                                       track_index=1, clip_index=0)
            assert result["mask_type"] == "gradient_vertical"
            assert result["service"] == "frei0r.alphagrad"
            assert result["params"]["tilt"] == "0.25"
        finally:
            os.unlink(tmpfile)

    def test_add_mask_with_custom_params(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = mask_mod.add_mask(
                s, "rectangle", track_index=1, clip_index=0,
                params={"position_x": "0.3", "position_y": "0.7"})
            assert result["params"]["position_x"] == "0.3"
            assert result["params"]["position_y"] == "0.7"
            # Defaults should still be present for un-overridden params
            assert result["params"]["size_x"] == "0.5"
        finally:
            os.unlink(tmpfile)

    def test_add_mask_invalid_type(self):
        s, tmpfile = _make_session_with_clip()
        try:
            with pytest.raises(ValueError, match="Unknown mask type"):
                mask_mod.add_mask(s, "nonexistent_mask",
                                  track_index=1, clip_index=0)
        finally:
            os.unlink(tmpfile)

    def test_add_mask_global(self):
        s = Session()
        proj_mod.new_project(s, "hd1080p30")
        result = mask_mod.add_mask(s, "rectangle")
        assert result["target"] == "global"

    def test_add_mask_track_level(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = mask_mod.add_mask(s, "ellipse", track_index=1)
            assert result["target"] == "track 1"
        finally:
            os.unlink(tmpfile)


# ============================================================================
# feather and invert options
# ============================================================================

class TestFeatherInvert:
    def test_feather_default_not_set(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = mask_mod.add_mask(s, "rectangle",
                                       track_index=1, clip_index=0)
            # feather should not appear when 0.0
            assert "feather" not in result["params"]
        finally:
            os.unlink(tmpfile)

    def test_feather_nonzero(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = mask_mod.add_mask(s, "rectangle",
                                       track_index=1, clip_index=0,
                                       feather=0.5)
            assert result["params"]["feather"] == "0.5"
        finally:
            os.unlink(tmpfile)

    def test_invert_default_not_set(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = mask_mod.add_mask(s, "ellipse",
                                       track_index=1, clip_index=0)
            assert "invert" not in result["params"]
        finally:
            os.unlink(tmpfile)

    def test_invert_true(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = mask_mod.add_mask(s, "ellipse",
                                       track_index=1, clip_index=0,
                                       invert=True)
            assert result["params"]["invert"] == "1"
        finally:
            os.unlink(tmpfile)

    def test_feather_and_invert_together(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = mask_mod.add_mask(s, "rectangle",
                                       track_index=1, clip_index=0,
                                       feather=0.3, invert=True)
            assert result["params"]["feather"] == "0.3"
            assert result["params"]["invert"] == "1"
        finally:
            os.unlink(tmpfile)


# ============================================================================
# set_mask_param
# ============================================================================

class TestSetMaskParam:
    def test_set_param(self):
        s, tmpfile = _make_session_with_clip()
        try:
            add_result = mask_mod.add_mask(s, "rectangle",
                                           track_index=1, clip_index=0)
            idx = add_result["filter_index"]
            result = mask_mod.set_mask_param(
                s, idx, "position_x", "0.8",
                track_index=1, clip_index=0)
            assert result["action"] == "set_mask_param"
            assert result["new_value"] == "0.8"
        finally:
            os.unlink(tmpfile)

    def test_set_param_invalid_index(self):
        s, tmpfile = _make_session_with_clip()
        try:
            with pytest.raises(IndexError):
                mask_mod.set_mask_param(s, 99, "position_x", "0.5",
                                        track_index=1, clip_index=0)
        finally:
            os.unlink(tmpfile)


# ============================================================================
# animate_mask
# ============================================================================

class TestAnimateMask:
    def test_animate_position(self):
        s, tmpfile = _make_session_with_clip()
        try:
            add_result = mask_mod.add_mask(s, "rectangle",
                                           track_index=1, clip_index=0)
            idx = add_result["filter_index"]
            keyframes = [
                {"time": "00:00:00.000", "value": "0.2", "easing": "linear"},
                {"time": "00:00:02.000", "value": "0.8", "easing": "smooth"},
            ]
            result = mask_mod.animate_mask(
                s, idx, "position_x", keyframes,
                track_index=1, clip_index=0)
            assert result["action"] == "animate_mask"
            assert result["keyframes_applied"] == 2
            assert result["param"] == "position_x"
        finally:
            os.unlink(tmpfile)

    def test_animate_single_keyframe(self):
        s, tmpfile = _make_session_with_clip()
        try:
            add_result = mask_mod.add_mask(s, "ellipse",
                                           track_index=1, clip_index=0)
            idx = add_result["filter_index"]
            keyframes = [
                {"time": "00:00:01.000", "value": "0.5"},
            ]
            result = mask_mod.animate_mask(
                s, idx, "size_x", keyframes,
                track_index=1, clip_index=0)
            assert result["keyframes_applied"] == 1
            # Easing should default to "linear"
            assert result["keyframes"][0]["easing"] == "linear"
        finally:
            os.unlink(tmpfile)

    def test_animate_invalid_filter_index(self):
        s, tmpfile = _make_session_with_clip()
        try:
            with pytest.raises(IndexError):
                mask_mod.animate_mask(
                    s, 99, "position_x",
                    [{"time": "00:00:00.000", "value": "0.5"}],
                    track_index=1, clip_index=0)
        finally:
            os.unlink(tmpfile)


# ============================================================================
# add_track_matte
# ============================================================================

class TestTrackMatte:
    def test_add_track_matte(self):
        s, tmpfile = _make_session_with_two_tracks()
        try:
            result = mask_mod.add_track_matte(s, source_track=1,
                                              target_track=2)
            assert result["action"] == "add_track_matte"
            assert result["service"] == "frei0r.alphatop"
            assert result["source_track"] == 1
            assert result["target_track"] == 2
            assert result["transition_id"] is not None
        finally:
            os.unlink(tmpfile)

    def test_track_matte_invalid_source(self):
        s, tmpfile = _make_session_with_two_tracks()
        try:
            with pytest.raises(IndexError, match="Source"):
                mask_mod.add_track_matte(s, source_track=99, target_track=2)
        finally:
            os.unlink(tmpfile)

    def test_track_matte_invalid_target(self):
        s, tmpfile = _make_session_with_two_tracks()
        try:
            with pytest.raises(IndexError, match="Target"):
                mask_mod.add_track_matte(s, source_track=1, target_track=99)
        finally:
            os.unlink(tmpfile)


# ============================================================================
# list_masks
# ============================================================================

class TestListMasks:
    def test_list_empty(self):
        s, tmpfile = _make_session_with_clip()
        try:
            result = mask_mod.list_masks(s, track_index=1, clip_index=0)
            assert result == []
        finally:
            os.unlink(tmpfile)

    def test_list_after_add(self):
        s, tmpfile = _make_session_with_clip()
        try:
            mask_mod.add_mask(s, "rectangle",
                              track_index=1, clip_index=0)
            result = mask_mod.list_masks(s, track_index=1, clip_index=0)
            assert len(result) == 1
            assert result[0]["mask_type"] == "rectangle"
            assert result[0]["service"] == "frei0r.alphaspot"
        finally:
            os.unlink(tmpfile)

    def test_list_multiple_masks(self):
        s, tmpfile = _make_session_with_clip()
        try:
            mask_mod.add_mask(s, "rectangle",
                              track_index=1, clip_index=0)
            mask_mod.add_mask(s, "ellipse",
                              track_index=1, clip_index=0)
            result = mask_mod.list_masks(s, track_index=1, clip_index=0)
            assert len(result) == 2
            types = [m["mask_type"] for m in result]
            assert "rectangle" in types
            assert "ellipse" in types
        finally:
            os.unlink(tmpfile)

    def test_list_identifies_gradient(self):
        s, tmpfile = _make_session_with_clip()
        try:
            mask_mod.add_mask(s, "gradient_vertical",
                              track_index=1, clip_index=0)
            result = mask_mod.list_masks(s, track_index=1, clip_index=0)
            assert len(result) == 1
            assert result[0]["mask_type"] == "gradient_vertical"
        finally:
            os.unlink(tmpfile)


# ============================================================================
# remove_mask
# ============================================================================

class TestRemoveMask:
    def test_remove_mask(self):
        s, tmpfile = _make_session_with_clip()
        try:
            add_result = mask_mod.add_mask(s, "rectangle",
                                           track_index=1, clip_index=0)
            idx = add_result["filter_index"]
            result = mask_mod.remove_mask(s, idx,
                                          track_index=1, clip_index=0)
            assert result["action"] == "remove_mask"
            assert result["service"] == "frei0r.alphaspot"

            # Should be gone now
            masks = mask_mod.list_masks(s, track_index=1, clip_index=0)
            assert len(masks) == 0
        finally:
            os.unlink(tmpfile)

    def test_remove_mask_invalid_index(self):
        s, tmpfile = _make_session_with_clip()
        try:
            with pytest.raises(IndexError):
                mask_mod.remove_mask(s, 99,
                                     track_index=1, clip_index=0)
        finally:
            os.unlink(tmpfile)

    def test_undo_add_mask(self):
        s, tmpfile = _make_session_with_clip()
        try:
            mask_mod.add_mask(s, "ellipse",
                              track_index=1, clip_index=0)
            assert len(mask_mod.list_masks(s, track_index=1,
                                           clip_index=0)) == 1
            s.undo()
            assert len(mask_mod.list_masks(s, track_index=1,
                                           clip_index=0)) == 0
        finally:
            os.unlink(tmpfile)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
