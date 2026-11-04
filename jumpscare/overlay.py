"""Transparent, click-through, always-on-top window that flashes an image or plays a GIF."""

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImageReader, QMovie, QPixmap
from PySide6.QtWidgets import QLabel, QWidget


class JumpscareOverlay(QWidget):
    def __init__(self, monitor: int, scale: float, fade_ms: int) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        # Never steal focus: activating a window can minimize a fullscreen game.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._monitor = monitor
        self._scale = scale
        self._fade_ms = fade_ms
        self._movie: QMovie | None = None

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._start_fade)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setEasingCurve(QEasingCurve.Type.InQuad)
        self._fade.finished.connect(self._finish)

    def _screen_geometry(self) -> QRect:
        screens = QGuiApplication.screens()
        screen = screens[self._monitor] if self._monitor < len(screens) else None
        return (screen or QGuiApplication.primaryScreen()).geometry()

    def show_image(self, path: Path, duration_ms: int) -> bool:
        """Show a still image for duration_ms total (fade included), or play a GIF once through.

        Returns False if the file can't be loaded.
        """
        if path.suffix.lower() == ".gif":
            movie = QMovie(str(path))
            if movie.isValid() and movie.frameCount() > 1:
                self._play_movie(path, movie)
                return True
            # Single-frame GIFs fall through and are treated as still images.

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return False
        self._reset()
        target = self._fit(pixmap.size())
        self._label.setPixmap(
            pixmap.scaled(
                target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        self._present()
        self._hide_timer.start(max(duration_ms - self._fade_ms, 0))
        return True

    def _fit(self, size: QSize) -> QSize:
        """Size that fits inside the screen times scale, keeping aspect ratio."""
        geo = self._screen_geometry()
        bounds = QSize(int(geo.width() * self._scale), int(geo.height() * self._scale))
        return size.scaled(bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def _play_movie(self, path: Path, movie: QMovie) -> None:
        self._reset()
        movie.setScaledSize(self._fit(QImageReader(str(path)).size()))
        movie.frameChanged.connect(self._on_movie_frame)
        self._movie = movie
        self._label.setMovie(movie)
        self._present()
        movie.start()

    def _on_movie_frame(self, frame: int) -> None:
        movie = self._movie
        if movie is None or frame != movie.frameCount() - 1:
            return
        # Last frame: freeze it so the GIF does not loop, let it show for its delay, then fade.
        delay = max(movie.nextFrameDelay(), 1)
        movie.setPaused(True)
        self._hide_timer.start(delay)

    def _reset(self) -> None:
        self._hide_timer.stop()
        self._fade.stop()
        if self._movie is not None:
            self._movie.stop()
            self._movie = None
        self._label.clear()

    def _present(self) -> None:
        geo = self._screen_geometry()
        self.setGeometry(geo)
        self._label.setGeometry(0, 0, geo.width(), geo.height())
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()

    def _start_fade(self) -> None:
        if self._fade_ms <= 0:
            self._finish()
            return
        self._fade.setDuration(self._fade_ms)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _finish(self) -> None:
        self.hide()
        self._reset()
