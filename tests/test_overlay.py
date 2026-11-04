from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QTest

from jumpscare.overlay import JumpscareOverlay


def make_png(path, w=100, h=50):
    pixmap = QPixmap(w, h)
    pixmap.fill(QColor("red"))
    assert pixmap.save(str(path), "PNG")
    return path


def test_rejects_unreadable_image(qt_app, tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    overlay = JumpscareOverlay(monitor=0, scale=0.9, fade_ms=0)
    assert overlay.show_image(bad, 100) is False
    assert not overlay.isVisible()


def test_window_is_click_through_and_unfocusable(qt_app):
    flags = JumpscareOverlay(monitor=0, scale=0.9, fade_ms=0).windowFlags()
    assert flags & Qt.WindowType.WindowTransparentForInput
    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus
    assert flags & Qt.WindowType.WindowStaysOnTopHint


def test_shows_scaled_image_then_hides(qt_app, tmp_path):
    overlay = JumpscareOverlay(monitor=99, scale=0.5, fade_ms=50)  # out-of-range monitor -> primary
    assert overlay.show_image(make_png(tmp_path / "ok.png"), 50) is True
    assert overlay.isVisible()

    screen = qt_app.primaryScreen().geometry()
    shown = overlay._label.pixmap()
    assert shown.width() <= screen.width() * 0.5
    assert shown.height() <= screen.height() * 0.5
    assert abs(shown.width() / shown.height() - 2.0) < 0.05

    QTest.qWait(400)
    assert not overlay.isVisible()
