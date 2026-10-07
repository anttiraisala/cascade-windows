"""A tiny fake EWMH window manager used to test the X11 backend against Xvfb.

It does not draw anything and does not reparent windows. It pretends every window has decorations
of ``extents`` (left, right, top, bottom) by publishing _NET_FRAME_EXTENTS and by treating the
position in _NET_MOVERESIZE_WINDOW as the position of the frame (north-west gravity).
"""

import threading

from Xlib import X, Xatom, display, error


def _signed(value):
    return value - (1 << 32) if value >= (1 << 31) else value


class FakeWindowManager(threading.Thread):
    def __init__(self, display_name, extents=(2, 2, 20, 2), viewports=(1, 1), viewport_origin=(0, 0)):
        super().__init__(daemon=True)
        self.display_name = display_name
        self.extents = extents
        self.viewports = viewports
        self.viewport_origin = viewport_origin
        self.ready = threading.Event()
        self.failed = None
        self.clients = []
        self.saved_geometry = {}

    def run(self):
        try:
            self.d = display.Display(self.display_name)
            self.root = self.d.screen().root
            self.root.change_attributes(
                event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
                onerror=None,
            )
            self.d.sync()
            geometry = self.root.get_geometry()
            self._setup(geometry.width, geometry.height)
            self.ready.set()
            while True:
                self._dispatch(self.d.next_event())
        except Exception as problem:  # noqa: BLE001 - the thread ends when the server goes away
            self.failed = problem
            self.ready.set()

    def atom(self, name):
        return self.d.intern_atom(name)

    def _setup(self, width, height):
        names = [
            "_NET_SUPPORTED", "_NET_CLIENT_LIST", "_NET_CLIENT_LIST_STACKING",
            "_NET_MOVERESIZE_WINDOW", "_NET_RESTACK_WINDOW", "_NET_WM_STATE",
            "_NET_FRAME_EXTENTS", "_NET_WORKAREA", "_NET_DESKTOP_VIEWPORT",
        ]
        self._set(self.root, "_NET_SUPPORTED", Xatom.ATOM, [self.atom(n) for n in names])
        self._set(self.root, "_NET_NUMBER_OF_DESKTOPS", Xatom.CARDINAL, [1])
        self._set(self.root, "_NET_CURRENT_DESKTOP", Xatom.CARDINAL, [0])
        self._set(
            self.root, "_NET_DESKTOP_GEOMETRY", Xatom.CARDINAL,
            [width * self.viewports[0], height * self.viewports[1]],
        )
        self._set(self.root, "_NET_DESKTOP_VIEWPORT", Xatom.CARDINAL, list(self.viewport_origin))
        self._set(self.root, "_NET_WORKAREA", Xatom.CARDINAL, [0, 0, width, height])
        self._publish_lists()

    def _set(self, window, name, type_, values):
        window.change_property(self.atom(name), type_, 32, values)
        self.d.flush()

    def _publish_lists(self):
        self._set(self.root, "_NET_CLIENT_LIST", Xatom.WINDOW, [w.id for w in self.clients])
        self._set(self.root, "_NET_CLIENT_LIST_STACKING", Xatom.WINDOW, [w.id for w in self.clients])

    def _dispatch(self, ev):
        if ev.type == X.MapRequest:
            window = ev.window
            window.map()
            self._set(window, "_NET_FRAME_EXTENTS", Xatom.CARDINAL, list(self.extents))
            self._set(window, "_NET_WM_DESKTOP", Xatom.CARDINAL, [0])
            if all(w.id != window.id for w in self.clients):
                self.clients.append(window)
            self._publish_lists()
        elif ev.type == X.ConfigureRequest:
            args = {}
            for bit, key in ((X.CWX, "x"), (X.CWY, "y"), (X.CWWidth, "width"), (X.CWHeight, "height")):
                if ev.value_mask & bit:
                    args[key] = getattr(ev, key)
            if ev.value_mask & X.CWStackMode:
                args["stack_mode"] = ev.stack_mode
            ev.window.configure(**args)
            self.d.flush()
        elif ev.type == X.ClientMessage:
            self._client_message(ev)
        elif ev.type == X.DestroyNotify or ev.type == X.UnmapNotify:
            pass

    def _client_message(self, ev):
        kind = self.d.get_atom_name(ev.client_type)
        data = ev.data[1]
        window = ev.window
        if kind == "_NET_MOVERESIZE_WINDOW":
            flags = data[0]
            args = {}
            if flags & (1 << 8):
                args["x"] = _signed(data[1]) + self.extents[0]
            if flags & (1 << 9):
                args["y"] = _signed(data[2]) + self.extents[2]
            if flags & (1 << 10):
                args["width"] = max(1, data[3])
            if flags & (1 << 11):
                args["height"] = max(1, data[4])
            window.configure(**args)
        elif kind == "_NET_RESTACK_WINDOW":
            window.configure(stack_mode=X.Above)
            self.clients = [w for w in self.clients if w.id != window.id] + [window]
            self._publish_lists()
        elif kind == "_NET_WM_STATE":
            self._change_state(window, data)
        self.d.flush()

    def _change_state(self, window, data):
        action = data[0]
        maximized = [self.atom("_NET_WM_STATE_MAXIMIZED_HORZ"), self.atom("_NET_WM_STATE_MAXIMIZED_VERT")]
        if not any(a in data[1:3] for a in maximized):
            return
        if action == 1:
            geometry = window.get_geometry()
            self.saved_geometry[window.id] = (geometry.x, geometry.y, geometry.width, geometry.height)
            screen = self.root.get_geometry()
            window.configure(x=self.extents[0], y=self.extents[2],
                             width=screen.width - self.extents[0] - self.extents[1],
                             height=screen.height - self.extents[2] - self.extents[3])
            self._set(window, "_NET_WM_STATE", Xatom.ATOM, maximized)
        else:
            x, y, width, height = self.saved_geometry.pop(window.id, (50, 50, 400, 300))
            window.configure(x=x, y=y, width=width, height=height)
            self._set(window, "_NET_WM_STATE", Xatom.ATOM, [])
