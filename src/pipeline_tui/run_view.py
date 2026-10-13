"""One run on its own screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, ListItem, ListView, Markdown, Static

from .runs import Run


class RunScreen(Screen):
    """One run: its state.md on top, its reports on the left, the chosen report on the right."""

    BINDINGS = [("escape", "app.pop_screen", "Back")]
    DEFAULT_CSS = """
    RunScreen #state { padding: 0 1; border-bottom: solid $primary; }
    RunScreen ListView { width: 28; border-right: solid $primary; }
    """

    def __init__(self, run: Run) -> None:
        super().__init__()
        self._run = run

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._run.state or "No state.md yet: the run is still going, or was interrupted.", id="state", markup=False)
        with Horizontal():
            yield ListView(*(ListItem(Label(report.name)) for report in self._run.reports))
            with VerticalScroll():
                yield Markdown()
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"{self._run.ticket} · run {self._run.number}"

    async def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.index is not None:
            await self.query_one(Markdown).update(self._run.reports[event.list_view.index].read_text())
