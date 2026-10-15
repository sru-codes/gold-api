"""Thread-safe in-memory snapshot store with optional disk persistence."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class SnapshotStore:
    """Holds the latest assembled payload for every section.

    The refresh engine writes sections under a lock; HTTP handlers read a deep
    copy under the same lock. Reads never block on network work because the
    engine only holds the lock while swapping a finished section in.
    """

    SECTIONS = ("gold", "fx", "bars", "macro", "news")

    def __init__(self, state_path: Path | None = None):
        self._lock = threading.RLock()
        self._sections: dict[str, dict[str, Any]] = {}
        self._providers: dict[str, dict[str, Any]] = {}
        self._state_path = Path(state_path) if state_path else None
        self._started_at = _utc_now_iso()
        self._last_cycle_at: str | None = None
        self._cycle_count = 0

    # -- writes -----------------------------------------------------------
    def put_section(self, name: str, data: Any, *, source_url: str | None = None, fetched_at: str | None = None) -> None:
        with self._lock:
            self._sections[name] = {
                "data": data,
                "status": "ok",
                "error": None,
                "source_url": source_url,
                "fetched_at_utc": fetched_at or _utc_now_iso(),
            }

    def put_error(self, name: str, code: str, message: str) -> None:
        with self._lock:
            existing = self._sections.get(name, {})
            self._sections[name] = {
                "data": existing.get("data"),
                "status": "error",
                "error": {"code": code, "message": message},
                "source_url": existing.get("source_url"),
                "fetched_at_utc": existing.get("fetched_at_utc"),
                "failed_at_utc": _utc_now_iso(),
            }

    def put_provider(self, provider_id: str, entry: dict[str, Any]) -> None:
        with self._lock:
            self._providers[provider_id] = {**entry, "updated_at_utc": _utc_now_iso()}

    def mark_cycle(self) -> None:
        with self._lock:
            self._cycle_count += 1
            self._last_cycle_at = _utc_now_iso()

    # -- reads ------------------------------------------------------------
    def section(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._sections.get(name)
            return deepcopy(value) if value is not None else None

    def providers(self) -> list[dict[str, Any]]:
        with self._lock:
            return [deepcopy(v) for v in self._providers.values()]

    def meta(self) -> dict[str, Any]:
        with self._lock:
            return {
                "started_at_utc": self._started_at,
                "last_cycle_at_utc": self._last_cycle_at,
                "cycle_count": self._cycle_count,
                "sections": sorted(self._sections.keys()),
            }

    # -- persistence ------------------------------------------------------
    def save(self) -> None:
        """Best-effort atomic write of the whole store to disk."""
        if self._state_path is None:
            return
        with self._lock:
            payload = {
                "meta": {
                    "started_at_utc": self._started_at,
                    "last_cycle_at_utc": self._last_cycle_at,
                    "cycle_count": self._cycle_count,
                },
                "sections": self._sections,
                "providers": self._providers,
            }
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            tmp.replace(self._state_path)
        except OSError:
            # Persistence is a convenience; never fail a refresh because of it.
            pass

    def load(self) -> bool:
        """Load a previously persisted store, if present."""
        if self._state_path is None or not self._state_path.is_file():
            return False
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        with self._lock:
            self._sections = payload.get("sections", {})
            self._providers = payload.get("providers", {})
            meta = payload.get("meta", {})
            self._started_at = meta.get("started_at_utc", self._started_at)
            self._last_cycle_at = meta.get("last_cycle_at_utc")
            self._cycle_count = int(meta.get("cycle_count", 0))
        return True
