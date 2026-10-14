from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from diffpl.ingest.http import CachedFetcher, FetchError


class FakeTime:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
        self.mono = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> datetime:
        return self.now

    def monotonic(self) -> float:
        return self.mono

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.mono += seconds
        self.now += timedelta(seconds=seconds)


def make_fetcher(
    tmp_path: Path, transport: httpx.MockTransport, t: FakeTime, min_interval: float = 1.0
) -> CachedFetcher:
    return CachedFetcher(
        tmp_path,
        min_interval=min_interval,
        transport=transport,
        clock=t.clock,
        sleep=t.sleep,
        monotonic=t.monotonic,
    )


def test_cache_hit_keeps_original_fetched_at(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b'{"a": 1}')

    t = FakeTime()
    with make_fetcher(tmp_path, httpx.MockTransport(handler), t) as fetcher:
        first = fetcher.get("https://x.test/a")
        t.now += timedelta(minutes=10)
        second = fetcher.get("https://x.test/a")

    assert len(calls) == 1
    assert second.from_cache
    assert second.fetched_at == first.fetched_at
    assert second.body == b'{"a": 1}'


def test_expired_cache_refetches(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b"x")

    t = FakeTime()
    with make_fetcher(tmp_path, httpx.MockTransport(handler), t) as fetcher:
        fetcher.get("https://x.test/a", ttl=timedelta(minutes=5))
        t.now += timedelta(minutes=6)
        fetched = fetcher.get("https://x.test/a", ttl=timedelta(minutes=5))

    assert len(calls) == 2
    assert not fetched.from_cache


def test_rate_limit_spaces_requests(tmp_path: Path) -> None:
    t = FakeTime()
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x"))
    with make_fetcher(tmp_path, transport, t, min_interval=1.5) as fetcher:
        fetcher.get("https://x.test/a")
        fetcher.get("https://x.test/b")

    assert t.sleeps == [1.5]


def test_retries_then_succeeds(tmp_path: Path) -> None:
    statuses = iter([429, 503, 200])
    transport = httpx.MockTransport(lambda r: httpx.Response(next(statuses), content=b"ok"))
    t = FakeTime()
    with make_fetcher(tmp_path, transport, t, min_interval=0) as fetcher:
        fetched = fetcher.get("https://x.test/a")

    assert fetched.status == 200
    assert t.sleeps == [1.0, 2.0]


def test_client_error_is_not_retried(tmp_path: Path) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(404)

    t = FakeTime()
    with (
        make_fetcher(tmp_path, httpx.MockTransport(handler), t) as fetcher,
        pytest.raises(FetchError, match="404"),
    ):
        fetcher.get("https://x.test/missing")
    assert len(calls) == 1
