# Source Overview

> Last updated: 2026-05-06

This document summarizes the source inventory currently configured in Nexus after the DeanAgent-Backend sync.

## Totals

| Metric | Value |
| --- | ---: |
| Total configured sources | 321 |
| Enabled sources | 195 |
| Disabled sources | 126 |
| Source dimensions | 12 |
| Scholar acquisition sources | 49 |
| University leadership sources | 50 |
| Paper warehouse sources | 21 |
| Talent scout sources | 28 |

## By Dimension

| Dimension | Total | Enabled | Notes |
| --- | ---: | ---: | --- |
| `beijing_policy` | 16 | 15 | Regional policy monitoring |
| `events` | 6 | 3 | Conference and activity tracking |
| `industry` | 10 | 6 | Industry and company movement |
| `national_policy` | 8 | 8 | National policy and regulation |
| `paper` | 21 | 0 | Top conference/journal paper warehouse — disabled by default |
| `personnel` | 54 | 54 | Personnel tracking plus leadership sources |
| `regional_policy` | 4 | 4 | Shanghai and Shenzhen policy tracking |
| `scholars` | 49 | 0 | Scholar acquisition configs — disabled by default |
| `talent` | 7 | 4 | Talent and recruitment signals |
| `talent_scout` | 28 | 0 | Competition/GitHub talent signals — disabled, manual export only |
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

- `60+` sources provide a `crawler_class`, which means the registry may route them through dedicated parser implementations instead of template-only handling.
- `29` sources currently use `crawler_class: university_news_auto` for broad university news coverage.
- Paper warehouse sources use venue-specific classes: `aclanthology`, `openreview`, `openreview_journal`, `nips_papers_cc`, `cvf_openaccess`, `ecva_papers`, `ijcai_proceedings`, `ojs_aaai`, `jmlr_papers`, `jair_oai`.
- Talent scout sources use: `competition_source`, `github_talent_source`, `evidence_only_source`.

## New Dimensions (post DeanAgent-Backend Sync)

### Paper Warehouse

21 paper sources across 14 venues, organized in `sources/paper/`:

| File | Venue | Sources | Type |
| --- | --- | ---: | --- |
| `top_conference_papers.yaml` | JMLR, JAIR, TMLR, ACL (long+short), ICLR, ICML, NeurIPS, CVPR, ICCV, EMNLP, ECCV, IJCAI, AAAI | 14 | Paper records (persist to DB) |
| `conferences.yaml` | OpenReview Author, ACL Anthology Author, CVF OpenAccess Author | 3 | Paper author signals (talent) |
| `journals.yaml` | DBLP, arXiv, Semantic Scholar, Academic Paper Authors | 4 | Paper author signals (talent) |

Each source includes an `enrichment` profile specifying QPS limits and methods for metadata backfill.

### Talent Scout

28 sources organized in `sources/talent/`:

| File | Count | Description |
| --- | ---: | --- |
| `competition.yaml` | 26 | Competition signal sources (CCF BDCI, Aliyun Tianchi, Kaggle, ICPC, CTFTime, NOI/IOI, RoboMaster, etc.) |
| `github.yaml` | 2 | GitHub AI user/repo-contributor sources |

All talent_scout sources are disabled by default (`is_enabled: false`) and intended for manual ad-hoc export workflows via `persist_to_db: false`.

## Sources Directory Structure

After the May 2026 reorganization, sources are organized in subdirectories:

```
sources/
  events/         — events.yaml
  industry/       — industry.yaml
  paper/          — conferences.yaml, journals.yaml, top_conference_papers.yaml
  personnel/      — personnel.yaml
  policy/         — beijing_policy.yaml, national_policy.yaml, regional_policy.yaml
  scholars/       — scholar-{cas,fudan,nju,pku,ruc,sjtu,tsinghua,ustc,zju}.yaml
  social/         — twitter.yaml, twitter_kol_accounts.yaml
  talent/         — competition.yaml, github.yaml, talent.yaml
  technology/     — technology.yaml
  universities/   — universities-{aggregators,ai-institutes,awards,news,provinces,top-tier}.yaml, university_leadership_sources.yaml
```

## Largest Groups

| Group | Count |
| --- | ---: |
| `university_news` | 61 |
| `university_leadership_official` | 50 |
| `policy` | 28 |
| `talent_competitions` | 26 |
| `paper_warehouse` | 14 |
| `tsinghua` | 13 |
| `company_blogs` | 12 |
| `ai_institutes` | 11 |
| `pku` | 9 |
| `academic` | 8 |
| `news` | 8 |
| `international_media` | 7 |

## Operational Notes

- The largest increment in this sync is the paper warehouse (21 sources) and talent scout competition sources (26 sources).
- Policy intelligence now spans:
  - native policy dimensions: `national_policy`, `beijing_policy`, `regional_policy`
  - cross-dimension policy signals from `talent` and `universities`
- The regional policy slice is intentionally narrow:
  - Beijing remains the primary local policy field
  - outside Beijing, only Shanghai and Shenzhen are tracked in `regional_policy`
- Twitter monitoring has been normalized to a platform-level source plus a standalone account inventory YAML file.
- Scholar ingestion sources are present and typed, but disabled by default in the current checked-in config set.
- Paper warehouse sources are disabled by default — enable after configuring API access (OpenReview, OpenAlex, etc.).
- Talent scout sources are disabled and intended for manual export workflows only.
- For UI consumption, prefer:
  - `/api/v1/sources`
  - `/api/v1/sources/catalog`
  - `/api/v1/sources/facets`
  - `/api/v1/institutions/flat`
  - `/api/v1/institutions/hierarchy`
