from datetime import datetime, timedelta
from pathlib import Path

from pipeline_tui.runs import load_runs


def test_lists_runs_newest_first_and_skips_batch_directories(runs_root: Path) -> None:
    assert [(run.ticket, run.number) for run in load_runs(runs_root)] == [("XYZ-2", 3), ("ABC-1", 1)]


def test_finished_run_reads_verdict_pr_and_duration_from_state(runs_root: Path) -> None:
    run = next(run for run in load_runs(runs_root) if run.ticket == "ABC-1")

    assert run.verdict == "done:pr-opened"
    assert run.pr == "https://bitbucket.org/example/webui/pull-requests/545"
    assert run.started == datetime(2026, 10, 1, 10, 0)
    assert run.duration == timedelta(hours=1, minutes=15)
    assert [report.name for report in run.reports] == [
        "00-assignment.md",
        "01-investigate.md",
        "02-implement.md",
        "03-review.md",
    ]


def test_unfinished_run_has_no_verdict_and_only_its_assignment(runs_root: Path) -> None:
    run = next(run for run in load_runs(runs_root) if run.ticket == "XYZ-2")

    assert (run.state, run.verdict, run.pr, run.duration) == (None, None, None, None)
    assert [report.name for report in run.reports] == ["00-assignment.md"]


def test_run_without_pull_request_has_no_pr(tmp_path: Path) -> None:
    run_dir = tmp_path / "XYZ-6029" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "state.md").write_text("investigate — ticket-investigator (-) — confidence high\ndone:nothing-to-build\n")

    [run] = load_runs(tmp_path)

    assert (run.verdict, run.pr) == ("done:nothing-to-build", None)


def test_hand_written_state_still_yields_its_pr_and_stages(tmp_path: Path) -> None:
    run_dir = tmp_path / "ABC-7935" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "state.md").write_text(
        "01 investigate · ticket-investigator · confidence high\n"
        "03-review · change-reviewer · pass (3 nits)\n"
        "04 pull-request · ticket-implementer · opened · https://bitbucket.org/example/webui/pull-requests/525 (OPEN)\n"
        "PR: https://bitbucket.org/example/webui/pull-requests/525\n"
        "done:pr-opened\n"
    )

    [run] = load_runs(tmp_path)

    assert run.pr == "https://bitbucket.org/example/webui/pull-requests/525"
    assert [stage.name for stage in run.stages] == ["investigate", "review", "pull-request"]
    assert run.stages[1].result == " · change-reviewer · pass (3 nits)"


def test_summary_comes_from_the_assignment_else_from_the_investigation(tmp_path: Path) -> None:
    new = tmp_path / "ABC-1" / "run-1"
    new.mkdir(parents=True)
    (new / "00-assignment.md").write_text("# ABC-1\n\n- Ticket: ABC-1\n- Summary: Ports table sorts wrong\n")
    old = tmp_path / "ABC-2" / "run-1"
    old.mkdir(parents=True)
    (old / "00-assignment.md").write_text("# ABC-2\n\n- Ticket: ABC-2\n")
    (old / "01-investigate.md").write_text(
        '## Ticket\n\nABC-2, Bug. Summary: "Read "Resources" from the \\"DOM\\"". Labels: UI\n'
    )
    unknown = tmp_path / "ABC-3" / "run-1"
    unknown.mkdir(parents=True)
    (unknown / "01-investigate.md").write_text('## Ticket\n\nABC-3, Bug, "No label marks this title"\n')

    summaries = {run.ticket: run.summary for run in load_runs(tmp_path)}

    assert summaries == {
        "ABC-1": "Ports table sorts wrong",
        "ABC-2": 'Read "Resources" from the "DOM"',
        "ABC-3": None,
    }
