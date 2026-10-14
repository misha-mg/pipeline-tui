"""The first screen: the batch going on now, the statistics, the server, and what needs a look."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.color import Color
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Footer, Header, ProgressBar, Static

from .banner import banner
from .batch import Batch, TmuxSession, load_batch
from .chart import day_bars
from .fmt import share, span
from .live import LiveScreen
from .overview import Stats, needs_attention, runs_per_day, ticket_stats
from .pr_screen import PullRequestsScreen
from .run_view import RunScreen
from .runs import Run, load_runs
from .server_block import ServerBlock
from .table import RunsScreen

WEEK = timedelta(days=7)
# The statistics' longest period, and the chart's: the chart draws the same runs the table counts.
MONTH_DAYS = 30
CHART_HEIGHT = 6


class HomeScreen(LiveScreen):
    BINDINGS = [("a", "all_runs", "All runs"), ("p", "pull_requests", "Pull requests")]
    DEFAULT_CSS = """
    HomeScreen #banner { width: 100%; padding: 1 2 0 2; content-align: center top; text-wrap: nowrap; text-overflow: clip; }
    HomeScreen .block { border: round $primary; padding: 1 2; height: auto; }
    /* The statistics block's height: table 15 + gap 1 + chart 9, padding 2, border 2. */
    HomeScreen #top { height: 29; }
    HomeScreen #top > .block { width: 1fr; height: 100%; }
    /* A month of bars, three columns a day. */
    HomeScreen #top > #statistics { width: 2fr; }
    HomeScreen #chart { margin-top: 1; }
    HomeScreen #bottom { height: 1fr; }
    HomeScreen #bottom > .block { width: 1fr; height: 100%; }
    /* Under the blocks above, so their edges line up. */
    HomeScreen #bottom > #attention-block { width: 2fr; }
    HomeScreen #attention { height: 1fr; }
    """

    def __init__(self, root: Path, read_session: Callable[[], TmuxSession | None], mock_url: str) -> None:
        super().__init__()
        self._root = root
        self._read_session = read_session
        self._mock_url = mock_url
        self._attention: dict[str, Run] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="banner")
        with Horizontal(id="top"):
            # A long batch scrolls rather than stretching the row.
            with VerticalScroll(id="now", classes="block"):
                yield Static(id="batch")
                yield ProgressBar(show_eta=False)
            with Vertical(id="statistics", classes="block"):
                yield Static(id="stats")
                yield Static(id="chart")
        with Horizontal(id="bottom"):
            # .pipeline-runs sits in the webui main checkout.
            yield ServerBlock(self._root.parent, self._mock_url, classes="block")
            with Vertical(id="attention-block", classes="block"):
                yield DataTable(id="attention", cursor_type="row")
                yield Static("Nothing needs attention.", id="all-clear")
        yield Footer()

    def on_mount(self) -> None:
        theme = self.app.current_theme
        background, foreground = Color.parse(theme.background), Color.parse(theme.foreground)
        self.query_one("#banner", Static).update(
            banner(Color.parse(theme.primary), Color.parse(theme.accent), background.blend(foreground, 0.45))
        )
        self.query_one("#statistics").border_title = "Statistics"
        self.query_one("#attention-block").border_title = "Needs attention · 7 days"
        self.query_one("#attention", DataTable).add_columns("Ticket", "Run", "Started", "Verdict")

    def action_refresh(self) -> None:
        runs = load_runs(self._root)
        batch = load_batch(self._root, self._read_session(), runs)
        now = datetime.now()
        self._show_batch(batch, now)
        self.query_one("#stats", Static).update(_stats_table(runs, batch, now, self.app.theme_variables["primary"]))
        self.query_one("#chart", Static).update(day_bars(runs_per_day(runs, now.date(), MONTH_DAYS), CHART_HEIGHT))
        self.query_one("#statistics").border_subtitle = f"runs per day · {MONTH_DAYS} days"
        running = {batch.current} if batch and batch.current else set()
        self._show_attention(needs_attention(runs, now - WEEK, running))

    def action_all_runs(self) -> None:
        self.app.push_screen(RunsScreen(self._root))

    def action_pull_requests(self) -> None:
        self.app.push_screen(PullRequestsScreen(self._root, self.app.pull_requests))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.app.push_screen(RunScreen(self._attention[event.row_key.value]))

    def _show_batch(self, batch: Batch | None, now: datetime) -> None:
        block = self.query_one("#now")
        bar = self.query_one(ProgressBar)
        bar.display = batch is not None
        if batch is None:
            block.border_title = "Now"
            self.query_one("#batch", Static).update("No batch has run yet.")
            return
        block.border_title = "Now" if batch.current else "Last batch"
        bar.update(total=len(batch.tickets), progress=len(batch.outcomes))
        self.query_one("#batch", Static).update(_batch_text(batch, now))

    def _show_attention(self, runs: list[Run]) -> None:
        table = self.query_one("#attention", DataTable)
        self._attention = {str(run.path): run for run in runs}
        table.clear()
        for key, run in self._attention.items():
            table.add_row(run.ticket, str(run.number), f"{run.started:%d %b %H:%M}", run.verdict or "unfinished", key=key)
        table.display = bool(runs)
        self.query_one("#all-clear").display = not runs


def _batch_text(batch: Batch, now: datetime) -> Text:
    text = Text()
    text.append(f"Started {batch.started:%d %b %H:%M} · {len(batch.outcomes)} of {len(batch.tickets)} tickets done\n")
    if batch.current:
        since = span(now - batch.current_run.started) if batch.current_run else "preparing"
        text.append("Running  ", style="bold").append(f"{batch.current} · {since}\n")
    for ticket, outcome in batch.outcomes:
        text.append(f"  done   {ticket}  {outcome}\n", style="dim")
    finished = {ticket for ticket, _ in batch.outcomes} | {batch.current}
    waiting = [ticket for ticket in batch.tickets if ticket not in finished]
    if waiting:
        text.append(f"  next   {', '.join(waiting)}\n", style="dim")
    text.rstrip()
    return text


def _stats_table(runs: list[Run], batch: Batch | None, now: datetime, heading: str) -> Table:
    # The last batch's own tickets, from when it started: a manual run alongside it is not its.
    batch_runs = [r for r in runs if batch and r.ticket in batch.tickets]
    columns = [
        ("Last batch", f"{batch.started:%d %b %H:%M}" if batch else "–", ticket_stats(batch_runs, batch.started if batch else None)),
        ("Week", "7 days", ticket_stats(runs, now - WEEK)),
        ("Month", f"{MONTH_DAYS} days", ticket_stats(runs, now - timedelta(days=MONTH_DAYS))),
    ]
    table = Table.grid(padding=(0, 3))
    table.add_column(no_wrap=True)
    for _ in columns:
        table.add_column(justify="right", no_wrap=True)
    table.add_row("", *(Text(title, style="bold") for title, _, _ in columns))
    table.add_row("", *(Text(note, style="dim") for _, note, _ in columns))
    sections: list[tuple[str, list[tuple[str, Callable[[Stats], str]]]]] = [
        (
            "Outcomes · by ticket",
            [
                ("Tickets", lambda s: str(s.tickets)),
                ("Average run", lambda s: span(s.average_run) if s.average_run else "–"),
                ("PR opened", lambda s: share(s.pr_opened)),
                ("Nothing to build", lambda s: share(s.nothing_to_build)),
                ("Blocked", lambda s: share(s.blocked)),
            ],
        ),
        (
            "Quality · by run",
            [
                ("First review passed", lambda s: share(s.first_review_passed)),
                ("Rework rounds", lambda s: f"{s.rework_rounds:.1f}" if s.rework_rounds is not None else "–"),
                ("App-test passed", lambda s: share(s.app_test_passed)),
                ("App-test unverified", lambda s: share(s.app_test_unverified)),
            ],
        ),
    ]
    for n, (title, rows) in enumerate(sections):
        if n:
            table.add_row("")
        table.add_row(Text(title, style=f"bold {heading}"))
        for label, cell in rows:
            table.add_row(f"  {label}", *(cell(stats) for _, _, stats in columns))
    return table
