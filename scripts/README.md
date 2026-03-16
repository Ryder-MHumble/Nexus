# Scripts 目录说明

## crawl/ — 爬取

| 脚本 | 说明 |
|------|------|
| `run_single.py` | 单源爬虫测试：`python scripts/crawl/run_single.py --source <id>` |
| `run_all.py` | 批量爬虫：`python scripts/crawl/run_all.py` |

## intel/ — 业务智能处理

| 脚本 | 说明 |
|------|------|
| `process_policy.py` | 政策智能：`python scripts/intel/process_policy.py [--dry-run]` |
| `process_personnel.py` | 人事情报：`python scripts/intel/process_personnel.py [--dry-run] [--enrich]` |
| `process_tech_frontier.py` | 科技前沿：`python scripts/intel/process_tech_frontier.py [--dry-run]` |
| `process_university_eco.py` | 高校生态：`python scripts/intel/process_university_eco.py` |

## data/ — 数据构建与导入

| 脚本 | 说明 |
|------|------|
| `generate_index.py` | 生成 data/index.json（前端索引，Pipeline Stage 5 调用） |
| `rebuild_institutions.py` | 重建机构数据：`python scripts/data/rebuild_institutions.py [--dry-run]` |
| `update_institution_categories.py` | 批量更新机构分类/优先级（Supabase） |
| `import_supervised_students.py` | 导入在读/毕业生信息 |
| `import_adjunct_supervisors.py` | 从 Excel 导入兼职导师协议 |
| `redistribute_adjunct_scholars.py` | 重新分配兼职学者到对应院系 |
