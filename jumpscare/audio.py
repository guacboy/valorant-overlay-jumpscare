"""Audio playback through pygame.mixer. Several sounds can overlap."""

import logging
import os
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402

log = logging.getLogger(__name__)


class AudioPlayer:
    def __init__(self) -> None:
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
            self._cache[key] = pygame.mixer.Sound(str(path))
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
