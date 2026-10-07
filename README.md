# BIST News Analyzer

Collects Borsa Istanbul news and KAP disclosures, analyzes them with a **local LLM (Ollama)**, and serves the results to an Expo mobile app. Analyses are descriptive only; the app never produces buy/sell signals.

> Work in progress. Full architecture notes, model comparison and screenshots will land in Phase 7.

## Stack

Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 18 · Ollama · Expo (React Native + TypeScript)

## Quickstart

Prerequisites: Docker + Compose, [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com) running on the host.

```bash
cp .env.example .env              # then set POSTGRES_PASSWORD
docker compose up -d              # PostgreSQL (+ bist_test database for pytest)

ollama pull qwen3.5:4b-q4_K_M     # primary candidate
ollama pull gemma4:e4b-it-q4_K_M  # secondary candidate

cd backend
uv sync
uv run alembic upgrade head
uv run python scripts/seed_stocks.py   # tracked stocks from config/stocks.yaml (idempotent)
uv run pytest
uv run python scripts/ollama_smoke_test.py [--model gemma4:e4b-it-q4_K_M]
```

Run the collectors:

```bash
uv run python -m app.workers.main --once rss   # one Google News RSS run, then exit
uv run python -m app.workers.main --once kap   # one KAP disclosure run (single request), then exit
uv run python -m app.workers.main              # scheduler: RSS every 120 min, KAP every 60 min
```

Tests that call a real Ollama server are marked `ollama` and skipped by default (`uv run pytest -m ollama` to run them).
