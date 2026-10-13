"""The terminal UI: the home screen first, every run and each run's reports a key away."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from textual.app import App

from .batch import TmuxSession, read_tmux_session
from .bitbucket import PullRequests
from .home import HomeScreen
from .live import LiveScreen
from .server import MOCK_URL
from .theme import GRUVBOX_SOFT

REFRESH_SECONDS = 5


class RunsApp(App):
    TITLE = "Pipeline runs"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(
        self,
        root: Path,
        read_session: Callable[[], TmuxSession | None] = read_tmux_session,
        mock_url: str = MOCK_URL,
        pull_requests: PullRequests | None = None,
    ) -> None:
        super().__init__()
        self.sub_title = str(root)
        self._root = root
        self._read_session = read_session
        self._mock_url = mock_url
        # Every screen reads the pull requests from here; the PR screen also fetches them.
        self.pull_requests = pull_requests or PullRequests()

    def get_default_screen(self) -> HomeScreen:
        return HomeScreen(self._root, self._read_session, self._mock_url)

    def on_mount(self) -> None:
        self.register_theme(GRUVBOX_SOFT)
        self.theme = GRUVBOX_SOFT.name
        self.set_interval(REFRESH_SECONDS, self._refresh_screen)

    def _refresh_screen(self) -> None:
        # Only the screen on show reloads; one underneath reloads when it is shown again.
        if isinstance(self.screen, LiveScreen):
            self.screen.action_refresh()
