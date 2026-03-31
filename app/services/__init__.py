"""Services package — organized into sub-packages by responsibility.

Sub-packages:
  core/     — Core entity CRUD services (articles, sources, institutions, events, ...)
  stores/   — Data persistence layer (JSON stores, readers)
  llm/      — LLM API wrapper and call tracking
  external/ — Third-party API clients (AMiner, Twitter, Supabase, Sentiment)
  scholar/  — Scholar data service
  intel/    — Business intelligence (policy, personnel, tech frontier, ...)
"""
from app.services.core import (
    article_service,
    crawl_service,
    dimension_service,
    event_service,
    project_service,
    project_taxonomy_service,
    source_service,
)
from app.services.core import institution as institution_service
from app.services.external import sentiment_service
from app.services.stores import supervised_student_store

__all__ = [
    "article_service",
    "crawl_service",
    "dimension_service",
    "event_service",
    "institution_service",
    "project_service",
    "project_taxonomy_service",
    "sentiment_service",
    "source_service",
    "supervised_student_store",
]
