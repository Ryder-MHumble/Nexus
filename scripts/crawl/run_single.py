"""CLI tool to test a single source crawl."""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load .env file
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


async def run_crawl(source_id: str, domain: str = None, domain_group: str = None):
    from app.crawlers.registry import CrawlerRegistry
    from app.crawlers.utils.playwright_pool import close_browser
    from app.crawlers.utils.json_storage import save_crawl_result_json
    from app.scheduler.manager import load_all_source_configs
    from app.db.client import close_client, init_client
    from app.config import settings
    from app.services.domain_filter import get_domain_filter

    try:
        # Initialize DB client
        try:
            await init_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        except Exception as e:
            print(f"Warning: Failed to initialize DB client: {e}")
            print("DB unavailable, crawl results will not be persisted")

        configs = load_all_source_configs()
        config = next((c for c in configs if c["id"] == source_id), None)

        if config is None:
            print(f"Source not found: {source_id}")
            print(f"Available sources: {[c['id'] for c in configs]}")
            return

        # 解析领域关键词
        domain_keywords = None
        if domain or domain_group:
            domain_filter = get_domain_filter()
            # 如果指定了 domain/domain_group，则不使用 YAML 的 keyword_filter
            domain_keywords = domain_filter.resolve_keywords(
                domain=domain,
                domain_group=domain_group,
                custom_keywords=None,  # 命令行参数优先，不使用 YAML 配置
            )
            print(f"Domain filter: {domain or domain_group}")
            if domain_keywords:
                print(f"Keywords: {domain_keywords[:10]}..." if len(domain_keywords) > 10 else f"Keywords: {domain_keywords}")
            else:
                print("Keywords: [] (no filter)")

        print(f"\n=== Crawling: {config.get('name', source_id)} ===")
        print(f"Method: {config.get('crawl_method')}")
        print(f"URL: {config.get('url')}")
        print()

        crawler = CrawlerRegistry.create_crawler(config, domain_keywords=domain_keywords)
        result = await crawler.run()

        print("\n=== Results ===")
        print(f"Status: {result.status.value}")
        print(f"Items found: {result.items_total}")
        print(f"Items new: {result.items_new}")
        print(f"Duration: {result.duration_seconds:.1f}s")

        if result.error_message:
            print(f"Error: {result.error_message}")

        # Persist to DB
        await save_crawl_result_json(result, config)
        print("Persisted to DB (if DB client available)")

        if result.items:
            print(f"\n--- First {min(5, len(result.items))} items ---")
            for item in result.items[:5]:
                print(f"  [{item.published_at or 'no date'}] {item.title}")
                print(f"    URL: {item.url}")
                if item.content:
                    print(f"    Content: {item.content[:100]}...")
                print()
    finally:
        # Avoid subprocess cleanup warnings for dynamic crawlers in CLI mode.
        try:
            await close_browser()
        except Exception:
            pass
        try:
            await close_client()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test crawl a single source")
    parser.add_argument("--source", "-s", required=True, help="Source ID to crawl")
    parser.add_argument("--domain", "-d", help="Domain filter (e.g., technology.ai, economy.finance)")
    parser.add_argument("--domain-group", "-g", help="Domain group filter (e.g., tech_all, livelihood_all)")
    args = parser.parse_args()
    asyncio.run(run_crawl(args.source, domain=args.domain, domain_group=args.domain_group))
