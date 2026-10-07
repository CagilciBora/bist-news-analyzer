from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Stock
from app.services.stock_seed import (
    DEFAULT_STOCKS_FILE,
    StockSeed,
    StockSeedFile,
    load_stock_seeds,
    upsert_stocks,
)

INITIAL_TICKERS = {"THYAO", "ASELS", "GARAN", "AKBNK", "BIMAS", "EREGL", "KCHOL", "SISE", "TUPRS", "FROTO"}


def test_default_config_contains_initial_list() -> None:
    seeds = load_stock_seeds(DEFAULT_STOCKS_FILE)

    assert {s.ticker for s in seeds} == INITIAL_TICKERS
    assert all(s.aliases for s in seeds), "every stock needs at least one alias for news matching"


def test_aliases_are_stripped_and_deduplicated() -> None:
    seed = StockSeed(ticker="THYAO", name="THY", aliases=[" THY ", "thy", "", "Türk Hava Yolları"])

    assert seed.aliases == ["THY", "Türk Hava Yolları"]


@pytest.mark.parametrize("ticker", ["thyao", "TOOLONGX", "TH", "TH-AO"])
def test_invalid_ticker_is_rejected(ticker: str) -> None:
    with pytest.raises(ValidationError):
        StockSeed(ticker=ticker, name="x")


def test_duplicate_tickers_in_file_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate tickers: THYAO"):
        StockSeedFile.model_validate(
            {"stocks": [{"ticker": "THYAO", "name": "a"}, {"ticker": "THYAO", "name": "b"}]}
        )


def test_load_from_custom_file(tmp_path: Path) -> None:
    path = tmp_path / "stocks.yaml"
    path.write_text(
        "stocks:\n  - ticker: PGSUS\n    name: Pegasus\n    aliases: [Pegasus]\n", encoding="utf-8"
    )

    assert [s.ticker for s in load_stock_seeds(path)] == ["PGSUS"]


def test_upsert_is_idempotent(db_session: Session) -> None:
    seeds = load_stock_seeds()

    first = upsert_stocks(db_session, seeds)
    second = upsert_stocks(db_session, seeds)

    assert set(first.inserted) == INITIAL_TICKERS and first.updated == []
    assert second.inserted == [] and set(second.updated) == INITIAL_TICKERS
    assert db_session.scalar(select(func.count()).select_from(Stock)) == len(INITIAL_TICKERS)


def test_upsert_updates_existing_and_inserts_new(db_session: Session) -> None:
    upsert_stocks(db_session, [StockSeed(ticker="THYAO", name="Old", aliases=["THY"])])

    result = upsert_stocks(
        db_session,
        [
            StockSeed(ticker="THYAO", name="Türk Hava Yolları A.O.", aliases=["THY", "Turkish Airlines"]),
            StockSeed(ticker="PGSUS", name="Pegasus", aliases=["Pegasus"], is_active=False),
        ],
    )

    assert result.inserted == ["PGSUS"] and result.updated == ["THYAO"]
    thy = db_session.scalars(select(Stock).where(Stock.ticker == "THYAO")).one()
    assert thy.name == "Türk Hava Yolları A.O."
    assert thy.aliases == ["THY", "Turkish Airlines"]
    pgsus = db_session.scalars(select(Stock).where(Stock.ticker == "PGSUS")).one()
    assert pgsus.is_active is False
