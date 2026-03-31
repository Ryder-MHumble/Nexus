import pytest

from app.services.core.institution import list_query as lq
from app.services.core.institution import search as inst_search
from app.services.core.institution import taxonomy as inst_taxonomy


@pytest.mark.asyncio
async def test_flat_view_org_type_company_alias(monkeypatch):
    async def fake_fetch_all_institutions():
        return [
            {
                "id": "huawei",
                "name": "华为技术有限公司",
                "entity_type": "organization",
                "region": "国内",
                "org_type": "企业",
            },
            {
                "id": "tsinghua",
                "name": "清华大学",
                "entity_type": "organization",
                "region": "国内",
                "org_type": "高校",
            },
        ]

    monkeypatch.setattr(lq, "fetch_all_institutions", fake_fetch_all_institutions)

    result = await lq.get_institutions_unified(
        view="flat",
        entity_type="organization",
        region="国内",
        org_type="公司",
        page=1,
        page_size=20,
    )

    assert result.total == 1
    assert result.items[0].id == "huawei"


@pytest.mark.asyncio
async def test_search_org_type_company_alias(monkeypatch):
    async def fake_fetch_all_institutions():
        return [
            {
                "id": "huawei",
                "name": "华为技术有限公司",
                "entity_type": "organization",
                "region": "国内",
                "org_type": "企业",
            },
            {
                "id": "tsinghua",
                "name": "清华大学",
                "entity_type": "organization",
                "region": "国内",
                "org_type": "高校",
            },
        ]

    monkeypatch.setattr(inst_search, "fetch_all_institutions", fake_fetch_all_institutions)

    result = await inst_search.search_institutions("华为", org_type="公司")
    assert [inst["id"] for inst in result] == ["huawei"]


@pytest.mark.asyncio
async def test_taxonomy_merges_company_and_enterprise(monkeypatch):
    async def fake_fetch_all_institutions():
        return [
            {
                "id": "company_a",
                "name": "企业A",
                "entity_type": "organization",
                "region": "国内",
                "org_type": "企业",
            },
            {
                "id": "company_b",
                "name": "企业B",
                "entity_type": "organization",
                "region": "国内",
                "org_type": "公司",
            },
        ]

    monkeypatch.setattr(inst_taxonomy, "fetch_all_institutions", fake_fetch_all_institutions)

    result = await inst_taxonomy.get_institution_taxonomy()
    company_bucket = result["regions"]["国内"]["org_types"]["企业"]

    assert company_bucket["count"] == 2
    assert company_bucket["display_name"] == "公司"
    assert result["org_type_aliases"]["公司"] == "企业"
