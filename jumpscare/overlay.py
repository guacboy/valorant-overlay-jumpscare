"""Transparent, click-through, always-on-top window for jumpscares.

Media is shown at its original size, centered on the screen, and only shrunk when it is
larger than the screen. The window is sized to the media so the game stays uncovered.

Media is loaded ahead of time with prepare() so play() can show it instantly. One video
player is created at startup and reused, so videos never wait for a player to spin up.
Video frames are converted and keyed on a background thread so the UI thread never falls
behind; if processing can't keep up, older frames are skipped and playback speed stays correct.
"""

import logging
import threading
from enum import Enum, auto
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QGuiApplication, QImage, QImageReader, QMovie, QPainter, QPaintEvent, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtWidgets import QWidget

from jumpscare.chroma import chroma_key, is_green_screen
from jumpscare.media import is_video

log = logging.getLogger(__name__)

KEY_MAX_WIDTH = 960  # green screen frames are keyed at most this wide, then scaled back up
DETECT_SAMPLE_WIDTH = 320  # first frame is shrunk to this width for green screen detection
DISPLAY_FORMAT = QImage.Format.Format_ARGB32_Premultiplied  # fastest format for the painter


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


def display_size(media: QSize, screen: QSize) -> QSize:
    """The media's original size, shrunk (keeping aspect ratio) only if it is larger than the screen."""
    if media.width() <= screen.width() and media.height() <= screen.height():
        return QSize(media)
    return media.scaled(screen, Qt.AspectRatioMode.KeepAspectRatio)


def resized(image: QImage | QPixmap, size: QSize) -> QImage | QPixmap:
    if image.size() == size:
        return image
    return image.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


def detect_green_screen(image: QImage) -> bool:
    return is_green_screen(qimage_to_rgba(image.scaledToWidth(min(image.width(), DETECT_SAMPLE_WIDTH))))


def render_video_frame(image: QImage, screen: QSize, key: bool) -> QImage:
    """Size the frame for display, keying out the green screen when key is True.

    Keyed frames wider than KEY_MAX_WIDTH are keyed at that width; the painter scales them
    back up on the UI thread, which splits the work across two threads.
    """
    target = display_size(image.size(), screen)
    if not key:
        return resized(image, target).convertToFormat(DISPLAY_FORMAT)
    work = target
    if target.width() > KEY_MAX_WIDTH:
        work = target.scaled(QSize(KEY_MAX_WIDTH, target.height()), Qt.AspectRatioMode.KeepAspectRatio)
    return rgba_to_qimage(chroma_key(qimage_to_rgba(resized(image, work)))).convertToFormat(DISPLAY_FORMAT)


class FrameRenderer(QObject):
    """Renders video frames on a pool thread, always working on the newest frame submitted.

    Frames that arrive while a render is running replace each other, so a slow render
    skips frames instead of building a backlog.
    """

    rendered = Signal(int, QImage)  # generation, finished frame

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._job: tuple[int, QVideoFrame, QSize, bool] | None = None
        self._running = False

    def submit(self, generation: int, frame: QVideoFrame, screen: QSize, key: bool) -> None:
        with self._lock:
            self._job = (generation, frame, screen, key)
            if self._running:
                return
            self._running = True
        QThreadPool.globalInstance().start(self._run)

    def _run(self) -> None:
        while True:
            with self._lock:
                job, self._job = self._job, None
                if job is None:
                    self._running = False
                    return
            generation, frame, screen, key = job
            image = frame.toImage()
            if image.isNull():
                continue
            try:
                self.rendered.emit(generation, render_video_frame(image, screen, key))
            except RuntimeError:  # the app is shutting down and the receiver is gone
                return

    def shutdown(self) -> None:
        """Drop pending work and wait for a running render to finish."""
        with self._lock:
            self._job = None
        QThreadPool.globalInstance().waitForDone(2000)


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
        self._place(QSize(1, 1))
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
        self._preview: QImage | None = None  # first video frame, shown the moment play() runs
        self._frame: QImage | QPixmap | None = None  # what paintEvent draws, stretched to the window
        self._video_size: QSize | None = None  # display size of the prepared or playing video
        self._generation = 0  # bumped on every stop so late background renders are dropped

        self._renderer = FrameRenderer()
        self._renderer.rendered.connect(self._on_frame_rendered)

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

    def current_frame(self) -> QImage | None:
        """The image currently on screen, as a QImage at its displayed size."""
        if self._frame is None:
            return None
        image = self._frame.toImage() if isinstance(self._frame, QPixmap) else self._frame
        return resized(image, self.size())

    def shutdown(self) -> None:
        """Stop playback and background rendering before the app exits."""
        self._stop()
        self._renderer.shutdown()

    def _screen_geometry(self) -> QRect:
        screens = QGuiApplication.screens()
        screen = screens[self._monitor] if self._monitor < len(screens) else None
        return (screen or QGuiApplication.primaryScreen()).geometry()

    def _place(self, size: QSize) -> None:
        """Size the window to the media and center it on the screen."""
        rect = QRect(QPoint(0, 0), size)
        rect.moveCenter(self._screen_geometry().center())
        if self.geometry() != rect:
            self.setGeometry(rect)

    # Preparing

    def prepare(self, path: Path) -> bool:
        """Load media so the next play() starts instantly. Returns False if it can't be loaded."""
        self._stop()
        self._key_video = None
        self._video_size = None
        screen = self._screen_geometry().size()

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
                movie.setScaledSize(display_size(QImageReader(str(path)).size(), screen))
                movie.frameChanged.connect(self._on_movie_frame)
                self._kind, self._path, self._movie = Kind.GIF, path, movie
                return True
            # Single-frame GIFs are treated as still images.

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return False
        self._kind, self._path, self._pixmap = Kind.IMAGE, path, resized(pixmap, display_size(pixmap.size(), screen))
        return True

    # Playing

    def play(self) -> bool:
        """Show the prepared media. Returns False if nothing is prepared."""
        if self._kind is None or self._active:
            return False
        self._active = True
        if self._kind is Kind.IMAGE:
            self._show_frame(self._pixmap)
            self._hide_timer.start(self._image_duration_ms)
        elif self._kind is Kind.GIF:
            self._movie.start()  # the first frame arrives through _on_movie_frame
        else:
            if self._preview is not None:
                self._show_frame(self._preview, self._video_size)
            self._player.play()
        return True

    def _show_frame(self, frame: QImage | QPixmap, size: QSize | None = None) -> None:
        """Draw frame at size (its own size by default), centered on the screen."""
        self._frame = frame
        self._place(size or frame.size())
        if not self.isVisible():
            self.show()
        self.raise_()
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        if self._frame is None:
            return
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        target = self.rect()
        if self._frame.size() != target.size():  # keyed video frames are scaled back up here
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if isinstance(self._frame, QPixmap):
            painter.drawPixmap(target, self._frame)
        else:
            painter.drawImage(target, self._frame)
        painter.end()

    # Frame handling

    def _on_movie_frame(self, frame: int) -> None:
        movie = self._movie
        if movie is None or not self._active or self.sender() is not movie:
            return
        self._show_frame(movie.currentPixmap())
        if frame == movie.frameCount() - 1:
            # Last frame: freeze it so the GIF does not loop, let it show for its delay, then vanish.
            delay = max(movie.nextFrameDelay(), 1)
            movie.setPaused(True)
            self._hide_timer.start(delay)

    def _on_video_frame(self, frame: QVideoFrame) -> None:
        if self._kind is not Kind.VIDEO or not frame.isValid():
            return
        screen = self._screen_geometry().size()
        if self._key_video is None or not self._active:
            # Preloading (or a first frame that arrived late): render here, it is not time critical.
            image = frame.toImage()
            if image.isNull():
                return
            if self._key_video is None:
                self._key_video = detect_green_screen(image)
                self._video_size = display_size(image.size(), screen)
            rendered = render_video_frame(image, screen, self._key_video)
            if self._active:
                self._show_frame(rendered, self._video_size)
            else:
                self._preview = rendered
            return
        self._renderer.submit(self._generation, frame, screen, self._key_video)

    def _on_frame_rendered(self, generation: int, image: QImage) -> None:
        if generation == self._generation and self._active and self._kind is Kind.VIDEO:
            self._show_frame(image, self._video_size)

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
        self._generation += 1
        if movie is not None:
            movie.stop()
        if stop_player:
            self._player.stop()
        self._frame = None
        self.hide()

    def _finish(self) -> None:
        self._stop()
        self.finished.emit()
