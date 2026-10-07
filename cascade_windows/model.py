"""Backend independent data types.

All coordinates are in pixels and are relative to the top-left corner of one workspace "cell",
that is, the area of one screen. Backends translate to and from the coordinates used by the
window system (for example viewport offsets on Compiz).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

# Window kinds. Only "normal" windows are cascaded; dialogs are left where they are.
KIND_NORMAL = "normal"
KIND_DIALOG = "dialog"
KIND_OTHER = "other"


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center(self) -> Tuple[float, float]:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px < self.right and self.y <= py < self.bottom

    def distance_sq(self, px: float, py: float) -> float:
        """Squared distance from a point to the rectangle (0 when inside)."""
        dx = max(self.x - px, 0, px - (self.right - 1))
        dy = max(self.y - py, 0, py - (self.bottom - 1))
        return dx * dx + dy * dy

    def intersect(self, other: "Rect") -> "Rect":
        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        return Rect(left, top, max(0, right - left), max(0, bottom - top))

    def to_list(self) -> List[int]:
        return [self.x, self.y, self.width, self.height]

    @staticmethod
    def from_list(values) -> "Rect":
        x, y, width, height = (int(v) for v in values)
        return Rect(x, y, width, height)

    def __str__(self) -> str:
        return "%dx%d%+d%+d" % (self.width, self.height, self.x, self.y)


@dataclass(frozen=True)
class Monitor:
    index: int
    name: str
    rect: Rect
    workarea: Rect  # monitor rectangle minus panels, docks and launchers


@dataclass(frozen=True)
class WindowInfo:
    id: int
    title: str
    wm_class: str
    workspace: str  # opaque workspace key, see Backend.workspaces()
    rect: Rect  # visible window rectangle including decorations
    kind: str = KIND_NORMAL
    minimized: bool = False
    fullscreen: bool = False
    sticky: bool = False
    maximized: bool = False
    resizable: bool = True
    stack_index: int = 0  # position in the stacking order, 0 = bottom
    open_index: int = 0  # position in the opening order, 0 = oldest

    def describe(self) -> str:
        flags = [
            name
            for name, value in (
                ("minimized", self.minimized),
                ("fullscreen", self.fullscreen),
                ("sticky", self.sticky),
                ("maximized", self.maximized),
                ("fixed-size", not self.resizable),
            )
            if value
        ]
        return "0x%x %-6s ws=%s %s %r [%s]%s" % (
            self.id,
            self.kind,
            self.workspace,
            self.rect,
            self.title[:40],
            self.wm_class,
            (" (" + ", ".join(flags) + ")") if flags else "",
        )
