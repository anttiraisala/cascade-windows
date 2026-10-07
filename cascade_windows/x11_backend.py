"""X11 backend: talks to the window manager through the EWMH protocol with python-xlib.

Works with any EWMH compliant window manager, in particular Muffin (Linux Mint Cinnamon) and
Compiz (Ubuntu Unity 7). Compiz workspaces are usually viewports of one large virtual desktop;
both real desktops and viewports are supported.
"""

from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .backend import Backend, BackendError
from .geometry import ANCHOR_BOTTOM_LEFT
from .model import KIND_DIALOG, KIND_NORMAL, KIND_OTHER, Monitor, Rect, WindowInfo

try:
    from Xlib import X, Xatom, display, error
    from Xlib.protocol import event

    _IMPORT_ERROR: Optional[Exception] = None
except ImportError as import_error:  # pragma: no cover - depends on the machine
    _IMPORT_ERROR = import_error

log = logging.getLogger("cascade_windows")

# _NET_MOVERESIZE_WINDOW flag bits (EWMH).
_GRAVITY_NORTH_WEST = 1
_FLAG_X = 1 << 8
_FLAG_Y = 1 << 9
_FLAG_WIDTH = 1 << 10
_FLAG_HEIGHT = 1 << 11
_SOURCE_PAGER = 2 << 12

_STATE_REMOVE = 0
_STATE_ADD = 1

_SETTLE_PASSES = 3
_WM_DELAY = 0.06  # seconds to let the window manager process requests
_UNMAXIMIZE_TIMEOUT = 1.5

_MAXIMIZED = ("_NET_WM_STATE_MAXIMIZED_HORZ", "_NET_WM_STATE_MAXIMIZED_VERT")


@dataclass(frozen=True)
class _Extents:
    left: int = 0
    right: int = 0
    top: int = 0
    bottom: int = 0


@dataclass(frozen=True)
class _Hints:
    min_width: int = 0
    min_height: int = 0
    max_width: int = 0  # 0 means no limit
    max_height: int = 0
    base_width: int = 0
    base_height: int = 0
    inc_width: int = 1
    inc_height: int = 1


@dataclass
class _Extra:
    """Per-window details needed when moving a window."""

    window: object
    net: _Extents
    gtk: _Extents
    hints: _Hints


@dataclass
class _Pending:
    window_id: int
    col: int
    row: int
    rect: Rect
    anchor: str
    sent_x: int
    sent_y: int


@dataclass(frozen=True)
class _Strut:
    left: int
    right: int
    top: int
    bottom: int
    left_start_y: int
    left_end_y: int
    right_start_y: int
    right_end_y: int
    top_start_x: int
    top_end_x: int
    bottom_start_x: int
    bottom_end_x: int


def _to_unsigned(value: int) -> int:
    return int(value) & 0xFFFFFFFF


class X11Backend(Backend):
    name = "x11"

    def __init__(self, display_name: Optional[str] = None) -> None:
        if _IMPORT_ERROR is not None:
            raise BackendError(
                "The Python X11 library is missing. Install it with: sudo apt install python3-xlib"
            )
        try:
            self.display = display.Display(display_name)
        except Exception as problem:  # noqa: BLE001 - python-xlib raises several types
            raise BackendError("Cannot connect to the X server: %s" % problem)
        self.display.set_error_handler(self._ignore_error)
        self.root = self.display.screen().root
        self._atoms: Dict[str, int] = {}
        self._atom_names: Dict[int, str] = {}
        self._extras: Dict[int, _Extra] = {}
        self._pending: List[_Pending] = []
        self._awaiting_unmaximize: Set[int] = set()

        geometry = self.root.get_geometry()
        self.screen_width = int(geometry.width)
        self.screen_height = int(geometry.height)
        self._read_workspace_layout()
        self._supported = {
            self._name_of(a) for a in self._raw_values(self.root, "_NET_SUPPORTED")
        }
        if "_NET_CLIENT_LIST" not in self._supported and not self._cardinals(
            self.root, "_NET_CLIENT_LIST"
        ):
            raise BackendError(
                "The window manager does not support the EWMH window list "
                "(_NET_CLIENT_LIST). Is a window manager running?"
            )

    # ------------------------------------------------------------------ low level

    @staticmethod
    def _ignore_error(err, request) -> None:
        log.debug("Ignoring X error %s for %s", err, request)

    def atom(self, name: str) -> int:
        value = self._atoms.get(name)
        if value is None:
            value = self.display.intern_atom(name)
            self._atoms[name] = value
        return value

    def _name_of(self, atom: int) -> str:
        name = self._atom_names.get(atom)
        if name is None:
            try:
                name = self.display.get_atom_name(atom)
            except error.XError:
                name = ""
            self._atom_names[atom] = name
        return name

    def _property(self, window, name: str):
        try:
            return window.get_full_property(self.atom(name), X.AnyPropertyType)
        except error.XError:
            return None

    def _raw_values(self, window, name: str) -> List[int]:
        prop = self._property(window, name)
        if prop is None or prop.format != 32:
            return []
        return [int(v) for v in prop.value]

    def _cardinals(self, window, name: str) -> List[int]:
        return [_to_unsigned(v) for v in self._raw_values(window, name)]

    def _atom_set(self, window, name: str) -> Set[str]:
        return {self._name_of(a) for a in self._raw_values(window, name)}

    def _atom_list(self, window, name: str) -> List[str]:
        return [self._name_of(a) for a in self._raw_values(window, name)]

    def _text(self, window, name: str) -> str:
        prop = self._property(window, name)
        if prop is None or prop.format != 8:
            return ""
        value = prop.value
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        return str(value)

    def _send_client_message(self, window, type_name: str, values) -> None:
        data = [_to_unsigned(v) for v in values] + [0] * (5 - len(values))
        message = event.ClientMessage(
            window=window, client_type=self.atom(type_name), data=(32, data[:5])
        )
        mask = X.SubstructureRedirectMask | X.SubstructureNotifyMask
        self.root.send_event(message, event_mask=mask)
        self.display.flush()

    # ------------------------------------------------------------------ workspaces

    def _read_workspace_layout(self) -> None:
        self.desktop_count = max(1, (self._cardinals(self.root, "_NET_NUMBER_OF_DESKTOPS") or [1])[0])
        size = self._cardinals(self.root, "_NET_DESKTOP_GEOMETRY")
        if len(size) >= 2 and size[0] > 0 and size[1] > 0:
            self.columns = max(1, int(math.ceil(size[0] / float(self.screen_width))))
            self.rows = max(1, int(math.ceil(size[1] / float(self.screen_height))))
        else:
            self.columns = self.rows = 1
        self.uses_viewports = self.columns * self.rows > 1

    def _viewport_origin(self) -> Tuple[int, int]:
        values = self._cardinals(self.root, "_NET_DESKTOP_VIEWPORT")
        if len(values) >= 2:
            return values[0], values[1]
        return 0, 0

    def _current_desktop(self) -> int:
        values = self._cardinals(self.root, "_NET_CURRENT_DESKTOP")
        desktop = values[0] if values else 0
        return min(desktop, self.desktop_count - 1)

    def _key(self, desktop: int, col: int, row: int) -> str:
        if self.uses_viewports:
            return "%d:%d,%d" % (desktop, col, row)
        return str(desktop)

    def _parse_key(self, key: str) -> Tuple[int, int, int]:
        if ":" in key:
            desktop, cell = key.split(":", 1)
            col, row = cell.split(",", 1)
            return int(desktop), int(col), int(row)
        return int(key), 0, 0

    def current_workspace(self) -> str:
        vx, vy = self._viewport_origin()
        col = min(self.columns - 1, vx // self.screen_width)
        row = min(self.rows - 1, vy // self.screen_height)
        return self._key(self._current_desktop(), col, row)

    def workspaces(self) -> List[str]:
        keys = []
        for desktop in range(self.desktop_count):
            for row in range(self.rows):
                for col in range(self.columns):
                    keys.append(self._key(desktop, col, row))
        return keys

    # ------------------------------------------------------------------ monitors

    def _monitor_rects(self) -> List[Tuple[str, Rect]]:
        found: List[Tuple[str, Rect]] = []
        try:
            if hasattr(self.root, "xrandr_get_monitors"):
                reply = self.root.xrandr_get_monitors(True)
                for item in reply.monitors:
                    if item.width_in_pixels > 0 and item.height_in_pixels > 0:
                        found.append(
                            (
                                self._name_of(item.name) or "monitor",
                                Rect(item.x, item.y, item.width_in_pixels, item.height_in_pixels),
                            )
                        )
        except Exception as problem:  # noqa: BLE001
            log.debug("RandR monitor query failed: %s", problem)
        if not found:
            try:
                resources = self.root.xrandr_get_screen_resources_current()
                for crtc in resources.crtcs:
                    info = self.display.xrandr_get_crtc_info(crtc, resources.config_timestamp)
                    if info.mode and info.width > 0 and info.height > 0:
                        found.append(
                            ("crtc%d" % len(found), Rect(info.x, info.y, info.width, info.height))
                        )
            except Exception as problem:  # noqa: BLE001
                log.debug("RandR CRTC query failed: %s", problem)
        if not found:
            found.append(("screen", Rect(0, 0, self.screen_width, self.screen_height)))
        found.sort(key=lambda item: (item[1].x, item[1].y))
        return found

    def _struts(self) -> List[Tuple[str, _Strut]]:
        candidates: List[int] = []
        seen: Set[int] = set()
        for wid in self._cardinals(self.root, "_NET_CLIENT_LIST"):
            if wid not in seen:
                seen.add(wid)
                candidates.append(wid)
        try:
            for child in self.root.query_tree().children:
                if child.id not in seen:
                    seen.add(child.id)
                    candidates.append(child.id)
        except error.XError:
            pass
        found = []
        for wid in candidates:
            window = self.display.create_resource_object("window", wid)
            values = self._cardinals(window, "_NET_WM_STRUT_PARTIAL")
            if len(values) >= 12:
                strut = _Strut(*values[:12])
            else:
                values = self._cardinals(window, "_NET_WM_STRUT")
                if len(values) < 4:
                    continue
                last_x, last_y = self.screen_width - 1, self.screen_height - 1
                strut = _Strut(*values[:4], 0, last_y, 0, last_y, 0, last_x, 0, last_x)
            if not any((strut.left, strut.right, strut.top, strut.bottom)):
                continue
            title = self._text(window, "_NET_WM_NAME") or hex(wid)
            found.append((title, strut))
        return found

    @staticmethod
    def _overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
        return start_a <= end_b and start_b <= end_a

    def _work_area_for(self, rect: Rect, struts: List[Tuple[str, _Strut]]) -> Rect:
        left = right = top = bottom = 0
        for _title, s in struts:
            if s.left > rect.x and self._overlaps(
                s.left_start_y, s.left_end_y, rect.y, rect.bottom - 1
            ):
                left = max(left, s.left - rect.x)
            edge = self.screen_width - s.right
            if s.right > 0 and rect.right > edge and self._overlaps(
                s.right_start_y, s.right_end_y, rect.y, rect.bottom - 1
            ):
                right = max(right, rect.right - edge)
            if s.top > rect.y and self._overlaps(
                s.top_start_x, s.top_end_x, rect.x, rect.right - 1
            ):
                top = max(top, s.top - rect.y)
            edge = self.screen_height - s.bottom
            if s.bottom > 0 and rect.bottom > edge and self._overlaps(
                s.bottom_start_x, s.bottom_end_x, rect.x, rect.right - 1
            ):
                bottom = max(bottom, rect.bottom - edge)
        area = Rect(rect.x + left, rect.y + top, rect.width - left - right, rect.height - top - bottom)
        clip = self._wm_work_area()
        if clip is not None:
            clipped = area.intersect(clip)
            if clipped.width > 0 and clipped.height > 0:
                area = clipped
        if area.width < 1 or area.height < 1:
            return rect
        return area

    def _wm_work_area(self) -> Optional[Rect]:
        """The window manager's own work area, used only when it looks plausible."""
        values = self._cardinals(self.root, "_NET_WORKAREA")
        index = self._current_desktop()
        if len(values) < 4 * (index + 1):
            return None
        x, y, width, height = values[4 * index : 4 * index + 4]
        if width == 0 or height == 0:
            return None
        if x >= self.screen_width or y >= self.screen_height:
            return None
        if width > self.screen_width or height > self.screen_height:
            return None
        return Rect(x, y, width, height)

    def monitors(self) -> List[Monitor]:
        struts = self._struts()
        result = []
        for index, (name, rect) in enumerate(self._monitor_rects()):
            result.append(Monitor(index, name, rect, self._work_area_for(rect, struts)))
        return result

    def pointer_position(self) -> Tuple[int, int]:
        pointer = self.root.query_pointer()
        return int(pointer.root_x), int(pointer.root_y)

    # ------------------------------------------------------------------ windows

    def _read_extents(self, window, name: str) -> _Extents:
        values = self._cardinals(window, name)
        if len(values) >= 4:
            return _Extents(*[int(v) for v in values[:4]])
        return _Extents()

    def _read_hints(self, window) -> _Hints:
        try:
            raw = window.get_wm_normal_hints()
        except error.XError:
            raw = None
        if raw is None:
            return _Hints()
        flags = int(getattr(raw, "flags", 0))
        min_size = bool(flags & (1 << 4))
        max_size = bool(flags & (1 << 5))
        increment = bool(flags & (1 << 6))
        base_size = bool(flags & (1 << 8))
        min_width = int(getattr(raw, "min_width", 0)) if min_size else 0
        min_height = int(getattr(raw, "min_height", 0)) if min_size else 0
        return _Hints(
            min_width=min_width,
            min_height=min_height,
            max_width=int(getattr(raw, "max_width", 0)) if max_size else 0,
            max_height=int(getattr(raw, "max_height", 0)) if max_size else 0,
            base_width=int(getattr(raw, "base_width", 0)) if base_size else min_width,
            base_height=int(getattr(raw, "base_height", 0)) if base_size else min_height,
            inc_width=max(1, int(getattr(raw, "width_inc", 1))) if increment else 1,
            inc_height=max(1, int(getattr(raw, "height_inc", 1))) if increment else 1,
        )

    def _kind_of(self, window) -> str:
        types = self._atom_list(window, "_NET_WM_WINDOW_TYPE")
        kind = KIND_NORMAL
        for name in types:
            if name == "_NET_WM_WINDOW_TYPE_NORMAL":
                kind = KIND_NORMAL
            elif name == "_NET_WM_WINDOW_TYPE_DIALOG":
                kind = KIND_DIALOG
            else:
                kind = KIND_OTHER
            break
        if kind == KIND_NORMAL:
            transient = self._cardinals(window, "WM_TRANSIENT_FOR")
            if transient and transient[0] != 0:
                kind = KIND_DIALOG
        return kind

    def _visible_abs(self, window, extra: _Extra) -> Optional[Rect]:
        """Visible rectangle (frame without invisible borders) in virtual desktop coordinates."""
        try:
            geometry = window.get_geometry()
            origin = self.root.translate_coords(window, 0, 0)
        except error.XError:
            return None
        vx, vy = self._viewport_origin()
        net, gtk = extra.net, extra.gtk
        return Rect(
            int(origin.x) + vx - net.left + gtk.left,
            int(origin.y) + vy - net.top + gtk.top,
            int(geometry.width) + net.left + net.right - gtk.left - gtk.right,
            int(geometry.height) + net.top + net.bottom - gtk.top - gtk.bottom,
        )

    def _cell_of(self, rect: Rect) -> Tuple[int, int]:
        if not self.uses_viewports:
            return 0, 0
        cx, cy = rect.center
        col = min(self.columns - 1, max(0, int(cx // self.screen_width)))
        row = min(self.rows - 1, max(0, int(cy // self.screen_height)))
        return col, row

    def _read_window(self, wid: int, stack_index: int, open_index: int) -> Optional[WindowInfo]:
        window = self.display.create_resource_object("window", wid)
        extra = _Extra(
            window,
            self._read_extents(window, "_NET_FRAME_EXTENTS"),
            self._read_extents(window, "_GTK_FRAME_EXTENTS"),
            self._read_hints(window),
        )
        absolute = self._visible_abs(window, extra)
        if absolute is None:
            return None
        states = self._atom_set(window, "_NET_WM_STATE")
        desktops = self._cardinals(window, "_NET_WM_DESKTOP")
        desktop = desktops[0] if desktops else self._current_desktop()
        sticky = desktop == 0xFFFFFFFF or "_NET_WM_STATE_STICKY" in states
        if desktop >= self.desktop_count:
            desktop = self._current_desktop()
        col, row = self._cell_of(absolute)
        rect = Rect(
            absolute.x - col * self.screen_width,
            absolute.y - row * self.screen_height,
            absolute.width,
            absolute.height,
        )
        allowed = self._atom_set(window, "_NET_WM_ALLOWED_ACTIONS")
        hints = extra.hints
        fixed_size = (
            hints.min_width > 0
            and hints.min_width == hints.max_width
            and hints.min_height == hints.max_height
        )
        resizable = not fixed_size and (not allowed or "_NET_WM_ACTION_RESIZE" in allowed)
        wm_class = ""
        try:
            pair = window.get_wm_class()
            if pair:
                wm_class = pair[1]
        except error.XError:
            pass
        title = self._text(window, "_NET_WM_NAME")
        if not title:
            try:
                value = window.get_wm_name()
                title = value if isinstance(value, str) else ""
            except error.XError:
                title = ""
        self._extras[wid] = extra
        return WindowInfo(
            id=wid,
            title=title,
            wm_class=wm_class,
            workspace=self._key(desktop, col, row),
            rect=rect,
            kind=self._kind_of(window),
            minimized="_NET_WM_STATE_HIDDEN" in states,
            fullscreen="_NET_WM_STATE_FULLSCREEN" in states,
            sticky=sticky,
            maximized=any(name in states for name in _MAXIMIZED),
            resizable=resizable,
            stack_index=stack_index,
            open_index=open_index,
        )

    def windows(self) -> List[WindowInfo]:
        opening = self._cardinals(self.root, "_NET_CLIENT_LIST")
        stacking = self._cardinals(self.root, "_NET_CLIENT_LIST_STACKING") or opening
        open_index = {wid: i for i, wid in enumerate(opening)}
        result = []
        for stack_index, wid in enumerate(stacking):
            info = self._read_window(wid, stack_index, open_index.get(wid, stack_index))
            if info is not None:
                result.append(info)
        return result

    # ------------------------------------------------------------------ actions

    def _extra_for(self, window: WindowInfo) -> Optional[_Extra]:
        extra = self._extras.get(window.id)
        if extra is None:
            if self._read_window(window.id, window.stack_index, window.open_index) is None:
                return None
            extra = self._extras.get(window.id)
        return extra

    def _change_state(self, window: WindowInfo, action: int, names) -> None:
        extra = self._extra_for(window)
        if extra is None:
            return
        first = self.atom(names[0])
        second = self.atom(names[1]) if len(names) > 1 else 0
        self._send_client_message(extra.window, "_NET_WM_STATE", [action, first, second, 2, 0])

    def unmaximize(self, window: WindowInfo) -> None:
        self._change_state(window, _STATE_REMOVE, _MAXIMIZED)
        self._awaiting_unmaximize.add(window.id)

    def set_maximized(self, window: WindowInfo, maximized: bool) -> None:
        self._change_state(window, _STATE_ADD if maximized else _STATE_REMOVE, _MAXIMIZED)

    def _constrain(self, hints: _Hints, width: int, height: int) -> Tuple[int, int]:
        width, height = max(width, hints.min_width), max(height, hints.min_height)
        if hints.max_width:
            width = min(width, hints.max_width)
        if hints.max_height:
            height = min(height, hints.max_height)
        if hints.inc_width > 1:
            width = hints.base_width + ((width - hints.base_width) // hints.inc_width) * hints.inc_width
            while width < hints.min_width:
                width += hints.inc_width
        if hints.inc_height > 1:
            height = (
                hints.base_height
                + ((height - hints.base_height) // hints.inc_height) * hints.inc_height
            )
            while height < hints.min_height:
                height += hints.inc_height
        return max(1, width), max(1, height)

    def _send_move(self, extra: _Extra, x: int, y: int, size: Optional[Tuple[int, int]]) -> None:
        flags = _GRAVITY_NORTH_WEST | _FLAG_X | _FLAG_Y | _SOURCE_PAGER
        width = height = 0
        if size is not None:
            flags |= _FLAG_WIDTH | _FLAG_HEIGHT
            width, height = size
        self._send_client_message(extra.window, "_NET_MOVERESIZE_WINDOW", [flags, x, y, width, height])

    def place(
        self, window: WindowInfo, workspace: str, rect: Rect, anchor: str, resize: bool
    ) -> None:
        extra = self._extra_for(window)
        if extra is None:
            return
        _desktop, col, row = self._parse_key(workspace)
        net, gtk = extra.net, extra.gtk
        try:
            current = extra.window.get_geometry()
        except error.XError:
            return
        if resize:
            client_width = rect.width - (net.left + net.right) + (gtk.left + gtk.right)
            client_height = rect.height - (net.top + net.bottom) + (gtk.top + gtk.bottom)
            client_width, client_height = self._constrain(extra.hints, client_width, client_height)
            size: Optional[Tuple[int, int]] = (client_width, client_height)
        else:
            client_width, client_height = int(current.width), int(current.height)
            size = None
        visible_width = client_width + net.left + net.right - gtk.left - gtk.right
        visible_height = client_height + net.top + net.bottom - gtk.top - gtk.bottom
        visible_x = rect.x
        visible_y = rect.bottom - visible_height if anchor == ANCHOR_BOTTOM_LEFT else rect.y
        vx, vy = self._viewport_origin()
        frame_x = col * self.screen_width + visible_x - gtk.left - vx
        frame_y = row * self.screen_height + visible_y - gtk.top - vy
        log.debug(
            "place 0x%x -> %dx%d%+d%+d (frame request %+d%+d)",
            window.id, visible_width, visible_height, visible_x, visible_y, frame_x, frame_y,
        )
        self._send_move(extra, frame_x, frame_y, size)
        self._pending.append(
            _Pending(window.id, col, row, rect, anchor, frame_x, frame_y)
        )

    def raise_window(self, window: WindowInfo) -> None:
        extra = self._extra_for(window)
        if extra is None:
            return
        if "_NET_RESTACK_WINDOW" in self._supported:
            # source indication 2 (pager), no sibling, detail 0 (Above)
            self._send_client_message(extra.window, "_NET_RESTACK_WINDOW", [2, 0, 0, 0, 0])
        else:
            extra.window.configure(stack_mode=X.Above)
            self.display.flush()

    def sync(self) -> None:
        self.display.sync()
        deadline = time.monotonic() + _UNMAXIMIZE_TIMEOUT
        while self._awaiting_unmaximize and time.monotonic() < deadline:
            for wid in list(self._awaiting_unmaximize):
                extra = self._extras.get(wid)
                if extra is None or not any(
                    name in self._atom_set(extra.window, "_NET_WM_STATE") for name in _MAXIMIZED
                ):
                    self._awaiting_unmaximize.discard(wid)
            if self._awaiting_unmaximize:
                time.sleep(0.02)
        self._awaiting_unmaximize.clear()
        time.sleep(_WM_DELAY)

    def commit(self) -> None:
        """Wait for the window manager, then fix windows that ended up in the wrong place."""
        self.sync()
        for attempt in range(_SETTLE_PASSES):
            corrected = False
            for item in self._pending:
                extra = self._extras.get(item.window_id)
                if extra is None:
                    continue
                actual = self._visible_abs(extra.window, extra)
                if actual is None:
                    continue
                vx, vy = self._viewport_origin()
                target_x = item.col * self.screen_width + item.rect.x
                if item.anchor == ANCHOR_BOTTOM_LEFT:
                    target_y = item.row * self.screen_height + item.rect.bottom - actual.height
                else:
                    target_y = item.row * self.screen_height + item.rect.y
                dx, dy = target_x - actual.x, target_y - actual.y
                if dx == 0 and dy == 0:
                    continue
                log.debug("correcting 0x%x by %+d%+d (pass %d)", item.window_id, dx, dy, attempt + 1)
                item.sent_x += dx
                item.sent_y += dy
                self._send_move(extra, item.sent_x, item.sent_y, None)
                corrected = True
            if not corrected:
                break
            self.sync()
        self._pending.clear()
        self.display.sync()

    # ------------------------------------------------------------------ diagnostics

    def _window_manager_name(self) -> str:
        check = self._cardinals(self.root, "_NET_SUPPORTING_WM_CHECK")
        if not check:
            return "unknown"
        window = self.display.create_resource_object("window", check[0])
        return self._text(window, "_NET_WM_NAME") or "unknown"

    def diagnose(self) -> List[str]:
        lines = [
            "backend: x11 (python-xlib)",
            "desktop: %s, session: %s"
            % (os.environ.get("XDG_CURRENT_DESKTOP", "?"), os.environ.get("XDG_SESSION_TYPE", "?")),
            "window manager: %s" % self._window_manager_name(),
            "screen: %dx%d" % (self.screen_width, self.screen_height),
            "desktops: %d, viewports: %dx%d (%s)"
            % (
                self.desktop_count,
                self.columns,
                self.rows,
                "used as workspaces" if self.uses_viewports else "not used",
            ),
            "current workspace: %s" % self.current_workspace(),
            "workspace keys: %s" % ", ".join(self.workspaces()),
            "pointer: %d,%d" % self.pointer_position(),
            "_NET_RESTACK_WINDOW supported: %s" % ("_NET_RESTACK_WINDOW" in self._supported),
            "_NET_WORKAREA: %s" % (self._cardinals(self.root, "_NET_WORKAREA") or "none"),
        ]
        for title, s in self._struts():
            lines.append(
                "strut from %r: left=%d right=%d top=%d bottom=%d" % (title[:30], s.left, s.right, s.top, s.bottom)
            )
        for monitor in self.monitors():
            lines.append(
                "monitor %d %s: %s, work area %s" % (monitor.index, monitor.name, monitor.rect, monitor.workarea)
            )
        for window in self.windows():
            lines.append("window " + window.describe())
        return lines
