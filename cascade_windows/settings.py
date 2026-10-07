"""Loading, validating and writing the configuration file."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from typing import Callable, Dict, Optional, Tuple

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
        json.dump(default_settings_dict(), handle, indent=2)
        handle.write("\n")
    return path


assert {f.name for f in fields(Settings)} == (
    {attr for attr, _l, _h in _INT_KEYS.values()}
    | set(_BOOL_KEYS.values())
    | {attr for attr, _c in _CHOICE_KEYS.values()}
), "every Settings field must be reachable from the configuration file"
