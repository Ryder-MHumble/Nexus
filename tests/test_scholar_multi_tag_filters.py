from app.services.scholar._filters import _apply_filters


def _run_filters(items, **overrides):
    kwargs = {
        "university": None,
        "department": None,
        "position": None,
        "is_academician": None,
        "is_potential_recruit": None,
        "is_advisor_committee": None,
        "is_adjunct_supervisor": None,
        "has_email": None,
        "keyword": None,
        "project_category": None,
        "project_subcategory": None,
        "project_categories": None,
        "project_subcategories": None,
        "event_types": None,
        "participated_event_id": None,
        "is_cobuild_scholar": None,
        "region": None,
        "affiliation_type": None,
        "institution_names": None,
        "custom_field_key": None,
        "custom_field_value": None,
        "inst_map": {},
        "community_name": None,
        "community_type": None,
    }
    kwargs.update(overrides)
    return _apply_filters(items, **kwargs)


def test_multi_project_categories_filter_matches_any_category():
    items = [
        {
            "name": "A",
            "project_tags": [{"category": "教育培养", "subcategory": "学术委员会"}],
            "event_tags": [],
        },
        {
            "name": "B",
            "project_tags": [{"category": "科研学术", "subcategory": "科研立项"}],
            "event_tags": [],
        },
        {
            "name": "C",
            "project_tags": [{"category": "人才引育", "subcategory": "卓工公派"}],
            "event_tags": [],
        },
    ]

    filtered = _run_filters(items, project_categories="教育培养,科研学术")
    assert [i["name"] for i in filtered] == ["A", "B"]


def test_multi_project_subcategories_support_alias_matching():
    items = [
        {
            "name": "A",
            "project_tags": [{"category": "教育培养", "subcategory": "学院学生高校导师"}],
            "event_tags": [],
        },
        {
            "name": "B",
            "project_tags": [{"category": "教育培养", "subcategory": "教学委员会"}],
            "event_tags": [],
        },
    ]

    filtered = _run_filters(items, project_subcategories="学院学生事务导师")
    assert [i["name"] for i in filtered] == ["A"]


def test_multi_event_types_filter_matches_any_type():
    items = [
        {
            "name": "A",
            "project_tags": [],
            "event_tags": [{"category": "科研学术", "event_type": "XAI智汇讲坛"}],
        },
        {
            "name": "B",
            "project_tags": [],
            "event_tags": [{"category": "科研学术", "event_type": "学术年会"}],
        },
        {
            "name": "C",
            "project_tags": [],
            "event_tags": [{"category": "教育培养", "event_type": "开学典礼"}],
        },
    ]

    filtered = _run_filters(items, event_types="XAI智汇讲坛,学术年会")
    assert [i["name"] for i in filtered] == ["A", "B"]


def test_region_filter_includes_empty_university_as_domestic():
    items = [
        {"name": "A", "university": "", "project_tags": [], "event_tags": []},
        {"name": "B", "university": "MIT", "project_tags": [], "event_tags": []},
    ]

    domestic = _run_filters(items, region="国内")
    assert [i["name"] for i in domestic] == ["A"]


def test_affiliation_type_filter_includes_empty_university_as_other():
    items = [
        {"name": "A", "university": "", "project_tags": [], "event_tags": []},
        {"name": "B", "university": "清华大学", "project_tags": [], "event_tags": []},
    ]

    other = _run_filters(items, affiliation_type="其他")
    assert [i["name"] for i in other] == ["A"]


def test_affiliation_type_company_alias_matches_enterprise():
    items = [
        {"name": "A", "university": "华为技术有限公司", "project_tags": [], "event_tags": []},
        {"name": "B", "university": "清华大学", "project_tags": [], "event_tags": []},
    ]
    inst_map = {
        "华为技术有限公司": {"region": "国内", "org_type": "企业"},
        "清华大学": {"region": "国内", "org_type": "高校"},
    }

    company = _run_filters(items, affiliation_type="公司", inst_map=inst_map)
    assert [i["name"] for i in company] == ["A"]
