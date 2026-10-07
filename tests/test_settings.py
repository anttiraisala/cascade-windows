import json
import os
import tempfile
import unittest

from cascade_windows.settings import (
    Settings,
    SettingsError,
    default_settings_dict,
    load_settings,
    settings_from_dict,
    settings_to_dict,
    write_default_config,
)


class SettingsTest(unittest.TestCase):
    def test_defaults_match_the_documented_values(self):
        settings = Settings()
        self.assertEqual(settings.margin_left, 20)
        self.assertEqual(settings.size_mode, "anchored")
        self.assertTrue(settings.wrap_enabled)

    def test_partial_configuration_keeps_other_defaults(self):
        settings = settings_from_dict({"margin": {"top": 5}, "step": {"x": 11}})
        self.assertEqual(settings.margin_top, 5)
        self.assertEqual(settings.margin_left, 20)
        self.assertEqual(settings.step_x, 11)
        self.assertEqual(settings.step_y, 40)

    def test_round_trip_through_the_dictionary_form(self):
        original = Settings(size_mode="fit", step_x=7, wrap_enabled=False, order="name")
        self.assertEqual(settings_from_dict(settings_to_dict(original)), original)

    def test_unknown_keys_are_reported_but_ignored(self):
        warnings = []
        settings = settings_from_dict({"colour": 1, "margin": {"diagonal": 2}}, warnings.append)
        self.assertEqual(settings, Settings())
        self.assertEqual(len(warnings), 2)

    def test_invalid_values_raise_clear_errors(self):
        for data in (
            {"size_mode": "spiral"},
            {"step": {"x": -1}},
            {"step": {"x": "wide"}},
            {"step": {"x": True}},
            {"wrap": {"enabled": "yes"}},
            {"percent": {"width": 150}},
            {"margin": 20},
        ):
            with self.subTest(data=data):
                with self.assertRaises(SettingsError):
                    settings_from_dict(data)

    def test_missing_file_means_defaults(self):
        self.assertEqual(load_settings("/nonexistent/config.json"), Settings())

    def test_broken_json_is_reported_with_the_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.json")
            with open(path, "w") as handle:
                handle.write("{ not json")
            with self.assertRaises(SettingsError) as context:
                load_settings(path)
            self.assertIn(path, str(context.exception))

    def test_written_default_config_loads_back_as_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "sub", "config.json")
            write_default_config(path)
            with open(path) as handle:
                self.assertEqual(json.load(handle), default_settings_dict())
            self.assertEqual(load_settings(path), Settings())

    def test_existing_config_is_not_overwritten_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.json")
            with open(path, "w") as handle:
                handle.write('{"step": {"x": 1}}')
            write_default_config(path)
            self.assertEqual(load_settings(path).step_x, 1)


if __name__ == "__main__":
    unittest.main()
