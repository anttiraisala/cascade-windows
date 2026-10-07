"""Turning the GNOME Shell extension on and off (the list of enabled extensions in gsettings).

The installer copies the extension files; this module edits ``org.gnome.shell enabled-extensions``. The
running shell watches that setting, so on an X11 session the extension starts at once; on Wayland the shell
must be restarted by logging out and in because it only scans for new extensions when it starts.
"""

from __future__ import annotations

import ast
import subprocess
from typing import Callable, List

from .backend import BackendError

EXTENSION_UUID = "cascade-windows@anttiraisala.github.io"
SCHEMA = "org.gnome.shell"
ENABLED_KEY = "enabled-extensions"
DISABLED_KEY = "disabled-extensions"


def parse_list(text: str) -> List[str]:
    """Parse the gsettings text of a string array, for example ``['a', 'b']`` or ``@as []``."""
    text = text.strip()
    if text.startswith("@as"):
        text = text[3:].strip()
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        raise BackendError("Cannot understand the gsettings value %r" % text)
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise BackendError("Cannot understand the gsettings value %r" % text)
    return list(value)


def format_list(items: List[str]) -> str:
    return "[" + ", ".join("'" + item.replace("\\", "\\\\").replace("'", "\\'") + "'" for item in items) + "]"


def _gsettings(runner: Callable, *arguments: str) -> str:
    try:
        done = runner(["gsettings", *arguments], capture_output=True, text=True)
    except FileNotFoundError:
        raise BackendError("The 'gsettings' command was not found.")
    if done.returncode != 0:
        raise BackendError("gsettings %s failed: %s" % (" ".join(arguments), done.stderr.strip()))
    return done.stdout


def _change(runner: Callable, key: str, edit: Callable[[List[str]], List[str]]) -> bool:
    current = parse_list(_gsettings(runner, "get", SCHEMA, key))
    updated = edit(list(current))
    if updated == current:
        return False
    _gsettings(runner, "set", SCHEMA, key, format_list(updated))
    return True


def enable(runner: Callable = subprocess.run) -> str:
    _change(runner, DISABLED_KEY, lambda items: [i for i in items if i != EXTENSION_UUID])
    changed = _change(runner, ENABLED_KEY, lambda items: items if EXTENSION_UUID in items else items + [EXTENSION_UUID])
    return ("Enabled the GNOME Shell extension %s" if changed else "The GNOME Shell extension %s was already enabled") % EXTENSION_UUID


def disable(runner: Callable = subprocess.run) -> str:
    changed = _change(runner, ENABLED_KEY, lambda items: [i for i in items if i != EXTENSION_UUID])
    return ("Disabled the GNOME Shell extension %s" if changed else "The GNOME Shell extension %s was not enabled") % EXTENSION_UUID
