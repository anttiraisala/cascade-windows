# GNOME Shell support (Ubuntu 24.04, Wayland and X11 sessions)

On Wayland an ordinary program cannot move other applications' windows. Only the compositor can, and in
GNOME the compositor is GNOME Shell. So the GNOME version consists of two small parts that talk to each
other over D-Bus:

```
 Super+Shift+C / panel menu                                        GNOME Shell
          |                                                  +--------------------+
          v                                                  |  extension (JS)    |
  cascade-windows (Python)  --- D-Bus, JSON strings --->     |  - lists windows   |
   - settings, geometry, planning, undo (shared core)        |  - moves windows   |
   - GnomeBackend                                            |  - raises windows  |
                                                             +--------------------+
```

The extension is deliberately thin: it only reports the state of the shell and carries out moves. It makes
no layout decisions. All logic (settings, geometry, planning, undo) stays in the Python core that the X11
version uses too, so every feature and every fix works on every platform, and the layout rules exist in
exactly one place.

The extension's keyboard shortcut and panel menu simply start the same `cascade-windows` command that
Linux Mint and Unity 7 use.

## Parts

| Part | Where | Notes |
|---|---|---|
| `cascade_windows/gnome_backend.py` | Python | `GnomeBackend`, the `Backend` implementation that talks to the extension. |
| `cascade_windows/shell_protocol.py` | Python | Constants and (de)serialization of the protocol below. |
| `cascade_windows/gnome_install.py` | Python | Turns the extension on and off (`enabled-extensions` in gsettings). |
| `gnome-extension/` | JavaScript | The GNOME Shell extension. Priority target: GNOME Shell 46 (Ubuntu 24.04); written to also load on 47 to 50 (Ubuntu 26.04 has 50). |
| `install.sh`, `uninstall.sh` | shell | Choose the right parts for the desktop (see below). |

Files of the extension: `metadata.json`, `extension.js` (enables the service, the shortcuts and the panel menu),
`lib/protocol.js` (pure logic, tested with Node), `lib/windows.js` (the only code that talks to Mutter),
`lib/service.js` (D-Bus), `lib/panel.js` (panel menu), `icons/` (the panel icon: two overlapping windows with title bars, drawn as filled
shapes so that the shell can recolor it), `schemas/` (shortcut settings).

## Choosing the backend

`cascade-windows --backend auto|x11|gnome` (default `auto`):

- `auto` on a desktop whose `XDG_CURRENT_DESKTOP` names GNOME uses the GNOME backend when the extension
  answers on D-Bus. On a GNOME X11 session without the extension it falls back to the X11 backend. On a GNOME
  Wayland session without the extension it stops with a message explaining how to enable the extension.
- `auto` on any other desktop (Cinnamon, Unity 7, ...) uses the X11 backend exactly as before.

The installer applies the same rule (`./install.sh --backend auto|x11|gnome`): on GNOME it copies the extension to
`~/.local/share/gnome-shell/extensions/cascade-windows@anttiraisala.github.io/`, compiles its settings schema and
adds it to the enabled extensions; elsewhere it installs the X11 version (Nemo actions and a gsettings shortcut).
The Python core is installed in both cases. The GNOME install does not need `python3-xlib`. The shortcut
`Super+Shift+C` and the panel menu come from the extension itself, and the menu has the same entries in the same
order as the Nemo submenu: Cascade Windows, Cascade Workspace, Cascade All Workspaces, Undo Cascade,
Cascade Settings...

## The D-Bus protocol

All data is carried in JSON strings, so the protocol does not depend on GVariant type details and is easy to
extend. The Python side uses `busctl --user --json=short`, which ships with systemd on every supported
desktop; it needs no extra Python libraries.

| | |
|---|---|
| Bus (session) | `io.github.anttiraisala.CascadeWindows` |
| Object path | `/io/github/anttiraisala/CascadeWindows` |
| Interface | `io.github.anttiraisala.CascadeWindows` |
| Protocol version | `1` (also in the state, so both sides can refuse a mismatch) |

### `GetState() -> s`

Returns a JSON object:

```json
{
  "protocol": 1,
  "shell_version": "46.0",
  "monitors": [
    {"index": 0, "name": "Virtual-1", "rect": [0, 0, 1920, 1080], "workarea": [0, 27, 1920, 1053]}
  ],
  "workspaces": ["0", "1"],
  "current_workspace": "0",
  "pointer": [960, 540],
  "windows": [
    {
      "id": 1234, "title": "Terminal", "wm_class": "gnome-terminal-server",
      "workspace": "0", "rect": [100, 100, 800, 600], "kind": "normal",
      "minimized": false, "fullscreen": false, "sticky": false, "maximized": false,
      "resizable": true, "stack_index": 3, "open_index": 1
    }
  ]
}
```

- All rectangles are `[x, y, width, height]` in the shell's global logical coordinates (the same space for all
  monitors; with fractional scaling these are logical pixels). Window rectangles are the visible frame
  (`Meta.Window.get_frame_rect()`), not the buffer with its shadows. A monitor `workarea` is the monitor minus
  panels and docks (`Workspace.get_work_area_for_monitor()`).
- Workspace keys are the workspace indexes as strings. A sticky window reports the current workspace.
- `kind` is `normal` for normal windows, `dialog` for dialog and modal dialog windows and for windows that are
  transient for another window, and `other` for everything else (docks, desktop, menus, splash screens, ...).
  Only windows of the kinds `normal` and `dialog` need to be listed, but listing others is harmless.
- `stack_index` is the position in the stacking order, 0 = bottom. `open_index` is the creation order, 0 = oldest.
- `resizable` is false when the window has no resize action or fixed size hints.

### `Apply(s) -> s`

The argument is a JSON array of operations that are executed in order. The result is
`{"ok": true, "errors": []}`, where `errors` lists human readable messages for operations that failed (for
example because the window no longer exists). A failed operation does not stop the following ones.

| Operation | Meaning |
|---|---|
| `{"op": "unmaximize", "id": N}` | Restore a maximized (or edge-tiled) window. The shell applies this asynchronously and refuses to move a window that is still maximized, so the caller reads `GetState` until the window reports `maximized: false` before it places the window. `GnomeBackend` does this. |
| `{"op": "maximize", "id": N, "value": true}` | Maximize (`true`) or restore (`false`) a window. Used by undo. |
| `{"op": "place", "id": N, "rect": [x, y, w, h], "resize": true}` | Make the visible frame of the window `rect`. When `resize` is false the size is not changed and only `x` and `y` are used. |
| `{"op": "raise", "id": N}` | Raise the window to the top of the stacking order. |

The extension never decides *where* a window goes. The Python side computes the final position of the top-left
corner (using the anchor of the cascade slot) and, after the shell has settled, reads the state again and sends
corrections for windows that ended up with a different size than requested (terminals that snap to whole
character cells, windows with minimum sizes). This is the same approach as in the X11 backend.

## Testing

Automatic (`python3 -m unittest discover -s tests`):

- `tests/fake_shell.py` simulates a shell (windows, minimum sizes, size increments, slow restores). Backend tests
  run against it directly and, when `dbus-daemon`, `busctl` and a Python with PyGObject are available, over a
  private session bus with a real D-Bus service, which also covers the transport.
- `gnome-extension/tests/` holds Node tests for the pure parts of the extension (`node --test`), run from the
  Python suite when Node.js is installed. The installer is tested against a throw-away home with a fake gsettings.

The parts that talk to GNOME Shell itself (`lib/windows.js`, `lib/service.js`, `lib/panel.js`, `extension.js`) can
only be tested in a real GNOME session. Test them in a virtual machine:

1. Get the code: `git clone https://github.com/anttiraisala/cascade-windows.git`, `cd cascade-windows`,
   `git checkout gnome-extension`.
2. `./install.sh` (it detects GNOME; use `./install.sh --backend gnome` to force it).
3. Log out and in again. A Wayland shell only looks for new extensions when it starts.
4. Check that it runs:
   - `gnome-extensions info cascade-windows@anttiraisala.github.io` should say `State: ACTIVE`.
   - `~/.local/bin/cascade-windows --backend gnome --diagnose` should list the monitors and windows.
5. Open a few windows and press `Super+Shift+C`, or use the panel menu (the icon at the right end of the top bar).
6. When something does not work, collect: the output of `gnome-shell --version`, of the `--diagnose` command above
   and of `journalctl -b -o cat /usr/bin/gnome-shell | grep -i -E "cascade|error" | tail -50`. The `lg`
   (Looking Glass, Alt+F2) Extensions tab also shows errors of a failed extension.
7. `./uninstall.sh` removes everything (`--purge` also removes the configuration).

## Unverified against a real shell

The first version of the extension was written without access to a GNOME session. These are the places where a
mistake is most likely, so look at them first when something fails:

- `Gio.DBusExportedObject.wrapJSObject` returning `GLib.Variant('(s)', ...)` from the method handlers.
- Maximizing and unmaximizing: `Meta.MaximizeFlags.BOTH` up to GNOME Shell 46, no arguments from 47
  (`ShellWindows._setMaximized`), and reading the state through the `maximized_horizontally` and
  `maximized_vertically` properties (`isMaximized`).
- The `skip_taskbar` property and the stacking order of `global.get_window_actors()`.
- Adding the shortcuts with `Main.wm.addKeybinding` from an `as` setting, and the panel button class.
- Windows tiled to a screen edge count as maximized, so Undo restores them as fully maximized.

## Not in scope (yet)

- The desktop right-click menu. Desktop Icons NG draws the Ubuntu desktop and has its own menu; the first
  version only has the shortcut and a panel menu.
- Ultrawide monitor splitting and per-application rules. They are implemented once in the core and work here
  automatically when they exist.
