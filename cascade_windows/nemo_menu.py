"""Grouping the Nemo right-click entries into a "Cascade Windows" submenu.

Nemo (the file manager that also draws the desktop on Linux Mint) shows every ``*.nemo_action`` file as
a separate menu entry. A layout file, ``~/.config/nemo/actions-tree.json``, can arrange the entries into
submenus. That file is shared with the user's other actions, so it is only ever edited: our own submenu is
added or removed and everything else is kept exactly as it was.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional

SUBMENU_LABEL = "Cascade Windows"  # also the submenu's identifier in the layout file

# Action files in menu order, None marks a separator. The numbers in the file names make Nemo's own
# alphabetical order (used when the layout file cannot be applied) the same as this order. The menu
# labels are the Name= lines of the action files: Cascade Windows, Cascade Workspace,
# Cascade All Workspaces, Undo Cascade, Cascade Settings...
SUBMENU_ITEMS = [
    "cascade-windows-1-cascade.nemo_action",
    "cascade-windows-2-workspace.nemo_action",
    "cascade-windows-3-all.nemo_action",
    None,
    "cascade-windows-4-undo.nemo_action",
    "cascade-windows-5-settings.nemo_action",
]


class NemoMenuError(RuntimeError):
    """Raised when the layout file cannot be changed safely."""


def layout_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "nemo", "actions-tree.json")


def _is_ours(node) -> bool:
    return isinstance(node, dict) and node.get("type") == "submenu" and node.get("uuid") == SUBMENU_LABEL


def build_submenu() -> dict:
    children: List[dict] = []
    for position, item in enumerate(SUBMENU_ITEMS):
        if item is None:
            children.append({"uuid": "separator", "type": "separator", "position": position})
            continue
        children.append(
            {
                "uuid": item,
                "type": "action",
                "position": position,
                "user-label": None,  # None: show the Name= of the action file
                "user-icon": None,
            }
        )
    return {
        "uuid": SUBMENU_LABEL,
        "type": "submenu",
        "position": 0,
        "user-label": SUBMENU_LABEL,
        "user-icon": None,
        "children": children,
    }


def _read_layout(path: str) -> dict:
    """Read the layout file, or return an empty layout when there is none."""
    if not os.path.exists(path):
        return {"toplevel": []}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as problem:
        raise NemoMenuError(
            "Cannot read %s (%s). It was left untouched; the menu entries stay in a flat list." % (path, problem)
        )
    if not isinstance(data, dict) or not isinstance(data.get("toplevel"), list):
        raise NemoMenuError(
            "%s has an unexpected structure. It was left untouched; the menu entries stay in a flat list." % path
        )
    return data


def _write_layout(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    os.replace(temp, path)


def install(path: Optional[str] = None) -> str:
    """Add (or refresh) the submenu in the layout file. Other entries are preserved."""
    path = path or layout_path()
    data = _read_layout(path)
    entries = [node for node in data["toplevel"] if not _is_ours(node)]
    submenu = build_submenu()
    submenu["position"] = len(entries)
    entries.append(submenu)
    data["toplevel"] = entries
    _write_layout(path, data)
    return "Grouped the right-click entries into a '%s' submenu (%s)" % (SUBMENU_LABEL, path)


def remove(path: Optional[str] = None) -> str:
    """Remove the submenu from the layout file. The file is deleted when nothing else is left in it."""
    path = path or layout_path()
    if not os.path.exists(path):
        return "No Nemo layout file, nothing to remove"
    data = _read_layout(path)
    remaining = [node for node in data["toplevel"] if not _is_ours(node)]
    if len(remaining) == len(data["toplevel"]):
        return "The '%s' submenu was not in the Nemo layout file" % SUBMENU_LABEL
    if not remaining and set(data) == {"toplevel"}:
        os.remove(path)
        return "Removed the Nemo layout file (it only contained the '%s' submenu)" % SUBMENU_LABEL
    data["toplevel"] = remaining
    _write_layout(path, data)
    return "Removed the '%s' submenu from the Nemo layout file" % SUBMENU_LABEL
