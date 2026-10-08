# cascade-windows

A Windows-style **Cascade windows** command for Linux desktops. Right-click the desktop background
(or press `Super+Shift+C`) and the windows of a monitor are arranged in a tidy cascade, in the right
order and at the right size.

Supported today: **X11** sessions on **Linux Mint (Cinnamon)** and **Ubuntu Unity 7**.
Planned: GNOME Shell extension for Ubuntu 24.04 on Wayland (see `docs/PLAN.md`).

## Features

- Cascade the monitor under the mouse, the whole current workspace, or all workspaces. Always per monitor.
- Several size modes: `anchored` (default), `fit`, `percent`, `fixed`.
- Configurable margin around the monitor edge (defaults: 40 px top, 60 px right, 20 px bottom, 80 px left) and configurable X and Y steps.
- Wraps to a new round when there are too many windows.
- Minimized windows are skipped, dialogs and fixed-size windows are moved but keep their size (top-right corner at the cascade position), maximized windows are restored first.
- Undo.
- One JSON configuration file. See `docs/CONFIGURATION.md`.

## Install

Requirements: Python 3 and `python3-xlib` (`sudo apt install python3-xlib`).

```sh
git clone https://github.com/anttiraisala/cascade-windows.git
cd cascade-windows
./install.sh
```

On GNOME (Ubuntu 24.04 and newer) the installer installs a GNOME Shell extension instead of the Nemo menu and
shortcut; see `docs/GNOME.md` (under development, on the `gnome-extension` branch). The installer works at user level (no root). It installs the command to `~/.local/bin/cascade-windows`,
adds the desktop right-click entries (Nemo) and registers the `Super+Shift+C` shortcut. Options:

```
./install.sh --backend gnome|x11   choose the version explicitly (default: GNOME desktops get the GNOME Shell
                                 extension, everything else the X11 version)
./install.sh --install-deps      install python3-xlib with apt (asks for sudo); only the X11 version needs it
./install.sh --no-keybinding     do not register the shortcut
./install.sh --no-submenu        show the right-click entries as a flat list instead of one submenu
./install.sh --reset-config      replace the configuration file with a fresh one holding all defaults
                                 (the old file is kept as config.json.bak)
./install.sh --force             install even on a Wayland session
./install.sh --help              list the options
```

Update with `git pull` and `./install.sh`. A normal install never overwrites your configuration file.

Uninstall:

```
./uninstall.sh                   remove the program, the shortcut and the menu entries; keep the configuration
./uninstall.sh --purge           also delete the configuration file (and its backup) and the undo state
./uninstall.sh --remove-config   same as --purge
./uninstall.sh --help            list the options
```

Make sure `~/.local/bin` is in your `PATH` (Ubuntu and Mint add it automatically after the first login
once the folder exists).

## Use

| Action | How |
|---|---|
| Cascade this monitor | `Super+Shift+C`, or right-click the desktop and choose **Cascade Windows** |
| Cascade all monitors of this workspace | desktop menu: **Cascade Workspace** |
| Cascade every workspace | desktop menu: **Cascade All Workspaces** |
| Undo | desktop menu: **Undo Cascade** |
| Edit settings | desktop menu: **Cascade Settings...** |

The entries are grouped into one submenu through Nemo's layout file `~/.config/nemo/actions-tree.json`. The
installer only adds its own submenu to that file and keeps everything else in it. If the file cannot be
changed safely (for example it is not valid JSON), the entries are shown as a flat list instead.

Known limitations on Ubuntu Unity 7 (tested with Nemo 6.0.2 on Ubuntu 24.04):

- The desktop menu shows the entries as a flat list, in the correct order, instead of one submenu, even
  after restarting the desktop with `pkill -9 nemo-desktop` (the session starts it again). Everything works the
  same; only the grouping is missing.
- The `Super+Shift+C` shortcut is registered in gsettings, but Unity's Custom Shortcuts list does not show it
  and the key does not trigger. Use the right-click menu or run `cascade-windows` from a terminal.

Command line:

```
cascade-windows [--scope monitor|workspace|all] [--undo] [--dry-run]
                [--config FILE] [--init-config] [--edit-config] [--reset-config] [--show-config]
                [--diagnose] [--verbose]
```

| Option | Meaning |
|---|---|
| `--scope monitor\|workspace\|all` | What to cascade: the monitor under the pointer (default), every monitor of this workspace, or everything. |
| `--undo` | Restore the positions from before the last cascade. |
| `--dry-run` | Show what would be done without moving anything. |
| `--config FILE` | Use this configuration file instead of the default one. |
| `--init-config` | Write a configuration file with all defaults, unless one exists. |
| `--edit-config` | Create the configuration file if missing and open it in the default editor. |
| `--reset-config` | Replace the configuration file with a fresh one holding all defaults. The old file is saved as `config.json.bak`. |
| `--show-config` | Print the configuration file path and the settings in effect. |
| `--migrate-config` | Remove an untouched configuration file written by an older version (the installer does this). |
| `--diagnose` | Print the environment, monitors, work areas and windows. |
| `--install-keybinding COMMAND`, `--binding KEYS`, `--remove-keybinding` | Register or remove the keyboard shortcut (default `<Super><Shift>c`). |
| `--install-nemo-menu`, `--remove-nemo-menu` | Group the desktop right-click entries into a submenu, or back into a flat list. |
| `--backend auto\|x11\|gnome` | Window system access. `auto` (default) uses the GNOME Shell extension on GNOME desktops and X11 elsewhere. The GNOME extension is under development; see `docs/GNOME.md`. |
| `--allow-wayland` | Run on a Wayland session (only X11 windows can be moved). |
| `-v`, `--verbose` | Print debug information. |
| `--version` | Print the version. |

`cascade-windows --diagnose` prints the detected environment, monitors, work areas and windows. Please
attach its output when reporting a problem.

## Development

```sh
python3 -m unittest discover -s tests -v
```

This also runs the Node tests of the GNOME Shell extension (`node --test gnome-extension/tests/*.test.js`) when Node.js
is installed. The core in `cascade_windows/` has no X11 dependency and is covered by unit tests. See `CLAUDE.md`
and `docs/LANGUAGE_RULES.md` for the project conventions (everything in the repository is in English).
