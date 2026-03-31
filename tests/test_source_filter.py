# tests/test_source_filter.py
from unittest.mock import patch

from app.services.intel.shared import parse_source_filter, resolve_source_ids_by_names


def test_parse_source_filter_returns_none_when_all_params_empty():
    """所有参数为空时返回 None（不筛选）"""
    result = parse_source_filter(None, None, None, None)
    assert result is None


def test_parse_source_filter_single_id():
    """单个 source_id"""
    result = parse_source_filter("gov_cn_zhengce", None, None, None)
    assert result == {"gov_cn_zhengce"}


def test_parse_source_filter_multiple_ids():
    """逗号分隔的多个 source_ids"""
    result = parse_source_filter(None, "id1,id2,id3", None, None)
    assert result == {"id1", "id2", "id3"}


def test_parse_source_filter_whitespace_handling():
    """处理空白字符和空项"""
    result = parse_source_filter(" id1 ", " id2 , , id3 ", None, None)
    assert result == {"id1", "id2", "id3"}


def test_parse_source_filter_deduplication():
    """去重：source_id 和 source_ids 中有重复"""
    result = parse_source_filter("id1", "id1,id2", None, None)
    assert result == {"id1", "id2"}


def test_parse_source_filter_all_empty_strings():
    """全是空字符串时返回空集合"""
    result = parse_source_filter("", " , , ", None, None)
    assert result == set()


def test_resolve_source_ids_by_names_exact_match():
    """精确匹配信源名称"""
    mock_sources = [
        {"id": "gov_cn", "name": "中国政府网"},
        {"id": "xinhua", "name": "新华社"},
    ]
    with patch('app.scheduler.manager.load_all_source_configs', return_value=mock_sources):
        result = resolve_source_ids_by_names(["中国政府网"])
        assert result == {"gov_cn"}


def test_resolve_source_ids_by_names_fuzzy_match():
    """模糊匹配：子串匹配"""
    mock_sources = [
        {"id": "gov_cn", "name": "中国政府网-最新政策"},
        {"id": "beijing_gov", "name": "北京市人民政府网"},
        {"id": "xinhua", "name": "新华社"},
    ]
    with patch('app.scheduler.manager.load_all_source_configs', return_value=mock_sources):
        result = resolve_source_ids_by_names(["政府网"])
        assert result == {"gov_cn", "beijing_gov"}


def test_resolve_source_ids_by_names_case_insensitive():
    """大小写不敏感"""
    mock_sources = [
        {"id": "arxiv", "name": "ArXiv CS.AI"},
    ]
    with patch('app.scheduler.manager.load_all_source_configs', return_value=mock_sources):
        result = resolve_source_ids_by_names(["arxiv"])
        assert result == {"arxiv"}


def test_resolve_source_ids_by_names_space_handling():
    """去除空格后匹配"""
    mock_sources = [
        {"id": "gov", "name": "中国 政府 网"},
    ]
    with patch('app.scheduler.manager.load_all_source_configs', return_value=mock_sources):
        result = resolve_source_ids_by_names(["政府网"])
        assert result == {"gov"}


def test_resolve_source_ids_by_names_no_match():
    """没有匹配时返回空集合"""
    mock_sources = [
        {"id": "gov", "name": "中国政府网"},
    ]
    with patch('app.scheduler.manager.load_all_source_configs', return_value=mock_sources):
        result = resolve_source_ids_by_names(["不存在的信源"])
        assert result == set()


def test_resolve_source_ids_by_names_multiple_patterns():
    """多个名称模式"""
    mock_sources = [
        {"id": "gov", "name": "中国政府网"},
        {"id": "xinhua", "name": "新华社"},
        {"id": "people", "name": "人民日报"},
    ]
    with patch('app.scheduler.manager.load_all_source_configs', return_value=mock_sources):
        result = resolve_source_ids_by_names(["政府", "新华"])
        assert result == {"gov", "xinhua"}


def test_parse_source_filter_mixed_id_and_name():
    """混合使用 ID 和名称参数"""
    mock_sources = [
        {"id": "gov", "name": "中国政府网"},
        {"id": "xinhua", "name": "新华社"},
    ]
    with patch('app.scheduler.manager.load_all_source_configs', return_value=mock_sources):
        result = parse_source_filter("arxiv", "github", "政府", None)
        # arxiv, github (ID) + gov (from "政府" name match)
        assert result == {"arxiv", "github", "gov"}
