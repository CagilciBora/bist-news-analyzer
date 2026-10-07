import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.http import PoliteHttpClient
from app.collectors.kap import (
    DISCLOSURE_QUERY_URL,
    ISSUER_SCORE,
    QUERY_PAGE_REFERER,
    RELATED_SCORE,
    KapCollector,
    KapDisclosure,
    match_disclosure,
    parse_disclosures,
)
from app.models import MatchMethod, NewsItem, NewsStockLink, SourceType, Stock

FIXTURE = (Path(__file__).parent / "fixtures" / "kap_disclosures_sample.json").read_text(encoding="utf-8")
TODAY = date(2026, 10, 7)


def _by_index(disclosures: list[KapDisclosure]) -> dict[int, KapDisclosure]:
    return {d.index: d for d in disclosures}


def test_parse_converts_istanbul_time_to_utc_and_splits_codes() -> None:
    aselsan = _by_index(parse_disclosures(FIXTURE))[1672652]

    assert aselsan.published_at.astimezone(UTC) == datetime(2026, 10, 6, 6, 15, 33, tzinfo=UTC)
    assert aselsan.issuer_codes == ["ASELS"]
    assert aselsan.subject == "Yeni İş İlişkisi"


def test_parse_skips_malformed_entries() -> None:
    body = json.dumps([{"disclosureIndex": 1, "publishDate": "not a date"}, json.loads(FIXTURE)[0]])

    assert len(parse_disclosures(body)) == 1


def test_to_collected_builds_title_link_and_type() -> None:
    news = _by_index(parse_disclosures(FIXTURE))[1672652].to_collected()

    assert news.source_type is SourceType.KAP
    assert news.title == "Yeni İş İlişkisi: Sözleşme İmzalanması"
    assert news.url == "https://www.kap.org.tr/tr/Bildirim/1672652"
    assert news.kap_disclosure_type == "Yeni İş İlişkisi"


def test_title_does_not_repeat_identical_summary() -> None:
    mass = _by_index(parse_disclosures(FIXTURE))[1671000].to_collected()

    assert mass.title == "SPK İşlem Yasağı Nedeniyle Pay Duyurusu"


def test_same_subject_from_different_companies_hashes_differently() -> None:
    disclosures = _by_index(parse_disclosures(FIXTURE))
    garan, akbnk = disclosures[1672971].to_collected(), disclosures[1672972].to_collected()

    assert garan.title == akbnk.title and garan.published_at == akbnk.published_at
    assert garan.content_hash() != akbnk.content_hash()


@pytest.fixture
def tracked() -> dict[str, Stock]:
    stocks = [Stock(id=i, ticker=t, name=t) for i, t in enumerate(["THYAO", "ASELS", "GARAN", "AKBNK"], 1)]
    return {s.ticker: s for s in stocks}


def test_issuer_is_matched(tracked: dict[str, Stock]) -> None:
    garan = _by_index(parse_disclosures(FIXTURE))[1672971]  # stockCodes "GARAN, TGB"

    [match] = match_disclosure(garan, tracked)

    assert (match.ticker, match.method, match.score) == ("GARAN", MatchMethod.KAP, ISSUER_SCORE)


def test_few_related_stocks_are_matched_with_lower_score(tracked: dict[str, Stock]) -> None:
    joint_venture = _by_index(parse_disclosures(FIXTURE))[2573980]  # issuer TGSAS, related THYAO

    [match] = match_disclosure(joint_venture, tracked)

    assert (match.ticker, match.score) == ("THYAO", RELATED_SCORE)


def test_market_wide_announcements_are_ignored(tracked: dict[str, Stock]) -> None:
    mass = _by_index(parse_disclosures(FIXTURE))[1671000]  # ~150 related stocks, no issuer code

    assert match_disclosure(mass, tracked) == []


@pytest.fixture
def db_stocks(db_session: Session) -> list[Stock]:
    rows = [
        Stock(ticker="THYAO", name="THY"),
        Stock(ticker="ASELS", name="Aselsan"),
        Stock(ticker="GARAN", name="Garanti"),
        Stock(ticker="AKBNK", name="Akbank", is_active=False),
    ]
    db_session.add_all(rows)
    db_session.flush()
    return rows


def _collector() -> KapCollector:
    http = PoliteHttpClient(user_agent="test", min_interval=0, sleep=lambda _: None)
    return KapCollector(http, lookback_days=1, today=TODAY)


@respx.mock
def test_collect_sends_one_request_for_the_date_range(db_session: Session, db_stocks: list[Stock]) -> None:
    route = respx.post(DISCLOSURE_QUERY_URL).respond(text=FIXTURE)

    _collector().collect(db_session)

    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["Referer"] == QUERY_PAGE_REFERER
    body = json.loads(request.content)
    assert (body["fromDate"], body["toDate"]) == ("2026-10-06", "2026-10-07")
    assert body["mkkMemberOidList"] == []


@respx.mock
def test_collect_stores_tracked_disclosures_and_is_idempotent(
    db_session: Session, db_stocks: list[Stock]
) -> None:
    respx.post(DISCLOSURE_QUERY_URL).respond(text=FIXTURE)
    collector = _collector()

    first = collector.collect(db_session)
    second = collector.collect(db_session)

    # GARAN, ASELS (issuers) and the TGSAS joint venture (related: THYAO).
    # AKBNK is inactive; the mass announcement and unrelated disclosures are skipped.
    assert (first.disclosures, first.inserted, first.unmatched) == (7, 3, 4)
    assert (second.inserted, second.duplicates) == (0, 3)
    assert db_session.scalar(select(func.count()).select_from(NewsItem)) == 3
    assert db_session.scalar(select(func.count()).select_from(NewsStockLink)) == 3
    sources = set(db_session.scalars(select(NewsItem.source_type)))
    assert sources == {SourceType.KAP}


@respx.mock
def test_collect_survives_errors(db_session: Session, db_stocks: list[Stock]) -> None:
    respx.post(DISCLOSURE_QUERY_URL).respond(status_code=666, text="<html>WAF</html>")

    stats = _collector().collect(db_session)

    assert stats.failed is True and stats.inserted == 0


@respx.mock
def test_collect_survives_non_json_body(db_session: Session, db_stocks: list[Stock]) -> None:
    respx.post(DISCLOSURE_QUERY_URL).respond(text="<html>maintenance</html>")

    assert _collector().collect(db_session).failed is True
