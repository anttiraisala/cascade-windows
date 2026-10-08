import os
import shutil
import stat
import subprocess
import tempfile
import unittest

from cascade_windows import gnome_install
from cascade_windows.backend import BackendError

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UUID = gnome_install.EXTENSION_UUID


class FakeGsettings:
    """A runner that behaves like the gsettings command and remembers the values."""

    def __init__(self, enabled="@as []", disabled="@as []"):
        self.values = {"enabled-extensions": enabled, "disabled-extensions": disabled}
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        action, _schema, key = command[1:4]
        if action == "get":
            return subprocess.CompletedProcess(command, 0, self.values[key] + "\n", "")
        self.values[key] = command[4]
        return subprocess.CompletedProcess(command, 0, "", "")


class ListFormatTest(unittest.TestCase):
    def test_parsing(self):
        self.assertEqual(gnome_install.parse_list("@as []"), [])
        self.assertEqual(gnome_install.parse_list("[]"), [])
        self.assertEqual(gnome_install.parse_list("['a@b', 'c']\n"), ["a@b", "c"])
        self.assertEqual(gnome_install.parse_list('["it\'s"]'), ["it's"])

    def test_garbage_is_refused(self):
        for text in ("nonsense", "42", "[1, 2]", "{'a': 1}"):
            with self.assertRaises(BackendError):
                gnome_install.parse_list(text)

    def test_formatting_round_trips(self):
        for items in ([], ["a"], ["a@b", "it's", "back\\slash"]):
            self.assertEqual(gnome_install.parse_list(gnome_install.format_list(items)), items)


class EnableDisableTest(unittest.TestCase):
    def test_enable_adds_the_extension_and_keeps_the_others(self):
        runner = FakeGsettings(enabled="['other@x']")
        self.assertIn("Enabled", gnome_install.enable(runner))
        self.assertEqual(gnome_install.parse_list(runner.values["enabled-extensions"]), ["other@x", UUID])

    def test_enable_twice_changes_nothing(self):
        runner = FakeGsettings(enabled="['%s']" % UUID)
        self.assertIn("already enabled", gnome_install.enable(runner))
        self.assertFalse([c for c in runner.calls if c[1] == "set"])

    def test_enable_removes_the_extension_from_the_disabled_list(self):
        runner = FakeGsettings(disabled="['%s', 'keep@x']" % UUID)
        gnome_install.enable(runner)
        self.assertEqual(gnome_install.parse_list(runner.values["disabled-extensions"]), ["keep@x"])

    def test_disable_removes_only_this_extension(self):
        runner = FakeGsettings(enabled="['a@x', '%s', 'b@x']" % UUID)
        self.assertIn("Disabled", gnome_install.disable(runner))
        self.assertEqual(gnome_install.parse_list(runner.values["enabled-extensions"]), ["a@x", "b@x"])

    def test_disable_when_not_enabled_is_harmless(self):
        runner = FakeGsettings(enabled="['a@x']")
        self.assertIn("was not enabled", gnome_install.disable(runner))

    def test_missing_gsettings_is_reported(self):
        def runner(command, **kwargs):
            raise FileNotFoundError()

        with self.assertRaises(BackendError):
            gnome_install.enable(runner)


@unittest.skipUnless(shutil.which("bash") and shutil.which("glib-compile-schemas"), "needs bash and glib-compile-schemas")
class InstallerTest(unittest.TestCase):
    """Runs install.sh and uninstall.sh against a throw-away home with a fake gsettings."""

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        bin_dir = os.path.join(self.home, "fakebin")
        os.makedirs(bin_dir)
        script = os.path.join(bin_dir, "gsettings")
        with open(script, "w") as handle:
            handle.write('#!/bin/sh\nstore="$HOME/gs"; mkdir -p "$store"\n'
                         'case "$1" in\n'
                         '  get) [ -f "$store/$3" ] && cat "$store/$3" || echo "@as []" ;;\n'
                         '  set) echo "$4" > "$store/$3" ;;\nesac\n')
        os.chmod(script, os.stat(script).st_mode | stat.S_IEXEC)
        self.env = dict(os.environ, HOME=self.home, XDG_DATA_HOME=os.path.join(self.home, "data"),
                        XDG_CONFIG_HOME=os.path.join(self.home, "cfg"), XDG_CURRENT_DESKTOP="ubuntu:GNOME",
                        XDG_SESSION_TYPE="wayland", PATH=bin_dir + os.pathsep + os.environ["PATH"])
        self.env.pop("PYTHONPATH", None)  # python-xlib must not be needed on GNOME
        self.extension = os.path.join(self.home, "data", "gnome-shell", "extensions", UUID)

    def run_script(self, *command):
        return subprocess.run(["bash", os.path.join(REPO, command[0])] + list(command[1:]),
                              env=self.env, capture_output=True, text=True, cwd=REPO)

    def enabled(self):
        with open(os.path.join(self.home, "gs", "enabled-extensions")) as handle:
            return gnome_install.parse_list(handle.read())

    def test_gnome_install_copies_the_extension_enables_it_and_needs_no_xlib(self):
        done = self.run_script("install.sh")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        for name in ("metadata.json", "extension.js", "lib/protocol.js", "lib/windows.js",
                     "icons/cascade-symbolic.svg", "schemas/gschemas.compiled"):
            self.assertTrue(os.path.exists(os.path.join(self.extension, name)), name)
        self.assertFalse(os.path.exists(os.path.join(self.extension, "tests")))
        self.assertEqual(self.enabled(), [UUID])
        self.assertIn("Log out and in", done.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.home, "data", "nemo")))  # no Nemo entries on GNOME

    def test_installing_twice_keeps_one_entry(self):
        self.run_script("install.sh")
        self.run_script("install.sh")
        self.assertEqual(self.enabled(), [UUID])

    def test_uninstall_removes_the_extension_and_disables_it(self):
        self.run_script("install.sh")
        done = self.run_script("uninstall.sh")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertFalse(os.path.exists(self.extension))
        self.assertEqual(self.enabled(), [])

    def test_unknown_backend_is_rejected(self):
        done = self.run_script("install.sh", "--backend", "nonsense")
        self.assertEqual(done.returncode, 2)

    def test_the_x11_installer_still_refuses_wayland(self):
        done = self.run_script("install.sh", "--backend", "x11")
        self.assertEqual(done.returncode, 1)
        self.assertIn("Wayland", done.stderr)


if __name__ == "__main__":
    unittest.main()
