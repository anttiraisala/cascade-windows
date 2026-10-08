import unittest

from cascade_windows import environment


def report(env, tools=("gsettings", "nemo"), module=True, schemas=True):
    return environment.build_report(
        environ=env,
        which=lambda name: "/usr/bin/" + name if name in tools else None,
        run=lambda command: "fake 1.0",
        has_module=lambda name: module,
        schema_exists=lambda name: schemas,
    )


class EnvironmentTest(unittest.TestCase):
    def test_desktop_families(self):
        family = environment.desktop_family
        self.assertEqual(family({"XDG_CURRENT_DESKTOP": "X-Cinnamon"}), "cinnamon")
        self.assertEqual(family({"XDG_CURRENT_DESKTOP": "Unity:Unity7:ubuntu"}), "unity")
        self.assertEqual(family({"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}), "gnome")
        self.assertEqual(family({"XDG_CURRENT_DESKTOP": "KDE"}), "other")
        self.assertEqual(family({}), "other")

    def test_planned_install(self):
        self.assertIn("GNOME Shell extension", environment.planned_install("gnome", "wayland"))
        self.assertIn("X11 version", environment.planned_install("unity", "x11"))
        self.assertIn("Wayland", environment.planned_install("other", "wayland"))

    def test_report_lists_detection_and_tools(self):
        lines = report({"XDG_CURRENT_DESKTOP": "Unity:Unity7:ubuntu", "XDG_SESSION_TYPE": "x11"})
        text = "\n".join(lines)
        self.assertIn("desktop family: unity", text)
        self.assertIn("planned install: X11 version", text)
        self.assertIn("nemo version: fake 1.0", text)
        self.assertIn("gsettings: /usr/bin/gsettings", text)
        self.assertIn("busctl: not found", text)
        self.assertIn("shortcut schema com.canonical.unity.settings-daemon.plugins.media-keys: present", text)

    def test_missing_pieces_are_reported(self):
        text = "\n".join(report({}, tools=(), module=False, schemas=False))
        self.assertIn("(not set)", text)
        self.assertIn("python-xlib: missing", text)
        self.assertNotIn("shortcut schema", text)


if __name__ == "__main__":
    unittest.main()
