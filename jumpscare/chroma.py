"""Green screen detection and keying on RGBA uint8 arrays shaped (height, width, 4)."""

import numpy as np

# How much greener than max(red, blue) a pixel must be. Below LOW it is fully kept,
# above HIGH it is fully removed, and in between it is partially transparent.
KEY_LOW = 25
KEY_HIGH = 70
MIN_KEY_GREEN = 60  # dark pixels are never treated as screen
BORDER_FRACTION = 0.05  # outer band of the frame sampled for detection
DETECT_RATIO = 0.6  # share of border pixels that must be green to count as a green screen

# Alpha for every possible dominance value (-255..255, offset by 255). The second half is
# used for pixels too dark to key, so they always stay opaque. A lookup is much faster
# than computing the ramp per pixel.
_RAMP = np.clip((np.arange(-255, 256) - KEY_LOW) / (KEY_HIGH - KEY_LOW), 0.0, 1.0)
_ALPHA_LUT = np.concatenate(
    [np.round(255 * (1.0 - _RAMP)).astype(np.uint8), np.full(511, 255, dtype=np.uint8)]
)


def _dominance(rgba: np.ndarray) -> np.ndarray:
    rgb = rgba[..., :3].astype(np.int16)
    return rgb[..., 1] - np.maximum(rgb[..., 0], rgb[..., 2])


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
    if not border.size:
        return False
    screen = (_dominance(border) >= KEY_HIGH) & (border[..., 1] >= MIN_KEY_GREEN)
    return float(screen.mean()) >= DETECT_RATIO


def chroma_key(rgba: np.ndarray) -> np.ndarray:
    """Return a copy of an opaque frame with green screen made transparent and green spill removed."""
    green = rgba[..., 1]
    red_blue = np.maximum(rgba[..., 0], rgba[..., 2])

    index = green.astype(np.int16)
    index -= red_blue
    index += 255
    index += (green < MIN_KEY_GREEN) * np.int16(511)

    out = rgba.copy()
    out[..., 3] = _ALPHA_LUT[index]
    # Despill: green fringes on kept edges are pulled down to the red/blue level.
    np.minimum(green, red_blue, out=out[..., 1])
    return out
