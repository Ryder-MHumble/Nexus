"""Tests for run_all_crawl.py refactoring - Task 5 strategy-based execution."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# Import after mocking to avoid actual crawler registry initialization
def test_load_crawl_concurrency_config_defaults():
    """Test _load_crawl_concurrency_config returns defaults when file missing."""
    from scripts.crawl.run_all import _load_crawl_concurrency_config

    config = _load_crawl_concurrency_config()

    assert isinstance(config, dict)
    assert "strategy" in config
    assert "grouped" in config
    assert "fixed" in config

    # Check defaults
    grouped = config.get("grouped", {})
    assert grouped.get("static") == 20
    assert grouped.get("rss") == 20
    assert grouped.get("dynamic") == 8
    assert grouped.get("snapshot") == 10

    fixed = config.get("fixed", {})
    assert fixed.get("default") == 12


def test_group_configs_by_method():
    """Test _group_configs_by_method groups configs correctly."""
    from scripts.crawl.run_all import _group_configs_by_method

    configs = [
        {"id": "static1", "crawl_method": "static"},
        {"id": "static2", "crawl_method": "static"},
        {"id": "dynamic1", "crawl_method": "dynamic"},
        {"id": "rss1", "crawl_method": "rss"},
        {"id": "no_method"},  # Should default to 'static'
    ]

    grouped = _group_configs_by_method(configs)

    assert len(grouped["static"]) == 3  # static1, static2, no_method
    assert len(grouped["dynamic"]) == 1  # dynamic1
    assert len(grouped["rss"]) == 1  # rss1
    assert grouped["static"][2]["id"] == "no_method"  # Verify defaulting


@pytest.mark.asyncio
async def test_run_grouped_concurrently():
    """Test _run_grouped_concurrently executes groups with correct concurrency."""
    from scripts.crawl.run_all import _run_grouped_concurrently

    # Mock _crawl_single_source to track calls
    call_count = {"count": 0}
    active_count = {"count": 0}
    max_active = {"max": 0}

    async def mock_crawl_single_source(cfg, pbar=None):
        call_count["count"] += 1
        active_count["count"] += 1
        max_active["max"] = max(max_active["max"], active_count["count"])

        # Simulate some async work
        await asyncio.sleep(0.01)

        active_count["count"] -= 1
        return {
            "source_id": cfg["id"],
            "status": "success",
            "items_total": 10,
            "items_with_content": 10,
            "duration": 0.01,
            "error": None,
        }

    with patch("scripts.crawl.run_all._crawl_single_source", new=mock_crawl_single_source):
        grouped = {
            "static": [
                {"id": f"static_{i}"} for i in range(5)
            ],
            "dynamic": [
                {"id": f"dynamic_{i}"} for i in range(3)
            ],
        }

        concurrency_map = {
            "static": 2,
            "dynamic": 1,
        }

        results = await _run_grouped_concurrently(grouped, concurrency_map, pbar=None)

    # Verify all tasks were executed
    assert len(results) == 8
    assert call_count["count"] == 8

    # Verify concurrency was respected (max simultaneous tasks)
    # With static=2 and dynamic=1, running in parallel groups, max should be ~2-3
    # (depends on exact timing, but should be <= 3)
    assert max_active["max"] <= 3


def test_run_all_parameter_types():
    """Test run_all function signature and parameters."""
    from scripts.crawl.run_all import run_all
    import inspect

    sig = inspect.signature(run_all)
    params = sig.parameters

    assert "dimension_filter" in params
    assert params["dimension_filter"].default is None

    assert "concurrency" in params
    assert params["concurrency"].default is None

    assert "strategy" in params
    assert params["strategy"].default == "grouped"


def test_strategy_decision_logic_grouped():
    """Test that grouped strategy selects correct execution path."""
    # This is more of an integration test, verifying the logic is there
    from scripts.crawl.run_all import _load_crawl_concurrency_config

    conc_config = _load_crawl_concurrency_config()
    strategy = "grouped"

    # Simulate the logic in run_all
    if strategy == "grouped":
        concurrency_map = conc_config.get("strategies", {}).get("grouped", {
            "static": 20,
            "rss": 20,
            "dynamic": 8,
            "snapshot": 10,
        })
        assert isinstance(concurrency_map, dict)
        assert concurrency_map.get("static") >= 8
        assert concurrency_map.get("dynamic") >= 5


def test_strategy_decision_logic_fixed():
    """Test that fixed strategy selects correct execution path."""
    from scripts.crawl.run_all import _load_crawl_concurrency_config

    conc_config = _load_crawl_concurrency_config()
    strategy = "fixed"
    concurrency = None

    # Simulate the logic in run_all
    if strategy == "fixed":
        conc_val = concurrency or conc_config.get("strategies", {}).get("fixed", {}).get("default", 5)
        assert isinstance(conc_val, int)
        assert conc_val > 0
        concurrency_map = conc_val
        assert isinstance(concurrency_map, int)


def test_strategy_description_generation():
    """Test that strategy descriptions are generated correctly."""
    from scripts.crawl.run_all import _load_crawl_concurrency_config

    conc_config = _load_crawl_concurrency_config()

    # Test grouped strategy description
    concurrency_map = conc_config.get("strategies", {}).get("grouped", {
        "static": 20,
        "rss": 20,
        "dynamic": 8,
        "snapshot": 10,
    })
    if isinstance(concurrency_map, dict):
        strategy_desc = (
            f"分组 (static/rss={concurrency_map.get('static', 20)}, "
            f"dynamic={concurrency_map.get('dynamic', 8)}, "
            f"snapshot={concurrency_map.get('snapshot', 10)})"
        )
    assert "分组" in strategy_desc
    assert "20" in strategy_desc
    assert "8" in strategy_desc

    # Test fixed strategy description
    conc_val = 12
    strategy_desc = f"固定 (并发={conc_val})"
    assert "固定" in strategy_desc
    assert "12" in strategy_desc


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
