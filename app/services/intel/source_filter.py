"""Source filtering utilities — resolve source IDs from names and build filter sets."""
from __future__ import annotations


def resolve_source_ids_by_names(names: list[str]) -> set[str]:
    """根据信源名称（模糊匹配）解析出信源 ID 集合。

    Args:
        names: 待匹配的名称列表

    Returns:
        匹配到的信源 ID 集合
    """
    # 避免循环导入，在函数内部导入
    from app.scheduler.manager import load_all_source_configs

    # 直接读取 YAML 配置文件（同步操作，避免事件循环冲突）
    all_sources = load_all_source_configs()
    matched_ids = set()

    for name_pattern in names:
        pattern_lower = name_pattern.lower().replace(' ', '')
        for source in all_sources:
            source_name_lower = source.get('name', '').lower().replace(' ', '')
            if pattern_lower in source_name_lower:
                matched_ids.add(source['id'])

    return matched_ids


def parse_source_filter(
    source_id: str | None,
    source_ids: str | None,
    source_name: str | None,
    source_names: str | None,
) -> set[str] | None:
    """解析信源筛选参数，返回信源 ID 集合。

    Args:
        source_id: 单个信源 ID（精确）
        source_ids: 多个信源 ID，逗号分隔（精确）
        source_name: 单个信源名称（模糊）
        source_names: 多个信源名称，逗号分隔（模糊）

    Returns:
        None: 不筛选（返回所有信源）
        set[str]: 信源 ID 集合（已去重）
    """
    if not any([source_id, source_ids, source_name, source_names]):
        return None

    result = set()

    # 处理 ID（精确匹配）
    if source_id and source_id.strip():
        result.add(source_id.strip())
    if source_ids:
        for s in source_ids.split(','):
            if s.strip():
                result.add(s.strip())

    # 处理 name（模糊匹配）
    if source_name or source_names:
        names = []
        if source_name and source_name.strip():
            names.append(source_name.strip())
        if source_names:
            for s in source_names.split(','):
                if s.strip():
                    names.append(s.strip())

        if names:
            resolved_ids = resolve_source_ids_by_names(names)
            result.update(resolved_ids)

    return result if result else set()
