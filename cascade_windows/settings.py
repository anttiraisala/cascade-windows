"""Loading, validating and writing the configuration file."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from typing import Callable, Dict, Optional, Tuple

from .exclusions import ExcludeRule, RuleError, parse_rules, rule_to_dict

COMMENT_KEY = "comment"  # JSON has no comments, so explanations are ordinary keys that are ignored

SIZE_MODES = ("anchored", "fit", "percent", "fixed")
ORDERS = ("stacking", "opening", "name")


class SettingsError(ValueError):
    """Raised when the configuration file cannot be used."""


@dataclass
class Settings:
    margin_top: int = 40
    margin_right: int = 60
    margin_bottom: int = 20
    margin_left: int = 80
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
    skip_dialogs: bool = False
    restore_maximized: bool = True
    workarea_dock_windows: bool = True
    notify_excluded: bool = True
    exclude: Tuple[ExcludeRule, ...] = ()


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
    ("skip", "dialogs"): "skip_dialogs",
    ("restore_maximized",): "restore_maximized",
    ("workarea", "dock_windows"): "workarea_dock_windows",
    ("notify", "excluded"): "notify_excluded",
}

# Configuration path -> attribute, for the list of exclusion rules
_RULE_KEYS: Dict[Tuple[str, ...], str] = {("exclude",): "exclude"}

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
    known_leaves = set(_INT_KEYS) | set(_BOOL_KEYS) | set(_CHOICE_KEYS) | set(_RULE_KEYS)
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


def _is_comment_key(key: str) -> bool:
    return key == COMMENT_KEY or key.startswith(COMMENT_KEY + "_")


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
        elif path in _RULE_KEYS:
            try:
                rules = parse_rules(value, _is_comment_key)
            except RuleError as problem:
                raise SettingsError(str(problem))
            setattr(settings, _RULE_KEYS[path], rules)
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
    for path, attr in _RULE_KEYS.items():
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
        ("workarea",),
        ("notify",),
        ("exclude",),
    ]
    for head in order:
        for path, attr in table.items():
            if path[: len(head)] == head:
                node = result
                for part in path[:-1]:
                    node = node.setdefault(part, {})
                value = getattr(settings, attr)
                if path in _RULE_KEYS:
                    value = [rule_to_dict(rule) for rule in value]
                node[path[-1]] = value
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
    ("skip",): (
        "Windows that are left completely alone when true. dialogs=false: dialog windows are cascaded "
        "too; they keep their own size and their top-right corner goes to the cascade position."
    ),
    ("workarea",): (
        "How the free area of each monitor is found. dock_windows=true: panels and launchers that do "
        "not reserve screen space in the standard way (for example the Unity 7 launcher and top "
        "panel) are treated as obstacles, using their position and size. Set it to false if windows "
        "end up too far from the edges because of an overlay that is wrongly taken for a panel."
    ),
    ("notify",): (
        "excluded=true: show a short desktop notification when nothing was cascaded because the monitor "
        "or workspace is excluded (see 'exclude'). The message is also printed in the terminal."
    ),
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
    ("exclude",): (
        "Monitors and workspaces that the cascade leaves alone: windows there are not moved. A list of "
        "rules, each with 'monitor' and/or 'workspace'; a value can be one item or a list. A monitor is "
        "its name or its number, for example \"HDMI-1\" or 1. A workspace is its number or its position "
        "\"x,y\", numbered left to right and then top to bottom from 0 (\"0,0\" is the top-left "
        "workspace). 'monitor' alone: that monitor on every workspace. 'workspace' alone: every monitor "
        "of that workspace. Both: only that monitor on that workspace. Examples: "
        "{\"monitor\": \"HDMI-1\"}, {\"workspace\": 3}, {\"workspace\": \"1,0\", \"monitor\": [0, 2]}. "
        "Run 'cascade-windows --list-targets' to see the names and numbers. "
        "Run 'cascade-windows --ignore-exclusions' (or press Ctrl+Super+Shift+C) to cascade anyway."
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


def _strip_comments(value):
    if isinstance(value, dict):
        return {
            key: _strip_comments(item)
            for key, item in value.items()
            if not (str(key) == COMMENT_KEY or str(key).startswith(COMMENT_KEY + "_"))
        }
    return value


def _legacy_default_dicts() -> list:
    """Complete files that earlier versions generated, so that they can be recognised.

    Version 0.1.0 wrote steps of 30 and 30; later versions wrote steps of 120 and 40. Both used a
    margin of 20 on every side.
    """
    variants = []
    for step in ({"x": 30, "y": 30}, {"x": 120, "y": 40}):
        legacy = default_settings_dict()
        legacy["margin"] = {"top": 20, "right": 20, "bottom": 20, "left": 20}
        legacy["step"] = dict(step)
        del legacy["skip"]["dialogs"]
        variants.append(legacy)
    return variants


def remove_legacy_default_config(path: Optional[str] = None) -> bool:
    """Delete a configuration file that is an untouched copy of defaults of an earlier version.

    Such a file only freezes outdated defaults. Files the user has changed are never touched.
    Comment keys are ignored in the comparison. Returns True when a file was removed.
    """
    path = path or config_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    data = _strip_comments(data)
    data.setdefault("workarea", {"dock_windows": True})  # files from before this section existed
    data.setdefault("notify", {"excluded": True})  # files from before exclusions existed
    data.setdefault("exclude", [])
    if isinstance(data.get("skip"), dict) and data["skip"].get("dialogs") is False:
        del data["skip"]["dialogs"]  # files from before this setting existed
    if data not in _legacy_default_dicts():
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


def reset_config(path: Optional[str] = None) -> str:
    """Replace the configuration file with a fresh documented default file.

    An existing file is first copied to ``config.json.bak`` (an older backup is replaced).
    Returns a message describing what was done.
    """
    path = path or config_path()
    backup = None
    if os.path.exists(path):
        backup = path + ".bak"
        os.replace(path, backup)
    write_default_config(path)
    if backup:
        return "Wrote a fresh configuration file %s (the previous one was saved as %s)" % (path, backup)
    return "Wrote a fresh configuration file " + path


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
    | set(_RULE_KEYS.values())
    | {attr for attr, _c in _CHOICE_KEYS.values()}
), "every Settings field must be reachable from the configuration file"
