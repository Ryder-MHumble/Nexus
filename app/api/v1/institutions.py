"""Institution API — /api/v1/institutions/

统一的机构接口（高校 + 院系），支持自动 ID 生成和 AMiner 标准化名自动填充

Endpoints:
  GET    /institutions/                     机构列表（分页 + 多维过滤）
  GET    /institutions/stats                统计数据（按分组/分类/优先级）
  GET    /institutions/aminer/search-org    搜索 AMiner 机构名（辅助创建）
  GET    /institutions/{id}                 机构详情（高校或院系）
  POST   /institutions/                     创建机构（ID 自动生成）
  PATCH  /institutions/{id}                 更新机构
  DELETE /institutions/{id}                 删除机构
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.schemas.institution import (
    InstitutionCreate,
    InstitutionDetailResponse,
    InstitutionStatsResponse,
    InstitutionUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# List & Stats endpoints (must come before /{institution_id} to avoid catch-all)
# ---------------------------------------------------------------------------


@router.get(
    "",
    summary="机构列表（统一接口）",
    description=(
        "获取机构列表，支持扁平列表和层级结构两种视图。"
        "\n\n**视图类型（view 参数）：**"
        "\n- `flat`（默认）：扁平列表，用于「机构页」渲染组织卡片"
        "\n- `hierarchy`：层级结构，用于「学者页」支持高校→院系两级展开"
        "\n\n**分类体系：**"
        "\n- `entity_type`：实体类型（organization | department）"
        "\n- `region`：地域（国内 | 国际）"
        "\n- `org_type`：机构类型（高校 | 企业 | 研究机构 | 行业学会 | 其他）"
        "\n- `classification`：顶层分类（共建高校 | 兄弟院校 | 海外高校 | 其他高校）"
        "\n\n**排序规则：**region → org_type → classification → priority → 声望 → 名称"
        "\n\n**示例：**"
        "\n- 机构页：`?view=flat&entity_type=organization&region=国内&org_type=高校`"
        "\n- 学者页：`?view=hierarchy&region=国内&org_type=高校&classification=共建高校`"
    ),
)
async def list_institutions(
    # View control
    view: str = Query(default="flat", description="视图类型：flat（扁平列表）| hierarchy（层级结构）"),
    # Classification parameters
    entity_type: str | None = Query(default=None, description="实体类型：organization | department"),
    region: str | None = Query(default=None, description="地域：国内 | 国际"),
    org_type: str | None = Query(default=None, description="机构类型：高校 | 企业 | 研究机构 | 行业学会 | 其他"),
    classification: str | None = Query(default=None, description="顶层分类：共建高校 | 兄弟院校 | 海外高校 | 其他高校"),
    # Common parameters
    keyword: str | None = Query(default=None, description="关键词搜索（机构名称或 ID）"),
    page: int = Query(default=1, ge=1, description="页码（仅 flat 视图）"),
    page_size: int = Query(default=20, ge=1, le=200, description="每页条数（仅 flat 视图）"),
):
    """统一的机构查询接口，支持扁平和层级两种视图."""
    from app.services.core.institution import get_institutions_unified

    return await get_institutions_unified(
        view=view,
        entity_type=entity_type,
        region=region,
        org_type=org_type,
        classification=classification,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/stats",
    response_model=InstitutionStatsResponse,
    summary="机构统计",
    description="返回机构统计数据：总数、按分类/优先级分布、学生/导师总数。",
)
async def get_institution_stats():
    from app.services.core.institution import get_institution_stats

    return await get_institution_stats()


@router.get(
    "/taxonomy",
    summary="分类体系统计",
    description=(
        "返回机构分类体系的层级结构和统计数据，用于前端动态渲染导航栏。"
        "\n\n返回格式："
        "\n```json"
        "\n{"
        "\n  \"total\": 277,"
        "\n  \"regions\": {"
        "\n    \"国内\": {"
        "\n      \"count\": 250,"
        "\n      \"org_types\": {"
        "\n        \"高校\": {"
        "\n          \"count\": 200,"
        "\n          \"classifications\": {"
        "\n            \"共建高校\": {\"count\": 50},"
        "\n            \"兄弟院校\": {\"count\": 80}"
        "\n          }"
        "\n        },"
        "\n        \"企业\": {\"count\": 10},"
        "\n        \"研究机构\": {\"count\": 15}"
        "\n      }"
        "\n    },"
        "\n    \"国际\": {\"count\": 27, \"org_types\": {...}}"
        "\n  }"
        "\n}"
        "\n```"
    ),
)
async def get_institution_taxonomy():
    from app.services.core.institution import get_institution_taxonomy

    return await get_institution_taxonomy()



@router.get(
    "/taxonomy",
    summary="分类体系统计",
    description=(
        "返回分类体系的层级统计，用于前端动态渲染导航栏。"
        "\n\n**返回格式：**"
        "\n```json"
        "\n{"
        "\n  \"total\": 277,"
        "\n  \"regions\": {"
        "\n    \"国内\": {"
        "\n      \"count\": 250,"
        "\n      \"org_types\": {"
        "\n        \"高校\": {"
        "\n          \"count\": 200,"
        "\n          \"classifications\": {"
        "\n            \"共建高校\": {\"count\": 50},"
        "\n            \"兄弟院校\": {\"count\": 80},"
        "\n            \"海外高校\": {\"count\": 50},"
        "\n            \"其他高校\": {\"count\": 20}"
        "\n          }"
        "\n        },"
        "\n        \"企业\": {\"count\": 10},"
        "\n        \"研究机构\": {\"count\": 15}"
        "\n      }"
        "\n    },"
        "\n    \"国际\": {\"count\": 27, \"org_types\": {...}}"
        "\n  }"
        "\n}"
        "\n```"
    ),
)
async def get_institution_taxonomy():
    """返回分类体系的层级统计（region → org_type → classification）."""
    from app.services.core.institution import get_institution_taxonomy

    return await get_institution_taxonomy()


# ---------------------------------------------------------------------------
# Helper endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/aminer/search-org",
    summary="搜索 AMiner 机构名",
    description=(
        "搜索 AMiner 数据库中的机构信息，获取标准化的英文机构名（org_name）。"
        "\n\n此端点用于辅助机构创建：用户在创建高校或院系时，可先调用此接口查询"
        "对应的 AMiner 标准化名称，然后在创建请求中传入 `org_name` 字段。"
        "\n\n**Query Parameters:**"
        "\n- `q` (required): 机构名称（中文或英文均可），如 '清华大学' 或 'Tsinghua'"
        "\n- `size` (optional, default=5): 返回的结果数量，最多 10 个"
        "\n\n**返回示例：**"
        "\n```json"
        "\n{"
        "\n  \"query\": \"清华大学\","
        "\n  \"total\": 3,"
        "\n  \"items\": ["
        "\n    {\"id\": \"...\", \"name\": \"清华大学\", \"name_en\": \"Tsinghua University\", \"country\": \"China\"},"
        "\n    {\"id\": \"...\", \"name\": \"清华大学\", \"name_en\": \"Tsinghua Univ.\", \"country\": \"China\"}"
        "\n  ]"
        "\n}"
        "\n```"
    ),
)
async def search_aminer_organizations(q: str, size: int = 5):
    """搜索 AMiner 机构名."""
    if not q or not q.strip():
        raise HTTPException(
            status_code=400, detail="Query parameter 'q' is required and cannot be empty"
        )

    if size < 1 or size > 10:
        size = min(max(size, 1), 10)

    try:
        from app.services.external.aminer_client import get_aminer_client

        client = get_aminer_client()
        resp = await client.search_organizations(q, size=size)

        # Normalize response
        items = resp.get("data", [])
        return {
            "query": q,
            "total": len(items),
            "items": items,
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"AMiner API configuration error: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("AMiner search failed for '%s': %s", q, exc)
        raise HTTPException(
            status_code=502,
            detail=f"AMiner search failed: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{institution_id}",
    response_model=InstitutionDetailResponse,
    summary="机构详情",
    description=(
        "根据机构 ID 获取完整机构信息。"
        "\n\n**高校详情包含：**"
        "\n- 基本信息（分类、优先级、学生数、导师数）"
        "\n- 人员信息（驻院领导、委员会、校领导、重要学者）"
        "\n- 合作信息（联合实验室、培养合作、学术合作、人才双聘）"
        "\n- 院系列表"
        "\n\n**院系详情包含：**"
        "\n- 基本信息（名称、学者数）"
        "\n- 信源列表（source_id, source_name, scholar_count, is_enabled）"
    ),
)
async def get_institution(institution_id: str):
    from app.services.core.institution import get_institution_detail

    result = await get_institution_detail(institution_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Institution '{institution_id}' not found"
        )
    return result


# ---------------------------------------------------------------------------
# Write endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=InstitutionDetailResponse,
    summary="创建机构（支持简化模式）",
    description=(
        "创建新的机构记录（高校或院系）。**ID 不提供会自动生成**，让你专注于填写关键信息。"
        "\n\n## 三种使用场景"
        "\n\n### 场景 1: 新增高校（最简单）"
        "\n```json"
        "\n{\"name\": \"清华大学\", \"entity_type\": \"organization\", \"org_type\": \"高校\", \"region\": \"国内\", \"classification\": \"共建高校\"}"
        "\n```"
        "\nBody 最少字段：`name`, `entity_type='organization'`"
        "\n- `id` 不提供会自动生成（如 'qinghua'）"
        "\n- 可选：region, org_type, classification, priority, student_count_24/25, 人员和合作信息等"
        "\n\n### 场景 2: 新增院系（需选择高校）"
        "\n```json"
        "\n{\"name\": \"计算机科学与技术系\", \"entity_type\": \"department\", \"parent_id\": \"qinghua\"}"
        "\n```"
        "\nBody 必填字段：`name`, `entity_type='department'`, `parent_id`"
        "\n- `id` 不提供会自动生成"
        "\n- `parent_id` 必须是已存在的高校 ID（可先用 GET /institutions/ 查询）"
        "\n\n### 场景 3: 一次性创建高校+多个院系"
        "\n```json"
        "\n{"
        "\n  \"name\": \"北京大学\","
        "\n  \"entity_type\": \"organization\","
        "\n  \"departments\": ["
        "\n    {\"name\": \"计算机学院\"},"
        "\n    {\"name\": \"信息科学技术学院\"}"
        "\n  ]"
        "\n}"
        "\n```"
        "\n- 高校和所有院系的 ID 都会自动生成"
        "\n\n## 功能特性"
        "\n\n**自动生成 ID** — 从机构名称自动生成简洁易记的 ID（如 '清华' → 'qinghua'）"
        "\n\n**AMiner 标准化名** — 创建后自动调用 AMiner 机构搜索接口填充 `org_name`，"
        "获取标准化的英文机构名。查询失败不影响创建。"
        "\n\n**冲突检测** — 若 ID 已存在，返回 409 Conflict。院系 ID 必须全局唯一。"
    ),
    status_code=201,
)
async def create_institution(body: InstitutionCreate):
    from app.services.core.institution import InstitutionAlreadyExistsError, create_institution

    inst_data = body.model_dump()
    try:
        result = await create_institution(inst_data)
    except InstitutionAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 若 org_name 未传入，自动从 AMiner 查询并写回
    if not inst_data.get("org_name"):
        try:
            from app.services.external.aminer_client import get_aminer_client
            from app.services.core.institution import update_institution

            client = get_aminer_client()
            aminer_resp = await client.search_organizations(body.name)
            orgs = aminer_resp.get("data", [])
            if orgs:
                fetched_org_name = orgs[0].get("name_en") or orgs[0].get("name")
                if fetched_org_name:
                    updated = await update_institution(result.id, {"org_name": fetched_org_name})
                    if updated:
                        result = updated
                        logger.info(
                            "AMiner org_name auto-filled for '%s': %s",
                            result.id,
                            fetched_org_name,
                        )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "AMiner org_name lookup failed for '%s' (%s): %s",
                body.name,
                body.id,
                exc,
            )

    return result


@router.patch(
    "/{institution_id}",
    response_model=InstitutionDetailResponse,
    summary="更新机构",
    description=(
        "更新指定机构的信息。所有字段均可选，仅传入需要修改的字段。"
        "\n\n**高校可更新字段：**"
        "\n- 基本信息：name, avatar（校徽图片 URL）, category, priority"
        "\n- 学生导师：student_count_24, student_count_25, mentor_count"
        "\n- 人员信息：resident_leaders, degree_committee, teaching_committee, "
        "university_leaders, notable_scholars"
        "\n- 合作信息：key_departments, joint_labs, training_cooperation, "
        "academic_cooperation, talent_dual_appointment, recruitment_events, "
        "visit_exchanges, cooperation_focus"
        "\n\n**院系可更新字段：**"
        "\n- name"
    ),
)
async def update_institution(institution_id: str, body: InstitutionUpdate):
    from app.services.core.institution import update_institution

    updates = body.model_dump(exclude_none=True)
    result = await update_institution(institution_id, updates)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Institution '{institution_id}' not found"
        )
    return result


@router.delete(
    "/{institution_id}",
    summary="删除机构",
    description=(
        "删除指定的机构记录。"
        "\n\n**注意：**"
        "\n- 删除高校会同时删除其下所有院系"
        "\n- 删除院系不影响父高校"
    ),
    status_code=204,
)
async def delete_institution(institution_id: str):
    from app.services.core.institution import delete_institution

    deleted = await delete_institution(institution_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Institution '{institution_id}' not found"
        )
