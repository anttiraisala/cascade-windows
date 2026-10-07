import json
import os
import tempfile
import unittest

from cascade_windows import nemo_menu

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(path):
    with open(path) as handle:
        return json.load(handle)


def write(path, data):
    with open(path, "w") as handle:
        if isinstance(data, str):
            handle.write(data)
        else:
            json.dump(data, handle)


def ours(data):
    return [n for n in data["toplevel"] if n.get("uuid") == nemo_menu.SUBMENU_LABEL]


class NemoMenuTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = os.path.join(self.folder.name, "nemo", "actions-tree.json")

    def test_every_listed_action_file_exists_in_the_repository(self):
        for item in nemo_menu.SUBMENU_ITEMS:
            if item is not None:
                self.assertTrue(os.path.exists(os.path.join(REPO, "nemo", item)), item)

    def test_every_action_file_in_the_repository_is_in_the_submenu(self):
        listed = {item for item in nemo_menu.SUBMENU_ITEMS if item}
        found = {n for n in os.listdir(os.path.join(REPO, "nemo")) if n.endswith(".nemo_action")}
        self.assertEqual(listed, found)

    def test_creates_the_layout_file_when_there_is_none(self):
        nemo_menu.install(self.path)
        submenu = ours(read(self.path))[0]
        self.assertEqual(submenu["type"], "submenu")
        self.assertEqual(submenu["user-label"], "Cascade Windows")
        kinds = [c["type"] for c in submenu["children"]]
        self.assertEqual(kinds, ["action", "action", "action", "separator", "action", "action"])
        self.assertEqual(submenu["children"][0]["uuid"], "cascade-windows-1-cascade.nemo_action")
        self.assertIsNone(submenu["children"][0]["user-label"])  # the Name= of the action file is shown

    EXPECTED_ORDER = [
        "Cascade Windows",
        "Cascade Workspace",
        "Cascade All Workspaces",
        None,
        "Undo Cascade",
        "Cascade Settings...",
    ]

    def action_name(self, file_name):
        with open(os.path.join(REPO, "nemo", file_name), encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("Name="):
                    return line[len("Name="):].strip()
        self.fail("no Name= line in " + file_name)

    def test_submenu_shows_the_entries_in_the_requested_order(self):
        nemo_menu.install(self.path)
        children = sorted(ours(read(self.path))[0]["children"], key=lambda c: c["position"])
        shown = [None if c["type"] == "separator" else self.action_name(c["uuid"]) for c in children]
        self.assertEqual(shown, self.EXPECTED_ORDER)

    def test_flat_menu_without_the_layout_file_has_the_same_order(self):
        # Nemo sorts unlisted actions by file name; the numbers in the names keep the order.
        files = sorted(n for n in os.listdir(os.path.join(REPO, "nemo")) if n.endswith(".nemo_action"))
        self.assertEqual([self.action_name(n) for n in files], [e for e in self.EXPECTED_ORDER if e])

    def test_other_entries_and_fields_are_preserved(self):
        os.makedirs(os.path.dirname(self.path))
        mine = {"uuid": "other.nemo_action", "type": "action", "position": 0, "user-label": "Mine", "user-icon": None}
        write(self.path, {"toplevel": [mine], "extra": 1})
        nemo_menu.install(self.path)
        data = read(self.path)
        self.assertEqual(data["toplevel"][0], mine)
        self.assertEqual(data["extra"], 1)
        self.assertEqual(len(ours(data)), 1)

    def test_installing_again_does_not_duplicate_the_submenu(self):
        nemo_menu.install(self.path)
        nemo_menu.install(self.path)
        self.assertEqual(len(ours(read(self.path))), 1)

    def test_broken_or_unexpected_files_are_left_untouched(self):
        os.makedirs(os.path.dirname(self.path))
        for content in ("{ not json", '{"toplevel": "nope"}', "[1, 2]"):
            write(self.path, content)
            with self.assertRaises(nemo_menu.NemoMenuError):
                nemo_menu.install(self.path)
            with open(self.path) as handle:
                self.assertEqual(handle.read(), content)

    def test_remove_keeps_other_entries(self):
        os.makedirs(os.path.dirname(self.path))
        mine = {"uuid": "other.nemo_action", "type": "action", "position": 0}
        write(self.path, {"toplevel": [mine]})
        nemo_menu.install(self.path)
        nemo_menu.remove(self.path)
        self.assertEqual(read(self.path)["toplevel"], [mine])

    def test_remove_deletes_a_file_that_only_held_our_submenu(self):
        nemo_menu.install(self.path)
        nemo_menu.remove(self.path)
        self.assertFalse(os.path.exists(self.path))

    def test_remove_without_a_file_or_submenu_is_harmless(self):
        nemo_menu.remove(self.path)
        os.makedirs(os.path.dirname(self.path))
        write(self.path, {"toplevel": []})
        nemo_menu.remove(self.path)
        self.assertEqual(read(self.path), {"toplevel": []})

    def test_default_path_follows_xdg_config_home(self):
        from unittest import mock

        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/somewhere"}):
            self.assertEqual(nemo_menu.layout_path(), "/somewhere/nemo/actions-tree.json")


if __name__ == "__main__":
    unittest.main()
