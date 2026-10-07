"""Remembering window positions so the last cascade can be undone."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional

from .cascade import Plan
from .model import Rect
from .settings import state_dir


@dataclass(frozen=True)
class UndoEntry:
    window_id: int
    workspace: str
    rect: Rect
    maximized: bool


def undo_path() -> str:
    return os.path.join(state_dir(), "undo.json")


def entries_from_plan(plan: Plan) -> List[UndoEntry]:
    """Record the current position of every window the plan is about to move."""
    return [
        UndoEntry(m.window.id, m.window.workspace, m.window.rect, m.window.maximized)
        for m in plan.moves
    ]


def save_entries(entries: List[UndoEntry], path: Optional[str] = None) -> None:
    path = path or undo_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = [
        {
            "window": e.window_id,
            "workspace": e.workspace,
            "rect": e.rect.to_list(),
            "maximized": e.maximized,
        }
        for e in entries
    ]
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.replace(temp, path)


def load_entries(path: Optional[str] = None) -> List[UndoEntry]:
    path = path or undo_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [
            UndoEntry(
                int(item["window"]),
                str(item["workspace"]),
                Rect.from_list(item["rect"]),
                bool(item["maximized"]),
            )
            for item in data
        ]
    except (OSError, ValueError, KeyError, TypeError):
        return []
