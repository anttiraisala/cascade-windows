"""A report about the desktop environment, for finding out why something does not work or whether a new desktop is supported."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
from typing import Callable, List, Optional

from . import __version__, keybinding

TOOLS = ("gsettings", "busctl", "glib-compile-schemas", "nemo", "notify-send", "xdg-open", "gnome-shell")


def desktop_family(environ) -> str:
    """cinnamon, unity, gnome or other, from XDG_CURRENT_DESKTOP (for example "ubuntu:GNOME")."""
    parts = [part.strip().lower() for part in environ.get("XDG_CURRENT_DESKTOP", "").split(":")]
    if any("cinnamon" in part for part in parts):
        return "cinnamon"
    if any("unity" in part for part in parts):
        return "unity"
    if "gnome" in parts:
        return "gnome"
    return "other"


def planned_install(family: str, session_type: str) -> str:
    """What ./install.sh --backend auto does on this desktop."""
    if family == "gnome":
        return "GNOME Shell extension (shortcut and panel menu come from the extension)"
    if session_type == "wayland":
        return "nothing useful: this is a Wayland session and only GNOME is supported there"
    return "X11 version (Nemo right-click menu and a gsettings shortcut)"


def _run_text(command: List[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (result.stdout or result.stderr).strip().splitlines()[0] if (result.stdout or result.stderr).strip() else ""


def build_report(
    environ=None,
    which: Callable[[str], Optional[str]] = shutil.which,
    run: Callable[[List[str]], str] = _run_text,
    has_module: Callable[[str], bool] = lambda name: importlib.util.find_spec(name) is not None,
    schema_exists: Callable[[str], bool] = keybinding._schema_exists,
) -> List[str]:
    """Return the report lines. Every outside dependency can be replaced, so it is testable."""
    environ = os.environ if environ is None else environ
    family = desktop_family(environ)
    session_type = environ.get("XDG_SESSION_TYPE", "").lower()
    lines = ["cascade-windows %s, Python %s" % (__version__, platform.python_version())]
    release = _os_release()
    if release:
        lines.append("system: " + release)
    for name in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "DESKTOP_SESSION", "DISPLAY", "WAYLAND_DISPLAY"):
        lines.append("%s = %s" % (name, environ.get(name) or "(not set)"))
    lines.append("desktop family: %s" % family)
    lines.append("planned install: %s" % planned_install(family, session_type))
    lines.append("python-xlib: %s" % ("available" if has_module("Xlib") else "missing (needed by the X11 version)"))
    for tool in TOOLS:
        lines.append("%s: %s" % (tool, which(tool) or "not found"))
    if which("nemo"):
        lines.append("nemo version: %s" % (run(["nemo", "--version"]) or "unknown"))
    if which("gnome-shell"):
        lines.append("gnome-shell version: %s" % (run(["gnome-shell", "--version"]) or "unknown"))
    if which("gsettings") and family != "other":
        flavour = {"cinnamon": "cinnamon", "unity": "unity", "gnome": "gnome"}[family]
        for list_schema, _key, item_schema, _path in keybinding._candidates(flavour):
            lines.append("shortcut schema %s: %s" % (
                list_schema, "present" if schema_exists(list_schema) and schema_exists(item_schema) else "missing"))
    return lines


def _os_release() -> str:
    try:
        with open("/etc/os-release", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""
