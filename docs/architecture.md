# Nexus Architecture

> Last updated: 2026-05-06

Nexus is a crawler-driven knowledge platform. It ingests configured sources, normalizes the results into structured storage, enriches selected domains, and exposes the result through a typed API plus an operator-facing frontend.

## System Shape

```text
sources/{dimension}/*.yaml
  -> scheduler + crawler registry (32+ custom parsers)
  -> template crawlers / parser-backed crawlers
  -> raw article and state persistence
  -> domain intelligence pipelines
  -> FastAPI routes + Next.js console
```

## Runtime Layers

### 1. Source Configuration

- `sources/{dimension}/*.yaml` — organized in 10 subdirectories: `policy/`, `events/`, `industry/`, `personnel/`, `technology/`, `talent/`, `social/`, `scholars/`, `universities/`, `paper/`
- the source inventory is configuration-driven and evolves with the checked-in YAML catalog
- the current platform surfaces 11 dimensions: national_policy, beijing_policy, regional_policy, technology, talent, talent_scout, industry, universities, events, personnel, scholars, paper
- `load_all_source_configs()` uses `rglob("*.yaml")` for recursive directory traversal; each source records its `source_file_path` relative to `sources/`
- source catalog is auto-synced on startup into the DB `source_states` table

Operational note:

- platform-level Twitter monitoring is implemented as a source inside the `technology` dimension
- talent_scout sources (competitions, GitHub) are disabled by default and intended for manual ad-hoc export workflows
- paper warehouse sources are disabled by default; enable when API access is configured (OpenReview, OpenAlex, etc.)

### 2. Crawl Execution

Key modules:

- `app/scheduler/manager.py`
- `app/scheduler/jobs.py`
- `app/crawlers/registry.py`
- `app/crawlers/base.py` — abstract base with talent scout candidate metrics support
- `app/crawlers/templates/*`
- `app/crawlers/parsers/*` — 32+ custom parser implementations

Current configured crawl patterns by `crawl_method`:

- `static`
- `dynamic`
- `rss`
- `faculty`
- `university_leadership`
- parser-backed or source-specific crawlers

Additionally, 45+ sources specify `crawler_class` and are routed through parser implementations. 16 new parsers were added from the DeanAgent-Backend sync:

**Paper warehouse**: `aclanthology`, `openreview` (API), `openreview_journal`, `nips_papers_cc`, `cvf_openaccess`, `ecva_papers`, `ijcai_proceedings`, `ojs_aaai`, `jmlr_papers`, `jair_oai`

**Talent scout**: `competition_source`, `github_talent_source`, `paper_author_source`, `evidence_only_source`, `_talent_scout_common`, `zhejianglab_website_api`

### 3. Storage and Data Access

Key modules:

- `app/db/client.py`
- `app/db/pool.py`
- `app/services/stores/*`

Nexus uses a database facade with two supported modes:

- local PostgreSQL, recommended for development and self-hosted runs
- Supabase-compatible access for legacy compatibility and hosted deployments

The DB facade preserves a Supabase-like query surface for older services while allowing newer modules to run against local PostgreSQL through the same application code.

### 4. Domain Services

Key API domains:

- source catalog and crawler control
- institutions, scholars, projects, events, and students
- university leadership
- paper warehouse (new): paper ingestion, enrichment, and query
- policy, personnel, tech frontier, university, and sentiment intelligence
- report generation and report metadata APIs

Representative service modules:

- `app/services/core/source_service.py`
- `app/services/core/institution/*`
- `app/services/core/project_service.py`
- `app/services/core/event_service.py`
- `app/services/scholar/*` — query, achievement tags, profile classification
- `app/services/intel/*`
- `app/services/paper_service.py` — paper warehouse queries and ingestion management

Policy intelligence is currently assembled from:

- `national_policy`
- `beijing_policy`
- cross-dimension policy signals from adjacent domain content when the enrichment pipeline classifies them as policy-relevant

### 5. Presentation Layer

Backend:

- FastAPI app in `app/main.py`
- `102` OpenAPI paths in the current generated schema
- Scalar docs at `/docs`
- Swagger UI at `/swagger`

Frontend:

- Next.js console in `frontend/`
- source directory with facets and health
- batch crawl controls
- knowledge overview cards
- intelligence/report preview panel

## High-Value Flows

### Source Catalog

`/api/v1/sources`, `/api/v1/sources/catalog`, and `/api/v1/sources/facets` provide:

- filtering by dimension, group, tag, crawl method, schedule, enabled state, health state, and keyword
- pagination and sort control
- pre-aggregated facets for UI filtering

### Knowledge Graph

The current backend exposes dedicated CRUD and stats flows for:

- institutions
- `/api/v1/institutions/flat` for paginated list views
- `/api/v1/institutions/hierarchy` for tree-style organization views
- scholars
- projects
- events
- students
- leadership

This is the main delta that was synchronized from the newer crawler branch into Nexus.

### Paper Warehouse (NEW)

Paper warehouse sources ingest top conference and journal papers into a structured `papers` table. Each source specifies:

- `venue` / `venue_full` — conference/journal identity
- `year_configs` — per-year crawl parameters (venue_id, issue_ids, etc.)
- `enrichment` profile — primary/fallback methods and QPS limits for metadata enrichment

Supported enrichment methods: `openreview_note`, `openreview_profile`, `openalex`, `official_html`, `pdf_first_page`, `arxiv_by_id`.

### Reports

Report endpoints currently support:

- report dimension discovery
- sentiment report generation
- latest sentiment report shortcut

## Local Development Contract

Recommended commands:

```bash
./nexus.sh start
./nexus.sh status
./nexus.sh logs backend -f
./nexus.sh logs frontend -f
```

Verification commands:

```bash
python3 -m compileall app
./.venv/bin/pytest
python scripts/generate_openapi.py
cd frontend && npm run lint && npm run build
```
