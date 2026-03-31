from unittest.mock import AsyncMock, patch

import pytest

from app.services.core import source_service

MOCK_CONFIGS = [
    {
        "id": "leaders_tsinghua",
        "name": "清华大学-现任领导",
        "url": "https://example.com/leader",
        "dimension": "personnel",
        "dimension_name": "对人事",
        "group": "university_leadership_official",
        "tags": ["personnel", "leadership", "official"],
        "crawl_method": "university_leadership",
        "schedule": "weekly",
        "priority": 1,
        "is_enabled": True,
        "source_file": "university_leadership_sources.yaml",
    },
    {
        "id": "scholar_tsinghua",
        "name": "清华大学-师资",
        "url": "https://example.com/scholar",
        "dimension": "scholars",
        "dimension_name": "高校师资",
        "group": "tsinghua",
        "tags": ["faculty", "tsinghua", "ai"],
        "crawl_method": "faculty",
        "schedule": "weekly",
        "priority": 2,
        "is_enabled": False,
        "source_file": "scholar-tsinghua.yaml",
    },
    {
        "id": "policy_state_council",
        "name": "国务院政策",
        "url": "https://example.com/policy",
        "dimension": "national_policy",
        "dimension_name": "对国家",
        "group": "policy",
        "tags": ["policy", "state_council"],
        "crawl_method": "static",
        "schedule": "daily",
        "priority": 1,
        "is_enabled": True,
        "source_file": "national_policy.yaml",
    },
]

MOCK_STATES = {
    "leaders_tsinghua": {
        "last_crawl_at": "2026-03-29T10:00:00+00:00",
        "consecutive_failures": 0,
    },
    "scholar_tsinghua": {
        "is_enabled_override": True,
        "consecutive_failures": 1,
    },
    "policy_state_council": {
        "consecutive_failures": 3,
    },
}


def _mock_deps():
    return patch(
        "app.services.core.source_service.load_all_source_configs",
        return_value=MOCK_CONFIGS,
    ), patch(
        "app.services.core.source_service.get_all_source_states",
        new=AsyncMock(return_value=MOCK_STATES),
    )


@pytest.mark.asyncio
async def test_list_sources_supports_tag_and_enable_filters():
    p1, p2 = _mock_deps()
    with p1, p2:
        result = await source_service.list_sources(
            tags="leadership,faculty",
            is_enabled=True,
            sort_by="id",
        )

    ids = {item["id"] for item in result}
    assert ids == {"leaders_tsinghua", "scholar_tsinghua"}
    scholar_item = next(item for item in result if item["id"] == "scholar_tsinghua")
    assert scholar_item["is_enabled"] is True
    assert scholar_item["is_enabled_overridden"] is True
    assert scholar_item["health_status"] == "warning"


@pytest.mark.asyncio
async def test_list_sources_filters_health_status():
    p1, p2 = _mock_deps()
    with p1, p2:
        result = await source_service.list_sources(health_status="failing")

    assert len(result) == 1
    assert result[0]["id"] == "policy_state_council"
    assert result[0]["health_status"] == "failing"


@pytest.mark.asyncio
async def test_list_source_facets_returns_dimension_and_tags():
    p1, p2 = _mock_deps()
    with p1, p2:
        facets = await source_service.list_source_facets(dimensions="personnel,scholars")

    dimensions = {item["key"]: item for item in facets["dimensions"]}
    assert dimensions["personnel"]["count"] == 1
    assert dimensions["personnel"]["enabled_count"] == 1
    assert dimensions["scholars"]["count"] == 1
    assert dimensions["scholars"]["enabled_count"] == 1
    tags = {item["key"]: item["count"] for item in facets["tags"]}
    assert tags["leadership"] == 1
    assert tags["faculty"] == 1


@pytest.mark.asyncio
async def test_list_sources_catalog_pagination_and_applied_filters():
    p1, p2 = _mock_deps()
    with p1, p2:
        result = await source_service.list_sources_catalog(
            keyword="清华",
            page=1,
            page_size=1,
            sort_by="name",
            include_facets=True,
        )

    assert result["total_sources"] == 3
    assert result["filtered_sources"] == 2
    assert result["page"] == 1
    assert result["page_size"] == 1
    assert result["total_pages"] == 2
    assert len(result["items"]) == 1
    assert result["facets"] is not None
    assert result["applied_filters"]["keyword"] == "清华"
