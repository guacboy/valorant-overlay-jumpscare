# Valorant Overlay Jumpscare

A transparent, click-through overlay that flashes a random image over your screen at random intervals while you play, with optional audio. It can also play random audio cues on a separate timer.

It is a normal always-on-top desktop window. It does not read game memory, inject into the game, or touch Valorant files.

## Requirements

- Windows 10/11
- Python 3.11+
- Valorant set to **Windowed Fullscreen** (Settings > Video > Display Mode). Exclusive fullscreen draws over every other window, so the overlay would be hidden.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
git config core.hooksPath .githooks
```

The last line enables the pre-push hook, which runs the test suite and blocks the push if it fails.

## Adding media

| Folder | Contents |
| --- | --- |
| `assets/jumpscares/` | Images (`.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`) |
| `assets/jumpscare_sounds/` | Fallback jumpscare sounds (`.wav`, `.ogg`, `.mp3`) |
| `assets/cues/` | Audio cues played on their own timer |

Still images stay on screen for `jumpscare_duration_ms` (1 second by default). Animated GIFs ignore that setting: each GIF plays through once in full, then fades out, even if the file is set to loop.

To give an image its own sound, put an audio file with the same name next to it, e.g. `scream.png` with `scream.mp3`. Images without a paired sound use a random file from `assets/jumpscare_sounds/` (if any).

Folders are rescanned on every trigger, so you can add files while the overlay is running. Media files are gitignored.

## Running

```powershell
.\.venv\Scripts\python.exe -m jumpscare
```

To run without a console window, use `pythonw` instead of `python`. Logs go to `overlay.log` either way.

A red dot appears in the system tray. Right-click it to test a jumpscare, test a cue, pause, or quit.

### Hotkeys

| Default | Action |
| --- | --- |
| `ctrl+alt+j` | Show a jumpscare now |
| `ctrl+alt+k` | Play an audio cue now |
| `ctrl+alt+p` | Pause or resume the timers |

## Configuration

Edit `config.json`. Any key you leave out falls back to its default, and unknown keys are rejected so typos are caught at startup.

| Key | Default | Meaning |
| --- | --- | --- |
| `jumpscare_folder` | `assets/jumpscares` | Image folder (relative paths resolve from the config file's folder) |
| `jumpscare_sound_folder` | `assets/jumpscare_sounds` | Fallback sound folder |
| `cue_folder` | `assets/cues` | Audio cue folder |
| `jumpscare_interval_seconds` | `{min: 180, max: 900}` | Random wait between jumpscares |
| `jumpscare_duration_ms` | `1000` | Total time a still image is on screen, fade included (GIFs play in full instead) |
| `jumpscare_fade_ms` | `200` | Fade-out length, `0` for an instant cut; must not exceed the duration |
| `jumpscare_scale` | `0.9` | Max image size as a fraction of the screen |
| `jumpscare_audio_chance` | `1.0` | Probability a jumpscare plays a sound |
| `jumpscare_volume` | `1.0` | Jumpscare volume, 0 to 1 |
| `cues_enabled` | `true` | Turn the cue timer on or off |
| `cue_interval_seconds` | `{min: 60, max: 300}` | Random wait between cues |
| `cue_volume` | `0.8` | Cue volume, 0 to 1 |
| `monitor` | `0` | Screen index to show jumpscares on (falls back to primary) |
| `hotkeys` | see above | Key combos in `keyboard` library syntax; an empty string disables one |

Use `--config path\to\other.json` to load a different file.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Project layout

```
jumpscare/
  __main__.py   entry point, logging, Qt app
  app.py        timers, tray icon, hotkeys
  overlay.py    transparent click-through window
  audio.py      pygame mixer wrapper
  media.py      file discovery and random selection
  config.py     config loading and validation
tests/
```
