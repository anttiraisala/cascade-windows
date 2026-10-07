import contextlib
import io
import json
import os
import tempfile
import unittest

from cascade_windows.cli import main


class ShowConfigTest(unittest.TestCase):
    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(list(args))
        return code, out.getvalue()

    def test_show_config_prints_the_settings_in_effect(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.json")
            with open(path, "w") as handle:
                json.dump({"step": {"x": 77, "y": 5}}, handle)
            code, output = self.run_main("--config", path, "--show-config")
        self.assertEqual(code, 0)
        self.assertIn(path, output)
        data = json.loads(output[output.index("{"):])
        self.assertEqual(data["step"], {"x": 77, "y": 5})
        self.assertEqual(data["margin"]["left"], 20)

    def test_show_config_without_a_file_reports_the_defaults(self):
        code, output = self.run_main("--config", "/nonexistent/config.json", "--show-config")
        self.assertEqual(code, 0)
        self.assertIn("not found, using defaults", output)
        self.assertEqual(json.loads(output[output.index("{"):])["step"], {"x": 120, "y": 40})


if __name__ == "__main__":
    unittest.main()
