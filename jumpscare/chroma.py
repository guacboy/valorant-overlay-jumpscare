"""Green screen detection and keying on RGBA uint8 arrays shaped (height, width, 4)."""

import numpy as np

# How much greener than max(red, blue) a pixel must be. Below LOW it is fully kept,
# above HIGH it is fully removed, and in between it is partially transparent.
KEY_LOW = 25
KEY_HIGH = 70
MIN_KEY_GREEN = 60  # dark pixels are never treated as screen
BORDER_FRACTION = 0.05  # outer band of the frame sampled for detection
DETECT_RATIO = 0.6  # share of border pixels that must be green to count as a green screen


def _dominance(rgba: np.ndarray) -> np.ndarray:
    rgb = rgba[..., :3].astype(np.int16)
    return rgb[..., 1] - np.maximum(rgb[..., 0], rgb[..., 2])


def _is_screen_green(rgba: np.ndarray) -> np.ndarray:
    return (_dominance(rgba) >= KEY_HIGH) & (rgba[..., 1] >= MIN_KEY_GREEN)


def is_green_screen(rgba: np.ndarray) -> bool:
    """True when most of the frame's outer border is screen green."""
    h, w = rgba.shape[:2]
    band = max(1, int(min(h, w) * BORDER_FRACTION))
    border = np.concatenate(
        [
            rgba[:band].reshape(-1, 4),
            rgba[-band:].reshape(-1, 4),
            rgba[band:-band, :band].reshape(-1, 4),
            rgba[band:-band, -band:].reshape(-1, 4),
        ]
    )
    return bool(border.size) and float(_is_screen_green(border).mean()) >= DETECT_RATIO


def chroma_key(rgba: np.ndarray) -> np.ndarray:
    """Return a copy with green screen pixels made transparent and green spill removed."""
    out = rgba.copy()
    dom = _dominance(rgba)
    keep = 1.0 - np.clip((dom - KEY_LOW) / (KEY_HIGH - KEY_LOW), 0.0, 1.0)
    keep[rgba[..., 1] < MIN_KEY_GREEN] = 1.0
    out[..., 3] = (rgba[..., 3] * keep).astype(np.uint8)

    # Despill: green fringes on kept edges are pulled down to the red/blue level.
    limit = np.maximum(rgba[..., 0], rgba[..., 2])
    out[..., 1] = np.minimum(rgba[..., 1], limit)
    return out
