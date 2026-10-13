from collections import Counter
from datetime import date

from pipeline_tui.chart import day_bars
from pipeline_tui.overview import Outcome


def test_bars_scale_to_the_busiest_day_and_stack_outcomes() -> None:
    days = [
        (date(2026, 10, 1), Counter({Outcome.PR_OPENED: 3, Outcome.BLOCKED: 1})),
        (date(2026, 10, 2), Counter()),
        (date(2026, 10, 3), Counter({Outcome.PR_OPENED: 1})),
    ]
    chart = day_bars(days, height=4)

    assert [line.rstrip() for line in chart.plain.splitlines()] == [
        "4 ██",
        "  ██",
        "  ██",
        "  ██    ██",
        "  01 02 03",
        "■ PR opened  ■ nothing to build  ■ blocked",
    ]
    # The blocked run is the top cell of its bar.
    top_cell = next(span for span in chart.spans if span.start == len("4 "))
    assert top_cell.style == "$error"


def test_no_runs_draws_empty_bars() -> None:
    chart = day_bars([(date(2026, 10, 1), Counter())], height=2)

    assert [line.rstrip() for line in chart.plain.splitlines()][-2:] == ["  01", "■ PR opened  ■ nothing to build  ■ blocked"]
