import os
import shutil
import subprocess
import unittest

EXTENSION = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gnome-extension")


@unittest.skipUnless(shutil.which("node"), "needs Node.js")
class ExtensionLogicTest(unittest.TestCase):
    """Runs the Node tests of the pure parts of the GNOME Shell extension."""

    def test_node_tests_pass(self):
        tests = sorted(n for n in os.listdir(os.path.join(EXTENSION, "tests")) if n.endswith(".test.js"))
        done = subprocess.run(["node", "--test"] + [os.path.join("tests", n) for n in tests],
                              cwd=EXTENSION, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout[-3000:] + done.stderr[-1000:])

    def test_every_javascript_file_parses(self):
        files = ["extension.js"] + ["lib/" + n for n in sorted(os.listdir(os.path.join(EXTENSION, "lib")))]
        for name in files:
            done = subprocess.run(["node", "--check", name], cwd=EXTENSION, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, name + "\n" + done.stderr)

    @unittest.skipUnless(shutil.which("glib-compile-schemas"), "needs glib-compile-schemas")
    def test_the_settings_schema_is_valid(self):
        done = subprocess.run(["glib-compile-schemas", "--strict", "--dry-run", "schemas"],
                              cwd=EXTENSION, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
