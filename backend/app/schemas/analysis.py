"""Structured output schema for a single news analysis (see CLAUDE.md §6)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Topic(StrEnum):
    FINANSAL_SONUC = "finansal_sonuc"
    TEMETTU = "temettu"
    SERMAYE_ARTIRIMI = "sermaye_artirimi"
    YENI_IS_SOZLESME = "yeni_is_sozlesme"
    YATIRIM = "yatirim"
    YONETIM_DEGISIKLIGI = "yonetim_degisikligi"
    HUKUKI = "hukuki"
    SEKTOREL = "sektorel"
    MAKRO = "makro"
    DIGER = "diger"


class Tone(StrEnum):
    """Descriptive tone of the news itself. Not a trading signal."""

    OLUMLU = "olumlu"
    OLUMSUZ = "olumsuz"
    NOTR = "nötr"
    BELIRSIZ = "belirsiz"


class NewsAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: Topic
    summary: str = Field(min_length=1, description="2-3 cümlelik Türkçe özet")
    why_it_matters: str = Field(
        min_length=1, description="Şirket açısından neden önemli olabilir (1-2 cümle)"
    )
    related_metrics: list[str] = Field(default_factory=list, max_length=8)
    tone: Tone
    relevance: float = Field(ge=0.0, le=1.0)
