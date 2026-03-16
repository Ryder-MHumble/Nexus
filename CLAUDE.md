# Information Crawler — AI 开发上下文

中关村人工智能研究院**数据智能平台**（OpenClaw）。181 信源（138 启用）× 9 个信息维度 + 学者知识库维度（49 源），6 种模板爬虫 + 16 个自定义 Parser，v1 API **65+ 端点**（核心 14 + 业务智能 27 + 学者 14 + 项目/机构/活动/舆情/LLM追踪）。
82 个启用信源已配置 detail_selectors 或 RSS/API 自带正文，可自动获取文章正文（content 字段）。
技术栈：FastAPI + Supabase (PostgreSQL) + APScheduler 3.x + httpx + BS4 + Playwright。

**数据存储**：完全迁移到 Supabase 云数据库（2026-03-11），所有数据（文章、信源状态、爬取日志、舆情、学者等）均存储在数据库中，不再使用本地 JSON 文件。

**消费端生态**：向 4 个院内应用提供统一数据服务

| 消费端 | 服务对象 | 主要接入 API |
|--------|---------|------------|
| Dean-Agent 院长智能体 | 院长办、院领导 | `/intel/policy` `/intel/personnel` `/intel/daily-briefing` `/intel/tech-frontier` |
| ScholarDB-System 学者知识库 | 科研管理办 | `/scholars` `/institutions` `/projects` `/events` `/aminer` |
| Athena 战略情报引擎 | 战略发展部 | `/articles` `/intel/*` `/sentiment` |
| NanoBot 钉钉智能助理 | 全院各部门 | 全量 API（MCP 协议封装） |

## 部署环境

| 服务 | 地址 | 说明 |
|------|------|------|
| 后端 API | http://43.98.254.243:8001/ | FastAPI，API 文档：http://43.98.254.243:8001/docs |
| ScholarDB-System 前端 | http://43.98.254.243:8080/ | Next.js (学者知识库系统) |
| Dean-Agent 前端 | (另一个端口) | Next.js (院长智能体) |

服务器项目路径：

- 后端：`/home/ecs-user/Dean-Agent-Project/DeanAgent-Backend`
- ScholarDB-System 前端：`/home/ecs-user/Dean-Agent-Project/Dean-Agent-Fronted` (实际是 ScholarDB-System)
- Dean-Agent 前端：本地 `/Users/sunminghao/Desktop/Dean-Agent`

## 前端项目说明

**重要**：当前主要前端系统是 **ScholarDB-System（学者知识库系统）**，不是 Dean-Agent。

- **ScholarDB-System**：学者知识库前端，位于服务器 `/home/ecs-user/Dean-Agent-Project/Dean-Agent-Fronted`（路径名有误导性），使用 Next.js + TypeScript
  - 主要功能：机构页（Institution）、学者页（Scholar）、项目页（Program）、活动页（Event）、社群页（Community）
  - 访问地址：http://43.98.254.243:8080/
  - 使用的 API：`/api/v1/institutions`, `/api/v1/scholars`, `/api/v1/projects`, `/api/v1/events`

- **Dean-Agent**：院长智能体前端，位于本地 `/Users/sunminghao/Desktop/Dean-Agent`
  - 主要功能：政策情报、人事情报、科技前沿、每日简报
  - 使用的 API：`/api/v1/intel/*`

**当用户提到「前端」或「Scholar System」时，指的是 ScholarDB-System 学者知识库系统。**

## ⚠ API 端点清理（2026-03-15）

**已删除的冗余端点**：

为了简化 API 结构和避免前端调用错误，已删除以下冗余端点：

1. **`GET /api/v1/scholars/universities`** ❌ 已删除
   - 原功能：返回学者库中所有高校及其院系列表
   - 替代方案：`GET /api/v1/institutions?view=hierarchy&entity_type=organization`

2. **`GET /api/v1/institutions/scholars/`** ❌ 已删除
   - 原功能：获取所有高校及其院系，包含学者数量统计
   - 替代方案：`GET /api/v1/institutions?view=flat` 或 `?view=hierarchy`

3. **`GET /api/v1/institutions/scholars/stats`** ❌ 已删除
   - 原功能：返回高校、院系、学者的总体统计信息
   - 替代方案：`GET /api/v1/institutions/stats`

4. **`GET /api/v1/institutions/scholars/tree`** ❌ 已删除
   - 原功能：返回按 group → category → institution 三层分类的机构树
   - 替代方案：`GET /api/v1/institutions/taxonomy` 或 `/taxonomy/v2`

**统一使用 `/api/v1/institutions` 接口**：

- **扁平列表视图**：`GET /api/v1/institutions?view=flat&entity_type=organization&region=国内&org_type=高校`
- **层级结构视图**：`GET /api/v1/institutions?view=hierarchy&region=国内&org_type=高校&classification=共建高校`
- **分类体系统计**：`GET /api/v1/institutions/taxonomy` 或 `/taxonomy/v2`（含 sub_classification）
- **机构统计**：`GET /api/v1/institutions/stats`

**前端迁移指南**：

如果前端代码中使用了旧端点，请按以下方式迁移：

```typescript
// 旧代码（已失效）
const response = await fetch(`${API_BASE}/api/v1/scholars/universities?region=国内`);

// 新代码（推荐）
const response = await fetch(`${API_BASE}/api/v1/institutions?view=hierarchy&region=国内&entity_type=organization`);
```

## ⚠ 每次修改后必须做的事

**代码改完 → 验证通过 → 更新文档。三步缺一不可。**

### 必须更新的文档

每次修改爬虫代码、YAML 配置、或整体功能后，**必须同步更新以下文档**：

| 改了什么 | 必须更新 | 更新什么 |
|---------|---------|---------|
| 某个信源的 YAML（选择器/URL/启用状态） | `docs/CrawlStatus.md` | 该信源所在维度的状态表（条目数、启用状态、说明） |
| 新增/删除信源 | `docs/CrawlStatus.md` + `docs/TODO.md` | 总览表的源数统计、分组表、对应维度详情；TODO 中对应条目标记完成 |
| 新增维度 | `docs/CrawlStatus.md` + `docs/TODO.md` + `app/services/dimension_service.py` | 总览表新增行、新建维度详情章节、DIMENSION_NAMES 新增 |
| 爬虫模板改动 | `docs/CrawlStatus.md` | 如影响信源状态则更新对应维度表 |
| 修复禁用源 | `docs/CrawlStatus.md` + `docs/TODO.md` | 禁用源表删除该行、状态表更新为启用、TODO 对应条目打勾 |
| API 端点增删 | `docs/TODO.md` | 更新 API 相关待办状态 |
| 任何功能完成 | `docs/TODO.md` | 对应条目标记 `[x]` 完成 |

### 文档更新格式

`docs/CrawlStatus.md` 顶部有「最后更新」行，每次修改都要更新日期：
```markdown
> 最后更新: 2026-XX-XX
```

`docs/TODO.md` 顶部同理：
```markdown
> 最后更新: 2026-XX-XX
```

---

## 问题定位索引

**某个信源爬不到数据 / 选择器失效：**
→ `sources/{dimension}.yaml` 找到该源的 `selectors` / `url` 配置
→ `python scripts/run_single_crawl.py --source <id>` 单独测试
→ 用 Playwright MCP `browser_snapshot` 分析真实 DOM 结构

**某种爬虫类型（static/dynamic/rss/snapshot）整体出问题：**
→ `app/crawlers/templates/{type}_crawler.py`
→ `app/crawlers/utils/selector_parser.py`（static/dynamic 共享的列表解析、日期提取、详情页解析）

**自定义 Parser（arxiv/github/twitter 等）出问题：**
→ `app/crawlers/parsers/{name}.py`
→ 路由映射在 `app/crawlers/registry.py` 的 `_CUSTOM_MAP`

**LLM Scholar Crawler 问题：**
→ `app/crawlers/parsers/llm_faculty.py`（基于 LLM 的自适应学者信息爬取器）
→ 检查 `.env` 中的 `OPENROUTER_API_KEY`（或其他 LLM provider 的 API key）
→ YAML 配置：`crawler_class: llm_faculty`, `llm_provider`, `llm_model`, `max_list_tokens`, `max_detail_tokens`
→ 成本追踪：日志中会输出 API 调用次数、token 使用量、预估成本
→ 推荐模型：`deepseek/deepseek-chat`（性价比最高，$0.27/M input, $1.10/M output）

**Playwright 页面加载失败 / 超时：**
→ `app/crawlers/templates/dynamic_crawler.py`（爬虫逻辑）
→ `app/crawlers/utils/playwright_pool.py`（浏览器池）
→ YAML 中检查 `wait_for` / `wait_timeout`

**文章重复 / 去重不对：**
→ `app/crawlers/utils/dedup.py`（normalize_url + hash 逻辑）
→ `app/crawlers/utils/json_storage.py`（JSON 级去重，对比 previous url_hashes）

**调度任务不执行 / 频率不对：**
→ `app/scheduler/manager.py`（任务注册 + 频率映射）
→ `app/scheduler/jobs.py`（单次执行逻辑）
→ `app/scheduler/pipeline.py`（9 阶段 Pipeline 编排）
→ YAML 中检查 `schedule` / `is_enabled`
→ `.env` 中检查 `PIPELINE_CRON_HOUR` / `PIPELINE_CRON_MINUTE`

**API 返回异常：**
→ `app/api/v1/{articles,sources,dimensions,health}.py`（核心端点）
→ `app/api/v1/intel/{policy,personnel,tech_frontier,university}.py`（业务智能端点）
→ `app/api/v1/sentiment.py`（舆情监控端点：feed/overview/content detail）
→ `app/services/{article,source,crawl,dimension}_service.py`（核心业务逻辑）
→ `app/services/intel/{policy,personnel,tech_frontier,university}/service.py`（业务智能逻辑）
→ `app/services/external/sentiment_service.py`（舆情服务，从主库 sentiment_* 表读取）
→ `app/services/intel/shared.py`（共享工具：parse_source_filter 信源筛选、keyword_score 等）
→ `app/schemas/`（请求/响应校验）

**舆情 API 数据异常：**
→ `app/api/v1/sentiment.py` + `app/services/external/sentiment_service.py`
→ 数据来源：主库（yrawbjcyfafqmswnazmv）的 `sentiment_contents` / `sentiment_comments` / `sentiment_creators` 三张表
→ 使用 `app/db/client.get_client()`（主库 AsyncClient），与其他模块共用同一连接
→ 字段命名与原始社媒库完全一致：`liked_count`、`collected_count`、`nickname`、`user_id` 等
→ 如需重新迁移数据：重建 `scripts/migrate/03_migrate_sentiment.py`（参考迁移架构：fetch_all → _clean_*_row → upsert_batches）

**信源过滤不生效：**
→ `app/services/intel/shared.py` 的 `parse_source_filter()` 和 `resolve_source_ids_by_names()`
→ 所有 feed 类 API 支持 4 个信源过滤参数：
  - `source_id`: 单个信源 ID（精确匹配）
  - `source_ids`: 多个信源 ID，逗号分隔（精确匹配）
  - `source_name`: 单个信源名称（模糊匹配，子串、大小写不敏感、忽略空格）
  - `source_names`: 多个信源名称，逗号分隔（模糊匹配）
→ 支持的 API：policy/feed, personnel/feed, personnel/enriched-feed, university/feed, tech_frontier/signals, articles/
→ 测试：`pytest tests/test_source_filter.py -v`

**JSON 文件问题（已废弃）：**
→ 2026-03-11 已完全迁移到 Supabase 数据库，不再使用本地 JSON 文件
→ 所有数据（文章、信源状态、日志、学者、机构、项目、活动、Intel 处理结果）均存储在数据库
→ 爬虫仍会写入 JSON 到 `app/crawlers/utils/json_storage.py`，但仅作为临时缓存，最终数据存入 DB

**运行状态 / 爬取日志问题：**
→ `app/services/stores/source_state.py`（信源运行状态：Supabase `source_states` 表）
→ `app/services/stores/crawl_log_store.py`（爬取日志：Supabase `crawl_logs` 表）
→ `app/services/stores/snapshot_store.py`（快照数据：Supabase `snapshots` 表）

**HTTP 请求失败 / 限速 / UA 被封：**
→ `app/crawlers/utils/http_client.py`（重试、限速、UA 轮换）

## 数据库迁移验证

**通用验证工具**：`scripts/verify_db_migration.py`

用于验证数据库表结构变更后的数据完整性和一致性。

### 使用方法

```bash
# 基本用法：验证表是否存在
python scripts/verify_db_migration.py <table_name>

# 验证新字段是否添加成功
python scripts/verify_db_migration.py institutions --check-fields entity_type,region,org_type,classification,sub_classification

# 使用自定义一致性检查
python scripts/verify_db_migration.py institutions --check-fields entity_type --consistency-checks scripts/checks/institution_checks.py
```

### 验证内容

1. **新字段检查**：验证指定字段是否存在
2. **未迁移记录**：检查是否有字段值为 NULL 的记录
3. **数据分布统计**：统计各字段的值分布
4. **一致性检查**：运行自定义一致性检查函数
5. **查询测试**：测试基本查询是否正常

### 自定义一致性检查示例

```python
# scripts/checks/institution_checks.py
CONSISTENCY_CHECKS = {
    "organization 必须有 org_type": lambda row: (
        row.get("entity_type") != "organization" or row.get("org_type") is not None
    ),
    "department 不应有 org_type": lambda row: (
        row.get("entity_type") != "department" or row.get("org_type") is None
    ),
}
```

## 数据存储结构

**完全迁移到 Supabase 数据库（2026-03-11）**

所有数据存储在 Supabase PostgreSQL 数据库中，不再使用本地 JSON 文件：

### 主要数据表

| 表名 | 主键 | 说明 | 记录数 |
|-----|------|------|--------|
| articles | url_hash (SHA-256) | 文章数据（所有维度） | 2220+ |
| source_states | source_id | 信源运行状态 | 99 |
| crawl_logs | id (自增) | 爬取执行日志 | 439+ |
| snapshots | source_id | 页面快照数据 | 按需 |
| sentiment_contents | id (自增) | 舆情内容 | 327 |
| sentiment_comments | id (自增) | 舆情评论 | 9731 |
| sentiment_creators | id (自增) | 舆情创作者 | 98 |
| scholars | id | 学者数据 | 2686 |
| institutions | id | 机构数据（高校+院系） | 按需 |
| projects | id | 项目数据 | 按需 |
| events | id | 学术活动数据 | 按需 |
| intel_cache | module, filename | Intel 处理结果缓存 | 按需 |

### 本地文件（仅保留）

```
data/
├── state/
│   ├── article_annotations.json        # 文章标注（用户操作）
│   ├── scholar_annotations.json        # 学者标注（用户操作）
│   ├── faculty_annotations.json        # 教师标注（用户操作）
│   └── supervised_students.json        # 指导学生数据（用户操作）
├── institutions/                       # 机构相关静态文件
├── reports/                            # 报告文件
└── index.json                          # 前端索引（Pipeline 生成）
```

### 数据库连接

- **配置**：`.env` 中的 `SUPABASE_URL` 和 `SUPABASE_KEY`
- **客户端**：`app/db/client.py` 提供全局 AsyncClient
- **初始化**：`app/main.py` 启动时调用 `init_client()`
- **降级策略**：代码中保留 JSON 降级逻辑，但因文件不存在会自动失效

### 迁移历史

- **2026-03-10**：完成 articles、source_states、crawl_logs、snapshots、sentiment 迁移
- **2026-03-11**：删除所有本地 JSON 数据文件，完全依赖数据库（释放 28.32 MB 空间）

### 旧数据结构（已废弃）

以下路径已不再使用，仅作历史参考：

```
data/raw/{dimension}/{group?}/{source_id}/latest.json   # 已删除
data/scholars/scholars.json                              # 已删除
data/scholars/institutions.json                          # 已删除
data/scholars/projects.json                              # 已删除
data/scholars/events.json                                # 已删除
data/processed/policy_intel/                             # 已删除
data/processed/personnel_intel/                          # 已删除
data/processed/tech_frontier/                            # 已删除
data/processed/university_eco/                           # 已删除
data/processed/daily_briefing/                           # 已删除
data/state/source_state.json                             # 已删除
data/logs/{source_id}/crawl_logs.json                    # 已删除
```

## 文件路由规则

**配置驱动**：YAML `crawl_method` → 模板爬虫；`crawler_class` → 自定义 Parser（优先级更高）
```
crawl_method: static  → app/crawlers/templates/static_crawler.py
crawl_method: dynamic → app/crawlers/templates/dynamic_crawler.py
crawl_method: rss     → app/crawlers/templates/rss_crawler.py
crawl_method: snapshot→ app/crawlers/templates/snapshot_crawler.py
crawler_class: gov_json_api      → app/crawlers/parsers/gov_json_api.py
crawler_class: arxiv_api         → app/crawlers/parsers/arxiv_api.py
crawler_class: github_api        → app/crawlers/parsers/github_api.py
crawler_class: hacker_news_api   → app/crawlers/parsers/hacker_news_api.py
crawler_class: semantic_scholar  → app/crawlers/parsers/semantic_scholar.py
crawler_class: twitter_kol       → app/crawlers/parsers/twitter_kol.py
crawler_class: twitter_search    → app/crawlers/parsers/twitter_search.py
crawler_class: hunyuan_api      → app/crawlers/parsers/hunyuan_api.py
crawler_class: sjtu_cs_scholar    → app/crawlers/parsers/sjtu_cs_faculty.py
crawler_class: sjtu_ai_scholar    → app/crawlers/parsers/sjtu_ai_faculty.py
crawler_class: iscas_scholar      → app/crawlers/parsers/iscas_faculty.py
crawler_class: zju_cyber_scholar  → app/crawlers/parsers/zju_cyber_faculty.py
crawler_class: ymsc_scholar       → app/crawlers/parsers/ymsc_faculty.py
crawler_class: llm_faculty        → app/crawlers/parsers/llm_faculty.py (LLM 驱动的自适应爬虫，通用)
```

**维度 → YAML 文件**：
```
national_policy → sources/national_policy.yaml (8 源, 6 启用)
beijing_policy  → sources/beijing_policy.yaml  (14 源, 10 启用)
technology      → sources/technology.yaml      (34 源, 33 启用)
talent          → sources/talent.yaml          (7 源, 4 启用)
industry        → sources/industry.yaml        (10 源, 6 启用)
universities    → sources/universities.yaml    (55 源, 46 启用)
events          → sources/events.yaml          (6 源, 4 启用)
personnel       → sources/personnel.yaml       (4 源, 4 启用)
scholars       → sources/scholar-*.yaml (49 源，9 所高校，按需触发重爬)
                  ↳ scholar-tsinghua.yaml(13) · scholar-pku.yaml(9) · scholar-sjtu.yaml(5)
                  ↳ scholar-cas.yaml(5) · scholar-zju.yaml(3) · scholar-nju.yaml(5)
                  ↳ scholar-ustc.yaml(5) · scholar-fudan.yaml(2) · scholar-ruc.yaml(2)
twitter         → sources/twitter.yaml         (7 源, 7 启用, 需 API key)
                  ↳ 按 dimension 分配: technology 4源, industry 1源, talent 1源, sentiment 1源
```

**AMiner API 集成**：
```
GET /api/v1/aminer/organizations?name={机构名}     → 查询机构信息（本地 data/institution.json）
GET /api/v1/aminer/scholars/search?name=X&org=Y   → 搜索学者基础信息（AMiner API）
GET /api/v1/aminer/scholars/{aminer_id}           → 获取学者详细信息（AMiner API）

app/api/v1/aminer.py                    → AMiner API 路由（3 个查询端点）
app/services/aminer_client.py           → AMiner HTTP 客户端（调用外部 API）
app/services/institution_service.py     → 机构信息查询服务（search_institutions_for_aminer）
app/schemas/aminer.py                   → AMiner 响应 schemas
.env: AMINER_API_KEY                    → AMiner API 认证 token
```

**业务智能模块 (intel/)**：
```
app/api/v1/intel/router.py          → intel 子路由（聚合所有业务智能端点）
app/api/v1/intel/policy.py          → 政策智能 API (feed/opportunities/stats)
app/api/v1/intel/personnel.py       → 人事情报 API (feed/changes/stats/enriched-feed/enriched-stats)
app/api/v1/intel/tech_frontier.py   → 科技前沿 API (topics/opportunities/stats/signals)
app/api/v1/intel/university.py      → 高校生态 API (feed/overview/research-outputs)
app/api/v1/intel/daily_briefing.py  → 每日简报 API (today/latest/history)

app/services/intel/shared.py        → 共享工具（article_date, deduplicate_articles, clamp_value,
                                       keyword_score, extract_*, load_intel_json, parse_date_str）
app/services/intel/pipeline/base.py → Pipeline 共享基础（HashTracker 增量追踪 + save_output_json 统一输出）
app/services/intel/pipeline/policy_processor.py        → 政策处理管线
app/services/intel/pipeline/personnel_processor.py     → 人事处理管线
app/services/intel/pipeline/tech_frontier_processor.py → 科技前沿处理管线
app/services/intel/pipeline/university_eco_processor.py→ 高校生态处理管线
app/services/intel/pipeline/briefing_processor.py      → 每日简报处理管线

app/services/intel/policy/          → 政策智能 {rules, llm, service}
app/services/intel/personnel/       → 人事情报 {rules, llm, service}
app/services/intel/tech_frontier/   → 科技前沿 {rules, llm, service}
app/services/intel/university/      → 高校生态 {rules, service}
app/services/intel/daily_briefing/  → 每日简报 {rules, llm, service}

app/schemas/intel/policy.py         → 政策 Pydantic schemas
app/schemas/intel/personnel.py      → 人事 Pydantic schemas（含 PersonnelChangeEnriched）
app/schemas/intel/tech_frontier.py  → 科技前沿 Pydantic schemas（TechTopic/Opportunity/SignalItem）
app/schemas/intel/university.py     → 高校生态 Pydantic schemas
app/schemas/intel/daily_briefing.py → 每日简报 Pydantic schemas

scripts/process_policy_intel.py     → 政策数据处理脚本（两级管线）
scripts/process_personnel_intel.py  → 人事数据处理脚本（规则 + --enrich LLM）
scripts/process_tech_frontier.py    → 科技前沿处理脚本（规则 + --enrich LLM）
scripts/process_university_eco.py   → 高校生态处理脚本

data/processed/policy_intel/        → 政策处理输出 (feed.json, opportunities.json)
data/processed/personnel_intel/     → 人事处理输出 (feed.json, changes.json, enriched_feed.json)
data/processed/tech_frontier/       → 科技前沿输出 (topics.json, opportunities.json, stats.json)
data/processed/university_eco/      → 高校生态输出 (overview.json, feed.json, research_outputs.json)
data/processed/daily_briefing/      → 每日简报输出 (briefing.json)
```

新增业务智能模块时，在 `services/intel/` 下新建子包，在 `api/v1/intel/` 添加端点，在 `intel/router.py` 注册子路由。Pipeline 处理器继承 `pipeline/base.py` 的 HashTracker + save_output_json 共享工具。

**项目库模块 (projects)**：
```
GET  /api/v1/projects/              → 项目列表（分页 + 多维过滤）
GET  /api/v1/projects/stats         → 统计（按状态/类别/资助机构）
GET  /api/v1/projects/{id}          → 项目详情
POST /api/v1/projects/              → 创建项目（ID 自动生成）
PATCH /api/v1/projects/{id}         → 更新项目字段
DELETE /api/v1/projects/{id}        → 删除项目

app/api/v1/projects.py              → Projects API 路由
app/services/core/project_service.py → 项目库 CRUD 服务
app/schemas/project.py              → 项目库 Pydantic schemas
data/scholars/projects.json         → 项目数据本地 JSON 存储

字段说明：
  - 必填：name（项目名称）、pi_name（负责人）、status（状态）
  - 项目状态：申请中 | 在研 | 已结题 | 暂停 | 终止
  - 项目类别：国家级 | 省部级 | 横向课题 | 院内课题 | 国际合作 | 其他
  - 扩展字段：related_scholars（相关学者）、outputs（论文/专利等成果）、cooperation_institutions（合作机构）
  - 过滤参数：status, category, funder（模糊）, pi_name（模糊）, tag, keyword（全文）
```

## 内容过滤配置

**灵活的关键词过滤机制**，支持三种模式：

### 1. 无过滤模式（抓取所有内容）

```yaml
- id: "example_source"
  url: "https://example.com/news"
  crawl_method: "static"
  # 不设置 keyword_filter 和 keyword_blacklist
  # 将抓取所有文章
```

### 2. 白名单过滤（只抓取特定领域）

```yaml
- id: "ai_policy"
  url: "https://example.com/policy"
  crawl_method: "static"
  keyword_filter:
    - "人工智能"
    - "AI"
    - "机器学习"
    - "算法"
  # 只保留标题包含以上任一关键词的文章
```

**其他领域示例**：

- 医疗：`["医疗", "健康", "疫苗", "药品"]`
- 金融：`["金融", "银行", "支付", "区块链"]`
- 教育：`["教育", "在线学习", "MOOC", "智慧教育"]`

### 3. 黑名单过滤（排除不想要的内容）

```yaml
- id: "tech_news"
  url: "https://example.com/tech"
  crawl_method: "static"
  keyword_blacklist:
    - "广告"
    - "推广"
    - "招聘"
  # 排除标题包含以上任一关键词的文章
```

### 4. 组合过滤（白名单 + 黑名单）

```yaml
- id: "ai_research"
  url: "https://example.com/research"
  crawl_method: "static"
  keyword_filter: ["人工智能", "AI"]
  keyword_blacklist: ["招聘", "培训", "广告"]
  # 必须包含白名单关键词，且不包含黑名单关键词
```

### 过滤逻辑

```
1. 检查黑名单（优先级最高）→ 包含任一黑名单词 → 丢弃
2. 检查白名单（如果配置了）→ 不包含任一白名单词 → 丢弃
3. 通过所有检查 → 保留
```

### 自定义 Parser 集成

```python
from app.crawlers.utils.content_filter import should_keep_item

class MyCustomCrawler(BaseCrawler):
    async def fetch_and_parse(self) -> list[CrawledItem]:
        keyword_filter = self.config.get("keyword_filter")
        keyword_blacklist = self.config.get("keyword_blacklist")

        items = []
        for raw_item in self._fetch_raw_items():
            if not should_keep_item(raw_item.title, keyword_filter, keyword_blacklist):
                continue
            items.append(self._convert_to_crawled_item(raw_item))
        return items
```

## 常用工作流

### 修复某个信源的选择器
```
1. 读 sources/{dim}.yaml 找到该源配置
2. 用 Playwright MCP 打开该源 URL，snapshot 分析真实 DOM 结构
3. 修改 YAML 中 selectors
4. 验证：python scripts/run_single_crawl.py --source <id>
5. 确认输出有 items_new > 0
6. 更新 docs/CrawlStatus.md 中该源的状态行
```

### 添加新标准信源
```
1. 用 Playwright MCP 打开目标网站，snapshot 分析列表页结构
2. 确定 crawl_method（static 还是 dynamic）和 CSS 选择器
3. 编辑 sources/{dim}.yaml 添加条目
4. 验证：python scripts/run_single_crawl.py --source <new_id>
5. 检查 data/raw/{dim}/{group}/{id}/ 下是否生成 JSON
6. 更新 docs/CrawlStatus.md（总览表源数 + 该维度详情表新增行）
7. 更新 docs/TODO.md（如果是待办中的信源，标记完成）
```

### 添加自定义 Parser
```
1. 在 app/crawlers/parsers/ 新建 {name}.py（继承 BaseCrawler，实现 fetch_and_parse）
2. 在 app/crawlers/registry.py 的 _CUSTOM_MAP 中添加映射
3. 在 sources/*.yaml 中配置 crawler_class: "{name}"
4. 验证：python scripts/run_single_crawl.py --source <id>
5. 更新 docs/CrawlStatus.md + docs/TODO.md
```

### 使用 LLM Faculty Crawler（自适应学者信息爬取）
```
LLM Faculty Crawler 是基于 LLM 的自适应爬虫，无需手写 CSS 选择器，自动适配不同网站结构。

优势：
- 无需手写选择器，自动提取学者信息
- 自动适配不同网站结构（列表页 + 详情页）
- 使用便宜的国产模型（Deepseek V3），成本低至 $0.01-0.02/学者
- 数据完整度高（平均 70-80%）

配置步骤：
1. 在 .env 中配置 LLM API key：
   OPENROUTER_API_KEY=sk-or-v1-xxx  # 推荐使用 OpenRouter
   # 或者使用其他 provider：
   # SILICONFLOW_API_KEY=xxx
   # DASHSCOPE_API_KEY=xxx

2. 在 sources/*.yaml 中添加信源配置：
   - id: my_university_faculty
     name: XX大学XX学院-师资
     group: university_name
     university: XX大学
     department: XX学院
     url: https://example.edu.cn/faculty/list.htm
     crawler_class: llm_faculty           # 使用 LLM 爬虫
     llm_provider: openrouter             # openrouter | siliconflow | dashscope
     llm_model: deepseek/deepseek-chat    # 推荐 deepseek-chat（性价比最高）
     max_list_tokens: 4000                # 列表页最大输出 token
     max_detail_tokens: 8000              # 详情页最大输出 token
     schedule: weekly
     priority: 2
     is_enabled: true
     request_delay: 1.5                   # API 请求延迟（秒）
     tags:
     - faculty
     - university_name

3. 测试爬取：
   python scripts/run_single_crawl.py --source my_university_faculty

4. 查看成本统计：
   日志中会输出：
   - API 调用次数
   - 输入/输出 token 数量
   - 预估成本（美元）

成本对比（每个学者）：
- Claude 3.5 Sonnet: ~$0.10-0.15
- Deepseek V3: ~$0.01-0.02（便宜 10 倍）
- Qwen 2.5 72B: ~$0.015-0.025

推荐模型：
- deepseek/deepseek-chat（最便宜，$0.27/M input, $1.10/M output）
- qwen/qwen-2.5-72b-instruct（稍贵，$0.35/M input, $1.40/M output）

注意事项：
- 首次运行会较慢（需要提取所有学者详情）
- 后续运行会快很多（只提取新增学者）
- 建议 request_delay 设置为 1-2 秒，避免 API 限流
- 如果某个学者详情页提取失败，会自动跳过并记录日志
```

### 修改爬虫模板逻辑
```
1. 改 app/crawlers/templates/{type}_crawler.py
2. 验证：选 2-3 个使用该模板的源分别测试
   python scripts/run_single_crawl.py --source <id1>
   python scripts/run_single_crawl.py --source <id2>
3. ruff check app/crawlers/
4. 如影响信源状态则更新 docs/CrawlStatus.md 对应维度表
```

### 修改 API / 服务
```
1. 改 app/api/v1/ 或 app/services/
2. 验证：uvicorn app.main:app --reload 后用 curl 或 /docs 测试
3. ruff check app/
4. 更新 docs/TODO.md 对应条目
```

### 使用 Playwright MCP 辅助开发
分析网页结构时，优先用 Playwright MCP 工具：
- `browser_navigate` → 打开目标 URL
- `browser_snapshot` → 获取页面可访问性快照（比截图更适合分析 DOM）
- 根据 snapshot 结果确定 CSS 选择器，填入 YAML

## 关键设计决策

1. **APScheduler 3.x，不用 4.x** — 4.x 是 alpha，pip 安装不到稳定版
2. **URL 归一化保留 fragment** — snapshot_crawler 用 `#snapshot-{hash}` 区分同 URL 的不同快照
3. **纯 JSON 存储，无数据库** — 所有数据存本地 JSON 文件，轻量可维护
4. **信源配置读 YAML，运行状态存 JSON** — YAML 是静态配置源，`source_state.json` 存动态状态（last_crawl_at, failures, is_enabled_override）
5. **CrawlLog 记录 crawler 创建失败** — 即使实例化出错也可通过 API 追溯
6. **RSSHub 公共实例不可用** — rsshub.app 等全部 403，需自部署或用原生 feed
7. **JSON 级去重** — `json_storage.py` 通过对比 previous latest.json 的 url_hashes 标记 is_new
8. **static/dynamic 共享解析逻辑** — `selector_parser.py` 提取公共函数，消除两个模板间 ~100 行重复代码
9. **业务智能模块子包结构** — `services/intel/{domain}/` 每个维度一个子包（rules + service + llm），共享工具在 `shared.py`，避免 services/ 膨胀
10. **每日 Pipeline 10 阶段** — 爬取→政策处理→人事处理→高校生态→科技前沿→LLM 富化（条件：policy+personnel+tech_frontier）→机构图谱重建→索引生成→每日简报，Stage 4 由 `ENABLE_LLM_ENRICHMENT` + `OPENROUTER_API_KEY` 共同控制，Stage 4d 从 `scholars.json` 自动重建 `institutions.json`
11. **机构数据自动同步** — `institutions.json` 从 `scholars.json` 统计生成，每次 Pipeline 运行时自动更新，新增学者立即反映在机构图谱中，保留手动富化字段（category, priority, student_count）
12. **APScheduler 单 worker 限制** — 3.x 不支持多进程协调，`--workers 1` 是唯一安全配置
13. **首次启动自动触发 Pipeline** — `_check_needs_initial_data()` 检测空数据后异步触发，API 不阻塞
14. **文章 ID 使用 url_hash** — 64 字符 SHA-256 hex 字符串，替代原 DB 自增 ID

## 开发约定

- **Python 3.11+**，`X | Y` 联合类型
- **ruff** line-length=100，select E/F/I/W
- **async everywhere**：所有 HTTP、爬虫
- 新增标准信源：只改 `sources/*.yaml`
- 新增 API 信源：`parsers/` 加类 + `registry.py` 的 `_CUSTOM_MAP` 注册
- **git add 按文件名**，不用 `git add .`

## 项目文档索引

| 文档 | 路径 | 内容 |
|------|------|------|
| 任务优先级 | `docs/TODO.md` | P0-P3 分级待办，每次完成功能后更新 |
| 爬取状态 | `docs/CrawlStatus.md` | 各维度各源的爬取状态、数据量、禁用原因 |
| 信源全景 | `docs/SourceOverview.md` | 181 个信源全量清单，按维度/类型/状态分类 |
| 平台架构 | `docs/architecture.md` | 5 层平台架构、消费端接入、设计决策 |
| 产品生态 | `docs/files/产品生态架构全景.md` | 领导汇报用，平台定位 + 价值地图 + 演进方向 |
| 院长需求 | `docs/files/院长智能体.md` | 前端 Dean-Agent 功能需求 |

## 前端机构分类筛选对接

**问题**：前端左侧导航栏使用硬编码的分类规则（国内/国际 → 高校/企业/研究机构/其他），与数据库新的分类体系不一致。

**解决方案**：前端调用后端API获取动态分类结构，按照新的数据库字段（entity_type, region, org_type, classification, sub_classification）进行筛选。

### 后端API（已完成）

1. **GET /api/v1/institutions/taxonomy** - 获取分类体系（用于渲染导航栏）

   ```json
   {
     "total": 125,
     "regions": {
       "国内": {
         "count": 112,
         "org_types": {
           "高校": {"count": 87, "classifications": {"共建高校": {"count": 41}}},
           "企业": {"count": 8},
           "研究机构": {"count": 17}
         }
       },
       "国际": {"count": 13, "org_types": {...}}
     }
   }
   ```

2. **GET /api/v1/institutions?region=国内&org_type=高校&classification=共建高校** - 根据筛选条件获取机构列表

### 前端实现要点

1. **创建API客户端**：`lib/api/institutions.ts`
   - `fetchInstitutionTaxonomy()` - 获取分类体系
   - `fetchInstitutions(filters)` - 获取机构列表

2. **创建自定义Hook**：
   - `hooks/use-institution-taxonomy.ts` - 获取动态分类
   - `hooks/use-institutions.ts` - 获取机构列表

3. **修改学者知识图谱组件**：
   - 移除硬编码的分类数据
   - 使用 `useInstitutionTaxonomy()` 获取动态分类
   - 根据 taxonomy 数据渲染导航栏
   - 点击导航栏时调用 `fetchInstitutions()` 并传递筛选参数

### 测试验证

```bash
# 测试分类体系API
curl "http://43.98.254.243:8001/api/v1/institutions/taxonomy"

# 测试筛选API（注意：中文需要URL编码）
curl "http://43.98.254.243:8001/api/v1/institutions?region=%E5%9B%BD%E5%86%85&org_type=%E9%AB%98%E6%A0%A1&page_size=5"
```

前端测试：

1. 检查左侧导航栏是否动态渲染（显示实际的分类和数量）
2. 点击导航栏各个分类，检查是否正确调用API
3. 打开浏览器开发者工具Network面板，确认每次点击都有API请求

详细的前端实现代码示例见：`scripts/deploy_venues.sh`

## 常用命令

```bash
# 部署管理（根目录 deploy.sh，集成 venv/依赖/Playwright/服务管理）
./deploy.sh                                          # 智能部署（一键搞定所有事）
./deploy.sh init                                     # 仅初始化（不启动）
./deploy.sh start                                    # 启动服务
./deploy.sh stop                                     # 停止服务
./deploy.sh restart                                  # 重启服务
./deploy.sh status                                   # 查看详细状态
./deploy.sh logs -f                                  # 持续跟踪日志

# 开发调试
uvicorn app.main:app --reload                        # 前台启动（开发用）
python scripts/crawl/run_single.py --source <id>     # 测试单源
python scripts/crawl/run_all.py                      # 批量运行所有启用源
python scripts/process_policy_intel.py --dry-run     # 政策智能预览
python scripts/process_personnel_intel.py --dry-run  # 人事情报预览
python scripts/process_personnel_intel.py --enrich --force  # 人事 LLM 富化
python scripts/rebuild_institutions.py               # 手动重建 institutions.json（仅在添加新学者信源后使用）
python scripts/rebuild_institutions.py --dry-run     # 预览重建结果（不保存）
ruff check app/                                      # Lint
pytest                                               # 测试

# 领域过滤（2026-03-16 新增）
python scripts/crawl/run_single.py --source <id> --domain technology.ai          # 使用 AI 领域过滤
python scripts/crawl/run_single.py --source <id> --domain economy.finance        # 使用金融领域过滤
python scripts/crawl/run_single.py --source <id> --domain technology.ai,livelihood.education  # 多领域
python scripts/crawl/run_single.py --source <id> --domain-group tech_all         # 使用领域组合
python scripts/crawl/run_single.py --source <id> --domain all                    # 全领域不过滤
```

## 领域过滤系统（2026-03-16 新增）

**通用领域分类体系**，支持 6 大类 × 30+ 子领域，让爬虫框架适用于不同业务场景。

### 领域分类

| 一级领域 | 二级子领域示例 |
|---------|--------------|
| `technology` 科技 | `ai` 人工智能、`biotech` 生物科技、`quantum` 量子科技、`semiconductor` 半导体、`aerospace` 航空航天、`energy` 新能源 |
| `economy` 经济 | `finance` 金融、`industry` 产业、`trade` 贸易、`realestate` 房地产 |
| `livelihood` 民生 | `education` 教育、`healthcare` 医疗、`employment` 就业、`housing` 住房、`transportation` 交通 |
| `environment` 环境 | `pollution` 污染治理、`climate` 气候、`ecology` 生态 |
| `society` 社会 | `governance` 治理、`security` 安全、`law` 法律 |
| `culture` 文化 | `heritage` 文化遗产、`media` 传媒、`sports` 体育 |

### 使用方式

**命令行参数**（优先级最高）：
```bash
# 二级子领域
--domain technology.ai

# 一级领域（包含所有子领域）
--domain technology

# 多领域组合
--domain technology.ai,economy.finance

# 预设组合
--domain-group tech_all

# 全领域不过滤
--domain all
```

**YAML 配置**（向后兼容）：
```yaml
# 方式1：使用领域标识
domain_filter: "technology.ai"

# 方式2：自定义关键词
keyword_filter:
  - "自定义词1"
  - "自定义词2"

# 方式3：不过滤
domain_filter: "all"
```

**配置文件**：`config/domains.yaml` — 包含所有领域的关键词定义，可自定义扩展。

**优先级**：命令行参数 > YAML keyword_filter > 空列表（不过滤）
ruff check app/                                      # Lint
pytest                                               # 测试
```
