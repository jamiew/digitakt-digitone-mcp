"""Per-device on-disk storage: patterns, automation presets, MIDI recordings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

CONFIG_ROOT = Path.home() / ".mcp-config"


@dataclass(frozen=True, slots=True)
class Storage:
    """Resolves and owns the three data directories for one device."""

    patterns: Path
    presets: Path
    recordings: Path

    @classmethod
    def for_device(cls, slug: str, root: Path | None = None) -> Storage:
        base = (root or CONFIG_ROOT) / slug
        storage = cls(
            patterns=base / "patterns",
            presets=base / "presets",
            recordings=base / "recordings",
        )
        storage.ensure()
        return storage

    def ensure(self) -> None:
        for directory in (self.patterns, self.presets, self.recordings):
            directory.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------- helpers

    def pattern_path(self, name: str) -> Path:
        return self.patterns / f"{_strip_suffix(_file_name(name), '.json')}.json"

    def preset_path(self, name: str) -> Path:
        return self.presets / f"{_strip_suffix(_file_name(name), '.json')}.json"

    def recording_path(self, name: str) -> Path:
        return self.recordings / _ensure_suffix(_file_name(name), ".mid")


def _file_name(name: str) -> str:
    """Names come from the model, so refuse anything that would leave the data directory."""
    if not name or name in (".", "..") or Path(name).name != name:
        raise ToolError(f"Invalid name {name!r}: use a plain file name, without folders.")
    return name


def _strip_suffix(name: str, suffix: str) -> str:
    return name[: -len(suffix)] if name.endswith(suffix) else name


def _ensure_suffix(name: str, suffix: str) -> str:
    return name if name.endswith(suffix) else name + suffix


def read_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON object, or None if the file doesn't exist."""
    if not path.exists():
        return None
    with path.open() as handle:
        return json.load(handle)


def write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w") as handle:
        json.dump(data, handle, indent=2)
