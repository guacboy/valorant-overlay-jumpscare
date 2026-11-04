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


def overlay(duration_ms=1000):
    return JumpscareOverlay(monitor=0, image_duration_ms=duration_ms, video_volume=0.0)


def screen_size(qt_app):
    return qt_app.primaryScreen().geometry().size()


def wait_for_preview(ov, timeout_ms=3000):
    waited = 0
    while ov._preview is None and waited < timeout_ms:
        QTest.qWait(10)
        waited += 10
    assert ov._preview is not None, "video was not preloaded"


def play_video_until_hidden(ov, path, timeout_ms=4000):
    """Preload and play a video, returning the first frame shown."""
    assert ov.prepare(path) is True
    wait_for_preview(ov)
    assert ov.play() is True
    assert ov.isVisible(), "preloaded video should appear instantly"
    snapshot = ov.current_frame()
    waited = 0
    while ov.isVisible() and waited < timeout_ms:
        QTest.qWait(50)
        waited += 50
    assert not ov.isVisible(), "video did not finish and hide"
    return snapshot


def test_play_without_prepare_does_nothing(qt_app):
    ov = overlay()
    assert ov.play() is False
    assert not ov.isVisible()


def test_rejects_unreadable_image(qt_app, tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    ov = overlay()
    assert ov.prepare(bad) is False
    assert ov.play() is False


def test_window_is_click_through_and_unfocusable(qt_app):
    flags = overlay().windowFlags()
    assert flags & Qt.WindowType.WindowTransparentForInput
    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus
    assert flags & Qt.WindowType.WindowStaysOnTopHint


def test_image_fills_whole_screen(qt_app, tmp_path):
    ov = overlay(duration_ms=50)
    assert ov.prepare(make_png(tmp_path / "wide.png", 300, 100)) is True  # different shape than screen
    assert ov.play() is True
    assert ov.geometry() == qt_app.primaryScreen().geometry()
    assert ov.current_frame().size() == screen_size(qt_app)
    QTest.qWait(300)
    assert not ov.isVisible()


def test_still_image_shows_one_second_then_vanishes_without_fade(qt_app, tmp_path):
    ov = overlay(duration_ms=1000)
    ov.prepare(make_png(tmp_path / "pop.png"))
    ov.play()
    QTest.qWait(900)
    assert ov.isVisible()
    assert ov.windowOpacity() == 1.0
    QTest.qWait(250)
    assert not ov.isVisible()


def test_gif_plays_fully_once_then_hides(qt_app, tmp_path):
    gif = make_gif(tmp_path / "anim.gif", frames=4, delay_cs=10)  # about 400ms total
    ov = overlay(duration_ms=50)  # duration is ignored for animated GIFs
    assert ov.prepare(gif) is True
    ov.play()
    QTest.qWait(200)
    assert ov.isVisible(), "GIF was cut off before finishing"
    assert ov.current_frame().size() == screen_size(qt_app)
    QTest.qWait(700)
    assert not ov.isVisible(), "GIF kept looping instead of closing"


def test_single_frame_gif_uses_duration(qt_app, tmp_path):
    gif = make_gif(tmp_path / "still.gif", frames=1, delay_cs=0, loop_forever=False)
    ov = overlay(duration_ms=100)
    assert ov.prepare(gif) is True
    ov.play()
    QTest.qWait(400)
    assert not ov.isVisible()


def test_finished_emitted_once_per_play(qt_app, tmp_path):
    ov = overlay(duration_ms=50)
    count = []
    ov.finished.connect(lambda: count.append(1))
    ov.prepare(make_png(tmp_path / "a.png"))
    ov.play()
    QTest.qWait(200)
    assert count == [1]


def test_green_screen_video_is_keyed_and_fullscreen(qt_app, tmp_path):
    video = write_avi(tmp_path / "green.avi", green_screen_frames(5))
    ov = overlay()
    snapshot = play_video_until_hidden(ov, video)
    assert ov.video_keyed is True
    assert snapshot.size() == screen_size(qt_app)
    assert snapshot.pixelColor(1, 1).alpha() == 0
    center = snapshot.pixelColor(snapshot.width() // 2, snapshot.height() // 2)
    assert center.alpha() == 255 and center.red() > 150


def test_normal_video_is_not_keyed(qt_app, tmp_path):
    frames = green_screen_frames(5)
    for f in frames:
        f[:] = (90, 80, 70)
    video = write_avi(tmp_path / "plain.avi", frames)
    ov = overlay()
    snapshot = play_video_until_hidden(ov, video)
    assert ov.video_keyed is False
    assert snapshot.pixelColor(1, 1).alpha() == 255


def test_same_video_can_replay(qt_app, tmp_path):
    video = write_avi(tmp_path / "again.avi", green_screen_frames(3))
    ov = overlay()
    play_video_until_hidden(ov, video)
    play_video_until_hidden(ov, video)


def test_missing_video_rejected(qt_app, tmp_path):
    assert overlay().prepare(tmp_path / "nope.mp4") is False


def test_render_sizes(qt_app):
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImage

    from jumpscare.overlay import KEY_MAX_WIDTH, render_video_frame

    frame = QImage(1920, 1080, QImage.Format.Format_RGB32)
    frame.fill(QColor(0, 200, 0))
    screen = QSize(2560, 1440)
    assert render_video_frame(frame, screen, key=False).size() == screen
    keyed = render_video_frame(frame, screen, key=True)
    assert keyed.width() == KEY_MAX_WIDTH
    assert abs(keyed.width() / keyed.height() - screen.width() / screen.height()) < 0.01


def test_renderer_skips_to_newest_frame(qt_app):
    from PySide6.QtCore import QSize, QThreadPool
    from PySide6.QtGui import QImage
    from PySide6.QtMultimedia import QVideoFrame

    from jumpscare.overlay import FrameRenderer

    renderer = FrameRenderer()
    got = []
    renderer.rendered.connect(lambda generation, image: got.append(generation))
    image = QImage(1920, 1080, QImage.Format.Format_RGB32)
    image.fill(QColor(0, 200, 0))
    for generation in range(20):  # far faster than frames can be keyed
        renderer.submit(generation, QVideoFrame(image), QSize(1920, 1080), True)
    QThreadPool.globalInstance().waitForDone(5000)
    QTest.qWait(50)  # deliver queued signals
    assert got[-1] == 19, "newest frame must always be rendered"
    assert len(got) < 20, "frames that piled up should have been skipped"
