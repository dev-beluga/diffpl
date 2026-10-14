"""HTTP fetching with a disk cache, a request rate limit and retries.

Every response carries `fetched_at`, the UTC time the server answered. A cache hit returns the
original `fetched_at`, so downstream `as_of` values reflect when the data was observed, not
when it was read from disk.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class Fetched:
    url: str
    status: int
    body: bytes
    fetched_at: datetime
    from_cache: bool

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


class FetchError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class CachedFetcher:
    """GET requests with at most one request per `min_interval` seconds.

    `ttl=None` caches forever, which suits content pinned to a commit.
    """

    def __init__(
        self,
        cache_dir: Path,
        *,
        min_interval: float = 1.0,
        max_retries: int = 4,
        timeout: float = 30.0,
        user_agent: str = "diffpl/0.1 (+https://github.com/dev-beluga/diffpl)",
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cache_dir = cache_dir
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._clock = clock
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request: float | None = None
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent},
            transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CachedFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get(self, url: str, *, ttl: timedelta | None = timedelta(hours=1)) -> Fetched:
        cached = self._read_cache(url, ttl)
        if cached is not None:
            return cached
        fetched = self._request(url)
        self._write_cache(fetched)
        return fetched

    def _cache_paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / f"{key}.body", self.cache_dir / f"{key}.json"

    def _read_cache(self, url: str, ttl: timedelta | None) -> Fetched | None:
        body_path, meta_path = self._cache_paths(url)
        if not (body_path.exists() and meta_path.exists()):
            return None
        meta = json.loads(meta_path.read_text())
        fetched_at = datetime.fromisoformat(meta["fetched_at"])
        if ttl is not None and self._clock() - fetched_at > ttl:
            return None
        return Fetched(url, meta["status"], body_path.read_bytes(), fetched_at, from_cache=True)

    def _write_cache(self, fetched: Fetched) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        body_path, meta_path = self._cache_paths(fetched.url)
        body_path.write_bytes(fetched.body)
        meta = {"url": fetched.url, "status": fetched.status, "fetched_at": fetched.fetched_at}
        meta_path.write_text(json.dumps(meta, default=datetime.isoformat))

    def _wait_for_slot(self) -> None:
        if self._last_request is not None:
            wait = self.min_interval - (self._monotonic() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        self._last_request = self._monotonic()

    def _request(self, url: str) -> Fetched:
        for attempt in range(self.max_retries + 1):
            self._wait_for_slot()
            try:
                response = self._client.get(url)
            except httpx.TransportError as exc:
                if attempt == self.max_retries:
                    raise FetchError(f"GET {url} failed: {exc}") from exc
            else:
                if response.status_code == 200:
                    return Fetched(url, 200, response.content, self._clock(), from_cache=False)
                if response.status_code not in RETRY_STATUSES or attempt == self.max_retries:
                    raise FetchError(
                        f"GET {url} returned {response.status_code}", response.status_code
                    )
            self._sleep(2.0**attempt)
        raise AssertionError("unreachable")
