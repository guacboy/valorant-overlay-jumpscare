from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QTest

from jumpscare.overlay import JumpscareOverlay


def make_png(path, w=100, h=50):
    pixmap = QPixmap(w, h)
    pixmap.fill(QColor("red"))
    assert pixmap.save(str(path), "PNG")
    return path


def make_gif(path, frames, delay_cs, loop_forever=True):
    """Minimal 1x1 GIF with the given frame count and per-frame delay (hundredths of a second)."""
    data = bytearray(b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\x00\x00\x00\x00\xff")
    if loop_forever:
        data += b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"
    for i in range(frames):
        data += b"\x21\xf9\x04\x00" + delay_cs.to_bytes(2, "little") + b"\x00\x00"
        data += b"\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00"
        data += b"\x02\x02" + (b"\x44\x01" if i % 2 == 0 else b"\x4c\x01") + b"\x00"
    data += b"\x3b"
    path.write_bytes(bytes(data))
    return path


def test_gif_plays_fully_once_then_hides(qt_app, tmp_path):
    gif = make_gif(tmp_path / "anim.gif", frames=4, delay_cs=10)  # about 400ms total
    overlay = JumpscareOverlay(monitor=0, scale=0.5, fade_ms=0)
    assert overlay.show_image(gif, 50) is True  # duration is ignored for animated GIFs

    QTest.qWait(200)
    assert overlay.isVisible(), "GIF was cut off before finishing"

    QTest.qWait(700)
    assert not overlay.isVisible(), "GIF kept looping instead of closing"


def test_single_frame_gif_uses_duration(qt_app, tmp_path):
    gif = make_gif(tmp_path / "still.gif", frames=1, delay_cs=0, loop_forever=False)
    overlay = JumpscareOverlay(monitor=0, scale=0.5, fade_ms=0)
    assert overlay.show_image(gif, 100) is True
    QTest.qWait(400)
    assert not overlay.isVisible()


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
