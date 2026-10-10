import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from cascade_windows import cli
from cascade_windows.cascade import SCOPE_ALL, SCOPE_MONITOR, SCOPE_WORKSPACE, build_plan
from cascade_windows.exclusions import (
    ExcludeRule,
    RuleError,
    WorkspaceGrid,
    describe_targets,
    is_excluded,
    parse_rules,
    rule_to_dict,
    unmatched_references,
)
from cascade_windows.model import Rect
from cascade_windows.settings import Settings, SettingsError, settings_from_dict, settings_to_dict
from tests.fake_backend import FakeBackend, make_monitor, make_window

LEFT = make_monitor(0, 0, 0, 1920, 1080, name="HDMI-1")
RIGHT = make_monitor(1, 1920, 0, 1920, 1080, name="eDP-1")
GRID = WorkspaceGrid.create(["0", "1", "2", "3"], 2)  # 2 columns, 2 rows


class GridTest(unittest.TestCase):
    def test_workspaces_are_numbered_in_reading_order(self):
        self.assertEqual([GRID.position(i) for i in range(4)], [(0, 0), (1, 0), (0, 1), (1, 1)])
        self.assertEqual(GRID.index_at(1, 1), 3)
        self.assertEqual(GRID.index_at(0, 1), 2)
        self.assertIsNone(GRID.index_at(2, 0))
        self.assertIsNone(GRID.index_at(0, 2))

    def test_unknown_columns_mean_one_row(self):
        grid = WorkspaceGrid.create(["0", "1", "2"])
        self.assertEqual((grid.columns, grid.rows), (3, 1))
        self.assertEqual(grid.position(2), (2, 0))

    def test_a_single_column(self):
        grid = WorkspaceGrid.create(["0", "1", "2"], 1)
        self.assertEqual(grid.position(2), (0, 2))

    def test_labels(self):
        self.assertEqual(GRID.label(2), "2 (0,1)")


class ParseTest(unittest.TestCase):
    def test_monitor_name_number_and_lists(self):
        rules = parse_rules([{"monitor": "HDMI-1"}, {"monitor": [0, "eDP-1"]}])
        self.assertEqual(rules[0], ExcludeRule(("HDMI-1",), None))
        self.assertEqual(rules[1], ExcludeRule((0, "eDP-1"), None))

    def test_workspace_number_and_position(self):
        rules = parse_rules([{"workspace": 3}, {"workspace": ["1,0", 2, " 0 , 1 "]}])
        self.assertEqual(rules[0].workspaces, (3,))
        self.assertEqual(rules[1].workspaces, ((1, 0), 2, (0, 1)))

    def test_comment_keys_are_allowed(self):
        rules = parse_rules([{"comment": "ignore the TV", "monitor": 2}],
                            lambda key: key == "comment" or key.startswith("comment_"))
        self.assertEqual(rules[0].monitors, (2,))

    def test_round_trip(self):
        data = [{"monitor": "HDMI-1"}, {"workspace": "1,0", "monitor": [0, 2]}, {"workspace": [1, 2]}]
        self.assertEqual([rule_to_dict(r) for r in parse_rules(data)], data)

    def test_bad_rules_are_rejected(self):
        for bad in (
            "monitor", [3], [{}], [{"monitor": []}], [{"monitor": True}], [{"monitor": -1}],
            [{"monitor": ""}], [{"workspace": "left"}], [{"workspace": -2}], [{"workspace": 1.5}],
            [{"monitors": 1}], [{"monitor": 1, "workspaces": 2}],
        ):
            with self.assertRaises(RuleError, msg=repr(bad)):
                parse_rules(bad)

    def test_error_names_the_rule(self):
        with self.assertRaises(RuleError) as context:
            parse_rules([{"monitor": 0}, {"workspace": "x"}])
        self.assertIn("exclude[1]", str(context.exception))


class MatchTest(unittest.TestCase):
    def excluded(self, data, monitor, workspace):
        return is_excluded(parse_rules(data), monitor, workspace, GRID)

    def test_monitor_alone_applies_to_every_workspace(self):
        for workspace in "0123":
            self.assertTrue(self.excluded([{"monitor": "HDMI-1"}], LEFT, workspace))
            self.assertFalse(self.excluded([{"monitor": "HDMI-1"}], RIGHT, workspace))

    def test_monitor_names_ignore_case_and_numbers_are_indexes(self):
        self.assertTrue(self.excluded([{"monitor": "hdmi-1"}], LEFT, "0"))
        self.assertTrue(self.excluded([{"monitor": 1}], RIGHT, "0"))
        self.assertFalse(self.excluded([{"monitor": 1}], LEFT, "0"))

    def test_workspace_alone_applies_to_every_monitor(self):
        self.assertTrue(self.excluded([{"workspace": 2}], LEFT, "2"))
        self.assertTrue(self.excluded([{"workspace": 2}], RIGHT, "2"))
        self.assertFalse(self.excluded([{"workspace": 2}], LEFT, "1"))

    def test_workspace_by_position(self):
        self.assertTrue(self.excluded([{"workspace": "0,1"}], LEFT, "2"))
        self.assertFalse(self.excluded([{"workspace": "0,1"}], LEFT, "1"))
        self.assertFalse(self.excluded([{"workspace": "1,0"}], LEFT, "2"))

    def test_both_keys_exclude_only_the_combination(self):
        rules = [{"workspace": "1,0", "monitor": "HDMI-1"}]
        self.assertTrue(self.excluded(rules, LEFT, "1"))
        self.assertFalse(self.excluded(rules, RIGHT, "1"))
        self.assertFalse(self.excluded(rules, LEFT, "0"))

    def test_any_rule_may_match(self):
        rules = [{"monitor": 0}, {"workspace": 3}]
        self.assertTrue(self.excluded(rules, LEFT, "1"))
        self.assertTrue(self.excluded(rules, RIGHT, "3"))
        self.assertFalse(self.excluded(rules, RIGHT, "1"))

    def test_unknown_workspace_key_matches_no_workspace_rule(self):
        self.assertFalse(self.excluded([{"workspace": 0}], LEFT, "elsewhere"))


class ReportTest(unittest.TestCase):
    def test_targets_list_numbers_positions_and_names(self):
        lines = describe_targets([LEFT, RIGHT], GRID, "1")
        text = "\n".join(lines)
        self.assertIn("2 column(s), 2 row(s)", text)
        self.assertIn("  1  1,0  (current)", text)
        self.assertIn("  2  0,1", text)
        self.assertIn("  0  HDMI-1", text)
        self.assertIn("  1  eDP-1", text)

    def test_unmatched_references_are_reported(self):
        rules = parse_rules([{"monitor": "VGA-1"}, {"monitor": 0}, {"workspace": 9}, {"workspace": "2,2"}, {"workspace": "1,1"}])
        messages = unmatched_references(rules, [LEFT, RIGHT], GRID)
        self.assertEqual(len(messages), 3)
        self.assertIn("VGA-1", messages[0])
        self.assertIn("exclude[2]", messages[1])
        self.assertIn("2,2", messages[2])


def plan(windows, rules, scope=SCOPE_WORKSPACE, current="0", pointer=(10, 10), ignore=False):
    settings = Settings(exclude=parse_rules(rules))
    return build_plan([LEFT, RIGHT], windows, ["0", "1", "2", "3"], current, pointer, settings, scope,
                      workspace_columns=2, ignore_exclusions=ignore)


def moved(result):
    return sorted(move.window.id for move in result.moves)


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.windows = [
            make_window(1, Rect(100, 100, 400, 300)),                 # HDMI-1, workspace 0
            make_window(2, Rect(2000, 100, 400, 300)),                # eDP-1, workspace 0
            make_window(3, Rect(100, 100, 400, 300), workspace="1"),  # HDMI-1, workspace 1
            make_window(4, Rect(2000, 100, 400, 300), workspace="1"), # eDP-1, workspace 1
        ]

    def test_without_rules_nothing_changes(self):
        self.assertEqual(moved(plan(self.windows, [])), [1, 2])

    def test_an_excluded_monitor_is_left_alone_while_the_others_are_cascaded(self):
        result = plan(self.windows, [{"monitor": "HDMI-1"}])
        self.assertEqual(moved(result), [2])
        self.assertEqual(result.excluded_windows, 1)

    def test_all_scope_applies_the_rules_per_workspace(self):
        result = plan(self.windows, [{"monitor": "HDMI-1", "workspace": 1}], scope=SCOPE_ALL)
        self.assertEqual(moved(result), [1, 2, 4])
        self.assertEqual(result.excluded_windows, 1)

    def test_an_excluded_workspace_skips_every_monitor(self):
        result = plan(self.windows, [{"workspace": "1,0"}], scope=SCOPE_ALL)
        self.assertEqual(moved(result), [1, 2])
        self.assertEqual(result.excluded_windows, 2)

    def test_monitor_scope_on_an_excluded_monitor_does_nothing(self):
        result = plan(self.windows, [{"monitor": 0}], scope=SCOPE_MONITOR, pointer=(50, 50))
        self.assertEqual(moved(result), [])
        self.assertTrue(result.target_excluded)

    def test_monitor_scope_on_another_monitor_works(self):
        result = plan(self.windows, [{"monitor": 0}], scope=SCOPE_MONITOR, pointer=(2500, 50))
        self.assertEqual(moved(result), [2])
        self.assertFalse(result.target_excluded)

    def test_ignoring_the_exclusions(self):
        result = plan(self.windows, [{"monitor": 0}], ignore=True)
        self.assertEqual(moved(result), [1, 2])
        self.assertEqual(result.excluded_windows, 0)

    def test_describe_mentions_the_exclusions(self):
        text = "\n".join(plan(self.windows, [{"workspace": 0}]).describe())
        self.assertIn("2 window(s) left alone", text)


class SettingsTest(unittest.TestCase):
    def test_the_rules_are_read_and_written(self):
        data = {"exclude": [{"monitor": "HDMI-1"}, {"workspace": "1,0"}]}
        settings = settings_from_dict(data)
        self.assertEqual(len(settings.exclude), 2)
        self.assertEqual(settings_to_dict(settings)["exclude"], data["exclude"])

    def test_default_is_no_rules_and_notifications_on(self):
        settings = Settings()
        self.assertEqual(settings.exclude, ())
        self.assertTrue(settings.notify_excluded)
        self.assertEqual(settings_to_dict(settings)["exclude"], [])

    def test_invalid_rules_stop_with_a_clear_message(self):
        with self.assertRaises(SettingsError) as context:
            settings_from_dict({"exclude": [{"workspace": "left"}]})
        self.assertIn("exclude[0]", str(context.exception))

    def test_notifications_can_be_turned_off(self):
        self.assertFalse(settings_from_dict({"notify": {"excluded": False}}).notify_excluded)


class CliTest(unittest.TestCase):
    def run_cli(self, config, *args, windows=None, pointer=(50, 50)):
        backend = FakeBackend(
            [LEFT, RIGHT],
            windows if windows is not None else [make_window(1, Rect(100, 100, 400, 300))],
            workspaces=["0", "1", "2", "3"],
            pointer=pointer,
        )
        backend.workspace_columns = lambda: 2
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.json")
            with open(path, "w") as handle:
                json.dump(config, handle)
            with mock.patch.object(cli, "create_backend", return_value=backend), \
                    mock.patch.object(cli, "_notify") as notify, \
                    mock.patch("cascade_windows.undo.save_entries"), \
                    contextlib.redirect_stdout(out):
                code = cli.main(["--config", path] + list(args))
        return code, out.getvalue(), notify, backend

    def test_an_excluded_monitor_prints_and_notifies(self):
        code, output, notify, backend = self.run_cli({"exclude": [{"monitor": "HDMI-1"}]}, "--scope", "monitor")
        self.assertEqual(code, 0)
        self.assertIn("excluded", output)
        self.assertIn("--ignore-exclusions", output)
        notify.assert_called_once()
        self.assertFalse([c for c in backend.calls if c[0] == "place"])

    def test_the_notification_can_be_turned_off(self):
        config = {"exclude": [{"monitor": 0}], "notify": {"excluded": False}}
        _code, output, notify, _backend = self.run_cli(config, "--scope", "monitor")
        self.assertIn("excluded", output)
        notify.assert_not_called()

    def test_ignore_exclusions_cascades_anyway(self):
        _code, output, notify, backend = self.run_cli(
            {"exclude": [{"monitor": 0}]}, "--scope", "monitor", "--ignore-exclusions")
        self.assertIn("Cascaded 1 window(s)", output)
        notify.assert_not_called()
        self.assertTrue([c for c in backend.calls if c[0] == "place"])

    def test_partial_exclusion_reports_what_was_left_alone(self):
        windows = [make_window(1, Rect(100, 100, 400, 300)), make_window(2, Rect(2000, 100, 400, 300))]
        _code, output, notify, _backend = self.run_cli(
            {"exclude": [{"monitor": 0}]}, "--scope", "workspace", windows=windows)
        self.assertIn("Cascaded 1 window(s); 1 window(s) left alone", output)
        notify.assert_not_called()

    def test_list_targets(self):
        _code, output, _notify, _backend = self.run_cli({"exclude": [{"monitor": "VGA-9"}]}, "--list-targets")
        self.assertIn("2 column(s), 2 row(s)", output)
        self.assertIn("HDMI-1", output)
        self.assertIn("warning: exclude[0]: no monitor matches 'VGA-9'", output)

    def test_no_windows_without_exclusions_keeps_the_old_message(self):
        _code, output, notify, _backend = self.run_cli({}, "--scope", "monitor", windows=[])
        self.assertIn("No windows to cascade.", output)
        notify.assert_not_called()


class BackendColumnsTest(unittest.TestCase):
    """The workspace grid as the X11 and GNOME backends report it."""

    class FakeX11:
        def __init__(self, layout, desktops=4, viewports=None):
            self.uses_viewports = viewports is not None
            self.columns = viewports[0] if viewports else 1
            self.desktop_count = desktops
            self.root = None
            self._layout = layout

        def _cardinals(self, root, name):
            return self._layout if name == "_NET_DESKTOP_LAYOUT" else []

    def columns(self, **kwargs):
        from cascade_windows.x11_backend import X11Backend

        return X11Backend.workspace_columns(self.FakeX11(**kwargs))

    def test_compiz_viewports_use_the_viewport_columns(self):
        self.assertEqual(self.columns(layout=[], desktops=1, viewports=(2, 2)), 2)

    def test_horizontal_layout_with_columns(self):
        self.assertEqual(self.columns(layout=[0, 2, 2, 0]), 2)

    def test_horizontal_layout_with_rows_only(self):
        self.assertEqual(self.columns(layout=[0, 0, 2, 0], desktops=5), 3)

    def test_vertical_single_column(self):
        self.assertEqual(self.columns(layout=[1, 1, 4, 0]), 1)

    def test_vertical_grid_is_not_understood(self):
        self.assertEqual(self.columns(layout=[1, 2, 2, 0]), 0)

    def test_no_layout_property(self):
        self.assertEqual(self.columns(layout=[]), 0)

    def test_gnome_state_carries_the_columns(self):
        from cascade_windows.shell_protocol import parse_state

        state = json.dumps({
            "protocol": 1, "monitors": [{"index": 0, "rect": [0, 0, 10, 10]}], "workspaces": ["0", "1"],
            "workspace_columns": 2, "current_workspace": "0", "windows": [],
        })
        self.assertEqual(parse_state(state).workspace_columns, 2)
        without = json.loads(state)
        del without["workspace_columns"]
        self.assertEqual(parse_state(json.dumps(without)).workspace_columns, 0)


if __name__ == "__main__":
    unittest.main()
