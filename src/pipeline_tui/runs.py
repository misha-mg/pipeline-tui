"""The ticket-pipeline runs on disk, read from a `.pipeline-runs` directory.

A run lives in `<root>/<TICKET>/run-<N>/`. The pipeline writes `00-assignment.md` when the run
starts, and the stage reports (`<NN>-<stage>.md`) together with `state.md` only when it ends:
`state.md` has a line per stage, the pull request's URL when one was opened, and the verdict as its
last line. Older runs wrote `state.md` by hand, so a stage line may start with `01 `, `01-` or
nothing, and the PR's URL may sit anywhere.

The ticket's summary is a `- Summary: ` line in `00-assignment.md`. Runs from before that line
existed have it only in the investigation report, worded freely; it is taken from there when a
`Summary:` label marks it, and is otherwise unknown.

An unfinished run has no stage reports yet, and the files cannot tell a run still going from one
that was interrupted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

_TICKET = re.compile(r"[A-Z]+-\d+")
_RUN = re.compile(r"run-(\d+)")
_REPORT = re.compile(r"\d\d-.+\.md")
_PR = re.compile(r"https://bitbucket\.org/\S+?/pull-requests/\d+")
_REASON = re.compile(r"^reason: (.+)$", re.MULTILINE)
_SUMMARY = re.compile(r"(?:\*\*)?Summary:(?:\*\*)?[ \t]*(.+)")
# A quoted summary runs to the line's last quote: quotes inside it may or may not be escaped.
_QUOTED = re.compile(r'"(.*)"')
_STAGE = re.compile(r"(?:\d\d[ -])?(investigate|diff|implement|review|app-test|pull-request)\b(.*)", re.IGNORECASE)


@dataclass(frozen=True)
class Stage:
    name: str
    # The rest of its state.md line: agent, mode and result, in that run's wording.
    result: str


@dataclass(frozen=True)
class Run:
    ticket: str
    number: int
    path: Path
    started: datetime
    # When state.md was written; None while the run has none.
    finished: datetime | None
    # state.md as written; None while the run has none.
    state: str | None
    # 00-assignment.md and the stage reports, in the order they were written.
    reports: tuple[Path, ...]
    # The ticket's Jira summary; None when the run's files do not give it.
    summary: str | None = None

    @property
    def verdict(self) -> str | None:
        return self.state.strip().splitlines()[-1] if self.state else None

    @property
    def pr(self) -> str | None:
        match = _PR.search(self.state or "")
        return match.group(0) if match else None

    @property
    def reason(self) -> str | None:
        """Why the run ended as it did, when state.md says: a blocked run's cause, say."""
        match = _REASON.search(self.state or "")
        return match.group(1) if match else None

    @property
    def stages(self) -> tuple[Stage, ...]:
        """The stages state.md lists, in order; an app-test may be listed twice, as run and as result."""
        lines = (self.state or "").splitlines()
        return tuple(Stage(m.group(1).lower(), m.group(2)) for line in lines if (m := _STAGE.match(line)))

    @property
    def duration(self) -> timedelta | None:
        return self.finished - self.started if self.finished else None


def load_runs(root: Path) -> list[Run]:
    """Every run under root, the most recently started first."""
    runs = [
        _load_run(run_dir, ticket_dir.name, int(match.group(1)))
        for ticket_dir in root.iterdir()
        if ticket_dir.is_dir() and _TICKET.fullmatch(ticket_dir.name)
        for run_dir in ticket_dir.iterdir()
        if run_dir.is_dir() and (match := _RUN.fullmatch(run_dir.name))
    ]
    return sorted(runs, key=lambda run: run.started, reverse=True)


def _load_run(path: Path, ticket: str, number: int) -> Run:
    # The assignment is written as the run starts; a run claimed a moment ago may not have it yet.
    assignment = path / "00-assignment.md"
    started = _mtime(assignment if assignment.exists() else path)
    state_file = path / "state.md"
    has_state = state_file.exists()
    return Run(
        ticket=ticket,
        number=number,
        path=path,
        started=started,
        finished=_mtime(state_file) if has_state else None,
        state=state_file.read_text() if has_state else None,
        reports=tuple(sorted(p for p in path.iterdir() if _REPORT.fullmatch(p.name))),
        summary=_summary(assignment) or _summary(path / "01-investigate.md"),
    )


def _summary(report: Path) -> str | None:
    match = _SUMMARY.search(report.read_text()) if report.exists() else None
    if not match:
        return None
    text = match.group(1).strip()
    quoted = _QUOTED.match(text)
    return quoted.group(1).replace('\\"', '"') if quoted else text


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)
