from sqlalchemy import Boolean, String, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    # Alternative names used for matching news to this stock (e.g. "THY" for THYAO).
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(100)), server_default=text("'{}'"))
    sector: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    def __repr__(self) -> str:
        return f"Stock(ticker={self.ticker!r})"
