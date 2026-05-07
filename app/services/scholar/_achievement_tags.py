"""Normalize paper-venue achievement tags for scholar list/detail responses."""
from __future__ import annotations

import re
from typing import Any

VENUE_ACHIEVEMENT_TAG_OPTIONS: tuple[str, ...] = (
    "JMLR",
    "JAIR",
    "TMLR",
    "ACL",
    "EMNLP",
    "ICLR",
    "ICML",
    "NeurIPS",
    "CVPR",
    "ICCV",
    "ECCV",
    "AAAI",
    "IJCAI",
)

COMPETITION_ACHIEVEMENT_TAG_OPTIONS: tuple[str, ...] = ()

ACHIEVEMENT_TAG_OPTIONS: tuple[str, ...] = (
    *VENUE_ACHIEVEMENT_TAG_OPTIONS,
    *COMPETITION_ACHIEVEMENT_TAG_OPTIONS,
)

_TAG_MATCHERS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "JMLR",
        (
            re.compile(r"\bJMLR\b"),
            re.compile("JOURNAL OF MACHINE LEARNING RESEARCH"),
        ),
    ),
    (
        "JAIR",
        (
            re.compile(r"\bJAIR\b"),
            re.compile("JOURNAL OF ARTIFICIAL INTELLIGENCE RESEARCH"),
        ),
    ),
    (
        "TMLR",
        (
            re.compile(r"\bTMLR\b"),
            re.compile("TRANSACTIONS ON MACHINE LEARNING RESEARCH"),
        ),
    ),
    ("ACL", (re.compile(r"\bACL\b"), re.compile("ASSOCIATION FOR COMPUTATIONAL LINGUISTICS"))),
    (
        "EMNLP",
        (
            re.compile(r"\bEMNLP\b"),
            re.compile("EMPIRICAL METHODS IN NATURAL LANGUAGE PROCESSING"),
        ),
    ),
    (
        "ICLR",
        (
            re.compile(r"\bICLR\b"),
            re.compile("INTERNATIONAL CONFERENCE ON LEARNING REPRESENTATIONS"),
        ),
    ),
    (
        "ICML",
        (re.compile(r"\bICML\b"), re.compile("INTERNATIONAL CONFERENCE ON MACHINE LEARNING")),
    ),
    (
        "NeurIPS",
        (
            re.compile(r"\bNEURIPS\b"),
            re.compile(r"\bNIPS\b"),
            re.compile("NEURAL INFORMATION PROCESSING SYSTEMS"),
        ),
    ),
    ("CVPR", (re.compile(r"\bCVPR\b"), re.compile("COMPUTER VISION AND PATTERN RECOGNITION"))),
    ("ICCV", (re.compile(r"\bICCV\b"), re.compile("INTERNATIONAL CONFERENCE ON COMPUTER VISION"))),
    ("ECCV", (re.compile(r"\bECCV\b"), re.compile("EUROPEAN CONFERENCE ON COMPUTER VISION"))),
    ("AAAI", (re.compile(r"\bAAAI\b"), re.compile("AAAI CONFERENCE ON ARTIFICIAL INTELLIGENCE"))),
    (
        "IJCAI",
        (
            re.compile(r"\bIJCAI\b"),
            re.compile("INTERNATIONAL JOINT CONFERENCE ON ARTIFICIAL INTELLIGENCE"),
        ),
    ),
)

AchievementFilter = tuple[str, int | None]


def _normalize_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("&", " AND ").replace("+", " PLUS ")
    text = re.sub(r"[^A-Za-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().upper()


def _add_matches(text: Any, result: set[str]) -> None:
    normalized = _normalize_text(text)
    if not normalized:
        return
    for tag, patterns in _TAG_MATCHERS:
        if any(pattern.search(normalized) for pattern in patterns):
            result.add(tag)


def _normalize_raw_tag(value: Any) -> str | None:
    result: set[str] = set()
    _add_matches(value, result)
    return next((tag for tag in ACHIEVEMENT_TAG_OPTIONS if tag in result), None)


def _split_filter_values(value: str | list[Any] | tuple[Any, ...] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = value.replace("，", ",").split(",")
    else:
        values = [str(item) for item in value]
    return [item.strip() for item in values if item and item.strip()]


def parse_achievement_filter_tokens(
    value: str | list[Any] | tuple[Any, ...] | None,
) -> list[AchievementFilter]:
    filters: list[AchievementFilter] = []
    for token in _split_filter_values(value):
        tag_text = token
        year: int | None = None
        match = re.match(r"^(.+?)[：:](\d{4})$", token)
        if match:
            tag_text = match.group(1).strip()
            year = int(match.group(2))
        tag = _normalize_raw_tag(tag_text)
        if tag is None:
            continue
        item = (tag, year)
        if item not in filters:
            filters.append(item)
    return filters


def _coerce_year(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def publication_matches_achievement_filters(
    publication: dict[str, Any],
    filters: list[AchievementFilter],
) -> bool:
    venue_text = " ".join(
        str(publication.get(key) or "")
        for key in (
            "venue",
            "conference",
            "journal",
            "venue_name",
            "publication_venue",
            "booktitle",
        )
    )
    publication_tags: set[str] = set()
    _add_matches(venue_text, publication_tags)
    publication_year = _coerce_year(publication.get("year") or publication.get("venue_year"))

    return any(
        tag in publication_tags and (year is None or publication_year == year)
        for tag, year in filters
    )


def extract_achievement_tags(
    *,
    achievement_tags: Any = None,
    representative_publications: list[dict[str, Any]] | None = None,
    awards: list[dict[str, Any]] | None = None,
) -> list[str]:
    result: set[str] = set()

    raw_tags = achievement_tags
    if isinstance(raw_tags, list):
        for raw_tag in raw_tags:
            _add_matches(raw_tag, result)
    elif isinstance(raw_tags, str):
        _add_matches(raw_tags, result)

    for publication in representative_publications or []:
        if not isinstance(publication, dict):
            continue
        _add_matches(
            " ".join(
                str(publication.get(key) or "")
                for key in (
                    "venue",
                    "conference",
                    "journal",
                    "venue_name",
                    "publication_venue",
                    "booktitle",
                )
            ),
            result,
        )

    return [tag for tag in ACHIEVEMENT_TAG_OPTIONS if tag in result]
