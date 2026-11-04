"""Transparent, click-through, always-on-top window that flashes an image."""

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPixmap
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

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._start_fade)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setEasingCurve(QEasingCurve.Type.InQuad)
        self._fade.finished.connect(self.hide)

    def _screen_geometry(self) -> QRect:
        screens = QGuiApplication.screens()
        screen = screens[self._monitor] if self._monitor < len(screens) else None
        return (screen or QGuiApplication.primaryScreen()).geometry()

    def show_image(self, path: Path, duration_ms: int) -> bool:
        """Show the image for duration_ms, then fade out. Returns False if it can't be loaded."""
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return False

        geo = self._screen_geometry()
        self.setGeometry(geo)
        self._label.setGeometry(0, 0, geo.width(), geo.height())
        self._label.setPixmap(
            pixmap.scaled(
                int(geo.width() * self._scale),
                int(geo.height() * self._scale),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

        self._fade.stop()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._hide_timer.start(duration_ms)
        return True

    def _start_fade(self) -> None:
        if self._fade_ms <= 0:
            self.hide()
            return
        self._fade.setDuration(self._fade_ms)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()
