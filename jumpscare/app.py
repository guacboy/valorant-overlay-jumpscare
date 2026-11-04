"""Wires timers, overlay, audio, tray icon and global hotkeys together."""

import logging
import random

import keyboard
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from jumpscare.audio import AudioPlayer
from jumpscare.config import Config
from jumpscare.media import AUDIO_EXTS, RandomPicker, choose_jumpscare, list_files, random_delay_ms
from jumpscare.overlay import JumpscareOverlay

log = logging.getLogger(__name__)


def _tray_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#ff4655"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, 56, 56)
    painter.end()
    return QIcon(pixmap)


def _single_shot_timer(parent: QObject, slot) -> QTimer:
    timer = QTimer(parent)
    timer.setSingleShot(True)
    timer.timeout.connect(slot)
    return timer


class OverlayApp(QObject):
    # Hotkey callbacks run on the keyboard library's thread; signals hop them onto the Qt thread.
    jumpscare_requested = Signal()
    cue_requested = Signal()
    pause_toggle_requested = Signal()

    def __init__(self, qt_app: QApplication, cfg: Config) -> None:
        super().__init__()
        self._qt_app = qt_app
        self._cfg = cfg
        self._rng = random.Random()
        self._image_picker = RandomPicker(self._rng)
        self._scare_sound_picker = RandomPicker(self._rng)
        self._cue_picker = RandomPicker(self._rng)
        self._paused = False

        self._audio = AudioPlayer()
        self._overlay = JumpscareOverlay(cfg.monitor, cfg.jumpscare_scale, cfg.jumpscare_fade_ms)

        self._scare_timer = _single_shot_timer(self, self._on_scare_timer)
        self._cue_timer = _single_shot_timer(self, self._on_cue_timer)

        self.jumpscare_requested.connect(self.trigger_jumpscare)
        self.cue_requested.connect(self.trigger_cue)
        self.pause_toggle_requested.connect(lambda: self.set_paused(not self._paused))

        self._tray = self._build_tray()

    def _build_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(_tray_icon(), self)
        tray.setToolTip("Jumpscare overlay")
        menu = QMenu()
        menu.addAction("Test jumpscare", self.trigger_jumpscare)
        menu.addAction("Test audio cue", self.trigger_cue)
        menu.addSeparator()
        self._pause_action = QAction("Pause", menu, checkable=True)
        self._pause_action.toggled.connect(self.set_paused)
        menu.addAction(self._pause_action)
        menu.addAction("Quit", self.quit)
        self._menu = menu  # keep a reference so the menu is not garbage collected
        tray.setContextMenu(menu)
        return tray

    def _register_hotkeys(self) -> None:
        bindings = {
            self._cfg.hotkeys.test_jumpscare: self.jumpscare_requested.emit,
            self._cfg.hotkeys.test_cue: self.cue_requested.emit,
            self._cfg.hotkeys.toggle_pause: self.pause_toggle_requested.emit,
        }
        for combo, callback in bindings.items():
            if not combo:
                continue
            try:
                keyboard.add_hotkey(combo, callback)
                log.info("Hotkey registered: %s", combo)
            except (ValueError, ImportError, OSError) as exc:
                log.warning("Could not register hotkey %r: %s", combo, exc)

    def start(self) -> None:
        self._tray.show()
        self._register_hotkeys()
        self._schedule()
        log.info("Overlay running. Jumpscares from %s", self._cfg.jumpscare_folder)

    def _schedule(self) -> None:
        self._schedule_scare()
        self._schedule_cue()

    def _schedule_scare(self) -> None:
        delay = random_delay_ms(self._cfg.jumpscare_interval, self._rng)
        self._scare_timer.start(delay)
        log.info("Next jumpscare in %.0fs", delay / 1000)

    def _schedule_cue(self) -> None:
        if not self._cfg.cues_enabled:
            return
        delay = random_delay_ms(self._cfg.cue_interval, self._rng)
        self._cue_timer.start(delay)
        log.info("Next audio cue in %.0fs", delay / 1000)

    def _on_scare_timer(self) -> None:
        self.trigger_jumpscare()
        self._schedule_scare()

    def _on_cue_timer(self) -> None:
        self.trigger_cue()
        self._schedule_cue()

    def trigger_jumpscare(self) -> None:
        scare = choose_jumpscare(self._cfg, self._image_picker, self._scare_sound_picker, self._rng)
        if scare is None:
            log.warning("No images found in %s", self._cfg.jumpscare_folder)
            return
        if not self._overlay.show_image(scare.image, self._cfg.jumpscare_duration_ms):
            log.warning("Could not load image %s", scare.image.name)
            return
        log.info("Jumpscare: %s", scare.image.name)
        if scare.sound:
            self._audio.play(scare.sound, self._cfg.jumpscare_volume)

    def trigger_cue(self) -> None:
        cue = self._cue_picker.pick(list_files(self._cfg.cue_folder, AUDIO_EXTS))
        if cue is None:
            log.info("No audio cues found in %s", self._cfg.cue_folder)
            return
        log.info("Audio cue: %s", cue.name)
        self._audio.play(cue, self._cfg.cue_volume)

    def set_paused(self, paused: bool) -> None:
        if paused == self._paused:
            return
        self._paused = paused
        self._pause_action.setChecked(paused)
        if paused:
            self._scare_timer.stop()
            self._cue_timer.stop()
            log.info("Paused")
        else:
            log.info("Resumed")
            self._schedule()
        self._tray.setToolTip("Jumpscare overlay (paused)" if paused else "Jumpscare overlay")

    def quit(self) -> None:
        keyboard.unhook_all_hotkeys()
        self._audio.shutdown()
        self._tray.hide()
        self._qt_app.quit()
