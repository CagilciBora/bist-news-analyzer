import pytest

from app.collectors.matching import ACRONYM_SCORE, ALIAS_SCORE, TICKER_SCORE, StockMatcher
from app.models import MatchMethod, Stock


def _stock(id_: int, ticker: str, *aliases: str) -> Stock:
    return Stock(id=id_, ticker=ticker, name=ticker, aliases=list(aliases))


@pytest.fixture
def matcher() -> StockMatcher:
    return StockMatcher(
        [
            _stock(1, "THYAO", "Türk Hava Yolları", "THY", "Turkish Airlines"),
            _stock(2, "SISE", "Şişecam"),
            _stock(3, "BIMAS", "BİM", "Birleşik Mağazalar"),
            _stock(4, "TUPRS", "Tüpraş"),
            _stock(5, "GARAN", "Garanti BBVA", "Garanti Bankası"),
        ]
    )


def _tickers(matcher: StockMatcher, text: str) -> set[str]:
    return {m.ticker for m in matcher.match(text)}


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("THY'de 39 bin çalışan maaşında indirimi kabul etti", {"THYAO"}),
        ("THY’den Avrupa uçuşlarına kampanya", {"THYAO"}),
        ("Türk Hava Yolları’nın Hedef 12’si", {"THYAO"}),
        ("TÜRK HAVA YOLLARI rekor kırdı", {"THYAO"}),
        ("#THYAO hissesinde hacim arttı", {"THYAO"}),
        ("Tupras rafinerisinde bakım", {"TUPRS"}),
        ("Tüpraş’ın kâr payı önerisi", {"TUPRS"}),
        ("BIM yeni mağaza açtı", {"BIMAS"}),
        ("Bim'de bu hafta aktüel ürünler", {"BIMAS"}),
        ("Thy yeni hat açtı", {"THYAO"}),
        ("Sisecam ihracatını artırdı", {"SISE"}),
        ("Akbank ve Garanti BBVA kredi faizlerini güncelledi", {"GARAN"}),
        ("Tüpraş ve THY endekse yön verdi", {"TUPRS", "THYAO"}),
    ],
)
def test_matches(matcher: StockMatcher, title: str, expected: set[str]) -> None:
    assert _tickers(matcher, title) == expected


@pytest.mark.parametrize(
    "title",
    [
        "ŞİŞE VE CAM SANAYİSİNDE YENİ DÖNEM",  # folds to "SISE" but is a word, not the ticker
        "Bu şişe geri dönüştürülebilir",
        "Bimbo yeni ürün tanıttı",  # 'bim' inside a word
        "bim kelimesi küçük harfle",  # acronyms: all-caps or capitalized only
        "tHy karışık harf",
        "THYAOX diye bir kod yok",
        "Garanti süresi uzatıldı",  # generic word, not an alias
        "Fon soruşturmasında dev virman tablosu",
    ],
)
def test_does_not_match(matcher: StockMatcher, title: str) -> None:
    assert _tickers(matcher, title) == set()


def test_best_rule_wins_per_stock(matcher: StockMatcher) -> None:
    [match] = matcher.match("THYAO: Türk Hava Yolları (THY) yolcu sayısını açıkladı")

    assert match.method is MatchMethod.TICKER and match.score == TICKER_SCORE


def test_scores_by_rule(matcher: StockMatcher) -> None:
    [alias] = matcher.match("Türk Hava Yolları yeni hat açtı")
    [acronym] = matcher.match("THY yeni hat açtı")

    assert (alias.method, alias.score) == (MatchMethod.ALIAS, ALIAS_SCORE)
    assert (acronym.method, acronym.score) == (MatchMethod.ALIAS, ACRONYM_SCORE)
