# Nexus Roadmap

> Last updated: 2026-03-31

## Done Recently

- [x] Synchronized the newer crawler branch into Nexus
- [x] Added source catalog facets, grouping, health filtering, and pagination
- [x] Added institution, scholar, project, event, student, leadership, and report APIs
- [x] Upgraded the frontend console to expose source health, knowledge overview, and intelligence previews
- [x] Restored Nexus-facing metadata while keeping local PostgreSQL and Supabase-compatible runtime support
- [x] Added regression tests for source catalog, institution hierarchy, scholar filters, and crawler orchestration

## Next Up

### Platform

- [ ] Add a repeatable command or script for regenerating `openapi.json`
- [ ] Add CI coverage for backend tests plus frontend lint/build
- [ ] Review source configs where `crawl_method` is `unknown` and document the intended routing more clearly

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
