# Scripts

For normal local development, prefer `./nexus.sh`. The scripts below are useful for targeted crawler verification.

## Crawl

| Script | Purpose |
| --- | --- |
| `scripts/crawl/run_single.py` | Run one source for isolated debugging: `python scripts/crawl/run_single.py --source <source_id>` |
| `scripts/crawl/run_all.py` | Run all enabled sources in the current checkout |

## Typical Workflow

```bash
./nexus.sh start
python scripts/crawl/run_single.py --source <source_id>
./nexus.sh logs backend -f
```

If you add or modify routes or schemas, refresh [`openapi.json`](../openapi.json) after verification.
