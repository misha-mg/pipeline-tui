"""The runs' pull requests after the run: merged as they were, merged with changes, open, declined."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.widgets import DataTable, Footer, Header, Static

from .bitbucket import Fate, PullRequest, PullRequests
from .fmt import age, pr_label, share
from .live import LiveScreen
from .overview import Share
from .run_view import RunScreen
from .runs import Run, load_runs

SUMMARY_WIDTH = 40
NO_TOKEN = "Bitbucket is not connected: set BITBUCKET_TOKEN, or put the token in ~/.config/pipeline-tui/bitbucket-token."


class PullRequestsScreen(LiveScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]
    DEFAULT_CSS = """
    PullRequestsScreen #fates { padding: 1 2; border-bottom: solid $primary; height: auto; }
    PullRequestsScreen #note { padding: 0 2; color: $text-muted; height: auto; }
    """

    def __init__(self, root, pull_requests: PullRequests) -> None:
        super().__init__()
        self._root = root
        self._pull_requests = pull_requests
        # Each pull request by the latest run that names it.
        self._runs: dict[str, Run] = {}
        self._errors: list[str] = []
        # The first fetch takes longer than the app's refresh interval; one at a time.
        self._fetching = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="fates")
        yield Static(id="note")
        yield DataTable(cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Pull requests"
        table = self.query_one(DataTable)
        table.add_columns("Ticket")
        table.add_column("Summary", width=SUMMARY_WIDTH)
        table.add_columns("PR", "State", "Opened", "Open for", "Approvals", "Pushes after")

    def action_refresh(self) -> None:
        self._runs = {}
        for run in load_runs(self._root):
            if run.pr and run.pr not in self._runs:
                self._runs[run.pr] = run
        self._show()
        if self._pull_requests.connected and not self._fetching:
            self._fetching = True
            self._fetch(list(self._runs))

    @work(thread=True)
    def _fetch(self, urls: list[str]) -> None:
        errors = self._pull_requests.refresh(urls, datetime.now())
        self.app.call_from_thread(self._fetched, errors)

    def _fetched(self, errors: list[str]) -> None:
        self._fetching = False
        self._errors = errors
        self._show()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.app.push_screen(RunScreen(self._runs[event.row_key.value]))

    def _show(self) -> None:
        now = datetime.now()
        known = {url: pr for url in self._runs if (pr := self._pull_requests.get(url))}
        self.query_one("#fates", Static).update(_fates(list(known.values()), len(self._runs)))
        note = [] if self._pull_requests.connected else [NO_TOKEN]
        if self._errors:
            note.append(f"{len(self._errors)} could not be read; the first: {self._errors[0]}")
        self.query_one("#note", Static).update("\n".join(note))
        self.query_one("#note").display = bool(note)

        table = self.query_one(DataTable)
        selected = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value if table.row_count else None
        table.clear()
        for url, run in self._runs.items():
            table.add_row(*_row(run, known.get(url), now, self.app.theme_variables), key=url)
        if selected in self._runs:
            table.move_cursor(row=table.get_row_index(selected))


def _fates(prs: list[PullRequest], total: int) -> Table:
    fates = Counter(pr.fate for pr in prs)
    grid = Table.grid(padding=(0, 3))
    grid.add_column(no_wrap=True)
    grid.add_column(justify="right")
    for fate in (Fate.MERGED_AS_IS, Fate.MERGED_CHANGED, Fate.OPEN, Fate.DECLINED):
        grid.add_row(fate.value.capitalize(), share(Share(fates[fate], len(prs))))
    grid.add_row("", "")
    grid.add_row("Changes requested", share(Share(sum(pr.changes_requested > 0 for pr in prs), len(prs))))
    if len(prs) < total:
        grid.add_row(Text("Not fetched yet", style="dim"), Text(str(total - len(prs)), style="dim"))
    return grid


# Theme variables: the table draws with Rich, which takes their values, not their names.
FATE_COLORS = {
    Fate.MERGED_AS_IS: "success",
    Fate.MERGED_CHANGED: "primary",
    Fate.OPEN: "foreground",
    Fate.DECLINED: "error",
}


def _row(run: Run, pr: PullRequest | None, now: datetime, colors: dict[str, str]) -> tuple[str | Text, ...]:
    summary = run.summary or ""
    if len(summary) > SUMMARY_WIDTH:
        summary = summary[: SUMMARY_WIDTH - 1] + "…"
    if pr is None:
        return run.ticket, summary, pr_label(run), Text("–", style="dim"), "", "", "", ""
    return (
        run.ticket,
        summary,
        pr_label(run),
        Text(pr.fate.value, style=colors.get(FATE_COLORS[pr.fate], "")),
        f"{pr.opened:%d %b}",
        age((pr.closed or now) - pr.opened),
        str(pr.approvals),
        str(pr.pushes_after_opening),
    )
