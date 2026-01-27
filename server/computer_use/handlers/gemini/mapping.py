"""Shared mapping helpers for Gemini computer use."""

from __future__ import annotations

from typing import Tuple

GEMINI_CALL_METADATA_KEY = 'gemini_function_call'
DEFAULT_SCROLL_AMOUNT = 800


def _clamp_0_999(value: int) -> int:
    return max(0, min(999, value))


def get_display_dimensions(computer_tool) -> Tuple[int, int]:
    width = int(getattr(computer_tool, 'width', 1000) or 1000)
    height = int(getattr(computer_tool, 'height', 1000) or 1000)
    return width, height


def normalize_coordinate(coordinate: Tuple[int, int], width: int, height: int) -> dict:
    if not coordinate or width <= 0 or height <= 0:
        return {'x': 0, 'y': 0}

    x, y = coordinate
    x_norm = _clamp_0_999(int(round(x / width * 1000)))
    y_norm = _clamp_0_999(int(round(y / height * 1000)))
    return {'x': x_norm, 'y': y_norm}


def denormalize_coordinate(
    x: int | float, y: int | float, width: int, height: int
) -> Tuple[int, int]:
    if width <= 0 or height <= 0:
        return int(x), int(y)

    x_px = int(round((float(x) / 1000.0) * width))
    y_px = int(round((float(y) / 1000.0) * height))
    return x_px, y_px
