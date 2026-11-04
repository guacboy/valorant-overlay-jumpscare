"""Writes tiny uncompressed AVI files so video tests don't need ffmpeg or binary fixtures."""

import struct
from pathlib import Path

import numpy as np


def _chunk(tag: bytes, data: bytes) -> bytes:
    pad = b"\x00" if len(data) % 2 else b""
    return tag + struct.pack("<I", len(data)) + data + pad


def _list(kind: bytes, payload: bytes) -> bytes:
    return _chunk(b"LIST", kind + payload)


def write_avi(path: Path, frames: list[np.ndarray], fps: int = 10) -> Path:
    """frames are RGB uint8 arrays shaped (height, width, 3); width must be a multiple of 4."""
    h, w = frames[0].shape[:2]
    frame_size = w * h * 3
    usec = 1_000_000 // fps

    avih = struct.pack(
        "<14I", usec, frame_size * fps, 0, 0x10, len(frames), 0, 1, frame_size, w, h, 0, 0, 0, 0
    )
    strh = (
        b"vids"
        + b"DIB "
        + struct.pack("<IHHIIIIIIIi", 0, 0, 0, 0, 1, fps, 0, len(frames), frame_size, 0xFFFFFFFF, 0)
        + struct.pack("<4h", 0, 0, w, h)
    )
    strf = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, frame_size, 0, 0, 0, 0)
    hdrl = _list(b"hdrl", _chunk(b"avih", avih) + _list(b"strl", _chunk(b"strh", strh) + _chunk(b"strf", strf)))

    # Bottom-up BGR rows, as DIBs expect.
    movi_data = b"".join(_chunk(b"00db", f[::-1, :, ::-1].tobytes()) for f in frames)
    movi = _list(b"movi", movi_data)

    index, offset = b"", 4
    for _ in frames:
        index += b"00db" + struct.pack("<III", 0x10, offset, frame_size)
        offset += 8 + frame_size
    idx1 = _chunk(b"idx1", index)

    body = b"AVI " + hdrl + movi + idx1
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return path


def green_screen_frames(count: int, w: int = 64, h: int = 48) -> list[np.ndarray]:
    """Green background with a red square in the middle."""
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:] = (0, 200, 0)
    frame[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4] = (220, 30, 30)
    return [frame.copy() for _ in range(count)]
