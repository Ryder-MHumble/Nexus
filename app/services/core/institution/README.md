# Institution Service - 模块化架构

## 概述

Institution Service 已完成模块化拆分，从单一的 1387 行文件拆分为多个职责清晰的模块。

## 目录结构

```
app/services/core/institution/
├── __init__.py              # 公共 API 导出
├── README.md                # 本文档
├── classification.py        # 分类体系映射和转换
├── crud.py                  # 创建、更新、删除操作
├── detail_builder.py        # 详情响应构建器
├── detail_query.py          # 详情查询
├── legacy.py                # 向后兼容层（旧 API）
├── list_query.py            # 列表查询（扁平/层级视图）
├── sorting.py               # 排序逻辑
├── storage.py               # 数据库存储层
└── taxonomy.py              # 分类体系统计
```

## 模块职责

### `__init__.py` - 公共 API
导出所有公共函数，是外部代码的唯一入口点。

**导出函数**：
- CRUD: `create_institution`, `update_institution`, `delete_institution`
- 查询: `get_institution_detail`, `get_institutions_unified`
- 统计: `get_institution_stats`, `get_institution_taxonomy`
- 兼容: `get_institution_list`, `search_institutions_for_aminer`

### `storage.py` - 数据库存储层
处理所有 Supabase 数据库交互。

**函数**：
- `fetch_all_institutions()` - 获取所有机构
- `fetch_institution_by_id(id)` - 按 ID 获取单个机构
- `upsert_institution(data)` - 插入或更新机构
- `delete_institution_by_id(id)` - 删除机构

### `classification.py` - 分类体系
处理新旧分类体系的映射和转换。

**功能**：
- 旧参数映射（type/group/category → entity_type/region/org_type/classification）
- 分类推导（sub_classification → classification）
- 分类匹配逻辑

### `list_query.py` - 列表查询
统一的机构列表查询接口，支持两种视图。

**函数**：
- `get_institutions_unified()` - 统一查询接口
  - `view="flat"` - 扁平列表（用于机构页）
  - `view="hierarchy"` - 层级结构（用于学者页）

**过滤参数**：
- `entity_type` - 实体类型（organization | department）
- `region` - 地域（国内 | 国际）
- `org_type` - 机构类型（高校 | 企业 | 研究机构 | 行业学会 | 其他）
- `classification` - 顶层分类（共建高校 | 兄弟院校 | 海外高校 | 其他高校）
- `keyword` - 关键词搜索

### `detail_query.py` - 详情查询
获取单个机构的完整信息。

**函数**：
- `get_institution_detail(id)` - 获取机构详情

### `detail_builder.py` - 详情构建器
将数据库记录转换为 API 响应格式。

**函数**：
- `build_university_detail_from_db(row)` - 构建高校详情
- `build_department_detail_from_db(row)` - 构建院系详情

### `sorting.py` - 排序逻辑
机构列表的排序规则。

**排序优先级**：
1. region（国内 > 国际）
2. org_type（高校 > 企业 > 研究机构 > 行业学会 > 其他）
3. classification（共建高校 > 兄弟院校 > 海外高校 > 其他高校）
4. priority（数字越小越靠前）
5. 声望（学生数、导师数）
6. 名称（拼音排序）

### `taxonomy.py` - 分类体系统计
生成分类体系的层级统计数据。

**函数**：
- `get_institution_taxonomy()` - 获取分类体系统计
- `get_institution_stats()` - 获取机构统计数据

**返回格式**：
```json
{
  "total": 277,
  "regions": {
    "国内": {
      "count": 250,
      "org_types": {
        "高校": {
          "count": 200,
          "classifications": {
            "共建高校": {"count": 50}
          }
        }
      }
    }
  }
}
```

### `crud.py` - CRUD 操作
创建、更新、删除机构。

**函数**：
- `create_institution(data)` - 创建机构（自动生成 ID）
- `update_institution(id, updates)` - 更新机构字段
- `delete_institution(id)` - 删除机构

**异常**：
- `InstitutionAlreadyExistsError` - ID 冲突

### `legacy.py` - 向后兼容层
为旧代码提供兼容接口。

**函数**：
- `get_institution_list()` - 旧版列表查询（映射到 `get_institutions_unified`）
- `search_institutions_for_aminer()` - AMiner 机构搜索（同步包装器）

**注意**：新代码应使用 `get_institutions_unified()` 而不是 `get_institution_list()`。

## 使用示例

### 基本导入

```python
from app.services.core.institution import (
    get_institutions_unified,
    get_institution_detail,
    create_institution,
    update_institution,
    delete_institution,
)
```

### 查询机构列表（扁平视图）

```python
# 获取所有国内高校
result = await get_institutions_unified(
    view="flat",
    entity_type="organization",
    region="国内",
    org_type="高校",
    page=1,
    page_size=20,
)
```

### 查询机构列表（层级视图）

```python
# 获取共建高校及其院系
result = await get_institutions_unified(
    view="hierarchy",
    region="国内",
    org_type="高校",
    classification="共建高校",
)
```

### 获取机构详情

```python
detail = await get_institution_detail("qinghua")
```

### 创建机构

```python
new_inst = await create_institution({
    "name": "清华大学",
    "entity_type": "organization",
    "region": "国内",
    "org_type": "高校",
    "classification": "共建高校",
})
```

### 更新机构

```python
updated = await update_institution("qinghua", {
    "priority": 1,
    "student_count_25": 5000,
})
```

### 删除机构

```python
deleted = await delete_institution("qinghua")
```

## 迁移指南

### 从旧 API 迁移

**旧代码**：
```python
from app.services.core import institution_service

result = await institution_service.get_institution_list(
    type_filter="university",
    group="共建高校",
    page=1,
    page_size=20,
)
```

**新代码**：
```python
from app.services.core.institution import get_institutions_unified

result = await get_institutions_unified(
    view="flat",
    entity_type="organization",
    org_type="高校",
    classification="共建高校",
    page=1,
    page_size=20,
)
```

### 参数映射

| 旧参数 | 新参数 | 说明 |
|--------|--------|------|
| `type_filter="university"` | `entity_type="organization"` + `org_type="高校"` | 类型拆分 |
| `type_filter="department"` | `entity_type="department"` | 院系类型 |
| `group="共建高校"` | `classification="共建高校"` | 顶层分类 |
| `category="示范性合作伙伴"` | `sub_classification="示范性合作伙伴"` | 细粒度分类 |

## 测试

```bash
# 测试导入
python3 -c "from app.services.core.institution import *; print('✓ Import OK')"

# 测试 API 导入
python3 -c "from app.api.v1 import institutions; print('✓ API OK')"
```

## 维护指南

### 添加新功能

1. 确定功能属于哪个模块（CRUD/查询/统计/分类）
2. 在对应模块中添加函数
3. 在 `__init__.py` 中导出（如果是公共 API）
4. 更新本文档

### 修改现有功能

1. 找到对应的模块文件
2. 修改函数实现
3. 确保不破坏公共 API 签名
4. 更新文档（如有必要）

### 性能优化

- 数据库查询优化：修改 `storage.py`
- 排序优化：修改 `sorting.py`
- 过滤优化：修改 `list_query.py`

## 历史

- **2026-03-15**: 完成模块化拆分，从 1387 行单文件拆分为 9 个模块
- **2026-03-13**: 开始模块化重构
- **2026-03-11**: 完成数据库迁移（Supabase）
