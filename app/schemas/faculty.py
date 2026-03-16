"""Pydantic schemas for the Scholar API (/api/v1/scholars/)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# List item (lightweight, for GET /faculty/)
# ---------------------------------------------------------------------------


class ScholarListItem(BaseModel):
    """Single row in the faculty list — key fields only."""

    url_hash: str = Field(description="师资唯一 ID (url_hash of profile_url)")
    name: str = Field(description="中文姓名")
    name_en: str = Field(default="", description="英文姓名")
    photo_url: str = Field(default="", description="照片 URL")
    university: str = Field(default="", description="所属大学")
    department: str = Field(default="", description="所属院系")
    position: str = Field(default="", description="职称")
    academic_titles: list[str] = Field(default_factory=list, description="学术头衔（杰青/院士等）")
    is_academician: bool = Field(default=False, description="是否院士")
    research_areas: list[str] = Field(default_factory=list, description="研究方向")
    email: str = Field(default="", description="邮箱")
    profile_url: str = Field(default="", description="个人主页 URL")
    source_id: str = Field(default="", description="信源 ID")
    group: str = Field(default="", description="信源分组（高校名缩写）")
    data_completeness: int = Field(default=0, description="数据完整度 0–100")
    # User-managed fields (merged from annotations)
    is_potential_recruit: bool = Field(default=False, description="潜在招募对象")
    is_advisor_committee: bool = Field(default=False, description="顾问委员会成员")
    is_adjunct_supervisor: bool = Field(default=False, description="兼职导师")
    crawled_at: str = Field(default="", description="最后爬取时间 ISO8601")


class ScholarListResponse(BaseModel):
    """Response for GET /faculty/."""

    total: int = Field(description="符合条件的总师资数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页条数")
    total_pages: int = Field(description="总页数")
    items: list[ScholarListItem]


# ---------------------------------------------------------------------------
# Detail response (full FacultyRecord + user annotations merged)
# ---------------------------------------------------------------------------


class ScholarDetailResponse(BaseModel):
    """Full faculty record: crawled fields + user annotations merged."""

    # Identity
    url_hash: str
    source_id: str
    group: str
    # Basic
    name: str
    name_en: str
    gender: str
    photo_url: str
    # Affiliation
    university: str
    department: str
    secondary_departments: list[str]
    # Title
    position: str
    academic_titles: list[str]
    is_academician: bool
    # Research
    research_areas: list[str]
    keywords: list[str]
    bio: str
    bio_en: str
    # Contact
    email: str
    phone: str
    office: str
    # URLs
    profile_url: str
    lab_url: str
    google_scholar_url: str
    dblp_url: str
    orcid: str
    # Education
    phd_institution: str
    phd_year: str
    education: list[dict[str, Any]]
    # Metrics
    publications_count: int
    h_index: int
    citations_count: int
    metrics_updated_at: str
    # Achievements [crawler + user-managed]
    representative_publications: list[dict[str, Any]]
    patents: list[dict[str, Any]]
    awards: list[dict[str, Any]]
    # Institute relations [user-managed]
    is_advisor_committee: bool
    is_adjunct_supervisor: bool
    supervised_students: list[Any]
    supervised_students_count: int = 0
    joint_research_projects: list[Any]
    joint_management_roles: list[Any]
    academic_exchange_records: list[Any]
    is_potential_recruit: bool
    institute_relation_notes: str
    relation_updated_by: str
    relation_updated_at: str
    # Dynamic updates (crawler + user)
    recent_updates: list[dict[str, Any]]
    # Meta
    source_url: str
    crawled_at: str
    first_seen_at: str
    last_seen_at: str
    is_active: bool
    data_completeness: int


# ---------------------------------------------------------------------------
# Source item (for GET /faculty/sources)
# ---------------------------------------------------------------------------


class ScholarSourceItem(BaseModel):
    id: str
    name: str
    group: str
    university: str
    department: str
    is_enabled: bool
    item_count: int
    last_crawl_at: str | None


class ScholarSourcesResponse(BaseModel):
    total: int
    items: list[ScholarSourceItem]


# ---------------------------------------------------------------------------
# Stats response (for GET /faculty/stats)
# ---------------------------------------------------------------------------


class ScholarStatsResponse(BaseModel):
    total: int = Field(description="总师资数")
    academicians: int = Field(description="院士数")
    potential_recruits: int = Field(description="潜在招募对象数")
    advisor_committee: int = Field(description="顾问委员会成员数")
    adjunct_supervisors: int = Field(description="兼职导师数")
    by_university: list[dict[str, Any]] = Field(
        description="按高校统计 [{university, count}]"
    )
    by_department: list[dict[str, Any]] = Field(
        description="按院系统计 [{university, department, count}]"
    )
    by_position: list[dict[str, Any]] = Field(
        description="按职称统计 [{position, count}]"
    )
    completeness_buckets: dict[str, int] = Field(
        description="完整度分布 {<30, 30-60, 60-80, >80}"
    )
    sources_count: int = Field(description="信源数量")


# ---------------------------------------------------------------------------
# Write request schemas
# ---------------------------------------------------------------------------


class InstituteRelationUpdate(BaseModel):
    """PATCH /scholars/{url_hash}/relation — all fields optional."""

    is_advisor_committee: bool | None = Field(default=None, description="顾问委员会成员")
    is_adjunct_supervisor: bool | None = Field(default=None, description="兼职导师")
    supervised_students: list[Any] | None = Field(default=None, description="指导学生列表（字符串或对象均可）")
    joint_research_projects: list[str] | None = Field(default=None, description="联合科研项目列表")
    joint_management_roles: list[Any] | None = Field(
        default=None, description="在两院联合管理职务列表（字符串或对象均可）"
    )
    academic_exchange_records: list[Any] | None = Field(
        default=None, description="学术交流活动记录列表（字符串或对象均可）"
    )
    is_potential_recruit: bool | None = Field(default=None, description="潜在招募对象")
    institute_relation_notes: str | None = Field(default=None, description="补充备注（自由文本）")
    relation_updated_by: str | None = Field(default=None, description="更新人")


class UserUpdateCreate(BaseModel):
    """POST /scholars/{url_hash}/updates — add a user-authored dynamic update."""

    update_type: str = Field(description="动态类型（任意字符串，如 general/major_project/award 等）")
    title: str = Field(description="标题/摘要")
    content: str = Field(default="", description="详细内容")
    source_url: str = Field(default="", description="来源链接（可选）")
    published_at: str = Field(default="", description="事件时间 YYYY-MM-DD 或 ISO8601（可选）")
    added_by: str = Field(description="录入人（用户名），系统自动补充为 'user:{added_by}'")


class AchievementUpdate(BaseModel):
    """PATCH /scholars/{url_hash}/achievements — update academic achievements."""

    representative_publications: list[dict[str, Any]] | None = Field(
        default=None, description="代表性论文列表（传入则完全替换，None 不修改）"
    )
    patents: list[dict[str, Any]] | None = Field(
        default=None, description="专利列表（传入则完全替换，None 不修改）"
    )
    awards: list[dict[str, Any]] | None = Field(
        default=None, description="获奖/荣誉列表（传入则完全替换，None 不修改）"
    )
    updated_by: str = Field(
        default="", description="操作人（用户名），系统自动补充为 'user:{updated_by}'"
    )


class ScholarBasicUpdate(BaseModel):
    """PATCH /scholars/{url_hash}/basic — update basic faculty information.

    All fields are optional. None means "do not modify" (not clear/empty).
    Pass empty list [] to clear a list field; pass non-empty list to replace entirely.
    Directly modifies the raw JSON file (data/raw/scholars/.../latest.json).
    """

    # 基本信息
    name: str | None = Field(default=None, description="中文姓名")
    name_en: str | None = Field(default=None, description="英文姓名")
    gender: str | None = Field(default=None, description="性别: 'male' | 'female' | ''")
    photo_url: str | None = Field(default=None, description="照片 URL")
    profile_url: str | None = Field(default=None, description="个人主页 URL")

    # 机构
    university: str | None = Field(default=None, description="所属大学")
    department: str | None = Field(default=None, description="所属院系")

    # 职称
    position: str | None = Field(default=None, description="职称")
    academic_titles: list[str] | None = Field(default=None, description="学术头衔列表")
    is_academician: bool | None = Field(default=None, description="是否院士")

    # 研究方向
    research_areas: list[str] | None = Field(default=None, description="研究方向列表")
    keywords: list[str] | None = Field(default=None, description="关键词列表")
    bio: str | None = Field(default=None, description="中文个人简介")
    bio_en: str | None = Field(default=None, description="英文个人简介")

    # 联系方式
    email: str | None = Field(default=None, description="邮箱地址")
    phone: str | None = Field(default=None, description="电话号码")
    office: str | None = Field(default=None, description="办公室地址")

    # 学术链接
    lab_url: str | None = Field(default=None, description="实验室/课题组主页 URL")
    google_scholar_url: str | None = Field(default=None, description="Google Scholar 主页")
    dblp_url: str | None = Field(default=None, description="DBLP 作者主页")
    orcid: str | None = Field(default=None, description="ORCID ID")

    # 教育经历
    phd_institution: str | None = Field(default=None, description="博士毕业院校")
    phd_year: str | None = Field(default=None, description="博士毕业年份")
    education: list[dict[str, Any]] | None = Field(default=None, description="完整教育经历列表")

    updated_by: str = Field(default="user", description="修改人标识（默认 'user'）")
