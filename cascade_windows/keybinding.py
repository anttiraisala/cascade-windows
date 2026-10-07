"""Registering the keyboard shortcut in Cinnamon and in GNOME-style settings daemons (Unity 7)."""

from __future__ import annotations

import ast
import os
import subprocess
from typing import List, Optional, Tuple

BINDING_NAME = "cascade-windows"
DEFAULT_BINDING = "<Super><Shift>c"

_CINNAMON_LIST_SCHEMA = "org.cinnamon.desktop.keybindings"
_CINNAMON_ITEM_SCHEMA = "org.cinnamon.desktop.keybindings.custom-keybinding"
_CINNAMON_ITEM_PATH = "/org/cinnamon/desktop/keybindings/custom-keybindings/%s/"

_GNOME_LIST_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
_GNOME_ITEM_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
_GNOME_ITEM_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/%s/"


class KeybindingError(RuntimeError):
    """Raised when the shortcut cannot be registered automatically."""


def _gsettings(*args: str) -> str:
    try:
        result = subprocess.run(
            ["gsettings"] + list(args), capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        raise KeybindingError("The gsettings command is not installed")
    if result.returncode != 0:
        raise KeybindingError(result.stderr.strip() or "gsettings failed")
    return result.stdout.strip()


def _schema_exists(schema: str) -> bool:
    try:
        return schema in _gsettings("list-schemas").split()
    except KeybindingError:
        return False


def _get_list(schema: str, key: str) -> List[str]:
    text = _gsettings("get", schema, key)
    if text.startswith("@as"):
        text = text[3:].strip()
    return list(ast.literal_eval(text))


def _set_list(schema: str, key: str, values: List[str]) -> None:
    _gsettings("set", schema, key, repr(values))


def detect_flavour() -> Optional[str]:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "cinnamon" in desktop:
        return "cinnamon"
    if any(word in desktop for word in ("unity", "gnome", "ubuntu")):
        return "gnome"
    return None


def _schemas(flavour: str) -> Tuple[str, str, str, str]:
    if flavour == "cinnamon":
        return _CINNAMON_LIST_SCHEMA, "custom-list", _CINNAMON_ITEM_SCHEMA, _CINNAMON_ITEM_PATH
    return _GNOME_LIST_SCHEMA, "custom-keybindings", _GNOME_ITEM_SCHEMA, _GNOME_ITEM_PATH


def _entry(flavour: str) -> str:
    """What is stored in the list: an id for Cinnamon, a full path for GNOME."""
    if flavour == "cinnamon":
        return BINDING_NAME
    return _GNOME_ITEM_PATH % BINDING_NAME


def install(command: str, binding: str = DEFAULT_BINDING) -> str:
    """Register the shortcut. Returns a short description of what was done."""
    flavour = detect_flavour()
    if flavour is None:
        raise KeybindingError("Unsupported desktop %r" % os.environ.get("XDG_CURRENT_DESKTOP"))
    list_schema, list_key, item_schema, item_path = _schemas(flavour)
    if not _schema_exists(list_schema) or not _schema_exists(item_schema):
        raise KeybindingError("The %s settings schema is not available" % list_schema)
    path = item_path % BINDING_NAME
    schema_with_path = "%s:%s" % (item_schema, path)
    _gsettings("set", schema_with_path, "name", "Cascade Windows")
    _gsettings("set", schema_with_path, "command", command)
    if flavour == "cinnamon":
        _gsettings("set", schema_with_path, "binding", repr([binding]))
    else:
        _gsettings("set", schema_with_path, "binding", binding)
    entries = _get_list(list_schema, list_key)
    if _entry(flavour) not in entries:
        entries.append(_entry(flavour))
        _set_list(list_schema, list_key, entries)
    return "Registered %s for %r (%s)" % (binding, command, flavour)


def remove() -> str:
    flavour = detect_flavour()
    if flavour is None:
        raise KeybindingError("Unsupported desktop %r" % os.environ.get("XDG_CURRENT_DESKTOP"))
    list_schema, list_key, item_schema, item_path = _schemas(flavour)
    if not _schema_exists(list_schema):
        raise KeybindingError("The %s settings schema is not available" % list_schema)
    entries = [e for e in _get_list(list_schema, list_key) if e != _entry(flavour)]
    _set_list(list_schema, list_key, entries)
    _gsettings("reset-recursively", "%s:%s" % (item_schema, item_path % BINDING_NAME))
    return "Removed the shortcut"
