import numpy as np

from jumpscare.chroma import chroma_key, is_green_screen


def frame(bg, fg=None, size=(40, 60)):
    h, w = size
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., :3] = bg
    rgba[..., 3] = 255
    if fg is not None:
        rgba[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4, :3] = fg
    return rgba


def test_detects_green_screen():
    assert is_green_screen(frame((10, 190, 20), fg=(200, 50, 50)))


def test_ignores_normal_footage_with_green_subject():
    # Green in the middle (grass, a shirt) but not at the edges is not a green screen.
    assert not is_green_screen(frame((90, 80, 70), fg=(10, 190, 20)))


def test_ignores_dark_green_edges():
    assert not is_green_screen(frame((0, 40, 0)))


def test_key_removes_green_keeps_subject():
    out = chroma_key(frame((10, 190, 20), fg=(200, 50, 50)))
    assert out[0, 0, 3] == 0
    assert out[20, 30, 3] == 255
    assert tuple(out[20, 30, :3]) == (200, 50, 50)


def test_key_softens_greenish_edges_and_despills():
    px = np.array([[[100, 150, 100, 255]]], dtype=np.uint8)  # dominance 50, between low and high
    out = chroma_key(px)
    assert 0 < out[0, 0, 3] < 255
    assert out[0, 0, 1] == 100


def test_key_does_not_modify_input():
    src = frame((10, 190, 20))
    before = src.copy()
    chroma_key(src)
    assert np.array_equal(src, before)
