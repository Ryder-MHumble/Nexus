"""Scholar API — /api/v1/scholars/

Endpoints:
  GET  /scholars/                                       学者列表（分页 + 多维度筛选）
  GET  /scholars/stats                                  统计数据
  GET  /scholars/sources                                信源列表
  POST /scholars/                                       手动创建学者
  GET  /scholars/{url_hash}                             单条学者详情
  DELETE /scholars/{url_hash}                           删除学者记录
  PATCH /scholars/{url_hash}/basic                      更新基础信息（直接修改原始 JSON）
  PATCH /scholars/{url_hash}/relation                   更新合作关系字段（用户管理）
  POST  /faculty/{url_hash}/updates                    新增用户备注动态
  DELETE /scholars/{url_hash}/updates/{update_idx}      删除用户备注动态
  PATCH /scholars/{url_hash}/achievements               更新学术成就（论文、专利、奖项）
  GET  /scholars/{url_hash}/students                    查询指导学生列表
  POST /scholars/{url_hash}/students                    新增指导学生
  GET  /scholars/{url_hash}/students/{student_id}       查询单名学生详情
  PATCH /scholars/{url_hash}/students/{student_id}      更新学生信息
  DELETE /scholars/{url_hash}/students/{student_id}     删除学生记录
"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.schemas.scholar import (
    AchievementUpdate,
    ScholarBasicUpdate,
    ScholarCreateRequest,
    ScholarDetailResponse,
    ScholarImportResult,
    ScholarListResponse,
    ScholarStatsResponse,
    InstituteRelationUpdate,
    UserUpdateCreate,
)
from app.schemas.supervised_student import (
    SupervisedStudentCreate,
    SupervisedStudentListResponse,
    SupervisedStudentResponse,
    SupervisedStudentUpdate,
)
from app.services import scholar_service as svc
from app.services.stores import supervised_student_store as student_store

router = APIRouter()


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=ScholarListResponse,
    summary="学者列表",
    description=(
        "获取 scholars 维度下的学者列表，支持按高校、院系、职称、"
        "学术称号、关键词、数据完整度及信源过滤，按姓名升序排列。"
    ),
)
async def list_scholars(
    university: str | None = Query(None, description="高校名称（模糊匹配）"),
    department: str | None = Query(None, description="院系名称（模糊匹配）"),
    position: str | None = Query(
        None, description="职称（精确匹配，如 教授/副教授/研究员/助理教授）"
    ),
    is_academician: bool | None = Query(None, description="仅显示院士"),
    is_potential_recruit: bool | None = Query(None, description="仅显示潜在招募对象"),
    is_advisor_committee: bool | None = Query(None, description="仅显示顾问委员会成员"),
    is_adjunct_supervisor: bool | None = Query(None, description="仅显示兼职导师（adjunct_supervisor.status 非空）"),
    has_email: bool | None = Query(None, description="仅显示有邮箱联系方式的学者"),
    region: str | None = Query(
        None, description="地区筛选：国内 | 国际（根据高校名称自动推断）"
    ),
    affiliation_type: str | None = Query(
        None, description="机构类型筛选：高校 | 企业（公司） | 研究机构 | 其他（根据高校名称自动推断）"
    ),
    keyword: str | None = Query(
        None, description="关键词搜索（姓名/英文名/bio/研究方向/关键词）"
    ),
    community_name: str | None = Query(None, description="社群名称筛选（如 AAAI）"),
    community_type: str | None = Query(None, description="社群类型筛选（如 顶会/期刊）"),
    project_category: str | None = Query(None, description="按项目一级分类筛选（如 教育培养）"),
    project_subcategory: str | None = Query(None, description="按项目二级子类筛选（如 学术委员会）"),
    project_categories: str | None = Query(
        None,
        description="按多个项目一级分类筛选（逗号分隔，如 教育培养,科研学术）",
    ),
    project_subcategories: str | None = Query(
        None,
        description="按多个项目二级子类筛选（逗号分隔）",
    ),
    event_types: str | None = Query(
        None,
        description="按多个活动类型筛选（event_tags.event_type，逗号分隔）",
    ),
    participated_event_id: str | None = Query(None, description="按参与活动 ID 筛选"),
    is_cobuild_scholar: bool | None = Query(None, description="是否共建学者（项目分类标签非空）"),
    institution_group: str | None = Query(
        None, description="机构顶层分组（共建高校/兄弟院校/海外高校/其他高校/科研院所/行业学会）"
    ),
    institution_category: str | None = Query(
        None, description="机构细粒度分类（示范性合作伙伴/京内高校/京外C9/综合强校/工科强校/特色高校等）"
    ),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页条数"),
    custom_field_key: str | None = Query(None, description="自定义字段名（需配合 custom_field_value）"),
    custom_field_value: str | None = Query(None, description="自定义字段值"),
):
    return await svc.get_scholar_list(
        university=university,
        department=department,
        position=position,
        is_academician=is_academician,
        is_potential_recruit=is_potential_recruit,
        is_advisor_committee=is_advisor_committee,
        is_adjunct_supervisor=is_adjunct_supervisor,
        has_email=has_email,
        region=region,
        affiliation_type=affiliation_type,
        keyword=keyword,
        community_name=community_name,
        community_type=community_type,
        project_category=project_category,
        project_subcategory=project_subcategory,
        project_categories=project_categories,
        project_subcategories=project_subcategories,
        event_types=event_types,
        participated_event_id=participated_event_id,
        is_cobuild_scholar=is_cobuild_scholar,
        institution_group=institution_group,
        institution_category=institution_category,
        page=page,
        page_size=page_size,
        custom_field_key=custom_field_key,
        custom_field_value=custom_field_value,
    )


@router.get(
    "/stats",
    response_model=ScholarStatsResponse,
    summary="学者统计",
    description="返回学者库总览统计：总数、院士数、潜在招募数、按高校/职称分布、完整度分布。支持与列表接口相同的筛选参数。",
)
async def get_stats(
    university: str | None = Query(None, description="高校名称（模糊匹配）"),
    department: str | None = Query(None, description="院系名称（模糊匹配）"),
    position: str | None = Query(None, description="职称（精确匹配）"),
    is_academician: bool | None = Query(None, description="仅统计院士"),
    is_potential_recruit: bool | None = Query(None, description="仅统计潜在招募对象"),
    is_advisor_committee: bool | None = Query(None, description="仅统计顾问委员会成员"),
    is_adjunct_supervisor: bool | None = Query(None, description="仅统计兼职导师"),
    has_email: bool | None = Query(None, description="仅统计有邮箱的学者"),
    region: str | None = Query(None, description="地区筛选：国内 | 国际"),
    affiliation_type: str | None = Query(None, description="机构类型筛选：高校 | 企业（公司） | 研究机构 | 其他"),
    keyword: str | None = Query(None, description="关键词搜索"),
    community_name: str | None = Query(None, description="社群名称筛选（如 AAAI）"),
    community_type: str | None = Query(None, description="社群类型筛选（如 顶会/期刊）"),
    project_category: str | None = Query(None, description="按项目一级分类筛选"),
    project_subcategory: str | None = Query(None, description="按项目二级子类筛选"),
    project_categories: str | None = Query(None, description="按多个项目一级分类筛选（逗号分隔）"),
    project_subcategories: str | None = Query(None, description="按多个项目二级子类筛选（逗号分隔）"),
    event_types: str | None = Query(None, description="按多个活动类型筛选（逗号分隔）"),
    participated_event_id: str | None = Query(None, description="按参与活动 ID 筛选"),
    is_cobuild_scholar: bool | None = Query(None, description="是否共建学者"),
    institution_group: str | None = Query(None, description="机构顶层分组"),
    institution_category: str | None = Query(None, description="机构细粒度分类"),
    custom_field_key: str | None = Query(None, description="自定义字段名"),
    custom_field_value: str | None = Query(None, description="自定义字段值"),
):
    return await svc.get_scholar_stats(
        university=university,
        department=department,
        position=position,
        is_academician=is_academician,
        is_potential_recruit=is_potential_recruit,
        is_advisor_committee=is_advisor_committee,
        is_adjunct_supervisor=is_adjunct_supervisor,
        has_email=has_email,
        region=region,
        affiliation_type=affiliation_type,
        keyword=keyword,
        community_name=community_name,
        community_type=community_type,
        project_category=project_category,
        project_subcategory=project_subcategory,
        project_categories=project_categories,
        project_subcategories=project_subcategories,
        event_types=event_types,
        participated_event_id=participated_event_id,
        is_cobuild_scholar=is_cobuild_scholar,
        institution_group=institution_group,
        institution_category=institution_category,
        custom_field_key=custom_field_key,
        custom_field_value=custom_field_value,
    )


@router.post(
    "",
    response_model=ScholarDetailResponse,
    summary="手动创建学者",
    description=(
        "手动创建一条新的学者记录。只有 name 是必填字段，其他字段均可选。"
        "自动检测重复（同名 + 同机构 + 同联系方式），重复时返回 409 Conflict。"
        "成功创建后返回完整的学者详情（包含自动生成的 url_hash）。"
    ),
    status_code=201,
)
async def create_scholar(body: ScholarCreateRequest):
    detail, error = await svc.create_scholar(body.model_dump())

    if error.startswith("duplicate:"):
        existing_hash = error.split(":", 1)[1]
        raise HTTPException(
            status_code=409,
            detail=f"Scholar already exists with url_hash: {existing_hash}",
        )
    if error:
        raise HTTPException(status_code=400, detail=error)

    return detail


class ScholarBatchRequest(BaseModel):
    items: list[ScholarCreateRequest]
    skip_duplicates: bool = True
    added_by: str = "user"


@router.post(
    "/import",
    response_model=ScholarImportResult,
    summary="Excel/CSV 批量导入学者",
    description=(
        "上传 CSV 或 Excel (.xlsx) 文件，批量导入学者信息到 Supabase。\n\n"
        "**CSV/Excel 列名（中英文均可）：**\n"
        "姓名/name, 高校/university, 院系/department, 职称/position, 邮箱/email, "
        "电话/phone, 个人主页/profile_url, 研究方向/research_areas(逗号分隔), "
        "关键词/keywords(逗号分隔), 学术头衔/academic_titles(逗号分隔), "
        "是否院士/is_academician(是/否), 简介/bio\n\n"
        "**重复判定：** 同名 + 同机构（+ 联系方式相同），重复时默认跳过（skip_duplicates=true）。\n\n"
        "**返回：** 每行的处理结果（success/skipped/failed），以及汇总统计。"
    ),
    status_code=200,
)
async def import_scholars_file(
    file: UploadFile = File(..., description="CSV 或 .xlsx 文件"),
    skip_duplicates: bool = Query(default=True, description="重复时跳过（true）或报错（false）"),
    added_by: str = Query(default="user", description="操作人，用于审计"),
):
    content = await file.read()
    result = await svc.import_scholars_async(
        file_content=content,
        filename=file.filename or "upload.csv",
        skip_duplicates=skip_duplicates,
        added_by=added_by,
    )
    return result


@router.post(
    "/batch",
    response_model=ScholarImportResult,
    summary="JSON 批量创建学者",
    description=(
        "通过 JSON 列表批量创建学者，每条记录使用与「手动创建学者」相同的字段。\n\n"
        "**重复判定：** 同名 + 同机构（+ 联系方式相同），重复时默认跳过（skip_duplicates=true）。\n\n"
        "**返回：** 每条记录的处理结果（success/skipped/failed），以及汇总统计。"
    ),
    status_code=200,
)
async def batch_create_scholars(body: ScholarBatchRequest):
    items = [item.model_dump() for item in body.items]
    result = await svc.batch_create_scholars(
        items=items,
        skip_duplicates=body.skip_duplicates,
        added_by=body.added_by,
    )
    return result


# ---------------------------------------------------------------------------
# Write endpoints (user-managed fields only)
# ---------------------------------------------------------------------------


@router.patch(
    "/{url_hash}/basic",
    response_model=ScholarDetailResponse,
    summary="更新基础信息",
    description=(
        "更新指定学者的基础信息字段（名称、机构、院系、职称、简介、联系方式、学术链接、教育经历等）。"
        "直接修改原始 JSON 文件（data/raw/scholars/.../latest.json）。"
        "所有字段均可选，仅传入需要修改的字段；传 null 或不传则保持不变。"
        "列表字段（research_areas/keywords/academic_titles/education 等）"
        "传入 [] 表示清空，传入非空列表则完全替换。"
        "返回更新后的完整 faculty detail（包含 annotations 合并结果）。"
    ),
)
async def update_basic(url_hash: str, body: ScholarBasicUpdate):
    updates = body.model_dump(exclude_none=True)
    result = await svc.update_scholar_basic(url_hash, updates)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Faculty '{url_hash}' not found")
    return result


@router.patch(
    "/{url_hash}/relation",
    response_model=ScholarDetailResponse,
    summary="更新合作关系",
    description=(
        "更新指定学者的合作关系字段（顾问委员会、兼职导师、潜在招募等）。"
        "所有字段均可选，仅传入需要修改的字段。relation_updated_at 由服务端自动填写。"
        "这些字段永不被爬虫覆盖。"
    ),
)
async def update_relation(url_hash: str, body: InstituteRelationUpdate):
    updates = body.model_dump(exclude_none=True)
    result = await svc.update_scholar_relation(url_hash, updates)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Faculty '{url_hash}' not found")
    return result


@router.post(
    "/{url_hash}/updates",
    response_model=ScholarDetailResponse,
    summary="新增用户备注动态",
    description=(
        "为指定学者新增一条用户录入的动态备注（获奖/项目立项/任职履新等）。"
        "added_by 自动转换为 'user:{added_by}'，created_at 由服务端自动填写。"
    ),
    status_code=201,
)
async def add_update(url_hash: str, body: UserUpdateCreate):
    result = await svc.add_scholar_update(url_hash, body.model_dump())
    if result is None:
        raise HTTPException(status_code=404, detail=f"Faculty '{url_hash}' not found")
    return result


@router.delete(
    "/{url_hash}",
    summary="删除学者记录",
    description="删除指定的学者记录及其所有关联数据。",
    status_code=204,
)
async def delete_scholar(url_hash: str):
    deleted = await svc.delete_scholar(url_hash)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Faculty '{url_hash}' not found")


@router.delete(
    "/{url_hash}/updates/{update_idx}",
    response_model=ScholarDetailResponse,
    summary="删除用户备注动态",
    description=(
        "删除指定学者的用户备注动态（按 user_updates 列表中的索引）。"
        "只能删除 added_by 以 'user:' 开头的条目；尝试删除爬虫动态将返回 403。"
    ),
)
async def delete_update(url_hash: str, update_idx: int):
    try:
        result = await svc.delete_scholar_update(url_hash, update_idx)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result is None:
        raise HTTPException(status_code=404, detail=f"Faculty '{url_hash}' not found")
    return result


@router.patch(
    "/{url_hash}/achievements",
    response_model=ScholarDetailResponse,
    summary="更新学术成就",
    description=(
        "更新指定学者的学术成就字段（代表性论文、专利、获奖）。"
        "每个字段传入后会完全替换（而非追加），传 null 或不传则保持不变。"
        "这些字段由用户维护，但爬虫也可自动填充初始值。"
        "achievements_updated_at 由服务端自动填写。"
    ),
)
async def update_achievements(url_hash: str, body: AchievementUpdate):
    updates = body.model_dump(exclude_none=True)
    result = await svc.update_scholar_achievements(url_hash, updates)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Faculty '{url_hash}' not found")
    return result


@router.get(
    "/{url_hash}",
    response_model=ScholarDetailResponse,
    summary="学者详情",
    description="根据 url_hash 获取单条学者完整数据（爬虫字段 + 用户标注合并）。",
)
async def get_faculty(url_hash: str):
    result = await svc.get_scholar_detail(url_hash)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Faculty '{url_hash}' not found")
    return result


# ---------------------------------------------------------------------------
# Supervised students CRUD
# ---------------------------------------------------------------------------


async def _assert_faculty_exists(url_hash: str) -> None:
    """Raise 404 if the faculty member does not exist."""
    if await svc.get_scholar_detail(url_hash) is None:
        raise HTTPException(status_code=404, detail=f"Faculty '{url_hash}' not found")


@router.get(
    "/{url_hash}/students",
    response_model=SupervisedStudentListResponse,
    summary="查询指导学生列表",
    description="返回指定导师下的所有指导学生记录（联合培养学生）。",
)
async def list_students(url_hash: str):
    await _assert_faculty_exists(url_hash)
    students = await student_store.list_students(url_hash)
    return SupervisedStudentListResponse(
        total=len(students),
        faculty_url_hash=url_hash,
        items=students,
    )


@router.post(
    "/{url_hash}/students",
    response_model=SupervisedStudentResponse,
    summary="新增指导学生",
    description=(
        "为指定导师新增一名指导学生记录。"
        "id / created_at / updated_at 由服务端自动生成，added_by 自动补充为 'user:{added_by}'。"
    ),
    status_code=201,
)
async def add_student(url_hash: str, body: SupervisedStudentCreate):
    await _assert_faculty_exists(url_hash)
    record = await student_store.add_student(url_hash, body.model_dump())
    return record


@router.get(
    "/{url_hash}/students/{student_id}",
    response_model=SupervisedStudentResponse,
    summary="查询单名学生详情",
    description="根据学生记录 ID 获取单名指导学生的完整信息。",
)
async def get_student(url_hash: str, student_id: str):
    await _assert_faculty_exists(url_hash)
    record = await student_store.get_student(url_hash, student_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Student '{student_id}' not found")
    return record


@router.patch(
    "/{url_hash}/students/{student_id}",
    response_model=SupervisedStudentResponse,
    summary="更新学生信息",
    description=(
        "部分更新指定学生记录。所有字段均可选，传 null 或不传则保持不变。"
        "updated_at 由服务端自动更新。"
    ),
)
async def update_student(url_hash: str, student_id: str, body: SupervisedStudentUpdate):
    await _assert_faculty_exists(url_hash)
    updates = body.model_dump(exclude_none=True)
    record = await student_store.update_student(url_hash, student_id, updates)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Student '{student_id}' not found")
    return record


@router.delete(
    "/{url_hash}/students/{student_id}",
    summary="删除学生记录",
    description="删除指定导师下的一条学生记录。",
    status_code=204,
)
async def delete_student(url_hash: str, student_id: str):
    await _assert_faculty_exists(url_hash)
    deleted = await student_store.delete_student(url_hash, student_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Student '{student_id}' not found")
