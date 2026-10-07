from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class SourceType(StrEnum):
    RSS = "rss"
    KAP = "kap"


class MatchMethod(StrEnum):
    TICKER = "ticker"
    ALIAS = "alias"
    KAP = "kap"


def _str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    # VARCHAR + CHECK constraint storing the enum *values* (not names).
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda e: [m.value for m in e],
    )


class NewsItem(Base):
    """A news headline or KAP disclosure. Full article text is never stored (CLAUDE.md §2.4)."""

    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[SourceType] = mapped_column(_str_enum(SourceType, "source_type"))
    source_name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Hash of the normalized title + publish date; collapses the same story syndicated by many sites.
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    kap_disclosure_type: Mapped[str | None] = mapped_column(String(100))

    stock_links: Mapped[list["NewsStockLink"]] = relationship(
        back_populates="news", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"NewsItem(id={self.id!r}, title={self.title[:40]!r})"


class NewsStockLink(Base):
    __tablename__ = "news_stock_links"

    news_id: Mapped[int] = mapped_column(ForeignKey("news_items.id", ondelete="CASCADE"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    match_method: Mapped[MatchMethod] = mapped_column(_str_enum(MatchMethod, "match_method"))
    match_score: Mapped[float] = mapped_column(Float)

    news: Mapped[NewsItem] = relationship(back_populates="stock_links")
