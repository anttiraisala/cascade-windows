# Plan: cascade-windows

A Windows-style "Cascade windows" command for Linux desktops. The user right-clicks the desktop
background (or presses a shortcut) and the windows of a monitor or workspace are stacked in a neat
cascade, with correct sizes and stacking order.

## Target environments

| Environment | Session | Window manager | Desktop icons drawn by | Approach |
|---|---|---|---|---|
| Linux Mint | X11 | Cinnamon (Muffin) | `nemo-desktop` | X11 tool + Nemo actions |
| Ubuntu Unity 7 (on Ubuntu 24.04) | X11 | Compiz | `nemo-desktop` | X11 tool + Nemo actions |
| Ubuntu 24.04 GNOME | Wayland | gnome-shell (Mutter) | Desktop Icons NG (probably) | GNOME Shell extension (later) |

On Wayland a regular program cannot move other applications' windows, so the GNOME backend has to
live inside the compositor as a GNOME Shell extension. On X11 an ordinary program can do it through
the EWMH protocol.

## Architecture

```
cascade_windows/
  settings.py      load, validate and merge configuration (JSON)
  model.py         Rect, Monitor, WindowInfo (backend independent)
  geometry.py      pure layout math: Anchored, Fit, Percent, Fixed, wrap
  regions.py       monitor -> cascade regions (hook for ultrawide/portrait support)
  cascade.py       scopes, grouping, ordering, applying a plan
  undo.py          save and restore window positions
  backend.py       Backend interface
  x11_backend.py   python-xlib EWMH implementation (Mint, Unity 7)
  gnome_backend.py talks to the GNOME Shell extension over D-Bus (see docs/GNOME.md)
  shell_protocol.py the JSON protocol between the core and the extension
  cli.py           command line entry point
nemo/              desktop right-click menu entries (Nemo actions)
gnome-extension/   GNOME Shell extension (a thin window mover, see docs/GNOME.md)
scripts, install.sh, uninstall.sh
tests/
```

One shared core, one backend per window system, one command (`cascade-windows`) that the menu and
the shortcut both call.

## Behaviour

### Scopes

- **Cascade** (`--scope monitor`): the monitor under the mouse pointer, current workspace.
- **Cascade Workspace** (`--scope workspace`): every monitor of the current workspace, each monitor on its own.
- **Cascade All Workspaces** (`--scope all`): every monitor of every workspace, each on its own.
- **Undo Cascade** (`--undo`) restores the previous positions.

### Which windows are touched

- Minimized windows are skipped.
- Dialogs (window type dialog, or transient windows) are cascaded too, but keep their own size: their top-right
  corner goes to the top-right corner of their cascade position. `skip.dialogs` leaves them alone instead.
- Maximized windows are restored to normal size first.
- Fullscreen windows, "on all workspaces" windows, docks, panels and desktop widgets are skipped.
- Windows that cannot be resized are moved but keep their size; their top-right corner goes to the top-right
  corner of their cascade position.

### Area and margin

The window manager work area is used, so panels and launchers are respected. An additional empty
margin (defaults: top 40, right 60, bottom 20, left 80 px; configurable per side) is kept between the monitor edges and the windows.

### Size modes

- **Anchored** (default): every window has the same bottom-left corner, fixed in the bottom-left
  corner of the usable area. The back window's top-right corner is in the top margin, and each window
  in front of it is one step lower (Step Y) and one step further right (Step X). The front window's
  right edge reaches the right margin. Window k of n (0 = back) has
  `top = area.top + k * stepY`, `right = area.right - (n - 1 - k) * stepX`.
- **Fit**: all windows have the same size, the largest that lets the whole cascade fit in the area.
  Top-left corners step down and right.
- **Percent**: all windows have the same size, a percentage of the area. Top-left corners step down and right.
- **Fixed**: all windows have the same fixed size. Top-left corners step down and right.

### Wrap

When there are too many windows for the minimum size, the cascade restarts on a new round, shifted
slightly (default 12 px) so the rounds can be told apart. With wrap disabled the steps are
compressed instead.

### Order

Back to front by current stacking order (default), by opening order, or by application name.

### Configuration

Everything is in one JSON file, `~/.config/cascade-windows/config.json`, shared by every backend.
See `docs/CONFIGURATION.md`. A settings window may come later.

## Installation

User-level `install.sh` (no root needed): copies the package to `~/.local/share/cascade-windows`,
creates `~/.local/bin/cascade-windows`, installs the Nemo actions and registers `Super+Shift+C`.
A `.deb` package may follow once the behaviour is stable. Flatpak and Snap are not suitable because
their sandboxes block window control.

## Roadmap

1. Core: settings, geometry, planning, undo, tests. (done)
2. X11 backend, CLI, Nemo actions, shortcut, installer for Mint and Unity 7. (this milestone)
3. Settings window.
4. GNOME Shell extension for Ubuntu 24.04 on Wayland (design in `docs/GNOME.md`; the Python backend,
   protocol and a first version of the extension exist and wait for testing in a real GNOME session), and a way to add the desktop right-click entries there.
5. Ultrawide and portrait monitor support (below).
6. `.deb` package.

## Planned: ultrawide and portrait monitors

Ultrawide monitors (twice as wide as tall or wider) would make the Anchored windows unusably wide if
they spanned the whole monitor. The design keeps this in one place: a monitor is turned into one or
more **cascade regions** by `regions.py`, and windows are grouped per region instead of per monitor.
Today the function returns the whole work area. The planned options, global and overridable per
monitor (by output name such as `DP-1`, or by index):

- `split` (**the default for ultrawide monitors**): divide the monitor into virtual screens, each
  cascaded on its own as if it were a normal monitor. A window belongs to the part that contains its
  center. The number of parts is chosen automatically from the aspect ratio (for example a 32:9
  monitor becomes two 16:9 parts, a 48:9 monitor three), and can be set explicitly. The exact
  threshold is decided during implementation.
- `max_aspect` (alternative, selectable in the settings): limit one region to a maximum aspect ratio
  (for example 16:9) and place it with `align` (left, center, right).
- `ignore`: leave a monitor alone.
- Per-monitor `margin`, `step` and `min_size`.
- The auto-detection can be disabled so that an ultrawide monitor behaves like any other monitor.

Portrait (rotated) monitors already work with the same algorithm because sizes are derived from the
usable width and height; per-monitor step and minimum size overrides cover the remaining cases.

## Known risks

- Window managers differ in how they treat `_NET_MOVERESIZE_WINDOW`, frame extents and
  client-side decorations. The X11 backend therefore verifies positions after moving and corrects them.
- Compiz (Unity 7) workspaces are usually viewports of one large virtual desktop, not real EWMH
  desktops. The backend handles both.
- The GNOME Shell extension API changes between versions; the extension will target GNOME 46 first.
- The desktop right-click entry on GNOME depends on how Desktop Icons NG handles the background menu.
