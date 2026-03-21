"""Audacity CLI - Audio sync export module.

Exports label/marker data in interoperable formats (JSON, EDL, CSV)
for bridging audio markers from Audacity to video editors like Shotcut.

Also provides audio analysis helpers: beat detection, amplitude envelope,
and frequency band decomposition for audio-reactive animation.
"""

import json
import math
import os
import struct
import wave
from typing import Dict, Any, List


def seconds_to_timecode(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.mmm timecode.

    Args:
        seconds: Time in seconds (must be >= 0).

    Returns:
        Timecode string in HH:MM:SS.mmm format.
    """
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    remainder = seconds % 3600
    m = int(remainder // 60)
    s = remainder % 60
    ms = int(round((s - int(s)) * 1000))
    s_int = int(s)
    return f"{h:02d}:{m:02d}:{s_int:02d}.{ms:03d}"


def timecode_to_seconds(tc: str) -> float:
    """Convert HH:MM:SS.mmm timecode to seconds.

    Args:
        tc: Timecode string in HH:MM:SS.mmm format.

    Returns:
        Time in seconds.

    Raises:
        ValueError: If the timecode format is invalid.
    """
    tc = tc.strip()
    parts = tc.split(":")
    if len(parts) == 3:
        h = int(parts[0])
        m = int(parts[1])
        # Handle seconds with optional milliseconds
        s_parts = parts[2].split(".")
        s = int(s_parts[0])
        ms = 0
        if len(s_parts) == 2:
            ms_str = s_parts[1].ljust(3, "0")[:3]
            ms = int(ms_str)
        return h * 3600 + m * 60 + s + ms / 1000.0
    elif len(parts) == 2:
        m = int(parts[0])
        s_parts = parts[1].split(".")
        s = int(s_parts[0])
        ms = 0
        if len(s_parts) == 2:
            ms_str = s_parts[1].ljust(3, "0")[:3]
            ms = int(ms_str)
        return m * 60 + s + ms / 1000.0
    else:
        raise ValueError(
            f"Invalid timecode format: {tc!r}. Expected HH:MM:SS.mmm"
        )


def labels_to_json_markers(project: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Export labels as a JSON marker list.

    Args:
        project: Audacity project dict with a "labels" key.

    Returns:
        List of marker dicts with keys:
            - time: HH:MM:SS.mmm timecode of the start
            - time_seconds: start time in seconds
            - label: label text
            - type: "point" or "range"
            - duration: duration in seconds (0.0 for point labels)
    """
    labels = project.get("labels", [])
    markers = []
    for lbl in labels:
        start = lbl.get("start", 0.0)
        end = lbl.get("end", start)
        is_range = start != end
        duration = round(end - start, 3)
        markers.append({
            "time": seconds_to_timecode(start),
            "time_seconds": round(start, 3),
            "label": lbl.get("text", ""),
            "type": "range" if is_range else "point",
            "duration": duration,
        })
        # For range labels, also include end timecode for convenience
        if is_range:
            markers[-1]["end_time"] = seconds_to_timecode(end)
            markers[-1]["end_seconds"] = round(end, 3)
    return markers


def labels_to_edl(project: Dict[str, Any], title: str = "untitled") -> str:
    """Export labels as CMX 3600 EDL format string.

    The EDL (Edit Decision List) format is a standard interchange format
    for video editing. Each label becomes an event in the EDL.

    Args:
        project: Audacity project dict.
        title: Title line for the EDL file.

    Returns:
        EDL format string.
    """
    labels = project.get("labels", [])
    lines = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]

    for i, lbl in enumerate(labels):
        event_num = i + 1
        start = lbl.get("start", 0.0)
        end = lbl.get("end", start)
        if start == end:
            # Point label: use a minimal duration
            end = start + 0.001

        src_in = seconds_to_timecode(start)
        src_out = seconds_to_timecode(end)
        rec_in = src_in
        rec_out = src_out

        # Event line: NUM  REEL  TYPE  TRANSITION  SRC_IN  SRC_OUT  REC_IN  REC_OUT
        line = (
            f"{event_num:03d}  AX       AA/V  C        "
            f"{src_in} {src_out} {rec_in} {rec_out}"
        )
        lines.append(line)

        # Comment with label text
        text = lbl.get("text", "")
        if text:
            lines.append(f"* FROM CLIP NAME: {text}")
        lines.append("")

    return "\n".join(lines)


def labels_to_csv(project: Dict[str, Any]) -> str:
    """Export labels in Audacity's native tab-separated format.

    Format: start_time<tab>end_time<tab>label_text
    One label per line.

    Args:
        project: Audacity project dict.

    Returns:
        Tab-separated text string.
    """
    labels = project.get("labels", [])
    lines = []
    for lbl in labels:
        start = lbl.get("start", 0.0)
        end = lbl.get("end", start)
        text = lbl.get("text", "")
        lines.append(f"{start:.6f}\t{end:.6f}\t{text}")
    return "\n".join(lines)


def export_sync_data(
    project: Dict[str, Any],
    output_path: str,
    format: str = "json",
) -> Dict[str, Any]:
    """Export sync data to a file.

    Args:
        project: Audacity project dict.
        output_path: Path to write the sync file.
        format: Output format - "json", "edl", or "csv".

    Returns:
        Dict with keys: path, format, marker_count.

    Raises:
        ValueError: If format is not recognized.
    """
    format = format.lower()
    if format not in ("json", "edl", "csv"):
        raise ValueError(
            f"Unknown sync format: {format!r}. Use 'json', 'edl', or 'csv'."
        )

    labels = project.get("labels", [])

    if format == "json":
        markers = labels_to_json_markers(project)
        data = {
            "format": "audacity-sync",
            "version": "1.0",
            "project_name": project.get("name", "untitled"),
            "markers": markers,
        }
        content = json.dumps(data, indent=2)
    elif format == "edl":
        title = project.get("name", "untitled")
        content = labels_to_edl(project, title)
    elif format == "csv":
        content = labels_to_csv(project)

    # Ensure parent directory exists
    parent = os.path.dirname(os.path.abspath(output_path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "path": os.path.abspath(output_path),
        "format": format,
        "marker_count": len(labels),
    }


# ---------------------------------------------------------------------------
# Audio analysis helpers
# ---------------------------------------------------------------------------

def _read_wav_samples(audio_file: str):
    """Read a WAV file and return (samples_list, sample_rate, n_channels).

    Samples are raw integer values (not normalized). Returns a flat list
    of mono samples (averaged across channels if stereo).

    Raises:
        OSError: If the file cannot be opened.
        wave.Error: If the file is not a valid WAV.
    """
    with wave.open(audio_file, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_bytes = wf.readframes(n_frames)

    # Decode based on sample width
    if sampwidth == 1:
        # 8-bit unsigned
        fmt = f"{n_frames * n_channels}B"
        raw = list(struct.unpack(fmt, raw_bytes))
        # Centre around zero
        raw = [v - 128 for v in raw]
    elif sampwidth == 2:
        # 16-bit signed little-endian
        fmt = f"<{n_frames * n_channels}h"
        raw = list(struct.unpack(fmt, raw_bytes))
    elif sampwidth == 4:
        # 32-bit signed little-endian
        fmt = f"<{n_frames * n_channels}i"
        raw = list(struct.unpack(fmt, raw_bytes))
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth} bytes")

    # Convert to mono by averaging channels
    if n_channels == 1:
        mono = raw
    else:
        mono = []
        for i in range(n_frames):
            frame_vals = [raw[i * n_channels + c] for c in range(n_channels)]
            mono.append(sum(frame_vals) / n_channels)

    return mono, sample_rate, n_channels


def beat_detect(audio_file: str) -> List[Dict[str, Any]]:
    """Detect beats / onsets in a WAV audio file.

    Tries librosa first for accurate beat tracking. Falls back to a simple
    amplitude-threshold method using only the stdlib wave module.

    Args:
        audio_file: Path to a WAV file.

    Returns:
        List of dicts, each with keys:
            - time (float): Beat time in seconds.
            - strength (float): Normalized beat strength in [0, 1].
            - type (str): Always "beat".
    """
    # --- Try librosa ---
    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(audio_file, sr=None, mono=True)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)

        # Compute onset envelope for strength
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        max_env = float(onset_env.max()) if onset_env.max() > 0 else 1.0

        beats = []
        for frame, t in zip(beat_frames, beat_times):
            strength = float(onset_env[min(frame, len(onset_env) - 1)]) / max_env
            beats.append({
                "time": float(t),
                "strength": round(strength, 4),
                "type": "beat",
            })
        return beats

    except ImportError:
        pass
    except Exception:
        pass

    # --- Fallback: amplitude-threshold onset detection ---
    try:
        mono, sample_rate, _ = _read_wav_samples(audio_file)
    except Exception as exc:
        raise OSError(f"Cannot read audio file {audio_file!r}: {exc}") from exc

    if not mono:
        return []

    n_frames = len(mono)
    duration = n_frames / sample_rate

    # Use ~23ms hop (512 samples at 22050 Hz) for onset envelope
    hop = max(1, sample_rate // 43)  # ~23ms hops
    window = max(1, hop * 2)

    # Compute RMS over sliding window
    rms_frames = []
    for i in range(0, n_frames, hop):
        chunk = mono[i: i + window]
        if not chunk:
            break
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))
        rms_frames.append(rms)

    if not rms_frames:
        return []

    max_rms = max(rms_frames) or 1.0

    # Detect onsets: local maxima above 30% of peak that are stronger than neighbours
    beats = []
    threshold = max_rms * 0.3
    min_gap_frames = max(1, int(0.15 * sample_rate / hop))  # 150ms min gap between beats

    last_beat_idx = -min_gap_frames - 1
    for i in range(1, len(rms_frames) - 1):
        v = rms_frames[i]
        if (
            v > threshold
            and v >= rms_frames[i - 1]
            and v >= rms_frames[i + 1]
            and (i - last_beat_idx) >= min_gap_frames
        ):
            t = (i * hop) / sample_rate
            strength = round(v / max_rms, 4)
            beats.append({"time": round(t, 4), "strength": strength, "type": "beat"})
            last_beat_idx = i

    return beats


def amplitude_envelope(audio_file: str, fps: int = 30) -> List[float]:
    """Compute per-frame RMS amplitude for an audio file.

    Uses the stdlib wave module — no external dependencies required.

    Args:
        audio_file: Path to a WAV file.
        fps: Target frames per second for output.

    Returns:
        List of float RMS values, one per frame. Length is ceil(duration * fps).
        Values are normalized to [0, 1] relative to the peak RMS.

    Raises:
        OSError: If the file cannot be read.
    """
    try:
        mono, sample_rate, _ = _read_wav_samples(audio_file)
    except Exception as exc:
        raise OSError(f"Cannot read audio file {audio_file!r}: {exc}") from exc

    if not mono:
        return []

    n_samples = len(mono)
    samples_per_frame = max(1, sample_rate // fps)
    n_output_frames = math.ceil(n_samples / samples_per_frame)

    rms_values = []
    for frame_idx in range(n_output_frames):
        start = frame_idx * samples_per_frame
        end = min(start + samples_per_frame, n_samples)
        chunk = mono[start:end]
        if not chunk:
            rms_values.append(0.0)
            continue
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))
        rms_values.append(rms)

    # Normalize to [0, 1]
    peak = max(rms_values) if rms_values else 1.0
    if peak == 0.0:
        peak = 1.0

    return [round(v / peak, 6) for v in rms_values]


def frequency_bands(
    audio_file: str,
    fps: int = 30,
    bands: int = 8,
) -> List[List[float]]:
    """Compute per-frame frequency band energies for an audio file.

    Uses numpy FFT for spectral analysis. Returns an empty list if numpy
    is not available.

    The 8 default frequency bands correspond to:
        0: sub-bass    (20–60 Hz)
        1: bass        (60–250 Hz)
        2: low-mid     (250–500 Hz)
        3: mid         (500–2000 Hz)
        4: upper-mid   (2000–4000 Hz)
        5: presence    (4000–6000 Hz)
        6: brilliance  (6000–12000 Hz)
        7: air         (12000–20000 Hz)

    Args:
        audio_file: Path to a WAV file.
        fps: Target frames per second for output.
        bands: Number of frequency bands (splits spectrum evenly on log scale).

    Returns:
        List of lists: outer index = frame, inner index = band energy [0, 1].
        Returns [] if numpy is unavailable or the file cannot be read.
    """
    try:
        import numpy as np
    except ImportError:
        return []

    try:
        mono, sample_rate, _ = _read_wav_samples(audio_file)
    except Exception:
        return []

    if not mono:
        return []

    mono_arr = np.array(mono, dtype=np.float64)
    n_samples = len(mono_arr)
    samples_per_frame = max(1, sample_rate // fps)
    n_output_frames = math.ceil(n_samples / samples_per_frame)

    # Frequency boundaries for 8 standard bands (Hz)
    # Clamp to Nyquist
    nyquist = sample_rate / 2.0
    _standard_boundaries = [20, 60, 250, 500, 2000, 4000, 6000, 12000, 20000]

    if bands == 8 and len(_standard_boundaries) >= bands + 1:
        boundaries = [min(f, nyquist) for f in _standard_boundaries]
    else:
        # Log-spaced bands from 20 Hz to Nyquist
        log_min = math.log10(max(20, 1))
        log_max = math.log10(max(nyquist, 21))
        boundaries = [10 ** (log_min + (log_max - log_min) * i / bands)
                      for i in range(bands + 1)]

    result = []
    # Track per-band max for normalization
    band_max = [0.0] * bands

    raw_frames = []
    for frame_idx in range(n_output_frames):
        start = frame_idx * samples_per_frame
        end = min(start + samples_per_frame, n_samples)
        chunk = mono_arr[start:end]

        if len(chunk) < 2:
            raw_frames.append([0.0] * bands)
            continue

        # Apply Hann window
        window = np.hanning(len(chunk))
        windowed = chunk * window

        # FFT magnitude spectrum
        fft_mag = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(len(chunk), d=1.0 / sample_rate)

        # Compute energy in each band
        frame_bands = []
        for b in range(bands):
            lo = boundaries[b]
            hi = boundaries[b + 1] if b + 1 < len(boundaries) else nyquist
            mask = (freqs >= lo) & (freqs < hi)
            energy = float(np.sqrt(np.mean(fft_mag[mask] ** 2))) if mask.any() else 0.0
            frame_bands.append(energy)
            if energy > band_max[b]:
                band_max[b] = energy

        raw_frames.append(frame_bands)

    # Normalize each band to [0, 1]
    for frame_bands in raw_frames:
        normalized = []
        for b in range(bands):
            peak = band_max[b] if band_max[b] > 0 else 1.0
            normalized.append(round(frame_bands[b] / peak, 6))
        result.append(normalized)

    return result
