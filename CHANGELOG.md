# Changelog

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
