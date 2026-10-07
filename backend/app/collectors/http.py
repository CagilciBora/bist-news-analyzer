"""A deliberately slow, caching HTTP client for scraping public sources politely.

- Identifies itself with a User-Agent.
- Waits at least `min_interval` seconds between network requests.
- Caches response bodies on disk for `cache_ttl` seconds, so re-runs during
  development (or overlapping jobs) do not hit the source again.
"""

import hashlib
import logging
import time
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Self

import httpx

logger = logging.getLogger(__name__)


class PoliteHttpClient:
    def __init__(
        self,
        *,
        user_agent: str,
        min_interval: float = 3.0,
        cache_dir: Path | None = None,
        cache_ttl: float = 1800.0,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )
        self._min_interval = min_interval
        self._cache_dir = cache_dir
        self._cache_ttl = cache_ttl
        self._clock = clock
        self._sleep = sleep
        self._last_request_at: float | None = None
        self.network_requests = 0

    def get_text(self, url: str) -> str:
        cached = self._read_cache(url)
        if cached is not None:
            logger.debug("cache hit: %s", url)
            return cached

        self._wait_for_slot()
        logger.info("GET %s", url)
        response = self._client.get(url)
        self._last_request_at = self._clock()
        self.network_requests += 1
        response.raise_for_status()

        self._write_cache(url, response.text)
        return response.text

    def _wait_for_slot(self) -> None:
        if self._last_request_at is None:
            return
        remaining = self._min_interval - (self._clock() - self._last_request_at)
        if remaining > 0:
            self._sleep(remaining)

    def _cache_path(self, url: str) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()}.txt"

    def _read_cache(self, url: str) -> str | None:
        path = self._cache_path(url)
        if path is None or not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self._cache_ttl:
            return None
        return path.read_text(encoding="utf-8")

    def _write_cache(self, url: str, body: str) -> None:
        path = self._cache_path(url)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
