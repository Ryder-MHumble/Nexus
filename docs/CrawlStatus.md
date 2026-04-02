# Crawl Status

> Last updated: 2026-04-02

This file tracks the operational posture of the current Nexus checkout. For source inventory details, use [`SourceOverview.md`](SourceOverview.md).

## Current State

- configured sources: `268`
- enabled sources: `191`
- source dimensions: `9`
- generated OpenAPI paths: `100`
- frontend console: enabled in `frontend/`

## High-Signal Source Areas

- `personnel`: `54` enabled sources, including `50` university leadership crawlers
- `universities`: `74` enabled sources
- `technology`: `27` enabled sources
- `beijing_policy`: `15` enabled sources
- `national_policy`: `8` enabled sources

## Crawl Method Shape

- `static`: `100`
- `dynamic`: `53`
- `rss`: `14`
- `faculty`: `43`
- `university_leadership`: `50`
- parser-only: `8`
- parser-backed (`crawler_class` set): `45` total (`38` enabled)

## New In This Sync

- Added `university_news_auto` parser and synced `sources/universities-top-tier.yaml` (`29` auto-university-news sources).
- Synced unified Twitter source design: one platform source in `sources/twitter.yaml` with account inventory in `sources/twitter_kol_accounts.yaml`.
- Synced scheduler enhancement for YAML cron config (e.g., `schedule: cron` + `cron: {hour, minute, timezone}`).
- Synced RSS/image extraction optimization:
  - `extract_detail_images` support in RSS crawler
  - image fallback extraction from OpenGraph/Twitter card metadata
- Synced CLI crawl persistence behavior:
  - `scripts/crawl/run_single.py` and `run_all.py` now follow DB-first persistence path
  - explicit Playwright/DB client close in single-run flow

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
