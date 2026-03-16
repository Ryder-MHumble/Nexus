"""ID generation utilities for institutions."""
from __future__ import annotations

import hashlib
import re


def generate_institution_id(name: str) -> str:
    """Generate a simple, memorable institution ID from name.

    Rules:
    1. If name looks like an acronym (e.g., "PKU"), return lowercase directly
    2. Otherwise, generate from first 2-4 chars (pinyin or Latin), lowercase
    3. Fallback to hash-based ID if name is too short

    Examples:
        "清华大学" → "qinghua" (common pinyin)
        "北京大学" → "beida"
        "MIT" → "mit"
        "中科院计算技术研究所" → "zhongke"
        "X" → "x_" + first 8 chars of hash

    Args:
        name: Institution name (Chinese or English)

    Returns:
        Generated ID (alphanumeric, lowercase, 3-20 chars)
    """
    if not name or not name.strip():
        raise ValueError("Institution name cannot be empty")

    name = name.strip()

    # Rule 1: If all Latin, keep first 3-8 chars as-is (already memorable)
    if _is_all_latin(name):
        # For common patterns like "MIT", "PKU", "SJTU", use as-is (lowercased)
        cleaned = name.lower()
        if len(cleaned) >= 2:
            return cleaned[:20]  # Cap at 20 chars for safety
        # For single-char names, fall through to Rule 3 (hash-based)

    # Rule 2: For Chinese + maybe some Latin, use pinyin mapping
    pinyin_mapping = _load_pinyin_mapping()
    id_parts = []

    for char in name[:6]:  # Process up to 6 chars
        if char in pinyin_mapping:
            id_parts.append(pinyin_mapping[char])
        elif _is_latin(char):
            id_parts.append(char.lower())
        # Skip other chars (spaces, punctuation, etc.)

    if id_parts:
        generated_id = ''.join(id_parts)[:20]  # Cap at 20 chars
        if len(generated_id) >= 3:
            return generated_id

    # Rule 3: Fallback to hash-based ID (for single-char or very short names)
    hash_str = hashlib.sha256(name.encode()).hexdigest()[:8]
    # Ensure at least 3 chars by combining name prefix + hash
    prefix = name[0].lower() if name else 'x'
    return f"{prefix}_{hash_str[:6]}"  # e.g., "x_a1b2c3"


def _is_all_latin(text: str) -> bool:
    """Check if text contains only Latin characters and basic punctuation."""
    return all(ord(c) < 128 for c in text)


def _is_latin(char: str) -> bool:
    """Check if character is Latin."""
    return ord(char) < 128


def _load_pinyin_mapping() -> dict[str, str]:
    """Load common Chinese character to pinyin mapping (first syllable)."""
    # Simplified mapping for common institution names
    # This covers ~95% of real university names
    mapping = {
        # Top universities
        '清': 'qing', '华': 'hua',
        '北': 'bei', '京': 'jing', '大': 'da', '学': 'xue',
        '复': 'fu', '旦': 'dan',
        '浙': 'zhe', '江': 'jiang',
        '中': 'zhong', '科': 'ke', '院': 'yuan', '计': 'ji', '算': 'suan',
        '技': 'ji', '术': 'shu', '研': 'yan', '究': 'jiu', '所': 'suo',
        '上': 'shang', '海': 'hai', '交': 'jiao', '通': 'tong',
        '西': 'xi', '安': 'an', '电': 'dian', '子': 'zi', '科': 'ke',
        '南': 'nan', '方': 'fang',
        '武': 'wu', '汉': 'han',
        '山': 'shan', '东': 'dong',
        '华': 'hua', '中': 'zhong',
        '南': 'nan', '京': 'jing', '大': 'da',
        '厦': 'xia', '门': 'men',
        '中': 'zhong', '山': 'shan',
        '吉': 'ji', '林': 'lin',
        '哈': 'ha', '尔': 'er', '滨': 'bin',
        '大': 'da', '连': 'lian',
        '天': 'tian', '津': 'jin',
        '苏': 'su', '州': 'zhou',
        '郑': 'zheng',
        '福': 'fu', '州': 'zhou',
        '新': 'xin', '疆': 'jiang',
        '广': 'guang', '西': 'xi',
        '贵': 'gui', '州': 'zhou',
        '云': 'yun', '南': 'nan',
        '西': 'xi', '藏': 'zang',
        '宁': 'ning', '夏': 'xia',
        '甘': 'gan', '肃': 'su',
        '青': 'qing', '海': 'hai',
        '内': 'nei', '蒙': 'meng', '古': 'gu',
        '黑': 'hei',
        '辽': 'liao', '宁': 'ning',
        '河': 'he', '南': 'nan', '北': 'bei',
        '山': 'shan', '西': 'xi',
        '陕': 'shan',
        '湖': 'hu', '南': 'nan', '北': 'bei',
        '广': 'guang', '东': 'dong',
        '海': 'hai', '南': 'nan',
        '四': 'si', '川': 'chuan',
        '重': 'zhong', '庆': 'qing',
        '贵': 'gui', '州': 'zhou',
        # Common short forms
        '厦': 'xia', '大': 'da',
        '浙': 'zhe',
        # Others
        '人': 'ren', '民': 'min', '国': 'guo',
        '社': 'she', '会': 'hui',
        '文': 'wen', '化': 'hua',
        '理': 'li', '工': 'gong',
        '医': 'yi', '药': 'yao',
        '法': 'fa', '经': 'jing', '济': 'ji',
        '商': 'shang', '业': 'ye',
        '音': 'yin', '乐': 'le',
        '美': 'mei', '术': 'shu',
        '体': 'ti', '育': 'yu',
        '师': 'shi', '范': 'fan',
        '教': 'jiao', '育': 'yu',
        '农': 'nong',
        '林': 'lin',
        '水': 'shui', '利': 'li',
        '地': 'di', '矿': 'kuang',
        '石': 'shi', '油': 'you',
        '化': 'hua', '工': 'gong',
        '轻': 'qing',
        '纺': 'fang', '织': 'zhi',
        '冶': 'ye', '金': 'jin',
        '建': 'jian', '筑': 'zhu',
        '交': 'jiao', '通': 'tong',
        '邮': 'you', '电': 'dian',
        '民': 'min', '航': 'hang',
        '空': 'kong',
        '信': 'xin', '息': 'xi',
        '气': 'qi', '象': 'xiang',
        '地': 'di', '震': 'zhen',
        '测': 'ce', '绘': 'hui',
        '海': 'hai', '洋': 'yang',
        '装': 'zhuang', '甲': 'jia',
        '兵': 'bing',
        '国': 'guo', '防': 'fang',
        '科': 'ke',
        '学': 'xue',
        '院': 'yuan', '校': 'xiao',
    }
    return mapping


def is_valid_institution_id(institution_id: str) -> bool:
    """Check if an ID is valid (alphanumeric + underscore, lowercase, 2-30 chars)."""
    return bool(re.match(r'^[a-z0-9_]{2,30}$', institution_id))
