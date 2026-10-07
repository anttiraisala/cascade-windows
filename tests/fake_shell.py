"""A simulated GNOME Shell for the tests: the state and the operations of the D-Bus protocol.

It behaves like a compositor in the ways that matter to the backend: windows have minimum sizes and
size increments (like terminals), fixed-size windows ignore resizing, maximizing fills the work area.
"""

import json

from cascade_windows.backend import BackendError


def shell_monitor(index, x, y, width, height, name=None, panel=0):
    return {
        "index": index,
        "name": name or "Virtual-%d" % index,
        "rect": [x, y, width, height],
        "workarea": [x, y + panel, width, height - panel],
    }


def shell_window(window_id, rect=(100, 100, 400, 300), **kwargs):
    window = {
        "id": window_id,
        "title": "window %d" % window_id,
        "wm_class": "app",
        "workspace": "0",
        "rect": list(rect),
        "kind": "normal",
        "minimized": False,
        "fullscreen": False,
        "sticky": False,
        "maximized": False,
        "resizable": True,
        "stack_index": window_id,
        "open_index": window_id,
    }
    window.update(kwargs)
    return window


class FakeShell:
    def __init__(self, monitors, windows, workspaces=("0",), current="0", pointer=(10, 10),
                 shell_version="46.0"):
        self.monitors = monitors
        self.windows = {w["id"]: dict(w) for w in windows}
        self.stack = [w["id"] for w in sorted(windows, key=lambda w: w["stack_index"])]
        self.workspaces = list(workspaces)
        self.current = current
        self.pointer = list(pointer)
        self.shell_version = shell_version
        self.restore = {}
        self.unmaximize_lag = 0  # GetState calls before a restore takes effect (like a slow client)
        self._restoring = {}

    def get_state(self):
        for window_id in list(self._restoring):
            self._restoring[window_id] -= 1
            if self._restoring[window_id] <= 0:
                del self._restoring[window_id]
                self._restore(self.windows[window_id], now=True)
        windows = []
        for window in self.windows.values():
            visible = {k: v for k, v in window.items() if not k.startswith("_")}
            visible["stack_index"] = self.stack.index(window["id"])
            windows.append(visible)
        return {
            "protocol": 1,
            "shell_version": self.shell_version,
            "monitors": self.monitors,
            "workspaces": self.workspaces,
            "current_workspace": self.current,
            "pointer": self.pointer,
            "windows": windows,
        }

    def apply(self, operations):
        errors = []
        for operation in operations:
            window = self.windows.get(operation.get("id"))
            if window is None:
                errors.append("no window with id %r" % operation.get("id"))
                continue
            name = operation["op"]
            if name == "unmaximize":
                self._restore(window)
            elif name == "maximize":
                if operation["value"]:
                    self._maximize(window)
                else:
                    self._restore(window)
            elif name == "place":
                if window["maximized"]:
                    errors.append("place of window %d failed: the window is still maximized" % window["id"])
                    continue
                self._place(window, operation["rect"], operation["resize"])
            elif name == "raise":
                self.stack.remove(window["id"])
                self.stack.append(window["id"])
            else:
                errors.append("unknown operation %r" % name)
        return {"ok": not errors, "errors": errors}

    def _maximize(self, window):
        if window["maximized"]:
            return
        self.restore[window["id"]] = list(window["rect"])
        window["maximized"] = True
        monitor = self.monitors[0]
        window["rect"] = list(monitor["workarea"])

    def _restore(self, window, now=False):
        if not window["maximized"]:
            return
        if self.unmaximize_lag and not now:
            self._restoring.setdefault(window["id"], self.unmaximize_lag)
            return
        window["maximized"] = False
        window["rect"] = self.restore.pop(window["id"], window["rect"])

    def _place(self, window, rect, resize):
        x, y, width, height = rect
        if resize and window["resizable"]:
            minimum = window.get("_min", (1, 1))
            increments = window.get("_inc", (1, 1))
            width = max(width, minimum[0])
            height = max(height, minimum[1])
            width -= width % increments[0]
            height -= height % increments[1]
        else:
            width, height = window["rect"][2], window["rect"][3]
        window["rect"] = [x, y, width, height]


class FakeTransport:
    """Calls a FakeShell in the same process, with the same JSON strings as the real bus."""

    def __init__(self, shell):
        self.shell = shell
        self.calls = []
        self.available = True

    def call(self, method, payload=None):
        self.calls.append((method, payload))
        if not self.available:
            raise BackendError("not available")
        if method == "GetState":
            return json.dumps(self.shell.get_state())
        if method == "Apply":
            return json.dumps(self.shell.apply(json.loads(payload)))
        raise BackendError("unknown method " + method)

    def is_available(self):
        return self.available

    def operations(self):
        """The operations of every Apply call, in order."""
        return [json.loads(payload) for method, payload in self.calls if method == "Apply"]
