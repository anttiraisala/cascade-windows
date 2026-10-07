import json
import os
import tempfile
import unittest

from cascade_windows.settings import (
    Settings,
    SettingsError,
    COMMENT_KEY,
    default_settings_dict,
    documented_default_dict,
    remove_legacy_default_config,
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
                self.assertEqual(json.load(handle), documented_default_dict())
            self.assertEqual(load_settings(path), Settings())

    def test_existing_config_is_not_overwritten_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.json")
            with open(path, "w") as handle:
                handle.write('{"step": {"x": 1}}')
            write_default_config(path)
            self.assertEqual(load_settings(path).step_x, 1)


def strip_comments(value):
    if isinstance(value, dict):
        return {
            k: strip_comments(v)
            for k, v in value.items()
            if not (k == COMMENT_KEY or k.startswith(COMMENT_KEY + "_"))
        }
    return value


class CommentTest(unittest.TestCase):
    def test_comment_keys_are_ignored_without_warnings_at_any_level(self):
        warnings = []
        data = {
            "comment": "top",
            "comment_size_mode": "about the mode",
            "step": {"comment": "nested", "x": 9},
        }
        settings = settings_from_dict(data, warnings.append)
        self.assertEqual(warnings, [])
        self.assertEqual(settings.step_x, 9)

    def test_documented_defaults_equal_the_plain_defaults_without_comments(self):
        self.assertEqual(strip_comments(documented_default_dict()), default_settings_dict())
        self.assertEqual(settings_from_dict(documented_default_dict()), Settings())

    def test_every_section_and_every_choice_setting_is_explained(self):
        documented = documented_default_dict()
        self.assertIn(COMMENT_KEY, documented)
        for key, value in default_settings_dict().items():
            if isinstance(value, dict):
                self.assertIn(COMMENT_KEY, documented[key], key)
                self.assertTrue(documented[key][COMMENT_KEY], key)
            else:
                self.assertIn(COMMENT_KEY + "_" + key, documented, key)

    def test_the_size_mode_comment_names_every_mode(self):
        text = documented_default_dict()["comment_size_mode"]
        for mode in ("anchored", "fit", "percent", "fixed"):
            self.assertIn("'%s'" % mode, text)

    def test_comments_are_plain_english_text(self):
        def texts(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == COMMENT_KEY or key.startswith(COMMENT_KEY + "_"):
                        yield item
                    else:
                        for found in texts(item):
                            yield found
        for text in texts(documented_default_dict()):
            self.assertTrue(text.isascii(), text)


class LegacyConfigTest(unittest.TestCase):
    def write(self, folder, data):
        path = os.path.join(folder, "config.json")
        with open(path, "w") as handle:
            json.dump(data, handle)
        return path

    def legacy(self):
        data = default_settings_dict()
        data["step"] = {"x": 30, "y": 30}
        return data

    def test_untouched_legacy_file_is_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, self.legacy())
            self.assertTrue(remove_legacy_default_config(path))
            self.assertFalse(os.path.exists(path))

    def test_modified_file_is_kept(self):
        with tempfile.TemporaryDirectory() as folder:
            data = self.legacy()
            data["step"]["x"] = 31
            path = self.write(folder, data)
            self.assertFalse(remove_legacy_default_config(path))
            self.assertTrue(os.path.exists(path))

    def test_file_with_current_defaults_is_kept(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, default_settings_dict())
            self.assertFalse(remove_legacy_default_config(path))
            self.assertTrue(os.path.exists(path))

    def test_missing_or_broken_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(remove_legacy_default_config(os.path.join(folder, "none.json")))
            path = os.path.join(folder, "config.json")
            with open(path, "w") as handle:
                handle.write("{ broken")
            self.assertFalse(remove_legacy_default_config(path))
            self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
