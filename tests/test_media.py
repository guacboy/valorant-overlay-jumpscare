import json
import random

from jumpscare.config import Interval, load_config
from jumpscare.media import (
    IMAGE_EXTS,
    RandomPicker,
    choose_jumpscare,
    list_files,
    paired_audio,
    random_delay_ms,
)


def touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def make_cfg(tmp_path, **overrides):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(overrides), encoding="utf-8")
    return load_config(path)


def test_list_files_filters_and_sorts(tmp_path):
    touch(tmp_path / "b.png")
    touch(tmp_path / "a.PNG")
    touch(tmp_path / "notes.txt")
    (tmp_path / "sub.png").mkdir()
    assert [p.name for p in list_files(tmp_path, IMAGE_EXTS)] == ["a.PNG", "b.png"]


def test_list_files_missing_folder(tmp_path):
    assert list_files(tmp_path / "missing", IMAGE_EXTS) == []


def test_paired_audio(tmp_path):
    image = touch(tmp_path / "scream.png")
    assert paired_audio(image) is None
    sound = touch(tmp_path / "scream.mp3")
    assert paired_audio(image) == sound


def test_picker_never_repeats_with_multiple_items():
    picker = RandomPicker(random.Random(0))
    picks = [picker.pick(["a", "b", "c"]) for _ in range(50)]
    assert all(x != y for x, y in zip(picks, picks[1:]))


def test_picker_single_and_empty():
    picker = RandomPicker(random.Random(0))
    assert picker.pick([]) is None
    assert picker.pick(["only"]) == "only"
    assert picker.pick(["only"]) == "only"


def test_random_delay_within_bounds():
    rng = random.Random(1)
    for _ in range(200):
        assert 2000 <= random_delay_ms(Interval(2, 5), rng) <= 5000


def pickers():
    rng = random.Random(0)
    return RandomPicker(rng), rng


def test_choose_none_without_images(tmp_path):
    assert choose_jumpscare(make_cfg(tmp_path), *pickers()) is None


def test_choose_prefers_paired_sound(tmp_path):
    cfg = make_cfg(tmp_path)
    image = touch(cfg.jumpscare_folder / "face.png")
    paired = touch(cfg.jumpscare_folder / "face.wav")
    scare = choose_jumpscare(cfg, *pickers())
    assert scare.media == image
    assert scare.sound == paired


def test_image_without_same_named_sound_is_silent(tmp_path):
    cfg = make_cfg(tmp_path)
    touch(cfg.jumpscare_folder / "face.png")
    touch(cfg.jumpscare_folder / "other.ogg")  # a sound with a different name is not used
    assert choose_jumpscare(cfg, *pickers()).sound is None


def test_choose_silent_when_audio_chance_zero(tmp_path):
    cfg = make_cfg(tmp_path, jumpscare_audio_chance=0)
    touch(cfg.jumpscare_folder / "face.png")
    touch(cfg.jumpscare_folder / "face.wav")
    assert choose_jumpscare(cfg, *pickers()).sound is None


def test_videos_are_picked(tmp_path):
    cfg = make_cfg(tmp_path)
    video = touch(cfg.jumpscare_folder / "clip.mp4")
    assert choose_jumpscare(cfg, *pickers()).media == video


def test_video_gets_only_same_named_sound(tmp_path):
    cfg = make_cfg(tmp_path)
    video = touch(cfg.jumpscare_folder / "clip.mp4")
    assert choose_jumpscare(cfg, *pickers()).sound is None
    paired = touch(video.with_suffix(".mp3"))
    assert choose_jumpscare(cfg, *pickers()).sound == paired
