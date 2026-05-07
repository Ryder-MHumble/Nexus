"""Rule-based scholar profile classification helpers.

The classifier is intentionally conservative: uncertain cases stay ``None`` so
the UI can show "待判定" instead of over-claiming identity or student status.

⚠️ MAINTENANCE NOTE (2026-04-30)
-------------------------------
The Chinese-name / Chinese-institution / student-role heuristics are the domain
of the **academic-monitor** service (``src/student_paper_crawl/identity/rules.py``).
That file is the authoritative source — it is called by
``/api/identity/enrich-paper`` to populate ``papers.profile_flags``.

This local classifier exists because **scholar table rows don't have OpenReview
profiles** — they carry ``custom_fields.metadata_profile`` instead, so they
need a row-shaped classifier. When you update CHINESE_ORG_HINTS / _STUDENT_RE /
_NON_STUDENT_RE here, also update the mirror in academic-monitor to keep the
two decision surfaces consistent.

See also: ``scripts/sql/20260430_add_paper_author_enrichment_fields.sql``.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

RULE_VERSION = "scholar_profile_rules_v2"

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CJK_ONLY_RE = re.compile(r"[\u4e00-\u9fff]+")
_LATIN_TOKEN_RE = re.compile(r"[a-z]+")

_COMPOUND_CHINESE_SURNAMES = {
    "欧阳", "司马", "上官", "诸葛", "东方", "尉迟", "公孙", "皇甫", "澹台", "令狐",
    "宇文", "长孙", "慕容", "司徒", "司空", "夏侯", "西门", "南宫", "闻人", "万俟",
}

_CHINESE_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄"
    "和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋庞熊纪舒屈项祝董梁杜"
    "阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田胡凌霍虞万"
    "支柯昝管卢莫经房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉龚程嵇邢滑"
    "裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷"
    "车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘斜厉戎祖武符刘景詹束龙叶幸司韶"
    "郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴胥能苍双闻莘党翟谭"
    "贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴"
    "瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广"
    "禄阙东殴殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养"
    "鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
)
_CHINESE_SURNAMES.update(
    "付覃欧区闫"
    "趙錢孫吳鄭馮陳蔣瀋韓楊朱許張華韋馬鳳呂蕭"
    "黃賀湯羅鍾駱闕劉葉龍譚賴喬龔嚴盧藍"
)

_PINYIN_SURNAME_TOKENS = {
    "ai", "an", "ao", "bai", "bao", "bi", "bian", "cai", "cao", "cen", "chang",
    "chao", "che", "chen", "cheng", "chi", "chong", "chu", "cui", "dai", "dan",
    "deng", "di", "ding", "dong", "dou", "du", "duan", "fan", "fang", "fei",
    "feng", "fu", "gan", "gao", "ge", "geng", "gong", "gou", "gu", "guan",
    "guo", "han", "hang", "hao", "he", "heng", "hong", "hou", "hu", "hua",
    "huai", "huang", "ji", "jia", "jian", "jiang", "jin", "jing", "kang",
    "ke", "kong", "kuang", "lai", "lan", "lang", "lao", "lei", "leng", "li",
    "lian", "liang", "liao", "lin", "ling", "liu", "long", "lou", "lu",
    "luan", "luo", "lv", "ma", "mao", "mei", "meng", "mi", "miao", "min", "mo",
    "mu", "na", "nan", "nie", "ning", "niu", "ou", "pan", "pang", "pei",
    "peng", "ping", "pu", "qi", "qian", "qin", "qiu", "qu", "quan", "ran",
    "rao", "ren", "rong", "ruan", "sang", "shao", "shen", "sheng", "shi",
    "shu", "song", "su", "sun", "tan", "tang", "tao", "teng", "tian", "tong",
    "wan", "wang", "wei", "wen", "wu", "xi", "xia", "xiang", "xiao", "xie",
    "xin", "xing", "xiong", "xu", "xuan", "xue", "yan", "yang", "yao", "ye",
    "tu", "yi", "yin", "ying", "you", "yu", "yuan", "zeng", "zha", "zhai", "zhang",
    "zhao", "zheng", "zhi", "zhong", "zhou", "zhu", "zhuang", "zou",
    # Common romanization variants used by Chinese diaspora names.
    "chan", "cheung", "chow", "chuang", "hsu", "ip", "kwok", "lam", "lau", "leung",
    "lee", "ng", "tsang", "wong", "yip",
}

_CHINESE_ORG_HINTS = (
    "中国",
    "北京",
    "上海",
    "清华",
    "北大",
    "浙江大学",
    "复旦",
    "南京大学",
    "中国科学技术大学",
    "哈尔滨工业大学",
    "国防科技大学",
    "中山大学",
    "华中科技大学",
    "武汉大学",
    "西安交通大学",
    "上海交通大学",
    "北京航空航天大学",
    "北京理工大学",
    "电子科技大学",
    "中国科学院",
)

_CHINA_COUNTRIES = {"cn", "china", "pr china", "p.r. china", "中国", "中华人民共和国"}
_NON_CHINA_COUNTRIES = {
    "us",
    "usa",
    "united states",
    "uk",
    "united kingdom",
    "canada",
    "australia",
    "germany",
    "france",
    "italy",
    "japan",
    "korea",
    "south korea",
    "singapore",
    "netherlands",
    "switzerland",
    "sweden",
}

_STUDENT_RE = re.compile(
    r"\b(phd|doctoral|master'?s?|msc|graduate|undergraduate|bachelor'?s?)\s+"
    r"(student|candidate|researcher)\b|"
    r"\b(student|doctoral candidate|phd candidate|graduate assistant)\b|"
    r"博士生|硕士生|研究生|本科生|在读博士|博士研究生|硕士研究生",
    re.IGNORECASE,
)

_NON_STUDENT_RE = re.compile(
    r"教授|副教授|讲师|导师|博导|硕导|研究员|副研究员|助理研究员|工程师|院士|"
    r"\b(professor|faculty|lecturer|scientist|researcher|engineer|director|"
    r"principal investigator|pi|chair|fellow)\b",
    re.IGNORECASE,
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _custom_fields(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("custom_fields")
    return dict(raw) if isinstance(raw, dict) else {}


def _metadata_profile(custom_fields: dict[str, Any]) -> dict[str, Any]:
    raw = custom_fields.get("metadata_profile")
    return dict(raw) if isinstance(raw, dict) else {}


def _profile_flags(custom_fields: dict[str, Any]) -> dict[str, Any]:
    raw = custom_fields.get("profile_flags")
    return dict(raw) if isinstance(raw, dict) else {}


def _explicit_bool(*values: Any) -> bool | None:
    for value in values:
        if isinstance(value, bool):
            return value
    return None


def _has_mainland_student_import(custom_fields: dict[str, Any]) -> bool:
    return isinstance(custom_fields.get("mainland_student_import"), dict)


def _cjk_name_text(value: Any) -> str:
    return "".join(_CJK_ONLY_RE.findall(_clean(value)))


def _has_chinese_surname(name: str) -> bool:
    if not name:
        return False
    if any(name.startswith(surname) for surname in _COMPOUND_CHINESE_SURNAMES):
        return len(name) >= 3
    return name[0] in _CHINESE_SURNAMES and 2 <= len(name) <= 5


def _latin_tokens(value: Any) -> list[str]:
    text = _clean(value).lower().replace("-", " ")
    return _LATIN_TOKEN_RE.findall(text)


def _looks_like_chinese_latin_name(value: Any) -> bool:
    tokens = [token for token in _latin_tokens(value) if len(token) > 1]
    if len(tokens) < 2 or len(tokens) > 5:
        return False
    return tokens[0] in _PINYIN_SURNAME_TOKENS or tokens[-1] in _PINYIN_SURNAME_TOKENS


def _classify_name_identity(row: dict[str, Any]) -> bool | None:
    for key in ("name", "name_en"):
        cjk_name = _cjk_name_text(row.get(key))
        if cjk_name:
            return _has_chinese_surname(cjk_name)

    for key in ("name", "name_en"):
        if _looks_like_chinese_latin_name(row.get(key)):
            return True

    primary_name = _clean(row.get("name")) or _clean(row.get("name_en"))
    if primary_name:
        return False
    return None


def _text_blob(row: dict[str, Any], custom_fields: dict[str, Any]) -> str:
    metadata = _metadata_profile(custom_fields)
    parts: list[str] = [
        _clean(row.get("name")),
        _clean(row.get("name_en")),
        _clean(row.get("university")),
        _clean(row.get("department")),
        _clean(row.get("position")),
        _clean(row.get("bio")),
        _clean(metadata.get("current_institution")),
        _clean(metadata.get("current_department")),
        _clean(custom_fields.get("aaai_plus_org_all")),
        _clean(custom_fields.get("aaai_plus_org_main")),
        _clean(custom_fields.get("aaai_plus_education")),
    ]
    return " ".join(part for part in parts if part)


def _role_text_blob(row: dict[str, Any], custom_fields: dict[str, Any]) -> str:
    metadata = _metadata_profile(custom_fields)
    parts: list[str] = [
        _clean(row.get("position")),
        _clean(metadata.get("current_degree_stage")),
        _clean(metadata.get("current_department")),
    ]
    return " ".join(part for part in parts if part)


def classify_is_chinese(row: dict[str, Any]) -> bool | None:
    custom_fields = _custom_fields(row)
    if _has_mainland_student_import(custom_fields):
        return True

    name_identity = _classify_name_identity(row)
    if name_identity is not None:
        return name_identity

    country = _clean(custom_fields.get("org_country")).lower()
    text = _text_blob(row, custom_fields)

    if country in _CHINA_COUNTRIES:
        return True
    if any(hint in text for hint in _CHINESE_ORG_HINTS):
        return True
    if country in _NON_CHINA_COUNTRIES:
        return False
    return None


def classify_is_current_student(row: dict[str, Any]) -> bool | None:
    custom_fields = _custom_fields(row)
    metadata = _metadata_profile(custom_fields)
    flags = _profile_flags(custom_fields)
    explicit = _explicit_bool(flags.get("is_current_student"), metadata.get("is_current_student"))
    if explicit is not None:
        return explicit
    if _has_mainland_student_import(custom_fields):
        return True
    role_text = _role_text_blob(row, custom_fields)
    if _NON_STUDENT_RE.search(role_text):
        return False
    if _STUDENT_RE.search(role_text):
        return True
    return None


def classify_is_mainland(row: dict[str, Any]) -> bool | None:
    custom_fields = _custom_fields(row)
    metadata = _metadata_profile(custom_fields)
    flags = _profile_flags(custom_fields)
    explicit = _explicit_bool(flags.get("is_mainland"), metadata.get("is_mainland"))
    if explicit is not None:
        return explicit
    if _has_mainland_student_import(custom_fields):
        return True
    country = _clean(custom_fields.get("org_country")).lower()
    if country in _CHINA_COUNTRIES:
        return True
    if country in _NON_CHINA_COUNTRIES:
        return False
    return None


def classify_scholar_profile(row: dict[str, Any]) -> dict[str, Any]:
    """Return merged custom_fields plus classifier output groups."""
    custom_fields = _custom_fields(row)
    metadata = _metadata_profile(custom_fields)
    is_chinese = classify_is_chinese(row)
    is_current_student = classify_is_current_student(row)
    is_mainland = classify_is_mainland(row)
    updated_at = datetime.now(UTC).isoformat()

    profile_flags = {
        "is_chinese": is_chinese,
        "is_current_student": is_current_student,
        "is_mainland": is_mainland,
        "rule_version": RULE_VERSION,
        "updated_at": updated_at,
        "identity_note": (
            "Rule-based classifier; is_chinese is recalculated from name identity signals. "
            "supervised_students linkage is not treated as current student evidence."
        ),
    }
    metadata_profile = {
        **metadata,
        "is_chinese": is_chinese,
        "is_current_student": is_current_student,
        "is_mainland": is_mainland,
        "last_classified_at": updated_at,
        "classifier_rule_version": RULE_VERSION,
    }

    merged_custom_fields = {
        **{k: v for k, v in custom_fields.items() if k != "mainland_student_import"},
        "profile_flags": profile_flags,
        "metadata_profile": metadata_profile,
    }
    return {
        "profile_flags": profile_flags,
        "metadata_profile": metadata_profile,
        "custom_fields": merged_custom_fields,
    }
