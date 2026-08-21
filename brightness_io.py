"""Binary brightness-data I/O shared by the brightness analysis program."""

from __future__ import annotations

import array
import sys
from pathlib import Path

import numpy as np


BRIGHTNESS_WIDTH = 4784
BRIGHTNESS_HEIGHT = 3190
FLOAT32_BYTES = 4


def validate_brightness_bin(
    bin_path: str | Path,
    width: int = BRIGHTNESS_WIDTH,
    height: int = BRIGHTNESS_HEIGHT,
) -> Path:
    path = Path(bin_path).expanduser()
    expected_size = width * height * FLOAT32_BYTES
    actual_size = path.stat().st_size
    if actual_size != expected_size:
        raise ValueError(
            f"亮度文件大小错误：期望 {expected_size} 字节，实际 {actual_size} 字节"
        )
    return path


def convert_brightness_bin_to_txt(
    bin_path: str | Path,
    txt_path: str | Path | None = None,
    width: int = BRIGHTNESS_WIDTH,
    height: int = BRIGHTNESS_HEIGHT,
) -> Path:
    """Convert little-endian float32 data into a height-by-width text matrix."""
    source = validate_brightness_bin(bin_path, width, height)
    destination = Path(txt_path).expanduser() if txt_path else source.with_suffix(".txt")
    destination.parent.mkdir(parents=True, exist_ok=True)
    row_bytes = width * FLOAT32_BYTES
    with source.open("rb") as binary, destination.open("w", encoding="utf-8", newline="\n") as text:
        for row_index in range(height):
            raw = binary.read(row_bytes)
            if len(raw) != row_bytes:
                raise ValueError(f"亮度文件在第 {row_index + 1} 行提前结束")
            values = array.array("f")
            values.frombytes(raw)
            if sys.byteorder != "little":
                values.byteswap()
            text.write(" ".join(format(value, ".9g") for value in values))
            text.write("\n")
    return destination.resolve()


def _numpy_uniform_filter(data: np.ndarray, size: int) -> np.ndarray:
    """NumPy fallback for a square mean filter with reflected edges."""
    before = size // 2
    after = size - before - 1
    filtered = np.asarray(data, dtype=np.float64)
    for axis in (0, 1):
        pad_width = [(0, 0), (0, 0)]
        pad_width[axis] = (before, after)
        padded = np.pad(filtered, pad_width, mode="symmetric")
        cumulative = np.cumsum(padded, axis=axis, dtype=np.float64)
        zero_shape = list(cumulative.shape)
        zero_shape[axis] = 1
        cumulative = np.concatenate(
            (np.zeros(zero_shape, dtype=np.float64), cumulative), axis=axis
        )
        head = [slice(None), slice(None)]
        tail = [slice(None), slice(None)]
        head[axis] = slice(size, None)
        tail[axis] = slice(None, -size)
        filtered = (cumulative[tuple(head)] - cumulative[tuple(tail)]) / size
    return filtered


def create_corrected_brightness_txt(
    source_path: str | Path,
    output_path: str | Path | None = None,
    width: int = BRIGHTNESS_WIDTH,
    height: int = BRIGHTNESS_HEIGHT,
    filter_size: int = 20,
) -> Path:
    """Create ``mat / uniform_filter(mat)`` data and save it as text."""
    source = Path(source_path).expanduser()
    if source.suffix.lower() == ".bin":
        validate_brightness_bin(source, width, height)
        data = np.memmap(source, dtype="<f4", mode="r", shape=(height, width))
    else:
        data = np.loadtxt(source, dtype=np.float32)
        if data.shape != (height, width):
            raise ValueError(
                f"亮度矩阵尺寸错误：期望 {width} × {height}，实际 "
                f"{data.shape[1]} × {data.shape[0]}"
            )

    try:
        from scipy.ndimage import uniform_filter

        blurred = uniform_filter(np.asarray(data, dtype=np.float64), size=filter_size)
    except ImportError:
        blurred = _numpy_uniform_filter(data, filter_size)

    corrected = np.zeros_like(blurred)
    np.divide(data, blurred, out=corrected, where=blurred != 0)
    corrected[~np.isfinite(corrected)] = 0

    destination = (
        Path(output_path).expanduser()
        if output_path
        else source.with_name(f"修正{source.stem}.txt")
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(destination, corrected, fmt="%.9g")
    return destination.resolve()
