from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.http import PoliteHttpClient
from app.collectors.rss import GOOGLE_NEWS_SEARCH, RssCollector, build_query_url, parse_feed
from app.models import MatchMethod, NewsItem, NewsStockLink, SourceType, Stock

FIXTURE = (Path(__file__).parent / "fixtures" / "google_news_sample.xml").read_text(encoding="utf-8")
EMPTY_FEED = '<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>'


def test_build_query_url_quotes_terms_and_limits_period() -> None:
    stock = Stock(ticker="THYAO", name="THY", aliases=["Türk Hava Yolları", "THY"])

    url = build_query_url(stock, lookback_days=7)

    assert url.startswith(GOOGLE_NEWS_SEARCH)
    params = parse_qs(urlparse(url).query)
    assert params["q"] == ['"THYAO" OR "Türk Hava Yolları" OR "THY" when:7d']
    assert params["hl"] == ["tr"] and params["ceid"] == ["TR:tr"]


def test_parse_feed_extracts_metadata_only() -> None:
    items = parse_feed(FIXTURE)

    assert len(items) == 6  # the entry without a date is skipped
    first = items[0]
    assert first.title == "THY'de 39 bin çalışan maaşında indirimi kabul etti"
    assert first.source_name == "Sözcü"
    assert first.source_type is SourceType.RSS
    assert first.url == "https://news.google.com/rss/articles/AAA111?oc=5"
    assert first.published_at == datetime(2026, 10, 5, 11, 1, tzinfo=UTC)


@pytest.fixture
def stocks(db_session: Session) -> dict[str, Stock]:
    rows = [
        Stock(ticker="THYAO", name="Türk Hava Yolları A.O.", aliases=["Türk Hava Yolları", "THY"]),
        Stock(ticker="TUPRS", name="Tüpraş", aliases=["Tüpraş"]),
        Stock(ticker="GARAN", name="Garanti", aliases=["Garanti BBVA"]),
        Stock(ticker="KCHOL", name="Koç Holding", aliases=["Koç Holding"], is_active=False),
    ]
    db_session.add_all(rows)
    db_session.flush()
    return {s.ticker: s for s in rows}


def _mock_feeds(thyao_feed: str) -> respx.Route:
    """THYAO's query returns the fixture; every other stock's query returns an empty feed."""
    route = respx.get(url__regex=r".*%22THYAO%22.*").respond(text=thyao_feed)  # routes match in order
    respx.get(url__regex=r"^https://news\.google\.com/rss/search.*").respond(text=EMPTY_FEED)
    return route


def _collector() -> RssCollector:
    http = PoliteHttpClient(user_agent="test", min_interval=0, cache_dir=None, sleep=lambda _: None)
    return RssCollector(http)


@respx.mock
def test_collect_stores_matched_news_and_skips_the_rest(
    db_session: Session, stocks: dict[str, Stock]
) -> None:
    _mock_feeds(FIXTURE)

    stats = _collector().collect(db_session)

    assert stats.queries == 3  # inactive KCHOL is not queried
    assert stats.entries == 6
    # Two "turizm zirvesi" titles are the same story -> one duplicate.
    # "Fon soruşturması" and "Yeni uçuş noktaları - Garanti BBVA Yatırım" do not match any stock.
    assert (stats.inserted, stats.duplicates, stats.unmatched) == (3, 1, 2)

    titles = set(db_session.scalars(select(NewsItem.title)))
    assert "Yeni uçuş noktaları açıklandı" not in titles  # source name must not cause a GARAN match


@respx.mock
def test_headline_mentioning_two_stocks_is_linked_to_both(
    db_session: Session, stocks: dict[str, Stock]
) -> None:
    _mock_feeds(FIXTURE)
    _collector().collect(db_session)

    item = db_session.scalars(select(NewsItem).where(NewsItem.title.startswith("Tüpraş’ın"))).one()
    links = {link.stock_id: link for link in item.stock_links}
    assert set(links) == {stocks["TUPRS"].id, stocks["THYAO"].id}
    assert links[stocks["THYAO"].id].match_method is MatchMethod.TICKER
    assert links[stocks["TUPRS"].id].match_method is MatchMethod.ALIAS


@respx.mock
def test_second_run_inserts_nothing(db_session: Session, stocks: dict[str, Stock]) -> None:
    _mock_feeds(FIXTURE)
    collector = _collector()

    collector.collect(db_session)
    second = collector.collect(db_session)

    assert second.inserted == 0 and second.duplicates == 4
    assert db_session.scalar(select(func.count()).select_from(NewsItem)) == 3
    assert db_session.scalar(select(func.count()).select_from(NewsStockLink)) == 4


@respx.mock
def test_failed_query_does_not_stop_other_stocks(db_session: Session, stocks: dict[str, Stock]) -> None:
    respx.get(url__regex=r".*%22THYAO%22.*").respond(status_code=503)
    respx.get(url__regex=r".*%22TUPRS%22.*").respond(text=FIXTURE)
    respx.get(url__regex=r".*%22GARAN%22.*").respond(text=EMPTY_FEED)

    stats = _collector().collect(db_session)

    assert stats.failed_queries == 1
    assert stats.inserted == 3
