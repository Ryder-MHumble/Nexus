from app.services.intel.policy.source_scope import (
    get_policy_agency_type,
    get_policy_category,
    is_policy_signal_article,
)


def test_cross_dimension_policy_sources_are_included():
    talent_article = {"dimension": "talent", "group": "policy", "tags": ["talent"]}
    university_article = {
        "dimension": "universities",
        "group": "provincial",
        "tags": ["education", "policy", "shanghai"],
    }
    assert is_policy_signal_article(talent_article) is True
    assert is_policy_signal_article(university_article) is True


def test_non_policy_talent_tracking_source_is_excluded():
    article = {"dimension": "talent", "group": "tracking", "tags": ["academic"]}
    assert is_policy_signal_article(article) is False


def test_policy_category_and_agency_type_cover_new_scope():
    regional = {"dimension": "regional_policy", "source_id": "shenzhen_stic_notice"}
    talent = {"dimension": "talent", "group": "policy", "source_id": "moe_talent"}
    university = {
        "dimension": "universities",
        "group": "provincial",
        "tags": ["policy", "education"],
        "source_id": "shanghai_jw",
    }

    assert get_policy_category(regional) == "区域政策"
    assert get_policy_category(talent) == "人才政策"
    assert get_policy_category(university) == "高校政策"
    assert get_policy_category(regional, is_opportunity=True) == "政策机会"
    assert get_policy_agency_type(regional) == "regional"
    assert get_policy_agency_type(talent) == "ministry"
