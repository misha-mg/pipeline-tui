import asyncio
from io import StringIO
from datetime import datetime
from pathlib import Path

from rich.console import Console
from textual.widgets import DataTable, Label, Markdown, Static

from conftest import ASSIGNMENT, write
from test_bitbucket import FakeApi, update
from pipeline_tui.app import RunsApp
from pipeline_tui.batch import TmuxSession
from pipeline_tui.bitbucket import Bitbucket, PullRequests
from pipeline_tui.home import HomeScreen
from pipeline_tui.pr_screen import PullRequestsScreen
from pipeline_tui.run_view import RunScreen
from pipeline_tui.server_block import ServerBlock
from pipeline_tui.table import RunsScreen

BATCH = TmuxSession(
    created=datetime(2026, 10, 1, 9, 55),
    command="tools/ticket-pipeline/batch.sh ABC-1 XYZ-2 ABC-3 ; exec bash",
    windows=("batch", "XYZ-2"),
)


# Nothing listens on the discard port: the server block finds no mock, fast.
NO_MOCK = "http://127.0.0.1:9"


def no_session() -> None:
    return None


def text_of(widget: Static) -> str:
    """The widget's text as a terminal would show it."""
    console = Console(width=100, record=True, file=StringIO())
    console.print(widget.content)
    return console.export_text()


def test_home_shows_the_running_batch_and_the_statistics(runs_root: Path) -> None:
    async def scenario() -> None:
        app = RunsApp(runs_root, read_session=lambda: BATCH, mock_url=NO_MOCK)
        async with app.run_test(size=(100, 40)):
            assert isinstance(app.screen, HomeScreen)
            assert "██╗" in text_of(app.screen.query_one("#banner", Static))
            batch = text_of(app.screen.query_one("#batch", Static))
            assert "1 of 3 tickets done" in batch
            assert "XYZ-2" in batch and "ABC-3" in batch
            stats = text_of(app.screen.query_one("#stats", Static))
            assert "Tickets" in stats and "100% (1)" in stats
            assert "First review passed" in stats
            # The fixture's only finished run started on 1 October.
            assert "Last day" in stats and "01 Oct" in stats and "01 Oct–" in stats
            # Nothing in the fixture is from the last week.
            assert app.screen.query_one("#all-clear").display
            assert not app.screen.query_one("#attention").display

    asyncio.run(scenario())


def test_home_opens_a_run_that_needs_attention(runs_root: Path) -> None:
    # The fixture's runs are older than the attention block's week; this one is from today.
    blocked = runs_root / "ABC-5" / "run-1"
    write(blocked / "00-assignment.md", "# ABC-5", datetime.now())
    write(blocked / "state.md", "reason: the mock did not answer\nblocked:tooling\n", datetime.now())

    async def scenario() -> None:
        app = RunsApp(runs_root, read_session=no_session, mock_url=NO_MOCK)
        async with app.run_test() as pilot:
            attention = app.screen.query_one("#attention", DataTable)
            assert [str(attention.get_row_at(i)[0]) for i in range(attention.row_count)] == ["ABC-5"]

            attention.focus()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, RunScreen)
            summary = text_of(app.screen.query_one("#summary", Static))
            assert "blocked:tooling" in summary
            assert "Reason   the mock did not answer" in summary

    asyncio.run(scenario())


def test_table_shows_each_run_with_its_outcome(runs_root: Path) -> None:
    async def scenario() -> None:
        app = RunsApp(runs_root, read_session=no_session, mock_url=NO_MOCK)
        async with app.run_test() as pilot:
            await pilot.press("a")
            await pilot.pause()
            assert isinstance(app.screen, RunsScreen)
            table = app.screen.query_one(DataTable)
            rows = [table.get_row_at(i) for i in range(table.row_count)]
            labels = [str(table.rows[key].label or "") for key in table.rows]

            assert [str(row[0]) for row in rows] == ["Fri 02 Oct", "XYZ-2", "Thu 01 Oct", "ABC-1"]
            assert labels == ["", "1", "", "2"]
            assert tuple(rows[3][1:]) == (
                "Ports table sorts by the wrong column", "1", "10:00", "1h 15m", "done:pr-opened", "#545"
            )
            assert (rows[1][1], rows[1][5]) == ("", "unfinished")
            # The cursor starts on the first run, not on its day row.
            assert table.cursor_row == 1

    asyncio.run(scenario())


def test_cursor_steps_over_day_rows_both_ways(runs_root: Path) -> None:
    async def scenario() -> None:
        app = RunsApp(runs_root, read_session=no_session, mock_url=NO_MOCK)
        async with app.run_test() as pilot:
            await pilot.press("a")
            await pilot.pause()
            table = app.screen.query_one(DataTable)
            await pilot.press("down")
            await pilot.pause()
            assert table.cursor_row == 3

            await pilot.press("up")
            await pilot.pause()
            assert table.cursor_row == 1

            # Above the first run is only its day row: the cursor stays on the run.
            await pilot.press("up")
            await pilot.pause()
            assert table.cursor_row == 1

    asyncio.run(scenario())


def test_enter_opens_the_run_and_escape_goes_back(runs_root: Path) -> None:
    async def scenario() -> None:
        app = RunsApp(runs_root, read_session=no_session, mock_url=NO_MOCK)
        async with app.run_test() as pilot:
            await pilot.press("a", "down", "enter")
            await pilot.pause()

            assert isinstance(app.screen, RunScreen)
            summary = text_of(app.screen.query_one("#summary", Static))
            assert "ABC-1 · Ports table sorts by the wrong column" in summary
            assert "01 Oct 10:00 · took 1h 15m" in summary
            assert "Reviews  1" in summary
            assert "https://bitbucket.org/example/webui/pull-requests/545" in summary
            assert "Reason" not in summary
            documents = [str(label.content) for label in app.screen.query(Label)]
            assert documents[-1] == "state.md"
            assert app.screen.query_one(Markdown).source == ASSIGNMENT

            await pilot.press("escape")
            assert isinstance(app.screen, RunsScreen)
            await pilot.press("escape")
            assert isinstance(app.screen, HomeScreen)

    asyncio.run(scenario())


def test_server_block_shows_worktrees_and_a_silent_mock(runs_root: Path) -> None:
    (runs_root.parent / ".claude" / "worktrees" / "ABC-1" / "node_modules").mkdir(parents=True)

    async def scenario() -> None:
        app = RunsApp(runs_root, read_session=no_session, mock_url=NO_MOCK)
        async with app.run_test() as pilot:
            block = app.screen.query_one(ServerBlock)
            await app.workers.wait_for_complete()
            await pilot.pause()
            text = text_of(block)
            assert "1 · 1 with node_modules" in text
            assert "not answering" in text

    asyncio.run(scenario())


def tickets_in(table: DataTable) -> list[str]:
    """The tickets of the run rows, leaving out the day rows."""
    return [str(table.get_row(key)[0]) for key in table.rows if not key.value.startswith("day:")]


def test_filter_steps_through_outcomes_and_escape_clears_it(runs_root: Path) -> None:
    async def scenario() -> None:
        app = RunsApp(runs_root, read_session=no_session, mock_url=NO_MOCK)
        async with app.run_test() as pilot:
            await pilot.press("a")
            await pilot.pause()
            table = app.screen.query_one(DataTable)
            assert tickets_in(table) == ["XYZ-2", "ABC-1"]

            await pilot.press("f")
            await pilot.pause()
            assert tickets_in(table) == ["ABC-1"]
            assert app.screen.title == "All runs · PR opened"

            # PR opened → nothing to build → blocked → unfinished.
            await pilot.press("f", "f", "f")
            await pilot.pause()
            assert tickets_in(table) == ["XYZ-2"]

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, RunsScreen)
            assert tickets_in(table) == ["XYZ-2", "ABC-1"]

    asyncio.run(scenario())


def test_search_matches_the_summary_and_escape_clears_it(runs_root: Path) -> None:
    async def scenario() -> None:
        app = RunsApp(runs_root, read_session=no_session, mock_url=NO_MOCK)
        async with app.run_test() as pilot:
            await pilot.press("a")
            await pilot.pause()
            table = app.screen.query_one(DataTable)

            # "r" is the refresh key, yet it goes into the search; case does not matter.
            await pilot.press("slash", *"SoRts", "enter")
            await pilot.pause()
            assert tickets_in(table) == ["ABC-1"]
            assert app.screen.title == "All runs · “SoRts”"

            await pilot.press("escape")
            await pilot.pause()
            assert tickets_in(table) == ["XYZ-2", "ABC-1"]
            assert isinstance(app.screen, RunsScreen)

    asyncio.run(scenario())


def test_pull_requests_screen_fetches_the_runs_pull_requests_and_counts_their_fates(runs_root: Path, tmp_path: Path) -> None:
    api = FakeApi()
    api.add(545, "MERGED", [update("MERGED", "a", "2026-10-02T10:00:00.000000+00:00"), update("OPEN", "a", "2026-10-01T10:00:00.000000+00:00")])
    pull_requests = PullRequests(tmp_path / "cache.json", Bitbucket("secret", api))

    async def scenario() -> None:
        app = RunsApp(runs_root, read_session=no_session, mock_url=NO_MOCK, pull_requests=pull_requests)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.press("p")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert isinstance(app.screen, PullRequestsScreen)
            fates = text_of(app.screen.query_one("#fates", Static))
            assert "Merged as is" in fates and "100% (1)" in fates
            table = app.screen.query_one(DataTable)
            assert [str(cell) for cell in table.get_row_at(0)][:4] == ["ABC-1", "Ports table sorts by the wrong column", "#545", "merged as is"]

            await pilot.press("enter")
            await pilot.pause()
            assert "bitbucket.org/example/webui/pull-requests/545 · merged as is" in text_of(app.screen.query_one("#summary", Static))

    asyncio.run(scenario())


def test_pull_requests_screen_without_a_token_says_how_to_connect(runs_root: Path) -> None:
    async def scenario() -> None:
        app = RunsApp(runs_root, read_session=no_session, mock_url=NO_MOCK)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.press("p")
            await pilot.pause()
            assert "BITBUCKET_TOKEN" in text_of(app.screen.query_one("#note", Static))
            assert "Not fetched yet" in text_of(app.screen.query_one("#fates", Static))

    asyncio.run(scenario())
