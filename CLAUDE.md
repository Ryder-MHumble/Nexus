# Nexus Workspace Context

Nexus is a crawler-driven knowledge infrastructure project with a FastAPI backend and a Next.js operations console. After the May 2026 DeanAgent-Backend sync, it now includes a paper warehouse dimension and talent scout competition/GitHub signal sources.

## Current Reality

- `321` configured sources (up from 272)
- `195` enabled (up from 168)
- `102` generated OpenAPI paths
- `11` dimensions: national_policy, beijing_policy, regional_policy, technology, talent, talent_scout, industry, universities, events, personnel, scholars, paper
- local PostgreSQL is the recommended development backend
- Supabase-compatible access is still supported for legacy compatibility
- Sources now organized in subdirectories under `sources/`: paper/, policy/, talent/, social/, events/, industry/, personnel/, scholars/, technology/, universities/

## Main Areas

- `app/api/v1/`: route surface
- `app/services/core/`: source, institution, project, and event logic
- `app/services/scholar/`: scholar-specific query, achievement tags, and profile classification
- `app/services/intel/`: intelligence and report logic
- `app/services/paper_service.py`: paper warehouse queries and ingestion management (NEW)
- `app/crawlers/`: templates, parsers (32+ custom parsers), registry, and crawl utilities
- `frontend/`: Next.js 16 console
- `sources/`: YAML-driven source inventory organized in 10 subdirectories

## New Capabilities (from DeanAgent-Backend Sync)

- **Paper Warehouse** (21 sources): Top AI conference/journal paper ingestion from ICLR, ICML, NeurIPS, CVPR, ACL, AAAI, IJCAI, JMLR, JAIR, TMLR etc. with year-configurable crawling and enrichment profiles
- **Talent Scout** (28 sources): Competition signal sources (CCF BDCI, Kaggle, ICPC, CTFTime, etc.) and GitHub talent sources for candidate discovery
- **Crawler parsers** (16 new): aclanthology, openreview_api, openreview_journal, nips_papers_cc, cvf_openaccess, ecva_papers, ijcai_proceedings, ojs_aaai, jmlr_papers, jair_oai, competition_source, github_talent_source, paper_author_source, evidence_only_source, _talent_scout_common, zhejianglab_website_api
- **Talent Scout Metrics**: base crawler now supports `_apply_talent_scout_metrics` for candidate-name-based counting and `_should_apply_candidate_metrics` routing logic
- **Source catalog sync**: startup now syncs source configs into DB source_states table

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
