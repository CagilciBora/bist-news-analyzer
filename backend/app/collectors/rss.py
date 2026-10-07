"""Google News RSS collector.

One query per active stock (ticker OR aliases, limited to the last N days), so a full
run costs ~one request per stock. Only headline, source, date and link are kept.
"""

import calendar
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.http import PoliteHttpClient
from app.collectors.matching import StockMatcher
from app.collectors.text import strip_source_suffix
from app.models import SourceType, Stock
from app.services.news_store import CollectedNews, store_news

logger = logging.getLogger(__name__)

GOOGLE_NEWS_SEARCH = "https://news.google.com/rss/search"
FALLBACK_SOURCE_NAME = "Google News"


def build_query_url(stock: Stock, lookback_days: int) -> str:
    terms = " OR ".join(f'"{term}"' for term in [stock.ticker, *stock.aliases])
    params = {"q": f"{terms} when:{lookback_days}d", "hl": "tr", "gl": "TR", "ceid": "TR:tr"}
    return f"{GOOGLE_NEWS_SEARCH}?{urlencode(params, quote_via=quote)}"


def parse_feed(xml: str) -> list[CollectedNews]:
    """Parse a Google News RSS document. Entries without link, title or date are skipped."""
    items: list[CollectedNews] = []
    for entry in feedparser.parse(xml).entries:
        link, raw_title, published = entry.get("link"), entry.get("title"), entry.get("published_parsed")
        if not (link and raw_title and published):
            continue
        source_name = (entry.get("source") or {}).get("title") or FALLBACK_SOURCE_NAME
        items.append(
            CollectedNews(
                source_type=SourceType.RSS,
                source_name=source_name,
                url=link,
                title=strip_source_suffix(raw_title, source_name),
                # feedparser normalizes dates to a UTC struct_time.
                published_at=datetime.fromtimestamp(calendar.timegm(published), tz=UTC),
            )
        )
    return items


@dataclass
class CollectStats:
    queries: int = 0
    failed_queries: int = 0
    entries: int = 0
    inserted: int = 0
    duplicates: int = 0
    unmatched: int = 0


class RssCollector:
    def __init__(self, http: PoliteHttpClient, *, lookback_days: int = 7) -> None:
        self._http = http
        self._lookback_days = lookback_days

    def collect(self, session: Session) -> CollectStats:
        """Fetch every active stock's feed and store new, matched headlines.

        Commits after each stock so one failing query does not discard the others.
        """
        stocks = list(session.scalars(select(Stock).where(Stock.is_active).order_by(Stock.ticker)))
        matcher = StockMatcher(stocks)
        stats = CollectStats()

        for stock in stocks:
            stats.queries += 1
            try:
                xml = self._http.get_text(build_query_url(stock, self._lookback_days))
            except httpx.HTTPError as exc:
                stats.failed_queries += 1
                logger.warning("RSS fetch failed for %s: %s", stock.ticker, exc)
                continue

            for news in parse_feed(xml):
                stats.entries += 1
                # Match against all tracked stocks: one headline can concern several.
                matches = matcher.match(news.title)
                if not matches:
                    stats.unmatched += 1
                elif store_news(session, news, matches) is None:
                    stats.duplicates += 1
                else:
                    stats.inserted += 1
            session.commit()

        logger.info("RSS collection finished: %s", stats)
        return stats
