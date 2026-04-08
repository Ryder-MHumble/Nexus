# Source Overview

> Last updated: 2026-04-07

This document summarizes the source inventory currently configured in Nexus.

## Totals

| Metric | Value |
| --- | ---: |
| Total configured sources | 272 |
| Enabled sources | 195 |
| Disabled sources | 77 |
| Source dimensions | 10 |
| Scholar acquisition sources | 49 |
| University leadership sources | 50 |

## By Dimension

| Dimension | Total | Enabled | Notes |
| --- | ---: | ---: | --- |
| `beijing_policy` | 16 | 15 | Regional policy monitoring |
| `events` | 6 | 3 | Conference and activity tracking |
| `industry` | 10 | 6 | Industry and company movement |
| `national_policy` | 8 | 8 | National policy and regulation |
| `personnel` | 54 | 54 | Personnel tracking plus leadership sources |
| `regional_policy` | 4 | 4 | Shanghai and Shenzhen policy tracking |
| `scholars` | 49 | 0 | Scholar acquisition configs currently disabled by default in this checkout |
| `talent` | 7 | 4 | Talent and recruitment signals |
| `technology` | 34 | 27 | Research and technology frontier |
| `universities` | 84 | 74 | University and institute activity |

## Crawl Method Distribution

The source configs currently declare these `crawl_method` values:

| Crawl Method | Count |
| --- | ---: |
| `static` | 104 |
| `dynamic` | 53 |
| `university_leadership` | 50 |
| `faculty` | 43 |
| `rss` | 14 |
| parser-only | 8 |

Additional note:

- `45` sources provide a `crawler_class`, which means the registry may route them through dedicated parser implementations instead of template-only handling.
- `29` sources currently use `crawler_class: university_news_auto` for broad university news coverage.
- `1` source currently uses `schedule: cron` with explicit cron fields.

## Largest Groups

| Group | Count |
| --- | ---: |
| `university_news` | 61 |
| `university_leadership_official` | 50 |
| `policy` | 28 |
| `tsinghua` | 13 |
| `company_blogs` | 12 |
| `ai_institutes` | 11 |
| `pku` | 9 |
| `academic` | 8 |
| `news` | 8 |
| `international_media` | 7 |

## Operational Notes

- The largest increment in this sync is auto university news coverage (`university_news` now `61` total entries).
- Policy intelligence now spans:
  - native policy dimensions: `national_policy`, `beijing_policy`, `regional_policy`
  - cross-dimension policy signals from `talent` and `universities`
- The regional policy slice is intentionally narrow:
  - Beijing remains the primary local policy field
  - outside Beijing, only Shanghai and Shenzhen are tracked in `regional_policy`
- Twitter monitoring has been normalized to a platform-level source plus a standalone account inventory YAML file.
- Scholar ingestion sources are present and typed, but disabled by default in the current checked-in config set.
- For UI consumption, prefer:
  - `/api/v1/sources`
  - `/api/v1/sources/catalog`
  - `/api/v1/sources/facets`
  - `/api/v1/institutions/flat`
  - `/api/v1/institutions/hierarchy`
