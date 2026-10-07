"""Backend for GNOME Shell: talks to the cascade-windows extension over D-Bus (see docs/GNOME.md).

The extension only reports the shell state and carries out moves. All decisions are made here, in the same
shared core that the X11 backend uses.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .backend import Backend, BackendError
from .geometry import ANCHOR_BOTTOM_LEFT, ANCHOR_TOP_LEFT, ANCHOR_TOP_RIGHT
from .model import Monitor, Rect, WindowInfo
from . import shell_protocol as protocol

log = logging.getLogger("cascade_windows")

_SETTLE_DELAY = 0.15  # seconds the shell gets to apply moves before the result is checked
_SETTLE_PASSES = 4  # how many times positions are corrected


class BusctlTransport:
    """Calls the extension with ``busctl --user`` (part of systemd, JSON output, no extra libraries)."""

    def __init__(self, env: Optional[Dict[str, str]] = None, timeout: float = 15.0,
                 runner: Callable[..., "subprocess.CompletedProcess"] = subprocess.run):
        self.env = env
        self.timeout = timeout
        self._run = runner

    def call(self, method: str, payload: Optional[str] = None) -> str:
        command = [
            "busctl", "--user", "--json=short", "call",
            protocol.BUS_NAME, protocol.OBJECT_PATH, protocol.INTERFACE, method,
        ]
        if payload is not None:
            command += ["s", payload]
        try:
            done = self._run(command, capture_output=True, text=True, timeout=self.timeout, env=self.env)
        except FileNotFoundError:
            raise BackendError("The 'busctl' command (part of systemd) was not found, so the GNOME Shell "
                               "extension cannot be reached.")
        except subprocess.TimeoutExpired:
            raise BackendError("The GNOME Shell extension did not answer within %d seconds." % self.timeout)
        if done.returncode != 0:
            raise BackendError(explain_failure(done.stderr.strip()))
        try:
            return json.loads(done.stdout)["data"][0]
        except (ValueError, KeyError, IndexError, TypeError):
            raise BackendError("Unexpected answer from busctl: %r" % done.stdout[:200])

    def is_available(self) -> bool:
        """True when something answers on the extension's bus name."""
        try:
            self.call(protocol.METHOD_GET_STATE)
        except BackendError:
            return False
        return True


def extension_missing_message(detail: str = "") -> str:
    return ("The cascade-windows GNOME Shell extension is not running. Install it with ./install.sh and "
            "enable it with 'gnome-extensions enable cascade-windows@anttiraisala.github.io'. On Wayland, "
            "log out and in again after installing it." + (" (%s)" % detail if detail else ""))


def explain_failure(message: str) -> str:
    lowered = message.lower()
    if "not provided by any" in lowered or "name has no owner" in lowered or "not activatable" in lowered \
            or "serviceunknown" in lowered:
        return extension_missing_message(message)
    return "Calling the GNOME Shell extension failed: " + message


@dataclass
class _Pending:
    window_id: int
    rect: Rect  # the slot the window should get
    anchor: str
    resize: bool


class GnomeBackend(Backend):
    name = "gnome"

    def __init__(self, transport=None, settle_delay: float = _SETTLE_DELAY):
        self.transport = transport or BusctlTransport()
        self.settle_delay = settle_delay
        self._state: Optional[protocol.ShellState] = None
        self._queue: List[dict] = []
        self._pending: List[_Pending] = []

    # ------------------------------------------------------------------ state

    def _snapshot(self) -> protocol.ShellState:
        if self._state is None:
            try:
                self._state = protocol.parse_state(self.transport.call(protocol.METHOD_GET_STATE))
            except protocol.ProtocolError as problem:
                raise BackendError(str(problem))
        return self._state

    def _fresh(self) -> protocol.ShellState:
        self._state = None
        return self._snapshot()

    def monitors(self) -> List[Monitor]:
        return list(self._snapshot().monitors)

    def pointer_position(self) -> Tuple[int, int]:
        return self._snapshot().pointer

    def current_workspace(self) -> str:
        return self._snapshot().current_workspace

    def workspaces(self) -> List[str]:
        return list(self._snapshot().workspaces)

    def windows(self) -> List[WindowInfo]:
        return list(self._snapshot().windows)

    # ------------------------------------------------------------------ requests

    def _flush(self) -> None:
        if not self._queue:
            return
        operations, self._queue = self._queue, []
        try:
            answer = self.transport.call(protocol.METHOD_APPLY, protocol.encode_operations(operations))
            errors = protocol.parse_apply_result(answer)
        except protocol.ProtocolError as problem:
            raise BackendError(str(problem))
        for message in errors:
            log.warning("GNOME Shell extension: %s", message)
        self._state = None

    def unmaximize(self, window: WindowInfo) -> None:
        self._queue.append(protocol.op_unmaximize(window.id))

    def set_maximized(self, window: WindowInfo, maximized: bool) -> None:
        self._queue.append(protocol.op_maximize(window.id, maximized))

    def place(self, window: WindowInfo, workspace: str, rect: Rect, anchor: str, resize: bool) -> None:
        if resize:
            width, height = rect.width, rect.height
        else:
            width, height = window.rect.width, window.rect.height
        x, y = _position(rect, anchor, width, height)
        log.debug("place 0x%x -> %dx%d%+d%+d", window.id, width, height, x, y)
        self._queue.append(protocol.op_place(window.id, Rect(x, y, width, height), resize))
        self._pending.append(_Pending(window.id, rect, anchor, resize))

    def raise_window(self, window: WindowInfo) -> None:
        self._queue.append(protocol.op_raise(window.id))

    def sync(self) -> None:
        self._flush()
        time.sleep(self.settle_delay)

    def commit(self) -> None:
        """Flush the requests, then fix windows that did not end up where the cascade wants them."""
        self.sync()
        for attempt in range(_SETTLE_PASSES):
            actual = {w.id: w for w in self._fresh().windows}
            for item in self._pending:
                window = actual.get(item.window_id)
                if window is None:
                    continue
                if item.resize and item.anchor == ANCHOR_BOTTOM_LEFT and window.rect.height != item.rect.height:
                    # The window could not get the requested height (for example a terminal that snaps
                    # to whole character rows). Keep its top edge where the cascade wants it, so the
                    # staircase of title bars stays regular, and let the bottom edge fall short.
                    item.anchor = ANCHOR_TOP_LEFT
                x, y = _position(item.rect, item.anchor, window.rect.width, window.rect.height)
                if (x, y) == (window.rect.x, window.rect.y):
                    continue
                log.debug("correcting 0x%x to %+d%+d (pass %d)", item.window_id, x, y, attempt + 1)
                self._queue.append(
                    protocol.op_place(item.window_id, Rect(x, y, window.rect.width, window.rect.height), False)
                )
            if not self._queue:
                break
            self.sync()
        self._pending.clear()
        self._state = None

    # ------------------------------------------------------------------ diagnostics

    def diagnose(self) -> List[str]:
        state = self._fresh()
        lines = [
            "backend: gnome (GNOME Shell extension over D-Bus)",
            "shell version: %s, protocol: %d" % (state.shell_version or "?", protocol.PROTOCOL_VERSION),
            "current workspace: %s" % state.current_workspace,
            "workspace keys: %s" % ", ".join(state.workspaces),
            "pointer: %d,%d" % state.pointer,
        ]
        for monitor in state.monitors:
            lines.append(
                "monitor %d %s: %s, work area %s" % (monitor.index, monitor.name, monitor.rect, monitor.workarea)
            )
        for window in state.windows:
            lines.append("window " + window.describe())
        return lines


def _position(rect: Rect, anchor: str, width: int, height: int) -> Tuple[int, int]:
    """Top-left corner of a window of the given size placed in ``rect`` at the given anchor."""
    x = rect.right - width if anchor == ANCHOR_TOP_RIGHT else rect.x
    y = rect.bottom - height if anchor == ANCHOR_BOTTOM_LEFT else rect.y
    return x, y
