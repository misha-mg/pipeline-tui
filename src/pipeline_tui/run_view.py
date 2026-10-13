"""One run on its own screen."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.content import Content
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, ListItem, ListView, Markdown, Static

from .bitbucket import PullRequest
from .fmt import span
from .runs import Run


class RunScreen(Screen):
    """One run: a summary on top, its documents on the left, the chosen document on the right."""

    BINDINGS = [("escape", "app.pop_screen", "Back")]
    DEFAULT_CSS = """
    RunScreen #summary { padding: 1 2; border-bottom: solid $primary; }
    RunScreen ListView { width: 28; border-right: solid $primary; }
    """

    def __init__(self, run: Run) -> None:
        super().__init__()
        self._run = run
        # The reports, then state.md: the summary above is drawn from it, the file has the rest.
        state = run.path / "state.md"
        self._documents: tuple[Path, ...] = run.reports + ((state,) if run.state is not None else ())

    def compose(self) -> ComposeResult:
        yield Header()
        pr = self.app.pull_requests.get(self._run.pr) if self._run.pr else None
        yield Static(_summary(self._run, pr, datetime.now()), id="summary")
        with Horizontal():
            yield ListView(*(ListItem(Label(document.name)) for document in self._documents))
            with VerticalScroll():
                yield Markdown()
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"{self._run.ticket} · run {self._run.number}"

    async def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.index is None:
            return
        document = self._documents[event.list_view.index]
        text = document.read_text()
        # state.md is one fact per line, not Markdown: as Markdown its lines would run together.
        await self.query_one(Markdown).update(f"```\n{text}\n```" if document.name == "state.md" else text)


def _summary(run: Run, pr: PullRequest | None, now: datetime) -> Content:
    if run.duration is None:
        time = f"started {run.started:%d %b %H:%M} · {span(now - run.started)} ago, no result yet"
    else:
        time = f"{run.started:%d %b %H:%M} · took {span(run.duration)}"
    rows = [
        ("Ticket", f"{run.ticket} · {run.summary}" if run.summary else run.ticket),
        ("Verdict", run.verdict or "unfinished"),
        ("Time", time),
        ("Reviews", str(sum(stage.name == "review" for stage in run.stages))),
        ("PR", f"{run.pr} · {pr.fate.value}" if pr else run.pr or "–"),
    ]
    if run.reason:
        rows.append(("Reason", run.reason))
    return Content("\n").join(Content.assemble((f"{label:<9}", "bold"), value) for label, value in rows)
