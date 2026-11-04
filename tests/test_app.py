import json

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QTest

from jumpscare.app import OverlayApp
from jumpscare.config import load_config


def make_app(qt_app, tmp_path, names):
    folder = tmp_path / "assets" / "jumpscares"
    folder.mkdir(parents=True)
    for name in names:
        pixmap = QPixmap(10, 10)
        pixmap.fill(QColor("red"))
        pixmap.save(str(folder / name), "PNG")
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"jumpscare_duration_ms": 50, "min_gap_seconds": 0}), encoding="utf-8")
    return OverlayApp(qt_app, load_config(cfg_path))


def test_next_jumpscare_is_preloaded_then_replaced_after_playing(qt_app, tmp_path):
    app = make_app(qt_app, tmp_path, ["a.png", "b.png"])
    try:
        app._prepare_next()
        first = app._next
        assert first is not None
        assert app._overlay.prepared_path == first.media

        app.trigger_jumpscare()
        assert app._next is None
        assert app._overlay.isVisible()

        QTest.qWait(200)
        assert not app._overlay.isVisible()
        assert app._next is not None, "next jumpscare should be preloaded once the last one finishes"
        assert app._next.media != first.media
    finally:
        app._audio.shutdown()


def test_deleted_preloaded_file_falls_back_to_another(qt_app, tmp_path):
    app = make_app(qt_app, tmp_path, ["a.png", "b.png"])
    try:
        app._prepare_next()
        app._next.media.unlink()
        app.trigger_jumpscare()
        assert app._overlay.isVisible()
    finally:
        app._audio.shutdown()


def test_empty_folder_is_harmless(qt_app, tmp_path):
    app = make_app(qt_app, tmp_path, [])
    try:
        app._prepare_next()
        assert app._next is None
        app.trigger_jumpscare()
        assert not app._overlay.isVisible()
    finally:
        app._audio.shutdown()
