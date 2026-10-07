import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from cascade_windows import shell_protocol as protocol
from cascade_windows.backend import BackendError
from cascade_windows.cascade import SCOPE_ALL, SCOPE_WORKSPACE, apply_plan, plan_for_backend, restore_positions
from cascade_windows.cli import create_backend, desktop_is_gnome
from cascade_windows.gnome_backend import BusctlTransport, GnomeBackend, explain_failure
from cascade_windows.model import Rect
from cascade_windows.settings import Settings
from cascade_windows.undo import entries_from_plan

from tests.fake_shell import FakeShell, FakeTransport, shell_monitor, shell_window

MONITOR = shell_monitor(0, 0, 0, 1920, 1080)


def make_backend(windows, monitors=(MONITOR,), **kwargs):
    shell = FakeShell(list(monitors), windows, **kwargs)
    transport = FakeTransport(shell)
    return GnomeBackend(transport, settle_delay=0), shell, transport


def cascade(backend, settings=None, scope=SCOPE_WORKSPACE):
    settings = settings or Settings()
    plan = plan_for_backend(backend, settings, scope)
    apply_plan(backend, plan, settings)
    return plan


def rect_of(shell, window_id):
    return Rect.from_list(shell.windows[window_id]["rect"])


class ProtocolTest(unittest.TestCase):
    def state(self, **changes):
        data = FakeShell([MONITOR], [shell_window(1)]).get_state()
        data.update(changes)
        return json.dumps(data)

    def test_state_is_turned_into_the_shared_model(self):
        state = protocol.parse_state(self.state())
        self.assertEqual(state.monitors[0].workarea, Rect(0, 0, 1920, 1080))
        self.assertEqual(state.workspaces, ["0"])
        self.assertEqual(state.current_workspace, "0")
        self.assertEqual(state.pointer, (10, 10))
        window = state.windows[0]
        self.assertEqual((window.id, window.rect, window.kind, window.resizable), (1, Rect(100, 100, 400, 300), "normal", True))

    def test_protocol_mismatch_is_refused_with_advice(self):
        with self.assertRaises(protocol.ProtocolError) as caught:
            protocol.parse_state(self.state(protocol=99))
        self.assertIn("install.sh", str(caught.exception))

    def test_broken_state_is_reported(self):
        for text in ("not json", "[]", json.dumps({"protocol": 1}), json.dumps({"protocol": 1, "monitors": [{}]})):
            with self.assertRaises(protocol.ProtocolError):
                protocol.parse_state(text)

    def test_unknown_window_kinds_become_other(self):
        data = json.loads(self.state())
        data["windows"][0]["kind"] = "tooltip"
        self.assertEqual(protocol.parse_state(json.dumps(data)).windows[0].kind, "other")

    def test_apply_result_errors(self):
        self.assertEqual(protocol.parse_apply_result('{"ok": true, "errors": []}'), [])
        self.assertEqual(protocol.parse_apply_result('{"ok": false, "errors": ["gone"]}'), ["gone"])
        with self.assertRaises(protocol.ProtocolError):
            protocol.parse_apply_result("nonsense")


class BackendReadingTest(unittest.TestCase):
    def test_reads_monitors_windows_workspaces_and_pointer(self):
        backend, _shell, _t = make_backend(
            [shell_window(1), shell_window(2, workspace="1")],
            monitors=[MONITOR, shell_monitor(1, 1920, 0, 1920, 1080)],
            workspaces=("0", "1"), pointer=(2000, 5))
        self.assertEqual([m.index for m in backend.monitors()], [0, 1])
        self.assertEqual(backend.workspaces(), ["0", "1"])
        self.assertEqual(backend.current_workspace(), "0")
        self.assertEqual(backend.pointer_position(), (2000, 5))
        self.assertEqual([w.id for w in backend.windows()], [1, 2])

    def test_the_state_is_asked_for_once_per_snapshot(self):
        backend, _shell, transport = make_backend([shell_window(1)])
        backend.monitors(), backend.windows(), backend.workspaces(), backend.pointer_position()
        self.assertEqual([c[0] for c in transport.calls], ["GetState"])

    def test_diagnose_lists_the_shell_state(self):
        backend, _shell, _t = make_backend([shell_window(1)])
        text = "\n".join(backend.diagnose())
        self.assertIn("backend: gnome", text)
        self.assertIn("shell version: 46.0", text)
        self.assertIn("monitor 0 Virtual-0", text)
        self.assertIn("window 0x1", text)


class CascadeOnFakeShellTest(unittest.TestCase):
    def test_three_windows_get_the_same_rectangles_as_on_x11(self):
        backend, shell, _t = make_backend([shell_window(i, (100 + 40 * i, 100, 400, 300)) for i in (1, 2, 3)])
        cascade(backend)
        self.assertEqual(rect_of(shell, 1), Rect(80, 40, 1540, 1020))
        self.assertEqual(rect_of(shell, 2), Rect(80, 80, 1660, 980))
        self.assertEqual(rect_of(shell, 3), Rect(80, 120, 1780, 940))

    def test_stacking_order_follows_the_cascade(self):
        backend, shell, _t = make_backend([shell_window(1, stack_index=2), shell_window(2, stack_index=0),
                                           shell_window(3, stack_index=1)])
        cascade(backend)
        self.assertEqual(shell.stack, [2, 3, 1])

    def test_maximized_window_is_restored_before_it_is_placed(self):
        backend, shell, transport = make_backend([shell_window(1, (0, 0, 1920, 1080), maximized=True)])
        shell.restore[1] = [100, 100, 400, 300]
        cascade(backend)
        self.assertFalse(shell.windows[1]["maximized"])
        self.assertEqual(rect_of(shell, 1), Rect(80, 40, 1780, 1020))
        operations = [op["op"] for batch in transport.operations() for op in batch]
        self.assertLess(operations.index("unmaximize"), operations.index("place"))
        self.assertEqual(transport.operations()[0], [{"op": "unmaximize", "id": 1}])

    def test_fixed_size_windows_and_dialogs_keep_their_size_and_get_the_top_right_corner(self):
        backend, shell, _t = make_backend([
            shell_window(1),
            shell_window(2, (300, 300, 320, 240), resizable=False),
            shell_window(3, (500, 300, 350, 200), kind="dialog"),
        ])
        cascade(backend)
        for window_id, size in ((2, (320, 240)), (3, (350, 200))):
            rect = rect_of(shell, window_id)
            self.assertEqual((rect.width, rect.height), size)
        # window 2 is the middle one of three: its slot ends one step before the right margin
        self.assertEqual((rect_of(shell, 2).right, rect_of(shell, 2).y), (1860 - 120, 80))
        self.assertEqual((rect_of(shell, 3).right, rect_of(shell, 3).y), (1860, 120))

    def test_windows_that_snap_to_a_grid_keep_a_regular_staircase(self):
        backend, shell, _t = make_backend([
            shell_window(1),
            shell_window(2, _inc=[9, 17]),
            shell_window(3),
            shell_window(4, _inc=[9, 17]),
        ])
        cascade(backend)
        self.assertEqual([rect_of(shell, i).y for i in (1, 2, 3, 4)], [40, 80, 120, 160])
        for window_id in (2, 4):
            rect = rect_of(shell, window_id)
            self.assertLessEqual(rect.bottom, 1060)
            self.assertGreater(rect.bottom, 1060 - 17 - 5)

    def test_minimum_sizes_are_corrected_by_position_not_size(self):
        backend, shell, _t = make_backend([shell_window(1, _min=[2500, 300]), shell_window(2)])
        cascade(backend)
        rect = rect_of(shell, 1)
        self.assertEqual((rect.width, rect.y), (2500, 40))

    def test_each_monitor_is_cascaded_on_its_own(self):
        backend, shell, _t = make_backend(
            [shell_window(1, (100, 100, 400, 300)), shell_window(2, (2000, 100, 400, 300))],
            monitors=[MONITOR, shell_monitor(1, 1920, 0, 1920, 1080)])
        cascade(backend)
        self.assertEqual(rect_of(shell, 1), Rect(80, 40, 1780, 1020))
        self.assertEqual(rect_of(shell, 2), Rect(2000, 40, 1780, 1020))

    def test_all_scope_reaches_other_workspaces(self):
        backend, shell, _t = make_backend(
            [shell_window(1), shell_window(2, workspace="1")], workspaces=("0", "1"))
        cascade(backend, scope=SCOPE_ALL)
        self.assertEqual(rect_of(shell, 2), Rect(80, 40, 1780, 1020))

    def test_undo_restores_positions_sizes_and_maximized_state(self):
        backend, shell, _t = make_backend([
            shell_window(1, (100, 100, 400, 300)),
            shell_window(2, (0, 0, 1920, 1080), maximized=True),
        ])
        shell.restore[2] = [300, 200, 500, 400]
        before = {i: list(shell.windows[i]["rect"]) for i in (1,)}
        settings = Settings()
        plan = plan_for_backend(backend, settings, SCOPE_WORKSPACE)
        entries = entries_from_plan(plan)
        apply_plan(backend, plan, settings)
        self.assertNotEqual(rect_of(shell, 1), Rect.from_list(before[1]))
        restored = restore_positions(backend, entries)
        self.assertEqual(restored, 2)
        self.assertEqual(list(rect_of(shell, 1).to_list()), before[1])
        self.assertTrue(shell.windows[2]["maximized"])

    def test_requests_are_sent_in_a_few_batches(self):
        backend, _shell, transport = make_backend([shell_window(i) for i in range(1, 9)])
        cascade(backend)
        self.assertLessEqual(len(transport.operations()), 3)

    def test_errors_reported_by_the_extension_are_logged_and_do_not_stop_the_work(self):
        backend, shell, _t = make_backend([shell_window(1)])
        backend.windows()
        shell.windows.pop(1)
        shell.windows[2] = shell_window(2)
        shell.stack = [2]
        backend.raise_window(plan_for_backend(backend, Settings(), SCOPE_WORKSPACE).moves[0].window)
        with self.assertLogs("cascade_windows", level=logging.WARNING) as logs:
            backend.sync()
        self.assertIn("no window", logs.output[0])

    def test_unreachable_extension_raises_a_backend_error(self):
        backend, _shell, transport = make_backend([shell_window(1)])
        transport.available = False
        with self.assertRaises(BackendError):
            backend.windows()


class BackendSelectionTest(unittest.TestCase):
    def test_desktop_names(self):
        for value, expected in (("ubuntu:GNOME", True), ("GNOME", True), ("GNOME-Flashback:GNOME", True),
                                ("X-Cinnamon", False), ("Unity:Unity7:ubuntu", False), ("", False),
                                ("KDE", False)):
            self.assertEqual(desktop_is_gnome({"XDG_CURRENT_DESKTOP": value}), expected, value)

    def available(self, yes=True):
        backend, _shell, transport = make_backend([shell_window(1)])
        transport.available = yes
        return backend

    def test_gnome_desktop_with_the_extension_uses_the_gnome_backend(self):
        backend = self.available()
        chosen = create_backend(environ={"XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "XDG_SESSION_TYPE": "wayland"},
                                gnome_backend=backend)
        self.assertIs(chosen, backend)

    def test_forced_gnome_backend_is_used_on_any_desktop(self):
        backend = self.available(False)
        self.assertIs(create_backend(kind="gnome", environ={"XDG_CURRENT_DESKTOP": "X-Cinnamon"},
                                     gnome_backend=backend), backend)

    def test_gnome_wayland_without_the_extension_explains_what_to_do(self):
        with self.assertRaises(BackendError) as caught:
            create_backend(environ={"XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "XDG_SESSION_TYPE": "wayland"},
                           gnome_backend=self.available(False))
        self.assertIn("gnome-extensions enable", str(caught.exception))

    def x11_module(self):
        module = mock.MagicMock()
        return module, mock.patch.dict(sys.modules, {"cascade_windows.x11_backend": module})

    def test_gnome_x11_session_without_the_extension_falls_back_to_x11(self):
        module, patcher = self.x11_module()
        with patcher:
            chosen = create_backend(environ={"XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "XDG_SESSION_TYPE": "x11"},
                                    gnome_backend=self.available(False))
        self.assertIs(chosen, module.X11Backend.return_value)

    def test_other_desktops_keep_using_the_x11_backend_even_if_gnome_backend_is_available(self):
        module, patcher = self.x11_module()
        with patcher:
            for desktop in ("X-Cinnamon", "Unity:Unity7:ubuntu"):
                chosen = create_backend(environ={"XDG_CURRENT_DESKTOP": desktop, "XDG_SESSION_TYPE": "x11"},
                                        gnome_backend=self.available())
                self.assertIs(chosen, module.X11Backend.return_value)

    def test_wayland_on_another_desktop_is_still_refused(self):
        with self.assertRaises(BackendError) as caught:
            create_backend(environ={"XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": "wayland"})
        self.assertIn("Wayland", str(caught.exception))

    def test_unknown_backend_kind_is_rejected(self):
        with self.assertRaises(BackendError):
            create_backend(kind="nonsense", environ={})


class BusctlTransportTest(unittest.TestCase):
    def runner(self, returncode=0, stdout="", stderr="", raises=None):
        calls = []

        def run(command, **kwargs):
            calls.append((command, kwargs))
            if raises:
                raise raises
            return subprocess.CompletedProcess(command, returncode, stdout, stderr)

        run.calls = calls
        return run

    def test_command_line_and_answer_parsing(self):
        run = self.runner(stdout='{"type":"s","data":["{\\"a\\":1}"]}')
        answer = BusctlTransport(runner=run).call("Apply", "[1]")
        self.assertEqual(answer, '{"a":1}')
        command = run.calls[0][0]
        self.assertEqual(command[:5], ["busctl", "--user", "--json=short", "call", protocol.BUS_NAME])
        self.assertEqual(command[-3:], ["Apply", "s", "[1]"])

    def test_call_without_a_payload_has_no_arguments(self):
        run = self.runner(stdout='{"type":"s","data":["x"]}')
        BusctlTransport(runner=run).call("GetState")
        self.assertEqual(run.calls[0][0][-1], "GetState")

    def test_missing_extension_is_explained(self):
        run = self.runner(returncode=1, stderr="Call failed: The name io.github.x was not provided by any .service files")
        with self.assertRaises(BackendError) as caught:
            BusctlTransport(runner=run).call("GetState")
        self.assertIn("extension is not running", str(caught.exception))

    def test_other_failures_are_reported(self):
        self.assertIn("boom", explain_failure("boom"))

    def test_missing_busctl_and_timeouts_and_bad_output(self):
        with self.assertRaises(BackendError):
            BusctlTransport(runner=self.runner(raises=FileNotFoundError())).call("GetState")
        with self.assertRaises(BackendError):
            BusctlTransport(runner=self.runner(raises=subprocess.TimeoutExpired("busctl", 1))).call("GetState")
        with self.assertRaises(BackendError):
            BusctlTransport(runner=self.runner(stdout="garbage")).call("GetState")

    def test_is_available_is_false_when_the_call_fails(self):
        self.assertFalse(BusctlTransport(runner=self.runner(returncode=1, stderr="no")).is_available())


def find_python_with_gi():
    for candidate in (sys.executable, "/usr/bin/python3.12", "/usr/bin/python3.11", "/usr/bin/python3.10",
                      "/usr/bin/python3", shutil.which("python3")):
        if candidate and os.path.exists(candidate):
            done = subprocess.run([candidate, "-c", "import gi; from gi.repository import Gio"],
                                  capture_output=True)
            if done.returncode == 0:
                return candidate
    return None


PYTHON_WITH_GI = find_python_with_gi()
BUS_TOOLS = bool(shutil.which("dbus-daemon") and shutil.which("busctl"))


@unittest.skipUnless(PYTHON_WITH_GI and BUS_TOOLS,
                     "needs dbus-daemon, busctl and a Python with PyGObject")
class RealBusTest(unittest.TestCase):
    """The whole path over a private session bus: busctl, JSON, the protocol and the backend."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.daemon = subprocess.Popen(["dbus-daemon", "--session", "--nofork", "--print-address=1"],
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.addCleanup(self.stop, self.daemon)
        address = self.daemon.stdout.readline().strip()
        self.env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS=address)
        self.service = None

    def stop(self, process):
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        if process.stdout:
            process.stdout.close()

    def start_service(self, windows, **kwargs):
        scenario = dict(monitors=[MONITOR], windows=windows, **kwargs)
        path = os.path.join(self.folder.name, "scenario.json")
        with open(path, "w") as handle:
            json.dump(scenario, handle)
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.service = subprocess.Popen(
            [PYTHON_WITH_GI, os.path.join(repo, "tests", "fake_shell_service.py"), path],
            stdout=subprocess.PIPE, text=True, env=self.env, cwd=repo)
        self.addCleanup(self.stop, self.service)
        self.assertEqual(self.service.stdout.readline().strip(), "ready")
        return GnomeBackend(BusctlTransport(env=self.env), settle_delay=0.01)

    def test_cascade_over_the_bus(self):
        backend = self.start_service([shell_window(i, (100 + 40 * i, 100, 400, 300)) for i in (1, 2, 3)])
        cascade(backend)
        rects = {w.id: w.rect for w in backend.windows()}
        self.assertEqual(rects[1], Rect(80, 40, 1540, 1020))
        self.assertEqual(rects[2], Rect(80, 80, 1660, 980))
        self.assertEqual(rects[3], Rect(80, 120, 1780, 940))

    def test_unusual_titles_survive_the_round_trip(self):
        title = 'Caf\u00e9 \u2014 \u65e5\u672c\u8a9e "quoted" back\\slash \'single\''
        backend = self.start_service([shell_window(1, title=title)])
        self.assertEqual(backend.windows()[0].title, title)

    def test_staircase_correction_over_the_bus(self):
        backend = self.start_service([shell_window(1), shell_window(2, _inc=[9, 17]), shell_window(3)])
        cascade(backend)
        self.assertEqual([w.rect.y for w in backend.windows()], [40, 80, 120])

    def test_missing_extension_is_reported_on_a_bus_without_the_service(self):
        transport = BusctlTransport(env=self.env, timeout=10)
        self.assertFalse(transport.is_available())
        with self.assertRaises(BackendError):
            GnomeBackend(transport).windows()


if __name__ == "__main__":
    unittest.main()
