import json

import pytest

from jumpscare.config import DEFAULT_CONFIG_PATH, ConfigError, load_config


def write(tmp_path, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_missing_file_uses_defaults(tmp_path):
    cfg = load_config(tmp_path / "nope.json")
    assert cfg.jumpscare_interval.min == 180
    assert cfg.jumpscare_folder == tmp_path / "assets" / "jumpscares"


def test_repo_config_is_valid():
    load_config(DEFAULT_CONFIG_PATH)


def test_partial_override_keeps_nested_defaults(tmp_path):
    cfg = load_config(write(tmp_path, {"hotkeys": {"test_cue": "f9"}, "cue_volume": 0.5}))
    assert cfg.hotkeys.test_cue == "f9"
    assert cfg.hotkeys.test_jumpscare == "ctrl+alt+j"
    assert cfg.cue_volume == 0.5


def test_absolute_folder_kept(tmp_path):
    target = tmp_path / "elsewhere"
    cfg = load_config(write(tmp_path, {"cue_folder": str(target)}))
    assert cfg.cue_folder == target


@pytest.mark.parametrize(
    "override",
    [
        {"typo_key": 1},
        {"hotkeys": {"bogus": "f1"}},
        {"hotkeys": "f1"},
        {"jumpscare_interval_seconds": {"min": 10, "max": 5}},
        {"cue_interval_seconds": {"min": 0, "max": 5}},
        {"jumpscare_volume": 1.5},
        {"jumpscare_scale": 0},
        {"jumpscare_duration_ms": 0},
        {"jumpscare_fade_ms": -1},
        {"jumpscare_duration_ms": 500, "jumpscare_fade_ms": 600},
        {"monitor": -1},
        {"min_gap_seconds": -1},
    ],
)
def test_invalid_values_rejected(tmp_path, override):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, override))


def test_bad_json_rejected(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)
