"""Turning a monitor into the regions that are cascaded independently.

Today a monitor has exactly one region: its whole work area. This is the single place to extend
for ultrawide monitors (limit the region to a maximum aspect ratio, or split the monitor into
several virtual screens) and for per-monitor overrides. See "Planned: ultrawide and portrait
monitors" in docs/PLAN.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .model import Monitor, Rect
from .settings import Settings


@dataclass(frozen=True)
class Region:
    index: int
    rect: Rect  # work area of the region, before the margin is applied


def regions_for_monitor(monitor: Monitor, settings: Settings) -> List[Region]:
    return [Region(0, monitor.workarea)]
