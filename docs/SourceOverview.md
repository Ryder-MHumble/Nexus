# Source Overview

> Last updated: 2026-03-31

This document summarizes the source inventory currently configured in Nexus.

## Totals

| Metric | Value |
| --- | ---: |
| Total configured sources | 245 |
| Enabled sources | 168 |
| Disabled sources | 77 |
| Source dimensions | 10 |
| Scholar acquisition sources | 49 |
| University leadership sources | 50 |

## By Dimension

| Dimension | Total | Enabled | Notes |
| --- | ---: | ---: | --- |
| `beijing_policy` | 16 | 15 | Regional policy monitoring |
| `events` | 6 | 3 | Conference and activity tracking |
| `industry` | 11 | 7 | Industry and company movement |
| `national_policy` | 8 | 8 | National policy and regulation |
| `personnel` | 54 | 54 | Personnel tracking plus leadership sources |
| `scholars` | 49 | 0 | Scholar acquisition configs currently disabled by default in this checkout |
| `sentiment` | 1 | 1 | Sentiment-specific ingestion |
| `talent` | 8 | 5 | Talent and recruitment signals |
| `technology` | 37 | 30 | Research and technology frontier |
| `universities` | 55 | 45 | University and institute activity |

## Crawl Method Distribution

The source configs currently declare these `crawl_method` values:

| Crawl Method | Count |
| --- | ---: |
| `static` | 100 |
| `university_leadership` | 50 |
| `faculty` | 43 |
| `dynamic` | 24 |
| `rss` | 14 |
| parser-backed or source-specific | 14 |

Additional note:

- `22` sources also provide a `crawler_class`, which means the registry may route them through dedicated parser implementations instead of template-only handling.

## Largest Groups

| Group | Count |
| --- | ---: |
| `university_leadership_official` | 50 |
| `university_news` | 32 |
| `policy` | 24 |
| `tsinghua` | 13 |
| `company_blogs` | 12 |
| `ai_institutes` | 11 |
| `news` | 9 |
| `pku` | 9 |
| `academic` | 8 |
| `international_media` | 7 |

## Operational Notes

- The biggest increment synchronized into Nexus in this round is the `university_leadership_official` group, which contributes `50` leadership-focused sources.
- Scholar ingestion sources are present and typed, but disabled by default in the current checked-in config set.
- For UI consumption, prefer:
  - `/api/v1/sources`
  - `/api/v1/sources/catalog`
  - `/api/v1/sources/facets`
