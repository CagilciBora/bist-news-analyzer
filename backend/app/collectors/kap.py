"""KAP (Kamuyu Aydınlatma Platformu) disclosure collector.

Uses the JSON endpoint behind KAP's public "Bildirim Sorgu" page. One POST returns
every disclosure in the date range for the whole market (~300/day, capped at 2000),
so a run costs a single request; filtering to tracked stocks happens client-side.
Only metadata is stored: subject, summary line, publisher, date and the public link.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.http import PoliteHttpClient
from app.collectors.matching import StockMatch
from app.models import MatchMethod, SourceType, Stock
from app.services.news_store import CollectedNews, store_news

logger = logging.getLogger(__name__)

KAP_BASE = "https://www.kap.org.tr"
DISCLOSURE_QUERY_URL = f"{KAP_BASE}/tr/api/disclosure/members/byCriteria"
QUERY_PAGE_REFERER = f"{KAP_BASE}/tr/bildirim-sorgu"
RESPONSE_CAP = 2000
KAP_TZ = ZoneInfo("Europe/Istanbul")
SOURCE_NAME = "KAP"

ISSUER_SCORE = 1.0
RELATED_SCORE = 0.7
# Market-wide announcements (e.g. MKK notices) list 100+ related stocks; those are noise.
MAX_RELATED_STOCKS = 3
_MAX_DISCLOSURE_TYPE_LEN = 200


def disclosure_url(disclosure_index: int) -> str:
    return f"{KAP_BASE}/tr/Bildirim/{disclosure_index}"


def _split_codes(raw: str | None) -> list[str]:
    return [code.strip() for code in re.split(r"[,;]", raw or "") if code.strip()]


def _title(subject: str, summary: str) -> str:
    """'Yeni İş İlişkisi' + 'Sözleşme İmzalanması' -> 'Yeni İş İlişkisi: Sözleşme İmzalanması'."""
    if not summary or summary.casefold() == subject.casefold():
        return subject
    return f"{subject}: {summary}"


@dataclass(frozen=True)
class KapDisclosure:
    index: int
    published_at: datetime
    publisher: str
    subject: str
    summary: str
    disclosure_class: str
    issuer_codes: list[str]
    related_codes: list[str]

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "KapDisclosure":
        local = datetime.strptime(raw["publishDate"], "%d.%m.%Y %H:%M:%S")
        return cls(
            index=int(raw["disclosureIndex"]),
            published_at=local.replace(tzinfo=KAP_TZ),
            publisher=(raw.get("kapTitle") or "").strip(),
            subject=(raw.get("subject") or "").strip(),
            summary=(raw.get("summary") or "").strip(),
            disclosure_class=(raw.get("disclosureClass") or "").strip(),
            issuer_codes=_split_codes(raw.get("stockCodes")),
            related_codes=_split_codes(raw.get("relatedStocks")),
        )

    def to_collected(self) -> CollectedNews:
        return CollectedNews(
            source_type=SourceType.KAP,
            source_name=SOURCE_NAME,
            url=disclosure_url(self.index),
            title=_title(self.subject, self.summary),
            published_at=self.published_at,
            kap_disclosure_type=self.subject[:_MAX_DISCLOSURE_TYPE_LEN] or None,
            dedupe_key=f"kap:{self.index}",
        )


def match_disclosure(disclosure: KapDisclosure, stocks_by_ticker: dict[str, Stock]) -> list[StockMatch]:
    """Link a disclosure to tracked stocks: the issuer always, related stocks only if few."""
    matches: dict[str, StockMatch] = {}
    related = disclosure.related_codes if len(disclosure.related_codes) <= MAX_RELATED_STOCKS else []
    for codes, score in ((related, RELATED_SCORE), (disclosure.issuer_codes, ISSUER_SCORE)):
        for code in codes:
            stock = stocks_by_ticker.get(code)
            if stock is not None:
                matches[code] = StockMatch(stock.id, stock.ticker, MatchMethod.KAP, score)
    return list(matches.values())


def parse_disclosures(body: str) -> list[KapDisclosure]:
    disclosures: list[KapDisclosure] = []
    for raw in json.loads(body):
        try:
            disclosures.append(KapDisclosure.from_api(raw))
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed KAP disclosure %r: %s", raw.get("disclosureIndex"), exc)
    return disclosures


@dataclass
class KapCollectStats:
    disclosures: int = 0
    inserted: int = 0
    duplicates: int = 0
    unmatched: int = 0
    failed: bool = False


class KapCollector:
    def __init__(
        self,
        http: PoliteHttpClient,
        *,
        lookback_days: int = 1,
        today: date | None = None,
    ) -> None:
        self._http = http
        self._lookback_days = lookback_days
        self._today = today

    def _date_range(self) -> tuple[date, date]:
        end = self._today or datetime.now(KAP_TZ).date()
        return end - timedelta(days=self._lookback_days), end

    def collect(self, session: Session) -> KapCollectStats:
        stats = KapCollectStats()
        start, end = self._date_range()
        payload = {
            "fromDate": start.isoformat(),
            "toDate": end.isoformat(),
            "mkkMemberOidList": [],
            "subjectList": [],
        }
        try:
            body = self._http.post_json(
                DISCLOSURE_QUERY_URL, payload, headers={"Referer": QUERY_PAGE_REFERER}
            )
            disclosures = parse_disclosures(body)
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.warning("KAP fetch failed for %s..%s: %s", start, end, exc)
            stats.failed = True
            return stats

        if len(disclosures) >= RESPONSE_CAP:
            logger.warning("KAP response hit the %d cap; shorten the lookback window", RESPONSE_CAP)

        stocks = session.scalars(select(Stock).where(Stock.is_active))
        stocks_by_ticker = {s.ticker: s for s in stocks}
        for disclosure in disclosures:
            stats.disclosures += 1
            matches = match_disclosure(disclosure, stocks_by_ticker)
            if not matches:
                stats.unmatched += 1
            elif store_news(session, disclosure.to_collected(), matches) is None:
                stats.duplicates += 1
            else:
                stats.inserted += 1
        session.commit()

        logger.info("KAP collection finished: %s", stats)
        return stats
