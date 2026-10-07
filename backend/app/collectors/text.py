"""Turkish-aware text normalization used for matching and de-duplication."""

import hashlib
import re
import unicodedata
from datetime import datetime

_TURKISH_TO_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
_NON_ALNUM = re.compile(r"[^0-9a-z]+")
_WHITESPACE = re.compile(r"\s+")


def fold(text: str) -> str:
    """Map Turkish letters/diacritics to ASCII, keeping case: 'Tüpraş' -> 'Tupras', 'BİM' -> 'BIM'.

    Done before lowercasing because Python lowercases 'İ' to 'i' + combining dot.
    """
    text = text.translate(_TURKISH_TO_ASCII)
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WHITESPACE.sub(" ", stripped).strip()


def fold_lower(text: str) -> str:
    return fold(text).lower()


def strip_source_suffix(title: str, source_name: str | None) -> str:
    """Google News titles look like 'Headline - Source'; drop the trailing source."""
    title = title.strip()
    if source_name:
        suffix = f" - {source_name.strip()}"
        if title.endswith(suffix):
            return title[: -len(suffix)].rstrip()
    return title


def content_hash(title: str, published_at: datetime) -> str:
    """Stable hash of a headline's normalized words plus its publication day (UTC).

    The same story republished by several sites on the same day hashes identically;
    a recurring generic headline on a different day does not.
    """
    words = _NON_ALNUM.sub(" ", fold_lower(title)).strip()
    key = f"{words}|{published_at.date().isoformat()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
