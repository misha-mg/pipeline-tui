import os
from datetime import datetime
from pathlib import Path

import pytest

ASSIGNMENT = "# ABC-1 — run 1 assignment\n\n- Ticket: ABC-1\n- Summary: Ports table sorts by the wrong column\n"

FINISHED_STATE = """\
01 investigate (ticket-investigator, -): confidence medium
02 implement (ticket-implementer, implement): done
03 review (change-reviewer, -): pass
pr: https://bitbucket.org/example/webui/pull-requests/545
done:pr-opened
"""


def write(path: Path, text: str, at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.utime(path, (at.timestamp(), at.timestamp()))


@pytest.fixture
def runs_root(tmp_path: Path) -> Path:
    """A .pipeline-runs with one finished run, one unfinished run, and a batch stopped after one ticket."""
    # The main checkout is tmp_path, as .pipeline-runs sits in the webui main checkout.
    root = tmp_path / ".pipeline-runs"
    done = root / "ABC-1" / "run-1"
    write(done / "00-assignment.md", ASSIGNMENT, datetime(2026, 10, 1, 10, 0))
    write(done / "01-investigate.md", "# investigate", datetime(2026, 10, 1, 11, 0))
    write(done / "02-implement.md", "# implement", datetime(2026, 10, 1, 11, 0))
    write(done / "03-review.md", "# review", datetime(2026, 10, 1, 11, 0))
    write(done / "diff-0.patch", "", datetime(2026, 10, 1, 10, 30))
    write(done / "state.md", FINISHED_STATE, datetime(2026, 10, 1, 11, 15))

    going = root / "XYZ-2" / "run-3"
    write(going / "00-assignment.md", "# XYZ-2 — run 3 assignment", datetime(2026, 10, 2, 9, 0))

    write(
        root / "batch-20261001-095500" / "summary.tsv",
        "ABC-1\tdone:pr-opened\thttps://bitbucket.org/example/webui/pull-requests/545\t/x/ABC-1/run-1\n"
        "ABC-3\tnot started\t-\t-\n",
        datetime(2026, 10, 1, 11, 20),
    )
    return root
