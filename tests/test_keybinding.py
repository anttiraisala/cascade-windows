import os
import unittest
from unittest import mock

from cascade_windows import keybinding

CINNAMON_SCHEMAS = [
    "org.cinnamon.desktop.keybindings",
    "org.cinnamon.desktop.keybindings.custom-keybinding",
]
GNOME_SCHEMAS = [
    "org.gnome.settings-daemon.plugins.media-keys",
    "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding",
]
UNITY_SCHEMAS = [
    "com.canonical.unity.settings-daemon.plugins.media-keys",
    "com.canonical.unity.settings-daemon.plugins.media-keys.custom-keybinding",
]
UNITY_PATH = "/com/canonical/unity/settings-daemon/plugins/media-keys/custom-keybindings/cascade-windows/"


class FakeGsettings:
    """Just enough of the gsettings command to test list handling."""

    def __init__(self, schemas):
        self.schemas = schemas
        self.values = {}

    def __call__(self, *args):
        command = args[0]
        # Like the real gsettings, the per-shortcut schemas are relocatable and are only listed
        # by list-relocatable-schemas, never by list-schemas.
        if command == "list-schemas":
            return "\n".join(name for name in self.schemas if not name.endswith("custom-keybinding"))
        if command == "list-relocatable-schemas":
            return "\n".join(name for name in self.schemas if name.endswith("custom-keybinding"))
        if command == "get":
            return self.values.get((args[1], args[2]), "@as []")
        if command == "set":
            self.values[(args[1], args[2])] = args[3]
            return ""
        if command == "reset-recursively":
            self.values = {k: v for k, v in self.values.items() if k[0] != args[1]}
            return ""
        raise AssertionError("unexpected gsettings call %r" % (args,))


class KeybindingTest(unittest.TestCase):
    def run_with(self, desktop, schemas):
        fake = FakeGsettings(schemas)
        patches = [
            mock.patch.object(keybinding, "_gsettings", fake),
            mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": desktop}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        return fake

    def test_cinnamon_registers_an_id_and_a_binding_list(self):
        fake = self.run_with("X-Cinnamon", CINNAMON_SCHEMAS)
        keybinding.install("/home/me/.local/bin/cascade-windows --scope monitor")
        self.assertEqual(
            fake.values[("org.cinnamon.desktop.keybindings", "custom-list")], "['cascade-windows']"
        )
        item = "org.cinnamon.desktop.keybindings.custom-keybinding:/org/cinnamon/desktop/keybindings/custom-keybindings/cascade-windows/"
        self.assertEqual(fake.values[(item, "binding")], "['<Super><Shift>c']")
        self.assertEqual(fake.values[(item, "name")], "Cascade Windows")

    def test_unity_prefers_the_canonical_schema(self):
        fake = self.run_with("Unity:Unity7:ubuntu", UNITY_SCHEMAS + GNOME_SCHEMAS)
        keybinding.install("/x/cascade-windows --scope monitor")
        entries = fake.values[(UNITY_SCHEMAS[0], "custom-keybindings")]
        self.assertIn(UNITY_PATH, entries)
        item = UNITY_SCHEMAS[1] + ":" + UNITY_PATH
        self.assertEqual(fake.values[(item, "binding")], "<Super><Shift>c")
        self.assertEqual(fake.values[(item, "name")], "Cascade Windows")

    def test_unity_install_moves_an_older_gnome_style_registration(self):
        fake = self.run_with("Unity:Unity7:ubuntu", UNITY_SCHEMAS + GNOME_SCHEMAS)
        old = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/cascade-windows/"
        fake.values[(GNOME_SCHEMAS[0], "custom-keybindings")] = repr([old, "/other/"])
        keybinding.install("cmd")
        self.assertEqual(fake.values[(GNOME_SCHEMAS[0], "custom-keybindings")], repr(["/other/"]))

    def test_unity_removal_clears_both_locations(self):
        fake = self.run_with("Unity:Unity7:ubuntu", UNITY_SCHEMAS + GNOME_SCHEMAS)
        keybinding.install("cmd")
        keybinding.remove()
        self.assertEqual(fake.values[(UNITY_SCHEMAS[0], "custom-keybindings")], "[]")

    def test_unity_falls_back_to_the_gnome_schema(self):
        fake = self.run_with("Unity:Unity7:ubuntu", GNOME_SCHEMAS)
        keybinding.install("/x/cascade-windows --scope monitor")
        entries = fake.values[("org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings")]
        self.assertIn(
            "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/cascade-windows/", entries
        )
        item = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:" + (
            "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/cascade-windows/"
        )
        self.assertEqual(fake.values[(item, "binding")], "<Super><Shift>c")

    def test_installing_twice_does_not_duplicate_the_entry(self):
        fake = self.run_with("X-Cinnamon", CINNAMON_SCHEMAS)
        keybinding.install("cmd")
        keybinding.install("cmd")
        self.assertEqual(
            fake.values[("org.cinnamon.desktop.keybindings", "custom-list")], "['cascade-windows']"
        )

    def test_other_shortcuts_are_preserved_and_removal_only_takes_ours(self):
        fake = self.run_with("X-Cinnamon", CINNAMON_SCHEMAS)
        fake.values[("org.cinnamon.desktop.keybindings", "custom-list")] = "['custom0']"
        keybinding.install("cmd")
        self.assertIn("custom0", fake.values[("org.cinnamon.desktop.keybindings", "custom-list")])
        keybinding.remove()
        self.assertEqual(
            fake.values[("org.cinnamon.desktop.keybindings", "custom-list")], "['custom0']"
        )

    def test_missing_schema_is_reported_by_name(self):
        self.run_with("X-Cinnamon", CINNAMON_SCHEMAS[:1])  # the relocatable schema is missing
        with self.assertRaises(keybinding.KeybindingError) as context:
            keybinding.install("cmd")
        self.assertIn("custom-keybinding", str(context.exception))

    def test_no_schemas_at_all_is_reported(self):
        self.run_with("Unity:Unity7:ubuntu", [])
        with self.assertRaises(keybinding.KeybindingError):
            keybinding.install("cmd")

    def test_unknown_desktop_is_reported(self):
        self.run_with("KDE", [])
        with self.assertRaises(keybinding.KeybindingError):
            keybinding.install("cmd")


if __name__ == "__main__":
    unittest.main()
