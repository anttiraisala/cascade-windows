# cascade-windows

Windows-style "Cascade windows" for Linux desktops. See `README.md` and `docs/PLAN.md`.

The maintainer chats in Finnish, but everything in this repository is written in English.
The full rules are imported below and always apply:

@docs/LANGUAGE_RULES.md

## Working notes

- Default branch is `master`.
- Pure logic (settings, geometry, planning, undo) lives in `cascade_windows/` and has no X11 dependency. Keep it that way so it stays unit-testable.
- Window-system access is isolated behind the `Backend` interface in `cascade_windows/backend.py`. The X11 implementation is `x11_backend.py`; a GNOME Shell extension (Wayland) is planned as a second backend.
- Run the tests with `python3 -m unittest discover -s tests -v`.
