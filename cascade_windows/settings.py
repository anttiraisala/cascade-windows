"""Loading, validating and writing the configuration file."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from typing import Callable, Dict, Optional, Tuple

COMMENT_KEY = "comment"  # JSON has no comments, so explanations are ordinary keys that are ignored

SIZE_MODES = ("anchored", "fit", "percent", "fixed")
ORDERS = ("stacking", "opening", "name")


class SettingsError(ValueError):
    """Raised when the configuration file cannot be used."""


@dataclass
class Settings:
    margin_top: int = 20
    margin_right: int = 20
    margin_bottom: int = 20
    margin_left: int = 20
    step_x: int = 120
    step_y: int = 40
    size_mode: str = "anchored"
    percent_width: int = 70
    percent_height: int = 70
    fixed_width: int = 900
    fixed_height: int = 600
    min_width: int = 300
    min_height: int = 200
    order: str = "stacking"
    wrap_enabled: bool = True
    wrap_offset: int = 12
    skip_minimized: bool = True
    skip_fullscreen: bool = True
    skip_sticky: bool = True
    restore_maximized: bool = True


# Configuration path -> (attribute, minimum, maximum)
_INT_KEYS: Dict[Tuple[str, ...], Tuple[str, int, int]] = {
    ("margin", "top"): ("margin_top", 0, 10000),
    ("margin", "right"): ("margin_right", 0, 10000),
    ("margin", "bottom"): ("margin_bottom", 0, 10000),
    ("margin", "left"): ("margin_left", 0, 10000),
    ("step", "x"): ("step_x", 0, 10000),
    ("step", "y"): ("step_y", 0, 10000),
    ("percent", "width"): ("percent_width", 1, 100),
    ("percent", "height"): ("percent_height", 1, 100),
    ("fixed", "width"): ("fixed_width", 50, 100000),
    ("fixed", "height"): ("fixed_height", 50, 100000),
    ("min_size", "width"): ("min_width", 1, 100000),
    ("min_size", "height"): ("min_height", 1, 100000),
    ("wrap", "offset"): ("wrap_offset", 0, 1000),
}

_BOOL_KEYS: Dict[Tuple[str, ...], str] = {
    ("wrap", "enabled"): "wrap_enabled",
    ("skip", "minimized"): "skip_minimized",
    ("skip", "fullscreen"): "skip_fullscreen",
    ("skip", "sticky"): "skip_sticky",
    ("restore_maximized",): "restore_maximized",
}

_CHOICE_KEYS: Dict[Tuple[str, ...], Tuple[str, Tuple[str, ...]]] = {
    ("size_mode",): ("size_mode", SIZE_MODES),
    ("order",): ("order", ORDERS),
}


def config_dir() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "cascade-windows")


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def state_dir() -> str:
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "state"
    )
    return os.path.join(base, "cascade-windows")


def _dotted(path: Tuple[str, ...]) -> str:
    return ".".join(path)


def _walk(data: dict, prefix: Tuple[str, ...], warn: Callable[[str], None]):
    """Yield (path, value) for every leaf, warning about unknown keys."""
    known_leaves = set(_INT_KEYS) | set(_BOOL_KEYS) | set(_CHOICE_KEYS)
    known_prefixes = {path[:i] for path in known_leaves for i in range(1, len(path))}
    for key, value in data.items():
        path = prefix + (str(key),)
        if str(key) == COMMENT_KEY or str(key).startswith(COMMENT_KEY + "_"):
            continue  # free text for humans ("comment", "comment_<name>"), allowed at every level
        if path in known_leaves:
            yield path, value
        elif path in known_prefixes:
            if not isinstance(value, dict):
                raise SettingsError("'%s' must be an object" % _dotted(path))
            for item in _walk(value, path, warn):
                yield item
        else:
            warn("Ignoring unknown setting '%s'" % _dotted(path))


def settings_from_dict(data: dict, warn: Optional[Callable[[str], None]] = None) -> Settings:
    """Build Settings from a (possibly partial) nested dictionary."""
    if warn is None:
        warn = lambda message: None  # noqa: E731
    if not isinstance(data, dict):
        raise SettingsError("The configuration file must contain a JSON object")
    settings = Settings()
    for path, value in _walk(data, (), warn):
        if path in _INT_KEYS:
            attr, low, high = _INT_KEYS[path]
            if isinstance(value, bool) or not isinstance(value, int):
                raise SettingsError("'%s' must be a whole number" % _dotted(path))
            if not low <= value <= high:
                raise SettingsError(
                    "'%s' must be between %d and %d" % (_dotted(path), low, high)
                )
            setattr(settings, attr, value)
        elif path in _BOOL_KEYS:
            if not isinstance(value, bool):
                raise SettingsError("'%s' must be true or false" % _dotted(path))
            setattr(settings, _BOOL_KEYS[path], value)
        else:
            attr, choices = _CHOICE_KEYS[path]
            if value not in choices:
                raise SettingsError(
                    "'%s' must be one of: %s" % (_dotted(path), ", ".join(choices))
                )
            setattr(settings, attr, value)
    return settings


def settings_to_dict(settings: Settings) -> dict:
    """Return the nested dictionary form used in the configuration file."""
    result: dict = {}
    table = {}
    for path, (attr, _low, _high) in _INT_KEYS.items():
        table[path] = attr
    for path, attr in _BOOL_KEYS.items():
        table[path] = attr
    for path, (attr, _choices) in _CHOICE_KEYS.items():
        table[path] = attr
    # Keep a stable, readable order that matches docs/CONFIGURATION.md.
    order = [
        ("margin",),
        ("step",),
        ("size_mode",),
        ("percent",),
        ("fixed",),
        ("min_size",),
        ("order",),
        ("wrap",),
        ("skip",),
        ("restore_maximized",),
    ]
    for head in order:
        for path, attr in table.items():
            if path[: len(head)] == head:
                node = result
                for part in path[:-1]:
                    node = node.setdefault(part, {})
                node[path[-1]] = getattr(settings, attr)
    return result


def default_settings_dict() -> dict:
    return settings_to_dict(Settings())


_COMMENTS = {
    (): (
        "cascade-windows configuration. Every key is optional: a missing key uses its built-in "
        "default, so you may delete anything you do not want to change. All sizes are in pixels. "
        "Keys named 'comment' are ignored by the program; edit or delete them freely. "
        "Run 'cascade-windows --show-config' to see the settings that are in effect."
    ),
    ("margin",): (
        "Empty space kept between the screen work area (the screen minus panels and docks) and the "
        "cascaded windows, per side."
    ),
    ("step",): (
        "Offset between neighbouring windows in the cascade. x = horizontal step, y = vertical step. "
        "They are independent of each other. 0 means no offset in that direction."
    ),
    ("size_mode",): None,
    ("percent",): "Window size for size_mode 'percent', as a percentage (1-100) of the usable area.",
    ("fixed",): "Window size for size_mode 'fixed', in pixels. It is limited to the usable area.",
    ("min_size",): (
        "The smallest size a window may get in the 'anchored' and 'fit' modes. When the cascade "
        "would make windows smaller, see 'wrap'."
    ),
    ("order",): None,
    ("wrap",): (
        "What to do when there are too many windows for one cascade. enabled=true: start a new round "
        "of the cascade, moved 'offset' pixels right and down. enabled=false: squeeze the steps "
        "instead, so everything stays in one cascade."
    ),
    ("skip",): "Windows that are left completely alone when true.",
}

_COMMENT_AFTER = {
    ("size_mode",): (
        "How big the windows become. 'anchored': every window keeps the same bottom-left corner in "
        "the bottom-left of the usable area; the back window reaches the top margin and the front "
        "window reaches the right margin, so windows get different sizes. 'fit': all windows have "
        "the same size, the largest one that lets the whole cascade fit; top-left corners step "
        "down and right (the classic cascade). 'percent': all windows have the same size, a "
        "percentage of the usable area (see 'percent'). 'fixed': all windows have the same size in "
        "pixels (see 'fixed')."
    ),
    ("restore_maximized",): (
        "true: a maximized window is restored to its normal size and then cascaded like the others. "
        "false: maximized windows are left alone."
    ),
    ("order",): (
        "Which window goes to the back. 'stacking': keep the current front-to-back order. "
        "'opening': the order the windows were opened, oldest at the back. 'name': by application "
        "name, then window title."
    ),
}


def documented_default_dict() -> dict:
    """The default settings with explanatory 'comment' entries, as written by --edit-config."""
    plain = default_settings_dict()
    documented: dict = {COMMENT_KEY: _COMMENTS[()]}
    for key, value in plain.items():
        comment = _COMMENTS.get((key,))
        if isinstance(value, dict):
            documented[key] = {COMMENT_KEY: comment}
            documented[key].update(value)
        else:
            if (key,) in _COMMENT_AFTER:
                documented[COMMENT_KEY + "_" + key] = _COMMENT_AFTER[(key,)]
            documented[key] = value
    return documented


def _legacy_default_dict() -> dict:
    """The defaults that version 0.1.0 wrote to the configuration file (steps were 30 and 30)."""
    legacy = default_settings_dict()
    legacy["step"] = {"x": 30, "y": 30}
    return legacy


def remove_legacy_default_config(path: Optional[str] = None) -> bool:
    """Delete a configuration file that is an untouched copy of the old defaults.

    Such a file only freezes outdated defaults. Files the user has changed are never touched.
    Returns True when a file was removed.
    """
    path = path or config_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return False
    if data != _legacy_default_dict():
        return False
    os.remove(path)
    return True


def load_settings(
    path: Optional[str] = None, warn: Optional[Callable[[str], None]] = None
) -> Settings:
    """Load settings from ``path`` (default location when None). Missing file means defaults."""
    path = path or config_path()
    if not os.path.exists(path):
        return Settings()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as error:
        raise SettingsError(
            "%s is not valid JSON (line %d, column %d): %s"
            % (path, error.lineno, error.colno, error.msg)
        )
    except OSError as error:
        raise SettingsError("Cannot read %s: %s" % (path, error))
    return settings_from_dict(data, warn)


def write_default_config(path: Optional[str] = None, overwrite: bool = False) -> str:
    """Write a configuration file containing all defaults and return its path."""
    path = path or config_path()
    if os.path.exists(path) and not overwrite:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(documented_default_dict(), handle, indent=2)
        handle.write("\n")
    return path


assert {f.name for f in fields(Settings)} == (
    {attr for attr, _l, _h in _INT_KEYS.values()}
    | set(_BOOL_KEYS.values())
    | {attr for attr, _c in _CHOICE_KEYS.values()}
), "every Settings field must be reachable from the configuration file"
