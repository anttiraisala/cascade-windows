# Configuration

Settings live in `~/.config/cascade-windows/config.json` (or `$XDG_CONFIG_HOME/cascade-windows/config.json`).
Every key is optional; missing keys use the defaults below. Run `cascade-windows --init-config` to write
a file containing all defaults, or `cascade-windows --edit-config` to open it in your editor.
Unknown keys are ignored with a warning. Invalid values make the command stop with a clear message.

```json
{
  "margin": { "top": 20, "right": 20, "bottom": 20, "left": 20 },
  "step": { "x": 30, "y": 30 },
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
