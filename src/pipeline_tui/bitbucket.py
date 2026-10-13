"""What became of the runs' pull requests, read from the Bitbucket Cloud API and kept in a cache.

A pull request that is merged or declined never changes again, so it is fetched once; an open one
is fetched again when its copy is older than MAX_AGE.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

MAX_AGE = timedelta(minutes=10)
TOKEN_FILE = Path.home() / ".config" / "pipeline-tui" / "bitbucket-token"
CACHE_FILE = Path.home() / ".cache" / "pipeline-tui" / "pull-requests.json"

_PR_URL = re.compile(r"https://bitbucket\.org/([^/]+)/([^/]+)/pull-requests/(\d+)")


class Fate(Enum):
    OPEN = "open"
    MERGED_AS_IS = "merged as is"
    MERGED_CHANGED = "merged with changes"
    DECLINED = "declined"


@dataclass(frozen=True)
class PullRequest:
    url: str
    # OPEN, MERGED, DECLINED or SUPERSEDED, as Bitbucket says.
    state: str
    opened: datetime
    # When it was merged or declined; None while it is open.
    closed: datetime | None
    # Commits pushed to its branch after it was opened: by people, as the pipeline pushes once.
    pushes_after_opening: int
    approvals: int
    changes_requested: int
    fetched: datetime

    @property
    def fate(self) -> Fate:
        if self.state == "MERGED":
            return Fate.MERGED_CHANGED if self.pushes_after_opening else Fate.MERGED_AS_IS
        return Fate.OPEN if self.state == "OPEN" else Fate.DECLINED

    @property
    def final(self) -> bool:
        return self.state != "OPEN"


def load_token() -> str | None:
    """BITBUCKET_TOKEN from the environment, else the token file; None when neither is set."""
    token = os.environ.get("BITBUCKET_TOKEN") or (TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else "")
    return token or None


def _get_json(url: str, token: str) -> Any:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


class Bitbucket:
    """Reads one pull request: its state, reviews, and the pushes to it after it was opened."""

    def __init__(self, token: str, get_json: Callable[[str, str], Any] = _get_json) -> None:
        self._token = token
        self._get_json = get_json

    def pull_request(self, url: str, now: datetime) -> PullRequest:
        match = _PR_URL.match(url)
        if not match:
            raise ValueError(f"not a Bitbucket pull request: {url}")
        workspace, repo, number = match.groups()
        api = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}/pullrequests/{number}"
        pr = self._get_json(api, self._token)
        updates = [entry["update"] for entry in self._activity(f"{api}/activity?pagelen=50") if "update" in entry]
        # Every update while open names the branch's head; the first head is what the pipeline pushed.
        heads = {update["source"]["commit"]["hash"] for update in updates if update["state"] == "OPEN"}
        closings = [_time(update["date"]) for update in updates if update["state"] != "OPEN"]
        participants = pr.get("participants", [])
        return PullRequest(
            url=url,
            state=pr["state"],
            opened=_time(pr["created_on"]),
            closed=None if pr["state"] == "OPEN" else min(closings, default=_time(pr["updated_on"])),
            pushes_after_opening=max(len(heads) - 1, 0),
            approvals=sum(bool(p.get("approved")) for p in participants),
            changes_requested=sum(p.get("state") == "changes_requested" for p in participants),
            fetched=now,
        )

    def _activity(self, url: str | None) -> Iterable[dict[str, Any]]:
        while url:
            page = self._get_json(url, self._token)
            yield from page["values"]
            url = page.get("next")


class PullRequests:
    """The pull requests seen so far, kept at path between runs of the app (only in memory without one).

    Without a client nothing is fetched: what the cache holds is all there is.
    """

    def __init__(self, path: Path | None = None, client: Bitbucket | None = None) -> None:
        self._path = path
        self._client = client
        self._known: dict[str, PullRequest] = self._load()

    @property
    def connected(self) -> bool:
        return self._client is not None

    def get(self, url: str) -> PullRequest | None:
        return self._known.get(url)

    def refresh(self, urls: Iterable[str], now: datetime) -> list[str]:
        """Fetch the ones never seen and the open ones gone stale; return the errors, one per URL."""
        if self._client is None:
            return []
        errors = []
        for url in urls:
            known = self._known.get(url)
            if known and (known.final or now - known.fetched < MAX_AGE):
                continue
            try:
                self._known[url] = self._client.pull_request(url, now)
            except (OSError, ValueError, KeyError) as error:
                errors.append(f"{url}: {error}")
        self._save()
        return errors

    def _load(self) -> dict[str, PullRequest]:
        if self._path is None:
            return {}
        try:
            rows = json.loads(self._path.read_text())
        except (OSError, ValueError):
            return {}
        return {row["url"]: _from_row(row) for row in rows}

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        rows = [asdict(pr) for pr in self._known.values()]
        self._path.write_text(json.dumps(rows, default=datetime.isoformat, indent=1))


def _from_row(row: dict[str, Any]) -> PullRequest:
    times = {key: _time(row[key]) if row[key] else None for key in ("opened", "closed", "fetched")}
    return PullRequest(**{**row, **times})


def _time(text: str) -> datetime:
    """Bitbucket's UTC time as local time without a zone, the way the runs' times are kept."""
    return datetime.fromisoformat(text).astimezone().replace(tzinfo=None)
