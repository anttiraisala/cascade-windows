import os
import tempfile
import unittest

from cascade_windows import undo
from cascade_windows.cascade import (
    SCOPE_ALL,
    SCOPE_MONITOR,
    SCOPE_WORKSPACE,
    apply_plan,
    build_plan,
    plan_for_backend,
    restore_positions,
    sort_windows,
)
from cascade_windows.model import KIND_DIALOG, KIND_OTHER, Rect
from cascade_windows.settings import Settings

from tests.fake_backend import FakeBackend, make_monitor, make_window

LEFT = make_monitor(0, 0, 0, 1920, 1080, panel=30)
RIGHT = make_monitor(1, 1920, 0, 1920, 1080)


def plan(windows, settings=None, scope=SCOPE_WORKSPACE, current="0", pointer=(10, 10),
         workspaces=("0", "1"), monitors=(LEFT, RIGHT)):
    return build_plan(monitors, windows, list(workspaces), current, pointer,
                      settings or Settings(), scope)


def moved_ids(result):
    return [move.window.id for move in result.moves]


class SelectionTest(unittest.TestCase):
    def test_minimized_windows_are_skipped(self):
        result = plan([make_window(1), make_window(2, minimized=True)])
        self.assertEqual(moved_ids(result), [1])

    def test_dialogs_and_special_windows_stay_where_they_are(self):
        result = plan([make_window(1), make_window(2, kind=KIND_DIALOG),
                       make_window(3, kind=KIND_OTHER)])
        self.assertEqual(moved_ids(result), [1])

    def test_fullscreen_and_sticky_windows_are_skipped_by_default(self):
        result = plan([make_window(1), make_window(2, fullscreen=True), make_window(3, sticky=True)])
        self.assertEqual(moved_ids(result), [1])

    def test_skip_options_can_be_turned_off(self):
        settings = Settings(skip_minimized=False)
        result = plan([make_window(1, minimized=True)], settings)
        self.assertEqual(moved_ids(result), [1])

    def test_maximized_windows_are_included_by_default(self):
        self.assertEqual(moved_ids(plan([make_window(1, maximized=True)])), [1])

    def test_maximized_windows_can_be_left_alone(self):
        settings = Settings(restore_maximized=False)
        self.assertEqual(moved_ids(plan([make_window(1, maximized=True)], settings)), [])


class ScopeTest(unittest.TestCase):
    def setUp(self):
        self.windows = [
            make_window(1, Rect(100, 100, 400, 300)),                 # left monitor, workspace 0
            make_window(2, Rect(2000, 100, 400, 300)),                # right monitor, workspace 0
            make_window(3, Rect(100, 100, 400, 300), workspace="1"),  # left monitor, workspace 1
        ]

    def test_monitor_scope_uses_the_monitor_under_the_pointer(self):
        self.assertEqual(moved_ids(plan(self.windows, scope=SCOPE_MONITOR, pointer=(50, 50))), [1])
        self.assertEqual(moved_ids(plan(self.windows, scope=SCOPE_MONITOR, pointer=(2500, 50))), [2])

    def test_workspace_scope_covers_every_monitor_of_the_current_workspace(self):
        self.assertEqual(sorted(moved_ids(plan(self.windows, scope=SCOPE_WORKSPACE))), [1, 2])

    def test_all_scope_covers_every_workspace(self):
        self.assertEqual(sorted(moved_ids(plan(self.windows, scope=SCOPE_ALL))), [1, 2, 3])

    def test_each_monitor_is_cascaded_separately(self):
        result = plan(self.windows, scope=SCOPE_WORKSPACE)
        by_id = {move.window.id: move.rect for move in result.moves}
        # Both are single windows, so each fills the usable area of its own monitor.
        self.assertEqual(by_id[1], Rect(20, 50, 1880, 1010))   # 30 px panel + 20 px margin
        self.assertEqual(by_id[2], Rect(1940, 20, 1880, 1040))

    def test_unknown_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            plan(self.windows, scope="everything")


class OrderTest(unittest.TestCase):
    def setUp(self):
        self.windows = [
            make_window(1, title="b", wm_class="Zed", stack_index=2, open_index=0),
            make_window(2, title="a", wm_class="Zed", stack_index=0, open_index=1),
            make_window(3, title="c", wm_class="alpha", stack_index=1, open_index=2),
        ]

    def test_stacking_order_is_the_default(self):
        self.assertEqual([w.id for w in sort_windows(self.windows, "stacking")], [2, 3, 1])

    def test_opening_order(self):
        self.assertEqual([w.id for w in sort_windows(self.windows, "opening")], [1, 2, 3])

    def test_name_order_sorts_by_application_then_title(self):
        self.assertEqual([w.id for w in sort_windows(self.windows, "name")], [3, 2, 1])

    def test_back_window_is_planned_first_and_gets_the_top_of_the_cascade(self):
        result = plan(self.windows, scope=SCOPE_WORKSPACE, monitors=(LEFT,))
        self.assertEqual(moved_ids(result), [2, 3, 1])
        self.assertLess(result.moves[0].rect.y, result.moves[2].rect.y)


class ApplyTest(unittest.TestCase):
    def test_maximized_windows_are_restored_before_they_are_moved(self):
        backend = FakeBackend([LEFT], [make_window(1, maximized=True)])
        result = plan_for_backend(backend, Settings(), SCOPE_WORKSPACE)
        apply_plan(backend, result, Settings())
        kinds = [call[0] for call in backend.calls]
        self.assertLess(kinds.index("unmaximize"), kinds.index("place"))
        self.assertFalse(backend.window(1).maximized)

    def test_windows_are_raised_back_to_front_then_committed(self):
        windows = [make_window(i) for i in (1, 2, 3)]
        backend = FakeBackend([LEFT], windows)
        apply_plan(backend, plan_for_backend(backend, Settings(), SCOPE_WORKSPACE), Settings())
        raised = [call[1] for call in backend.calls if call[0] == "raise"]
        self.assertEqual(raised, [1, 2, 3])
        self.assertEqual(backend.calls[-1], ("commit",))

    def test_fixed_size_windows_keep_their_size(self):
        window = make_window(1, resizable=False)
        backend = FakeBackend([LEFT], [window])
        apply_plan(backend, plan_for_backend(backend, Settings(), SCOPE_WORKSPACE), Settings())
        self.assertEqual((backend.window(1).rect.width, backend.window(1).rect.height), (400, 300))
        self.assertEqual((backend.window(1).rect.x, backend.window(1).rect.y), (20, 50))

    def test_dialogs_are_never_touched(self):
        dialog = make_window(2, kind=KIND_DIALOG)
        backend = FakeBackend([LEFT], [make_window(1), dialog])
        apply_plan(backend, plan_for_backend(backend, Settings(), SCOPE_WORKSPACE), Settings())
        self.assertEqual(backend.window(2).rect, dialog.rect)
        self.assertNotIn(2, [call[1] for call in backend.calls if call[0] in ("place", "raise")])

    def test_everything_ends_up_inside_the_margin(self):
        windows = [make_window(i) for i in range(1, 8)]
        backend = FakeBackend([LEFT], windows)
        apply_plan(backend, plan_for_backend(backend, Settings(), SCOPE_WORKSPACE), Settings())
        for window in backend.windows():
            self.assertGreaterEqual(window.rect.x, 20)
            self.assertGreaterEqual(window.rect.y, 50)
            self.assertLessEqual(window.rect.right, 1900)
            self.assertLessEqual(window.rect.bottom, 1060)


class UndoTest(unittest.TestCase):
    def test_undo_restores_positions_and_maximized_state(self):
        originals = [
            make_window(1, Rect(10, 20, 300, 200)),
            make_window(2, Rect(0, 30, 1920, 1050), maximized=True),
        ]
        backend = FakeBackend([LEFT], originals)
        result = plan_for_backend(backend, Settings(), SCOPE_WORKSPACE)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "undo.json")
            undo.save_entries(undo.entries_from_plan(result), path)
            apply_plan(backend, result, Settings())
            self.assertNotEqual(backend.window(1).rect, originals[0].rect)
            restored = restore_positions(backend, undo.load_entries(path))
        self.assertEqual(restored, 2)
        self.assertEqual(backend.window(1).rect, originals[0].rect)
        self.assertEqual(backend.window(2).rect, originals[1].rect)
        self.assertTrue(backend.window(2).maximized)

    def test_windows_that_disappeared_are_ignored(self):
        backend = FakeBackend([LEFT], [make_window(1)])
        entries = [undo.UndoEntry(99, "0", Rect(0, 0, 10, 10), False)]
        self.assertEqual(restore_positions(backend, entries), 0)

    def test_missing_or_broken_undo_file_means_nothing_to_undo(self):
        self.assertEqual(undo.load_entries("/nonexistent/undo.json"), [])
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "undo.json")
            with open(path, "w") as handle:
                handle.write("garbage")
            self.assertEqual(undo.load_entries(path), [])


if __name__ == "__main__":
    unittest.main()
