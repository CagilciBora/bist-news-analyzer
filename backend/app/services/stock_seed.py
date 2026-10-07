"""Load the tracked-stock list from YAML and upsert it into the `stocks` table."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import literal_column
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Stock

DEFAULT_STOCKS_FILE = Path(__file__).resolve().parents[2] / "config" / "stocks.yaml"


class StockSeed(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ticker: str = Field(pattern=r"^[A-Z0-9]{3,6}$")
    name: str = Field(min_length=1)
    sector: str | None = None
    aliases: list[str] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("aliases")
    @classmethod
    def _clean_aliases(cls, aliases: list[str]) -> list[str]:
        # Strip, drop empties and case-insensitive duplicates while keeping order.
        seen: set[str] = set()
        cleaned: list[str] = []
        for alias in (a.strip() for a in aliases):
            if alias and alias.casefold() not in seen:
                seen.add(alias.casefold())
                cleaned.append(alias)
        return cleaned


class StockSeedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stocks: list[StockSeed]

    @field_validator("stocks")
    @classmethod
    def _unique_tickers(cls, stocks: list[StockSeed]) -> list[StockSeed]:
        tickers = [s.ticker for s in stocks]
        duplicates = sorted({t for t in tickers if tickers.count(t) > 1})
        if duplicates:
            raise ValueError(f"duplicate tickers: {', '.join(duplicates)}")
        return stocks


@dataclass
class SeedResult:
    inserted: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)


def load_stock_seeds(path: Path = DEFAULT_STOCKS_FILE) -> list[StockSeed]:
    with path.open(encoding="utf-8") as fh:
        return StockSeedFile.model_validate(yaml.safe_load(fh)).stocks


def upsert_stocks(session: Session, seeds: list[StockSeed]) -> SeedResult:
    """Insert new stocks and update existing ones by ticker. Does not commit.

    Stocks missing from `seeds` are left untouched; deactivate them via `is_active: false`.
    """
    result = SeedResult()
    if not seeds:
        return result

    base = insert(Stock).values([s.model_dump() for s in seeds])
    stmt = base.on_conflict_do_update(
        index_elements=[Stock.ticker],
        set_={col: base.excluded[col] for col in ("name", "sector", "aliases", "is_active")},
    ).returning(
        Stock.ticker,
        # xmax = 0 only for freshly inserted rows; a conflict update sets it.
        (literal_column("xmax") == 0).label("inserted"),
    )

    for ticker, inserted in session.execute(stmt):
        (result.inserted if inserted else result.updated).append(ticker)
    return result
