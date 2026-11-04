"""App-wide settings (CLAUDE.md §8.3): one small JSON file, separate from saves.

Settings are preferences, not progress, so they never go in a save slot and a
broken or missing file just means defaults. Unknown keys are ignored, so an
older app can read a newer app's file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tidewrack.services.storage import data_dir


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    log_visible: bool = True
    log_share: float = Field(default=0.4, ge=0.1, le=0.8)  # of the game screen's text area


def settings_path() -> Path:
    return data_dir() / "settings.json"


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Settings:
        try:
            return Settings.model_validate(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, ValidationError):
            return Settings()

    def save(self, settings: Settings) -> None:
        """Atomic, like slot saves: a kill mid-write leaves the old file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(settings.model_dump_json(indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
