# Market Pulse Radar

A compact, production‑flavored web app that turns **news + social chatter** into **per‑ticker signals** (sentiment, novelty, velocity) with **explanations and backtests**. Built to showcase Data Science, Data Engineering, MLOps, LLMs, and DevOps in one coherent project.

> ⚠️ Educational demo. Not investment advice. Respect all data source TOS/licensing.

---

## 1) Features (MVP)

* Ingest from **GDELT**, **SEC EDGAR RSS**, **Stocktwits** (hourly).
* Normalize, dedupe, **link entities → tickers**; compute **FinBERT sentiment**, **MiniLM embeddings**, **novelty**, and **mention velocity**.
* Aggregate into per‑ticker **signals** with score + tags (earnings/guidance/M\&A).
* Basic **backtests** vs EOD prices (Alpha Vantage / Stooq fallback).
* **Explainability**: show top contributing articles/posts with excerpts.
* Minimal, inviting **web UI** (heatmap + ticker cards) via FastAPI + simple frontend.

---

## 2) Architecture (high level)

```
[Collectors] -> MinIO (raw NDJSON) -> [Normalizer + Ticker Linker]
   -> [Sentiment + Embeddings] -> Postgres (Timescale + pgvector)
   -> [Signal Scorer + Backtester] -> API -> UI
```

**Stores**

* **MinIO** (S3‑compatible) — raw/clean/features (cheap, append‑only).
* **Postgres 16 + Timescale + pgvector** — operational queries, time series, vectors.

**Orchestration**

* **Prefect** flows for ingest/transform/score/backtest; cron‑style schedules.

**Observability**

* **Prometheus/Grafana** dashboards; **Loki** for logs.

---

## 3) Tech choices (why these)

* **Python 3.11 + uv** — fast resolver/installer; reproducible `uv.lock`.
* **FastAPI** — quick, typed API; async capable.
* **TimescaleDB** — hypertables for time series; easy SQL.
* **pgvector** — store embeddings, do similarity.
* **MinIO** — S3 locally with Docker; keeps data‑lake pattern.
* **FinBERT** — finance‑tuned sentiment out‑of‑the‑box.
* **Sentence‑Transformers (MiniLM‑L6‑v2)** — small, fast, 384‑dim.
* **MLflow** — track models/experiments; optional in MVP.
* **Grafana/Prometheus/Loki** — production‑style monitoring.

---

## 4) Repository layout

```
market-pulse/
├─ collectors/                 # Source-specific adapters (pull → NDJSON)
│  ├─ gdelt.py
│  ├─ sec.py
│  └─ stocktwits.py
├─ pipelines/                  # Dataflow stages; pure, testable functions
│  ├─ normalize.py             # lang detect, clean text, boilerplate strip
│  ├─ linking.py               # ticker mapping (cashtags + synonyms + NER)
│  ├─ features.py              # sentiment, embeddings, novelty, velocity
│  ├─ scorer.py                # per-ticker signal calc + tagging
│  └─ backtest.py              # joins signals with prices; metrics
├─ api/
│  ├─ main.py                  # FastAPI app factory & routers
│  └─ routers/                 # /signals, /explain, /backtest endpoints
├─ models/                     # Pydantic schemas + SQL models (SQLAlchemy)
├─ infra/
│  ├─ docker-compose.yml       # Local stack (DB, MinIO, Prefect, API, Grafana)
│  ├─ grafana/                 # Dashboards & provisioning
│  ├─ prometheus/              # Scrape config
│  └─ prefect/                 # Prefect deployment configs
├─ sql/
│  ├─ schema.sql               # tables, indexes, extensions
│  └─ migrations/              # Alembic migration scripts
├─ configs/                    # YAML/JSON: sources, schedules, weights
├─ scripts/                    # one-off utilities (seed tickers, load prices)
├─ tests/                      # unit + integration tests (pytest)
├─ .env.example                # environment variable template
├─ pyproject.toml              # uv project config
├─ uv.lock                     # resolved lockfile for reproducibility
├─ Makefile                    # common dev commands (see below)
└─ README.md                   # this file
```

---

## 5) Quickstart (local)

### Prereqs

* Docker & Docker Compose
* Python 3.11
* `uv` ([https://docs.astral.sh/uv/](https://docs.astral.sh/uv/))

### 5.1 Clone & configure

```bash
git clone https://github.com/<you>/market-pulse.git
cd market-pulse
cp .env.example .env   # fill in API keys (Alpha Vantage, Stocktwits), secrets
```

### 5.2 Start infrastructure

```bash
make up            # or: docker compose -f infra/docker-compose.yml up -d
make init-db       # runs sql/schema.sql and enables extensions
```

### 5.3 Create & sync Python env with uv

```bash
uv sync --python 3.11   # creates .venv and installs deps from pyproject/uv.lock
uv run pytest -q        # sanity test
```

### 5.4 Run flows & API

```bash
uv run python -m collectors.gdelt       # one-shot fetch to MinIO + DB
uv run python -m pipelines.scorer       # compute signals
uv run uvicorn api.main:app --reload    # http://localhost:8000/docs
```

**Helpful Make commands**

```bash
make up / make down / make logs
make init-db / make migrate / make seed-tickers
make ingest   # run all collectors once
make score    # recompute signals window
make backtest # daily backtest
```

---

## 6) Configuration

* **`.env`** (never commit secrets):

```
POSTGRES_URL=postgresql+psycopg://postgres:postgres@db:5432/market
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=changeme
AV_API_KEY=...
STWITS_TOKEN=...
SENTENCE_MODEL=sentence-transformers/all-MiniLM-L6-v2
FINBERT_MODEL=ProsusAI/finbert
```

* **`configs/sources.yaml`**: per‑source schedules, rate‑limits, fields to keep.
* **`configs/scoring.yaml`**: weights for score, thresholds, tag rules.

---

## 7) Data model (minimal)

* `article(id, source, url UNIQUE, published_at, title, text, lang, hash, credibility)`
* `article_embed(article_id, embedding VECTOR[384])`
* `article_ticker(article_id, ticker, confidence)`
* `price_bar(ticker, ts, o,h,l,c,v, timeframe)`
* `signal(id, ticker, ts, sentiment, novelty, velocity, event_tags, score)`

**Indexes**: `(ticker, ts DESC)` on `signal` & `price_bar`; `pgvector_ops` on `article_embed.embedding`.

**Hypertables**: `signal`, `price_bar` (Timescale) partitioned by time.

---

## 8) Organization rules (how we work)

### 8.1 Code principles

* **Generic over specific**: write source **adapters** against a small interface (`fetch() → iterable[Item]`), not hard‑coded endpoints.
* **Pure functions** in `pipelines/` (I/O at edges). Easy to test.
* **Config‑driven**: no magic constants; expose weights/thresholds in `configs/*`.
* **No copy‑pasting code** from blogs/repos. If you take an idea, **cite the source in PR description**; re‑implement cleanly.
* **Separation of concerns**: collectors ≠ transforms ≠ storage ≠ scoring ≠ serving.
* **Determinism**: set seeds; avoid implicit current time in functions (pass it in).

### 8.2 Style & quality

* **Type hints** required; `mypy --strict` on CI.
* **Ruff** for linting + import order; **Black** for formatting.
* Minimal comments; instead use **clear names** and **short docstrings** at module boundary.
* Tests: `pytest` with `tests/unit` (fast), `tests/integration` (dockerized DB/MinIO).
* **Pre‑commit** hooks (ruff, black, mypy, pytest -q on changed tests).

### 8.3 Git workflow

* Branches: `main` (release), `dev` (integration), `feature/<short>`.
* **Conventional Commits** (`feat:`, `fix:`, `chore:` …). Auto‑generate CHANGELOG.
* Every PR: checklist for tests, docs, migration notes, dashboard updates if needed.

### 8.4 Data & compliance

* Respect robots.txt and API TOS. Store `source_url`, `license`, `retrieved_at` per item.
* **Attribution**: keep source name; expose in UI.
* **PII**: none expected; if added, document and scrub.
* **Retention**: raw `30–90 days`, features `180 days`, signals `indef` (tunable in config).

### 8.5 Secrets & security

* No secrets in code/commits. Use `.env` locally; for CI, use repo secrets.
* Rotate API keys quarterly. Principle of least privilege for buckets/DB.

### 8.6 Performance & cost

* Batch first (hourly), then stream if needed. Rate‑limit + backoff.
* Cache symbol maps; pre‑filter languages; avoid embedding full body (use title/lead).

---

## 9) API (thin)

* `GET /signals?ticker=TSLA&from=2025-08-01&to=2025-08-15` → list of signal points.
* `GET /explain?signal_id=123` → top contributing articles with excerpts & weights.
* `GET /backtest?window=1d&universe=sp100` → metrics snapshot.

OpenAPI docs at `/docs` when running locally.

---

## 10) Testing strategy

* **Unit**: pipelines are pure → fixtures with tiny JSON lines.
* **Integration**: spin Postgres/MinIO with docker-compose; run collectors end‑to‑end.
* **Eval**: backtest produces metrics JSON → snapshot test against tolerance.

---

## 11) CI/CD (GitHub Actions)

* Matrix: py3.11 on ubuntu.
* Jobs: lint (ruff/black), typecheck (mypy), tests (pytest), build images, push on tags.
* Optional: Terraform plan/apply for cloud variant.

---

## 12) Roadmap (next)

1. Reddit adapter (+ OAuth); brigading filter.
2. Intraday prices (Polygon/Finnhub) + intraday backtests.
3. Topic clustering (BERTopic) → **Narrative heatmap**.
4. Model monitoring: drift on sentiment/velocity; alerting.
5. User auth + saved watchlists.
6. RAG explanations (per‑signal citations with verbatim quotes & highlights).

---

## 13) Makefile (suggested targets)

```Makefile
up:          ## start local stack
	docker compose -f infra/docker-compose.yml up -d

down:        ## stop stack
	docker compose -f infra/docker-compose.yml down -v

logs:        ## follow logs
	docker compose -f infra/docker-compose.yml logs -f --tail=200

init-db:     ## create schema & extensions
	psql $$POSTGRES_URL -f sql/schema.sql

migrate:     ## run alembic migrations
	uv run alembic upgrade head

ingest:      ## run all collectors once
	uv run python -m collectors.gdelt && \
	uv run python -m collectors.sec && \
	uv run python -m collectors.stocktwits

score:       ## recompute signals for last N hours
	uv run python -m pipelines.scorer --hours 24

backtest:    ## run backtest
	uv run python -m pipelines.backtest --window 1d
```

---

## 14) FAQ

* **Why uv instead of Poetry/pip?** Faster resolves/installs, clean lockfile, simple `uv run` UX.
* **Can I run without Docker?** Yes—start Postgres/MinIO manually and point `.env`.
* **Can I swap sources/models?** Yes—adapters and models are behind small interfaces; update `configs/*`.

---

## 15) License & attribution

Choose a permissive license (MIT/Apache‑2.0). Attribute data sources in the UI and docs.
