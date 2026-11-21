"""Serial protocol for the Turing-style 3.5" USB secondary screen ("Rev A" family).

Pure functions only (no I/O), so everything here is unit-testable without hardware.

Wire format, as documented by the community (see README, "Protocol"):

* Every command is a 6-byte packet.  X/Y coordinates are 10-bit values packed
  across the first five bytes, and the last byte is the command code.
* ``DISPLAY_BITMAP`` is followed by raw little-endian RGB565 pixels for the
  rectangle (x, y) .. (ex, ey), inclusive.
* ``SET_ORIENTATION`` uses an 11-byte packet carrying the orientation and the
  resulting width/height.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

# Command codes
CMD_RESET = 0x65
CMD_CLEAR = 0x66
CMD_TO_BLACK = 0x67
CMD_SCREEN_OFF = 0x6C
CMD_SCREEN_ON = 0x6D
CMD_SET_BRIGHTNESS = 0x6E
CMD_SET_ORIENTATION = 0x79
CMD_DISPLAY_BITMAP = 0xC5
CMD_HELLO = 0x45

# Native panel is 320x480 portrait.
NATIVE_WIDTH = 320
NATIVE_HEIGHT = 480

ORIENTATIONS = {
    "portrait": 0,
    "reverse_portrait": 1,
    "landscape": 2,
    "reverse_landscape": 3,
}


def screen_size(orientation: str) -> tuple[int, int]:
    """Logical (width, height) for an orientation name."""
    if orientation not in ORIENTATIONS:
        raise ValueError(
            f"orientation must be one of {sorted(ORIENTATIONS)}, got {orientation!r}"
        )
    if ORIENTATIONS[orientation] in (0, 1):
        return NATIVE_WIDTH, NATIVE_HEIGHT
    return NATIVE_HEIGHT, NATIVE_WIDTH


def command_packet(cmd: int, x: int = 0, y: int = 0, ex: int = 0, ey: int = 0) -> bytes:
    """Build the 6-byte command packet (coordinates packed into 10-bit fields)."""
    for name, v in (("x", x), ("y", y), ("ex", ex), ("ey", ey)):
        if not 0 <= v <= 0x3FF:
            raise ValueError(f"{name}={v} out of range 0..1023")
    return bytes(
        [
            x >> 2,
            ((x & 3) << 6) | (y >> 4),
            ((y & 15) << 4) | (ex >> 6),
            ((ex & 63) << 2) | (ey >> 8),
            ey & 0xFF,
            cmd,
        ]
    )


def orientation_packet(orientation: str) -> bytes:
    """11-byte packet that selects orientation and announces the resulting size."""
    w, h = screen_size(orientation)
    return bytes(
        [0, 0, 0, 0, 0, CMD_SET_ORIENTATION, ORIENTATIONS[orientation] + 100]
        + [w >> 8, w & 0xFF, h >> 8, h & 0xFF]
    )


def brightness_packet(percent: float, inverted: bool = True) -> bytes:
    """Brightness 0-100 %.

    Community docs say the panel's scale is inverted (0 = brightest, 255 = darkest);
    ``inverted=False`` flips that in case a panel revision behaves the other way.
    """
    percent = max(0.0, min(100.0, float(percent)))
    raw = int(round(255 * percent / 100))
    if inverted:
        raw = 255 - raw
    return command_packet(CMD_SET_BRIGHTNESS, x=raw)


def screen_on_packet() -> bytes:
    return command_packet(CMD_SCREEN_ON)


def screen_off_packet() -> bytes:
    return command_packet(CMD_SCREEN_OFF)


def bitmap_header(x: int, y: int, width: int, height: int) -> bytes:
    """Header preceding the pixel data for a width x height rectangle at (x, y)."""
    if width <= 0 or height <= 0:
        raise ValueError("empty rectangle")
    return command_packet(CMD_DISPLAY_BITMAP, x, y, x + width - 1, y + height - 1)


def align_rect(
    rect: tuple[int, int, int, int], align: int, width: int, height: int
) -> tuple[int, int, int, int]:
    """Grow a rectangle outwards so every edge sits on a multiple of ``align`` pixels.

    Some panels mis-handle pixel data for rectangles with odd positions/widths, so all
    transmissions are snapped to a grid.  Edges are clamped to the screen.
    """
    if align <= 1:
        return rect
    x0, y0, x1, y1 = rect
    x0, y0 = (x0 // align) * align, (y0 // align) * align
    x1, y1 = -(-x1 // align) * align, -(-y1 // align) * align
    return x0, y0, min(x1, width), min(y1, height)


def rotate_region(
    image: Image.Image, x: int, y: int, mode: str, full_w: int, full_h: int
) -> tuple[Image.Image, int, int]:
    """Map a logical-landscape rectangle onto the native-portrait panel.

    ``mode`` is "ccw" or "cw" (the direction the picture is turned).  ``full_w`` x
    ``full_h`` is the logical screen (480 x 320).  Returns the turned image and its
    new top-left corner, so partial updates still land in the right place.
    """
    w, h = image.size
    if mode == "ccw":
        return image.transpose(Image.ROTATE_90), y, full_w - (x + w)
    if mode == "cw":
        return image.transpose(Image.ROTATE_270), full_h - (y + h), x
    raise ValueError("rotate must be 'cw' or 'ccw'")


def rgb565_array(image: Image.Image) -> np.ndarray:
    """PIL image -> (h, w) uint16 array of RGB565 values (what the panel really shows)."""
    a = np.asarray(image.convert("RGB"), dtype=np.uint16)
    return ((a[..., 0] & 0xF8) << 8) | ((a[..., 1] & 0xFC) << 3) | (a[..., 2] >> 3)


def rgb565_le(image: Image.Image) -> bytes:
    """Convert a PIL image to little-endian RGB565 bytes (row-major)."""
    return rgb565_array(image).astype("<u2").tobytes()


def changed_rects(
    diff: np.ndarray, tile: int = 32, max_rects: int = 6
) -> list[tuple[int, int, int, int]]:
    """Turn a boolean (h, w) "pixel changed" mask into a few tight rectangles.

    The mask is coarsened to ``tile`` x ``tile`` blocks, horizontal runs of blocks are
    merged, identical runs on consecutive rows are stacked, and each rectangle is then
    shrunk to the pixels that really changed.  If that still gives more than
    ``max_rects`` pieces (each blit has fixed latency) one bounding box is returned.
    """
    h, w = diff.shape
    if not diff.any():
        return []
    th, tw = -(-h // tile), -(-w // tile)
    pad = np.zeros((th * tile, tw * tile), dtype=bool)
    pad[:h, :w] = diff
    blocks = pad.reshape(th, tile, tw, tile).any(axis=(1, 3))

    open_runs: dict[tuple[int, int], int] = {}  # (c0, c1) -> first tile row
    spans: list[tuple[int, int, int, int]] = []  # r0, r1, c0, c1 (tile units, end exclusive)
    for r in range(th + 1):
        runs = set()
        if r < th:
            c = 0
            while c < tw:
                if blocks[r, c]:
                    c0 = c
                    while c < tw and blocks[r, c]:
                        c += 1
                    runs.add((c0, c))
                else:
                    c += 1
        for key in list(open_runs):
            if key not in runs:
                spans.append((open_runs.pop(key), r, key[0], key[1]))
        for key in runs:
            open_runs.setdefault(key, r)

    rects = []
    for r0, r1, c0, c1 in spans:
        y0, y1, x0, x1 = r0 * tile, min(r1 * tile, h), c0 * tile, min(c1 * tile, w)
        sub = diff[y0:y1, x0:x1]
        ys, xs = np.flatnonzero(sub.any(axis=1)), np.flatnonzero(sub.any(axis=0))
        rects.append((x0 + int(xs[0]), y0 + int(ys[0]), x0 + int(xs[-1]) + 1, y0 + int(ys[-1]) + 1))
    if len(rects) > max_rects:
        rects = [
            (min(r[0] for r in rects), min(r[1] for r in rects),
             max(r[2] for r in rects), max(r[3] for r in rects))
        ]
    return rects
