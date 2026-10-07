# cascade-windows

Windows-style "Cascade windows" for Linux desktops. See `README.md` and `docs/PLAN.md`.

The maintainer chats in Finnish, but everything in this repository is written in English.
The full rules are imported below and always apply:

@docs/LANGUAGE_RULES.md

## Working notes

- Default branch is `master`.
- Pure logic (settings, geometry, planning, undo) lives in `cascade_windows/` and has no X11 dependency. Keep it that way so it stays unit-testable.
- Window-system access is isolated behind the `Backend` interface in `cascade_windows/backend.py`. The X11 implementation is `x11_backend.py`. The GNOME backend (`gnome_backend.py`, protocol in `shell_protocol.py`) talks to a thin GNOME Shell extension over D-Bus; see `docs/GNOME.md`. All layout logic stays in the shared core.
- GNOME work happens on the `gnome-extension` branch. The X11 behaviour (Linux Mint, Unity 7) must not change; the full test suite must stay green.
- Run the tests with `python3 -m unittest discover -s tests -v`.
