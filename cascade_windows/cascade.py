"""Planning and applying a cascade. The planning part is pure and has no window system access."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .backend import Backend
from .geometry import ANCHOR_TOP_LEFT, ANCHOR_TOP_RIGHT, plan_layout, usable_area
from .model import KIND_DIALOG, KIND_NORMAL, Monitor, Rect, WindowInfo
from .regions import Region, regions_for_monitor
from .settings import Settings

log = logging.getLogger("cascade_windows")

SCOPE_MONITOR = "monitor"  # the monitor under the mouse pointer, current workspace
SCOPE_WORKSPACE = "workspace"  # every monitor of the current workspace
SCOPE_ALL = "all"  # every monitor of every workspace
SCOPES = (SCOPE_MONITOR, SCOPE_WORKSPACE, SCOPE_ALL)


@dataclass(frozen=True)
class Move:
    window: WindowInfo
    workspace: str
    rect: Rect
    anchor: str
    resize: bool = True  # False: the window keeps its own size


@dataclass
class GroupSummary:
    workspace: str
    monitor_name: str
    region_index: int
    area: Rect
    count: int


@dataclass
class Plan:
    moves: List[Move] = field(default_factory=list)  # back to front within each group
    groups: List[GroupSummary] = field(default_factory=list)

    def describe(self) -> List[str]:
        lines = []
        for group in self.groups:
            lines.append(
                "workspace %s, monitor %s, region %d: %d window(s) in %s"
                % (group.workspace, group.monitor_name, group.region_index, group.count, group.area)
            )
        for move in self.moves:
            lines.append(
                "  0x%x %r -> %s (%s)" % (move.window.id, move.window.title[:40], move.rect, move.anchor)
            )
        return lines


def is_eligible(window: WindowInfo, settings: Settings) -> bool:
    """Normal windows and (unless skipped) dialogs are cascaded; special windows stay where they are."""
    if window.kind == KIND_DIALOG:
        if settings.skip_dialogs:
            return False
    elif window.kind != KIND_NORMAL:
        return False
    if window.minimized and settings.skip_minimized:
        return False
    if window.fullscreen and settings.skip_fullscreen:
        return False
    if window.sticky and settings.skip_sticky:
        return False
    if window.maximized and not settings.restore_maximized:
        return False
    return True


def sort_windows(windows: Sequence[WindowInfo], order: str) -> List[WindowInfo]:
    """Return the windows back to front according to the configured order."""
    if order == "opening":
        return sorted(windows, key=lambda w: (w.open_index, w.stack_index))
    if order == "name":
        return sorted(
            windows, key=lambda w: (w.wm_class.lower(), w.title.lower(), w.open_index)
        )
    return sorted(windows, key=lambda w: (w.stack_index, w.open_index))


def find_monitor(monitors: Sequence[Monitor], x: float, y: float) -> Monitor:
    """The monitor containing a point, or the nearest one."""
    for monitor in monitors:
        if monitor.rect.contains(x, y):
            return monitor
    return min(monitors, key=lambda m: m.rect.distance_sq(x, y))


def find_region(regions: Sequence[Region], x: float, y: float) -> Region:
    for region in regions:
        if region.rect.contains(x, y):
            return region
    return min(regions, key=lambda r: r.rect.distance_sq(x, y))


def build_plan(
    monitors: Sequence[Monitor],
    windows: Sequence[WindowInfo],
    workspaces: Sequence[str],
    current_workspace: str,
    pointer: Tuple[int, int],
    settings: Settings,
    scope: str,
) -> Plan:
    if scope not in SCOPES:
        raise ValueError("Unknown scope %r" % scope)
    plan = Plan()
    if not monitors:
        return plan

    target_monitor: Optional[Monitor] = None
    if scope == SCOPE_MONITOR:
        target_monitor = find_monitor(monitors, pointer[0], pointer[1])

    workspace_rank: Dict[str, int] = {key: i for i, key in enumerate(workspaces)}
    regions_by_monitor = {m.index: regions_for_monitor(m, settings) for m in monitors}

    groups: Dict[Tuple[int, int, int], List[WindowInfo]] = {}
    group_info: Dict[Tuple[int, int, int], Tuple[str, Monitor, Region]] = {}
    for window in windows:
        if not is_eligible(window, settings):
            continue
        if scope != SCOPE_ALL and window.workspace != current_workspace:
            continue
        cx, cy = window.rect.center
        monitor = find_monitor(monitors, cx, cy)
        if target_monitor is not None and monitor.index != target_monitor.index:
            continue
        region = find_region(regions_by_monitor[monitor.index], cx, cy)
        key = (workspace_rank.get(window.workspace, len(workspace_rank)), monitor.index, region.index)
        groups.setdefault(key, []).append(window)
        group_info[key] = (window.workspace, monitor, region)

    for key in sorted(groups):
        workspace, monitor, region = group_info[key]
        ordered = sort_windows(groups[key], settings.order)
        area = usable_area(region.rect, settings)
        placements = plan_layout(len(ordered), area, settings)
        plan.groups.append(GroupSummary(workspace, monitor.name, region.index, area, len(ordered)))
        for window, placement in zip(ordered, placements):
            if window.kind == KIND_DIALOG or not window.resizable:
                # Dialogs and fixed-size windows keep their size; their top-right corner goes to the
                # top-right corner of the cascade position.
                plan.moves.append(Move(window, workspace, placement.rect, ANCHOR_TOP_RIGHT, False))
            else:
                plan.moves.append(Move(window, workspace, placement.rect, placement.anchor))
    return plan


def apply_plan(backend: Backend, plan: Plan, settings: Settings) -> None:
    """Carry out a plan: restore maximized windows, move and resize, then restack."""
    unmaximized = False
    for move in plan.moves:
        if move.window.maximized and settings.restore_maximized:
            backend.unmaximize(move.window)
            unmaximized = True
    if unmaximized:
        backend.sync()
    for move in plan.moves:
        backend.place(move.window, move.workspace, move.rect, move.anchor, move.resize)
    backend.sync()
    for move in plan.moves:  # back to front, so the last window of a group ends up on top
        backend.raise_window(move.window)
    backend.commit()


def plan_for_backend(backend: Backend, settings: Settings, scope: str) -> Plan:
    return build_plan(
        backend.monitors(),
        backend.windows(),
        backend.workspaces(),
        backend.current_workspace(),
        backend.pointer_position(),
        settings,
        scope,
    )


def restore_positions(backend: Backend, entries) -> int:
    """Put windows back to the positions saved in undo entries. Returns how many were restored."""
    by_id = {window.id: window for window in backend.windows()}
    restored = 0
    for entry in entries:
        window = by_id.get(entry.window_id)
        if window is None:
            continue
        backend.place(window, entry.workspace, entry.rect, ANCHOR_TOP_LEFT, window.resizable)
        if entry.maximized:
            backend.set_maximized(window, True)
        restored += 1
    backend.commit()
    return restored
