"""Every run in one table, grouped by day."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import DataTable, Footer, Header

from .fmt import pr_label, span
from .live import LiveScreen
from .run_view import RunScreen
from .runs import Run, load_runs

# Fits "10h 59m".
TIME_WIDTH = 11


class RunsScreen(LiveScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        self._runs: dict[str, Run] = {}
        # The row the cursor was last on, to tell which way it moves when it lands on a day row.
        self._last_row = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "All runs"
        table = self.query_one(DataTable)
        table.add_columns("Ticket", "Run", "Started")
        table.add_column("Time", width=TIME_WIDTH)
        table.add_columns("Verdict", "PR")

    def action_refresh(self) -> None:
        table = self.query_one(DataTable)
        # Rows are rebuilt on every refresh; keep the cursor on the run it was on.
        selected = self._selected_key(table)
        self._runs = {str(run.path): run for run in load_runs(self._root)}
        table.clear()
        day = None
        for number, (key, run) in enumerate(self._runs.items(), start=1):
            # Runs come newest first, so a day's runs sit together under one day row.
            if run.started.date() != day:
                day = run.started.date()
                table.add_row(Text(f"{day:%a %d %b}", style="bold"), key=f"day:{day}")
            table.add_row(*_row(run), key=key, label=str(number))
        if selected in self._runs:
            table.move_cursor(row=table.get_row_index(selected))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        # A day row is a heading, not a run: step over it the way the cursor was moving. The table
        # may have moved on since the event was sent, so look at where the cursor is now.
        table = event.data_table
        row = table.cursor_row
        if self._selected_key(table) in self._runs:
            self._last_row = row
            return
        step = 1 if row >= self._last_row else -1
        target = row + step if 0 <= row + step < table.row_count else row - step
        table.move_cursor(row=target)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key.value in self._runs:
            self.app.push_screen(RunScreen(self._runs[event.row_key.value]))

    @staticmethod
    def _selected_key(table: DataTable) -> str | None:
        if not table.row_count:
            return None
        return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value


def _row(run: Run) -> tuple[str, ...]:
    if run.duration is None:
        time, verdict = span(datetime.now() - run.started), "unfinished"
    else:
        time, verdict = span(run.duration), run.verdict or ""
    return run.ticket, str(run.number), f"{run.started:%H:%M}", time, verdict, pr_label(run)
