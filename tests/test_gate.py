import json
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QTest

from jumpscare.app import OverlayApp
from jumpscare.config import load_config
from jumpscare.gate import PlaybackGate


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_free_at_start():
    assert PlaybackGate(5).wait_s() == 0


def test_sound_blocks_for_length_plus_gap():
    clock = FakeClock()
    gate = PlaybackGate(5, clock)
    gate.occupy(2.0)
    assert gate.wait_s() == 7.0
    clock.now += 6.0
    assert gate.wait_s() == 1.0
    clock.now += 1.0
    assert gate.wait_s() == 0


def test_visual_blocks_until_released_then_gap():
    clock = FakeClock()
    gate = PlaybackGate(5, clock)
    gate.occupy(open_ended=True)
    clock.now += 60
    assert gate.wait_s() is None
    gate.release()
    assert gate.wait_s() == 5.0


def test_long_sound_outlasts_visual():
    clock = FakeClock()
    gate = PlaybackGate(5, clock)
    gate.occupy(10.0, open_ended=True)  # 10s scream with a 1s image
    clock.now += 1
    gate.release()
    assert gate.wait_s() == 14.0


def test_release_without_visual_is_noop():
    clock = FakeClock()
    gate = PlaybackGate(5, clock)
    gate.occupy(1.0)
    gate.release()
    assert gate.wait_s() == 6.0


def test_cue_waits_for_jumpscare_and_gap(qt_app, tmp_path):
    folder = tmp_path / "assets" / "jumpscares"
    folder.mkdir(parents=True)
    pixmap = QPixmap(10, 10)
    pixmap.fill(QColor("red"))
    pixmap.save(str(folder / "face.png"), "PNG")
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({"jumpscare_duration_ms": 100, "jumpscare_fade_ms": 0, "min_gap_seconds": 0.3}),
        encoding="utf-8",
    )
    app = OverlayApp(qt_app, load_config(cfg_path))
    cue_timer: QTimer = app._cue_timer
    try:
        app.trigger_jumpscare()
        app._on_cue_timer()
        assert cue_timer.isActive(), "cue should be deferred while the jumpscare is on screen"
        assert cue_timer.remainingTime() <= 250

        QTest.qWait(200)  # image gone, gap still running
        assert not app._overlay.isVisible()
        assert 0 < app._gate.wait_s() <= 0.3

        QTest.qWait(400)
        assert app._gate.wait_s() == 0
    finally:
        cue_timer.stop()
        app._scare_timer.stop()
        app._audio.shutdown()


def test_longest_waiting_event_goes_first(qt_app, tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"min_gap_seconds": 0.2}), encoding="utf-8")
    app = OverlayApp(qt_app, load_config(cfg_path))
    try:
        app._gate.occupy(0.1)
        app._on_cue_timer()  # cue starts waiting first
        assert app._cue_timer.isActive()

        time.sleep(0.4)  # gate frees up; no event processing, so the cue's timer stays pending
        assert app._gate.wait_s() == 0
        app._on_scare_timer()
        assert "Jumpscare" in app._waiting, "jumpscare must not cut in line ahead of the cue"
    finally:
        app._cue_timer.stop()
        app._scare_timer.stop()
        app._audio.shutdown()
