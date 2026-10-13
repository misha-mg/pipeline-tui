"""Every run in one table, grouped by day, with a filter by outcome and a search."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import DataTable, Footer, Header, Input

from .fmt import pr_label, span
from .live import LiveScreen
from .overview import Outcome, outcome
from .run_view import RunScreen
from .runs import Run, load_runs

# Fits "10h 59m".
TIME_WIDTH = 11
# Longer summaries are cut; the run's own screen has the whole ticket.
SUMMARY_WIDTH = 48


def _has(kind: Outcome) -> Callable[[Run], bool]:
    return lambda run: run.verdict is not None and outcome(run.verdict) is kind


# What `f` steps through, in order; the first shows every run.
FILTERS: tuple[tuple[str, Callable[[Run], bool]], ...] = (
    ("all", lambda run: True),
    *((kind.value, _has(kind)) for kind in Outcome if kind is not Outcome.OTHER),
    ("unfinished", lambda run: run.verdict is None),
)


class RunsScreen(LiveScreen):
    BINDINGS = [("escape", "back", "Back"), ("f", "next_filter", "Filter"), ("slash", "search", "Search")]
    DEFAULT_CSS = """
    RunsScreen #search { dock: bottom; display: none; }
    """

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        self._runs: dict[str, Run] = {}
        self._filter = 0
        # The row the cursor was last on, to tell which way it moves when it lands on a day row.
        self._last_row = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(cursor_type="row", zebra_stripes=True)
        yield Input(placeholder="Search a ticket or its summary · Enter keeps it · Esc clears it", id="search")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Ticket")
        table.add_column("Summary", width=SUMMARY_WIDTH)
        table.add_columns("Run", "Started")
        table.add_column("Time", width=TIME_WIDTH)
        table.add_columns("Verdict", "PR")

    def action_refresh(self) -> None:
        table = self.query_one(DataTable)
        # Rows are rebuilt on every refresh; keep the cursor on the run it was on.
        selected = self._selected_key(table)
        runs = load_runs(self._root)
        # A run keeps its number whatever the filter, so a number names one run.
        numbers = {str(run.path): n for n, run in enumerate(runs, start=1)}
        self._runs = {str(run.path): run for run in runs if self._shown(run)}
        table.clear()
        day = None
        for key, run in self._runs.items():
            # Runs come newest first, so a day's runs sit together under one day row.
            if run.started.date() != day:
                day = run.started.date()
                table.add_row(Text(f"{day:%a %d %b}", style="bold"), key=f"day:{day}")
            table.add_row(*_row(run), key=key, label=str(numbers[key]))
        if selected in self._runs:
            table.move_cursor(row=table.get_row_index(selected))
        self.title = " · ".join(["All runs", *self._narrowed_by()])

    def action_next_filter(self) -> None:
        self._filter = (self._filter + 1) % len(FILTERS)
        self.action_refresh()

    def action_search(self) -> None:
        search = self.query_one("#search", Input)
        search.display = True
        search.focus()

    def action_back(self) -> None:
        # Esc undoes the narrowest thing first: the search, then the filter, then the screen.
        search = self.query_one("#search", Input)
        if search.display:
            search.value = ""
            search.display = False
            self.query_one(DataTable).focus()
        elif self._filter:
            self._filter = 0
            self.action_refresh()
        else:
            self.app.pop_screen()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.action_refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query_one(DataTable).focus()

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
        if 0 <= target < table.row_count:
            table.move_cursor(row=target)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key.value in self._runs:
            self.app.push_screen(RunScreen(self._runs[event.row_key.value]))

    def _shown(self, run: Run) -> bool:
        query = self.query_one("#search", Input).value.strip().lower()
        matches = not query or query in run.ticket.lower() or query in (run.summary or "").lower()
        return matches and FILTERS[self._filter][1](run)

    def _narrowed_by(self) -> list[str]:
        query = self.query_one("#search", Input).value.strip()
        parts = [FILTERS[self._filter][0]] if self._filter else []
        return parts + [f"“{query}”"] if query else parts

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
    summary = run.summary or ""
    if len(summary) > SUMMARY_WIDTH:
        summary = summary[: SUMMARY_WIDTH - 1] + "…"
    return run.ticket, summary, str(run.number), f"{run.started:%H:%M}", time, verdict, pr_label(run)
