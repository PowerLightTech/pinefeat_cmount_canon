"""JSON-based configuration persistence for the standalone Pinefeat focuser app.

Stores the last-used connection settings and any number of named connection
profiles (port/baud) in a single JSON file under an OS-appropriate config
directory, without requiring any third-party dependency.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_DIR_NAME = "pinefeat-focuser"
CONFIG_FILE_NAME = "config.json"


def get_config_dir() -> Path:
    """Return (and create) the OS-appropriate config directory for this app."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    path = Path(base) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path() -> Path:
    return get_config_dir() / CONFIG_FILE_NAME


@dataclass
class ConnectionProfile:
    name: str
    port: str
    baudrate: int = 115200


@dataclass
class AppConfig:
    last_port: str | None = None
    last_baudrate: int = 115200
    profiles: list[ConnectionProfile] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "last_port": self.last_port,
            "last_baudrate": self.last_baudrate,
            "profiles": [asdict(p) for p in self.profiles],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        profiles = [
            ConnectionProfile(**p) for p in data.get("profiles", []) if "name" in p
        ]
        return cls(
            last_port=data.get("last_port"),
            last_baudrate=data.get("last_baudrate", 115200),
            profiles=profiles,
        )

    def get_profile(self, name: str) -> ConnectionProfile | None:
        return next((p for p in self.profiles if p.name == name), None)

    def upsert_profile(self, profile: ConnectionProfile) -> None:
        existing = self.get_profile(profile.name)
        if existing:
            self.profiles.remove(existing)
        self.profiles.append(profile)

    def remove_profile(self, name: str) -> bool:
        existing = self.get_profile(name)
        if not existing:
            return False
        self.profiles.remove(existing)
        return True


def load_config(path: Path | None = None) -> AppConfig:
    path = path or get_config_path()
    if not path.exists():
        return AppConfig()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return AppConfig()
    return AppConfig.from_dict(data)


def save_config(config: AppConfig, path: Path | None = None) -> None:
    path = path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)
