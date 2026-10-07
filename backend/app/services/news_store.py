"""Persist collected news items and their stock links, skipping duplicates."""

import hashlib
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.collectors.matching import StockMatch
from app.collectors.text import content_hash as title_content_hash
from app.models import NewsItem, NewsStockLink, SourceType


@dataclass(frozen=True)
class CollectedNews:
    source_type: SourceType
    source_name: str
    url: str
    title: str
    published_at: datetime
    kap_disclosure_type: str | None = None
    # Overrides title-based de-duplication when the source has a stable id
    # (KAP disclosures share generic titles, so they dedupe by disclosure number).
    dedupe_key: str | None = None

    def content_hash(self) -> str:
        if self.dedupe_key is not None:
            return hashlib.sha256(self.dedupe_key.encode("utf-8")).hexdigest()
        return title_content_hash(self.title, self.published_at)


def store_news(session: Session, news: CollectedNews, matches: list[StockMatch]) -> int | None:
    """Insert a news item with its stock links. Does not commit.

    Returns the new item's id, or None if an item with the same URL or content hash
    already exists (in which case nothing is written).
    """
    stmt = (
        insert(NewsItem)
        .values(
            source_type=news.source_type,
            source_name=news.source_name,
            url=news.url,
            title=news.title,
            published_at=news.published_at,
            content_hash=news.content_hash(),
            kap_disclosure_type=news.kap_disclosure_type,
        )
        .on_conflict_do_nothing()  # any unique constraint: url or content_hash
        .returning(NewsItem.id)
    )
    news_id = session.execute(stmt).scalar_one_or_none()
    if news_id is None:
        return None

    session.add_all(
        NewsStockLink(news_id=news_id, stock_id=m.stock_id, match_method=m.method, match_score=m.score)
        for m in matches
    )
    session.flush()
    return news_id
