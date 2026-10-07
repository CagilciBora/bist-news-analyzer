from datetime import UTC, datetime

import pytest

from app.collectors.text import content_hash, fold, fold_lower, strip_source_suffix

DAY = datetime(2026, 10, 5, 11, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "folded"),
    [
        ("Tüpraş", "Tupras"),
        ("BİM", "BIM"),
        ("Şişecam", "Sisecam"),
        ("Ereğli  Demir   Çelik", "Eregli Demir Celik"),
        ("Türkiye'nin İhracatı", "Turkiye'nin Ihracati"),
    ],
)
def test_fold_maps_turkish_letters_and_keeps_case(raw: str, folded: str) -> None:
    assert fold(raw) == folded


def test_fold_lower_handles_dotted_capital_i() -> None:
    # Plain str.lower() would turn "İ" into "i" + U+0307 and break matching.
    assert fold_lower("İSTANBUL") == "istanbul"


@pytest.mark.parametrize(
    ("title", "source", "expected"),
    [
        ("THY'den yeni hat - Sözcü", "Sözcü", "THY'den yeni hat"),
        (
            "THY’den ücretlere pike - Bülent Falakaoğlu - Evrensel.net",
            "Evrensel.net",
            "THY’den ücretlere pike - Bülent Falakaoğlu",
        ),
        ("Başlık - Başka", "Sözcü", "Başlık - Başka"),
        ("  Başlık  ", None, "Başlık"),
    ],
)
def test_strip_source_suffix(title: str, source: str | None, expected: str) -> None:
    assert strip_source_suffix(title, source) == expected


def test_content_hash_ignores_case_punctuation_and_diacritics() -> None:
    a = content_hash("Bakan Ersoy ve THY yönetiminden turizm zirvesi", DAY)
    b = content_hash("Bakan Ersoy ve THY Yönetiminden Turizm Zirvesi!", DAY.replace(hour=20))

    assert a == b


def test_content_hash_differs_across_days() -> None:
    assert content_hash("Borsa güne yükselişle başladı", DAY) != content_hash(
        "Borsa güne yükselişle başladı", DAY.replace(day=6)
    )
