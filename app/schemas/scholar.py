"""ScholarRecord — unified schema for academic scholar/faculty data.

Field design principles:
- Missing data → "" (str) / [] (list) / -1 (int metric, -1 = unknown) — never null
- All field names use snake_case for direct database column mapping
- `extra` in CrawledItem stores model_dump() of this schema
- On DB migration: SELECT from scholars dimension's latest.json,
  extract extra field → insert into scholars table directly

Data source labels (in field docstrings):
  [爬虫]    Populated by ScholarCrawler automatically
  [富化]    Populated by LLM enrichment or external API (Google Scholar/DBLP)
  [用户]    Manually maintained by internal staff — never overwritten by crawler

Data completeness score (data_completeness: 0–100) measures CRAWL quality only,
not user-maintained fields.

Sections
--------
基本信息      name, name_en, gender, photo_url
机构归属      university, department, secondary_departments
职称荣誉      position, academic_titles, is_academician
研究方向      research_areas, keywords, bio, bio_en
联系方式      email, phone, office
主页链接      profile_url, lab_url, google_scholar_url, dblp_url, orcid
教育经历      phd_institution, phd_year, education
学术指标      publications_count, h_index, citations_count, metrics_updated_at
合作关系      is_advisor_committee, is_adjunct_supervisor, supervised_students,
              joint_research_projects, joint_management_roles,
              academic_exchange_records, is_potential_recruit,
              institute_relation_notes, relation_updated_by, relation_updated_at
动态更新      recent_updates (list[DynamicUpdate])
元信息        source_id, source_url, crawled_at, first_seen_at, last_seen_at,
              is_active, data_completeness
"""
from __future__ import annotations

import re as _re
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class EducationRecord(BaseModel):
    """Single education entry (degree, institution, year). [富化]"""

    degree: str = ""         # 学历: "博士" | "硕士" | "学士" | "博士后"
    institution: str = ""    # 毕业/研修院校
    year: str = ""           # 毕业年份（字符串支持 "2003–2007" 区间）
    major: str = ""          # 专业/研究方向


class PublicationRecord(BaseModel):
    """Single representative publication entry. [爬虫/用户]"""

    title: str = ""
    """论文标题"""

    venue: str = ""
    """期刊/会议名称，如 'NeurIPS 2024'"""

    year: str = ""
    """发表年份，如 '2024'"""

    authors: str = ""
    """作者列表（逗号分隔）"""

    url: str = ""
    """论文链接（DOI/arXiv/ACM 等）"""

    citation_count: int = -1
    """被引次数（-1 = 未知）"""

    is_corresponding: bool = False
    """是否通讯作者"""

    added_by: str = "crawler"
    """数据来源: 'crawler' | 'user:{username}'"""


class PatentRecord(BaseModel):
    """Single patent entry. [爬虫/用户]"""

    title: str = ""
    """专利名称"""

    patent_no: str = ""
    """专利号，如 'CN202310001234.X'"""

    year: str = ""
    """授权/申请年份"""

    inventors: str = ""
    """发明人列表（逗号分隔）"""

    patent_type: str = ""
    """专利类型: 'invention' | 'utility' | 'design' | ''"""

    status: str = ""
    """专利状态: 'granted' | 'pending' | ''"""

    added_by: str = "crawler"
    """数据来源: 'crawler' | 'user:{username}'"""


class AwardRecord(BaseModel):
    """Single award / honor entry. [爬虫/用户]"""

    title: str = ""
    """奖项名称，如 '国家科技进步二等奖'"""

    year: str = ""
    """获奖年份"""

    level: str = ""
    """级别: 'national' | 'provincial' | 'institutional' | 'international' | ''"""

    grantor: str = ""
    """颁奖机构/组织，如 '中华人民共和国国务院'"""

    description: str = ""
    """简要说明"""

    added_by: str = "crawler"
    """数据来源: 'crawler' | 'user:{username}'"""


class AdjunctSupervisorInfo(BaseModel):
    """兼职导师协议详情，替代原 is_adjunct_supervisor: bool。[用户 - 人力部]"""

    status: str = ""
    """协议状态: '已签署' | '流程中' | ''（空表示非兼职导师）"""

    type: str = ""
    """导师类型: '教学研究型' | '研究型' | '教学型' | ''"""

    agreement_type: str = ""
    """协议类型，如 '双方协议，知识产权共有' | '三方协议，知识产权独有'"""

    agreement_period: str = ""
    """协议有效期，如 '2025.3.1-2028.2.28'"""

    recommender: str = ""
    """推荐主体，如 '培养部' | '科研部'"""


class ScholarProjectTag(BaseModel):
    """学者所属项目分类标签。"""

    category: str = ""
    """一级分类，如 '教育培养'"""

    subcategory: str = ""
    """二级子分类，如 '学术委员会'"""

    project_id: str = ""
    """来源项目标签 ID（可选）"""

    project_title: str = ""
    """来源项目标签标题（可选）"""


class ScholarEventTag(BaseModel):
    """学者参与活动分类标签。"""

    category: str = ""
    """一级分类，如 '科研学术'"""

    series: str = ""
    """二级系列，如 'XAI智汇讲坛'"""

    event_type: str = ""
    """三级活动类型，如 '学术报告'"""

    event_id: str = ""
    """来源活动 ID（可选）"""

    event_title: str = ""
    """来源活动标题（可选）"""


class DynamicUpdate(BaseModel):
    """A single time-stamped dynamic event for a scholar.

    Sources:
    - Crawled automatically from the scholar's personal page, news sites, etc.
    - Manually added by internal staff (added_by starts with "user:")
    """

    update_type: str = ""
    """事件类型:
    'major_project'   重大项目立项（国家级/省部级重点项目）
    'talent_title'    人才称号（新获杰青/长江/优青/院士等称号）
    'position_change' 任职履新（新职位/晋升/退休/离职）
    'award'           获奖（科技奖/学术奖等具体奖项）
    'publication'     重要论文/著作发表
    'other'           其他重要动态
    """

    title: str = ""
    """更新标题/摘要，如 '获批国家自然科学基金重大项目'"""

    content: str = ""
    """详细内容描述"""

    source_url: str = ""
    """来源 URL（爬虫数据时填写）"""

    published_at: str = ""
    """事件发生/发布时间 ISO8601"""

    crawled_at: str = ""
    """爬取/录入时间 ISO8601（自动填写）"""

    added_by: str = "crawler"
    """数据来源: 'crawler' | 'user:{username}'（区分自动爬取与人工录入）"""


# ---------------------------------------------------------------------------
# Main schema
# ---------------------------------------------------------------------------


class ScholarRecord(BaseModel):
    """Unified schema for a university faculty / researcher record.

    Stored as CrawledItem.extra (model_dump()) by ScholarCrawler.
    Designed for forward-compatibility with a relational scholars table.

    Two sections require special handling:
    - 合作关系: user-editable fields ([用户]), never overwritten by crawler
    - 动态更新: primarily crawled but also user-addable via API
    """

    # ===== 基本信息 [爬虫] =====
    name: str = ""
    """中文姓名（必填，去重 title 字段）"""

    name_en: str = ""
    """英文姓名，如 'Ya-Qin Zhang' [富化]"""

    gender: str = ""
    """性别: 'male' | 'female' | ''（未知）[富化]"""

    photo_url: str = ""
    """照片绝对 URL [爬虫]"""

    # ===== 机构归属 [爬虫] =====
    university: str = ""
    """所属大学全称，如 '清华大学'"""

    department: str = ""
    """所属院系全称，如 '计算机科学与技术系'"""

    secondary_departments: list[str] = Field(default_factory=list)
    """兼职/双聘院系列表 [富化]，如 ['人工智能研究院', '交叉信息研究院']"""

    # ===== 职称荣誉 [爬虫/富化] =====
    position: str = ""
    """职称，如 '教授' | '副教授' | '助理教授' | '研究员' | '副研究员'"""

    academic_titles: list[str] = Field(default_factory=list)
    """学术头衔列表 [富化]，如 ['长江学者', '杰青', '优青', '国家特聘专家', '院士']"""

    is_academician: bool = False
    """是否为中科院/工程院院士 [富化]"""

    # ===== 研究方向 [爬虫/富化] =====
    research_areas: list[str] = Field(default_factory=list)
    """研究方向列表，如 ['机器学习', '计算机视觉', '自然语言处理']"""

    keywords: list[str] = Field(default_factory=list)
    """细粒度关键词，用于检索与标签 [富化]"""

    bio: str = ""
    """中文个人简介/研究简介（完整纯文本）[爬虫]"""

    bio_en: str = ""
    """英文个人简介 [富化]"""

    # ===== 联系方式 [爬虫] =====
    email: str = ""
    """主联系邮箱，如 'xxx@tsinghua.edu.cn'"""

    phone: str = ""
    """联系电话"""

    office: str = ""
    """办公室地址，如 '东主楼 10-103'"""

    # ===== 主页与链接 [爬虫/富化] =====
    profile_url: str = ""
    """个人主页 URL，作为 CrawledItem.url 的去重 key [爬虫]"""

    lab_url: str = ""
    """实验室/课题组主页 URL [爬虫]"""

    google_scholar_url: str = ""
    """Google Scholar 主页 URL [富化]"""

    dblp_url: str = ""
    """DBLP 作者主页 URL [富化]"""

    orcid: str = ""
    """ORCID ID，如 '0000-0001-2345-6789' [富化]"""

    # ===== 教育经历 [富化] =====
    phd_institution: str = ""
    """博士毕业院校（快速检索冗余字段）"""

    phd_year: str = ""
    """博士毕业年份，如 '2005'"""

    education: list[EducationRecord] = Field(default_factory=list)
    """完整教育经历（学士/硕士/博士/博后），由详情页解析或 LLM 富化填充"""

    # ===== 学术指标 [富化，-1 表示未获取] =====
    publications_count: int = -1
    """发表论文总数（来源: Google Scholar / DBLP）"""

    h_index: int = -1
    """H 指数"""

    citations_count: int = -1
    """总被引次数"""

    metrics_updated_at: str = ""
    """学术指标最后更新时间 ISO8601"""

    # ===== 学术成就 [爬虫/用户] =====
    representative_publications: list[PublicationRecord] = Field(default_factory=list)
    """代表性论文列表（来源：个人主页/Google Scholar，或用户录入）"""

    patents: list[PatentRecord] = Field(default_factory=list)
    """专利列表（来源：个人主页/专利库，或用户录入）"""

    awards: list[AwardRecord] = Field(default_factory=list)
    """获奖/荣誉列表（来源：个人主页，或用户录入）"""

    # ===== 合作关系 [用户] =====
    # 所有字段由用户手动维护，爬虫绝不覆盖这些字段
    # -------------------------------------------------------------------------
    is_advisor_committee: bool = False
    """顾问委员（顾问委员会成员）[用户 - 综办/培养部/科研部]"""

    adjunct_supervisor: AdjunctSupervisorInfo = Field(default_factory=AdjunctSupervisorInfo)
    """兼职导师协议详情（空 status 表示非兼职导师）[用户 - 人力部]"""

    supervised_students: list[str] = Field(default_factory=list)
    """指导学生列表（学生姓名或 ID）[用户 - 培养部]"""

    joint_research_projects: list[str] = Field(default_factory=list)
    """联合承担的科研项目名称列表 [用户]"""

    joint_management_roles: list[str] = Field(default_factory=list)
    """担任的联合管理职务，如 '教学委员会委员' [用户]"""

    academic_exchange_records: list[str] = Field(default_factory=list)
    """学术交流活动记录（XAI 讲坛/联合研讨会/专题报告等）[用户 - 活动数据]"""

    participated_event_ids: list[str] = Field(default_factory=list)
    """参与活动 ID 列表（由活动关联自动维护）"""

    event_tags: list[ScholarEventTag] = Field(default_factory=list)
    """参与活动分类标签（创建/编辑时可配置）"""

    project_tags: list[ScholarProjectTag] = Field(default_factory=list)
    """所属项目分类标签（由项目关联自动维护）"""

    is_cobuild_scholar: bool = False
    """是否共建学者（project_tags 非空即为 True）"""

    is_potential_recruit: bool = False
    """潜在引进对象（通过学术顶会/青年论坛等活动识别）[用户 - 活动数据]"""

    institute_relation_notes: str = ""
    """合作关系补充备注（自由文本）[用户]"""

    relation_updated_by: str = ""
    """合作关系数据最后更新人（内部用户名/姓名）[用户]"""

    relation_updated_at: str = ""
    """合作关系数据最后更新时间 ISO8601 [用户]"""

    # ===== 动态更新 [爬虫+用户] =====
    # 爬虫自动追加，内部人员也可通过 API 手动录入
    # 追加式写入，不覆盖历史记录
    # -------------------------------------------------------------------------
    recent_updates: list[DynamicUpdate] = Field(default_factory=list)
    """近期动态更新列表（重大项目立项/人才称号/任职履新/获奖/论文等）"""

    # ===== 元信息 [爬虫] =====
    source_id: str = ""
    """来源信源 ID，如 'tsinghua_cs_faculty'"""

    source_url: str = ""
    """爬取来源列表页 URL"""

    crawled_at: str = ""
    """本次爬取时间 ISO8601"""

    first_seen_at: str = ""
    """首次发现时间 ISO8601（首次爬到时写入，后续不覆盖）"""

    last_seen_at: str = ""
    """最后一次在目标页面确认在职的时间 ISO8601"""

    is_active: bool = True
    """是否在职（True = 本次爬取中存在；False = 历史存在但当前未见）"""

    data_completeness: int = 0
    """爬虫数据完整度 0–100（仅评估可爬取字段，不含用户维护字段）"""

    # ===== 用户修改审计 [用户] =====
    _user_modified_at: str | None = None
    """用户手动修改基础信息的最后时间 ISO8601（无则 None）"""

    _user_modified_by: str | None = None
    """用户手动修改的记录人（username 或备注）"""


# ---------------------------------------------------------------------------
# Helper: compute data completeness score (crawled fields only)
# ---------------------------------------------------------------------------

_COMPLETENESS_WEIGHTS: list[tuple[str, int]] = [
    ("name", 20),
    ("bio", 15),
    ("research_areas", 15),
    ("position", 10),
    ("email", 10),
    ("_real_profile", 10),  # profile_url without a synthetic #hash fragment
    ("photo_url", 5),
    ("phd_institution", 5),
    ("_ext_link", 5),       # lab_url or google_scholar_url
    ("keywords", 5),
]


def compute_scholar_completeness(r: ScholarRecord) -> int:
    """Return crawl data completeness score 0–100 for a ScholarRecord.

    Only evaluates automatically-populated fields ([爬虫] / [富化]).
    User-maintained relationship fields are intentionally excluded.

    Typical scores:
    - List-page only (name + photo): ~25
    - With bio + position:           ~50–60
    - With email + research_areas:   ~70–80
    - Fully enriched:                100
    """
    score = 0
    for key, weight in _COMPLETENESS_WEIGHTS:
        if key == "_real_profile":
            if r.profile_url and "#" not in r.profile_url:
                score += weight
        elif key == "_ext_link":
            if r.lab_url or r.google_scholar_url:
                score += weight
        else:
            val = getattr(r, key, None)
            if val:
                score += weight
    return min(score, 100)


# ---------------------------------------------------------------------------
# Helper: parse research areas string → list
# ---------------------------------------------------------------------------

_RA_SPLITTER = _re.compile(r"[；;、，,/\\|\n\r]+")


def parse_research_areas(raw: str) -> list[str]:
    """Split a raw research areas string into a deduplicated list.

    Handles common Chinese and ASCII delimiters.
    Example: '机器学习；计算机视觉、NLP' → ['机器学习', '计算机视觉', 'NLP']
    """
    if not raw:
        return []
    parts = _RA_SPLITTER.split(raw)
    seen: set[str] = set()
    result: list[str] = []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            result.append(p)
    return result


# ---------------------------------------------------------------------------
# Helper: validate research areas — detect and remove navigation menu pollution
# ---------------------------------------------------------------------------

# Navigation/UI keywords that indicate the list is a nav menu, not research areas
_NAV_KEYWORDS: frozenset[str] = frozenset([
    "首页", "关于我们", "联系我们", "中心简介", "行政团队", "访问指南",
    "数学学人", "人才培养", "学术活动", "科学研究", "招募英才",
    "院系简介", "历史沿革", "组织机构", "行政管理", "基金会", "研究人员",
    "新闻中心", "通知公告", "学术动态", "返回首页", "网站地图",
    "English", "搜索", "登录", "注册",
])

# Footer/copyright keywords that indicate page footer content
_FOOTER_KEYWORDS: tuple[str, ...] = (
    "CopyRight", "版权所有", "All Rights Reserved",
    "备案号", "ICP备", "京ICP",
)

# Address/contact patterns (compiled regex)
_ADDRESS_PATTERN = _re.compile(
    r"邮政编码|邮编[：:]\s*\d{6}|通信地址[：:]|Copyright\s*©|"
    r"版权所有\s*©",
    _re.IGNORECASE,
)

# Work experience pattern: year range like "2018年10月 — 今" or "2010-2020"
_WORK_EXP_PATTERN = _re.compile(
    r"\d{4}\s*年?\s*\d{0,2}\s*月?\s*[—\-–~至]\s*(?:今|至今|现在|\d{4})"
)

_MAX_RESEARCH_AREAS = 15
_MIN_AVG_CHARS = 3
_MAX_SINGLE_ITEM_LEN = 100


def validate_research_areas(areas: list[str]) -> list[str]:
    """Validate research areas list for navigation menu pollution.

    Returns the original list if it looks valid, or [] if it appears
    to be a navigation menu accidentally captured as research areas.

    Pollution detection rules (any one triggers rejection):
    1. Count > 15
    2. Any item matches a known navigation keyword
    3. Average item length < 3 chars
    4. Any item contains footer/copyright keywords
    5. Any item matches address/contact patterns
    6. Any single item > 100 chars (likely garbage, not a research area)
    7. >50% of items match work experience year-range patterns
    """
    if not areas:
        return areas

    # Rule 1: too many items
    if len(areas) > _MAX_RESEARCH_AREAS:
        return []

    # Rule 2: nav keyword present
    for item in areas:
        if item in _NAV_KEYWORDS:
            return []

    # Rule 3: average char length too short
    avg_len = sum(len(a) for a in areas) / len(areas)
    if avg_len < _MIN_AVG_CHARS:
        return []

    # Rule 4: footer/copyright keyword in any item
    for item in areas:
        for kw in _FOOTER_KEYWORDS:
            if kw.lower() in item.lower():
                return []

    # Rule 5: address/contact pattern in any item
    for item in areas:
        if _ADDRESS_PATTERN.search(item):
            return []

    # Rule 6: single item too long — a real research area is rarely >100 chars
    for item in areas:
        if len(item) > _MAX_SINGLE_ITEM_LEN:
            return []

    # Rule 7: work experience pattern (year-range like "2018年—今")
    # Any item matching is a strong signal of contamination
    for item in areas:
        if _WORK_EXP_PATTERN.search(item):
            return []

    return areas


# ---------------------------------------------------------------------------
# Helper: validate scholar name — filter out navigation/menu items
# ---------------------------------------------------------------------------

# Blacklist of common non-person-name strings captured from nav/menu/footer
_NAME_BLACKLIST: frozenset[str] = frozenset(
    _NAV_KEYWORDS | {
        # Portal/mail links
        "北大邮箱", "深研院邮箱", "校友", "网上办公", "南燕门户", "捐赠",
        # Website section names
        "本院概况", "学院导航", "招生培养", "师资队伍", "走进南燕",
        "人才招聘", "信息公开", "数据统计", "校历",
        # Generic college/department/university names mistaken as people
        "信息工程学院", "化学生物学与生物技术学院", "环境与能源学院",
        "城市规划与设计学院", "新材料学院", "汇丰商学院", "国际法学院",
        "人文社会科学学院", "化学与环境工程学院", "生命科学学院",
        "计算机学院", "电子工程学院", "机械工程学院",
        "北京大学", "清华大学", "复旦大学", "上海交通大学",
        "浙江大学", "南京大学", "中国科学技术大学", "中国人民大学",
    }
)

# Pattern for non-name strings
_NON_NAME_PATTERN = _re.compile(
    r"^https?://|"           # URL
    r"^www\.|"               # URL without scheme
    r"@|"                    # Email
    r"[©®™]|"               # Copyright/trademark symbols
    r"\d{5,}|"              # 5+ consecutive digits (phone/postal)
    r"[（(]\d{3,}[)）]",     # Area code pattern
    _re.IGNORECASE,
)


def validate_scholar_name(name: str) -> bool:
    """Return True if *name* looks like a real person's name.

    Rejects known navigation keywords, blacklisted website section names,
    strings with URL/email/copyright patterns, and length outliers.
    """
    if not name or not name.strip():
        return False

    name = name.strip()

    # Rule 1: blacklist exact match
    if name in _NAME_BLACKLIST:
        return False

    # Rule 2: length constraints
    if len(name) < 2:
        return False
    has_cjk = any("\u4e00" <= c <= "\u9fff" for c in name)
    if has_cjk and len(name) > 20:
        return False
    if len(name) > 60:
        return False

    # Rule 3: non-name patterns (URL, email, copyright, digits)
    if _NON_NAME_PATTERN.search(name):
        return False

    return True


# ---------------------------------------------------------------------------
# API Response Schemas
# ---------------------------------------------------------------------------


class ScholarListItem(BaseModel):
    """Single scholar item in list response."""

    url_hash: str = ""
    name: str = ""
    name_en: str = ""
    photo_url: str = ""
    university: str = ""
    department: str = ""
    position: str = ""
    academic_titles: list[str] = Field(default_factory=list)
    is_academician: bool = False
    research_areas: list[str] = Field(default_factory=list)
    email: str = ""
    profile_url: str = ""
    is_potential_recruit: bool = False
    is_advisor_committee: bool = False
    adjunct_supervisor: AdjunctSupervisorInfo = Field(default_factory=AdjunctSupervisorInfo)
    is_cobuild_scholar: bool = False
    project_tags: list[ScholarProjectTag] = Field(default_factory=list)
    participated_event_ids: list[str] = Field(default_factory=list)
    event_tags: list[ScholarEventTag] = Field(default_factory=list)


class ScholarListResponse(BaseModel):
    """Paginated list of scholars."""

    total: int
    page: int
    page_size: int
    total_pages: int
    items: list[ScholarListItem] = Field(default_factory=list)


class ScholarDetailResponse(BaseModel):
    """Full scholar detail with all fields."""

    url_hash: str = ""
    url: str = ""
    content: str = ""
    name: str = ""
    name_en: str = ""
    gender: str = ""
    photo_url: str = ""
    university: str = ""
    department: str = ""
    secondary_departments: list[str] = Field(default_factory=list)
    position: str = ""
    academic_titles: list[str] = Field(default_factory=list)
    is_academician: bool = False
    research_areas: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    bio: str = ""
    bio_en: str = ""
    email: str = ""
    phone: str = ""
    office: str = ""
    profile_url: str = ""
    lab_url: str = ""
    google_scholar_url: str = ""
    dblp_url: str = ""
    orcid: str = ""
    phd_institution: str = ""
    phd_year: str = ""
    education: list[EducationRecord] = Field(default_factory=list)
    publications_count: int = -1
    h_index: int = -1
    citations_count: int = -1
    metrics_updated_at: str = ""
    representative_publications: list[PublicationRecord] = Field(default_factory=list)
    patents: list[PatentRecord] = Field(default_factory=list)
    awards: list[AwardRecord] = Field(default_factory=list)
    is_advisor_committee: bool = False
    adjunct_supervisor: AdjunctSupervisorInfo = Field(default_factory=AdjunctSupervisorInfo)
    supervised_students: list[str] = Field(default_factory=list)
    joint_research_projects: list[str] = Field(default_factory=list)
    joint_management_roles: list[str] = Field(default_factory=list)
    academic_exchange_records: list[str] = Field(default_factory=list)
    participated_event_ids: list[str] = Field(default_factory=list)
    event_tags: list[ScholarEventTag] = Field(default_factory=list)
    project_tags: list[ScholarProjectTag] = Field(default_factory=list)
    is_cobuild_scholar: bool = False
    is_potential_recruit: bool = False
    institute_relation_notes: str = ""
    relation_updated_by: str = ""
    relation_updated_at: str = ""
    recent_updates: list[DynamicUpdate] = Field(default_factory=list)
    supervised_students_count: int = 0
    custom_fields: dict[str, Any] = Field(default_factory=dict, description="用户自定义字段")


class UniversityCount(BaseModel):
    """University count in stats."""

    university: str
    count: int


class DepartmentCount(BaseModel):
    """Department count in stats."""

    university: str
    department: str
    count: int


class PositionCount(BaseModel):
    """Position count in stats."""

    position: str
    count: int


class ScholarStatsResponse(BaseModel):
    """Scholar statistics response."""

    total: int
    academicians: int
    potential_recruits: int
    advisor_committee: int
    adjunct_supervisors: int
    by_university: list[UniversityCount] = Field(default_factory=list)
    by_department: list[DepartmentCount] = Field(default_factory=list)
    by_position: list[PositionCount] = Field(default_factory=list)


class ScholarSourceItem(BaseModel):
    """Single source in sources list."""

    id: str
    name: str
    group: str = ""
    university: str = ""
    department: str = ""
    is_enabled: bool
    item_count: int
    last_crawl_at: str | None = None


class ScholarSourcesResponse(BaseModel):
    """Scholar sources list response."""

    total: int
    items: list[ScholarSourceItem] = Field(default_factory=list)


class ScholarBasicUpdate(BaseModel):
    """Request body for updating basic scholar information."""

    name: str | None = None
    name_en: str | None = None
    gender: str | None = None
    photo_url: str | None = None
    university: str | None = None
    department: str | None = None
    position: str | None = None
    academic_titles: list[str] | None = None
    research_areas: list[str] | None = None
    keywords: list[str] | None = None
    bio: str | None = None
    bio_en: str | None = None
    email: str | None = None
    phone: str | None = None
    office: str | None = None
    profile_url: str | None = None
    lab_url: str | None = None
    google_scholar_url: str | None = None
    dblp_url: str | None = None
    orcid: str | None = None
    phd_institution: str | None = None
    phd_year: str | None = None
    education: list[EducationRecord] | None = None
    secondary_departments: list[str] | None = None
    updated_by: str | None = None
    custom_fields: dict[str, str | None] | None = Field(
        default=None, description="用户自定义字段（浅合并：值为 null 删除该 key）",
    )


class InstituteRelationUpdate(BaseModel):
    """Request body for updating institute relation fields."""

    is_advisor_committee: bool | None = None
    adjunct_supervisor: AdjunctSupervisorInfo | None = None
    supervised_students: list[str] | None = None
    joint_research_projects: list[str] | None = None
    joint_management_roles: list[str] | None = None
    academic_exchange_records: list[str] | None = None
    participated_event_ids: list[str] | None = None
    event_tags: list[ScholarEventTag] | None = None
    project_tags: list[ScholarProjectTag] | None = None
    is_cobuild_scholar: bool | None = None
    is_potential_recruit: bool | None = None
    institute_relation_notes: str | None = None
    relation_updated_by: str | None = None


class UserUpdateCreate(BaseModel):
    """Request body for creating a user-authored dynamic update."""

    update_type: str
    title: str
    content: str = ""
    source_url: str = ""
    published_at: str = ""
    added_by: str = "user"


class AchievementUpdate(BaseModel):
    """Request body for updating academic achievements."""

    representative_publications: list[PublicationRecord] | None = None
    patents: list[PatentRecord] | None = None
    awards: list[AwardRecord] | None = None
    h_index: int | None = None
    citations_count: int | None = None
    publications_count: int | None = None


# ---------------------------------------------------------------------------
# Scholar creation schemas
# ---------------------------------------------------------------------------


class ScholarCreateRequest(BaseModel):
    """Request body for manually creating a new scholar record.

    Only `name` is required. All other fields are optional — pass only what
    you have; missing fields default to the same empty values used by the
    crawler ('' / [] / -1).
    """

    # 基本信息
    name: str = Field(..., min_length=1, description="姓名（必填）")
    name_en: str = ""
    gender: str = ""
    photo_url: str = ""

    # 机构归属
    university: str = ""
    department: str = ""
    secondary_departments: list[str] = Field(default_factory=list)

    # 职称荣誉
    position: str = ""
    academic_titles: list[str] = Field(default_factory=list)
    is_academician: bool = False

    # 研究方向
    research_areas: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    bio: str = ""
    bio_en: str = ""

    # 联系方式
    email: str = ""
    phone: str = ""
    office: str = ""

    # 主页与链接
    profile_url: str = ""
    lab_url: str = ""
    google_scholar_url: str = ""
    dblp_url: str = ""
    orcid: str = ""

    # 教育经历
    phd_institution: str = ""
    phd_year: str = ""
    education: list[EducationRecord] = Field(default_factory=list)

    # 标签关系
    participated_event_ids: list[str] = Field(default_factory=list)
    event_tags: list[ScholarEventTag] = Field(default_factory=list)
    project_tags: list[ScholarProjectTag] = Field(default_factory=list)
    is_cobuild_scholar: bool = False

    # 审计字段
    added_by: str = Field(default="user", description="操作人，用于审计")


class ScholarImportResultItem(BaseModel):
    """Single row result from Excel import."""

    row: int = Field(..., description="Excel 行号（从 1 开始，不含表头）")
    status: str = Field(..., description="'success' | 'skipped' | 'failed'")
    name: str = ""
    url_hash: str = Field(default="", description="成功/跳过时的 url_hash")
    reason: str = Field(default="", description="跳过或失败的原因")


class ScholarImportResult(BaseModel):
    """Summary result of an Excel bulk import."""

    total: int = Field(..., description="总行数（不含表头）")
    success: int = 0
    skipped: int = Field(default=0, description="重复跳过数")
    failed: int = 0
    items: list[ScholarImportResultItem] = Field(default_factory=list)
