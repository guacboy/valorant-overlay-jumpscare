"""File discovery, random selection and scheduling math. No Qt or audio imports here."""

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, TypeVar

from jumpscare.config import Config, Interval

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
AUDIO_EXTS = (".wav", ".ogg", ".mp3")

T = TypeVar("T")


@dataclass(frozen=True)
class Jumpscare:
    image: Path
    sound: Path | None


def list_files(folder: Path, exts: Sequence[str]) -> list[Path]:
    """Files in folder with one of the given extensions, sorted. Missing folder gives []."""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts)


def paired_audio(image: Path) -> Path | None:
    """Audio file next to the image with the same name, e.g. scream.png + scream.mp3."""
    for ext in AUDIO_EXTS:
        candidate = image.with_suffix(ext)
        if candidate.is_file():
            return candidate
    return None


class RandomPicker:
    """Picks a random item, avoiding the previous pick when there is more than one option."""

    def __init__(self, rng: random.Random):
        self._rng = rng
        self._last = None

    def pick(self, items: Sequence[T]) -> T | None:
        if not items:
            return None
        choices = [i for i in items if i != self._last] or list(items)
        self._last = self._rng.choice(choices)
        return self._last


def random_delay_ms(interval: Interval, rng: random.Random) -> int:
    return int(rng.uniform(interval.min, interval.max) * 1000)


def choose_jumpscare(
    cfg: Config,
    image_picker: RandomPicker,
    sound_picker: RandomPicker,
    rng: random.Random,
) -> Jumpscare | None:
    """Pick an image plus an optional sound. Folders are rescanned so new files are used live."""
    image = image_picker.pick(list_files(cfg.jumpscare_folder, IMAGE_EXTS))
    if image is None:
        return None
    sound = None
    if rng.random() < cfg.jumpscare_audio_chance:
        sound = paired_audio(image) or sound_picker.pick(
            list_files(cfg.jumpscare_sound_folder, AUDIO_EXTS)
        )
    return Jumpscare(image=image, sound=sound)
