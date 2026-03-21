"""Shotcut CLI - Audio sync import module.

Imports sync marker data exported from Audacity CLI and applies it
to the Shotcut timeline. Supports JSON and CSV sync formats, with
optional audio clip placement at marker positions.
"""

import json
import os
import re
from typing import Optional

from lxml import etree

from ..utils import mlt_xml
from ..utils.time import seconds_to_frames, frames_to_timecode
from .session import Session


def import_audio_sync(
    session: Session,
    sync_file: str,
    audio_file: Optional[str] = None,
    track_index: Optional[int] = None,
    format: str = "auto",
) -> dict:
    """Import sync data and optionally place audio clips.

    If audio_file is provided, adds audio clip to track at each range
    marker position. If no audio_file, only creates timeline guide markers.

    Args:
        session: Active Shotcut session.
        sync_file: Path to the sync file (JSON, CSV, or EDL).
        audio_file: Optional path to an audio file to place at markers.
        track_index: Track index for placing audio clips.
        format: File format - "auto", "json", "csv", or "edl".
            If "auto", detects from file extension.

    Returns:
        Dict with keys: markers_imported, clips_added.

    Raises:
        FileNotFoundError: If sync_file or audio_file does not exist.
        ValueError: If format is unrecognized or file is unparseable.
    """
    if not os.path.isfile(sync_file):
        raise FileNotFoundError(f"Sync file not found: {sync_file}")
    if audio_file and not os.path.isfile(audio_file):
        raise FileNotFoundError(f"Audio file not found: {audio_file}")

    session.checkpoint()

    markers = _parse_sync_file(sync_file, format)

    # Create markers on the tractor
    marker_result = create_markers_from_sync(session, markers)

    clips_added = 0
    if audio_file and track_index is not None:
        clips_added = _place_audio_clips(
            session, markers, audio_file, track_index
        )

    return {
        "markers_imported": marker_result["markers_created"],
        "clips_added": clips_added,
    }


def _parse_sync_file(sync_file: str, format: str) -> list[dict]:
    """Parse sync file. Auto-detect format from extension if format=='auto'.

    Args:
        sync_file: Path to the sync file.
        format: "auto", "json", "csv", or "edl".

    Returns:
        List of marker dicts with keys: time_seconds, label, type, duration.
    """
    format = format.lower()
    if format == "auto":
        ext = os.path.splitext(sync_file)[1].lower()
        format_map = {".json": "json", ".csv": "csv", ".tsv": "csv",
                      ".txt": "csv", ".edl": "edl"}
        format = format_map.get(ext, "json")

    with open(sync_file, "r", encoding="utf-8") as f:
        content = f.read()

    if format == "json":
        return _parse_json_sync(content)
    elif format == "csv":
        return _parse_csv_sync(content)
    elif format == "edl":
        return _parse_edl_sync(content)
    else:
        raise ValueError(
            f"Unknown sync format: {format!r}. Use 'json', 'csv', or 'edl'."
        )


def _parse_json_sync(content: str) -> list[dict]:
    """Parse JSON sync file content.

    Expects the format produced by Audacity CLI's export_sync_data:
    {
        "format": "audacity-sync",
        "markers": [
            {"time_seconds": float, "label": str, "type": str, "duration": float},
            ...
        ]
    }

    Returns:
        List of normalized marker dicts.
    """
    data = json.loads(content)

    # Handle wrapped format (audacity-sync envelope)
    if isinstance(data, dict) and "markers" in data:
        raw_markers = data["markers"]
    elif isinstance(data, list):
        raw_markers = data
    else:
        raise ValueError("JSON sync file must contain a 'markers' list or be a list")

    markers = []
    for m in raw_markers:
        markers.append({
            "time_seconds": float(m.get("time_seconds", 0.0)),
            "label": m.get("label", ""),
            "type": m.get("type", "point"),
            "duration": float(m.get("duration", 0.0)),
        })
    return markers


def _parse_csv_sync(content: str) -> list[dict]:
    """Parse CSV/TSV sync file content.

    Expects Audacity's tab-separated label format:
        start_time<tab>end_time<tab>label_text

    Returns:
        List of normalized marker dicts.
    """
    markers = []
    for line in content.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            # Try comma separation as fallback
            parts = line.split(",")
        if len(parts) < 2:
            continue

        try:
            start = float(parts[0])
            end = float(parts[1])
        except (ValueError, IndexError):
            continue

        text = parts[2].strip() if len(parts) > 2 else ""
        is_range = start != end
        duration = round(end - start, 3)

        markers.append({
            "time_seconds": round(start, 3),
            "label": text,
            "type": "range" if is_range else "point",
            "duration": duration,
        })
    return markers


def _parse_edl_sync(content: str) -> list[dict]:
    """Parse CMX 3600 EDL format sync data.

    Extracts events and their timecodes, plus any clip name comments.

    Returns:
        List of normalized marker dicts.
    """
    markers = []
    lines = content.strip().splitlines()
    current_label = ""

    for line in lines:
        line = line.strip()

        # Event line pattern: NUM  REEL  TYPE  TRANS  SRC_IN  SRC_OUT  REC_IN  REC_OUT
        event_match = re.match(
            r'^\d{3}\s+\S+\s+\S+\s+\S+\s+'
            r'(\d{2}:\d{2}:\d{2}\.\d{3})\s+'
            r'(\d{2}:\d{2}:\d{2}\.\d{3})\s+',
            line,
        )
        if event_match:
            src_in = event_match.group(1)
            src_out = event_match.group(2)
            start = _tc_to_seconds(src_in)
            end = _tc_to_seconds(src_out)
            is_range = abs(end - start) > 0.002
            duration = round(end - start, 3)

            markers.append({
                "time_seconds": round(start, 3),
                "label": current_label,
                "type": "range" if is_range else "point",
                "duration": max(duration, 0.0),
            })
            current_label = ""
            continue

        # Comment line with clip name
        clip_match = re.match(r'^\*\s*FROM CLIP NAME:\s*(.*)', line)
        if clip_match:
            current_label = clip_match.group(1).strip()
            # Apply label to the last marker if it has no label
            if markers and not markers[-1]["label"]:
                markers[-1]["label"] = current_label
            current_label = ""

    return markers


def _tc_to_seconds(tc: str) -> float:
    """Convert HH:MM:SS.mmm timecode to seconds."""
    parts = tc.split(":")
    if len(parts) == 3:
        h = int(parts[0])
        m = int(parts[1])
        s_parts = parts[2].split(".")
        s = int(s_parts[0])
        ms = int(s_parts[1].ljust(3, "0")[:3]) if len(s_parts) > 1 else 0
        return h * 3600 + m * 60 + s + ms / 1000.0
    return 0.0


def create_markers_from_sync(
    session: Session,
    markers: list[dict],
) -> dict:
    """Create MLT markers from parsed sync data.

    Stores markers as properties on the main tractor element,
    using Shotcut's marker property convention.

    Args:
        session: Active Shotcut session.
        markers: List of marker dicts from parsing.

    Returns:
        Dict with keys: markers_created.
    """
    if not session.is_open:
        raise RuntimeError("No project is open")

    tractor = session.get_main_tractor()

    # Get existing marker count
    existing_count = 0
    while mlt_xml.get_property(
        tractor, f"shotcut:marker.{existing_count}.text"
    ) is not None:
        existing_count += 1

    created = 0
    for marker in markers:
        idx = existing_count + created
        time_seconds = marker.get("time_seconds", 0.0)
        label = marker.get("label", "")
        marker_type = marker.get("type", "point")
        duration = marker.get("duration", 0.0)

        # Get fps for frame conversion
        profile = session.get_profile()
        fps_num = int(profile.get("frame_rate_num", 30000))
        fps_den = int(profile.get("frame_rate_den", 1001))

        start_frames = seconds_to_frames(time_seconds, fps_num, fps_den)
        start_tc = frames_to_timecode(start_frames, fps_num, fps_den)

        mlt_xml.set_property(tractor, f"shotcut:marker.{idx}.text", label)
        mlt_xml.set_property(tractor, f"shotcut:marker.{idx}.start", start_tc)
        mlt_xml.set_property(
            tractor, f"shotcut:marker.{idx}.type", marker_type
        )

        if marker_type == "range" and duration > 0:
            end_seconds = time_seconds + duration
            end_frames = seconds_to_frames(end_seconds, fps_num, fps_den)
            end_tc = frames_to_timecode(end_frames, fps_num, fps_den)
            mlt_xml.set_property(
                tractor, f"shotcut:marker.{idx}.end", end_tc
            )
            mlt_xml.set_property(
                tractor, f"shotcut:marker.{idx}.duration",
                str(round(duration, 3)),
            )

        created += 1

    # Store total marker count
    mlt_xml.set_property(
        tractor, "shotcut:marker.count", str(existing_count + created)
    )

    return {"markers_created": created}


def _place_audio_clips(
    session: Session,
    markers: list[dict],
    audio_file: str,
    track_index: int,
) -> int:
    """Place audio clips on a track at marker positions.

    Only range markers are used for clip placement since they have
    meaningful durations.

    Returns:
        Number of clips added.
    """
    profile = session.get_profile()
    fps_num = int(profile.get("frame_rate_num", 30000))
    fps_den = int(profile.get("frame_rate_den", 1001))

    audio_file = os.path.abspath(audio_file)

    # Get the track's playlist
    tractor = session.get_main_tractor()
    tracks = mlt_xml.get_tractor_tracks(tractor)
    if track_index < 0 or track_index >= len(tracks):
        raise IndexError(
            f"Track index {track_index} out of range (0-{len(tracks)-1})"
        )
    producer_id = tracks[track_index].get("producer")
    playlist = mlt_xml.find_element_by_id(session.root, producer_id)
    if playlist is None:
        raise RuntimeError(
            f"Playlist {producer_id!r} not found for track {track_index}"
        )

    clips_added = 0
    for marker in markers:
        if marker.get("type") != "range" or marker.get("duration", 0) <= 0:
            continue

        time_seconds = marker.get("time_seconds", 0.0)
        duration = marker.get("duration", 0.0)

        in_frames = seconds_to_frames(time_seconds, fps_num, fps_den)
        out_frames = seconds_to_frames(
            time_seconds + duration, fps_num, fps_den
        )
        in_tc = frames_to_timecode(in_frames, fps_num, fps_den)
        out_tc = frames_to_timecode(out_frames, fps_num, fps_den)

        # Create a producer for this audio clip
        caption = marker.get("label", "") or os.path.basename(audio_file)
        producer = mlt_xml.create_producer(
            session.root, audio_file,
            in_point="00:00:00.000",
            out_point=out_tc,
            caption=caption,
        )

        # Add blank gap before this clip if needed, then add the entry
        mlt_xml.add_entry_to_playlist(
            playlist, producer.get("id"),
            in_point=in_tc,
            out_point=out_tc,
        )
        clips_added += 1

    return clips_added


def list_sync_markers(session: Session) -> list[dict]:
    """List all imported sync markers.

    Args:
        session: Active Shotcut session.

    Returns:
        List of marker dicts with keys: index, text, start, type,
        and optionally end and duration for range markers.
    """
    if not session.is_open:
        raise RuntimeError("No project is open")

    tractor = session.get_main_tractor()
    markers = []
    idx = 0

    while True:
        text = mlt_xml.get_property(
            tractor, f"shotcut:marker.{idx}.text"
        )
        if text is None:
            break

        start = mlt_xml.get_property(
            tractor, f"shotcut:marker.{idx}.start", "00:00:00.000"
        )
        marker_type = mlt_xml.get_property(
            tractor, f"shotcut:marker.{idx}.type", "point"
        )

        marker = {
            "index": idx,
            "text": text,
            "start": start,
            "type": marker_type,
        }

        if marker_type == "range":
            end = mlt_xml.get_property(
                tractor, f"shotcut:marker.{idx}.end"
            )
            duration = mlt_xml.get_property(
                tractor, f"shotcut:marker.{idx}.duration"
            )
            if end:
                marker["end"] = end
            if duration:
                marker["duration"] = duration

        markers.append(marker)
        idx += 1

    return markers
