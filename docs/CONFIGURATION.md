# Configuration

Settings live in `~/.config/cascade-windows/config.json` (or `$XDG_CONFIG_HOME/cascade-windows/config.json`).
The file does not exist until you create it, and then the built-in defaults below are used. Every key is
optional; missing keys use the defaults. Run `cascade-windows --edit-config` to create the file (with all
defaults) and open it in your editor, and `cascade-windows --show-config` to see the file path and the
settings that are actually in effect. Note that a file written by an old version keeps its old values,
because the file always wins over the built-in defaults; delete it, or the keys you do not want to pin,
to get the current defaults.
JSON has no comments, so explanations are ordinary keys named `comment` (one per section) or
`comment_<setting>` (above a single setting, for example `comment_size_mode`). The program ignores them at
every level, so you can edit or delete them freely. `--edit-config` writes a new file with all of them; a
file you created earlier keeps what it has.
To start over with the current defaults, run `cascade-windows --reset-config` (or `./install.sh --reset-config`); the old
file is saved as `config.json.bak`. `./uninstall.sh --purge` deletes the file and its backup.
Unknown keys are ignored with a warning. Invalid values make the command stop with a clear message.

```json
{
  "margin": { "top": 40, "right": 60, "bottom": 20, "left": 80 },
  "step": { "x": 120, "y": 40 },
  "size_mode": "anchored",
  "percent": { "width": 70, "height": 70 },
  "fixed": { "width": 900, "height": 600 },
  "min_size": { "width": 300, "height": 200 },
  "order": "stacking",
  "wrap": { "enabled": true, "offset": 12 },
  "skip": { "minimized": true, "fullscreen": true, "sticky": true, "dialogs": false },
  "restore_maximized": true,
  "workarea": { "dock_windows": true },
  "notify": { "excluded": true },
  "exclude": []
}
```

| Key | Meaning |
|---|---|
| `margin.*` | Empty space in pixels between the window manager work area and the cascaded windows. |
| `step.x`, `step.y` | Horizontal and vertical offset in pixels between neighbouring windows in the cascade. |
| `size_mode` | `anchored`, `fit`, `percent` or `fixed`. See `docs/PLAN.md`. |
| `percent.*` | Window size as a percentage (1-100) of the usable area, used by `percent`. |
| `fixed.*` | Window size in pixels, used by `fixed`. |
| `min_size.*` | Smallest size used by `anchored` and `fit` before the cascade wraps (or compresses its steps). |
| `order` | `stacking` (current back-to-front order), `opening` (order the windows were opened) or `name` (application name, then title). |
| `wrap.enabled` | Start a new round when the windows do not fit. When `false` the steps are compressed instead. |
| `wrap.offset` | Pixel shift of each additional round. |
| `skip.minimized` | Do not touch minimized windows. |
| `skip.fullscreen` | Do not touch fullscreen windows. |
| `skip.sticky` | Do not touch windows that are shown on all workspaces. |
| `skip.dialogs` | Do not touch dialog windows. When `false` (the default) dialogs are cascaded too: they keep their own size and their top-right corner goes to the top-right corner of their cascade position. |
| `workarea.dock_windows` | Treat panels and launchers that do not reserve screen space in the standard way (for example the Unity 7 launcher and top panel) as obstacles, using their position and size. Turn off if an overlay is wrongly taken for a panel. |
| `restore_maximized` | Restore maximized windows to normal size before cascading. When `false` they are left alone. |
| `exclude` | A list of rules for monitors and workspaces that are never cascaded. See below. Empty by default. |
| `notify.excluded` | Show a short desktop notification when a cascade did nothing because the monitor or workspace is excluded. The message is always printed in the terminal too. |

## Excluding monitors and workspaces

`exclude` is a list of rules. Each rule is an object with `monitor` and/or `workspace`; a value is one item or a
list of items.

```json
"exclude": [
  { "monitor": "HDMI-1" },
  { "workspace": 3 },
  { "workspace": "1,0", "monitor": [0, 2] }
]
```

| Rule | Excludes |
|---|---|
| `{"monitor": X}` | monitor X on every workspace |
| `{"workspace": W}` | every monitor of workspace W |
| `{"workspace": W, "monitor": X}` | only monitor X on workspace W |

All keys of a rule must match for the rule to apply; a monitor on a workspace is left alone when any rule applies.
Windows there are not moved, and they do not count as windows to cascade. Other monitors are cascaded normally.
An empty rule, an unknown key or a wrong kind of value stops the command with a message that names the rule
(for example `exclude[1]`). A comment key (`comment`, `comment_...`) is allowed in a rule.

- A **monitor** is its name, compared without regard to case (for example `"HDMI-1"` on X11), or its number
  (index) as `cascade-windows --list-targets` prints it. On GNOME the names are `Monitor 0`, `Monitor 1`, ...
- A **workspace** is its number or its grid position `"x,y"` (a string). Workspaces are numbered in reading
  order, left to right and then top to bottom, starting from 0; `"0,0"` is the top-left workspace. In a 2 x 2
  grid the numbers are 0 and 1 on the first row and 2 and 3 on the second (`"0,1"` is number 2). A single row
  of workspaces has positions `"0,0"`, `"1,0"`, `"2,0"`, ... A single column has `"0,0"`, `"0,1"`, ...
- A rule that matches nothing right now (an unplugged monitor, a workspace that does not exist) is ignored;
  `--list-targets` and `--diagnose` warn about it.

`cascade-windows --ignore-exclusions` (shortcut `Ctrl+Super+Shift+C`) cascades the monitor under the pointer
even if it is excluded.

Windows of other special types (docks, panels, desktop widgets, splash screens) are never moved.

Windows that resize in steps (for example terminals, which snap to whole character rows) may end up a few
pixels smaller than planned. In `anchored` mode their top edge stays where the cascade wants it, and the
bottom edge falls short by less than one row.
