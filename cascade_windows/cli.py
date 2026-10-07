"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from typing import List, Optional

from . import __version__, gnome_install, keybinding, nemo_menu, undo
from .backend import Backend, BackendError
from .cascade import (
    SCOPE_MONITOR,
    SCOPES,
    apply_plan,
    plan_for_backend,
    restore_positions,
)
from .settings import (
    SettingsError,
    config_path,
    load_settings,
    remove_legacy_default_config,
    reset_config,
    settings_to_dict,
    write_default_config,
)

log = logging.getLogger("cascade_windows")

BACKEND_CHOICES = ("auto", "x11", "gnome")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cascade-windows",
        description="Arrange windows in a Windows-style cascade.",
        epilog="Scopes: monitor = the monitor under the mouse pointer; "
        "workspace = every monitor of the current workspace; all = every monitor of every workspace.",
    )
    parser.add_argument("--scope", choices=SCOPES, default=SCOPE_MONITOR, help="what to cascade (default: monitor)")
    parser.add_argument("--undo", action="store_true", help="restore the positions from before the last cascade")
    parser.add_argument("--dry-run", action="store_true", help="show what would be done without moving anything")
    parser.add_argument("--config", metavar="FILE", help="use this configuration file")
    parser.add_argument("--init-config", action="store_true", help="write a configuration file with all defaults")
    parser.add_argument("--reset-config", action="store_true", help="replace the configuration file with a fresh one holding all defaults (the old one is saved as config.json.bak)")
    parser.add_argument("--show-config", action="store_true", help="print the configuration file path and the settings in effect")
    parser.add_argument("--migrate-config", action="store_true", help="remove an untouched configuration file written by an older version")
    parser.add_argument("--edit-config", action="store_true", help="open the configuration file in the default editor")
    parser.add_argument("--diagnose", action="store_true", help="print information about the environment and windows")
    parser.add_argument("--install-keybinding", metavar="COMMAND", help="register the keyboard shortcut for COMMAND")
    parser.add_argument("--binding", default=keybinding.DEFAULT_BINDING, help="shortcut used with --install-keybinding (default: %(default)s)")
    parser.add_argument("--remove-keybinding", action="store_true", help="remove the keyboard shortcut")
    parser.add_argument("--install-nemo-menu", action="store_true", help="group the desktop right-click entries into a 'Cascade Windows' submenu")
    parser.add_argument("--remove-nemo-menu", action="store_true", help="remove the submenu and show the entries as a flat list again")
    parser.add_argument("--enable-gnome-extension", action="store_true", help="turn the GNOME Shell extension on (the installer does this)")
    parser.add_argument("--disable-gnome-extension", action="store_true", help="turn the GNOME Shell extension off")
    parser.add_argument("--backend", choices=BACKEND_CHOICES, default="auto",
                        help="window system access: x11, gnome (GNOME Shell extension) or auto (default)")
    parser.add_argument("--allow-wayland", action="store_true", help="run even on a Wayland session (only X11 windows can be moved)")
    parser.add_argument("-v", "--verbose", action="store_true", help="print debug information")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    return parser


def _notify(title: str, message: str) -> None:
    """Show a desktop notification when not started from a terminal (best effort)."""
    if sys.stderr.isatty() or shutil.which("notify-send") is None:
        return
    try:
        subprocess.run(["notify-send", "-i", "dialog-error", title, message], check=False)
    except OSError:
        pass


def desktop_is_gnome(environ=None) -> bool:
    """True when XDG_CURRENT_DESKTOP names GNOME (for example "ubuntu:GNOME")."""
    environ = os.environ if environ is None else environ
    return any(part.strip().upper() == "GNOME" for part in environ.get("XDG_CURRENT_DESKTOP", "").split(":"))


def create_backend(allow_wayland: bool = False, settings=None, kind: str = "auto", environ=None,
                   gnome_backend=None) -> Backend:
    """Pick the window system backend.

    ``auto`` uses the GNOME Shell extension on GNOME desktops when it answers, and the X11 backend
    everywhere else, so Linux Mint and Unity 7 behave exactly as before.
    """
    environ = os.environ if environ is None else environ
    if kind not in BACKEND_CHOICES:
        raise BackendError("Unknown backend %r" % kind)
    if kind == "gnome" or (kind == "auto" and desktop_is_gnome(environ)):
        from .gnome_backend import GnomeBackend, extension_missing_message

        backend = gnome_backend or GnomeBackend()
        if kind == "gnome" or backend.transport.is_available():
            return backend
        if environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            raise BackendError(extension_missing_message())
    if environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" and not allow_wayland:
        raise BackendError(
            "This is a Wayland session without the GNOME Shell extension. The X11 backend cannot move "
            "Wayland windows. On GNOME, install and enable the extension (./install.sh); other Wayland "
            "desktops are not supported."
        )
    from .x11_backend import X11Backend

    return X11Backend(use_dock_windows=True if settings is None else settings.workarea_dock_windows)


def _run(args: argparse.Namespace) -> int:
    path = args.config or config_path()
    if args.init_config:
        print(write_default_config(path))
        return 0
    if args.reset_config:
        print(reset_config(path))
        return 0
    if args.edit_config:
        write_default_config(path)
        opener = shutil.which("xdg-open")
        if opener is None:
            print(path)
            return 0
        subprocess.Popen([opener, path])
        return 0
    if args.install_nemo_menu:
        print(nemo_menu.install())
        return 0
    if args.remove_nemo_menu:
        print(nemo_menu.remove())
        return 0
    if args.enable_gnome_extension:
        print(gnome_install.enable())
        return 0
    if args.disable_gnome_extension:
        print(gnome_install.disable())
        return 0
    if args.migrate_config:
        if remove_legacy_default_config(path):
            print("Removed the unmodified configuration file written by an earlier version: " + path)
        return 0
    if args.show_config:
        settings = load_settings(args.config, warn=lambda message: print("warning: " + message, file=sys.stderr))
        print("configuration file: %s%s" % (path, "" if os.path.exists(path) else " (not found, using defaults)"))
        print(json.dumps(settings_to_dict(settings), indent=2))
        return 0
    if args.install_keybinding:
        print(keybinding.install(args.install_keybinding, args.binding))
        return 0
    if args.remove_keybinding:
        print(keybinding.remove())
        return 0

    settings = load_settings(args.config, warn=lambda message: print("warning: " + message, file=sys.stderr))
    backend = create_backend(args.allow_wayland, settings, args.backend)

    if args.diagnose:
        print("cascade-windows %s" % __version__)
        print("configuration: %s%s" % (path, "" if os.path.exists(path) else " (not found, using defaults)"))
        for line in backend.diagnose():
            print(line)
        return 0

    if args.undo:
        entries = undo.load_entries()
        if not entries:
            print("Nothing to undo.")
            return 0
        restored = restore_positions(backend, entries)
        print("Restored %d window(s)." % restored)
        return 0

    plan = plan_for_backend(backend, settings, args.scope)
    if args.dry_run:
        for line in plan.describe() or ["No windows to cascade."]:
            print(line)
        return 0
    if not plan.moves:
        print("No windows to cascade.")
        return 0
    undo.save_entries(undo.entries_from_plan(plan))
    apply_plan(backend, plan, settings)
    print("Cascaded %d window(s)." % len(plan.moves))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    try:
        return _run(args)
    except (BackendError, SettingsError, keybinding.KeybindingError, nemo_menu.NemoMenuError) as problem:
        print("cascade-windows: %s" % problem, file=sys.stderr)
        if not (args.install_keybinding or args.remove_keybinding
                or args.install_nemo_menu or args.remove_nemo_menu
                or args.enable_gnome_extension or args.disable_gnome_extension):
            _notify("Cascade Windows", str(problem))
        return 1
    except KeyboardInterrupt:
        return 130
