"""The interface every window system backend implements."""

from __future__ import annotations

from typing import List, Tuple

from .model import Monitor, Rect, WindowInfo


class BackendError(RuntimeError):
    """Raised when the window system cannot be used."""


class Backend:
    """Window system access.

    Coordinates are relative to the top-left corner of one workspace cell (see model.py).
    Workspace keys are opaque strings chosen by the backend.
    """

    name = "abstract"

    def monitors(self) -> List[Monitor]:
        raise NotImplementedError

    def pointer_position(self) -> Tuple[int, int]:
        """Mouse pointer position in the current workspace."""
        raise NotImplementedError

    def current_workspace(self) -> str:
        raise NotImplementedError

    def workspaces(self) -> List[str]:
        """All workspace keys, in their natural order."""
        raise NotImplementedError

    def workspace_columns(self) -> int:
        """How many workspaces are in one row of the workspace grid; 0 when unknown (one row)."""
        return 0

    def windows(self) -> List[WindowInfo]:
        raise NotImplementedError

    def unmaximize(self, window: WindowInfo) -> None:
        raise NotImplementedError

    def set_maximized(self, window: WindowInfo, maximized: bool) -> None:
        raise NotImplementedError

    def place(
        self,
        window: WindowInfo,
        workspace: str,
        rect: Rect,
        anchor: str,
        resize: bool,
    ) -> None:
        """Move (and, when ``resize``, resize) the window so its visible rectangle is ``rect``.

        When the window manager forces a different size, the corner named by ``anchor``
        ("top-left", "bottom-left" or "top-right") of ``rect`` must stay where it is.
        """
        raise NotImplementedError

    def raise_window(self, window: WindowInfo) -> None:
        raise NotImplementedError

    def commit(self) -> None:
        """Flush requests and correct placements the window manager adjusted."""
        raise NotImplementedError

    def sync(self) -> None:
        """Wait until the window manager has processed the requests sent so far."""
        raise NotImplementedError

    def diagnose(self) -> List[str]:
        """Lines of information for ``--diagnose``."""
        return []
