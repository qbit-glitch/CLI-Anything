"""
session_bridge.py — Maps session_id UUIDs to project file paths on disk.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

SESSION_DIR = Path.home() / ".cli-anything-mcp" / "sessions"
INDEX_FILE = Path.home() / ".cli-anything-mcp" / "sessions.json"


@dataclass
class SessionEntry:
    session_id: str
    harness: str
    project_path: str
    created_at: float


class SessionBridge:
    def __init__(
        self,
        session_dir: Path | None = None,
        index_file: Path | None = None,
    ) -> None:
        self._session_dir: Path = session_dir if session_dir is not None else SESSION_DIR
        self._index_file: Path = index_file if index_file is not None else INDEX_FILE
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, SessionEntry] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def new_session(self, harness: str, project_path: str | None = None) -> str:
        """Create a new session and return its session_id (UUID string)."""
        sid = str(uuid.uuid4())
        if project_path is None:
            project_path = str(self._session_dir / f"{sid}.json")
        entry = SessionEntry(
            session_id=sid,
            harness=harness,
            project_path=project_path,
            created_at=time.time(),
        )
        self._sessions[sid] = entry
        self._save()
        return sid

    def get_project_path(self, session_id: str) -> str:
        """Return project file path for the given session_id.

        Raises KeyError if the session does not exist.
        """
        return self._sessions[session_id].project_path

    def delete_session(self, session_id: str) -> None:
        """Remove a session and delete its project file if it exists."""
        entry = self._sessions.pop(session_id, None)
        if entry is not None:
            p = Path(entry.project_path)
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
        self._save()

    def list_sessions(self) -> list[dict]:
        """Return all sessions as a list of dicts."""
        return [asdict(e) for e in self._sessions.values()]

    def cleanup_stale(self, max_age_hours: int = 24) -> int:
        """Remove sessions older than max_age_hours.  Returns count removed."""
        cutoff = time.time() - max_age_hours * 3600
        stale = [
            sid
            for sid, entry in self._sessions.items()
            if entry.created_at < cutoff
        ]
        for sid in stale:
            self.delete_session(sid)
        return len(stale)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load sessions index from _index_file."""
        if not self._index_file.exists():
            return
        try:
            raw = json.loads(self._index_file.read_text(encoding="utf-8"))
            session_dir_resolved = self._session_dir.resolve()
            for item in raw:
                entry = SessionEntry(**item)
                # Guard against tampered index redirecting project writes to
                # arbitrary paths (e.g., ~/.ssh/authorized_keys).
                try:
                    p = Path(entry.project_path).resolve()
                    if not p.is_relative_to(session_dir_resolved):
                        continue
                except Exception:
                    continue
                self._sessions[entry.session_id] = entry
        except Exception:
            # Corrupted index — start fresh
            self._sessions = {}

    def _save(self) -> None:
        """Persist sessions index to _index_file atomically."""
        self._index_file.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(e) for e in self._sessions.values()]
        tmp = self._index_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self._index_file)
