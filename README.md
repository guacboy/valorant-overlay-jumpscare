# Valorant Overlay Jumpscare

A transparent, click-through overlay that flashes a random image, GIF or video over your screen at random intervals while you play, with optional audio. It can also play random sounds on a separate timer.

It is a normal always-on-top desktop window. It does not read game memory, inject into the game, or touch Valorant files.

## Requirements

- Windows 10/11
- Python 3.11+
- Valorant set to **Windowed Fullscreen** (Settings > Video > Display Mode). Exclusive fullscreen draws over every other window, so the overlay would be hidden.

## Setup

Commands below are for a bash terminal (Git Bash on Windows).

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements-dev.txt
git config core.hooksPath .githooks
```

On macOS or Linux the activate script is at `.venv/bin/activate` instead. The last line enables the pre-push hook, which runs the test suite and blocks the push if it fails.

## Adding media

| Folder | Contents |
| --- | --- |
| `assets/jumpscares/` | Images (`.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`) and videos (`.mp4`, `.webm`, `.mov`, `.mkv`, `.avi`) |
| `assets/sounds/` | Sounds (`.wav`, `.ogg`, `.mp3`) played on their own timer |

Every jumpscare fills the whole screen. Media whose shape differs from your monitor's is scaled up until there are no gaps, and the overflow is cropped evenly from the edges.

Still images pop up for `jumpscare_duration_ms` (1 second by default) and then vanish instantly, with no fade. Animated GIFs and videos ignore that setting: each one plays through once for its full length, then vanishes. GIFs that are set to loop still play only once. Videos play with their own sound track at `jumpscare_volume`.

### Green screen videos

Green screen videos are keyed automatically. When a video is loaded, the overlay checks the edges of its first frame. If they are mostly bright green, the green is removed from every frame (with soft edges and green spill cleanup) so only the subject appears over your game. Videos without a green border play unchanged, so green objects in normal footage are left alone. To keep 60 fps video smooth, keyed frames are processed at up to 960 pixels wide and then scaled to your screen, which softens the cut-out edges slightly.

Video frames are converted and keyed on a background thread, so the overlay never falls behind the video's sound. If your PC is busy (for example mid-match), the overlay skips a frame instead of slowing the video down.

### Instant playback

The app keeps everything loaded in the background between jumpscares. As soon as one finishes, the next one is picked and loaded during the quiet time, including its sound and, for videos, its first frame and the green screen check. A single video player is created at startup and reused, so when the timer fires the jumpscare appears immediately instead of waiting for a player to start.

### Sounds

A jumpscare only plays a sound when an audio file (`.wav`, `.ogg`, `.mp3`) with exactly the same name sits next to it in `assets/jumpscares/`, e.g. `scream.png` with `scream.mp3`. Without one, an image pops up silently and a video plays with just its own sound track.

Dead silence at the start and end of every sound file (jumpscare sounds and files in `assets/sounds/`) is trimmed automatically when it is loaded, so sounds hit right away. Anything quieter than `trim_silence_threshold` counts as silence. A video's own sound track is not trimmed.

### No overlapping

Jumpscares and sounds never play over each other. Each one starts at least `min_gap_seconds` (5 by default) after the previous one has completely finished, counting the full length of any sound and the whole run of a GIF or video. If a timer fires too early, that event waits for the gap instead of being skipped. When both are waiting, the one that has waited longer goes first. The tray and hotkey test actions play immediately, but the next timed event still waits for them.

Folders are rescanned on every trigger, so you can add files while the overlay is running. Media files are gitignored.

## Running

With the venv activated:

```bash
python -m jumpscare
```

To keep it running without tying up the terminal, start it with `pythonw -m jumpscare &` instead. Logs go to `overlay.log` either way.

A red dot appears in the system tray. Right-click it to test a jumpscare, test a sound, pause, or quit.

### Hotkeys

| Default | Action |
| --- | --- |
| `ctrl+alt+j` | Show a jumpscare now |
| `ctrl+alt+k` | Play a sound now |
| `ctrl+alt+p` | Pause or resume the timers |

## Configuration

Edit `config.json`. Any key you leave out falls back to its default, and unknown keys are rejected so typos are caught at startup.

| Key | Default | Meaning |
| --- | --- | --- |
| `jumpscare_folder` | `assets/jumpscares` | Image folder (relative paths resolve from the config file's folder) |
| `sound_folder` | `assets/sounds` | Folder of sounds played on their own timer |
| `jumpscare_interval_seconds` | `{min: 180, max: 900}` | Random wait between jumpscares |
| `jumpscare_duration_ms` | `1000` | How long a still image is on screen (GIFs and videos play in full instead) |
| `jumpscare_audio_chance` | `1.0` | Probability a same-named sound plays with its jumpscare |
| `jumpscare_volume` | `1.0` | Jumpscare volume (sounds and video sound tracks), 0 to 1 |
| `sounds_enabled` | `true` | Turn the sound timer on or off |
| `sound_interval_seconds` | `{min: 60, max: 300}` | Random wait between sounds |
| `sound_volume` | `0.8` | Sound volume, 0 to 1 |
| `trim_silence_threshold` | `0.01` | Level (fraction of full volume) below which leading and trailing audio is cut, `0` to disable |
| `min_gap_seconds` | `5` | Minimum quiet time between the end of one jumpscare or sound and the start of the next |
| `monitor` | `0` | Screen index to show jumpscares on (falls back to primary) |
| `hotkeys` | see above | Key combos in `keyboard` library syntax; an empty string disables one |

Use `--config path/to/other.json` to load a different file.

## Tests

```bash
python -m pytest
```

## Project layout

```
jumpscare/
  __main__.py   entry point, logging, Qt app
  app.py        timers, tray icon, hotkeys
  overlay.py    transparent click-through window, GIF and video playback
  audio.py      pygame mixer wrapper, silence trimming
  media.py      file discovery and random selection
  gate.py       keeps jumpscares and sounds from overlapping
  chroma.py     green screen detection and keying
  config.py     config loading and validation
tests/
```
