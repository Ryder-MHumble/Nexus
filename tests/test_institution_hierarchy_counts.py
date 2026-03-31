import pytest

from app.services.core.institution import list_query as lq
from app.services.scholar import _filters as scholar_filters


def _mock_scholar_aggregation():
    counts = {
        ("org", "清华大学"): 100,
        ("dept", "清华大学", "计算机系"): 60,
        ("dept", "清华大学", "软件学院"): 40,
        ("org", "北航"): 50,
        ("dept", "北航", "计算机学院"): 50,
    }
    university_names = {
        "清华大学": "清华大学",
        "北航": "北航",
    }
    department_names = {
        "清华大学": {"计算机系": "计算机系", "软件学院": "软件学院"},
        "北航": {"计算机学院": "计算机学院"},
    }
    return counts, university_names, department_names


@pytest.mark.asyncio
async def test_hierarchy_includes_virtual_org_and_missing_departments(monkeypatch):
    async def fake_get_inst_map():
        return {}

    async def fake_fetch_all_institutions():
        return [
            {
                "id": "tsinghua",
                "name": "清华大学",
                "entity_type": "organization",
                "region": "国内",
                "org_type": "高校",
                "classification": "共建高校",
                "sub_classification": "示范性合作伙伴",
            },
            {
                "id": "tsinghua_cs",
                "name": "计算机系",
                "entity_type": "department",
                "parent_id": "tsinghua",
            },
        ]

    async def fake_aggregate_scholars_by_institution(is_adjunct_supervisor=None):
        assert is_adjunct_supervisor is None
        return _mock_scholar_aggregation()

    monkeypatch.setattr(lq, "fetch_all_institutions", fake_fetch_all_institutions)
    monkeypatch.setattr(
        lq,
        "_aggregate_scholars_by_institution",
        fake_aggregate_scholars_by_institution,
    )
    monkeypatch.setattr(
        scholar_filters,
        "get_institution_classification_map",
        fake_get_inst_map,
    )

    result = await lq._get_hierarchy_view()
    assert result["primary_institutions"] == result["organizations"]
    organizations = result["organizations"]
    by_name = {org["name"]: org for org in organizations}

    assert set(by_name.keys()) == {"清华大学", "北航"}
    assert by_name["清华大学"]["scholar_count"] == 100
    assert by_name["北航"]["scholar_count"] == 50
    assert by_name["北航"]["id"].startswith("virtual_org_")
    assert by_name["清华大学"]["secondary_institutions"] == by_name["清华大学"]["departments"]

    dept_by_name = {
        d["name"]: d["scholar_count"]
        for d in by_name["清华大学"]["departments"]
    }
    assert dept_by_name["计算机系"] == 60
    assert dept_by_name["软件学院"] == 40

    assert sum(org["scholar_count"] for org in organizations) == 150


@pytest.mark.asyncio
async def test_hierarchy_virtual_org_respects_classification_filter(monkeypatch):
    async def fake_get_inst_map():
        return {}

    async def fake_fetch_all_institutions():
        return [
            {
                "id": "tsinghua",
                "name": "清华大学",
                "entity_type": "organization",
                "region": "国内",
                "org_type": "高校",
                "classification": "共建高校",
            }
        ]

    async def fake_aggregate_scholars_by_institution(is_adjunct_supervisor=None):
        return _mock_scholar_aggregation()

    monkeypatch.setattr(lq, "fetch_all_institutions", fake_fetch_all_institutions)
    monkeypatch.setattr(
        lq,
        "_aggregate_scholars_by_institution",
        fake_aggregate_scholars_by_institution,
    )
    monkeypatch.setattr(
        scholar_filters,
        "get_institution_classification_map",
        fake_get_inst_map,
    )

    result = await lq._get_hierarchy_view(classification="共建高校")
    assert result["primary_institutions"] == result["organizations"]
    organizations = result["organizations"]

    assert [org["name"] for org in organizations] == ["清华大学"]
    assert organizations[0]["scholar_count"] == 100


@pytest.mark.asyncio
async def test_hierarchy_region_filters_do_not_double_count_duplicate_org_rows(monkeypatch):
    async def fake_fetch_all_institutions():
        return [
            {
                "id": "org_cn",
                "name": "清华大学",
                "entity_type": "organization",
                "region": "国内",
                "org_type": "高校",
            },
            {
                "id": "org_cn_dup",
                "name": "清华大学",
                "entity_type": "organization",
                "region": "国际",
                "org_type": "高校",
            },
            {
                "id": "org_intl",
                "name": "MIT",
                "entity_type": "organization",
                "region": "国际",
                "org_type": "高校",
            },
        ]

    async def fake_aggregate_scholars_by_institution(is_adjunct_supervisor=None):
        return (
            {
                ("org", "清华大学"): 100,
                ("org", "mit"): 50,
            },
            {
                "清华大学": "清华大学",
                "mit": "MIT",
            },
            {},
        )

    async def fake_get_inst_map():
        return {
            "清华大学": {"region": "国内", "org_type": "高校"},
            "MIT": {"region": "国际", "org_type": "高校"},
        }

    monkeypatch.setattr(lq, "fetch_all_institutions", fake_fetch_all_institutions)
    monkeypatch.setattr(
        lq,
        "_aggregate_scholars_by_institution",
        fake_aggregate_scholars_by_institution,
    )
    monkeypatch.setattr(
        scholar_filters,
        "get_institution_classification_map",
        fake_get_inst_map,
    )

    domestic = await lq._get_hierarchy_view(region="国内")
    international = await lq._get_hierarchy_view(region="国际")
    all_orgs = await lq._get_hierarchy_view()

    assert domestic["primary_institutions"] == domestic["organizations"]
    assert international["primary_institutions"] == international["organizations"]
    assert all_orgs["primary_institutions"] == all_orgs["organizations"]

    assert [org["name"] for org in domestic["organizations"]] == ["清华大学"]
    assert [org["name"] for org in international["organizations"]] == ["MIT"]
    assert sum(org["scholar_count"] for org in domestic["organizations"]) == 100
    assert sum(org["scholar_count"] for org in international["organizations"]) == 50
    assert sum(org["scholar_count"] for org in all_orgs["organizations"]) == 150
