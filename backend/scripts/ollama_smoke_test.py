"""Phase 0 smoke test: classify Turkish headlines with a local Ollama model.

Checks that
  1. the Ollama server is reachable and the model is pulled,
  2. schema-constrained output (`format=<JSON schema>`) parses into `NewsAnalysis`,
  3. throughput and GPU/CPU placement are acceptable on this machine.

Usage:
    uv run python scripts/ollama_smoke_test.py                  # model from .env
    uv run python scripts/ollama_smoke_test.py --model gemma4:e4b-it-q4_K_M
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.analysis import NewsAnalysis

SAMPLE_HEADLINES: list[tuple[str, str]] = [
    ("THYAO", "Türk Hava Yolları üçüncü çeyrekte yolcu sayısını yüzde 9 artırdı"),
    ("TUPRS", "Tüpraş yönetim kurulu brüt 12 TL kâr payı dağıtımı önerdi"),
    ("ASELS", "ASELSAN yurt dışı müşteriyle 85 milyon dolarlık sözleşme imzaladı"),
]

SYSTEM_PROMPT = """Sen Borsa İstanbul haberlerini sınıflandıran betimleyici bir analiz asistanısın.
Kurallar:
- Yatırım tavsiyesi verme. "al", "sat", "tut", "hedef fiyat", "kesin yükselir" gibi ifadeler kullanma.
- Sayı uydurma; yalnızca başlıkta geçen bilgileri kullan.
- Sadece istenen JSON şemasına uygun yanıt ver. Tüm metin alanları Türkçe olsun.
- topic: haberin konusu. tone: haberin şirket açısından betimleyici tonu (sinyal değil).
- relevance: haberin belirtilen hisseyle ne kadar ilgili olduğu (0-1)."""


def check_model_available(client: httpx.Client, model: str) -> None:
    tags = client.get("/api/tags").raise_for_status().json()
    names = {m["name"] for m in tags.get("models", [])}
    if model not in names:
        sys.exit(f"Model '{model}' is not pulled. Run: ollama pull {model}\nAvailable: {sorted(names)}")


def classify(client: httpx.Client, model: str, num_ctx: int, ticker: str, headline: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Hisse: {ticker}\nHaber başlığı: {headline}"},
        ],
        "format": NewsAnalysis.model_json_schema(),
        "think": False,
        "stream": False,
        "options": {"temperature": 0, "num_ctx": num_ctx},
    }
    result: dict[str, Any] = client.post("/api/chat", json=payload).raise_for_status().json()
    return result


def report_placement(client: httpx.Client, model: str) -> None:
    for m in client.get("/api/ps").raise_for_status().json().get("models", []):
        if m["name"] == model:
            size, vram = m.get("size", 0), m.get("size_vram", 0)
            pct = 100 * vram / size if size else 0
            print(f"Placement: {vram / 1e9:.2f} GB of {size / 1e9:.2f} GB on GPU ({pct:.0f}%)")


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", default=settings.ollama_model)
    args = parser.parse_args()

    failures = 0
    with httpx.Client(base_url=settings.ollama_base_url, timeout=settings.ollama_timeout_seconds) as client:
        check_model_available(client, args.model)
        print(f"Model: {args.model}  num_ctx={settings.ollama_num_ctx}\n")

        for ticker, headline in SAMPLE_HEADLINES:
            started = time.perf_counter()
            response = classify(client, args.model, settings.ollama_num_ctx, ticker, headline)
            wall = time.perf_counter() - started

            eval_count = response.get("eval_count", 0)
            eval_seconds = response.get("eval_duration", 0) / 1e9
            tok_per_s = eval_count / eval_seconds if eval_seconds else 0.0
            print(f"[{ticker}] {headline}")
            print(f"  wall={wall:.1f}s  gen={eval_count} tok @ {tok_per_s:.1f} tok/s")

            raw = response["message"]["content"]
            try:
                analysis = NewsAnalysis.model_validate_json(raw)
            except ValidationError as exc:
                failures += 1
                print(f"  INVALID OUTPUT: {exc.error_count()} error(s)\n  raw: {raw}\n")
                continue
            print(json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False, indent=2), "\n")

        report_placement(client, args.model)

    print(f"\n{len(SAMPLE_HEADLINES) - failures}/{len(SAMPLE_HEADLINES)} outputs valid.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
