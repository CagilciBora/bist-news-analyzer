import pytest
from pydantic import ValidationError

from app.schemas.analysis import NewsAnalysis, Tone, Topic

VALID = {
    "topic": "temettu",
    "summary": "Şirket brüt 12 TL kâr payı önerdi.",
    "why_it_matters": "Kâr dağıtım politikası hakkında bilgi verir.",
    "related_metrics": ["temettü verimi"],
    "tone": "olumlu",
    "relevance": 0.9,
}


def test_valid_payload_parses() -> None:
    analysis = NewsAnalysis.model_validate(VALID)

    assert analysis.topic is Topic.TEMETTU
    assert analysis.tone is Tone.OLUMLU


@pytest.mark.parametrize(
    "override",
    [
        {"topic": "al_sinyali"},
        {"tone": "yükseliş"},
        {"relevance": 1.5},
        {"relevance": -0.1},
        {"summary": ""},
        {"unexpected_field": "x"},
    ],
)
def test_invalid_payload_is_rejected(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        NewsAnalysis.model_validate({**VALID, **override})


def test_json_schema_is_usable_as_ollama_format() -> None:
    schema = NewsAnalysis.model_json_schema()

    assert schema["type"] == "object"
    assert set(schema["required"]) >= {"topic", "summary", "why_it_matters", "tone", "relevance"}
