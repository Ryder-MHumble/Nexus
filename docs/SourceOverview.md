# 信源全景概览 — SourceOverview

> 最后更新: 2026-03-06 | 系统版本: v39

---

## 一、汇总统计

| 指标 | 数值 |
|------|------|
| 信源总数 | 181 |
| 启用信源 | 138 |
| 禁用信源 | 43 |
| 信息监测维度 | 9（国家政策/北京政策/技术动态/人才/产业/高校/活动/人事/舆情） |
| 学者知识库维度 | 1（49 个采集源，覆盖 9 所高校） |

### 爬虫类型分布

| 爬虫类型 | 数量 | 说明 |
|---------|------|------|
| static（httpx + BS4） | ~85 | 服务端渲染页面，CSS 选择器提取 |
| dynamic（Playwright） | ~22 | JS 渲染页面，浏览器自动化 |
| rss（feedparser） | ~10 | RSS/Atom 订阅源 |
| 自定义 Parser | ~17 | API/特殊格式（arxiv/github/twitter 等） |
| scholar/faculty | ~47 | 高校师资专用爬虫（含 LLM 自适应） |

---

## 二、信息监测维度（9 维度）

### 2.1 国家政策（8 源，6 启用）

| source_id | 信源名称 | 爬虫类型 | 调度频率 | 启用 |
|-----------|---------|---------|---------|:----:|
| gov_cn_zhengce | 中国政府网-最新政策 | dynamic | 2h | ✅ |
| ndrc_policy | 国家发改委-通知公告 | static | 4h | ✅ |
| moe_policy | 教育部-政策法规 | static | 4h | ✅ |
| most_policy | 科技部-信息公开 | static | 4h | ✅ |
| cac_policy | 国家网信办-政策法规 | static | 4h | ❌ |
| samr_news | 国家市监总局-要闻 | static | daily | ❌ |
| miit_policy | 工信部-政策文件 | dynamic | daily | ✅ |
| nsfc_news | 国家自然科学基金委-通知公告 | static | daily | ❌ |

### 2.2 北京政策（14 源，10 启用）

| source_id | 信源名称 | 爬虫类型 | 调度频率 | 启用 |
|-----------|---------|---------|---------|:----:|
| beijing_zhengce | 首都之窗-政策文件 | static | 4h | ✅ |
| bjkw_policy | 北京市科委/中关村管委会 | static | 4h | ✅ |
| bjjw_policy | 北京市教委 | static | daily | ✅ |
| bjrsj_policy | 北京市人社局 | static | daily | ✅ |
| zgc_policy | 中关村示范区 | static | daily | ❌ |
| ncsti_policy | 国际科创中心 | static | daily | ✅ |
| bjjxj_policy | 北京市经信局-通知公告 | static | 4h | ✅ |
| bjzscqj_policy | 北京市知识产权局 | static | daily | ✅ |
| bjfgw_policy | 北京市发改委-政策文件 | static | daily | ✅ |
| bjhd_policy | 海淀区政府 | static | daily | ❌ |
| beijing_ywdt | 首都之窗-要闻 | static | 4h | ✅ |
| bjd_news | 北京日报 | static | daily | ❌ |
| bjrd_renshi | 北京市人大常委会 | static | daily | ✅ |
| beijing_rsrm | 首都之窗-人事任免 | static | daily | ❌ |

### 2.3 技术动态（34 源，33 启用）

| source_id | 信源名称 | 爬虫类型 | 调度频率 | 启用 |
|-----------|---------|---------|---------|:----:|
| 36kr_ai_rss | 36氪-AI频道 | rss | 2h | ✅ |
| techcrunch_ai_rss | TechCrunch AI | rss | 2h | ✅ |
| theverge_ai_rss | The Verge AI | rss | 4h | ✅ |
| mit_tech_review_rss | MIT Technology Review | rss | daily | ✅ |
| venturebeat_ai_rss | VentureBeat AI | rss | 4h | ✅ |
| ieee_spectrum_ai_rss | IEEE Spectrum AI | rss | daily | ✅ |
| wired_ai_rss | Wired AI | rss | daily | ✅ |
| arstechnica_ai_rss | Ars Technica AI | rss | daily | ✅ |
| openai_blog | OpenAI Blog | rss | daily | ✅ |
| anthropic_blog | Anthropic News | static | daily | ✅ |
| google_deepmind_blog | Google DeepMind Blog | dynamic | daily | ✅ |
| meta_ai_blog | Meta AI Blog | static | daily | ✅ |
| microsoft_ai_blog | Microsoft AI Blog | rss | daily | ✅ |
| mistral_ai_news | Mistral AI News | static | daily | ✅ |
| xai_blog | xAI Blog (Grok) | dynamic | daily | ❌ |
| stability_ai_news | Stability AI News | static | daily | ✅ |
| huggingface_blog | Hugging Face Blog | static | daily | ✅ |
| arxiv_cs_ai | ArXiv cs.AI | arxiv_api | daily | ✅ |
| arxiv_cs_lg | ArXiv cs.LG（机器学习） | arxiv_api | daily | ✅ |
| arxiv_cs_cl | ArXiv cs.CL（NLP/大模型） | arxiv_api | daily | ✅ |
| hacker_news | Hacker News | hacker_news_api | 2h | ✅ |
| reddit_ml_rss | Reddit r/MachineLearning | rss | 4h | ✅ |
| github_trending | GitHub Trending | github_api | daily | ✅ |
| qwen_blog | Qwen Blog（阿里通义千问） | static | daily | ✅ |
| minimax_news | MiniMax 新闻动态 | dynamic | daily | ✅ |
| moonshot_research | 月之暗面-最新研究 | dynamic | daily | ✅ |
| hunyuan_news | 腾讯混元-最新动态 | hunyuan_api | daily | ✅ |
| zhipu_news | 智谱AI-最新动态 | dynamic | daily | ❌ |
| jiqizhixin_rss | 机器之心 | rss | 2h | ❌ |
| reddit_localllama_rss | Reddit r/LocalLLaMA | rss | 4h | ❌ |
| cohere_blog | Cohere Blog | static | daily | ❌ |
| runway_blog | Runway Blog | dynamic | weekly | ❌ |
| inflection_ai_blog | Inflection AI Blog | static | weekly | ❌ |

> 注：共 34 源（实际启用 33，jiqizhixin_rss 等已禁用）

### 2.4 人才发展（7 源，4 启用）

| source_id | 信源名称 | 爬虫类型 | 调度频率 | 启用 |
|-----------|---------|---------|---------|:----:|
| semantic_scholar_ai | Semantic Scholar-AI 论文 | semantic_scholar | weekly | ✅ |
| moe_talent | 教育部人才计划公示 | static | daily | ✅ |
| nature_index | Nature Index | static | monthly | ✅ |
| wrsa_talent | 欧美同学会 | static | monthly | ✅ |
| csrankings | CSRankings | static | monthly | ❌ |
| nsfc_talent | NSFC 杰青/优青公示 | static | daily | ❌ |
| aminer_ai | AMiner-AI 学者 | static | weekly | ❌ |

### 2.5 产业趋势（10 源，6 启用）

| source_id | 信源名称 | 爬虫类型 | 调度频率 | 启用 |
|-----------|---------|---------|---------|:----:|
| 36kr_news | 36氪-快讯 | static | 2h | ✅ |
| tmtpost_news | 钛媒体 | rss | 4h | ✅ |
| jiemian_tech | 界面新闻-科技 | static | daily | ✅ |
| cyzone_news | 创业邦 | static | 4h | ✅ |
| chinaventure_news | 投中网 | static | daily | ✅ |
| 36kr_investment | 36氪-融资频道 | static | daily | ✅ |
| huxiu_news | 虎嗅 | static | 4h | ❌ |
| thepaper_tech | 澎湃新闻-科技 | static | daily | ❌ |
| iyiou_ai | 亿欧-AI | static | daily | ❌ |
| caict_news | 中国信通院-动态 | static | daily | ❌ |

### 2.6 高校动态（55 源，46 启用）

**高校新闻（universities-news）**

| source_id | 信源名称 | 爬虫类型 | 调度频率 | 启用 |
|-----------|---------|---------|---------|:----:|
| tsinghua_news | 清华大学新闻网 | static | daily | ✅ |
| pku_news | 北京大学新闻网 | dynamic | daily | ✅ |
| ustc_news | 中国科大新闻网 | static | daily | ✅ |
| sjtu_news | 上海交大新闻网 | static | daily | ✅ |
| fudan_news | 复旦大学新闻网 | static | daily | ✅ |
| ruc_news | 中国人民大学新闻网 | dynamic | daily | ✅ |
| hit_news | 哈尔滨工业大学新闻网 | static | daily | ✅ |
| seu_news | 东南大学新闻网 | static | daily | ✅ |
| sysu_news | 中山大学新闻网 | dynamic | daily | ✅ |
| sustech_news | 南方科技大学新闻网 | static | daily | ✅ |
| xjtu_news | 西安交通大学新闻网 | static | daily | ✅ |
| uestc_news | 电子科技大学新闻网 | static | daily | ✅ |
| whu_news | 武汉大学新闻网 | static | daily | ✅ |
| hust_news | 华中科技大学新闻网 | static | daily | ✅ |
| tju_news | 天津大学新闻网 | static | daily | ✅ |
| tongji_news | 同济大学新闻网 | static | daily | ✅ |
| jlu_news | 吉林大学新闻网 | static | daily | ✅ |
| xmu_news | 厦门大学新闻网 | static | daily | ✅ |
| sdu_news | 山东大学新闻网 | static | daily | ✅ |
| csu_news | 中南大学新闻网 | static | daily | ✅ |
| xidian_news | 西安电子科技大学新闻网 | static | daily | ✅ |
| bnu_news | 北京师范大学新闻网 | static | daily | ✅ |
| bit_news | 北京理工大学新闻网 | static | daily | ✅ |
| buaa_news | 北京航空航天大学新闻网 | static | daily | ✅ |
| nudt_news | 国防科技大学-科大要闻 | static | daily | ✅ |
| zju_news | 浙江大学新闻网 | static | daily | ❌ |
| nju_news | 南京大学新闻网 | static | daily | ❌ |
| bupt_news | 北京邮电大学新闻网 | dynamic | daily | ❌ |
| nankai_news | 南开大学新闻网 | dynamic | daily | ❌ |
| nwpu_news | 西北工业大学新闻网 | dynamic | daily | ❌ |
| scu_news | 四川大学新闻网 | dynamic | daily | ❌ |
| lzu_news | 兰州大学新闻网 | dynamic | daily | ❌ |

**AI 研究机构（universities-ai-institutes）**

| source_id | 信源名称 | 爬虫类型 | 调度频率 | 启用 |
|-----------|---------|---------|---------|:----:|
| baai_news | 北京智源人工智能研究院(BAAI) | dynamic | daily | ✅ |
| tsinghua_air | 清华大学智能产业研究院(AIR) | static | daily | ✅ |
| shlab_news | 上海人工智能实验室 | dynamic | daily | ✅ |
| pcl_news | 鹏城实验室 | static | daily | ✅ |
| ia_cas_news | 中科院自动化所 | static | daily | ✅ |
| ict_cas_news | 中科院计算所 | static | daily | ✅ |
| sii_news | 上海创智学院 | static | daily | ✅ |
| slai_news | 深圳河套学院-学院动态 | static | daily | ✅ |
| iie_cas_news | 中科院信工所 | static | daily | ✅ |
| zhejianglab_news | 之江实验室 | dynamic | daily | ❌ |
| cesi_news | 中国电子标准化研究院 | static | daily | ❌ |

**获奖与评选（universities-awards）**

| source_id | 信源名称 | 爬虫类型 | 调度频率 | 启用 |
|-----------|---------|---------|---------|:----:|
| cas_news | 中国科学院 | static | monthly | ✅ |
| cae_news | 中国工程院 | static | monthly | ✅ |
| nosta_news | 国家科技奖励办 | dynamic | monthly | ✅ |
| moe_keji | 教育部科技司 | static | monthly | ✅ |

**区域教育厅（universities-provinces）**

| source_id | 信源名称 | 爬虫类型 | 调度频率 | 启用 |
|-----------|---------|---------|---------|:----:|
| beijing_jw | 北京市教委 | static | daily | ✅ |
| shanghai_jw | 上海市教委 | static | daily | ✅ |
| zhejiang_jyt | 浙江省教育厅 | static | daily | ✅ |
| jiangsu_jyt | 江苏省教育厅 | static | daily | ✅ |
| guangdong_jyt | 广东省教育厅 | static | daily | ✅ |

**聚合媒体（universities-aggregators）**

| source_id | 信源名称 | 爬虫类型 | 调度频率 | 启用 |
|-----------|---------|---------|---------|:----:|
| eol_news | 中国教育在线 | static | daily | ✅ |
| jyb_news | 中国教育报 | static | daily | ✅ |
| shanghairanking_news | 软科(Shanghai Ranking) | static | daily | ❌ |

### 2.7 活动日程（6 源，4 启用）

| source_id | 信源名称 | 爬虫类型 | 调度频率 | 启用 |
|-----------|---------|---------|---------|:----:|
| aideadlines | AI Conference Deadlines | dynamic | weekly | ✅ |
| wikicfp | WikiCFP-AI | static | weekly | ✅ |
| caai_news | CAAI 学会新闻 | static | daily | ✅ |
| ccf_focus | CCF 聚焦 | static | daily | ✅ |
| huodongxing | 活动行-人工智能 | static | weekly | ❌ |
| meeting_edu | 中国学术会议在线 | static | weekly | ❌ |

### 2.8 人事变动（4 源，4 启用）

| source_id | 信源名称 | 爬虫类型 | 调度频率 | 启用 |
|-----------|---------|---------|---------|:----:|
| mohrss_rsrm | 人社部-国务院人事任免 | dynamic | daily | ✅ |
| moe_renshi | 教育部-人事任免 | static | daily | ✅ |
| cas_renshi | 中科院-人事任免 | static | daily | ✅ |
| moe_renshi_si | 教育部-人事司公告 | static | daily | ✅ |

### 2.9 社交舆情 Twitter（7 源，7 启用）

| source_id | 信源名称 | 爬虫类型 | 调度频率 | 启用 |
|-----------|---------|---------|---------|:----:|
| twitter_ai_kol_international | Twitter AI KOL（国际） | twitter_kol | 4h | ✅ |
| twitter_ai_kol_chinese | Twitter AI KOL（华人） | twitter_kol | 4h | ✅ |
| twitter_ai_breakthrough | Twitter AI 突破性进展 | twitter_search | 4h | ✅ |
| twitter_ai_papers | Twitter AI 论文讨论 | twitter_search | daily | ✅ |
| twitter_ai_industry | Twitter AI 产业动态 | twitter_search | 4h | ✅ |
| twitter_ai_talent | Twitter AI 人才动态 | twitter_search | daily | ✅ |
| twitter_zgci_sentiment | Twitter 学院舆情监控 | twitter_search | 4h | ✅ |

> 注：需配置 Twitter API key（TWITTER_BEARER_TOKEN）

---

## 三、学者知识库维度（49 源）

所有学者采集源调度频率均为 `weekly`，当前状态为数据积累完成后按需重爬（is_enabled 视同 false）。

### 清华大学（13 源）

| source_id | 所属院系 | 爬虫类型 |
|-----------|---------|---------|
| tsinghua_cs_faculty | 计算机系 | faculty（LLM） |
| tsinghua_air_faculty | 智能产业研究院 AIR | faculty（LLM） |
| tsinghua_iiis_faculty | 交叉信息研究院 | faculty（LLM） |
| tsinghua_se_faculty | 软件学院 | faculty（LLM） |
| tsinghua_ee_faculty | 电子工程系 | faculty（LLM） |
| tsinghua_au_faculty | 自动化系 | faculty（LLM） |
| tsinghua_insc_faculty | 网络研究院 | faculty（LLM） |
| tsinghua_ias_faculty | 高等研究院 | faculty（LLM） |
| tsinghua_futurelab_faculty | 未来实验室 | faculty（LLM） |
| tsinghua_ymsc_faculty | 丘成桐数学科学中心 | ymsc_scholar |
| tsinghua_life_faculty | 生命科学学院 | faculty（LLM） |
| tsinghua_sigs_faculty | 深圳国际研究生院 | faculty（LLM） |
| tsinghua_iaiig_faculty | 人工智能国际治理研究院 | faculty（LLM） |

### 北京大学（9 源）

| source_id | 所属院系 | 爬虫类型 |
|-----------|---------|---------|
| pku_cs_faculty | 计算机学院 | faculty（LLM） |
| pku_cis_faculty | 智能学院 | faculty（LLM） |
| pku_icst_faculty | 王选计算机研究所 | faculty（LLM） |
| pku_ic_faculty | 集成电路学院 | faculty（LLM） |
| pku_ss_faculty | 软件与微电子学院 | faculty（LLM） |
| pku_cfcs_faculty | 前沿计算研究中心 | faculty（LLM） |
| pku_math_faculty | 数学学院 | faculty（LLM） |
| pku_eecs_sz_faculty | 信息工程学院（深圳） | faculty（LLM） |
| pku_coe_faculty | 工学院 | faculty（LLM） |

### 上海交通大学（5 源）

| source_id | 所属院系 | 爬虫类型 |
|-----------|---------|---------|
| sjtu_ai_faculty | 人工智能研究院 | sjtu_ai_scholar |
| sjtu_cs_faculty | 计算机系 | sjtu_cs_scholar |
| sjtu_se_faculty | 软件学院 | faculty（LLM） |
| sjtu_infosec_faculty | 网络空间安全学院 | faculty（LLM） |
| sjtu_qingyuan_faculty | 清源研究院 | faculty（LLM） |

### 中国科学院（5 源）

| source_id | 所属单位 | 爬虫类型 |
|-----------|---------|---------|
| ict_cas_faculty | 计算技术研究所 | faculty（LLM） |
| casia_faculty | 自动化研究所 | faculty（LLM） |
| iscas_academician | 软件研究所-院士 | iscas_scholar |
| iscas_researcher | 软件研究所-研究员 | iscas_scholar |
| iscas_associate_researcher | 软件研究所-副研究员 | iscas_scholar |

### 浙江大学（3 源）

| source_id | 所属院系 | 爬虫类型 |
|-----------|---------|---------|
| zju_cs_faculty | 计算机学院 | faculty（LLM） |
| zju_cyber_faculty | 网络空间安全学院 | zju_cyber_scholar |
| zju_soft_faculty | 软件学院 | faculty（LLM） |

### 南京大学（5 源）

| source_id | 所属院系 | 爬虫类型 |
|-----------|---------|---------|
| nju_cs_faculty | 计算机系 | faculty（LLM） |
| nju_ai_faculty | 人工智能学院 | faculty（LLM） |
| nju_software_faculty | 软件学院 | faculty（LLM） |
| nju_is_faculty | 智能科学与技术学院 | faculty（LLM） |
| nju_ise_faculty | 智能软件与工程学院 | faculty（LLM） |

### 中国科学技术大学（5 源）

| source_id | 所属院系 | 爬虫类型 |
|-----------|---------|---------|
| ustc_cs_faculty | 计算机学院 | faculty（LLM） |
| ustc_sist_faculty | 信息科学技术学院 | faculty（LLM） |
| ustc_se_faculty | 软件学院 | faculty（LLM） |
| ustc_ds_faculty | 大数据学院 | faculty（LLM） |
| ustc_cyber_faculty | 网络空间安全学院 | faculty（LLM） |

### 复旦大学（2 源）

| source_id | 所属院系 | 爬虫类型 |
|-----------|---------|---------|
| fudan_cs_faculty | 计算与智能创新学院 | faculty（LLM） |
| fudan_ai_robot_faculty | 智能机器人与先进制造创新学院 | faculty（LLM） |

### 中国人民大学（2 源）

| source_id | 所属院系 | 爬虫类型 |
|-----------|---------|---------|
| ruc_info_faculty | 信息学院 | faculty（LLM） |
| ruc_ai_faculty | 高瓴人工智能学院 | faculty（LLM） |

---

## 四、自定义 Parser 列表（16 个）

| Parser 名称 | crawler_class | 适用场景 | 信源示例 |
|------------|---------------|---------|---------|
| gov_json_api | gov_json_api | 政府 JSON API 格式 | ndrc_policy |
| arxiv_api | arxiv_api | arXiv 学术论文 API | arxiv_cs_ai/lg/cl |
| github_api | github_api | GitHub Trending API | github_trending |
| hacker_news_api | hacker_news_api | Hacker News 热帖 | hacker_news |
| semantic_scholar | semantic_scholar | Semantic Scholar 论文数据库 | semantic_scholar_ai |
| twitter_kol | twitter_kol | Twitter KOL 时间线 | twitter_ai_kol_* |
| twitter_search | twitter_search | Twitter 关键词搜索 | twitter_ai_breakthrough |
| hunyuan_api | hunyuan_api | 腾讯混元新闻 API | hunyuan_news |
| llm_faculty | llm_faculty | LLM 自适应学者爬虫（通用） | 大多数 faculty 源 |
| sjtu_cs_scholar | sjtu_cs_scholar | 上交大计算机系定制 | sjtu_cs_faculty |
| sjtu_ai_scholar | sjtu_ai_scholar | 上交大 AI 研究院定制 | sjtu_ai_faculty |
| tsinghua_cs_scholar | tsinghua_cs_scholar | 清华计算机系定制 | tsinghua_cs_faculty |
| iscas_scholar | iscas_scholar | 中科院软件所定制 | iscas_* |
| zju_cyber_scholar | zju_cyber_scholar | 浙大网安学院定制 | zju_cyber_faculty |
| ymsc_scholar | ymsc_scholar | 清华丘成桐数学中心定制 | tsinghua_ymsc_faculty |
| paper_transfer | paper_transfer | 学术论文转化分析 | （内部） |

---

## 五、禁用信源说明

以下 43 个信源当前处于禁用状态（is_enabled: false）：

| 维度 | 禁用数量 | 主要禁用原因 |
|------|---------|------------|
| 国家政策 | 2 | 网站结构变更、信息价值低 |
| 北京政策 | 4 | 选择器失效、重复来源 |
| 技术动态 | 5 | API 限制、内容质量问题 |
| 人才发展 | 3 | 更新频率低、需专项账号 |
| 产业趋势 | 4 | 网站改版、需认证 |
| 高校动态 | 11 | 网站动态渲染问题、选择器待修复 |
| 活动日程 | 2 | 数据不稳定 |
| 学者知识库 | 49 | 初次全量爬取已完成，按需触发模式 |

> 修复禁用信源：先用 Playwright MCP 分析页面结构 → 修改 YAML 选择器 → `python scripts/run_single_crawl.py --source <id>` 验证 → 重新启用

---

*本文档由 `/docs/SourceOverview.md` 维护，修改信源配置后同步更新。*
