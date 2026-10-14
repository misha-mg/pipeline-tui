"""What the runs add up to: outcome and quality statistics, runs per day, and the tickets that need a look."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum

from .runs import Run, Stage


class Outcome(Enum):
    PR_OPENED = "PR opened"
    NOTHING_TO_BUILD = "nothing to build"
    BLOCKED = "blocked"
    OTHER = "other"


def outcome(verdict: str) -> Outcome:
    if verdict == "done:pr-opened":
        return Outcome.PR_OPENED
    if verdict == "done:nothing-to-build":
        return Outcome.NOTHING_TO_BUILD
    return Outcome.BLOCKED if verdict.startswith("blocked") else Outcome.OTHER


@dataclass(frozen=True)
class Share:
    """count of total; with a handful of runs a percentage alone says little, so both are kept."""

    count: int
    total: int

    @property
    def ratio(self) -> float | None:
        return self.count / self.total if self.total else None


@dataclass(frozen=True)
class Stats:
    # Tickets with a finished run; each counts once, by the verdict of its latest finished run.
    tickets: int
    # Over every finished run, retries included.
    average_run: timedelta | None
    pr_opened: Share
    nothing_to_build: Share
    blocked: Share
    # The rest is over runs, retries included: of the runs that got a review, those whose first
    # review passed; the average rework rounds of the runs that implemented (None when none did);
    # and of the runs that reached the app test, how their last app test ended.
    first_review_passed: Share
    rework_rounds: float | None
    app_test_passed: Share
    app_test_unverified: Share


def ticket_stats(runs: list[Run], since: datetime | None = None) -> Stats:
    """Stats of the finished runs started at or after since (all of them when since is None)."""
    finished = [r for r in runs if r.duration is not None and (since is None or r.started >= since)]
    outcomes = Counter(outcome(r.verdict or "") for r in _latest_per_ticket(finished))
    tickets = sum(outcomes.values())

    return Stats(
        tickets=tickets,
        average_run=sum((r.duration for r in finished), timedelta()) / len(finished) if finished else None,
        pr_opened=Share(outcomes[Outcome.PR_OPENED], tickets),
        nothing_to_build=Share(outcomes[Outcome.NOTHING_TO_BUILD], tickets),
        blocked=Share(outcomes[Outcome.BLOCKED], tickets),
        **_quality([r.stages for r in finished]),
    )


def _quality(runs: list[tuple[Stage, ...]]) -> dict[str, Share | float | None]:
    first_reviews = [next((s.result for s in stages if s.name == "review"), "") for stages in runs]
    # A review that errored out (a usage limit, say) judged nothing: it counts neither way.
    verdicts = [result for result in first_reviews if "pass" in result or "fail" in result]
    implements = [n for stages in runs if (n := sum(s.name == "implement" for s in stages))]
    app_tests = [[s for s in stages if s.name == "app-test"] for stages in runs]
    last_app_tests = [_app_test(tests[-1]) for tests in app_tests if tests]

    return {
        "first_review_passed": Share(sum("pass" in result for result in verdicts), len(verdicts)),
        "rework_rounds": sum(n - 1 for n in implements) / len(implements) if implements else None,
        "app_test_passed": Share(last_app_tests.count("passed"), len(last_app_tests)),
        "app_test_unverified": Share(last_app_tests.count("unverified"), len(last_app_tests)),
    }


def _app_test(stage: Stage) -> str:
    result = stage.result.lower()
    if any(word in result for word in ("unverified", "blocked", "not run")):
        return "unverified"
    if "fail" in result:
        return "failed"
    return "passed" if "pass" in result else "unverified"


def runs_per_day(runs: list[Run], last_day: date, days: int) -> list[tuple[date, Counter[Outcome]]]:
    """Finished runs (retries included) by the day they started and their outcome, oldest day first."""
    first_day = last_day - timedelta(days=days - 1)
    per_day: dict[date, Counter[Outcome]] = {first_day + timedelta(days=i): Counter() for i in range(days)}
    for run in runs:
        if run.duration is not None and run.started.date() in per_day:
            per_day[run.started.date()][outcome(run.verdict or "")] += 1
    return list(per_day.items())


def needs_attention(runs: list[Run], since: datetime, running: Collection[str] = ()) -> list[Run]:
    """Latest runs since then that were blocked, or are unfinished and not running now.

    A ticket counts by its latest run only: a blocked run followed by one that opened a PR is
    settled.
    """
    return [
        r
        for r in _latest_per_ticket([r for r in runs if r.started >= since])
        if (r.verdict or "").startswith("blocked") or (r.duration is None and r.ticket not in running)
    ]


def _latest_per_ticket(runs: list[Run]) -> list[Run]:
    latest: dict[str, Run] = {}
    for run in runs:
        if run.ticket not in latest or run.started > latest[run.ticket].started:
            latest[run.ticket] = run
    return sorted(latest.values(), key=lambda r: r.started, reverse=True)
