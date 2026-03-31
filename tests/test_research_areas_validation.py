from app.schemas.scholar import validate_research_areas, validate_scholar_name

# ---------------------------------------------------------------------------
# validate_research_areas tests
# ---------------------------------------------------------------------------


def test_nav_menu_pollution_detected():
    """导航菜单条目应被整体清空"""
    nav_items = [
        "首页", "关于我们", "中心简介", "行政团队", "中心动态",
        "访问指南", "数学学人", "领军学者", "专业委员会", "中心教师",
        "博士后", "来访学者", "清华学者库", "人才培养", "国内博士招生",
        "海外博士招生", "暑期学校", "中学夏令营", "在读研究生", "学生动态",
    ]
    assert validate_research_areas(nav_items) == []


def test_too_many_items_detected():
    """超过 15 个条目视为污染"""
    many_items = [f"方向{i}" for i in range(16)]
    assert validate_research_areas(many_items) == []


def test_avg_length_too_short_detected():
    """平均字符数 < 3 视为污染"""
    short_items = ["A", "B", "C", "D"]
    assert validate_research_areas(short_items) == []


def test_valid_research_areas_pass():
    """正常研究方向不受影响"""
    valid = ["机器学习", "计算机视觉", "自然语言处理"]
    assert validate_research_areas(valid) == valid


def test_empty_list_passes():
    assert validate_research_areas([]) == []


def test_single_valid_item_passes():
    assert validate_research_areas(["深度学习"]) == ["深度学习"]


def test_exactly_15_items_passes():
    """恰好 15 个条目应通过"""
    items = [f"研究方向{i}" for i in range(15)]
    assert validate_research_areas(items) == items


def test_mixed_valid_with_one_nav_keyword():
    """只要有一个导航词就整体清空"""
    mixed = ["机器学习", "首页", "计算机视觉"]
    assert validate_research_areas(mixed) == []


# --- New: footer/address detection (Rule 4, 5) ---


def test_footer_copyright_detected():
    """含 CopyRight 的页脚文本应被拒绝"""
    footer = [
        "安徽省合肥市黄山路中国科学技术大学西区电三楼通信地址：安徽省合肥市４号信箱"
        " 计算机科学与技术学院 邮政编码：230027CopyRight  2009-2022"
        " 中国科学技术大学计算机科学与技术学院 All Rights Reserved."
    ]
    assert validate_research_areas(footer) == []


def test_footer_chinese_copyright_detected():
    """含"版权所有"的文本应被拒绝"""
    footer = [
        "版权所有 © 复旦大学计算与智能创新学院"
    ]
    assert validate_research_areas(footer) == []


def test_address_pattern_detected():
    """含邮政编码模式的文本应被拒绝"""
    addr = [
        "江苏省南京市栖霞区仙林大道163号 计算机科学技术楼邮编：210023 电话"
    ]
    assert validate_research_areas(addr) == []


def test_icp_pattern_detected():
    """含 ICP备 的文本应被拒绝"""
    icp = ["京ICP备12345678号"]
    assert validate_research_areas(icp) == []


# --- New: single item too long (Rule 6) ---


def test_single_item_too_long_rejected():
    """单项超过 100 字符应被拒绝"""
    long_item = ["A" * 101]
    assert validate_research_areas(long_item) == []


def test_single_item_exactly_100_passes():
    """单项恰好 100 字符应通过"""
    item_100 = ["A" * 100]
    assert validate_research_areas(item_100) == item_100


# --- New: work experience pattern (Rule 7) ---


def test_work_experience_pattern_rejected():
    """含工作经历年份模式的列表应被拒绝"""
    work_exp = [
        "2018年10月 — 今：中国科学院计算技术研究所 正高级工程师",
        "2012年10月 — 2018年9月：中国科学院计算技术研究所 副研究员",
        "2010年 6月 — 2012年9月：中国科学院计算技术研究所 助理研究员",
    ]
    assert validate_research_areas(work_exp) == []


def test_work_experience_mixed_with_valid_rejected():
    """即使只有一项含工作经历模式也应被拒绝"""
    mixed = [
        "机器学习",
        "计算机视觉",
        "2018年10月 — 今：某研究所 研究员",
    ]
    assert validate_research_areas(mixed) == []


def test_work_experience_majority_rejected():
    """工作经历占半数及以上时应被拒绝"""
    mostly_work = [
        "2018年—今：某研究所 教授",
        "2010年-2018年：某大学 副教授",
    ]
    assert validate_research_areas(mostly_work) == []


# ---------------------------------------------------------------------------
# validate_scholar_name tests
# ---------------------------------------------------------------------------


def test_valid_chinese_name():
    assert validate_scholar_name("张三") is True


def test_valid_english_name():
    assert validate_scholar_name("John Smith") is True


def test_valid_chinese_name_compound():
    assert validate_scholar_name("Nicola D'Ascenzo") is True


def test_nav_keyword_rejected():
    assert validate_scholar_name("首页") is False
    assert validate_scholar_name("English") is False
    assert validate_scholar_name("人才招聘") is False


def test_portal_keyword_rejected():
    assert validate_scholar_name("北大邮箱") is False
    assert validate_scholar_name("深研院邮箱") is False
    assert validate_scholar_name("网上办公") is False
    assert validate_scholar_name("南燕门户") is False
    assert validate_scholar_name("捐赠") is False


def test_section_name_rejected():
    assert validate_scholar_name("学院导航") is False
    assert validate_scholar_name("招生培养") is False
    assert validate_scholar_name("师资队伍") is False
    assert validate_scholar_name("科学研究") is False


def test_empty_rejected():
    assert validate_scholar_name("") is False
    assert validate_scholar_name("  ") is False


def test_single_char_rejected():
    assert validate_scholar_name("A") is False
    assert validate_scholar_name("张") is False


def test_too_long_chinese_rejected():
    assert validate_scholar_name("张" * 21) is False


def test_url_pattern_rejected():
    assert validate_scholar_name("https://example.com") is False


def test_email_pattern_rejected():
    assert validate_scholar_name("user@example.com") is False


def test_copyright_symbol_rejected():
    assert validate_scholar_name("© 2024") is False


def test_digits_rejected():
    assert validate_scholar_name("12345") is False
