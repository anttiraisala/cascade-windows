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
Unknown keys are ignored with a warning. Invalid values make the command stop with a clear message.

```json
{
  "margin": { "top": 20, "right": 20, "bottom": 20, "left": 20 },
  "step": { "x": 120, "y": 40 },
  "size_mode": "anchored",
  "percent": { "width": 70, "height": 70 },
  "fixed": { "width": 900, "height": 600 },
  "min_size": { "width": 300, "height": 200 },
  "order": "stacking",
  "wrap": { "enabled": true, "offset": 12 },
  "skip": { "minimized": true, "fullscreen": true, "sticky": true },
  "restore_maximized": true
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
| `restore_maximized` | Restore maximized windows to normal size before cascading. When `false` they are left alone. |

Dialogs and other non-normal windows are never moved.

Windows that resize in steps (for example terminals, which snap to whole character rows) may end up a few
pixels smaller than planned. In `anchored` mode their top edge stays where the cascade wants it, and the
bottom edge falls short by less than one row.
