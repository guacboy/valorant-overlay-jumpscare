from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QTest

from jumpscare.overlay import JumpscareOverlay
from tests.avi import green_screen_frames, write_avi


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
    overlay = JumpscareOverlay(monitor=0, scale=0.5)
    assert overlay.show_image(gif, 50) is True  # duration is ignored for animated GIFs

    QTest.qWait(200)
    assert overlay.isVisible(), "GIF was cut off before finishing"

    QTest.qWait(700)
    assert not overlay.isVisible(), "GIF kept looping instead of closing"


def test_single_frame_gif_uses_duration(qt_app, tmp_path):
    gif = make_gif(tmp_path / "still.gif", frames=1, delay_cs=0, loop_forever=False)
    overlay = JumpscareOverlay(monitor=0, scale=0.5)
    assert overlay.show_image(gif, 100) is True
    QTest.qWait(400)
    assert not overlay.isVisible()


def test_rejects_unreadable_image(qt_app, tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    overlay = JumpscareOverlay(monitor=0, scale=0.9)
    assert overlay.show_image(bad, 100) is False
    assert not overlay.isVisible()


def test_window_is_click_through_and_unfocusable(qt_app):
    flags = JumpscareOverlay(monitor=0, scale=0.9).windowFlags()
    assert flags & Qt.WindowType.WindowTransparentForInput
    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus
    assert flags & Qt.WindowType.WindowStaysOnTopHint


def test_shows_scaled_image_then_hides(qt_app, tmp_path):
    overlay = JumpscareOverlay(monitor=99, scale=0.5)  # out-of-range monitor -> primary
    assert overlay.show_image(make_png(tmp_path / "ok.png"), 50) is True
    assert overlay.isVisible()

    screen = qt_app.primaryScreen().geometry()
    shown = overlay._label.pixmap()
    assert shown.width() <= screen.width() * 0.5
    assert shown.height() <= screen.height() * 0.5
    assert abs(shown.width() / shown.height() - 2.0) < 0.05

    QTest.qWait(400)
    assert not overlay.isVisible()


def play_until_hidden(overlay, path, timeout_ms=4000):
    """Play a video and return a snapshot of the first frame shown."""
    assert overlay.show_video(path, 0.0) is True
    snapshot, waited = None, 0
    while waited < timeout_ms:
        QTest.qWait(50)
        waited += 50
        if snapshot is None and overlay._label.pixmap() is not None and not overlay._label.pixmap().isNull():
            snapshot = overlay._label.pixmap().toImage()
        if snapshot is not None and not overlay.isVisible():
            return snapshot
    raise AssertionError("video did not finish and hide")


def test_green_screen_video_is_keyed(qt_app, tmp_path):
    video = write_avi(tmp_path / "green.avi", green_screen_frames(5))
    overlay = JumpscareOverlay(monitor=0, scale=0.5)
    snapshot = play_until_hidden(overlay, video)
    assert overlay.video_keyed is True
    assert snapshot.pixelColor(1, 1).alpha() == 0
    center = snapshot.pixelColor(snapshot.width() // 2, snapshot.height() // 2)
    assert center.alpha() == 255 and center.red() > 150


def test_normal_video_is_not_keyed(qt_app, tmp_path):
    frames = green_screen_frames(5)
    for f in frames:
        f[:] = (90, 80, 70)
    video = write_avi(tmp_path / "plain.avi", frames)
    overlay = JumpscareOverlay(monitor=0, scale=0.5)
    snapshot = play_until_hidden(overlay, video)
    assert overlay.video_keyed is False
    assert snapshot.pixelColor(1, 1).alpha() == 255


def test_missing_video_rejected(qt_app, tmp_path):
    overlay = JumpscareOverlay(monitor=0, scale=0.5)
    assert overlay.show_video(tmp_path / "nope.mp4", 0.0) is False


def test_still_image_shows_one_second_then_vanishes_without_fade(qt_app, tmp_path):
    overlay = JumpscareOverlay(monitor=0, scale=0.5)
    assert overlay.show_image(make_png(tmp_path / "pop.png"), 1000) is True
    QTest.qWait(900)
    assert overlay.isVisible()
    assert overlay.windowOpacity() == 1.0
    QTest.qWait(250)
    assert not overlay.isVisible()
