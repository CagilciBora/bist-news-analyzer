"""Match headlines to tracked stocks by ticker and alias with word-boundary checks.

Rules:
- Tickers ("THYAO") match case-sensitively against the *original* text, so an
  all-caps Turkish word like "ŞİŞE" can never be mistaken for the ticker SISE.
- Short all-caps aliases (acronyms such as "THY", "BİM") match after diacritic
  folding in all-caps or capitalized form only: "BİM", "BIM" and "Bim'de" match,
  the lowercase word "bim" does not.
- Other aliases ("Türk Hava Yolları") match case- and diacritic-insensitively.
- Boundaries are any non-word character, so Turkish suffixes after an apostrophe
  still match: "THY'nin", "Tüpraş’ın".
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.collectors.text import fold, fold_lower
from app.models import MatchMethod, Stock

TICKER_SCORE = 1.0
ALIAS_SCORE = 0.9
ACRONYM_SCORE = 0.8
_MAX_ACRONYM_LEN = 4


@dataclass(frozen=True)
class StockMatch:
    stock_id: int
    ticker: str
    method: MatchMethod
    score: float


@dataclass(frozen=True)
class _Pattern:
    regex: re.Pattern[str]
    method: MatchMethod
    score: float
    target: str  # "original" | "folded" | "folded_lower"


def _bounded(*terms: str) -> re.Pattern[str]:
    alternatives = "|".join(re.escape(term) for term in dict.fromkeys(terms))
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)")


def _is_acronym(alias: str) -> bool:
    return alias.isupper() and len(alias) <= _MAX_ACRONYM_LEN


class StockMatcher:
    def __init__(self, stocks: Iterable[Stock]) -> None:
        self._patterns: dict[tuple[int, str], list[_Pattern]] = {}
        for stock in stocks:
            patterns = [_Pattern(_bounded(stock.ticker), MatchMethod.TICKER, TICKER_SCORE, "original")]
            for alias in stock.aliases:
                if _is_acronym(alias):
                    folded = fold(alias)
                    patterns.append(
                        _Pattern(
                            _bounded(folded, folded.capitalize()), MatchMethod.ALIAS, ACRONYM_SCORE, "folded"
                        )
                    )
                else:
                    patterns.append(
                        _Pattern(_bounded(fold_lower(alias)), MatchMethod.ALIAS, ALIAS_SCORE, "folded_lower")
                    )
            self._patterns[(stock.id, stock.ticker)] = patterns

    def match(self, text: str) -> list[StockMatch]:
        """Return at most one match per stock (the highest-scoring rule that fired)."""
        variants = {"original": text, "folded": fold(text), "folded_lower": fold_lower(text)}
        matches: list[StockMatch] = []
        for (stock_id, ticker), patterns in self._patterns.items():
            hits = [p for p in patterns if p.regex.search(variants[p.target])]
            if hits:
                best = max(hits, key=lambda p: p.score)
                matches.append(StockMatch(stock_id, ticker, best.method, best.score))
        return matches
