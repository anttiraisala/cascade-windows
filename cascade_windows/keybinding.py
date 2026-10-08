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

_UNITY_LIST_SCHEMA = "com.canonical.unity.settings-daemon.plugins.media-keys"
_UNITY_ITEM_SCHEMA = "com.canonical.unity.settings-daemon.plugins.media-keys.custom-keybinding"
_UNITY_ITEM_PATH = "/com/canonical/unity/settings-daemon/plugins/media-keys/custom-keybindings/%s/"


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
    """Check both normal and relocatable schemas (the per-shortcut schema is relocatable)."""
    for listing in ("list-schemas", "list-relocatable-schemas"):
        try:
            if schema in _gsettings(listing).split():
                return True
        except KeybindingError:
            continue
    return False


def _require_schemas(*schemas: str) -> None:
    for schema in schemas:
        if not _schema_exists(schema):
            raise KeybindingError("The %s settings schema is not available" % schema)


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
    if "unity" in desktop:
        return "unity"
    if any(word in desktop for word in ("gnome", "ubuntu")):
        return "gnome"
    return None


def _candidates(flavour: str) -> List[Tuple[str, str, str, str]]:
    """Schema sets to try, best first: (list schema, list key, item schema, item path template).

    Unity 7 keeps its custom shortcuts under com.canonical.unity.settings-daemon; the GNOME location is
    only a fallback there because Unity's own settings daemon ignores it.
    """
    if flavour == "cinnamon":
        return [(_CINNAMON_LIST_SCHEMA, "custom-list", _CINNAMON_ITEM_SCHEMA, _CINNAMON_ITEM_PATH)]
    gnome = (_GNOME_LIST_SCHEMA, "custom-keybindings", _GNOME_ITEM_SCHEMA, _GNOME_ITEM_PATH)
    if flavour == "unity":
        unity = (_UNITY_LIST_SCHEMA, "custom-keybindings", _UNITY_ITEM_SCHEMA, _UNITY_ITEM_PATH)
        return [unity, gnome]
    return [gnome]


def _entry(flavour: str, item_path: str) -> str:
    """What is stored in the list: an id for Cinnamon, a full path otherwise."""
    if flavour == "cinnamon":
        return BINDING_NAME
    return item_path % BINDING_NAME


def _choose(flavour: str) -> Tuple[str, str, str, str]:
    candidates = _candidates(flavour)
    for candidate in candidates:
        if _schema_exists(candidate[0]) and _schema_exists(candidate[2]):
            return candidate
    first = candidates[0]
    _require_schemas(first[0], first[2])  # raises with the name of the missing schema
    return first


def install(command: str, binding: str = DEFAULT_BINDING) -> str:
    """Register the shortcut. Returns a short description of what was done."""
    flavour = detect_flavour()
    if flavour is None:
        raise KeybindingError("Unsupported desktop %r" % os.environ.get("XDG_CURRENT_DESKTOP"))
    list_schema, list_key, item_schema, item_path = _choose(flavour)
    path = item_path % BINDING_NAME
    schema_with_path = "%s:%s" % (item_schema, path)
    _gsettings("set", schema_with_path, "name", "Cascade Windows")
    _gsettings("set", schema_with_path, "command", command)
    if flavour == "cinnamon":
        _gsettings("set", schema_with_path, "binding", repr([binding]))
    else:
        _gsettings("set", schema_with_path, "binding", binding)
    entry = _entry(flavour, item_path)
    entries = _get_list(list_schema, list_key)
    if entry not in entries:
        entries.append(entry)
        _set_list(list_schema, list_key, entries)
    if flavour == "unity" and list_schema != _GNOME_LIST_SCHEMA:
        _remove_from(_GNOME_LIST_SCHEMA, "custom-keybindings", _GNOME_ITEM_SCHEMA, _GNOME_ITEM_PATH, flavour)
    return "Registered %s for %r (%s)" % (binding, command, flavour)


def _remove_from(list_schema: str, list_key: str, item_schema: str, item_path: str, flavour: str) -> None:
    """Remove our entry from one location, ignoring locations that do not exist on this system."""
    if not (_schema_exists(list_schema) and _schema_exists(item_schema)):
        return
    entry = _entry(flavour, item_path)
    entries = _get_list(list_schema, list_key)
    if entry in entries:
        _set_list(list_schema, list_key, [e for e in entries if e != entry])
    _gsettings("reset-recursively", "%s:%s" % (item_schema, item_path % BINDING_NAME))


def remove() -> str:
    flavour = detect_flavour()
    if flavour is None:
        raise KeybindingError("Unsupported desktop %r" % os.environ.get("XDG_CURRENT_DESKTOP"))
    candidates = _candidates(flavour)
    _require_schemas(*[c[0] for c in candidates if _schema_exists(c[0])] or [candidates[0][0]])
    for list_schema, list_key, item_schema, item_path in candidates:
        _remove_from(list_schema, list_key, item_schema, item_path, flavour)
    return "Removed the shortcut"
