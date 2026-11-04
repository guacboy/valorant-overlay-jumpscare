"""Loads and validates config.json."""

import copy
import json
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"

DEFAULTS: dict = {
    "jumpscare_folder": "assets/jumpscares",
    "sound_folder": "assets/sounds",
    "jumpscare_interval_seconds": {"min": 180, "max": 900},
    "jumpscare_duration_ms": 1000,
    "jumpscare_audio_chance": 1.0,
    "jumpscare_volume": 1.0,
    "sounds_enabled": True,
    "sound_interval_seconds": {"min": 60, "max": 300},
    "sound_volume": 0.8,
    "trim_silence_threshold": 0.01,
    "min_gap_seconds": 5,
    "monitor": 0,
    "hotkeys": {
        "test_jumpscare": "ctrl+alt+j",
        "test_sound": "ctrl+alt+k",
        "toggle_pause": "ctrl+alt+p",
    },
}


class ConfigError(ValueError):
    """Raised when config.json contains invalid values."""


@dataclass(frozen=True)
class Interval:
    min: float
    max: float


@dataclass(frozen=True)
class Hotkeys:
    test_jumpscare: str
    test_sound: str
    toggle_pause: str


@dataclass(frozen=True)
class Config:
    jumpscare_folder: Path
    sound_folder: Path
    jumpscare_interval: Interval
    jumpscare_duration_ms: int
    jumpscare_audio_chance: float
    jumpscare_volume: float
    sounds_enabled: bool
    sound_interval: Interval
    sound_volume: float
    trim_silence_threshold: float
    min_gap_seconds: float
    monitor: int
    hotkeys: Hotkeys


def _merge(base: dict, override: dict, prefix: str = "") -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key not in base:
            raise ConfigError(f"Unknown config key: {prefix}{key}")
        if isinstance(base[key], dict):
            if not isinstance(value, dict):
                raise ConfigError(f"{prefix}{key} must be an object")
            merged[key] = _merge(base[key], value, f"{prefix}{key}.")
        else:
            merged[key] = value
    return merged


def _interval(raw: dict, name: str) -> Interval:
    low, high = float(raw["min"]), float(raw["max"])
    if low <= 0 or high < low:
        raise ConfigError(f"{name} needs 0 < min <= max (got min={low}, max={high})")
    return Interval(low, high)


def _fraction(raw: dict, name: str) -> float:
    value = float(raw[name])
    if not 0 <= value <= 1:
        raise ConfigError(f"{name} must be between 0 and 1 (got {value})")
    return value


def _non_negative_int(raw: dict, name: str, allow_zero: bool = True) -> int:
    value = int(raw[name])
    if value < 0 or (value == 0 and not allow_zero):
        raise ConfigError(f"{name} must be {'>= 0' if allow_zero else '> 0'} (got {value})")
    return value


def _non_negative_float(raw: dict, name: str) -> float:
    value = float(raw[name])
    if value < 0:
        raise ConfigError(f"{name} must be >= 0 (got {value})")
    return value


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Read config from path, filling in defaults. A missing file means all defaults."""
    path = Path(path)
    user: dict = {}
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    raw = _merge(DEFAULTS, user)
    base_dir = path.resolve().parent

    def folder(name: str) -> Path:
        p = Path(raw[name])
        return p if p.is_absolute() else base_dir / p

    return Config(
        jumpscare_folder=folder("jumpscare_folder"),
        sound_folder=folder("sound_folder"),
        jumpscare_interval=_interval(raw["jumpscare_interval_seconds"], "jumpscare_interval_seconds"),
        jumpscare_duration_ms=_non_negative_int(raw, "jumpscare_duration_ms", allow_zero=False),
        jumpscare_audio_chance=_fraction(raw, "jumpscare_audio_chance"),
        jumpscare_volume=_fraction(raw, "jumpscare_volume"),
        sounds_enabled=bool(raw["sounds_enabled"]),
        sound_interval=_interval(raw["sound_interval_seconds"], "sound_interval_seconds"),
        sound_volume=_fraction(raw, "sound_volume"),
        trim_silence_threshold=_fraction(raw, "trim_silence_threshold"),
        min_gap_seconds=_non_negative_float(raw, "min_gap_seconds"),
        monitor=_non_negative_int(raw, "monitor"),
        hotkeys=Hotkeys(**{k: str(v).strip() for k, v in raw["hotkeys"].items()}),
    )
