# Cloud Recommender Backend

Backend service for the Cloud Recommender POC, built with FastAPI, LangGraph, SQLAlchemy 2.0 (`asyncpg`), Alembic, and Pydantic v2.

---

## Architecture & Layout

```text
backend/
├── alembic/
│   ├── versions/
│   │   └── 2026_10_12_0001_initial_workload_and_catalog.py
│   └── env.py
├── src/
│   └── cloud_recommender/
│       ├── api/
│       │   ├── routes/
│       │   │   ├── catalog.py       # Catalog query endpoints
│       │   │   └── health.py        # Liveness & readiness probes
│       │   └── v1/
│       │       └── router.py        # /api/v1 router aggregation
│       ├── catalog/
│       │   ├── data/
│       │   │   └── curated_services.json # 18 curated cloud service seed fixtures
│       │   └── seeds.py             # Fixture loader and database seeder
│       ├── core/
│       │   └── config.py            # Environment-driven settings with pydantic-settings
│       ├── db/
│       │   ├── models.py            # SQLAlchemy 2.0 ORM models (Workload, Catalog)
│       │   ├── session.py           # Async engine & sessionmaker lifecycle
│       │   └── repositories/
│       │       ├── catalog_repo.py  # Service catalog query and upsert operations
│       │       └── workload_repo.py # Workload profile persistence operations
│       ├── schemas/
│       │   ├── catalog.py           # Catalog DTOs and query filters
│       │   ├── common.py            # Shared enums (CloudProvider, ServiceCategory, etc.)
│       │   ├── optimization.py      # Optimization audit and waste finding schemas
│       │   ├── recommendation.py    # Architecture recommendation and cost DTOs
│       │   └── workload.py          # Workload profile specification schemas
│       ├── services/
│       │   └── catalog_service.py   # Catalog service manager with offline fixture fallback
│       └── main.py                  # FastAPI application entrypoint and exception handlers
└── tests/                           # 50 unit and integration tests (93% coverage)
```

---

## API Endpoints

### Health & Readiness
- `GET /health` — Application liveness probe.
- `GET /health/ready` — Application and database readiness check.
- `GET /api/v1/health` — Versioned liveness probe.

### Service Catalog
- `GET /api/v1/catalog/services` — Filterable cloud service catalog list:
  - Query parameters:
    - `provider`: `azure`, `aws`, `gcp`
    - `category`: `compute`, `storage`, `database`, `networking`, `security`, `analytics`, `integration`
    - `is_serverless`: boolean
    - `compliance`: `hipaa`, `pci_dss`, `soc2`, `iso27001`, `fedramp`, `gdpr`
    - `search`: text query across service ID, name, description, and keywords
    - `limit`: page size (1 to 100, default 20)
    - `offset`: pagination offset
- `GET /api/v1/catalog/services/{service_id}` — Detailed service specification by provider-neutral identifier.

---

## Database Migrations

Database migrations are managed via Alembic with asynchronous engine support:

```bash
# Run migrations up to latest revision
uv run alembic upgrade head

# Downgrade one revision
uv run alembic downgrade -1
```

---

## Development & Testing Quality Gates

Run all quality checks from the `backend/` directory:

```bash
# 1. Lint and style checks
uv run ruff check .
uv run ruff format --check .

# 2. Strict static type analysis
uv run mypy src tests

# 3. Unit and integration tests with coverage
uv run pytest -v --cov=cloud_recommender --cov-report=term-missing
```
