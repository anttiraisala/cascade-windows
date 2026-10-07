"""An in-memory backend used by the tests."""

from cascade_windows.backend import Backend
from cascade_windows.model import KIND_NORMAL, Monitor, Rect, WindowInfo


class FakeBackend(Backend):
    name = "fake"

    def __init__(self, monitors, windows, workspaces=("0",), current="0", pointer=(10, 10)):
        self._monitors = monitors
        self._windows = {w.id: w for w in windows}
        self._workspaces = list(workspaces)
        self._current = current
        self._pointer = pointer
        self.calls = []

    def monitors(self):
        return list(self._monitors)

    def pointer_position(self):
        return self._pointer

    def current_workspace(self):
        return self._current

    def workspaces(self):
        return list(self._workspaces)

    def windows(self):
        return list(self._windows.values())

    def unmaximize(self, window):
        self.calls.append(("unmaximize", window.id))
        self._replace(window, maximized=False)

    def set_maximized(self, window, maximized):
        self.calls.append(("set_maximized", window.id, maximized))
        self._replace(window, maximized=maximized)

    def place(self, window, workspace, rect, anchor, resize):
        self.calls.append(("place", window.id, workspace, rect, anchor, resize))
        if not resize:
            current = self._windows[window.id].rect
            rect = Rect(rect.x, rect.y, current.width, current.height)
        self._replace(window, workspace=workspace, rect=rect)

    def raise_window(self, window):
        self.calls.append(("raise", window.id))

    def commit(self):
        self.calls.append(("commit",))

    def sync(self):
        self.calls.append(("sync",))

    def _replace(self, window, **changes):
        current = self._windows[window.id]
        values = dict(current.__dict__)
        values.update(changes)
        self._windows[window.id] = WindowInfo(**values)

    def window(self, window_id):
        return self._windows[window_id]


def make_window(window_id, rect=Rect(100, 100, 400, 300), **kwargs):
    kwargs.setdefault("title", "window %d" % window_id)
    kwargs.setdefault("wm_class", "app")
    kwargs.setdefault("workspace", "0")
    kwargs.setdefault("kind", KIND_NORMAL)
    kwargs.setdefault("stack_index", window_id)
    kwargs.setdefault("open_index", window_id)
    return WindowInfo(id=window_id, rect=rect, **kwargs)


def make_monitor(index, x, y, width, height, name=None, panel=0):
    rect = Rect(x, y, width, height)
    workarea = Rect(x, y + panel, width, height - panel)
    return Monitor(index, name or "MON%d" % index, rect, workarea)
