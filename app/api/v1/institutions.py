"""Institution API — /api/v1/institutions/

统一的机构接口（一级机构 + 二级机构），支持自动 ID 生成和 AMiner 标准化名自动填充

Endpoints:
  GET    /institutions/                     机构列表（分页 + 多维过滤）
  GET    /institutions/stats                统计数据（按分组/分类/优先级）
  GET    /institutions/aminer/search-org    搜索 AMiner 机构名（辅助创建）
  GET    /institutions/{id}                 机构详情（一级机构或二级机构）
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
    InstitutionHierarchyResponse,
    InstitutionListResponse,
    InstitutionSearchResponse,
    InstitutionSuggestionResponse,
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
    response_model=InstitutionListResponse | InstitutionHierarchyResponse,
    summary="机构列表（统一接口）",
    description=(
        "获取机构列表，支持扁平列表和层级结构两种视图。"
        "\n\n**视图类型（view 参数）：**"
        "\n- `flat`（默认）：扁平列表，用于「机构页」渲染组织卡片"
        "\n- `hierarchy`：层级结构，用于「学者页」支持一级机构→二级机构两级展开"
        "\n\n**分类体系：**"
        "\n- `entity_type`：实体类型（organization | department）"
        "\n- `region`：地域（国内 | 国际）"
        "\n- `org_type`：机构类型（高校 | 企业（公司） | 研究机构 | 行业学会 | 其他）"
        "\n- `classification`：顶层分类（共建高校 | 兄弟院校 | 海外高校 | 其他高校）"
        "\n\n**排序规则：**region → org_type → classification → priority → 声望 → 名称"
        "\n\n**示例：**"
        "\n- 机构页：`?view=flat&entity_type=organization&region=国内&org_type=高校`"
        "\n- 学者页：`?view=hierarchy&region=国内&org_type=高校&classification=共建高校`"
    ),
)
async def list_institutions(
    # View control
    view: str = Query(
        default="flat",
        pattern="^(flat|hierarchy)$",
        description="视图类型：flat（扁平列表）| hierarchy（层级结构）",
    ),
    # Classification parameters
    entity_type: str | None = Query(default=None, description="实体类型：organization | department"),
    region: str | None = Query(default=None, description="地域：国内 | 国际"),
    org_type: str | None = Query(default=None, description="机构类型：高校 | 企业（公司） | 研究机构 | 行业学会 | 其他"),
    classification: str | None = Query(default=None, description="顶层分类：共建高校 | 兄弟院校 | 海外高校 | 其他高校"),
    sub_classification: str | None = Query(default=None, description="二级分类"),
    # Common parameters
    keyword: str | None = Query(default=None, description="关键词搜索（机构名称或 ID）"),
    page: int = Query(default=1, ge=1, description="页码（仅 flat 视图）"),
    page_size: int = Query(default=20, ge=1, le=200, description="每页条数（仅 flat 视图）"),
    # Scholar filter
    is_adjunct_supervisor: bool | None = Query(default=None, description="仅统计共建导师（用于学者页侧边栏）"),
):
    """统一的机构查询接口，支持扁平和层级两种视图."""
    from app.services.core.institution import get_institutions_unified

    return await get_institutions_unified(
        view=view,
        entity_type=entity_type,
        region=region,
        org_type=org_type,
        classification=classification,
        sub_classification=sub_classification,
        keyword=keyword,
        page=page,
        page_size=page_size,
        is_adjunct_supervisor=is_adjunct_supervisor,
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
        "\n        \"企业\": {\"count\": 10, \"display_name\": \"公司\"},"
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


# ---------------------------------------------------------------------------
# Helper endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/search",
    response_model=InstitutionSearchResponse,
    summary="搜索机构（模糊匹配）",
    description=(
        "根据关键词搜索机构，支持模糊匹配。用于前端自动完成（autocomplete）功能。"
        "\n\n**匹配规则：**"
        "\n1. 精确匹配（最高优先级）"
        "\n2. 以关键词开头"
        "\n3. 包含关键词（不区分大小写）"
        "\n4. 字符重叠匹配"
        "\n\n**排序规则：**"
        "\n- 按相关性得分排序"
        "\n- 组织（organization）优先于院系（department）"
        "\n- 学者数量多的机构优先"
        "\n\n**Query Parameters:**"
        "\n- `q` (required): 搜索关键词"
        "\n- `limit` (optional, default=10): 返回结果数量"
        "\n- `region` (optional): 地域过滤（国内 | 国际）"
        "\n- `org_type` (optional): 机构类型过滤（高校 | 企业（公司） | 研究机构 | 其他）"
    ),
)
async def search_institutions_endpoint(
    q: str = Query(..., description="搜索关键词"),
    limit: int = Query(10, ge=1, le=50, description="返回结果数量"),
    region: str | None = Query(None, description="地域过滤"),
    org_type: str | None = Query(None, description="机构类型过滤"),
):
    """搜索机构（模糊匹配）."""
    from app.schemas.institution import InstitutionSearchResponse, InstitutionSearchResult
    from app.services.core.institution.search import search_institutions

    if not q or not q.strip():
        raise HTTPException(
            status_code=400, detail="Query parameter 'q' is required and cannot be empty"
        )

    try:
        results = await search_institutions(
            q, limit=limit, region=region, org_type=org_type
        )

        # Convert to response schema
        search_results = [
            InstitutionSearchResult(
                id=inst.get("id", ""),
                name=inst.get("name", ""),
                entity_type=inst.get("entity_type"),
                region=inst.get("region"),
                org_type=inst.get("org_type"),
                parent_id=inst.get("parent_id"),
                scholar_count=inst.get("scholar_count", 0),
            )
            for inst in results
        ]

        return InstitutionSearchResponse(
            query=q,
            total=len(search_results),
            results=search_results,
        )
    except Exception as e:
        logger.exception("Failed to search institutions: %s", e)
        raise HTTPException(status_code=500, detail=f"Search failed: {e!s}") from e


@router.get(
    "/suggest",
    response_model=InstitutionSuggestionResponse,
    summary="建议机构匹配",
    description=(
        "根据机构名称查找最佳匹配的机构。用于学者编辑时自动匹配已有机构。"
        "\n\n**返回内容：**"
        "\n- `matched`: 最佳匹配（强匹配，精确或前缀匹配）"
        "\n- `suggestions`: 建议列表（所有相关匹配）"
        "\n\n**使用场景：**"
        "\n- 用户编辑学者所属机构时，调用此接口查找是否已有该机构"
        "\n- 如果 `matched` 不为空，建议用户使用该标准名称"
        "\n- 如果 `matched` 为空但 `suggestions` 不为空，展示建议列表供用户选择"
        "\n- 如果都为空，说明是新机构，需要创建"
        "\n\n**Query Parameters:**"
        "\n- `institution_name` (recommended): 机构名称"
        "\n- `university` (legacy): 大学名称（兼容参数）"
    ),
)
async def suggest_institution_endpoint(
    institution_name: str | None = Query(None, description="机构名称"),
    university: str | None = Query(None, description="[兼容] 大学名称"),
):
    """建议机构匹配."""
    from app.schemas.institution import InstitutionSearchResult, InstitutionSuggestionResponse
    from app.services.core.institution.search import suggest_institution

    resolved_name = (institution_name or university or "").strip()
    if not resolved_name:
        raise HTTPException(
            status_code=400,
            detail="Query parameter 'institution_name' is required and cannot be empty",
        )

    try:
        result = await suggest_institution(resolved_name)

        # Convert to response schema
        matched = None
        if result.get("matched"):
            inst = result["matched"]
            matched = InstitutionSearchResult(
                id=inst.get("id", ""),
                name=inst.get("name", ""),
                entity_type=inst.get("entity_type"),
                region=inst.get("region"),
                org_type=inst.get("org_type"),
                parent_id=inst.get("parent_id"),
                scholar_count=inst.get("scholar_count", 0),
            )

        suggestions = [
            InstitutionSearchResult(
                id=inst.get("id", ""),
                name=inst.get("name", ""),
                entity_type=inst.get("entity_type"),
                region=inst.get("region"),
                org_type=inst.get("org_type"),
                parent_id=inst.get("parent_id"),
                scholar_count=inst.get("scholar_count", 0),
            )
            for inst in result.get("suggestions", [])
        ]

        return InstitutionSuggestionResponse(
            institution_name=resolved_name,
            university=resolved_name,
            matched=matched,
            suggestions=suggestions,
        )
    except Exception as e:
        logger.exception("Failed to suggest institution: %s", e)
        raise HTTPException(status_code=500, detail=f"Suggestion failed: {e!s}") from e


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
        "\n\n**一级机构详情包含：**"
        "\n- 基本信息（分类、优先级、学生数、导师数）"
        "\n- 人员信息（驻院领导、委员会、校领导、重要学者）"
        "\n- 合作信息（联合实验室、培养合作、学术合作、人才双聘）"
        "\n- 二级机构列表（`secondary_institutions`，兼容字段 `departments`）"
        "\n\n**二级机构详情包含：**"
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
        "创建新的机构记录（一级机构或二级机构）。**ID 不提供会自动生成**，让你专注于填写关键信息。"
        "\n\n## 三种使用场景"
        "\n\n### 场景 1: 新增一级机构（最简单）"
        "\n```json"
        "\n{\"name\": \"清华大学\", \"entity_type\": \"organization\", \"org_type\": \"高校\", \"region\": \"国内\", \"classification\": \"共建高校\"}"
        "\n```"
        "\nBody 最少字段：`name`, `entity_type='organization'`"
        "\n- `id` 不提供会自动生成（如 'qinghua'）"
        "\n- 可选：region, org_type, classification, priority, student_count_24/25, 人员和合作信息等"
        "\n\n### 场景 2: 新增二级机构（需选择父一级机构）"
        "\n```json"
        "\n{\"name\": \"计算机科学与技术系\", \"entity_type\": \"department\", \"parent_id\": \"qinghua\"}"
        "\n```"
        "\nBody 必填字段：`name`, `entity_type='department'`, `parent_id`"
        "\n- `id` 不提供会自动生成"
        "\n- `parent_id` 必须是已存在的一级机构 ID（可先用 GET /institutions/ 查询）"
        "\n\n### 场景 3: 一次性创建一级机构+多个二级机构"
        "\n```json"
        "\n{"
        "\n  \"name\": \"北京大学\","
        "\n  \"entity_type\": \"organization\","
        "\n  \"secondary_institutions\": ["
        "\n    {\"name\": \"计算机学院\"},"
        "\n    {\"name\": \"信息科学技术学院\"}"
        "\n  ]"
        "\n}"
        "\n```"
        "\n- 一级机构和所有二级机构的 ID 都会自动生成"
        "\n\n## 功能特性"
        "\n\n**自动生成 ID** — 从机构名称自动生成简洁易记的 ID（如 '清华' → 'qinghua'）"
        "\n\n**AMiner 标准化名** — 创建后自动调用 AMiner 机构搜索接口填充 `org_name`，"
        "获取标准化的英文机构名。查询失败不影响创建。"
        "\n\n**冲突检测** — 若 ID 已存在，返回 409 Conflict。二级机构重名仅在同一父机构下拦截。"
    ),
    status_code=201,
)
async def create_institution(body: InstitutionCreate):
    from app.services.core.institution import InstitutionAlreadyExistsError, create_institution

    inst_data = body.model_dump()
    if not inst_data.get("departments") and inst_data.get("secondary_institutions"):
        inst_data["departments"] = inst_data["secondary_institutions"]
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
        "\n\n**一级机构可更新字段：**"
        "\n- 基本信息：name, avatar（校徽图片 URL）, category, priority"
        "\n- 学生导师：student_count_24, student_count_25, mentor_count"
        "\n- 人员信息：resident_leaders, degree_committee, teaching_committee, "
        "university_leaders, notable_scholars"
        "\n- 合作信息：key_departments, joint_labs, training_cooperation, "
        "academic_cooperation, talent_dual_appointment, recruitment_events, "
        "visit_exchanges, cooperation_focus"
        "\n- 二级机构维护：`secondary_institutions`（兼容字段：`departments`）"
        "\n\n**二级机构可更新字段：**"
        "\n- name"
    ),
)
async def update_institution(institution_id: str, body: InstitutionUpdate):
    from app.services.core.institution import update_institution

    updates = body.model_dump(exclude_unset=True)
    if "secondary_institutions" in updates and "departments" not in updates:
        updates["departments"] = updates["secondary_institutions"]
    try:
        result = await update_institution(institution_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        "\n- 删除一级机构会同时删除其下所有二级机构"
        "\n- 删除二级机构不影响父一级机构"
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
