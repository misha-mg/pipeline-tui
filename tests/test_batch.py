from datetime import datetime
from pathlib import Path

from pipeline_tui.batch import TmuxSession, load_batch
from pipeline_tui.runs import load_runs


def session(created: datetime, windows: tuple[str, ...]) -> TmuxSession:
    command = "/srv/webui/tools/ticket-pipeline/batch.sh ABC-1 XYZ-2 ABC-3 ; exec bash"
    return TmuxSession(created=created, command=command, windows=("batch", *windows))


def test_running_batch_takes_tickets_from_tmux_and_progress_from_its_summary(runs_root: Path) -> None:
    runs = load_runs(runs_root)
    batch = load_batch(runs_root, session(datetime(2026, 10, 1, 9, 55), ("XYZ-2",)), runs)

    assert batch is not None
    assert batch.tickets == ("ABC-1", "XYZ-2", "ABC-3")
    assert batch.outcomes == (("ABC-1", "done:pr-opened"),)
    assert batch.progress == 1 / 3
    assert batch.current == "XYZ-2"
    assert batch.current_run is not None and batch.current_run.number == 3


def test_batch_directory_older_than_the_session_belongs_to_an_earlier_batch(runs_root: Path) -> None:
    batch = load_batch(runs_root, session(datetime(2026, 10, 3, 8, 0), ("ABC-1",)), load_runs(runs_root))

    assert batch is not None
    assert batch.outcomes == ()
    # The run of ABC-1 is from before this session: this batch has not claimed one yet.
    assert (batch.current, batch.current_run) == ("ABC-1", None)


def test_without_a_session_the_last_recorded_batch_is_shown_as_over(runs_root: Path) -> None:
    batch = load_batch(runs_root, None, load_runs(runs_root))

    assert batch is not None
    assert batch.started == datetime(2026, 10, 1, 9, 55)
    assert batch.tickets == ("ABC-1", "ABC-3")
    assert batch.outcomes == (("ABC-1", "done:pr-opened"),)
    assert batch.current is None


def test_no_session_and_no_batch_directory_is_no_batch(tmp_path: Path) -> None:
    assert load_batch(tmp_path, None, []) is None
