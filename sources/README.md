# Sources Configuration Guide

## Content Filtering Options

Nexus supports **3 filtering modes** for each source:

### 1. No Filtering (Default)
Crawl all content from the source without any keyword filtering.

```yaml
- id: "example_source"
  url: "https://example.com/news"
  crawl_method: "static"
  # No keyword_filter or keyword_blacklist = keep all articles
```

### 2. Domain-Based Filtering (Recommended)
Use predefined domain classifications from `config/domains.yaml`.

```yaml
- id: "ai_policy"
  url: "https://example.com/policy"
  crawl_method: "static"
  domain_filter: "technology.ai"  # Use AI domain keywords
  # Automatically applies keywords: 人工智能, AI, 机器学习, etc.
```

**Available domains**: See `config/domains.yaml` for full list
- `technology.ai` - Artificial Intelligence
- `technology.biotech` - Biotechnology
- `economy.finance` - Finance & Banking
- `livelihood.education` - Education
- `all` - No filtering (explicit)

**Domain groups** (multiple domains):
```yaml
domain_filter: "tech_all"  # All technology subdomains
```

### 3. Custom Keyword Filtering
Define source-specific keywords (overrides domain_filter).

**Whitelist only** (keep articles matching ANY keyword):
```yaml
- id: "custom_source"
  url: "https://example.com/news"
  crawl_method: "static"
  keyword_filter:
    - "blockchain"
    - "cryptocurrency"
    - "Web3"
```

**Blacklist only** (exclude articles matching ANY keyword):
```yaml
- id: "filtered_source"
  url: "https://example.com/news"
  crawl_method: "static"
  keyword_blacklist:
    - "advertisement"
    - "sponsored"
    - "recruitment"
```

**Combined** (whitelist + blacklist):
```yaml
- id: "precise_source"
  url: "https://example.com/research"
  crawl_method: "static"
  keyword_filter: ["AI", "machine learning"]
  keyword_blacklist: ["job posting", "training course"]
  # Must match whitelist AND not match blacklist
```

## Runtime Override

Override filtering at runtime with command-line arguments:

```bash
# Use domain filter (overrides YAML config)
python scripts/crawl/run_single.py --source my_source --domain technology.ai

# Multiple domains
python scripts/crawl/run_single.py --source my_source --domain technology.ai,economy.finance

# Domain group
python scripts/crawl/run_single.py --source my_source --domain-group tech_all

# Disable all filtering
python scripts/crawl/run_single.py --source my_source --domain all
```

## Migration Guide

**Old style** (deprecated but still supported):
```yaml
default_keyword_filter:
  - "AI"
  - "人工智能"
default_keyword_blacklist:
  - "广告"
```

**New style** (recommended):
```yaml
# Option 1: Use domain classification
domain_filter: "technology.ai"

# Option 2: Source-specific keywords
keyword_filter: ["AI", "人工智能"]
keyword_blacklist: ["广告"]
```

## Best Practices

1. **Use domain_filter for common topics** - Easier to maintain, consistent across sources
2. **Use keyword_filter for niche topics** - When domain doesn't fit your specific needs
3. **Test before deploying** - Run `scripts/crawl/run_single.py` to verify filtering works
4. **Document your choices** - Add comments explaining why you chose specific filters

## Examples by Use Case

### Academic Research (AI focus)
```yaml
domain_filter: "technology.ai"
```

### Policy Monitoring (General)
```yaml
# No filter - capture all policy documents
```

### Industry News (Exclude noise)
```yaml
keyword_blacklist: ["advertisement", "sponsored", "job", "recruitment"]
```

### Multi-domain Coverage
```yaml
domain_filter: "technology.ai,economy.finance,livelihood.education"
```
