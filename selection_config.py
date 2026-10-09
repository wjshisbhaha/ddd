"""Circle selection configuration and corrected-brightness calculations."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import numpy as np


NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?(?![A-Za-z])"
)


def parse_circle_config(path: str | Path) -> list[tuple[int, float, float, float]]:
    """Return (sequence, center_x, center_y, radius) for type-2 rows."""
    source = Path(path).expanduser()
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = source.read_text(encoding="gb18030")
    circles: list[tuple[int, float, float, float]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        numbers = NUMBER_PATTERN.findall(line)
        # 先用前两列判断记录类型。非数据行或非圆形记录直接跳过；
        # 只有第二列为2的圆形记录才必须提供完整的6个数字。
        if len(numbers) < 2:
            continue
        sequence = int(float(numbers[0]))
        shape_type = int(float(numbers[1]))
        if shape_type != 2:
            continue
        if len(numbers) < 6:
            raise ValueError(
                f"{source.name} 第{line_number}行是圆形记录（第二列为2），但不足6个数字"
            )
        center_x = float(numbers[2])
        center_y = float(numbers[3])
        right_x = float(numbers[4])
        radius = abs(right_x - center_x)
        if radius <= 0:
            raise ValueError(f"{source.name} 第{line_number}行圆半径必须大于0")
        circles.append((sequence, center_x, center_y, radius))
    circles.sort(key=lambda item: item[0])
    if not circles:
        raise ValueError(f"{source.name} 没有类型为2的圆形配置")
    return circles


def calculate_circle_corrected_values(
    corrected_data: np.ndarray,
    circles: list[tuple[int, float, float, float]],
) -> list[float]:
    """Calculate speckle contrast (standard deviation / mean) in each circle."""
    if corrected_data.ndim != 2:
        raise ValueError("修正亮度数据必须是二维矩阵")
    height, width = corrected_data.shape
    values: list[float] = []
    for sequence, center_x, center_y, radius in circles:
        left = max(0, int(np.floor(center_x - radius)))
        right = min(width - 1, int(np.ceil(center_x + radius)))
        top = max(0, int(np.floor(center_y - radius)))
        bottom = min(height - 1, int(np.ceil(center_y + radius)))
        if left > right or top > bottom:
            raise ValueError(f"序号{sequence}的圆形区域在亮度数据范围外")
        yy, xx = np.ogrid[top:bottom + 1, left:right + 1]
        mask = (xx - center_x) ** 2 + (yy - center_y) ** 2 <= radius ** 2
        pixels = corrected_data[top:bottom + 1, left:right + 1][mask]
        pixels = pixels[np.isfinite(pixels)]
        if pixels.size == 0:
            raise ValueError(f"序号{sequence}的圆形区域没有有效修正亮度数据")
        mean_value = float(np.mean(pixels, dtype=np.float64))
        if mean_value == 0:
            raise ValueError(f"序号{sequence}的圆形区域平均值为0，无法计算散斑对比度")
        std_value = float(np.std(pixels, dtype=np.float64))
        values.append(std_value / mean_value)
    return values


def process_corrected_regions(
    plan: list[tuple[str, list[str]]],
    run_dir: str | Path,
    config_dir: str | Path,
) -> list[tuple[str, list[float]]]:
    """Copy used configs and calculate corrected-data speckle contrast by circle."""
    run_path = Path(run_dir).expanduser().resolve()
    source_dir = Path(config_dir).expanduser().resolve()
    if not source_dir.is_dir():
        raise ValueError(f"框选配置目录不存在：{source_dir}")
    blocks: list[tuple[str, list[float]]] = []
    for region_index, (config_name, _commands) in enumerate(plan, start=1):
        numeric_name = Path(config_name).stem
        config_path = source_dir / f"{numeric_name}.txt"
        if not config_path.is_file():
            raise ValueError(f"缺少框选配置文件：{config_path}")
        corrected_path = run_path / f"修正区域{region_index}.txt"
        if not corrected_path.is_file():
            raise ValueError(f"缺少修正亮度数据：{corrected_path}")
        copied_path = run_path / config_path.name
        shutil.copy2(config_path, copied_path)
        circles = parse_circle_config(config_path)
        corrected_data = np.loadtxt(corrected_path, dtype=np.float64)
        values = calculate_circle_corrected_values(corrected_data, circles)
        blocks.append((f"修正区域{region_index}", values))
    return blocks
