# cascade-windows

A Windows-style **Cascade windows** command for Linux desktops. Right-click the desktop background
(or press `Super+Shift+C`) and the windows of a monitor are arranged in a tidy cascade, in the right
order and at the right size.

Supported today: **X11** sessions on **Linux Mint (Cinnamon)** and **Ubuntu Unity 7**.
Planned: GNOME Shell extension for Ubuntu 24.04 on Wayland (see `docs/PLAN.md`).

## Features

- Cascade the monitor under the mouse, the whole current workspace, or all workspaces. Always per monitor.
- Several size modes: `anchored` (default), `fit`, `percent`, `fixed`.
- Configurable margin around the monitor edge (default 20 px) and configurable X and Y steps.
- Wraps to a new round when there are too many windows.
- Minimized windows are skipped, dialogs stay where they are, maximized windows are restored first.
- Undo.
- One JSON configuration file. See `docs/CONFIGURATION.md`.

## Install

Requirements: Python 3 and `python3-xlib` (`sudo apt install python3-xlib`).

```sh
git clone https://github.com/anttiraisala/cascade-windows.git
cd cascade-windows
./install.sh
```

The installer works at user level (no root). It installs the command to `~/.local/bin/cascade-windows`,
adds the desktop right-click entries (Nemo) and registers the `Super+Shift+C` shortcut. Options:

```
./install.sh --install-deps      install python3-xlib with apt (asks for sudo)
./install.sh --no-keybinding     do not register the shortcut
./install.sh --no-submenu        show the right-click entries as a flat list instead of one submenu
./install.sh --force             install even on a Wayland session
```

Uninstall with `./uninstall.sh`. Update with `git pull` and `./install.sh`.

Make sure `~/.local/bin` is in your `PATH` (Ubuntu and Mint add it automatically after the first login
once the folder exists).

## Use

| Action | How |
|---|---|
| Cascade this monitor | `Super+Shift+C`, or right-click the desktop and choose **Cascade Windows > Monitor** |
| Cascade all monitors of this workspace | desktop menu: **Cascade Windows > Workspace** |
| Cascade every workspace | desktop menu: **Cascade Windows > All Workspaces** |
| Undo | desktop menu: **Cascade Windows > Undo** |
| Edit settings | desktop menu: **Cascade Windows > Settings...** |

The entries are grouped into one submenu through Nemo's layout file `~/.config/nemo/actions-tree.json`. The
installer only adds its own submenu to that file and keeps everything else in it. If the file cannot be
changed safely (for example it is not valid JSON), the entries are shown as a flat list instead.

Command line:

```
cascade-windows [--scope monitor|workspace|all] [--undo] [--dry-run]
                [--config FILE] [--init-config] [--edit-config] [--diagnose] [--verbose]
```

`cascade-windows --diagnose` prints the detected environment, monitors, work areas and windows. Please
attach its output when reporting a problem.

## Development

```sh
python3 -m unittest discover -s tests -v
```

The core in `cascade_windows/` has no X11 dependency and is covered by unit tests. See `CLAUDE.md`
and `docs/LANGUAGE_RULES.md` for the project conventions (everything in the repository is in English).
