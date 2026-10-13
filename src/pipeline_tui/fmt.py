"""How times, sizes and pull requests are written on screen."""

from __future__ import annotations

from datetime import timedelta

from .overview import Share
from .runs import Run


def span(span: timedelta) -> str:
    minutes = int(span.total_seconds()) // 60
    return f"{minutes // 60}h {minutes % 60:02d}m" if minutes >= 60 else f"{minutes}m"


def age(span_: timedelta) -> str:
    """A span that may run to days: "3d 04h", or as span() under a day."""
    if span_ < timedelta(days=1):
        return span(span_)
    return f"{span_.days}d {span_.seconds // 3600:02d}h"


def share(share_: Share) -> str:
    """"85% (11)": the percentage, and how many it is."""
    return f"{share_.ratio:.0%} ({share_.count})" if share_.ratio is not None else "–"


def pr_label(run: Run) -> str:
    return "#" + run.pr.rsplit("/", 1)[-1] if run.pr else ""


def size(n: int) -> str:
    gigabytes = n / 1024**3
    return f"{gigabytes:.0f} GB" if gigabytes >= 1 else f"{n / 1024**2:.0f} MB"
