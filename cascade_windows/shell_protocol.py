"""The protocol between the Python core and the GNOME Shell extension (see docs/GNOME.md).

Pure data handling: no D-Bus and no GNOME imports, so it can be tested anywhere.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .model import KIND_DIALOG, KIND_NORMAL, KIND_OTHER, Monitor, Rect, WindowInfo

PROTOCOL_VERSION = 1
BUS_NAME = "io.github.anttiraisala.CascadeWindows"
OBJECT_PATH = "/io/github/anttiraisala/CascadeWindows"
INTERFACE = "io.github.anttiraisala.CascadeWindows"
METHOD_GET_STATE = "GetState"
METHOD_APPLY = "Apply"

_KINDS = (KIND_NORMAL, KIND_DIALOG, KIND_OTHER)


class ProtocolError(ValueError):
    """The other side sent something this version cannot understand."""


@dataclass(frozen=True)
class ShellState:
    monitors: List[Monitor]
    workspaces: List[str]
    current_workspace: str
    pointer: Tuple[int, int]
    windows: List[WindowInfo]
    shell_version: str = ""


def _rect(value: Any, what: str) -> Rect:
    try:
        return Rect.from_list(value)
    except (TypeError, ValueError):
        raise ProtocolError("%s is not a [x, y, width, height] list: %r" % (what, value))


def _window(data: Dict[str, Any]) -> WindowInfo:
    try:
        kind = data.get("kind", KIND_NORMAL)
        if kind not in _KINDS:
            kind = KIND_OTHER
        return WindowInfo(
            id=int(data["id"]),
            title=str(data.get("title", "")),
            wm_class=str(data.get("wm_class", "")),
            workspace=str(data["workspace"]),
            rect=_rect(data["rect"], "window rect"),
            kind=kind,
            minimized=bool(data.get("minimized", False)),
            fullscreen=bool(data.get("fullscreen", False)),
            sticky=bool(data.get("sticky", False)),
            maximized=bool(data.get("maximized", False)),
            resizable=bool(data.get("resizable", True)),
            stack_index=int(data.get("stack_index", 0)),
            open_index=int(data.get("open_index", 0)),
        )
    except KeyError as missing:
        raise ProtocolError("window without %s: %r" % (missing, data))


def parse_state(text: str) -> ShellState:
    """Turn the JSON returned by GetState into a ShellState."""
    try:
        data = json.loads(text)
    except ValueError as problem:
        raise ProtocolError("GetState did not return valid JSON: %s" % problem)
    if not isinstance(data, dict):
        raise ProtocolError("GetState did not return a JSON object")
    version = data.get("protocol")
    if version != PROTOCOL_VERSION:
        raise ProtocolError(
            "The GNOME Shell extension speaks protocol %r but this program speaks protocol %d. "
            "Update both to the same version (run ./install.sh again and log out and in)."
            % (version, PROTOCOL_VERSION)
        )
    try:
        monitors = [
            Monitor(
                int(m["index"]),
                str(m.get("name", "monitor %s" % m["index"])),
                _rect(m["rect"], "monitor rect"),
                _rect(m.get("workarea", m["rect"]), "monitor workarea"),
            )
            for m in data["monitors"]
        ]
        pointer = data.get("pointer", [0, 0])
        return ShellState(
            monitors=monitors,
            workspaces=[str(w) for w in data["workspaces"]],
            current_workspace=str(data["current_workspace"]),
            pointer=(int(pointer[0]), int(pointer[1])),
            windows=[_window(w) for w in data.get("windows", [])],
            shell_version=str(data.get("shell_version", "")),
        )
    except (KeyError, TypeError, IndexError, ValueError) as problem:
        if isinstance(problem, ProtocolError):
            raise
        raise ProtocolError("GetState result is incomplete: %r" % (problem,))


# Operation builders ------------------------------------------------------------------------------


def op_unmaximize(window_id: int) -> Dict[str, Any]:
    return {"op": "unmaximize", "id": window_id}


def op_maximize(window_id: int, value: bool) -> Dict[str, Any]:
    return {"op": "maximize", "id": window_id, "value": bool(value)}


def op_place(window_id: int, rect: Rect, resize: bool) -> Dict[str, Any]:
    return {"op": "place", "id": window_id, "rect": rect.to_list(), "resize": bool(resize)}


def op_raise(window_id: int) -> Dict[str, Any]:
    return {"op": "raise", "id": window_id}


def encode_operations(operations: List[Dict[str, Any]]) -> str:
    return json.dumps(operations, separators=(",", ":"))


def parse_apply_result(text: str) -> List[str]:
    """Return the error messages of an Apply call (empty when everything worked)."""
    try:
        data = json.loads(text)
    except ValueError as problem:
        raise ProtocolError("Apply did not return valid JSON: %s" % problem)
    if not isinstance(data, dict):
        raise ProtocolError("Apply did not return a JSON object")
    return [str(e) for e in data.get("errors", [])]
