"""Keeps jumpscares and audio cues from overlapping."""

import time
from typing import Callable


class PlaybackGate:
    """Tracks when the current playback ends so the next one starts at least gap_s seconds later.

    Visuals (images, GIFs, videos) have no known length up front, so they hold the gate open
    until release() is called when the overlay finishes. Sounds occupy it for their length.
    """

    def __init__(self, gap_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._gap = gap_s
        self._clock = clock
        self._end = float("-inf")
        self._open_ended = False

    def occupy(self, length_s: float = 0.0, open_ended: bool = False) -> None:
        self._end = max(self._end, self._clock() + length_s)
        self._open_ended = self._open_ended or open_ended

    def release(self) -> None:
        """End an open-ended playback now. Any longer sound that is still playing keeps counting."""
        if self._open_ended:
            self._open_ended = False
            self._end = max(self._end, self._clock())

    def wait_s(self) -> float | None:
        """Seconds until the next playback may start: 0 when free, None while a visual is on screen."""
        if self._open_ended:
            return None
        return max(0.0, self._end + self._gap - self._clock())
