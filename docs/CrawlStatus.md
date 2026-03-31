# Crawl Status

> Last updated: 2026-03-31

This file tracks the operational posture of the current Nexus checkout. For source inventory details, use [`SourceOverview.md`](SourceOverview.md).

## Current State

- configured sources: `245`
- enabled sources: `168`
- source dimensions: `10`
- generated OpenAPI paths: `100`
- frontend console: enabled in `frontend/`

## High-Signal Source Areas

- `personnel`: `54` enabled sources, including `50` university leadership crawlers
- `universities`: `45` enabled sources
- `technology`: `30` enabled sources
- `beijing_policy`: `15` enabled sources
- `national_policy`: `8` enabled sources

## Crawl Method Shape

- `static`: `100`
- `dynamic`: `24`
- `rss`: `14`
- `faculty`: `43`
- `university_leadership`: `50`
- parser-backed or source-specific: `14`

## Operational Guidance

Use these commands during local debugging:

```bash
./nexus.sh start
./nexus.sh status
./nexus.sh logs backend -f
python scripts/crawl/run_single.py --source <source_id>
```

## Notes

- Scholar acquisition sources are checked in but disabled by default in this workspace.
- Source health and facet views should be inspected through:
  - `/api/v1/sources`
  - `/api/v1/sources/catalog`
  - `/api/v1/sources/facets`
