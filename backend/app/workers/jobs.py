"""Job functions run by the worker scheduler (and callable manually)."""

import logging

from app.collectors.http import PoliteHttpClient
from app.collectors.kap import KapCollector, KapCollectStats
from app.collectors.rss import CollectStats, RssCollector
from app.core.config import get_settings
from app.core.db import SessionLocal

logger = logging.getLogger(__name__)


def _http_client() -> PoliteHttpClient:
    settings = get_settings()
    return PoliteHttpClient(
        user_agent=settings.http_user_agent,
        min_interval=settings.http_min_interval_seconds,
        cache_dir=settings.http_cache_dir,
        cache_ttl=settings.http_cache_ttl_seconds,
    )


def collect_rss() -> CollectStats:
    settings = get_settings()
    with _http_client() as http, SessionLocal() as session:
        return RssCollector(http, lookback_days=settings.rss_lookback_days).collect(session)


def collect_kap() -> KapCollectStats:
    settings = get_settings()
    with _http_client() as http, SessionLocal() as session:
        return KapCollector(http, lookback_days=settings.kap_lookback_days).collect(session)
