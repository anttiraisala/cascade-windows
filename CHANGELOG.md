# Changelog

## Unreleased

- Excluding monitors and workspaces: the `exclude` setting lists rules (`monitor` and/or `workspace`) for places the cascade leaves alone. Monitors are given by name or number, workspaces by number or by grid position `x,y`, numbered left to right and top to bottom from 0.
- `--list-targets` prints the workspace numbers and positions and the monitor names and numbers; `--diagnose` includes the same and warns about rules that match nothing.
- A short notification (and a message in the terminal) tells why nothing happened when the monitor is excluded; `notify.excluded` turns the notification off.
- `--ignore-exclusions` and a second shortcut, `Ctrl+Super+Shift+C`, cascade the monitor under the pointer even if it is excluded. The installer registers both shortcuts (Cinnamon, Unity 7) and the GNOME extension provides both; `--keybinding-id` selects which one `--install-keybinding` registers and `--remove-keybinding` removes both.
- GNOME protocol: the state optionally carries `workspace_columns`.

## 0.3.0

- GNOME Shell support (Ubuntu 24.04 with GNOME Shell 46 and Ubuntu 26.04 with GNOME Shell 50, Wayland and X11 sessions) through a thin GNOME Shell extension. All layout logic stays in the shared Python core. See `docs/GNOME.md`.
- The extension adds the `Super+Shift+C` shortcut and a panel menu with the same entries as the desktop menu.
- `./install.sh` and `cascade-windows` detect the desktop and choose the right version automatically (`--backend auto|x11|gnome` overrides it).
- Dialogs and windows that cannot be resized are cascaded too: the top-right corner goes to the cascade position and the size is kept (`skip.dialogs` turns this off).
- New options: `--reset-config`, `--enable-gnome-extension`, `--disable-gnome-extension`, `--environment-report`; the installer and uninstaller gained `--reset-config` and `--purge`.
- The right-click entries are grouped into a Nemo submenu where Nemo supports it.
- Ubuntu Unity 7: the shortcut is registered under `com.canonical.unity.settings-daemon`, where Unity reads its custom shortcuts. The desktop menu stays a flat list there (Nemo limitation).

## 0.2.0

- X11 version for Linux Mint (Cinnamon) and Ubuntu Unity 7: per monitor and per workspace cascade, `Super+Shift+C`, desktop right-click menu, undo and a JSON configuration file.
