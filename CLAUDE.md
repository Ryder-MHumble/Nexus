# Nexus Workspace Context

Nexus is a crawler-driven data infrastructure project with a FastAPI backend and a Next.js operations console.

## Current Reality

- `245` configured sources
- `168` enabled
- `100` generated OpenAPI paths
- local PostgreSQL is the recommended development backend
- Supabase-compatible access is still supported for legacy compatibility

## Main Areas

- `app/api/v1/`: route surface
- `app/services/core/`: source, institution, project, and event logic
- `app/services/scholar/`: scholar-specific query and mutation flows
- `app/services/intel/`: intelligence and report logic
- `app/crawlers/`: templates, parsers, registry, and crawl utilities
- `frontend/`: Next.js 16 console

## Recommended Commands

```bash
./nexus.sh start
./nexus.sh status
./nexus.sh logs backend -f
./nexus.sh logs frontend -f
```

Backend-only:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 43817
```

Frontend-only:

```bash
cd frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:43817/api/v1 npm run dev
```

## Verification Standard

After code changes, prefer this validation set:

```bash
python3 -m compileall app
./.venv/bin/pytest
cd frontend && npm run lint && npm run build
```

## Documentation Contract

If routes, schema metadata, or startup behavior change, update:

- `README.md`
- `openapi.json`
- `docs/architecture.md`
- `docs/SourceOverview.md`
- `frontend/README.md`
- `scripts/README.md`

## Current Frontend Scope

The frontend is not a full business application yet. It is currently an operator console that focuses on:

- source directory and selection
- crawler control and export settings
- runtime status monitoring
- knowledge capability overview
- intelligence and report previews
