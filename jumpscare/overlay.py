"""Transparent, click-through, always-on-top window that flashes an image or plays a GIF or video."""

import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QImage, QImageReader, QMovie, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtWidgets import QLabel, QWidget

from jumpscare.chroma import chroma_key, is_green_screen

log = logging.getLogger(__name__)


def qimage_to_rgba(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h, stride = image.width(), image.height(), image.bytesPerLine()
    buf = np.frombuffer(image.constBits(), dtype=np.uint8, count=stride * h)
    return buf.reshape(h, stride)[:, : w * 4].reshape(h, w, 4).copy()


def rgba_to_qimage(rgba: np.ndarray) -> QImage:
    h, w = rgba.shape[:2]
    data = np.ascontiguousarray(rgba)
    return QImage(data.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()


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
        self._player: QMediaPlayer | None = None
        self._sink: QVideoSink | None = None
        self._audio_out: QAudioOutput | None = None
        self._key_video: bool | None = None  # decided from the first frame

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._start_fade)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setEasingCurve(QEasingCurve.Type.InQuad)
        self._fade.finished.connect(self._finish)

    @property
    def video_keyed(self) -> bool | None:
        """Whether the current video is being chroma keyed (None before its first frame)."""
        return self._key_video

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

    def show_video(self, path: Path, volume: float) -> bool:
        """Play a video once through with its sound, keying out a green screen if one is detected.

        Decoding is asynchronous, so a broken file is reported through the log, not the return value.
        """
        if not path.is_file():
            return False
        self._reset()
        self._key_video = None
        self._audio_out = QAudioOutput(self)
        self._audio_out.setVolume(volume)
        self._sink = QVideoSink(self)
        self._sink.videoFrameChanged.connect(self._on_video_frame)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_out)
        self._player.setVideoSink(self._sink)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_video_error)
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()
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

    def _on_video_frame(self, frame: QVideoFrame) -> None:
        if self._sink is None or self.sender() is not self._sink or not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        # Scale first so keying works on screen-sized pixels, not the full source resolution.
        image = image.scaled(
            self._fit(image.size()),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if self._key_video is None:
            self._key_video = is_green_screen(qimage_to_rgba(image))
            self._present()
        if self._key_video:
            image = rgba_to_qimage(chroma_key(qimage_to_rgba(image)))
        self._label.setPixmap(QPixmap.fromImage(image))

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if self.sender() is not self._player:
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._start_fade()  # last frame stays on screen during the fade
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._finish()

    def _on_video_error(self, _error: QMediaPlayer.Error, message: str) -> None:
        if self.sender() is not self._player:
            return
        log.warning("Video failed: %s", message)
        self._finish()

    def _reset(self) -> None:
        self._hide_timer.stop()
        self._fade.stop()
        if self._movie is not None:
            self._movie.stop()
            self._movie = None
        if self._player is not None:
            self._player.stop()
            for obj in (self._player, self._sink, self._audio_out):
                obj.deleteLater()
            self._player = self._sink = self._audio_out = None
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
