"""Runs per day as stacked bars, drawn with block characters in the theme's colors."""

from __future__ import annotations

from collections import Counter
from datetime import date
from math import ceil

from textual.content import Content

from .overview import Outcome

# Bottom to top: a day's blocked runs sit on top of its bar, where they catch the eye.
STACK = (
    (Outcome.PR_OPENED, "$success"),
    (Outcome.NOTHING_TO_BUILD, "$secondary"),
    (Outcome.OTHER, "$foreground-muted"),
    (Outcome.BLOCKED, "$error"),
)
BAR = "██"


def day_bars(days: list[tuple[date, Counter[Outcome]]], height: int) -> Content:
    """One bar per day, scaled so the busiest day is height rows, its run count just above it; day
    numbers below, legend last."""
    top = max((sum(counts.values()) for _, counts in days), default=0)
    columns = [_column(counts, top, height) for _, counts in days]
    totals = [sum(counts.values()) for _, counts in days]
    lines = []
    # One row more than the bars: the busiest day's count sits above its full-height bar.
    for row in reversed(range(height + 1)):
        parts: list[tuple[str, str] | str] = []
        for column, total in zip(columns, totals):
            filled = height - column.count(None)
            if row < filled:
                parts.append((BAR, column[row]))
            elif row == filled and total:
                parts.append(str(total).rjust(len(BAR)))
            else:
                parts.append(" " * len(BAR))
            parts.append(" ")
        lines.append(Content.assemble(*parts))
    lines.append(Content(" ".join(f"{day:%d}" for day, _ in days)))
    lines.append(_legend(days))
    return Content("\n").join(lines)


def _column(counts: Counter[Outcome], top: int, height: int) -> list[str | None]:
    """A bar's cells, bottom up: each holds its outcome's style, or None above the bar."""
    cells: list[str | None] = []
    total = 0
    for kind, style in STACK:
        # Rounding the running total up keeps a single run visible on the busiest day's scale.
        before, total = total, total + counts[kind]
        cells += [style] * (ceil(total * height / top) - ceil(before * height / top)) if top else []
    return cells + [None] * (height - len(cells))


def _legend(days: list[tuple[date, Counter[Outcome]]]) -> Content:
    shown = [(kind, style) for kind, style in STACK if kind is not Outcome.OTHER or any(c[kind] for _, c in days)]
    parts: list[tuple[str, str] | str] = []
    for kind, style in shown:
        parts += [("■ ", style), kind.value, "  "]
    return Content.assemble(*parts[:-1])
