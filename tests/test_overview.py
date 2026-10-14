from datetime import date, datetime, timedelta
from pathlib import Path

from pipeline_tui.overview import Outcome, Share, needs_attention, runs_per_day, ticket_stats
from pipeline_tui.runs import Run

START = datetime(2026, 10, 1, 10, 0)


def run(ticket: str, number: int, hours_in: float, verdict: str | None, minutes: int = 10) -> Run:
    started = START + timedelta(hours=hours_in)
    return Run(
        ticket=ticket,
        number=number,
        path=Path(f"/runs/{ticket}/run-{number}"),
        started=started,
        finished=started + timedelta(minutes=minutes) if verdict else None,
        state=f"{verdict}\n" if verdict else None,
        reports=(),
    )


RUNS = [
    run("ABC-4", 1, 50, None),
    run("ABC-3", 1, 40, "done:nothing-to-build", minutes=2),
    run("ABC-2", 2, 30, "done:pr-opened", minutes=20),
    run("ABC-2", 1, 20, "blocked:tooling", minutes=30),
    run("ABC-1", 1, 0, "blocked:tooling", minutes=10),
]


def test_tickets_count_once_by_their_latest_verdict_and_time_averages_every_run() -> None:
    stats = ticket_stats(RUNS)

    assert stats.tickets == 3
    assert stats.average_run == timedelta(minutes=(2 + 20 + 30 + 10) / 4)
    assert (stats.pr_opened, stats.nothing_to_build, stats.blocked) == (Share(1, 3),) * 3


def test_stats_since_leave_older_runs_out() -> None:
    stats = ticket_stats(RUNS, since=START + timedelta(hours=25))

    assert stats.tickets == 2
    assert stats.blocked.count == 0


def test_no_finished_runs_gives_empty_stats() -> None:
    stats = ticket_stats([run("ABC-4", 1, 0, None)])

    assert (stats.tickets, stats.average_run, stats.pr_opened.ratio) == (0, None, None)


def test_attention_lists_latest_blocked_and_unfinished_runs_not_running_now() -> None:
    assert [r.ticket for r in needs_attention(RUNS, since=START)] == ["ABC-4", "ABC-1"]
    assert [r.ticket for r in needs_attention(RUNS, since=START, running={"ABC-4"})] == ["ABC-1"]
    assert needs_attention(RUNS, since=START + timedelta(hours=1), running={"ABC-4"}) == []


def test_runs_per_day_counts_finished_runs_by_outcome_with_empty_days_kept() -> None:
    days = runs_per_day(RUNS, last_day=date(2026, 10, 3), days=3)

    assert [day for day, _ in days] == [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)]
    assert days[0][1] == {Outcome.BLOCKED: 1}
    assert days[1][1] == {Outcome.BLOCKED: 1, Outcome.PR_OPENED: 1}
    # ABC-4's run on the 3rd is unfinished, so only ABC-3's counts.
    assert days[2][1] == {Outcome.NOTHING_TO_BUILD: 1}


def stated(ticket: str, state: str) -> Run:
    return Run(ticket, 1, Path(f"/runs/{ticket}/run-1"), START, START + timedelta(minutes=10), state, ())


def test_quality_reads_reviews_reworks_and_the_last_app_test_of_each_run() -> None:
    runs = [
        # Passed review first time; the app test ran, then its result line says passed.
        stated("A-1", "investigate — x\nimplement — x\nreview — x — pass\napp-test — app-tester — pass\napp-test: passed\ndone:pr-opened\n"),
        # Failed its first review, reworked once.
        stated("A-2", "01-implement · x · done\n02-review · x · fail\n03-implement · x · done\n04-review · x · pass\ndone:pr-opened\n"),
        # The first review errored out: it judged nothing. The app test could not run.
        stated("A-3", "implement: x\nreview: x — error: session limit\napp-test: unverified:app-test — no environment\nblocked:tooling\n"),
        # Never got past the investigation.
        stated("A-4", "investigate — x — confidence high\ndone:nothing-to-build\n"),
    ]
    stats = ticket_stats(runs)

    assert stats.first_review_passed == Share(1, 2)
    assert stats.rework_rounds == (0 + 1 + 0) / 3
    assert (stats.app_test_passed, stats.app_test_unverified) == (Share(1, 2), Share(1, 2))


def test_quality_is_none_without_runs_that_got_that_far() -> None:
    stats = ticket_stats([stated("A-4", "investigate — x\ndone:nothing-to-build\n")])

    assert (stats.first_review_passed.ratio, stats.rework_rounds, stats.app_test_passed.ratio) == (None, None, None)

