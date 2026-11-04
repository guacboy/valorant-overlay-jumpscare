import math
import wave

import numpy as np
import pytest

from jumpscare.audio import AudioPlayer, trim_silence


def test_trims_mono_edges():
    samples = np.array([0, 5, -3, 20000, 0, -15000, 2, 0], dtype=np.int16)
    assert trim_silence(samples, 0.01).tolist() == [20000, 0, -15000]


def test_trims_stereo_using_loudest_channel():
    samples = np.array([[0, 0], [0, 9000], [8000, 0], [0, 0]], dtype=np.int16)
    assert trim_silence(samples, 0.01).tolist() == [[0, 9000], [8000, 0]]


def test_float_samples():
    samples = np.array([0.0, 0.001, 0.5, 0.0], dtype=np.float32)
    assert trim_silence(samples, 0.01).tolist() == [0.5]


def test_all_silent_clip_untouched():
    samples = np.zeros(100, dtype=np.int16)
    assert trim_silence(samples, 0.01) is samples


def test_threshold_zero_disables():
    samples = np.array([0, 0, 100, 0], dtype=np.int16)
    assert trim_silence(samples, 0.0) is samples


def test_player_trims_loaded_sound(tmp_path):
    rate = 22050
    tone = [int(12000 * math.sin(i / 8)) for i in range(int(rate * 0.2))]
    pcm = [0] * (rate // 2) + tone + [0] * (rate // 2)  # 0.5s silence, 0.2s tone, 0.5s silence
    path = tmp_path / "padded.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.array(pcm, dtype=np.int16).tobytes())

    player = AudioPlayer(silence_threshold=0.01)
    if not player.available:
        pytest.skip("no audio device")
    try:
        assert 0.15 < player._load(path).get_length() < 0.3
    finally:
        player.shutdown()
