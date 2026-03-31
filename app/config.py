from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # RSSHub
    RSSHUB_BASE_URL: str = "https://rsshub.app"

    # Playwright
    PLAYWRIGHT_MAX_CONTEXTS: int = 3

    # Scheduler
    MAX_CONCURRENT_CRAWLS: int = 5
    DEFAULT_REQUEST_DELAY: float = 1.0

    # Database backend
    DB_BACKEND: str = "postgres"  # postgres | supabase

    # Local PostgreSQL (recommended)
    POSTGRES_DSN: str = ""  # optional, e.g. postgresql://user:pass@127.0.0.1:5432/zgci_db
    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "zgci_db"

    # Supabase (legacy / optional fallback)
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # Social media cookies
    WEIBO_COOKIE: str = ""
    XIAOHONGSHU_COOKIE: str = ""

    # API auth
    API_KEY: str = ""

    # OpenRouter LLM
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "google/gemini-2.0-flash-001"
    # Dedicated model for daily briefing (stronger model for better narrative)
    BRIEFING_LLM_MODEL: str = "google/gemini-2.5-pro"

    # Twitter API (twitterapi.io)
    TWITTER_API_KEY: str = ""
    TWITTER_API_PROXY: str = ""  # e.g. http://127.0.0.1:7890

    # AMiner API
    AMINER_API_KEY: str = ""
    AMINER_SCHOLAR_DETAIL_URL: str = "https://data.ihainan.me/api/aminer/scholar/detail"

    # Pipeline schedule (UTC)
    PIPELINE_CRON_HOUR: int = 6
    PIPELINE_CRON_MINUTE: int = 0

    # LLM enrichment in daily pipeline (requires OPENROUTER_API_KEY)
    ENABLE_LLM_ENRICHMENT: bool = True
    LLM_THRESHOLD: int = 40  # min matchScore for policy LLM enrichment

    # Startup behavior
    STARTUP_CRAWL_ENABLED: bool = True  # trigger pipeline on first start if no data

    # Paths
    SOURCES_DIR: Path = BASE_DIR / "sources"


settings = Settings()
