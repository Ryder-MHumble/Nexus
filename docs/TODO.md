# Nexus Roadmap

> Last updated: 2026-05-06

## Done Recently

- [x] Synchronized the DeanAgent-Backend capabilities into Nexus (May 2026)
- [x] Added paper warehouse dimension: 21 sources across ICLR/ICML/NeurIPS/CVPR/ICC/VACL/EMNLP/ECCV/IJCAI/AAAI/JMLR/JAIR/TMLR with 10 new crawler parsers
- [x] Added talent scout dimension: 28 competition/GitHub signal sources with 6 new crawler parsers
- [x] Reorganized `sources/` into 10 subdirectories (paper/, talent/, policy/, social/, etc.) with `rglob` recursive loading
- [x] Added `source_file_path` tracking in source configs for subdirectory awareness
- [x] Added talent scout candidate metrics to base crawler (`_apply_talent_scout_metrics`, `_should_apply_candidate_metrics`)
- [x] Registered 16 new custom parsers in crawler registry (total 32+)
- [x] Added paper schemas (`app/schemas/paper.py`) and paper service (`app/services/paper_service.py`)
- [x] Added publication service, scholar achievement tags, and profile classifier
- [x] Added source catalog auto-sync on startup
- [x] Added config fields: `REQUIRE_DB_ON_STARTUP`, `SILICONFLOW_API_*`, `DINGTALK_*`, `OPENROUTER_API_URL`
- [x] Synchronized the newer crawler branch into Nexus
- [x] Synced `university_news_auto` parser and `sources/universities-top-tier.yaml` for expanded top-tier university news crawling
- [x] Synced unified Twitter platform crawling (`sources/twitter.yaml` + `sources/twitter_kol_accounts.yaml`) with YAML cron scheduling
- [x] Synced crawl pipeline optimizations: RSS detail-image enrichment, image metadata fallback extraction, DB-first crawl persistence path
- [x] Added source catalog facets, grouping, health filtering, and pagination
- [x] Added institution, scholar, project, event, student, leadership, and report APIs
- [x] Upgraded the frontend console to expose source health, knowledge overview, and intelligence previews
- [x] Restored Nexus-facing metadata while keeping local PostgreSQL and Supabase-compatible runtime support
- [x] Added regression tests for source catalog, institution hierarchy, scholar filters, and crawler orchestration

## Next Up

### Platform

- [x] Add a repeatable command or script for regenerating `openapi.json` (`python scripts/generate_openapi.py`)
- [ ] Add CI coverage for backend tests plus frontend lint/build
- [ ] Review source configs where `crawl_method` is `unknown` and document the intended routing more clearly
- [ ] Add targeted regression tests for `university_news_auto` and `twitter_ai_kol_international` source behavior

### Paper Warehouse

- [ ] Add paper API routes (list, search, detail) to complement the paper_service
- [ ] Add paper enrichment pipeline integration into the daily scheduler
- [ ] Add paper-to-scholar linkage (match paper authors against scholar profiles)
- [ ] Add paper warehouse frontend views in the console

### Knowledge Workflows

- [ ] Add dedicated frontend pages for institutions, scholars, projects, events, and leadership, beyond the current overview widgets
- [ ] Expose leadership history and change-diff views in the API and console
- [ ] Add frontend search flows for AMiner-assisted institution matching and scholar lookup

### Reports and Intelligence

- [ ] Expand report generation beyond sentiment to policy, technology, personnel, and university domains
- [ ] Add richer preview cards for report metadata, trend shifts, and recent anomalies
- [ ] Add explicit source-to-report traceability in report responses

### Operations

- [ ] Add smoke tests for `./nexus.sh` startup and health checks
- [ ] Add environment templates for local PostgreSQL bootstrap
- [ ] Document production deployment topology for backend plus frontend split hosting
