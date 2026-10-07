"""Runs the X11 backend against a private Xvfb server with a fake window manager.

Skipped automatically when Xvfb or python-xlib is not available.
"""

import os
import shutil
import subprocess
import time
import unittest

try:
    from Xlib import X, Xatom, display

    from cascade_windows.x11_backend import X11Backend
    from tests.fake_wm import FakeWindowManager

    HAVE_XLIB = True
except ImportError:
    HAVE_XLIB = False

from cascade_windows.cascade import SCOPE_ALL, SCOPE_WORKSPACE, apply_plan, plan_for_backend
from cascade_windows.model import Rect
from cascade_windows.settings import Settings

SCREEN = (1920, 1080)


def _lock_is_stale(number):
    """True when the lock file of display ``number`` belongs to a process that no longer exists."""
    try:
        with open("/tmp/.X%d-lock" % number) as handle:
            pid = int(handle.read().strip())
        os.kill(pid, 0)
    except (OSError, ValueError):
        return True
    return False


def _remove_display_files(number):
    for path in ("/tmp/.X%d-lock" % number, "/tmp/.X11-unix/X%d" % number):
        try:
            os.unlink(path)
        except OSError:
            pass


def start_xvfb():
    for number in range(90, 400):
        if os.path.exists("/tmp/.X%d-lock" % number):
            if not _lock_is_stale(number):
                continue
            _remove_display_files(number)
        process = subprocess.Popen(
            ["Xvfb", ":%d" % number, "-screen", "0", "%dx%dx24" % SCREEN, "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            if os.path.exists("/tmp/.X11-unix/X%d" % number):
                return process, ":%d" % number
            if process.poll() is not None:
                break
            time.sleep(0.05)
        process.terminate()
        process.wait()
        _remove_display_files(number)
    raise RuntimeError("Could not start Xvfb")


@unittest.skipUnless(HAVE_XLIB and shutil.which("Xvfb"), "needs python-xlib and Xvfb")
class XvfbTestCase(unittest.TestCase):
    wm_options = {}

    def setUp(self):
        self.xvfb, self.display_name = start_xvfb()
        self.addCleanup(self._stop_xvfb)
        self.wm = FakeWindowManager(self.display_name, **self.wm_options)
        self.wm.start()
        self.assertTrue(self.wm.ready.wait(5))
        self.assertIsNone(self.wm.failed)
        self.client = display.Display(self.display_name)
        self.root = self.client.screen().root
        self.backend = X11Backend(self.display_name)
        self.addCleanup(self.client.close)
        self.addCleanup(self.backend.display.close)

    def _stop_xvfb(self):
        self.xvfb.terminate()
        self.xvfb.wait()
        _remove_display_files(int(self.display_name[1:]))

    def create_client(self, x, y, width, height, title, fixed_size=False, dialog=False,
                      minimized=False, increments=None, dock=False):
        window = self.root.create_window(
            x, y, width, height, 0, self.client.screen().root_depth, X.InputOutput, X.CopyFromParent
        )
        window.set_wm_name(title)
        window.set_wm_class("test", "TestApp")
        if fixed_size:
            window.set_wm_normal_hints(
                flags=(1 << 4) | (1 << 5), min_width=width, min_height=height,
                max_width=width, max_height=height,
            )
        if increments:
            window.set_wm_normal_hints(
                flags=(1 << 6) | (1 << 8), width_inc=increments[0], height_inc=increments[1],
                base_width=0, base_height=0,
            )
        if dialog or dock:
            kind = "_NET_WM_WINDOW_TYPE_DOCK" if dock else "_NET_WM_WINDOW_TYPE_DIALOG"
            window.change_property(
                self.client.intern_atom("_NET_WM_WINDOW_TYPE"), Xatom.ATOM, 32,
                [self.client.intern_atom(kind)],
            )
        window.map()
        self.client.sync()
        self.wait_until(lambda: window.id in self.client_list())
        if minimized:
            window.change_property(
                self.client.intern_atom("_NET_WM_STATE"), Xatom.ATOM, 32,
                [self.client.intern_atom("_NET_WM_STATE_HIDDEN")],
            )
            self.client.sync()
        return window

    def client_list(self):
        prop = self.root.get_full_property(self.client.intern_atom("_NET_CLIENT_LIST"), X.AnyPropertyType)
        return list(prop.value) if prop else []

    def wait_until(self, condition, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.02)
        self.fail("timed out waiting for the window manager")

    def visible(self, window):
        """Visible (decorated) rectangle of a window, in root coordinates."""
        if window.id not in self.backend._extras:
            self.backend.windows()
        extra = self.backend._extras[window.id]
        rect = self.backend._visible_abs(window, extra)
        self.assertIsNotNone(rect)
        return rect

    def cascade(self, scope=SCOPE_WORKSPACE, settings=None):
        settings = settings or Settings()
        self.backend.windows()  # refresh per-window details
        plan = plan_for_backend(self.backend, settings, scope)
        apply_plan(self.backend, plan, settings)
        return plan



class X11BackendTest(XvfbTestCase):
    def test_reads_windows_with_decorations_and_flags(self):
        window = self.create_client(100, 100, 400, 300, "one")
        info = {w.id: w for w in self.backend.windows()}[window.id]
        self.assertEqual(info.title, "one")
        self.assertEqual(info.wm_class, "TestApp")
        self.assertEqual(info.rect, Rect(98, 80, 404, 322))  # client + decoration extents
        self.assertTrue(info.resizable)
        self.assertEqual(info.kind, "normal")

    def test_cascades_three_windows_exactly(self):
        windows = [self.create_client(100 + 40 * i, 100, 400, 300, "w%d" % i) for i in range(3)]
        self.cascade()
        expected = [Rect(80, 40, 1540, 1020), Rect(80, 80, 1660, 980), Rect(80, 120, 1780, 940)]
        for window, rect in zip(windows, expected):
            self.assertEqual(self.visible(window), rect)

    def test_stacking_order_follows_the_cascade(self):
        windows = [self.create_client(100, 100, 400, 300, "w%d" % i) for i in range(3)]
        self.cascade()
        order = self.client_list()
        self.assertEqual([w.id for w in windows if w.id in order], [i for i in order if i in {w.id for w in windows}])

    def test_dialogs_minimized_and_fixed_size_windows(self):
        normal = self.create_client(100, 100, 400, 300, "normal")
        dialog = self.create_client(300, 300, 200, 100, "dialog", dialog=True)
        hidden = self.create_client(500, 200, 300, 200, "hidden", minimized=True)
        fixed = self.create_client(700, 400, 320, 240, "fixed", fixed_size=True)
        before_dialog = self.visible(dialog)
        before_hidden = self.visible(hidden)
        self.cascade()
        moved_dialog = self.visible(dialog)
        self.assertEqual((moved_dialog.width, moved_dialog.height), (before_dialog.width, before_dialog.height))
        self.assertNotEqual(moved_dialog, before_dialog)  # dialogs are cascaded too, at their own size
        self.assertGreaterEqual(moved_dialog.y, 40)
        self.assertLessEqual(moved_dialog.right, 1860)
        self.assertEqual(self.visible(hidden), before_hidden)
        self.assertEqual(self.visible(fixed).width, 324)  # size untouched (client + decorations)
        self.assertEqual(self.visible(fixed).height, 262)
        self.assertGreaterEqual(self.visible(normal).width, 1000)

    def test_maximized_window_is_restored_and_cascaded(self):
        window = self.create_client(100, 100, 400, 300, "max")
        self.backend.windows()
        info = {w.id: w for w in self.backend.windows()}[window.id]
        self.backend.set_maximized(info, True)
        self.backend.sync()
        self.wait_until(lambda: self.visible(window).width >= 1900)
        self.cascade()
        self.assertEqual(self.visible(window), Rect(80, 40, 1780, 1020))

    def test_undo_restores_the_original_position(self):
        from cascade_windows.cascade import restore_positions
        from cascade_windows.undo import entries_from_plan

        window = self.create_client(100, 100, 400, 300, "undo")
        self.backend.windows()
        original = self.visible(window)
        self.backend.windows()
        plan = plan_for_backend(self.backend, Settings(), SCOPE_WORKSPACE)
        entries = entries_from_plan(plan)
        apply_plan(self.backend, plan, Settings())
        self.assertNotEqual(self.visible(window), original)
        restore_positions(self.backend, entries)
        self.assertEqual(self.visible(window), original)

    def test_windows_that_snap_to_a_grid_keep_a_regular_staircase(self):
        """Terminals resize in whole character cells. Their top edges must still line up."""
        windows = [
            self.create_client(100, 100, 400, 300, "plain 0"),
            self.create_client(100, 100, 400, 300, "terminal", increments=(9, 17)),
            self.create_client(100, 100, 400, 300, "plain 2"),
            self.create_client(100, 100, 400, 300, "terminal 2", increments=(9, 17)),
        ]
        self.cascade()
        tops = [self.visible(window).y for window in windows]
        self.assertEqual(tops, [40, 80, 120, 160])
        for window in (windows[1], windows[3]):
            rect = self.visible(window)
            self.assertLessEqual(rect.bottom, 1060)
            self.assertGreater(rect.bottom, 1060 - 17 - 5)  # at most one row short

    def test_fit_mode_places_every_window_inside_the_margins(self):
        windows = [self.create_client(100, 100, 400, 300, "w%d" % i) for i in range(5)]
        self.cascade(settings=Settings(size_mode="fit"))
        for window in windows:
            rect = self.visible(window)
            self.assertGreaterEqual(rect.x, 80)
            self.assertGreaterEqual(rect.y, 40)
            self.assertLessEqual(rect.right, 1860)
            self.assertLessEqual(rect.bottom, 1060)


class ViewportBackendTest(XvfbTestCase):
    """Compiz style workspaces: a 2x1 grid of viewports, currently looking at the right one."""

    wm_options = {"viewports": (2, 1), "viewport_origin": (1920, 0)}

    def test_workspace_keys_and_current_workspace(self):
        self.assertEqual(self.backend.workspaces(), ["0:0,0", "0:1,0"])
        self.assertEqual(self.backend.current_workspace(), "0:1,0")

    def test_windows_on_the_other_viewport_are_cascaded_there(self):
        here = self.create_client(100, 100, 400, 300, "here")
        there = self.create_client(-1800, 100, 400, 300, "there")  # one viewport to the left
        infos = {w.id: w for w in self.backend.windows()}
        self.assertEqual(infos[here.id].workspace, "0:1,0")
        self.assertEqual(infos[there.id].workspace, "0:0,0")
        self.cascade(scope=SCOPE_ALL)
        self.assertEqual(self.visible(here), Rect(1920 + 80, 40, 1780, 1020))
        self.assertEqual(self.visible(there), Rect(80, 40, 1780, 1020))

    def test_workspace_scope_leaves_other_viewports_alone(self):
        self.create_client(100, 100, 400, 300, "here")
        there = self.create_client(-1800, 100, 400, 300, "there")
        before = self.visible(there)
        self.cascade(scope=SCOPE_WORKSPACE)
        self.assertEqual(self.visible(there), before)


@unittest.skipUnless(HAVE_XLIB, "needs python-xlib")
class DockObstructionTest(unittest.TestCase):
    monitor = Rect(0, 0, 1920, 1080)

    def obstruction(self, dock):
        return X11Backend._dock_obstruction(self.monitor, dock)

    def test_top_bar(self):
        self.assertEqual(self.obstruction(Rect(0, 0, 1920, 24)), (0, 0, 24, 0))

    def test_bottom_bar(self):
        self.assertEqual(self.obstruction(Rect(0, 1040, 1920, 40)), (0, 0, 0, 40))

    def test_left_and_right_bars(self):
        self.assertEqual(self.obstruction(Rect(0, 0, 64, 1080)), (64, 0, 0, 0))
        self.assertEqual(self.obstruction(Rect(1856, 0, 64, 1080)), (0, 64, 0, 0))

    def test_bar_on_another_monitor_is_ignored(self):
        self.assertEqual(self.obstruction(Rect(1920, 0, 64, 1080)), (0, 0, 0, 0))

    def test_only_the_part_on_this_monitor_counts(self):
        self.assertEqual(self.obstruction(Rect(-30, 0, 94, 1080)), (64, 0, 0, 0))

    def test_floating_small_or_huge_windows_are_ignored(self):
        self.assertEqual(self.obstruction(Rect(800, 500, 200, 40)), (0, 0, 0, 0))   # in the middle
        self.assertEqual(self.obstruction(Rect(0, 0, 300, 24)), (0, 0, 0, 0))       # too short a bar
        self.assertEqual(self.obstruction(Rect(0, 0, 1920, 1080)), (0, 0, 0, 0))    # covers everything


class DockWindowTest(XvfbTestCase):
    """Two monitors side by side; bars that do not set struts, like the Unity 7 panel and launcher."""

    def setUp(self):
        super().setUp()
        self.backend._monitor_rects = lambda: [
            ("A", Rect(0, 0, 960, 1080)),
            ("B", Rect(960, 0, 960, 1080)),
        ]

    def add_bars(self):
        self.create_client(0, 0, 1920, 24, "panel", dock=True)
        self.create_client(0, 0, 64, 1080, "launcher", dock=True)

    def test_work_areas_exclude_the_bars_on_the_right_monitors_only(self):
        self.add_bars()
        areas = {m.name: m.workarea for m in self.backend.monitors()}
        self.assertEqual(areas["A"], Rect(64, 24, 896, 1056))
        self.assertEqual(areas["B"], Rect(960, 24, 960, 1056))

    def test_cascaded_windows_stay_clear_of_the_bars_on_both_monitors(self):
        self.add_bars()
        left = self.create_client(200, 200, 400, 300, "left")
        right = self.create_client(1200, 200, 400, 300, "right")
        self.cascade()
        self.assertEqual(self.visible(left), Rect(144, 64, 756, 996))     # launcher 64 + left 80, panel 24 + top 40
        self.assertEqual(self.visible(right), Rect(1040, 64, 820, 996))   # right monitor: no launcher

    def test_bars_are_ignored_when_the_setting_is_off(self):
        self.backend.use_dock_windows = False
        self.add_bars()
        areas = {m.name: m.workarea for m in self.backend.monitors()}
        self.assertEqual(areas["A"], Rect(0, 0, 960, 1080))

    def test_diagnose_lists_the_bars(self):
        self.add_bars()
        text = "\n".join(self.backend.diagnose())
        self.assertIn("dock window 'panel'", text)
        self.assertIn("dock window 'launcher'", text)


if __name__ == "__main__":
    unittest.main()
