"""Fullscreen, transparent, click-through, always-on-top window for jumpscares.

Media is loaded ahead of time with prepare() so play() can show it instantly. One video
player is created at startup and reused, so videos never wait for a player to spin up.
"""

import logging
from enum import Enum, auto
from pathlib import Path

import numpy as np
from PySide6.QtCore import QRect, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QGuiApplication, QImage, QImageReader, QMovie, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtWidgets import QLabel, QWidget

from jumpscare.chroma import chroma_key, is_green_screen
from jumpscare.media import is_video

log = logging.getLogger(__name__)

KEY_MAX_WIDTH = 1280  # green screen frames are keyed at most this wide, then scaled to the screen


class Kind(Enum):
    IMAGE = auto()
    GIF = auto()
    VIDEO = auto()


def qimage_to_rgba(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h, stride = image.width(), image.height(), image.bytesPerLine()
    buf = np.frombuffer(image.constBits(), dtype=np.uint8, count=stride * h)
    return buf.reshape(h, stride)[:, : w * 4].reshape(h, w, 4).copy()


def rgba_to_qimage(rgba: np.ndarray) -> QImage:
    h, w = rgba.shape[:2]
    data = np.ascontiguousarray(rgba)
    return QImage(data.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()


def cover(image: QImage | QPixmap, size: QSize) -> QImage | QPixmap:
    """Scale to fill size completely, keeping aspect ratio, and crop the overflow evenly."""
    scaled = image.scaled(
        size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
    )
    x = (scaled.width() - size.width()) // 2
    y = (scaled.height() - size.height()) // 2
    return scaled.copy(x, y, size.width(), size.height())


class JumpscareOverlay(QWidget):
    finished = Signal()  # emitted when the image, GIF or video has disappeared

    def __init__(self, monitor: int, image_duration_ms: int, video_volume: float) -> None:
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
        self._image_duration_ms = image_duration_ms

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fit_to_screen()
        self.winId()  # create the native window now so the first show is instant

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._finish)

        # Prepared media and playback state.
        self._kind: Kind | None = None
        self._path: Path | None = None
        self._pixmap: QPixmap | None = None
        self._movie: QMovie | None = None
        self._active = False
        self._key_video: bool | None = None  # decided from the video's first frame
        self._preview: QPixmap | None = None  # first video frame, shown the moment play() runs

        self._audio_out = QAudioOutput(self)
        self._audio_out.setVolume(video_volume)
        self._sink = QVideoSink(self)
        self._sink.videoFrameChanged.connect(self._on_video_frame)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_out)
        self._player.setVideoSink(self._sink)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_video_error)

    @property
    def prepared_path(self) -> Path | None:
        return self._path if not self._active else None

    @property
    def video_keyed(self) -> bool | None:
        """Whether the prepared or playing video is chroma keyed (None until its first frame)."""
        return self._key_video

    def _screen_geometry(self) -> QRect:
        screens = QGuiApplication.screens()
        screen = screens[self._monitor] if self._monitor < len(screens) else None
        return (screen or QGuiApplication.primaryScreen()).geometry()

    def _fit_to_screen(self) -> QSize:
        geo = self._screen_geometry()
        if self.geometry() != geo:
            self.setGeometry(geo)
            self._label.setGeometry(0, 0, geo.width(), geo.height())
        return geo.size()

    # Preparing

    def prepare(self, path: Path) -> bool:
        """Load media so the next play() starts instantly. Returns False if it can't be loaded."""
        self._stop()
        self._key_video = None
        screen = self._fit_to_screen()

        if is_video(path):
            if not path.is_file():
                return False
            self._kind, self._path = Kind.VIDEO, path
            url = QUrl.fromLocalFile(str(path))
            if self._player.source() == url:
                self._player.setPosition(0)
                self._player.pause()
            else:
                self._player.setSource(url)  # pause() follows once it has loaded
            return True

        if path.suffix.lower() == ".gif":
            movie = QMovie(str(path))
            if movie.isValid() and movie.frameCount() > 1:
                movie.setCacheMode(QMovie.CacheMode.CacheAll)
                movie.setScaledSize(
                    QImageReader(str(path)).size().scaled(screen, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
                )
                movie.frameChanged.connect(self._on_movie_frame)
                self._kind, self._path, self._movie = Kind.GIF, path, movie
                return True
            # Single-frame GIFs are treated as still images.

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return False
        self._kind, self._path, self._pixmap = Kind.IMAGE, path, cover(pixmap, screen)
        return True

    # Playing

    def play(self) -> bool:
        """Show the prepared media. Returns False if nothing is prepared."""
        if self._kind is None or self._active:
            return False
        self._active = True
        if self._kind is Kind.IMAGE:
            self._label.setPixmap(self._pixmap)
            self._present()
            self._hide_timer.start(self._image_duration_ms)
        elif self._kind is Kind.GIF:
            self._present()
            self._movie.start()
        else:
            if self._preview is not None:
                self._label.setPixmap(self._preview)
                self._present()
            self._player.play()
        return True

    def _present(self) -> None:
        self._fit_to_screen()
        if not self.isVisible():
            self.show()
        self.raise_()

    # Frame handling

    def _on_movie_frame(self, frame: int) -> None:
        movie = self._movie
        if movie is None or not self._active or self.sender() is not movie:
            return
        self._label.setPixmap(cover(movie.currentPixmap(), self._screen_geometry().size()))
        if frame == movie.frameCount() - 1:
            # Last frame: freeze it so the GIF does not loop, let it show for its delay, then vanish.
            delay = max(movie.nextFrameDelay(), 1)
            movie.setPaused(True)
            self._hide_timer.start(delay)

    def _render_video_frame(self, image: QImage) -> QPixmap:
        screen = self._screen_geometry().size()
        if self._key_video is None:
            sample = image.scaledToWidth(min(image.width(), 320))
            self._key_video = is_green_screen(qimage_to_rgba(sample))
        if not self._key_video:
            return QPixmap.fromImage(cover(image, screen))
        work = screen.scaled(
            QSize(min(KEY_MAX_WIDTH, screen.width()), screen.height()), Qt.AspectRatioMode.KeepAspectRatio
        )
        keyed = rgba_to_qimage(chroma_key(qimage_to_rgba(cover(image, work))))
        if keyed.size() != screen:
            keyed = keyed.scaled(screen, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return QPixmap.fromImage(keyed)

    def _on_video_frame(self, frame: QVideoFrame) -> None:
        if self._kind is not Kind.VIDEO or not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        pixmap = self._render_video_frame(image)
        if not self._active:
            self._preview = pixmap  # first frame from the paused, preloaded video
            return
        self._label.setPixmap(pixmap)
        if not self.isVisible():
            self._present()

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if self._kind is not Kind.VIDEO:
            return
        if status == QMediaPlayer.MediaStatus.LoadedMedia and not self._active:
            self._player.pause()  # decodes the first frame without starting playback
        elif status == QMediaPlayer.MediaStatus.EndOfMedia and self._active:
            self._finish()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._fail()

    def _on_video_error(self, _error: QMediaPlayer.Error, message: str) -> None:
        if self._kind is Kind.VIDEO:
            log.warning("Video failed: %s", message)
            self._fail()

    # Stopping

    def _fail(self) -> None:
        was_active = self._active
        self._stop()
        if was_active:
            self.finished.emit()

    def _stop(self) -> None:
        """Hide and drop the current media. State is cleared first so signals fired by
        stopping the player are ignored."""
        self._hide_timer.stop()
        stop_player = self._kind is Kind.VIDEO and self._active
        movie = self._movie
        self._kind = self._path = self._pixmap = self._movie = self._preview = None
        self._active = False
        if movie is not None:
            movie.stop()
        if stop_player:
            self._player.stop()
        self._label.clear()
        self.hide()

    def _finish(self) -> None:
        self._stop()
        self.finished.emit()
