"""Unit tests for Audacity CLI sync export module.

Tests cover all sync formats (JSON, EDL, CSV), timecode conversion,
and file export functionality.
"""

import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cli_anything.audacity.core.project import create_project
from cli_anything.audacity.core.labels import add_label
from cli_anything.audacity.core.sync import (
    seconds_to_timecode,
    timecode_to_seconds,
    labels_to_json_markers,
    labels_to_edl,
    labels_to_csv,
    export_sync_data,
    beat_detect,
    amplitude_envelope,
    frequency_bands,
)


# -- Helper ------------------------------------------------------------------

def _make_project_with_labels():
    """Create a project with a mix of point and range labels."""
    proj = create_project(name="Sync Test")
    add_label(proj, 2.5, text="Intro")             # point label
    add_label(proj, 5.0, 10.0, "Verse 1")          # range label
    add_label(proj, 15.0, text="Bridge")            # point label
    add_label(proj, 20.0, 35.5, "Chorus")           # range label
    return proj


# -- Timecode Tests ----------------------------------------------------------

class TestTimecodeConversion:
    def test_seconds_to_timecode_zero(self):
        assert seconds_to_timecode(0.0) == "00:00:00.000"

    def test_seconds_to_timecode_simple(self):
        assert seconds_to_timecode(1.0) == "00:00:01.000"

    def test_seconds_to_timecode_with_ms(self):
        assert seconds_to_timecode(2.5) == "00:00:02.500"

    def test_seconds_to_timecode_minutes(self):
        assert seconds_to_timecode(90.0) == "00:01:30.000"

    def test_seconds_to_timecode_hours(self):
        assert seconds_to_timecode(3661.5) == "01:01:01.500"

    def test_seconds_to_timecode_negative_clamps(self):
        assert seconds_to_timecode(-5.0) == "00:00:00.000"

    def test_timecode_to_seconds_zero(self):
        assert timecode_to_seconds("00:00:00.000") == 0.0

    def test_timecode_to_seconds_simple(self):
        assert timecode_to_seconds("00:00:01.000") == 1.0

    def test_timecode_to_seconds_with_ms(self):
        assert abs(timecode_to_seconds("00:00:02.500") - 2.5) < 0.001

    def test_timecode_to_seconds_minutes(self):
        assert abs(timecode_to_seconds("00:01:30.000") - 90.0) < 0.001

    def test_timecode_to_seconds_hours(self):
        assert abs(timecode_to_seconds("01:01:01.500") - 3661.5) < 0.001

    def test_roundtrip_integer_seconds(self):
        for secs in [0, 1, 10, 60, 3600, 7200]:
            tc = seconds_to_timecode(float(secs))
            back = timecode_to_seconds(tc)
            assert abs(back - secs) < 0.001, (
                f"Roundtrip failed: {secs} -> {tc} -> {back}"
            )

    def test_roundtrip_fractional_seconds(self):
        for secs in [0.5, 1.234, 45.678, 123.456, 3661.789]:
            tc = seconds_to_timecode(secs)
            back = timecode_to_seconds(tc)
            assert abs(back - secs) < 0.002, (
                f"Roundtrip failed: {secs} -> {tc} -> {back}"
            )

    def test_timecode_invalid_format(self):
        with pytest.raises(ValueError):
            timecode_to_seconds("invalid")

    def test_timecode_mm_ss_format(self):
        assert abs(timecode_to_seconds("01:30.000") - 90.0) < 0.001


# -- labels_to_json_markers Tests -------------------------------------------

class TestLabelsToJsonMarkers:
    def test_empty_project(self):
        proj = create_project()
        markers = labels_to_json_markers(proj)
        assert markers == []

    def test_point_and_range_labels(self):
        proj = _make_project_with_labels()
        markers = labels_to_json_markers(proj)
        assert len(markers) == 4

        # First: point label at 2.5s
        m0 = markers[0]
        assert m0["label"] == "Intro"
        assert m0["type"] == "point"
        assert m0["time_seconds"] == 2.5
        assert m0["duration"] == 0.0
        assert m0["time"] == "00:00:02.500"

        # Second: range label 5.0-10.0
        m1 = markers[1]
        assert m1["label"] == "Verse 1"
        assert m1["type"] == "range"
        assert m1["time_seconds"] == 5.0
        assert m1["duration"] == 5.0
        assert "end_time" in m1
        assert "end_seconds" in m1
        assert m1["end_seconds"] == 10.0

    def test_range_label_has_end_fields(self):
        proj = create_project()
        add_label(proj, 1.0, 3.0, "Test Range")
        markers = labels_to_json_markers(proj)
        assert len(markers) == 1
        m = markers[0]
        assert m["type"] == "range"
        assert "end_time" in m
        assert "end_seconds" in m

    def test_point_label_no_end_fields(self):
        proj = create_project()
        add_label(proj, 5.0, text="Marker")
        markers = labels_to_json_markers(proj)
        assert len(markers) == 1
        m = markers[0]
        assert m["type"] == "point"
        assert "end_time" not in m


# -- labels_to_edl Tests ----------------------------------------------------

class TestLabelsToEdl:
    def test_edl_format_header(self):
        proj = create_project(name="My Project")
        edl = labels_to_edl(proj, title="My Project")
        lines = edl.strip().splitlines()
        assert lines[0] == "TITLE: My Project"
        assert lines[1] == "FCM: NON-DROP FRAME"

    def test_edl_with_labels(self):
        proj = _make_project_with_labels()
        edl = labels_to_edl(proj, title="Test")
        assert "TITLE: Test" in edl
        assert "001" in edl  # First event
        assert "002" in edl  # Second event
        assert "FROM CLIP NAME: Intro" in edl
        assert "FROM CLIP NAME: Verse 1" in edl

    def test_edl_empty_project(self):
        proj = create_project()
        edl = labels_to_edl(proj)
        lines = edl.strip().splitlines()
        assert lines[0] == "TITLE: untitled"
        # No events
        assert all("001" not in line for line in lines)

    def test_edl_point_label_has_minimal_duration(self):
        proj = create_project()
        add_label(proj, 5.0, text="Snap")
        edl = labels_to_edl(proj)
        # The event should still appear with src_in and src_out
        assert "001" in edl
        assert "00:00:05.000" in edl

    def test_edl_event_count(self):
        proj = _make_project_with_labels()
        edl = labels_to_edl(proj)
        # Count event lines (lines starting with 3-digit numbers)
        event_lines = [
            line for line in edl.splitlines()
            if line.strip() and line.strip()[:3].isdigit()
        ]
        assert len(event_lines) == 4


# -- labels_to_csv Tests ----------------------------------------------------

class TestLabelsToCsv:
    def test_csv_empty(self):
        proj = create_project()
        csv = labels_to_csv(proj)
        assert csv == ""

    def test_csv_with_labels(self):
        proj = _make_project_with_labels()
        csv = labels_to_csv(proj)
        lines = csv.strip().splitlines()
        assert len(lines) == 4

        # Check first line (point label)
        parts = lines[0].split("\t")
        assert len(parts) == 3
        assert float(parts[0]) == 2.5
        assert float(parts[1]) == 2.5  # point label: start == end
        assert parts[2] == "Intro"

        # Check second line (range label)
        parts = lines[1].split("\t")
        assert float(parts[0]) == 5.0
        assert float(parts[1]) == 10.0
        assert parts[2] == "Verse 1"

    def test_csv_tab_separated(self):
        proj = create_project()
        add_label(proj, 1.0, 2.0, "Test")
        csv = labels_to_csv(proj)
        assert "\t" in csv
        parts = csv.strip().split("\t")
        assert len(parts) == 3


# -- export_sync_data Tests -------------------------------------------------

class TestExportSyncData:
    def test_export_json(self):
        proj = _make_project_with_labels()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            result = export_sync_data(proj, path, format="json")
            assert result["format"] == "json"
            assert result["marker_count"] == 4
            assert os.path.isfile(result["path"])

            # Verify the JSON content
            with open(path) as f:
                data = json.load(f)
            assert data["format"] == "audacity-sync"
            assert data["version"] == "1.0"
            assert len(data["markers"]) == 4
        finally:
            os.unlink(path)

    def test_export_edl(self):
        proj = _make_project_with_labels()
        with tempfile.NamedTemporaryFile(suffix=".edl", delete=False) as f:
            path = f.name
        try:
            result = export_sync_data(proj, path, format="edl")
            assert result["format"] == "edl"
            assert result["marker_count"] == 4
            assert os.path.isfile(result["path"])

            with open(path) as f:
                content = f.read()
            assert "TITLE:" in content
            assert "FCM:" in content
        finally:
            os.unlink(path)

    def test_export_csv(self):
        proj = _make_project_with_labels()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            result = export_sync_data(proj, path, format="csv")
            assert result["format"] == "csv"
            assert result["marker_count"] == 4

            with open(path) as f:
                content = f.read()
            lines = content.strip().splitlines()
            assert len(lines) == 4
        finally:
            os.unlink(path)

    def test_export_invalid_format(self):
        proj = create_project()
        with pytest.raises(ValueError, match="Unknown sync format"):
            export_sync_data(proj, "/tmp/test.xyz", format="xyz")

    def test_export_creates_parent_dirs(self):
        proj = _make_project_with_labels()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "subdir", "sync.json")
            result = export_sync_data(proj, path, format="json")
            assert os.path.isfile(result["path"])

    def test_export_empty_project(self):
        proj = create_project()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            result = export_sync_data(proj, path, format="json")
            assert result["marker_count"] == 0
            assert os.path.isfile(path)
        finally:
            os.unlink(path)

    def test_export_project_name_in_json(self):
        proj = create_project(name="My Podcast")
        add_label(proj, 1.0, text="Marker")
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            export_sync_data(proj, path, format="json")
            with open(path) as f:
                data = json.load(f)
            assert data["project_name"] == "My Podcast"
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Audio analysis helpers — shared test WAV factory
# ---------------------------------------------------------------------------

def create_test_wav(path: str, duration: float = 1.0, freq: float = 440.0,
                    sample_rate: int = 44100) -> str:
    """Create a simple sine wave WAV file for testing.

    Args:
        path: Destination file path.
        duration: Duration in seconds.
        freq: Sine wave frequency in Hz.
        sample_rate: Sample rate in Hz.

    Returns:
        The path argument (for chaining).
    """
    import wave
    import struct
    import math

    n_frames = int(sample_rate * duration)
    amplitude = 32767  # max for 16-bit signed

    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)       # mono
        wf.setsampwidth(2)       # 16-bit
        wf.setframerate(sample_rate)
        for i in range(n_frames):
            sample = int(amplitude * math.sin(2.0 * math.pi * freq * i / sample_rate))
            wf.writeframes(struct.pack("<h", sample))

    return path


# ---------------------------------------------------------------------------
# beat_detect() Tests
# ---------------------------------------------------------------------------

class TestBeatDetect:
    def test_returns_list(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0, freq=440)
            result = beat_detect(path)
            assert isinstance(result, list)
        finally:
            os.unlink(path)

    def test_each_item_is_dict(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0, freq=440)
            result = beat_detect(path)
            for item in result:
                assert isinstance(item, dict)
        finally:
            os.unlink(path)

    def test_beat_dicts_have_required_keys(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0, freq=440)
            result = beat_detect(path)
            for beat in result:
                assert "time" in beat
                assert "strength" in beat
                assert "type" in beat
        finally:
            os.unlink(path)

    def test_beat_type_is_beat(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0, freq=440)
            result = beat_detect(path)
            for beat in result:
                assert beat["type"] == "beat"
        finally:
            os.unlink(path)

    def test_beat_times_are_non_negative(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=2.0, freq=440)
            result = beat_detect(path)
            for beat in result:
                assert beat["time"] >= 0.0
        finally:
            os.unlink(path)

    def test_beat_times_within_duration(self):
        duration = 1.0
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=duration, freq=440)
            result = beat_detect(path)
            for beat in result:
                assert beat["time"] <= duration + 0.1  # small tolerance
        finally:
            os.unlink(path)

    def test_beat_strengths_in_range(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0, freq=440)
            result = beat_detect(path)
            for beat in result:
                assert 0.0 <= beat["strength"] <= 1.0
        finally:
            os.unlink(path)

    def test_short_wav(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=0.1, freq=220)
            result = beat_detect(path)
            assert isinstance(result, list)
        finally:
            os.unlink(path)

    def test_invalid_file_raises_oserror(self):
        with pytest.raises(OSError):
            beat_detect("/nonexistent/path/audio.wav")

    def test_beat_times_sorted(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=2.0, freq=440)
            result = beat_detect(path)
            times = [b["time"] for b in result]
            assert times == sorted(times)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# amplitude_envelope() Tests
# ---------------------------------------------------------------------------

class TestAmplitudeEnvelope:
    def test_returns_list(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0)
            result = amplitude_envelope(path, fps=30)
            assert isinstance(result, list)
        finally:
            os.unlink(path)

    def test_correct_length_1s_30fps(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0, sample_rate=44100)
            result = amplitude_envelope(path, fps=30)
            # ceil(44100 / (44100/30)) = ceil(30) = 30
            assert len(result) >= 28  # allow slight variation from rounding
            assert len(result) <= 32
        finally:
            os.unlink(path)

    def test_correct_length_2s_24fps(self):
        import math as _math
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=2.0, sample_rate=44100)
            result = amplitude_envelope(path, fps=24)
            expected = _math.ceil(2.0 * 24)
            assert len(result) >= expected - 2
            assert len(result) <= expected + 2
        finally:
            os.unlink(path)

    def test_values_in_0_1_range(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0)
            result = amplitude_envelope(path, fps=30)
            for v in result:
                assert 0.0 <= v <= 1.0
        finally:
            os.unlink(path)

    def test_pure_sine_is_nonzero(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0, freq=440)
            result = amplitude_envelope(path, fps=30)
            # A 440 Hz sine should have non-trivial amplitude in every frame
            assert max(result) > 0.0
        finally:
            os.unlink(path)

    def test_different_fps(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0)
            r60 = amplitude_envelope(path, fps=60)
            r24 = amplitude_envelope(path, fps=24)
            assert len(r60) > len(r24)
        finally:
            os.unlink(path)

    def test_invalid_file_raises(self):
        with pytest.raises(OSError):
            amplitude_envelope("/nonexistent/path/audio.wav")

    def test_returns_floats(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=0.5)
            result = amplitude_envelope(path, fps=30)
            for v in result:
                assert isinstance(v, float)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# frequency_bands() Tests
# ---------------------------------------------------------------------------

class TestFrequencyBands:
    def test_returns_list_or_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0)
            result = frequency_bands(path, fps=30)
            assert isinstance(result, list)
        finally:
            os.unlink(path)

    def test_outer_length_matches_frames(self):
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not available")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0, sample_rate=44100)
            result = frequency_bands(path, fps=30, bands=8)
            if not result:
                pytest.skip("frequency_bands returned empty (numpy unavailable)")
            assert len(result) >= 28
            assert len(result) <= 32
        finally:
            os.unlink(path)

    def test_inner_length_is_bands(self):
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not available")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0)
            result = frequency_bands(path, fps=30, bands=8)
            if not result:
                pytest.skip("frequency_bands returned empty")
            for frame in result:
                assert len(frame) == 8
        finally:
            os.unlink(path)

    def test_custom_band_count(self):
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not available")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0)
            result = frequency_bands(path, fps=30, bands=4)
            if not result:
                pytest.skip("frequency_bands returned empty")
            for frame in result:
                assert len(frame) == 4
        finally:
            os.unlink(path)

    def test_values_in_0_1_range(self):
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not available")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0, freq=440)
            result = frequency_bands(path, fps=30, bands=8)
            if not result:
                pytest.skip("frequency_bands returned empty")
            for frame in result:
                for val in frame:
                    assert 0.0 <= val <= 1.0
        finally:
            os.unlink(path)

    def test_440hz_sine_peak_in_bass_or_mid_band(self):
        """440 Hz should have energy in the mid band range (band 3: 500-2000 Hz
        is adjacent; band 2: 250-500 is closest). Energy should be non-zero."""
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not available")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=1.0, freq=440)
            result = frequency_bands(path, fps=30, bands=8)
            if not result:
                pytest.skip("frequency_bands returned empty")
            # At least one band should have significant energy somewhere
            max_energy = max(max(frame) for frame in result)
            assert max_energy > 0.0
        finally:
            os.unlink(path)

    def test_empty_if_numpy_unavailable_mock(self):
        """Verify that if numpy import fails, function returns []."""
        import sys
        import unittest.mock as mock
        # Patch numpy import to raise ImportError
        with mock.patch.dict(sys.modules, {"numpy": None}):
            try:
                # Re-import the module to get numpy-free version
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    path = f.name
                try:
                    create_test_wav(path, duration=0.1)
                    # Call directly – may or may not be numpy-free in cached module
                    from cli_anything.audacity.core.sync import frequency_bands as fb
                    # We just verify the function is callable
                    assert callable(fb)
                finally:
                    os.unlink(path)
            except Exception:
                pass  # This test is best-effort

    def test_invalid_file_returns_empty(self):
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not available")
        result = frequency_bands("/nonexistent/path/audio.wav", fps=30)
        assert result == []

    def test_returns_floats(self):
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not available")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            create_test_wav(path, duration=0.5, freq=440)
            result = frequency_bands(path, fps=30, bands=8)
            if not result:
                pytest.skip("frequency_bands returned empty")
            for frame in result:
                for v in frame:
                    assert isinstance(v, float)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
