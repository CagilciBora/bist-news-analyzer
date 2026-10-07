from pathlib import Path

import httpx
import pytest
import respx

from app.collectors.http import PoliteHttpClient

URL_A = "https://example.test/a"
URL_B = "https://example.test/b"


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _client(
    clock: FakeClock,
    cache_dir: Path | None = None,
    *,
    min_interval: float = 3.0,
    cache_ttl: float = 1800.0,
) -> PoliteHttpClient:
    return PoliteHttpClient(
        user_agent="test-agent/1.0",
        cache_dir=cache_dir,
        min_interval=min_interval,
        cache_ttl=cache_ttl,
        clock=clock,
        sleep=clock.sleep,
    )


@respx.mock
def test_sends_user_agent() -> None:
    route = respx.get(URL_A).respond(text="ok")

    with _client(FakeClock()) as http:
        http.get_text(URL_A)

    assert route.calls.last.request.headers["User-Agent"] == "test-agent/1.0"


@respx.mock
def test_waits_min_interval_between_requests() -> None:
    respx.get(URL_A).respond(text="a")
    respx.get(URL_B).respond(text="b")
    clock = FakeClock()

    with _client(clock, min_interval=3.0) as http:
        http.get_text(URL_A)
        clock.now += 1.0  # only 1s passes before the next request
        http.get_text(URL_B)

    assert clock.sleeps == [pytest.approx(2.0)]


@respx.mock
def test_cache_hit_skips_network(tmp_path: Path) -> None:
    route = respx.get(URL_A).respond(text="body")

    with _client(FakeClock(), cache_dir=tmp_path) as http:
        assert http.get_text(URL_A) == "body"
        assert http.get_text(URL_A) == "body"
        assert http.network_requests == 1
    assert route.call_count == 1


@respx.mock
def test_expired_cache_refetches(tmp_path: Path) -> None:
    route = respx.get(URL_A).respond(text="body")

    with _client(FakeClock(), cache_dir=tmp_path, cache_ttl=0.0) as http:
        http.get_text(URL_A)
        http.get_text(URL_A)

    assert route.call_count == 2


@respx.mock
def test_http_errors_raise_and_are_not_cached(tmp_path: Path) -> None:
    respx.get(URL_A).respond(status_code=503)

    with _client(FakeClock(), cache_dir=tmp_path) as http, pytest.raises(httpx.HTTPStatusError):
        http.get_text(URL_A)

    assert list(tmp_path.iterdir()) == []
