# 信源爬取状态总览

> 最后更新: 2026-03-16 (v41: 新增 4 个北京市科委/中关村科创一线子频道信源 — bjkw_reform 深化改革、bjkw_industry 产业发展、bjkw_cooperation 开放合作、bjkw_frontier 科技前沿，每个信源爬取 20 条文章，100% 正文覆盖率；beijing_policy 维度从 11/14 提升到 15/18 启用，新增 80 条数据)

---

## 一、数据目录结构

```
data/raw/{dimension}/{group}/{source_id}/latest.json
```

覆盖模式：每次爬取生成全量条目，通过 `is_new` 标记区分新旧。

### JSON 格式

```json
{
  "source_id": "pku_news",
  "dimension": "universities",
  "group": "university_news",
  "source_name": "北京大学新闻网",
  "crawled_at": "2026-02-15T09:06:32+00:00",
  "previous_crawled_at": "2026-02-14T09:00:00+00:00",
  "item_count": 10,
  "new_item_count": 2,
  "items": [
    {
      "title": "刘志博、王剑威获2026年度陈嘉庚青年科学奖",
      "url": "https://news.pku.edu.cn/xwzh/xxx.htm",
      "url_hash": "7140a069...",
      "published_at": "2026-02-15T00:00:00",
      "author": null,
      "content": "获奖者简介及研究成果...",
      "content_hash": "a3b2c1d0...",
      "source_id": "pku_news",
      "dimension": "universities",
      "tags": ["university", "pku", "news"],
      "extra": {
        "pdf_url": "https://example.com/document.pdf"
      },
      "is_new": true
    }
  ]
}
```

**字段说明：**

- `content`：纯文本正文（`html_to_text()` 提取），用于全文搜索。
- `content_html`：清洗后的富文本 HTML（保留 `<img>`, `<a>`, `<table>` 等标签），用于前端渲染。
- `extra.pdf_url`：可选字段，包含页面中找到的 PDF 下载链接（绝对 URL）。如果页面无 PDF，此字段为空或不存在。
- `extra.images`：可选字段，图片元数据数组 `[{src, alt}]`，从正文 HTML 中提取。

---

## 二、业务智能加工数据 (processed)

原始爬取数据经 `scripts/process_*_intel.py` 加工后，输出到 `data/processed/` 供 API 直接读取。

```
data/processed/
  policy_intel/
    feed.json              # 政策动态 feed（含 matchScore/importance/LLM 增强）
    opportunities.json     # 结构化申报机会（截止日期/资助金额/联系人）
    _enriched/             # 单篇增强结果缓存
    _processed_hashes.json # 增量处理哈希追踪
  personnel_intel/
    feed.json              # 人事动态 feed（含 matchScore/importance/变动列表）
    changes.json           # 结构化人事变动（按人拆分：姓名/职务/部门/动作）
    _processed_hashes.json # 增量处理哈希追踪
```

### 加工管线状态

| 模块 | 脚本 | 方法 | 输入 | 产出 | API 前缀 |
|------|------|------|------|------|---------|
| policy_intel | `scripts/process_policy_intel.py` | 规则 + LLM (两级) | national_policy + beijing_policy + personnel 维度 raw JSON (184篇) | feed.json (184条, 55 LLM增强), opportunities.json (18条) | `/api/v1/intel/policy/` |
| personnel_intel | `scripts/process_personnel_intel.py` | 纯规则 (正则提取) | personnel 维度 raw JSON (62篇) | feed.json (62条), changes.json (84人次) | `/api/v1/intel/personnel/` |
| tech_frontier | `scripts/process_tech_frontier.py` | 规则 + LLM (两级) | technology + industry + twitter + universities(AI院所) 4维度 raw JSON (518篇) | topics.json (8主题, 168信号), opportunities.json (37条), stats.json | `/api/v1/intel/tech-frontier/` |

```
data/processed/
  ...
  tech_frontier/
    topics.json              # 8 个技术主题 + 内嵌 relatedNews/kolVoices
    opportunities.json       # 结构化机会（会议/合作/内参）
    stats.json               # KPI 指标（总主题数、飙升数、缺口数、周新信号）
    _enriched/               # LLM 增强结果缓存
    _processed_hashes.json   # 增量处理哈希追踪
```

```bash
# 运行政策智能加工（Tier 1 规则 + Tier 2 LLM 增强）
python scripts/process_policy_intel.py

# 运行人事情报加工（纯规则，无 LLM 费用）
python scripts/process_personnel_intel.py

# 运行科技前沿加工（8 主题分类 + 热度趋势）
python scripts/process_tech_frontier.py

# 试运行（不写文件）
python scripts/process_policy_intel.py --dry-run
python scripts/process_personnel_intel.py --dry-run
python scripts/process_tech_frontier.py --dry-run
```

---

## 三、各维度爬取状态

### 总览

| 维度 | 已配置 | 已启用 | 产出数据 | 正文覆盖率 | YAML 文件 |
|------|--------|--------|---------|-----------|----------|
| personnel (对人事) | 4 | 4 | ✅ 62条 | 98% | `sources/personnel.yaml` |
| universities (对高校) | 55 | 46 | ✅ 528条 | 81% | `sources/universities.yaml` |
| technology (对技术) | 34+4† | 33+4† | ✅ 299条+ | 97% | `sources/technology.yaml` + twitter |
| national_policy (对国家) | 8 | 6 | ✅ 52条 | 73% | `sources/national_policy.yaml` |
| beijing_policy (对北京) | 18 | 15 | ✅ 158条 | 98% | `sources/beijing_policy.yaml` |
| industry (对产业) | 10+1† | 6+1† | ✅ 49条 | 100% | `sources/industry.yaml` + twitter |
| talent (对人才) | 7+1† | 4+1† | ✅ 51条 | 86% | `sources/talent.yaml` + twitter |
| sentiment (对学院舆情) | 1† | 1† | ✅ 20条 | 100% | twitter 跨维度 |
| events (对日程) | 6 | 4 | ✅ 221条 | 0% (会议列表) | `sources/events.yaml` |
| university_faculty (高校师资) | 47 | 44 | ✅ 2200+位教师 | N/A (师资无正文) | `sources/university_faculty.yaml` |
| **合计** | **181** | **148** | **3000条+** | **74%** | **148 个数据文件** |

> † `sources/twitter.yaml` 的 7 个源按 `dimension` 字段分配到 4 个维度：technology 4源、industry 1源、talent 1源、sentiment 1源。
>
> 部分源正文覆盖率低于 100% 是因为 JSON 合并保留了旧条目（detail_selectors 配置前爬的），删除 `latest.json` 后重爬即可恢复。

### 正文来源分类

81 个启用信源配置 `detail_selectors`，自动抓取详情页正文。其余来源：

| 类型 | 源数 | 说明 |
|------|------|------|
| detail_selectors 抓取 | 81 | 爬虫自动进入详情页提取正文（v19: +caai_news, +cyzone_news, +qwen_blog, +minimax_news） |
| RSS 自带正文 | 12 | 36kr_ai_rss, mit_tech_review_rss, techcrunch_ai_rss, reddit_ml_rss, reddit_localllama_rss, tmtpost_news, theverge_ai_rss, venturebeat_ai_rss, wired_ai_rss, arstechnica_ai_rss, ieee_spectrum_ai_rss, openai_blog |
| API Parser | 6 | arxiv_cs_ai/cs_lg/cs_cl (abstract), github_trending (description), semantic_scholar_ai (abstract), hunyuan_news (content_brief) |
| Twitter API | 7 | 全部 100% 正文 |
| 仅列表/无正文 | 15 | jiqizhixin_rss (RSS 无正文字段), hacker_news (元数据), aideadlines/wikicfp (会议列表), 11 个新增国际 AI 公司博客（待配置 detail_selectors） |

> sjtu_news 的 `div.info` 选择器已修复为 `div.Article_content`，46/46 正文恢复。

---

### 详细状态：personnel (对人事) — 4/4 启用

| source_id | 名称 | 方法 | 条目数 | 详情页 | 说明 |
|-----------|------|------|--------|--------|------|
| mohrss_rsrm | 人社部-国务院人事任免 | dynamic | 20 | ✅ (20/20) | Playwright + `detail_fetch_js` (JS fetch 避免 Clear-Site-Data 反爬) + `div.TRS_Editor` |
| moe_renshi | 教育部-人事任免 | static | 20 | ✅ (20/20) | `div.TRS_Editor` |
| moe_renshi_si | 教育部-人事司公告 | static | 7 | ✅ (6/7) | `div.TRS_Editor` |
| cas_renshi | 中科院-人事任免 | static | 15 | ✅ (15/15) | `div.cobtbox`，关键词过滤任免/人事/选举 |

### 详细状态：universities (对高校) — 46/55 启用

46 个数据文件，528 条目，427 有正文 (81%)。全部 46 启用源已配置 detail_selectors。

#### A. 高校新闻网 (32 源, 25 启用)

| source_id | 名称 | 方法 | 条目数 | 正文数 | content selector |
|-----------|------|------|--------|--------|-----------------|
| tsinghua_news | 清华大学新闻网 | static | 10 | 10 | `div.content` |
| pku_news | 北京大学新闻网 | dynamic | 10 | 10 | `div.article` |
| ustc_news | 中国科大新闻网 | static | 30 | 30 | `div.article-content` |
| sjtu_news | 上海交大新闻网 | static | 46 | 46 | `div.Article_content` |
| fudan_news | 复旦大学新闻网 | static | 16 | 16 | `div.article` |
| buaa_news | 北京航空航天大学 | static | 5 | 4 | `div.v_news_content` |
| bit_news | 北京理工大学 | static | 21 | 21 | `div.article` |
| bnu_news | 北京师范大学 | static | 5 | 4 | `div.article` |
| ruc_news | 中国人民大学 | dynamic | 9 | 3 | `div.page-content` |
| tju_news | 天津大学 | static | 4 | 4 | `div.v_news_content` |
| tongji_news | 同济大学 | static | 5 | 2 | `div.v_news_content` |
| jlu_news | 吉林大学 | static | 10 | 10 | `#vsb_content_2` |
| hit_news | 哈尔滨工业大学 | static | 8 | 8 | `div.wp_articlecontent` |
| seu_news | 东南大学 | static | 5 | 1 | `div.wp_articlecontent` |
| xmu_news | 厦门大学 | static | 16 | 5 | `div.v_news_content` |
| sdu_news | 山东大学 | static | 16 | 16 | `div.nymain` |
| whu_news | 武汉大学 | static | 6 | 6 | `div.v_news_content` |
| hust_news | 华中科技大学 | static | 6 | 5 | `div.v_news_content` |
| csu_news | 中南大学 | static | 14 | 12 | `div.v_news_content` |
| xidian_news | 西安电子科技大学 | static | 12 | 12 | `div.v_news_content` |
| xjtu_news | 西安交通大学(要闻聚焦) | static | 10 | 10 | `div.v_news_content` |
| uestc_news | 电子科技大学 | static | 55 | 45 | `div.v_news_content` |
| nudt_news | 国防科技大学 | static | 22 | 22 | `div.pageCon` |
| sysu_news | 中山大学 | dynamic | 11 | 4 | `div.v_news_content` |
| sustech_news | 南方科技大学 | static | 6 | 6 | `div.u-content` |

#### B. AI 研究机构 (11 源, 10 启用)

| source_id | 名称 | 方法 | 条目数 | 正文数 | content selector |
|-----------|------|------|--------|--------|-----------------|
| baai_news | BAAI 智源社区 | dynamic | 9 | 9 | `div.post-content` |
| tsinghua_air | 清华 AIR | static | 16 | 16 | `div.v_news_content` |
| shlab_news | 上海 AI 实验室 | dynamic | 7 | 7 | `#lightgallery` |
| pcl_news | 鹏城实验室 | static | 10 | 10 | `div.article` |
| ia_cas_news | 中科院自动化所 | static | 37 | 34 | `div.trs_editor_view` |
| ict_cas_news | 中科院计算所 | static | 6 | 5 | `#xlmain` |
| sii_news | 上海创智学院 | static | 14 | 14 | `div.wp_articlecontent` |
| slai_news | 深圳河套学院 | static | 6 | 6 | `div.field-item` |
| cesi_news | 电子标准化研究院 | static | — | — | `div.content3` |
| iie_cas_news | 中科院信工所 | static | — | — | `div.about-content` |

#### C. 高教新闻聚合 (3 源, 2 启用)

| source_id | 名称 | 方法 | 条目数 | 正文数 | content selector |
|-----------|------|------|--------|--------|-----------------|
| eol_news | 中国教育在线 | static | 1 | 1 | `div.article` |
| jyb_news | 中国教育报 | static | 40 | 20 | `div.xl_text` |

#### D. 科技成果与荣誉 (4 源, 4 启用)

| source_id | 名称 | 方法 | 条目数 | 正文数 | content selector |
|-----------|------|------|--------|--------|-----------------|
| cas_news | 中国科学院 | static | 1 | 1 | `div.trs_editor_view` |
| cae_news | 中国工程院 | static | 6 | 6 | `#info_content` |
| nosta_news | 国家科技奖励办 | dynamic | 6 | 2 | `div.TRS_UEDITOR` |
| moe_keji | 教育部科技司 | static | 7 | 5 | `div.TRS_Editor` |

#### E. 省级教育厅 (5 源, 5 启用)

| source_id | 名称 | 方法 | 条目数 | 正文数 | content selector |
|-----------|------|------|--------|--------|-----------------|
| beijing_jw | 北京市教委 | static | 1 | 1 | `div.TRS_UEDITOR` |
| shanghai_jw | 上海市教委 | static | 2 | 2 | `#ivs_content` |
| zhejiang_jyt | 浙江省教育厅 | static | 6 | 6 | `#zoom` |
| jiangsu_jyt | 江苏省教育厅 | static | 5 | 5 | `#zoom` |
| guangdong_jyt | 广东省教育厅 | static | 2 | 2 | `div.article` |

#### 禁用源 (9)

| source_id | 名称 | 原因 |
|-----------|------|------|
| zju_news | 浙江大学 | URL 返回错误 |
| nju_news | 南京大学 | SSL 证书问题 |
| bupt_news | 北京邮电大学 | WAF 412 拦截 |
| nankai_news | 南开大学 | 全页面 JS 渲染 |
| nwpu_news | 西北工业大学 | 主页重度 JS 渲染 |
| scu_news | 四川大学 | WAF 412 拦截 |
| lzu_news | 兰州大学 | WAF 412 拦截 |
| zhejianglab_news | 之江实验室 | 复杂 SPA |
| shanghairanking_news | 软科 | URL 404 |

### 详细状态：technology (对技术) — 33/34 启用 + 4 Twitter

#### A. 国内科技媒体 (2 源, 2 启用)

| source_id | 名称 | 方法 | 说明 |
|-----------|------|------|------|
| jiqizhixin_rss | 机器之心 | rss | keyword_filter=[] 覆盖维度默认，12 条（RSS 无正文） |
| 36kr_ai_rss | 36氪-AI频道 | rss | RSS 自带正文 |

#### B. 国际科技源 (8 源, 8 启用)

| source_id | 名称 | 方法 | 说明 |
|-----------|------|------|------|
| techcrunch_ai_rss | TechCrunch AI | rss | RSS 自带正文 |
| theverge_ai_rss | The Verge AI | rss | keyword_filter 过滤 |
| mit_tech_review_rss | MIT Technology Review | rss | RSS 自带正文 |
| venturebeat_ai_rss | VentureBeat AI | rss | **新增** RSS 自带正文 |
| ieee_spectrum_ai_rss | IEEE Spectrum AI | rss | **新增** IEEE 权威技术视角 |
| wired_ai_rss | Wired AI | rss | **新增** keyword_filter 过滤 |
| arstechnica_ai_rss | Ars Technica AI | rss | **新增** 深度技术分析 |

#### C. 公司官方博客 (13 源, 13 启用) ⭐ **新增 11 个头部 AI 大厂**

> ⚠️ 新增 11 个博客暂未配置 `detail_selectors`，仅抓取列表页标题/链接，正文待后续补充。

| source_id | 名称 | 方法 | 正文 | 说明 |
|-----------|------|------|------|------|
| openai_blog | OpenAI Blog | rss | ✅ RSS | **恢复**：发现 RSS feed (openai.com/news/rss.xml) |
| anthropic_blog | Anthropic Research | static | ✅ detail | **恢复**：SSR 页面，static 可用 |
| google_deepmind_blog | Google DeepMind Blog | dynamic | ❌ | **新增**：Gemini、AlphaFold 等前沿研究 |
| meta_ai_blog | Meta AI Blog | dynamic | ❌ | **新增**：Llama 系列、开源 AI |
| microsoft_ai_blog | Microsoft AI Blog | static | ❌ | **新增**：Copilot、Azure AI |
| mistral_ai_news | Mistral AI News | dynamic | ❌ | **新增**：欧洲开源大模型领军 |
| xai_blog | xAI Blog (Grok) | dynamic | ❌ | **新增**：Elon Musk 的 AGI 研究 |
| cohere_blog | Cohere Blog | static | ❌ | **新增**：企业级 AI，2026 拟 IPO |
| stability_ai_news | Stability AI News | dynamic | ❌ | **新增**：Stable Diffusion 图像生成 |
| huggingface_blog | Hugging Face Blog | static | ❌ | **新增**：Transformers 开源社区 |
| runway_blog | Runway Blog | dynamic | ❌ | **新增**：视频生成 AI (Gen-3) |
| inflection_ai_blog | Inflection AI Blog | static | ❌ | **新增**：Pi 对话 AI |

#### D. ArXiv 论文 (3 源, 3 启用)

| source_id | 名称 | 方法 | 说明 |
|-----------|------|------|------|
| arxiv_cs_ai | ArXiv cs.AI | arxiv_api | AI 综合论文 |
| arxiv_cs_lg | ArXiv cs.LG | arxiv_api | **新增** 机器学习论文 |
| arxiv_cs_cl | ArXiv cs.CL | arxiv_api | **新增** NLP/大模型论文 |

#### E. 社区讨论 (5 源, 5 启用)

| source_id | 名称 | 方法 | 说明 |
|-----------|------|------|------|
| hacker_news | Hacker News | hacker_news_api | 元数据 |
| reddit_ml_rss | Reddit r/MachineLearning | rss | RSS 自带正文 |
| reddit_localllama_rss | Reddit r/LocalLLaMA | rss | RSS 自带正文 |
| github_trending | GitHub Trending | github_api | description |

#### F. 中国 AI 公司博客 (5 源, 4 启用) ⭐ **新增**

| source_id | 名称 | 方法 | 启用 | 说明 |
|-----------|------|------|------|------|
| qwen_blog | Qwen Blog (阿里通义千问) | static | ✅ | Hugo 博客，detail_selectors 取正文+content_html |
| minimax_news | MiniMax 新闻动态 | dynamic | ✅ | Next.js SPA，Playwright 抓取 |
| moonshot_research | 月之暗面-最新研究 | dynamic | ✅ | 外链聚合（kimi.com/blog, HuggingFace 等） |
| hunyuan_news | 腾讯混元-最新动态 | hunyuan_api | ✅ | 自定义 API Parser，数据来自公众号文章 |
| zhipu_news | 智谱AI-最新动态 | dynamic | ❌ | React SPA 无 DOM 链接，新闻更新停滞 |

### 详细状态：national_policy (对国家) — 7/8 启用

全部 7 启用源已配置 detail_selectors。

| source_id | 名称 | 方法 | 启用 | 条目数 | 详情页 | content selector |
|-----------|------|------|------|--------|--------|-----------------|
| gov_cn_zhengce | 国务院-最新政策 | dynamic | ✅ | 20 | ✅ (20/20) | `div.pages_content` |
| ndrc_policy | 发改委-通知通告 | static | ✅ | 5 | ✅ (4/5) | `div.TRS_Editor` |
| moe_policy | 教育部-政策法规 | static | ✅ | 8 | ✅ (8/8) | `div.TRS_Editor` |
| most_policy | 科技部-信息公开 | static | ✅ | 10 | ✅ (6/10) | `div.TRS_UEDITOR` (PDF 项无正文) |
| cac_policy | 国家网信办-政策法规 | static | ✅ | 9 | ✅ (9/9) | `div.main-content` AI 治理核心监管 |
| samr_news | 国家市监总局-要闻 | static | ✅ | 0 | — | `#zoom` 当期无匹配关键词 |
| miit_policy | 工信部-政策文件 | dynamic | ✅ | 10 | ✅ (10/10) | `div.ccontent.center` 已修复 (2026-03-16) |
| nsfc_news | 国家自然科学基金委 | static | ❌ | — | — | URL 404 |

### 详细状态：beijing_policy (对北京) — 15/18 启用

15 启用源全部配置 detail_selectors。

#### A. 政策文件

| source_id | 名称 | 方法 | 启用 | 条目数 | 详情页 |
|-----------|------|------|------|--------|--------|
| beijing_zhengce | 首都之窗-政策文件 | static | ✅ | 2 | ✅ (2/2) |
| bjkw_policy | 北京市科委/中关村管委会 | static | ✅ | 4 | ✅ (4/4) |
| bjkw_reform | 北京市科委/中关村-深化改革 | static | ✅ | 20 | ✅ (20/20) |
| bjkw_industry | 北京市科委/中关村-产业发展 | static | ✅ | 20 | ✅ (20/20) |
| bjkw_cooperation | 北京市科委/中关村-开放合作 | static | ✅ | 20 | ✅ (20/20) |
| bjkw_frontier | 北京市科委/中关村-科技前沿 | static | ✅ | 20 | ✅ (20/20) |
| bjjw_policy | 北京市教委 | static | ✅ | 14 | ✅ (13/14) |
| bjrsj_policy | 北京市人社局 | static | ✅ | 3 | ✅ (3/3) |
| zgc_policy | 中关村示范区 | static | ❌ | — | 域名连接被重置 |
| ncsti_policy | 国际科创中心 | static | ✅ | 6 | ✅ (6/6) keyword_filter=[] 不过滤 |
| bjjxj_policy | 北京市经信局-通知公告 | static | ✅ | 20 | ✅ (20/20) keyword_filter=[] 不过滤，base_url 已修复 |
| bjzscqj_policy | 北京市知识产权局 | static | ✅ | 10 | ✅ (10/10) keyword_filter=[] 不过滤 |
| bjfgw_policy | 北京市发改委-政策文件 | static | ✅ | 7 | ✅ (7/7) base_url 已修复，关键词已扩展 |
| bjhd_policy | 海淀区政府-要闻动态 | static | ✅ | 8 | ✅ (8/8) |

#### B. 人事变动与要闻

| source_id | 名称 | 方法 | 启用 | 条目数 | 详情页 |
|-----------|------|------|------|--------|--------|
| beijing_ywdt | 首都之窗-要闻 | static | ✅ | 2 | ✅ (2/2) |
| bjd_news | 北京日报 | static | ❌ | — | 布局复杂 |
| bjrd_renshi | 北京市人大常委会 | static | ✅ | 1 | ✅ (1/1) |

### 详细状态：industry (对产业) — 6/10 启用 + 1 Twitter

5 启用源配置 detail_selectors（含 cyzone_news 从 RSS 改为 static），1 RSS 自带正文。

| source_id | 名称 | 方法 | 启用 | 条目数 | 详情页 |
|-----------|------|------|------|--------|--------|
| 36kr_news | 36氪-快讯 | static | ✅ | 3 | ✅ (3/3) |
| huxiu_news | 虎嗅 | static | ❌ | — | WAF 反爬 |
| tmtpost_news | 钛媒体 | rss | ✅ | 12 | RSS 自带 |
| jiemian_tech | 界面新闻-科技 | static | ✅ | 6 | ✅ (6/6) `div.article-content` |
| thepaper_tech | 澎湃新闻-科技 | static | ❌ | — | Next.js SPA |
| iyiou_ai | 亿欧-AI | static | ❌ | — | 空壳页面 |
| chinaventure_news | 投中网 | static | ✅ | 9 | ✅ (9/9) `div.article_slice_pc` |
| 36kr_investment | 36氪-融资频道 | static | ❌ | — | URL 已下线 |
| cyzone_news | 创业邦 | static | ✅ | ✅ | `div.g-art-content` (v19 从 RSS 改为 static + detail_selectors) |
| caict_news | 中国信通院-动态 | static | ✅ | 🔴 | HTTP 412 Precondition Failed |

### 详细状态：talent (对人才) — 4/7 启用 + 1 Twitter

3 启用源配置 detail_selectors。

| source_id | 名称 | 方法 | 启用 | 条目数 | 详情页 |
|-----------|------|------|------|--------|--------|
| csrankings | CSRankings | static | ❌ | — | React SPA |
| semantic_scholar_ai | Semantic Scholar | API | ✅ | 20 | API 自带 (13/20 有 abstract) |
| nature_index | Nature Index | static | ✅ | 4 | ✅ (4/4) `div.c-article-body` |
| aminer_ai | AMiner-AI学者 | static | ❌ | — | JS SPA |
| nsfc_talent | NSFC杰青/优青公示 | static | ❌ | — | URL 404 |
| moe_talent | 教育部人才计划公示 | static | ✅ | 5 | ✅ (5/5) `div.TRS_Editor` |
| wrsa_talent | 欧美同学会 | static | ✅ | 2 | ✅ (2/2) `#Content` |

### 详细状态：events (对日程) — 4/6 启用

| source_id | 名称 | 方法 | 启用 | 条目数 | 说明 |
|-----------|------|------|------|--------|------|
| aideadlines | AI Conference Deadlines | dynamic | ✅ | 191 | 全量 AI 会议 |
| wikicfp | WikiCFP-AI | static | ✅ | 20 | AI 会议 CFP |
| ccf_focus | CCF 焦点 | static | ✅ | 0 | 当期无匹配关键词 |
| caai_news | CAAI 新闻 | static | ✅ | 10 | 中国人工智能学会，已配置 detail_selectors `div.content` (10/10 正文) |
| huodongxing | 活动行-人工智能 | static | ❌ | — | CAPTCHA/反爬 |
| meeting_edu | 中国学术会议在线 | static | ❌ | — | 站点无法连接 |

### 详细状态：university_faculty (高校师资) — 44/47 启用

> 新增维度 (2026-02-27)。专用 `FacultyCrawler` 模板（`crawl_method: faculty`），支持静态/Playwright 模式，
> 通过 `faculty_selectors` 配置提取姓名、职称、简介、联系方式、照片。
> 数据输出：`data/raw/university_faculty/{group}/{source_id}/latest.json`
> 字段：`title`=姓名, `extra.university`, `extra.department`, `extra.position`, `extra.email`, `extra.photo_url`
> 2026-02-28 v25：启用 9 个新信源（SJTU CS/InfoSec、Fudan CS、NJU CS/AI/IS、USTC CS/SIST、RUC AI）；
> SJTU CS 使用自定义 AJAX Parser（`crawler_class: sjtu_cs_faculty`）；
> 2026-02-28 v27：修复 4 个 PKU 数据零源（JS 重定向 URL + 错误选择器）；启用 nju_software/ustc_cyber/pku_math/tsinghua_ias 4 个新信源；修复 ict_cas 详情页选择器（completeness 35%→60%）。
> NJU 系列使用 `verify_ssl: false` 绕过老旧 TLS 握手失败；
> Fudan CS 使用 Playwright 等待 AJAX 加载；
> USTC SIST 指向 EEIS 子系教授列表（门户结构限制）。
> 2026-02-28 v30：创建 ISCAS 自定义 Parser（+73师资）；验证 8 个已启用源已产出数据（+428师资，平均完整度 51%）。
> 2026-02-28 v31：翻页修复 PKU CS(12→120)/CIS(8→37)、USTC CS URL修复(2→32)、USTC SIST翻页(8→59)、Tsinghua SE(5→41)；
> ZJU Cyber 自定义 Parser（富文本表格解析，+48）；ZJU CS/Soft 禁用（开发环境不可达）；总教师数 1928→2027，已启用源 33→34。
> 2026-03-01 v35：faculty_crawler 增强 — heading_sections 正则匹配、LLM 字段提取集成；修复 5 个高校源（tsinghua_ymsc/sjtu_se/sjtu_qingyuan/ustc_ds/pku_coe）URL/选择器；禁用 3 个不可达源（tsinghua_iaiig/tsinghua_sigs/ustc_se）；enable_llm 配置 4 源，已启用源 34→39。

| source_id | 机构 | 院系 | 状态 | 说明 |
| --------- | ---- | ---- | ---- | ---- |
| tsinghua_air_faculty | 清华大学 | 智能产业研究院 | ✅ 37人 | `ul li > h2+p` |
| tsinghua_cs_faculty | 清华大学 | 计算机系 | ✅ 135人 | `dd li > h2`，按研究所分块 |
| tsinghua_iiis_faculty | 清华大学 | 交叉信息研究院 | ✅ 77人 | 已启用 |
| tsinghua_se_faculty | 清华大学 | 软件学院 | ✅ 41人 | v31 验证：div.name-container 选择器正常工作 |
| tsinghua_ee_faculty | 清华大学 | 电子工程系 | ✅ 147人 | v28 修复：.line .t ul a 选择器，含detail_selectors(bio/email/research_areas) |
| tsinghua_au_faculty | 清华大学 | 自动化系 | ✅ 7人 | v28 修复：name改为h3，添加detail_selectors(bio/email/research_areas) |
| tsinghua_insc_faculty | 清华大学 | 网络研究院 | ✅ 53人 | v29 修复：URL → www.insc.tsinghua.edu.cn/szdw_/jsml.htm，<a>直选，heading_sections(bio/research_areas) |
| tsinghua_ias_faculty | 清华大学 | 高等研究院 | ✅ 29人 | v27 修复，URL → www.ias.tsinghua.edu.cn/yjry/jy.htm |
| tsinghua_futurelab_faculty | 清华大学 | 未来实验室 | ✅ 35人 | v29 修复：URL → thfl.tsinghua.edu.cn/yjdw/jzg/zxjg.htm，ul.teacher li 结构 |
| tsinghua_ymsc_faculty | 清华大学 | 丘成桐数学中心 | ✅ 已启用 | v35 修复：list_item=`a[href*='/info/']`、name=`h4`，enable_llm=true |
| tsinghua_life_faculty | 清华大学 | 生命科学学院 | ✅ 122人 | v29 修复：URL → life.tsinghua.edu.cn/szdw/jzyg1/All1/All.htm，div.pepolelist li 结构，bio 选择器 |
| tsinghua_sigs_faculty | 清华大学 | 深圳国际研究生院 | ❌ 禁用 | v35 禁用：AJAX+GsapAnimate 前端渲染，静态爬虫无法获取，需自定义 Parser |
| tsinghua_iaiig_faculty | 清华大学 | 人工智能国际治理研究院 | ❌ 禁用 | v35 禁用：ERR_CONNECTION_CLOSED，网络不可达 |
| pku_cs_faculty | 北京大学 | 计算机学院 | ✅ 120人 | v31 翻页修复 max_pages=10，`ul li > h3` |
| pku_cis_faculty | 北京大学 | 智能学院 | ✅ 37人 | v31 翻页修复 max_pages=5，`ul li > h3` |
| pku_icst_faculty | 北京大学 | 王选计算机研究所 | ✅ 已启用 | 待下次爬取 |
| pku_ic_faculty | 北京大学 | 集成电路学院 | ✅ 已启用 | 待下次爬取 |
| pku_ss_faculty | 北京大学 | 软件与微电子学院 | ✅ 已启用 | 待下次爬取 |
| pku_cfcs_faculty | 北京大学 | 前沿计算研究中心 | ✅ 已启用 | 待下次爬取 |
| pku_math_faculty | 北京大学 | 数学学院 | ✅ 20人 | v27 修复，URL → jsdw/js_20180628175159671361/index.htm |
| pku_eecs_sz_faculty | 北京大学 | 信息工程学院（深圳） | ✅ 已启用 | v35 修复：URL → pkusz.edu.cn/szdw/bsh/xxgcxy1.htm，ul li 结构 |
| pku_coe_faculty | 北京大学 | 工学院 | ✅ 已启用 | v35 修复：list_item=`a[href*='/teaching/all_time/']`，enable_llm=true |
| ict_cas_faculty | 中国科学院 | 计算技术研究所 | ✅ 24人 | `ul li > h5 a:last-child` |
| casia_faculty | 中国科学院 | 自动化研究所 | ✅ 20人 | `ul.row li > div.name` |
| iscas_faculty | 中国科学院 | 软件研究所 | ✅ 73人 | v30 自定义 Parser (`iscas_faculty`)，纯文本名单+正则提取 |
| sjtu_ai_faculty | 上海交通大学 | 人工智能研究院 | ✅ 已启用 | v34 开发自定义 Parser (`sjtu_ai_faculty`)，直接调用 /api/teacher?time=xxx API 端点获取教师列表 |
| sjtu_cs_faculty | 上海交通大学 | 计算机系 | ✅ 253人 | 自定义 AJAX Parser (`sjtu_cs_faculty`) |
| sjtu_se_faculty | 上海交通大学 | 软件学院 | ✅ 已启用 | v35 修复：URL → /Data/List/people，list_item=`div.tli`，label_prefix_sections |
| sjtu_infosec_faculty | 上海交通大学 | 网络空间安全学院 | ✅ 80人 | `div.Faculty li`，分字母索引页 |
| sjtu_qingyuan_faculty | 上海交通大学 | 清源研究院 | ✅ 已启用 | v35 修复：URL → /c/quanzhijiaoshi，list_item=`a[href^='/a/']`，enable_llm=true |
| fudan_cs_faculty | 复旦大学 | 计算与智能创新学院 | ✅ 189人 | Playwright + `li.news` AJAX |
| fudan_ai_robot_faculty | 复旦大学 | 智能机器人与先进制造创新学院 | ❌ 待启用 | URL 待确认 |
| nju_cs_faculty | 南京大学 | 计算机系 | ✅ 65人 | `li.list_item`，`verify_ssl: false` |
| nju_ai_faculty | 南京大学 | 人工智能学院 | ✅ 36人 | `li.news`，`verify_ssl: false` |
| nju_software_faculty | 南京大学 | 软件学院 | ✅ 56人 | v27 启用，table 结构，含 profile 链接 |
| nju_is_faculty | 南京大学 | 智能科学与技术学院 | ✅ 14人 | `li.news`，`verify_ssl: false` |
| nju_ise_faculty | 南京大学 | 智能软件与工程学院 | ✅ 15人 | v29 修复：URL → ise.nju.edu.cn/szll/zjzjs.htm，table tr td 结构，verify_ssl: false |
| ustc_cs_faculty | 中国科学技术大学 | 计算机学院 | ✅ 32人 | v31 URL修复 → js_23235/list.htm + max_pages=2 |
| ustc_sist_faculty | 中国科学技术大学 | 信息科学技术学院 | ✅ 59人 | v31 翻页修复 max_pages=8（8页×8人） |
| ustc_se_faculty | 中国科学技术大学 | 软件学院 | ❌ 禁用 | v35 禁用：官网无公开教师列表页 |
| ustc_ds_faculty | 中国科学技术大学 | 人工智能与数据科学学院 | ✅ 已启用 | v35 修复：URL → /szdw/list.htm，list_item=`li.list_item`，max_pages=2，enable_llm=true |
| ustc_cyber_faculty | 中国科学技术大学 | 网络空间安全学院 | ✅ 59人 | v27 启用，dd.fl 分职级列表结构 |
| zju_cs_faculty | 浙江大学 | 计算机学院 | ❌ 禁用 | 开发环境 ECONNREFUSED，需服务器测试 |
| zju_cyber_faculty | 浙江大学 | 网络空间安全学院 | ✅ 48人 | v31 自定义 Parser (`zju_cyber_faculty`)，富文本表格解析 |
| zju_soft_faculty | 浙江大学 | 软件学院 | ❌ 禁用 | 开发环境 ECONNREFUSED，需服务器测试 |
| ruc_info_faculty | 中国人民大学 | 信息学院 | ✅ 20人 | v29 修复：URL → info.ruc.edu.cn/jsky/szdw/ajxjgcx/bx/bx1/index.htm（JS redirect），div.research 结构 |
| ruc_ai_faculty | 中国人民大学 | 高瓴人工智能学院 | ✅ 26人 | `div.tutor`，含 bio |

---

## 四、运行方式

```bash
# 测试单个源（不写数据库，输出 JSON 到 data/raw/）
python scripts/run_single_crawl.py --source pku_news --no-db

# 批量运行所有启用信源（按维度汇总报告）
python scripts/run_all_crawl.py

# 只运行某个维度
python scripts/run_all_crawl.py --dimension technology

# 业务智能加工
python scripts/process_policy_intel.py
python scripts/process_personnel_intel.py

# 重新生成数据索引
python scripts/generate_index.py

# 启动完整服务（含调度器）
uvicorn app.main:app --reload
```

---

## 九、高校师资 (university_faculty)

### 总览

| 总源数 | 已启用 | 已禁用 | 覆盖学校 | 总教师数 | 平均完整度 | LLM 框架 |
|--------|--------|--------|---------|---------|-----------|---------|
| 47 | 44 | 3 | 清华/北大/中科院/上交/复旦/南大/中科大/浙大/人大 | 2200+ | 54.8% | ✅ v37 |

**数据说明：**
- v37 LLM 框架（2026-03-04）：集成 LLM 智能提取层，35 个信源配置 `llm_extraction: true`，自动提取混合数据（phone/research_areas/education）
  - 框架优势：无需手写复杂正则，LLM 理解上下文自动提取结构化数据
  - 成本优化：使用 Deepseek V3（$0.27/M input, $1.10/M output），单个教师成本 $0.0004
  - 数据质量：Phone 0%→94.8%, Research areas 0.7%→94.1%, Education 0%→90.4%（Tsinghua CS 测试）
  - 并行架构：按高校维度并行处理，每校最多 3 并发进程，总耗时 6.3h（vs 串行 ~20h）
  - 最终结果：37/39 源成功（94.9%），1,873 位教师，总成本 $0.50-0.70
- v35 修复：+6源（tsinghua_ymsc/sjtu_se/sjtu_qingyuan/ustc_ds/pku_coe/pku_eecs_sz），-2源禁用（tsinghua_iaiig/ustc_se）
- v34 修复：sjtu_ai_faculty 自定义 Parser 已启用
- 当前禁用源（3个）：tsinghua_sigs（AJAX+GsapAnimate 前端渲染）、tsinghua_iaiig（ERR_CONNECTION_CLOSED）、ustc_se（官网无公开教师列表页）
- 当前失败源（2个）：zju_cs_faculty、zju_soft_faculty（选择器需更新）
- 完整度评分基于 ScholarRecord schema（0-100分）
- 评分权重：name(20), bio(15), research_areas(15), position(10), email(10), profile_url(10), photo(5), 其他(15)
- 典型分数：列表页 ~25-30，含详情页 ~50-70，LLM 提取（llm_extraction）~70-85

### 按学校分组

| 学校组 | 源数 | 已启用 | 教师数 | 平均完整度 | 说明 |
|--------|------|--------|--------|-----------|------|
| **tsinghua** | 13 | 11 | 683+ | 55.3% | 清华各院系，v35 ymsc修复+启用，2个禁用(sigs/iaiig) |
| **pku** | 9 | 9 | 275+ | 56.0% | 北大各院系，v35 eecs_sz/coe修复启用，全部已启用 |
| **cas** | 4 | 3 | 117+ | 59.1% | 中科院3所，ISCAS自定义Parser(73人)，ict_cas(24人)，casia(20人) |
| **sjtu** | 5 | 5 | 333+ | 42.5% | 上交大，v35 se/qingyuan修复，v34 ai自定义Parser，全部已启用 |
| **fudan** | 2 | 1 | 189 | 45.0% | 复旦大学，Playwright AJAX加载，1个待启用(ai_robot，URL待确认) |
| **nju** | 5 | 5 | 186 | 42.6% | 南京大学，全部启用 |
| **ustc** | 5 | 4 | 150+ | 54.0% | 中科大，v35 ds修复启用，1个禁用(se，官网无公开列表) |
| **zju** | 3 | 1 | 48 | 44.7% | 浙大，v31 Cyber自定义Parser(+48)，CS/Soft禁用(ECONNREFUSED) |
| **ruc** | 2 | 2 | 46 | 52.5% | 中国人民大学，全部启用 |

### 已启用信源详情

#### 清华大学 (10/13 启用)

| source_id | 教师数 | 完整度 | 状态 | 说明 |
|-----------|--------|--------|------|------|
| tsinghua_air_faculty | 37 | 50.5% | ⚠️ 可接受 | 智能产业研究院，网站结构限制 |
| tsinghua_cs_faculty | 135 | 69.1% | ⚠️ 可接受 | 计算机系，接近优秀级别 |
| tsinghua_iiis_faculty | 77 | 62.9% | ⚠️ 可接受 | 交叉信息研究院，邮箱为图片 |
| tsinghua_se_faculty | 41 | 39.1% | ⚠️ 可接受 | 软件学院，v31 验证 div.name-container 正常工作（5→41人） |
| tsinghua_au_faculty | 7 | 75.0% | ✅ 良好 | 自动化系，v28 修复 name选择器 + detail_selectors |
| tsinghua_ee_faculty | 147 | 50.3% | ⚠️ 可接受 | 电子工程系，v28 修复 a 直选+detail_selectors，从7人→147人 |
| tsinghua_ias_faculty | 29 | 65.0% | ⚠️ 可接受 | 高等研究院，v27 修复 URL |
| tsinghua_insc_faculty | 53 | 75.9% | ✅ 优秀 | 网络研究院，v29 修复 URL + heading_sections |
| tsinghua_futurelab_faculty | 35 | 55.0% | ⚠️ 可接受 | 未来实验室，v29 修复 URL，ul.teacher li 卡片结构 |
| tsinghua_life_faculty | 122 | 43.3% | ⚠️ 可接受 | 生命科学学院，v29 修复 URL，div.pepolelist li + bio选择器 |

#### 北京大学 (7/9 启用)

| source_id | 教师数 | 完整度 | 状态 | 说明 |
|-----------|--------|--------|------|------|
| pku_cs_faculty | 120 | 50.0% | ⚠️ 可接受 | 计算机学院，v31 翻页修复 max_pages=10（12→120人） |
| pku_cis_faculty | 37 | 60.0% | ⚠️ 可接受 | 智能学院，v31 翻页修复 max_pages=5（8→37人） |
| pku_icst_faculty | 20 | 70.0% | ✅ 良好 | 王选所，v28 添加 research_areas 选择器 |
| pku_ic_faculty | 27 | 74.8% | ✅ 良好 | 集成电路学院，v28 修复 base_url + detail_selectors |
| pku_ss_faculty | 15 | 36.7% | ❌ 基础 | 软件与微电子学院，仅5人有个人主页 |
| pku_cfcs_faculty | 36 | 69.2% | ✅ 良好 | 前沿计算研究中心，v28 修复 bio + research_areas |
| pku_math_faculty | 20 | 60.0% | ✅ 良好 | 数学学院，v28 添加 research_areas 选择器 |

#### 中国科学院 (3/4 启用)

| source_id | 教师数 | 完整度 | 状态 | 说明 |
|-----------|--------|--------|------|------|
| casia_faculty | 20 | 79.8% | ✅ 优秀 | 自动化所，已配置detail_selectors+heading_sections |
| ict_cas_faculty | 24 | 60.0% | ⚠️ 可接受 | 计算技术研究所，v27 修复 detail_selectors |
| iscas_faculty | 73 | 37.5% | ⚠️ 基础 | 软件研究所，v30 自定义 Parser（纯文本名单+正则提取） |

#### 上海交通大学 (2/5 启用)

| source_id | 教师数 | 完整度 | 状态 | 说明 |
|-----------|--------|--------|------|------|
| sjtu_cs_faculty | 253 | 39.8% | ⚠️ 基础 | 计算机系，AJAX自定义Parser，v29添加detail_selectors(email/label_prefix_sections)，email+name+profile |
| sjtu_infosec_faculty | 80 | 55.0% | ⚠️ 可接受 | 网安学院，含职称和邮箱 |

#### 复旦大学 (1/2 启用)

| source_id | 教师数 | 完整度 | 状态 | 说明 |
|-----------|--------|--------|------|------|
| fudan_cs_faculty | 189 | 45.0% | ⚠️ 可接受 | 计算与智能学院，Playwright AJAX |

#### 南京大学 (5/5 启用)

| source_id | 教师数 | 完整度 | 状态 | 说明 |
|-----------|--------|--------|------|------|
| nju_cs_faculty | 65 | 44.0% | ⚠️ 可接受 | 计算机系，v28 修复 bio 选择器+label_prefix_sections，verify_ssl: false |
| nju_ai_faculty | 36 | 33.0% | ❌ 基础 | 人工智能学院，个人网站结构多样难统一，verify_ssl: false |
| nju_is_faculty | 14 | 49.0% | ⚠️ 可接受 | 智能科学技术学院，v28 修复 bio+research_areas，verify_ssl: false |
| nju_software_faculty | 56 | 47.0% | ⚠️ 可接受 | 软件学院，v28 添加 detail_selectors bio，table 结构 |
| nju_ise_faculty | 15 | 40.0% | ⚠️ 可接受 | 智能软件与工程学院，v29 修复 URL → ise.nju.edu.cn/szll/zjzjs.htm，table tr td 结构，verify_ssl: false |

#### 中国科学技术大学 (3/5 启用)

| source_id | 教师数 | 完整度 | 状态 | 说明 |
|-----------|--------|--------|------|------|
| ustc_cs_faculty | 32 | 45.0% | ⚠️ 可接受 | 计算机学院，v31 URL修复 → js_23235/list.htm + max_pages=2（2→32人） |
| ustc_sist_faculty | 59 | 57.0% | ⚠️ 可接受 | 信息学院→EEIS教师，v31 翻页修复 max_pages=8（8→59人） |
| ustc_cyber_faculty | 59 | 60.0% | ✅ 良好 | 网安学院，v28 添加 label_prefix_sections(职称/邮箱/研究方向) |

#### 浙江大学 (1/3 启用)

| source_id | 教师数 | 完整度 | 状态 | 说明 |
|-----------|--------|--------|------|------|
| zju_cs_faculty | — | — | ❌ 禁用 | 计算机学院，开发环境 ECONNREFUSED（需服务器测试） |
| zju_cyber_faculty | 48 | 44.7% | ⚠️ 可接受 | 网安学院，v31 自定义 Parser（富文本表格解析，页面所有链接指向同一 URL 为网站 bug） |
| zju_soft_faculty | — | — | ❌ 禁用 | 软件学院，开发环境 ECONNREFUSED（需服务器测试） |

#### 中国人民大学 (2/2 启用)

| source_id | 教师数 | 完整度 | 状态 | 说明 |
|-----------|--------|--------|------|------|
| ruc_ai_faculty | 26 | 55.0% | ⚠️ 可接受 | 高瓴人工智能学院，含bio |
| ruc_info_faculty | 20 | 50.0% | ⚠️ 可接受 | 信息学院，v29 修复 JS重定向URL → info.ruc.edu.cn/jsky/szdw/ajxjgcx/bx/bx1/index.htm，div.research 结构 |

### 禁用信源详情（当前仅 3 个真正禁用）

| source_id | 学校 | 原因 | 建议措施 |
|-----------|------|------|---------|
| tsinghua_sigs_faculty | 清华大学 | AJAX+GsapAnimate 前端渲染，静态爬虫无法获取 | 开发自定义 Parser |
| tsinghua_iaiig_faculty | 清华大学 | ERR_CONNECTION_CLOSED，网络不可达 | 待确认域名可访问性 |
| ustc_se_faculty | 中国科学技术大学 | 官网无公开教师列表页 | 暂无可行方案 |

### 待观察信源（已启用但数据量偏少或未验证）

| source_id | 学校 | 状态 | 备注 |
|-----------|------|------|------|
| zju_cs_faculty | 浙江大学 | ❌ 禁用（ECONNREFUSED） | 开发环境不可达，需服务器测试 |
| zju_soft_faculty | 浙江大学 | ❌ 禁用（ECONNREFUSED） | 开发环境不可达，需服务器测试 |
| fudan_ai_robot_faculty | 复旦大学 | ❌ 待启用 | 正确域名/URL 待确认 |
| pku_icst_faculty | 北京大学 | ✅ 已启用，未验证 | 待下次爬取确认数据产出 |
| pku_ic_faculty | 北京大学 | ✅ 已启用，未验证 | 待下次爬取确认数据产出 |
| pku_ss_faculty | 北京大学 | ✅ 已启用，未验证 | 待下次爬取确认数据产出 |
| pku_cfcs_faculty | 北京大学 | ✅ 已启用，未验证 | 待下次爬取确认数据产出 |

### 技术改进

**faculty_crawler.py 增强 (2026-02-28 v28):**
- 新增 `label_prefix_sections`：扫描 `<p>/<li>` 元素，提取"Label：Value"格式字段（适合 ustc_cyber/pku_ic 等中文页面）
- 新增 `list_item` 直选 `<a>` 回退：当 list_item 选择器选中 `<a>` 而非容器元素时，自动提取 get_text()/href（适合 tsinghua_ee 等无 `<li>` 包裹的列表）
- research_areas 详情页提取改用 `separator="\n"`：确保 `<li>` 列表项被换行分隔，parse_research_areas 可正确切割
- heading_sections 扩展支持 `<div>` 标签（之前仅支持 h2/h3/h4/p）

**faculty_crawler.py 增强 (2026-02-27):**
- 支持 `<p>` 标签作为章节标题（之前仅支持 h2/h3/h4）
- 使得更多中文学术网站的非标准HTML结构可被正确解析
- 受益信源：tsinghua_cs_faculty, casia_faculty

**http_client.py SSL 修复 (2026-02-28):**
- `verify=False` 仅跳过证书校验，无法修复 `SSLV3_ALERT_HANDSHAKE_FAILURE`（密码套件不匹配）
- 修复：`verify=False` 时创建 `ssl.SSLContext` 并设置 `SECLEVEL=0` 允许旧密码套件
- 受益信源：nju_cs_faculty, nju_ai_faculty, nju_is_faculty（南大服务器使用老旧TLS）

**sjtu_cs AJAX 自定义 Parser (2026-02-28):**
- SJTU CS 网站不提供静态HTML，通过 POST 到 AJAX 端点返回教师HTML片段
- 创建专用 `SJTUCSFacultyCrawler`（`app/crawlers/parsers/sjtu_cs_faculty.py`）
- 解析 `.name-list span a`，253名教师，耗时 0.5 秒

**ISCAS 纯文本列表自定义 Parser (2026-02-28 v30):**
- ISCAS 页面为无结构或半结构列表（纯文本或无明显 HTML 链接）
- 创建专用 `ISCASFacultyCrawler`（`app/crawlers/parsers/iscas_faculty.py`）
- 尝试多个选择器 (`ul li a`, `div.faculty a`, `p a`)，失败则用正则提取 2-4 字中文名字
- 可选详情页抓取，但当前页面无个人主页链接
- 提取 73 名研究员，耗时 120 秒（含重试 404 URL）

**heading_sections 模式:**
```yaml
detail_selectors:
  heading_sections:
    bio: "个人简历"
    research_areas: "研究方向"
    education: "教育背景"
```

### 下一步工作

1. ~~**修复低数据源**~~ ✅ 2026-02-28 - `ustc_cs_faculty` 已从 2→32 人（20 个源已验证产出数据）
2. **诊断浙大 3 源选择器失效** - zju_cs/cyber/soft 已启用但无数据，待用 Playwright 快照分析 DOM 结构
3. **扩展 USTC SIST** - 当前仅 EEIS 子系第1页(8人)，探索分页或门户子系批量爬取
4. **优化低质量源** - 为 pku_cs/pku_cis/nju 系列添加 detail_selectors 提升完整度（当前 30-38%）
5. ~~**处理 iscas_faculty**~~ ✅ 2026-02-28 - 创建自定义 Parser，成功提取 73 名研究员
6. **服务器环境测试** - 测试上交软件学院/清源等本地超时源（服务器可能可访问）
7. **LLM 富化** - 对已爬取 1928 条教师数据进行学术指标补充（Google Scholar/DBLP）

## 2026-03-01 更新：ISCAS 爬虫优化

### ICT CAS（计算技术研究所）
- **优化内容**：更新faculty detail页面选择器，针对实际页面结构
- **选择器目标**：
  - 基础信息：`dl.fl.w100.swwls_lm_imgtextlist_dl`
  - 简历：`dl.fl.w100.swwls_lm_imgtextlist_dl dd`
  - 研究方向：`div.fl.w100.swwls_ryxl_mod1 p`
- **验证结果**：✅ 成功提取24名研究员

### ISCAS（软件研究所）新增配置

ISCAS的三个列表页面只包含名称，已分别创建source条目：

| Source ID | 列表名称 | URL | 数量 |
|-----------|---------|-----|------|
| iscas_academician | 院士专家 | .../rcdw2016/yszj2016/ | 6 |
| iscas_researcher | 研究员 | .../rcdw2016/yjyzgjgcs2016/ | 60 |
| iscas_associate_researcher | 副研究员 | .../rcdw2016/fyjygjgcs2016/ | 112 |

**爬虫改进**：
1. 支持通过 `faculty_selectors.list_item` 配置列表项选择器
2. 自动分割空格分隔的人名（研究员/副研究员列表）
3. 特殊处理院士名字提取（匹配"XX院士"格式）

**总计**：178名ISCAS师资人员

