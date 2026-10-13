"""The home screen's server block: checks the server off the UI thread and shows what it found."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.content import Content
from textual.widgets import Static

from .fmt import size
from .server import ServerStatus, server_status, worktrees_size

STATUS_SECONDS = 60
# Measuring the worktrees reads every file in them.
SIZE_SECONDS = 600
# Less free disk than this is shown as a warning.
LOW_DISK = 0.10


class ServerBlock(Static):
    def __init__(self, main: Path, mock_url: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._main = main
        self._mock_url = mock_url
        self._server_status: ServerStatus | None = None
        self._measured_size: int | None = None

    def on_mount(self) -> None:
        self.border_title = "Server"
        self._redraw()
        self._check()
        self._measure()
        self.set_interval(STATUS_SECONDS, self._check)
        self.set_interval(SIZE_SECONDS, self._measure)

    @work(thread=True, exclusive=True, group="server-status")
    def _check(self) -> None:
        status = server_status(self._main, self._mock_url)
        self.app.call_from_thread(self._set_status, status)

    @work(thread=True, exclusive=True, group="worktrees-size")
    def _measure(self) -> None:
        measured = worktrees_size(self._main)
        self.app.call_from_thread(self._set_size, measured)

    def _set_status(self, status: ServerStatus) -> None:
        self._server_status = status
        self._redraw()

    def _set_size(self, measured: int) -> None:
        self._measured_size = measured
        self._redraw()

    def _redraw(self) -> None:
        status = self._server_status
        if status is None:
            self.update("Checking…")
            return
        low = status.disk_free < status.disk_total * LOW_DISK
        disk = f"{size(status.disk_free)} free of {size(status.disk_total)}"
        worktrees = f"{status.worktrees} · {status.with_node_modules} with node_modules · "
        worktrees += size(self._measured_size) if self._measured_size is not None else "measuring…"
        mock = (status.mock_board, "") if status.mock_board else ("not answering", "$error")
        self.update(
            Content("\n").join(
                [
                    Content.assemble("Disk       ", (disk, "$warning" if low else "")),
                    Content.assemble("Worktrees  ", worktrees),
                    Content.assemble("Mock       ", mock),
                ]
            )
        )
