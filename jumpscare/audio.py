"""Audio playback through pygame.mixer. Several sounds can overlap."""

import logging
import os
from pathlib import Path

import numpy as np

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402
import pygame.sndarray  # noqa: E402

log = logging.getLogger(__name__)


def trim_silence(samples: np.ndarray, threshold: float) -> np.ndarray:
    """Drop leading and trailing samples quieter than threshold (fraction of full scale).

    samples is (frames,) or (frames, channels). Fully silent clips are returned unchanged.
    """
    if threshold <= 0 or samples.size == 0:
        return samples
    full_scale = 1.0 if samples.dtype.kind == "f" else float(np.iinfo(samples.dtype).max)
    level = np.abs(samples.astype(np.float32))
    if level.ndim > 1:
        level = level.max(axis=1)
    loud = np.flatnonzero(level > threshold * full_scale)
    if loud.size == 0:
        return samples
    return samples[loud[0] : loud[-1] + 1]


class AudioPlayer:
    def __init__(self, silence_threshold: float = 0.0) -> None:
        self._silence_threshold = silence_threshold
        self._cache: dict[tuple[Path, float], pygame.mixer.Sound] = {}
        try:
            pygame.mixer.init()
            self.available = True
        except pygame.error as exc:
            log.warning("Audio disabled, mixer failed to start: %s", exc)
            self.available = False

    def _load(self, path: Path) -> pygame.mixer.Sound:
        key = (path, path.stat().st_mtime)
        if key not in self._cache:
            sound = pygame.mixer.Sound(str(path))
            samples = pygame.sndarray.array(sound)
            trimmed = trim_silence(samples, self._silence_threshold)
            if len(trimmed) != len(samples):
                sound = pygame.sndarray.make_sound(np.ascontiguousarray(trimmed))
            self._cache[key] = sound
        return self._cache[key]

    def play(self, path: Path, volume: float) -> None:
        if not self.available:
            return
        try:
            sound = self._load(path)
            sound.set_volume(volume)
            sound.play()
        except (pygame.error, OSError) as exc:
            log.warning("Could not play %s: %s", path.name, exc)

    def shutdown(self) -> None:
        if self.available:
            pygame.mixer.quit()
            self.available = False
