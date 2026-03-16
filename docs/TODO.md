# 后续任务清单

> 最后更新: 2026-03-10 (v39: 社媒舆情数据迁移 — 将社媒 Supabase（dfpijqpgsupvdmidztup）的 contents/comments/creators 三表迁移至主库 sentiment_contents/sentiment_comments/sentiment_creators，服务层改为从主库读取，删除旧 supabase_client.py)
> 基于前端 (Dean-Agent) 需求反推的优先级排序

---

## P0: 基础架构（已完成）

- [x] 项目骨架 (FastAPI + SQLAlchemy async + PostgreSQL + APScheduler 3.x)
- [x] 5 种模板爬虫 + 11 个自定义 Parser（全部注册）
- [x] 10 个维度 YAML 信源配置（181 源，148 启用；university_faculty 44/47 启用）
- [x] v1 REST API 27 端点 (articles/sources/dimensions/health + intel/policy 3 + intel/personnel 5 + faculty 13)
- [x] 项目库 API 6 端点 (GET /projects/ + /projects/stats + /projects/{id} + POST + PATCH + DELETE)，JSON 本地存储 data/projects.json，10 条 mock 数据
- [x] 调度系统 + 去重 + JSON 本地输出（data/raw/ 88 个 latest.json，覆盖模式 + is_new 标记）
- [x] Twitter 服务 + LLM 服务（OpenRouter）实现
- [x] 前端数据支撑状态文档 (crawl_status README)
- [x] 全量代码 Review（v7）— 消除 ~100 行重复代码、修复 3 个 P0 Bug、统一架构分层、优化 http_client/playwright_pool

### ⚠️ 已回退删除

- ~~v2 业务 API（13 端点 + schemas + business services）~~ — 代码已删除，需重新规划
- ~~API 设计文档 (docs/api_design/README.md)~~ — 随 v2 一起删除

---

## P1: 高优先级（直接影响前端功能）

### 信源补充
- [ ] 新增「领导讲话」信源 — gov.cn 国务院领导活动页 + 部委领导讲话
- [x] ~~恢复 bjfgw_policy~~ — v16: 改 URL 为 /fgwzwgk/2024zcwj/ 静态列表，static 可用
- [ ] 恢复 thepaper_tech (解析 __NEXT_DATA__ JSON)
- [ ] 恢复 huxiu_news (寻找 RSS feed 或 API)

### LLM 集成
- [ ] 配置 .env OPENROUTER_API_KEY + TWITTER_API_KEY
- [x] ~~重新规划业务 API 层~~ — v14: 政策智能两级处理（rules + LLM，减少 70% API 调用）；v15: 架构重构为 `services/intel/{domain}/` 子包结构，提取共享工具到 `shared.py`，迁移 policy 模块 + 新建 personnel 模块，URL 迁移至 `/api/v1/intel/...`

### 数据质量
- [x] ~~详情页内容抓取~~ — 已为 64 个启用信源配置 detail_selectors（universities 44, beijing_policy 7, national_policy 4, industry 3, talent 3, personnel 3），可自动抓取详情页正文。v11 修复 10 个源的错误选择器，新增 4 源。
- [x] ~~修复详情页 URL 404 问题~~ — selector_parser.py 增加 `_normalize_base_url()` 防止 urljoin 丢失路径段；修复 9 个源的 base_url 配置
- [x] ~~修复 title-only 源~~ — v11: 修复 bnu/ruc/jlu/sustech/slai 错误选择器，修复 uestc_news 列表选择器，修复 moe_renshi/si/talent TRS_UEDITOR→TRS_Editor，修复 jyb_news URL 空格 bug，新增 nosta/moe_keji/beijing_jw/nature_index detail_selectors
- [x] ~~修复 sii_news/buaa_news~~ — v13: sii_news 首页改版导致 404，改用 /czxw/list.htm (6→14条); buaa_news 首页 banner 仅 2 项，改用 /zhxw.htm (2→5条)
- [x] ~~人事变动提取~~ — v15: 纯规则引擎（正则）从 47 篇 personnel 文章中提取 84 条结构化任免记录（姓名、动作、职位、部门、日期），3 个 API 端点 (/api/v1/intel/personnel/feed|changes|stats)
- [x] ~~人事变动 LLM 富化~~ — v17: 为 84 条人事变动记录增加 LLM 分析（relevance/importance/group/note/actionSuggestion/background/signals/aiInsight），输出 enriched_feed.json，新增 2 个 API 端点 (/api/v1/intel/personnel/enriched-feed|enriched-stats)

---

## P2: 中优先级（扩展覆盖范围）

### 信源扩展
- [ ] Semantic Scholar API 扩展 — 支持 KOL 追踪 (hIndex, 论文数)
- [ ] ArXiv affiliation 变更检测 — 人才回流信号
- [ ] IT桔子/企查查 — 更全面投融资数据
- [x] 补充高校 HR/组织部页面 (15 所, snapshot 模式)
- [x] 补充 AI 院系官网 — v22→v37: 新建 university_faculty 维度，FacultyCrawler 模板；共 47 个信源，44 个已启用（2200+位教师），覆盖清华/北大/中科院/上交/复旦/南大/中科大/浙大/人大；11 个自定义 Parser 含 sjtu_cs/sjtu_ai/iscas/zju_cyber 等；v37 集成 LLM 智能提取层（35 源配置 llm_extraction=true），并行爬取架构，完成全量重爬（37/39 源成功，1,873 位教师）
- [x] faculty API 13 端点 — 师资列表/详情/统计/信源、基础信息/关系字段/动态备注/学术成就 PATCH、指导学生 CRUD（5 端点）
- [x] ScholarRecord 学术成就字段 — representative_publications / patents / awards，爬虫+用户双来源
- [ ] IEEE Fellow / ACM Fellow 年度公告源（awards.acm.org / ieee.org 为静态年度页面，非持续更新源）
- [ ] 微信公众号方案（搜狗微信搜索 / 公号后台）
- [x] ~~v16 信源拓展~~ — 新增 17 源 + 恢复 3 源：technology +6 RSS/ArXiv +2 恢复 (OpenAI/Anthropic blog)、national_policy +2 (网信办/市监总局)、beijing_policy +2 新 +1 恢复 (经信局/知产局/发改委)、events +2 (CCF/CAAI)、industry +2 (创业邦/信通院)、personnel +1 (中科院)、universities +2 (CESI/信工所)
- [x] ~~v19 中国 AI 大厂信源 + content_html 富文本~~ — 新增 5 中国 AI 公司博客 (Qwen/MiniMax/Moonshot/Hunyuan/Zhipu，4 启用)；新增 content_html 字段保留富文本 HTML（含图片标签）；新增 image_extractor + html_sanitizer 工具；新增 hunyuan_api 自定义 Parser

### 业务 API

- [x] ~~政策机会匹配~~ — v14: /api/v1/intel/policy/opportunities 端点 + 规则引擎自动检测机会（资金/截止日期正则）+ LLM 深度分析
- [x] ~~科技前沿数据 API~~ — v21: 8 主题分类（具身智能/多模态/AI Agent/AI4Science/端侧AI/大语言模型/AI安全/生成式AI应用），聚合 technology+industry+twitter+universities 4 维度 56 信源，规则引擎关键词匹配 + 热度趋势计算，5 个 API 端点 (/api/v1/intel/tech-frontier/topics|opportunities|stats|signals)
- [x] ~~Feed API 信源过滤~~ — v25: 所有 feed 类 API 支持 4 参数信源筛选（source_id/source_ids/source_name/source_names），精确+模糊匹配，覆盖 policy/feed, personnel/feed, personnel/enriched-feed, university/feed, tech_frontier/signals, articles/ 共 6 个端点，共享工具 parse_source_filter + resolve_source_ids_by_names，13 个单元测试全通过
- [ ] 学术流动分析 (LLM)
- [ ] 内参机会推荐 (LLM)

### 数据处理
- [x] ~~refined/ 数据管线~~ — v20: LLM 富化集成到每日 5 阶段 Pipeline（Stage 4），自动处理 policy + personnel，输出到 data/processed/
- [x] ~~缓存层~~ — v20: LLM 处理结果缓存在 _enriched/ 目录，增量追踪 hash 避免重复调用

---

## P3: 低优先级（锦上添花）

### 信源
- [ ] 创建 sentiment 维度 YAML (社交媒体，难度最高)
- [ ] 青塔 (Nuxt SPA，需 Playwright 深度适配)
- [ ] CNIPA 专利公告
- [ ] 修复 universities 禁用源 (zju, nju, bupt, nankai, nwpu, scu, lzu, zhejianglab, shanghairanking)

### 服务化 / 部署
- [x] ~~统一后端服务~~ — v20: 5 阶段 Pipeline（爬取→政策→人事→LLM 富化→索引）、启动健康验证、首次部署自动填充数据；v21: 扩展至 9 阶段（新增科技前沿处理 + 高校生态 + 每日简报）
- [x] ~~Pipeline 配置化~~ — v20: PIPELINE_CRON_HOUR/MINUTE 可配置调度时间、ENABLE_LLM_ENRICHMENT 控制 LLM 开关
- [x] ~~service.sh 增强~~ — v20: init 初始化命令、--production 生产模式、启动后健康检查
- [x] ~~systemd 部署~~ — v20: deploy/information-crawler.service + deploy/setup.sh 一键部署

### 基础设施
- [ ] Alembic 数据库迁移
- [x] ~~代码重复消除~~ — selector_parser.py 提取共享逻辑、http_client 重试函数统一
- [x] ~~Article IntegrityError 修复~~ — 改用 ON CONFLICT DO NOTHING
- [x] ~~CORS 配置修复~~ — 去掉无效 allow_credentials
- [x] ~~架构分层统一~~ — dimension_service.py、删除冗余 get_db_session、删除死字段 q
- [x] ~~Playwright 并发控制~~ — semaphore 限制 MAX_CONTEXTS
- [x] ~~sort_by 白名单~~ — 防止任意列名注入
- [ ] 单元测试 / 集成测试
- [ ] WebSocket 实时推送
- [ ] 部署验证 (Render)

---

## 不在爬虫范畴的模块

以下前端模块需要内部系统对接，不属于爬虫项目范围：

| 模块 | 所需系统 |
|------|---------|
| 院内管理 - 财务 | 内部财务系统 |
| 院内管理 - 项目督办 | 内部 OA/项目管理 |
| 院内管理 - 学生事务 | 学生信息系统 |
| 院内管理 - 舆情安全 | 舆情监测平台 (需 sentiment 维度 + 内部系统) |
| 院内管理 - 中心绩效 | 内部 KPI 系统 |
| 人脉网络 - 关系维护 | CRM 系统 |
| 人脉网络 - 社交行动 | CRM + 日历 |
| 智能日程 - 日程管理 | 飞书/Outlook 日历 API |
| 智能日程 - 邀约评估 | 日历 + 爬虫活动数据 |
| 智能日程 - 冲突化解 | 日历 API |
