"""Pure layout math. No window system access.

Windows are always handled back to front: index 0 is the back window, the last index is the
front window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .model import Rect
from .settings import Settings

ANCHOR_TOP_LEFT = "top-left"
ANCHOR_BOTTOM_LEFT = "bottom-left"


@dataclass(frozen=True)
class Placement:
    """Where one window should go and which corner must stay put if the size gets adjusted."""

    rect: Rect
    anchor: str


def usable_area(workarea: Rect, settings: Settings) -> Rect:
    """Shrink a work area by the configured margins (never below 1x1)."""
    left = workarea.x + settings.margin_left
    top = workarea.y + settings.margin_top
    right = workarea.right - settings.margin_right
    bottom = workarea.bottom - settings.margin_bottom
    return Rect(left, top, max(1, right - left), max(1, bottom - top))


def _fixed_window_size(area: Rect, settings: Settings) -> Tuple[int, int]:
    """Window size for the percent and fixed modes, limited to the area."""
    if settings.size_mode == "percent":
        width = round(area.width * settings.percent_width / 100.0)
        height = round(area.height * settings.percent_height / 100.0)
    else:
        width, height = settings.fixed_width, settings.fixed_height
    return max(1, min(width, area.width)), max(1, min(height, area.height))


def _smallest_size(area: Rect, settings: Settings) -> Tuple[int, int]:
    """The smallest size a window may get in this mode."""
    if settings.size_mode in ("percent", "fixed"):
        return _fixed_window_size(area, settings)
    return settings.min_width, settings.min_height


def _capacity(area: Rect, settings: Settings) -> Optional[int]:
    """How many windows fit one round of the cascade. None means there is no limit."""
    min_width, min_height = _smallest_size(area, settings)
    limits = []
    if settings.step_x > 0:
        limits.append((area.width - min_width) // settings.step_x + 1)
    if settings.step_y > 0:
        limits.append((area.height - min_height) // settings.step_y + 1)
    if not limits:
        return None
    return max(1, min(limits))


def _round_area(area: Rect, settings: Settings, round_index: int) -> Rect:
    """The area used by one round. Each extra round starts a little further in."""
    shift = round_index * settings.wrap_offset
    return Rect(
        area.x + shift,
        area.y + shift,
        max(1, area.width - shift),
        max(1, area.height - shift),
    )


def split_into_rounds(count: int, area: Rect, settings: Settings) -> List[int]:
    """Return how many windows go into each round of the cascade."""
    if count <= 0:
        return []
    if not settings.wrap_enabled:
        return [count]
    for rounds in range(1, count + 1):
        capacity = _capacity(_round_area(area, settings, rounds - 1), settings)
        if capacity is None:
            return [count]
        if capacity * rounds >= count:
            sizes = []
            remaining = count
            while remaining > 0:
                take = min(capacity, remaining)
                sizes.append(take)
                remaining -= take
            return sizes
    return [1] * count  # unreachable in practice: capacity is at least 1


def _steps(group: int, spare_width: int, spare_height: int, settings: Settings) -> Tuple[int, int]:
    """Step sizes for a group, compressed when the configured steps would not fit."""
    if group <= 1:
        return 0, 0
    step_x = min(settings.step_x, max(0, spare_width) // (group - 1))
    step_y = min(settings.step_y, max(0, spare_height) // (group - 1))
    return step_x, step_y


def _plan_group(group: int, area: Rect, settings: Settings) -> List[Placement]:
    mode = settings.size_mode
    if mode == "anchored":
        step_x, step_y = _steps(
            group, area.width - settings.min_width, area.height - settings.min_height, settings
        )
        placements = []
        for k in range(group):
            top = area.y + k * step_y
            right = area.right - (group - 1 - k) * step_x
            rect = Rect(area.x, top, max(1, right - area.x), max(1, area.bottom - top))
            placements.append(Placement(rect, ANCHOR_BOTTOM_LEFT))
        return placements

    if mode == "fit":
        step_x, step_y = _steps(
            group, area.width - settings.min_width, area.height - settings.min_height, settings
        )
        width = max(1, area.width - (group - 1) * step_x)
        height = max(1, area.height - (group - 1) * step_y)
    else:  # percent or fixed
        width, height = _fixed_window_size(area, settings)
        step_x, step_y = _steps(group, area.width - width, area.height - height, settings)
    return [
        Placement(Rect(area.x + k * step_x, area.y + k * step_y, width, height), ANCHOR_TOP_LEFT)
        for k in range(group)
    ]


def plan_layout(count: int, area: Rect, settings: Settings) -> List[Placement]:
    """Plan ``count`` windows (back to front) inside the usable ``area``."""
    placements: List[Placement] = []
    for round_index, group in enumerate(split_into_rounds(count, area, settings)):
        placements.extend(_plan_group(group, _round_area(area, settings, round_index), settings))
    return placements
