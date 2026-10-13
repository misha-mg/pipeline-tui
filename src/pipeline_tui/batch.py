"""The pipeline's batch: which tickets it was given, which are done, which runs now.

`batch.sh` runs in the tmux session `pipeline`: its window `batch` was started with the ticket
list on the command line, and each ticket gets a window named after it while it runs. Each
finished ticket adds a line to `.pipeline-runs/batch-<YYYYmmdd-HHMMSS>/summary.tsv`: ticket,
outcome, PR, run directory. The session outlives the batch, so a batch is running only while one
of its ticket windows is open.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .runs import Run

SESSION = "pipeline"
_TICKET = re.compile(r"[A-Z]+-\d+")
_BATCH_DIR = re.compile(r"batch-(\d{8}-\d{6})")


@dataclass(frozen=True)
class TmuxSession:
    created: datetime
    # The command the `batch` window was started with; it names the batch's tickets.
    command: str
    windows: tuple[str, ...]


@dataclass(frozen=True)
class Batch:
    started: datetime
    tickets: tuple[str, ...]
    # Finished tickets in the order they finished, each with its outcome from summary.tsv.
    outcomes: tuple[tuple[str, str], ...]
    # The ticket running now; None when the batch is over.
    current: str | None
    # The current ticket's run, once its pipeline has claimed a run directory.
    current_run: Run | None

    @property
    def progress(self) -> float:
        return len(self.outcomes) / len(self.tickets) if self.tickets else 0.0


def read_tmux_session(name: str = SESSION) -> TmuxSession | None:
    """The batch's tmux session, or None when there is none (or no tmux)."""
    try:
        result = subprocess.run(
            ["tmux", "list-windows", "-t", name, "-F", "#{session_created}\t#{window_name}\t#{pane_start_command}"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode:
        return None
    windows = [line.split("\t", 2) for line in result.stdout.splitlines()]
    command = next((cmd for _, name, cmd in windows if name == "batch"), "")
    return TmuxSession(
        created=datetime.fromtimestamp(int(windows[0][0])),
        command=command,
        windows=tuple(name for _, name, _ in windows),
    )


def load_batch(root: Path, session: TmuxSession | None, runs: list[Run]) -> Batch | None:
    """The batch running in session, or else the last one recorded under root; None if neither."""
    last = _last_batch_dir(root)
    if session is None:
        if last is None:
            return None
        summary = _summary(last[1])
        if not summary:
            return None
        return Batch(last[0], tuple(t for t, _ in summary), _done(summary), None, None)

    # batch.sh makes its directory just after the session starts; an older one is an earlier batch.
    outcomes = _done(_summary(last[1])) if last and last[0] >= session.created else ()
    current = next((w for w in session.windows if _TICKET.fullmatch(w)), None)
    current_run = next(
        (r for r in runs if r.ticket == current and r.started >= session.created), None
    ) if current else None
    return Batch(session.created, tuple(_TICKET.findall(session.command)), outcomes, current, current_run)


def _last_batch_dir(root: Path) -> tuple[datetime, Path] | None:
    dirs = [
        (datetime.strptime(m.group(1), "%Y%m%d-%H%M%S"), path)
        for path in root.iterdir()
        if path.is_dir() and (m := _BATCH_DIR.fullmatch(path.name))
    ]
    return max(dirs, default=None)


def _done(summary: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    # A batch stopped by the usage limit lists the tickets it did not start as "not started".
    return tuple(line for line in summary if line[1] != "not started")


def _summary(batch_dir: Path) -> tuple[tuple[str, str], ...]:
    summary = batch_dir / "summary.tsv"
    if not summary.exists():
        return ()
    return tuple(tuple(line.split("\t")[:2]) for line in summary.read_text().splitlines() if line)
