<div align="center">
  <img src="docs/NEXUS-Banner.png" alt="Nexus Banner" width="800" />

<h1>Nexus</h1>
  <p><strong>Structured knowledge infrastructure for AI applications</strong></p>

  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
  [![Next.js 16](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
</div>

Nexus turns multi-source web content into structured, queryable knowledge for downstream AI products. It combines configurable crawlers, scheduled processing pipelines, a typed FastAPI surface, and a Next.js operations console.

## Snapshot

- `102` OpenAPI paths across source management, crawler control, knowledge graph, intelligence, and report generation
- YAML-driven source inventory covering policy, technology, universities, events, personnel, and scholar workflows
- Explicit institution list endpoints for flat list and hierarchy consumers
- Repeatable OpenAPI generation via `python scripts/generate_openapi.py`
- Dual runtime support: local PostgreSQL recommended, Supabase-compatible facade retained

## What Shipped

The current Nexus workspace includes:

- Expanded source catalog APIs with facets, keyword search, grouping, health status, and pagination
- Knowledge APIs for institutions, scholars, projects, events, students, AMiner lookup, and university leadership
- Explicit institution list contracts for both paginated flat views and hierarchy views
- Report APIs for dimension discovery and sentiment report generation
- Clearer OpenAPI output for institutions, dimensions, reports, and LLM tracking
- RSS detail-image enrichment (`extract_detail_images`) and broader image metadata extraction (including OpenGraph/Twitter card fallbacks)
- Improved CLI crawl workflow that persists directly to DB and closes Playwright/DB resources explicitly
- Updated Next.js console with:
  - enhanced source directory and source health visibility
  - knowledge capability overview cards
  - intelligence panel for reports and leadership previews
- Verification coverage for source filtering, source catalog, institution hierarchy, scholar filters, crawler orchestration, and API contracts

## Quick Start

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cd frontend
npm install
cd ..
```

### 2. Configure environment

```bash
cp .env.example .env
```

Recommended local backend:

```env
DB_BACKEND=postgres
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password
POSTGRES_DB=nexus
```

You can also point Nexus at Supabase by setting `DB_BACKEND=supabase` together with `SUPABASE_URL` and `SUPABASE_KEY`.

### 3. Start the stack

```bash
./nexus.sh start
```

Default local endpoints:

- API: `http://localhost:43817`
- Scalar docs: `http://localhost:43817/docs`
- Swagger UI: `http://localhost:43817/swagger`
- Frontend console: `http://localhost:43819`

Useful lifecycle commands:

```bash
./nexus.sh status
./nexus.sh logs backend -f
./nexus.sh logs frontend -f
./nexus.sh restart
./nexus.sh stop
```

## Development

### Backend only

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 43817
```

### Frontend only

```bash
cd frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:43817/api/v1 npm run dev
```

### Validate the workspace

```bash
python3 -m compileall app
./.venv/bin/pytest
python scripts/generate_openapi.py

cd frontend
npm run lint
npm run build
```

## Key API Areas

Core operations:

- `/api/v1/sources`
- `/api/v1/sources/catalog`
- `/api/v1/sources/facets`
- `/api/v1/crawler/start`
- `/api/v1/crawler/status`

Knowledge graph:

- `/api/v1/institutions`
- `/api/v1/institutions/flat`
- `/api/v1/institutions/hierarchy`
- `/api/v1/scholars`
- `/api/v1/projects`
- `/api/v1/events`
- `/api/v1/students`
- `/api/v1/leadership`

Intelligence and reports:

- `/api/v1/intel/policy/*`
- `/api/v1/intel/personnel/*`
- `/api/v1/intel/tech-frontier/*`
- `/api/v1/intel/university/*`
- `/api/v1/reports/dimensions`
- `/api/v1/reports/sentiment/latest`

Generated schema:

- [`openapi.json`](openapi.json)
- refresh command: `python scripts/generate_openapi.py`

## Repository Guide

- [`docs/architecture.md`](docs/architecture.md): current system architecture and runtime flow
- [`docs/SourceOverview.md`](docs/SourceOverview.md): source counts, dimensions, and grouping summary
- [`docs/TODO.md`](docs/TODO.md): current roadmap
- [`frontend/README.md`](frontend/README.md): frontend console notes
- [`scripts/README.md`](scripts/README.md): supported script entry points

## Notes

- Scholar sources are intentionally present in config but currently disabled by default in this checkout.
- The backend keeps a PostgreSQL-like query facade so newer modules can run locally while older Supabase-oriented code paths still work.
- `openapi.json` is generated from the live FastAPI app and should be refreshed whenever routes or schema metadata change.
