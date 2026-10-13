from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pipeline_tui.bitbucket import Bitbucket, Fate, PullRequests

URL = "https://bitbucket.org/example/webui/pull-requests/{}"
API = "https://api.bitbucket.org/2.0/repositories/example/webui/pullrequests/{}"
NOW = datetime(2026, 10, 13, 12, 0)


def update(state: str, head: str, at: str) -> dict[str, Any]:
    return {"update": {"state": state, "date": at, "source": {"commit": {"hash": head}}}}


class FakeApi:
    """Bitbucket's answers by URL, and the URLs asked for."""

    def __init__(self) -> None:
        self.asked: list[str] = []
        self.answers: dict[str, Any] = {}

    def add(self, number: int, state: str, activity: list[dict[str, Any]], participants: list[dict[str, Any]] = []) -> None:
        self.answers[API.format(number)] = {
            "state": state,
            "created_on": "2026-10-06T10:00:00.000000+00:00",
            "updated_on": "2026-10-08T10:00:00.000000+00:00",
            "participants": participants,
        }
        # Activity comes in two pages, newest first, the way Bitbucket pages it.
        first = API.format(number) + "/activity?pagelen=50"
        second = first + "&page=2"
        self.answers[first] = {"values": activity[:1], "next": second}
        self.answers[second] = {"values": activity[1:]}

    def __call__(self, url: str, token: str) -> Any:
        assert token == "secret"
        self.asked.append(url)
        return self.answers[url]


def test_a_merged_pull_request_someone_pushed_to_is_merged_with_changes() -> None:
    api = FakeApi()
    api.add(
        550,
        "MERGED",
        [
            update("MERGED", "b", "2026-10-07T09:15:00.000000+00:00"),
            {"approval": {"date": "2026-10-07T09:14:00.000000+00:00"}},
            update("OPEN", "b", "2026-10-07T09:13:00.000000+00:00"),
            update("OPEN", "a", "2026-10-06T10:00:00.000000+00:00"),
        ],
        [{"approved": True, "state": "approved"}, {"approved": False, "state": "changes_requested"}],
    )

    pr = Bitbucket("secret", api).pull_request(URL.format(550), NOW)

    assert (pr.fate, pr.pushes_after_opening, pr.approvals, pr.changes_requested) == (Fate.MERGED_CHANGED, 1, 1, 1)
    # Closed when it was merged, not when it was last touched.
    assert pr.closed - pr.opened == timedelta(days=0, hours=23, minutes=15)


def test_merged_as_pushed_open_and_declined() -> None:
    api = FakeApi()
    api.add(1, "MERGED", [update("MERGED", "a", "2026-10-07T10:00:00.000000+00:00"), update("OPEN", "a", "2026-10-06T10:00:00.000000+00:00")])
    api.add(2, "OPEN", [update("OPEN", "a", "2026-10-06T10:00:00.000000+00:00")])
    api.add(3, "DECLINED", [update("DECLINED", "a", "2026-10-06T12:00:00.000000+00:00")])
    client = Bitbucket("secret", api)

    fates = [client.pull_request(URL.format(n), NOW) for n in (1, 2, 3)]

    assert [pr.fate for pr in fates] == [Fate.MERGED_AS_IS, Fate.OPEN, Fate.DECLINED]
    assert fates[1].closed is None


def test_the_cache_fetches_a_closed_pull_request_once_and_an_open_one_when_stale(tmp_path: Path) -> None:
    api = FakeApi()
    api.add(1, "MERGED", [update("OPEN", "a", "2026-10-06T10:00:00.000000+00:00")])
    api.add(2, "OPEN", [update("OPEN", "a", "2026-10-06T10:00:00.000000+00:00")])
    path = tmp_path / "cache.json"
    urls = [URL.format(1), URL.format(2), "https://example.com/not-a-pull-request"]

    errors = PullRequests(path, Bitbucket("secret", api)).refresh(urls, NOW)
    assert len(errors) == 1 and "not a Bitbucket pull request" in errors[0]
    asked = len(api.asked)

    # A new app, the same cache file: within ten minutes nothing is fetched again.
    cache = PullRequests(path, Bitbucket("secret", api))
    cache.refresh(urls[:2], NOW + timedelta(minutes=5))
    assert len(api.asked) == asked
    # Later only the open one is.
    cache.refresh(urls[:2], NOW + timedelta(minutes=11))
    assert all(url.startswith(API.format(2)) for url in api.asked[asked:])
    assert PullRequests(path).get(URL.format(1)).fate is Fate.MERGED_AS_IS


def test_without_a_client_the_cache_is_all_there_is(tmp_path: Path) -> None:
    cache = PullRequests(tmp_path / "cache.json")

    assert (cache.connected, cache.refresh([URL.format(1)], NOW), cache.get(URL.format(1))) == (False, [], None)
