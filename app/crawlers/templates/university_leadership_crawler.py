from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_content_hash
from app.crawlers.utils.html_sanitizer import sanitize_html
from app.crawlers.utils.text_extract import html_to_text

logger = logging.getLogger(__name__)

_TARGET_ROLES = ("校长", "常务副校长", "副校长", "党委书记","党委副书记","纪委书记", "党委常委", "党委常务副书记")
_ROLE_MARK_RE = re.compile(r"(党委书记|常务副校长|副校长|校\s*长(?!助理|办公室))")
_NON_TARGET_ROLE_RE = re.compile(
    r"(党委副书记|党委常委|党委常务副书记|纪委书记|监察专员|监委|副书?记|校长助理)"
)
_NON_TARGET_DETAIL_ROLE_RE = re.compile(
    r"(党委常务副书记|党委副书记|纪委书记|监察专员|监委|校长助理)"
)
_CJK_NAME_RE = re.compile(r"[\u4e00-\u9fff]{2,4}")
_IGNORE_NAME_WORDS = {
    "党委书记",
    "党委副书记",
    "常务副校长",
    "副校长",
    "校长",
    "现任领导",
    "领导",
    "更多",
    "详情",
    "简介",
    "点击",
    "查看",
    "个人主页",
    "党委",
    "助理",
    "办公室",
    "保卫",
    "学科建设",
    "政策法规",
    "最新动态",
    "查看更多",
    "校长信箱",
    "历任校党委书记",
    "历任校长",
    "历任",
    "大学",
    "学院",
    "湘潭大学",
    "学校领导班子",
    "国家监委",
    "监察专员",
    "学校概况",
    "学校简介",
    "学校历史",
    "研究方向",
    "教授",
    "院士",
}
_IGNORE_NAME_SUBSTRINGS = (
    "历任",
    "办公室",
    "助理",
    "信箱",
    "动态",
    "查看",
    "大学",
    "学院",
    "学科",
    "政策",
    "法规",
    "保卫",
    "党委",
    "校长",
    "书记",
    "常委",
    "纪委",
    "监委",
    "监察",
    "研究方向",
)


@dataclass
class LeaderCandidate:
    role: str
    name: str
    profile_url: str | None
    avatar_url: str | None
    source_text: str


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _extract_university_name(source_name: str, source_id: str) -> str:
    if source_name:
        return source_name.split("-", 1)[0].strip() or source_id
    return source_id


def _normalize_role(text: str | None) -> str | None:
    if not text:
        return None
    compact = re.sub(r"\s+", "", text)
    # "校长助理" must always be excluded even though it contains "校长".
    if "校长助理" in compact:
        return None

    # Prefer target roles when a title mixes target/non-target segments,
    # e.g. "党委常委、副校长" or "校长、党委副书记".
    if "常务副校长" in compact:
        return "常务副校长"
    if "副校长" in compact:
        return "副校长"
    if re.search(r"(?<!副)校长", compact):
        return "校长"
    if "党委书记" in compact and "党委副书记" not in compact:
        return "党委书记"

    if _NON_TARGET_ROLE_RE.search(compact):
        return None
    return None


def _detect_target_role_from_detail(text: str | None) -> str | None:
    if not text:
        return None
    compact = re.sub(r"\s+", "", text)
    if "常务副校长" in compact:
        return "常务副校长"
    if re.search(r"(?<!副)校长(?!助理|办公室)", compact):
        return "校长"
    if "副校长" in compact:
        return "副校长"
    idx_secretary = compact.find("党委书记")
    if idx_secretary != -1:
        idx_dep_secretary = compact.find("党委副书记")
        idx_exec_dep_secretary = compact.find("党委常务副书记")
        dep_before = idx_dep_secretary != -1 and idx_dep_secretary < idx_secretary
        exec_dep_before = idx_exec_dep_secretary != -1 and idx_exec_dep_secretary < idx_secretary
        if not dep_before and not exec_dep_before:
            return "党委书记"
    return None


def _build_detail_role_probe(detail_name_text: str | None, content_text: str | None) -> str:
    parts: list[str] = []
    if detail_name_text:
        parts.append(_normalize_space(detail_name_text))

    if content_text:
        lines = [_normalize_space(x) for x in content_text.splitlines() if _normalize_space(x)]
        if lines:
            # Keep only the beginning where current role usually appears.
            head_raw = " ".join(lines[:2])
            head = re.split(r"[。；;！？!?]", head_raw, maxsplit=1)[0][:80]
            parts.append(head)

    return _normalize_space(" ".join(parts))


def _clean_name(text: str) -> str:
    text = _normalize_space(text)
    text = re.sub(r"[（(].*?[）)]", "", text)
    text = text.replace("：", " ").replace(":", " ")
    text = re.sub(r"[、,，/|]", " ", text)
    return _normalize_space(text)


def _extract_names(text: str) -> list[str]:
    text = _clean_name(text)
    if not text:
        return []

    names: list[str] = []
    tokens = text.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in _IGNORE_NAME_WORDS or _ROLE_MARK_RE.search(token):
            i += 1
            continue
        if _CJK_NAME_RE.fullmatch(token) and not _is_ignored_name(token):
            names.append(token)
            i += 1
            continue
        if (
            re.fullmatch(r"[\u4e00-\u9fff]", token)
            and i + 1 < len(tokens)
            and re.fullmatch(r"[\u4e00-\u9fff]", tokens[i + 1])
        ):
            merged = token + tokens[i + 1]
            if not _is_ignored_name(merged):
                names.append(merged)
            i += 2
            continue
        i += 1

    if names:
        return _unique_preserve_order(names)

    fallback = [m.group(0) for m in _CJK_NAME_RE.finditer(text)]
    filtered = [n for n in fallback if not _is_ignored_name(n)]
    return _unique_preserve_order(filtered)


def _is_ignored_name(name: str) -> bool:
    if not name:
        return True
    if name in _IGNORE_NAME_WORDS:
        return True
    return any(part in name for part in _IGNORE_NAME_SUBSTRINGS)


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _looks_like_generic_avatar(url: str | None) -> bool:
    if not url:
        return False
    low = url.lower()
    return any(mark in low for mark in ("logo", "favicon", "icon", "default-avatar", "noavatar"))


class UniversityLeadershipCrawler(BaseCrawler):
    """Playwright crawler for official university leadership pages.

    It extracts only these roles:
      - 校长
      - 常务副校长
      - 副校长
      - 党委书记

    Then it opens each leader detail page and extracts avatar + profile content.
    """

    def _map_names_to_roles_from_text(self, block_text: str) -> dict[str, str]:
        text = _normalize_space(self._apply_role_aliases(block_text))
        role_mark_re = re.compile(
            r"(党\s*委\s*书\s*记|常\s*务\s*副\s*校\s*长|副\s*校\s*长|校\s*长(?!\s*助理|\s*办公室)|"
            r"党\s*委\s*副\s*书\s*记|党\s*委\s*常\s*委|党\s*委\s*常\s*务\s*副\s*书\s*记|"
            r"纪\s*委\s*书\s*记|监\s*察\s*专\s*员|监\s*委)"
        )
        matches = list(role_mark_re.finditer(text))
        if not matches:
            return {}

        mapped: dict[str, str] = {}
        for i, match in enumerate(matches):
            raw_role = match.group(1)
            role = _normalize_role(raw_role)
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            segment = text[start:end]
            names = _extract_names(segment)
            if not role:
                continue
            for name in names:
                mapped[name] = role
        return mapped

    def _apply_role_aliases(self, text: str | None) -> str:
        if not text:
            return ""
        aliases = self.config.get("role_aliases")
        if not isinstance(aliases, dict):
            return str(text)
        out = str(text)
        for src, dst in aliases.items():
            if not src or not dst:
                continue
            out = out.replace(str(src), str(dst))
        return out

    def _extract_candidates_from_block(self, block: Tag, base_url: str) -> list[LeaderCandidate]:
        block_text = _normalize_space(block.get_text(" ", strip=True))
        if not block_text:
            return []

        selectors = self.config.get("selectors", {})
        role_sel = selectors.get("role")
        name_sel = selectors.get("name")
        profile_link_sel = selectors.get("profile_link", "a[href]")
        avatar_sel = selectors.get("avatar")

        role_text = ""
        if role_sel:
            role_node = block.select_one(role_sel)
            if role_node:
                role_text = _normalize_space(role_node.get_text(" ", strip=True))
        if not role_text:
            role_node = block.select_one("h1,h2,h3,h4,h5,h6,strong,b,th,dt,.title,.post,.job,.position")
            if role_node:
                role_text = _normalize_space(role_node.get_text(" ", strip=True))
        default_role = _normalize_role(self._apply_role_aliases(role_text or block_text))

        links: list[tuple[str, str]] = []
        link_urls: list[str] = []
        avatar_urls: list[str] = []

        if avatar_sel:
            for img in block.select(avatar_sel):
                src = _normalize_space(img.get("src", "")) if isinstance(img, Tag) else ""
                if not src:
                    continue
                avatar_urls.append(urljoin(base_url, src))

        for a in block.select(profile_link_sel):
            href = _normalize_space(a.get("href", ""))
            if not href or href.startswith("#") or href.lower().startswith("javascript:"):
                continue
            abs_url = urljoin(base_url, href)
            link_urls.append(abs_url)
            name_text = _clean_name(a.get_text(" ", strip=True))
            names = _extract_names(self._apply_role_aliases(name_text))
            if not names:
                continue
            links.append((names[0], abs_url))

        text_role_map = self._map_names_to_roles_from_text(block_text)
        candidates: list[LeaderCandidate] = []

        if links:
            for name, profile_url in links:
                role = text_role_map.get(name) or default_role
                if role not in _TARGET_ROLES:
                    continue
                avatar_url = avatar_urls[len(candidates)] if len(avatar_urls) > len(candidates) else None
                candidates.append(
                    LeaderCandidate(
                        role=role,
                        name=name,
                        profile_url=profile_url,
                        avatar_url=avatar_url,
                        source_text=block_text,
                    )
                )
        elif link_urls:
            if name_sel:
                name_nodes = block.select(name_sel)
                if selectors.get("name_first_only"):
                    names = []
                    for node in name_nodes:
                        extracted = _extract_names(
                            self._apply_role_aliases(node.get_text(" ", strip=True))
                        )
                        if extracted:
                            names.append(extracted[0])
                    names = _unique_preserve_order(names)
                else:
                    name_text = " ".join(node.get_text(" ", strip=True) for node in name_nodes)
                    names = _extract_names(self._apply_role_aliases(name_text))
            else:
                name_text = re.sub(r"(党委书记|常务副校长|副校长|校\s*长)", " ", block_text)
                names = _extract_names(self._apply_role_aliases(name_text))
            for idx, name in enumerate(names):
                role = text_role_map.get(name) or default_role
                if role not in _TARGET_ROLES:
                    continue
                profile_url = link_urls[min(idx, len(link_urls) - 1)] if link_urls else None
                avatar_url = avatar_urls[min(idx, len(avatar_urls) - 1)] if avatar_urls else None
                candidates.append(
                    LeaderCandidate(
                        role=role,
                        name=name,
                        profile_url=profile_url,
                        avatar_url=avatar_url,
                        source_text=block_text,
                    )
                )
        else:
            if name_sel:
                name_nodes = block.select(name_sel)
                if selectors.get("name_first_only"):
                    names = []
                    for node in name_nodes:
                        extracted = _extract_names(
                            self._apply_role_aliases(node.get_text(" ", strip=True))
                        )
                        if extracted:
                            names.append(extracted[0])
                    names = _unique_preserve_order(names)
                else:
                    name_text = " ".join(node.get_text(" ", strip=True) for node in name_nodes)
                    names = _extract_names(self._apply_role_aliases(name_text))
            else:
                name_text = re.sub(r"(党委书记|常务副校长|副校长|校\s*长)", " ", block_text)
                names = _extract_names(self._apply_role_aliases(name_text))
            for name in names:
                if default_role not in _TARGET_ROLES:
                    continue
                avatar_url = avatar_urls[0] if avatar_urls else None
                candidates.append(
                    LeaderCandidate(
                        role=default_role,
                        name=name,
                        profile_url=None,
                        avatar_url=avatar_url,
                        source_text=block_text,
                    )
                )

        deduped: list[LeaderCandidate] = []
        seen: set[tuple[str, str, str | None]] = set()
        for candidate in candidates:
            key = (candidate.role, candidate.name, candidate.profile_url)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    async def _extract_from_list_page(self, html: str, base_url: str) -> list[LeaderCandidate]:
        soup = BeautifulSoup(html, "lxml")
        selectors = self.config.get("selectors", {})
        list_item_sel = selectors.get("list_item")

        if list_item_sel:
            blocks = soup.select(list_item_sel)
        else:
            blocks = soup.select(
                ".xleader li, .xleader .item, .leader li, .leaders li, .xxld li, "
                ".xrld li, .ld-list li, .list li, .leader-item, .person-item, "
                "div.tr, .table-row, .leader-row, tr"
            )

        candidates: list[LeaderCandidate] = []
        for block in blocks:
            if not isinstance(block, Tag):
                continue
            candidates.extend(self._extract_candidates_from_block(block, base_url))

        if candidates:
            return self._dedup_candidates(candidates)

        # Fallback for pages with plain text blocks only.
        fallback_nodes = soup.select("p,div,td,dd,h3,h4,span")
        for node in fallback_nodes:
            text = _normalize_space(node.get_text(" ", strip=True))
            if not text or len(text) > 90:
                continue
            role = _normalize_role(text)
            if role not in _TARGET_ROLES:
                continue
            cleaned = re.sub(r"(党委书记|常务副校长|副校长|校\s*长)", " ", text)
            names = _extract_names(cleaned)
            for name in names:
                candidates.append(
                    LeaderCandidate(
                        role=role,
                        name=name,
                        profile_url=None,
                        avatar_url=None,
                        source_text=text,
                    )
                )

        return self._dedup_candidates(candidates)

    def _dedup_candidates(self, candidates: list[LeaderCandidate]) -> list[LeaderCandidate]:
        deduped: list[LeaderCandidate] = []
        seen: set[tuple[str, str, str | None]] = set()
        for candidate in candidates:
            key = (candidate.role, candidate.name, candidate.profile_url)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    def _pick_first_node(self, soup: BeautifulSoup, selector_conf: str | list[str] | None) -> Tag | None:
        if not selector_conf:
            return None
        selectors = [selector_conf] if isinstance(selector_conf, str) else selector_conf
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                return node
        return None

    def _extract_intro_lines(self, content_node: Tag | None) -> list[str]:
        if not content_node:
            return []

        lines: list[str] = []
        for node in content_node.select("ul li, p"):
            text = _normalize_space(node.get_text(" ", strip=True))
            if not text:
                continue
            if text in lines:
                continue
            lines.append(text)
            if len(lines) >= 12:
                break
        return lines

    async def _fetch_detail(self, page, detail_url: str) -> dict[str, object]:
        detail_selectors = self.config.get("detail_selectors", {})
        wait_timeout = self.config.get("wait_timeout", 12000)

        await page.goto(detail_url, wait_until="domcontentloaded", timeout=wait_timeout)
        detail_wait = detail_selectors.get("content_wait")
        if detail_wait:
            try:
                await page.wait_for_selector(detail_wait, timeout=wait_timeout)
            except Exception:
                pass

        html = await page.content()

        marker_start = "<!--Start||content-->"
        marker_end = "<!--End||content-->"
        marker_html = None
        if marker_start in html and marker_end in html:
            start = html.find(marker_start)
            end = html.find(marker_end, start)
            if start != -1 and end != -1 and end > start:
                marker_html = html[start + len(marker_start):end]

        soup = BeautifulSoup(html, "html.parser")

        content_node = self._pick_first_node(
            soup,
            detail_selectors.get(
                "content",
                [
                    'form[name="_newscontent_fromname"]',
                    ".teachDetail3",
                    ".textBox #vsb_content",
                    "#vsb_content",
                    ".textBox",
                    ".article-content",
                    ".news_box",
                    "article",
                    ".content",
                    ".detail",
                ],
            ),
        )

        if content_node:
            for noisy in content_node.select(
                "script,style,header,footer,nav,.header,.footer,.nav,.menu,"
                ".breadcrumb,.sidebar,.side,.top,.bottom,.copyright,.share,.links"
            ):
                noisy.decompose()

        raw_html = marker_html or (str(content_node) if content_node else "")
        content_text = html_to_text(raw_html) if raw_html else None
        content_html = sanitize_html(raw_html, base_url=detail_url) if raw_html else None
        content_hash = compute_content_hash(content_text) if content_text else None

        avatar_node = self._pick_first_node(
            soup,
            detail_selectors.get(
                "avatar",
                [
                    ".arti_img img",
                    ".arti-img img",
                    ".article_img img",
                    ".picbox2 .pic img",
                    ".picbox2 img",
                    ".teachDetail3 .pic img",
                    ".teachDetail3 img",
                    "img",
                ],
            ),
        )
        avatar_url = None
        if avatar_node:
            src = avatar_node.get("src") if isinstance(avatar_node, Tag) else None
            if src:
                avatar_url = urljoin(detail_url, src)

        detail_name_node = self._pick_first_node(
            soup,
            detail_selectors.get("name", [".xName", ".name", "h1", "h2"]),
        )
        detail_name_text = (
            _normalize_space(detail_name_node.get_text(" ", strip=True))
            if detail_name_node
            else None
        )

        intro_lines = self._extract_intro_lines(content_node)

        return {
            "content": content_text,
            "content_html": content_html,
            "content_hash": content_hash,
            "avatar_url": avatar_url,
            "detail_name_text": detail_name_text,
            "intro_lines": intro_lines,
        }

    def _item_quality_score(self, item: CrawledItem, source_url: str) -> int:
        score = 0
        if item.url and not item.url.startswith(f"{source_url}#leader-"):
            score += 3
        if item.content and len(item.content) >= 80:
            score += 2
        if item.extra.get("avatar_url"):
            score += 1
        if item.extra.get("detail_name_text"):
            score += 1
        return score

    def _role_priority(self, role: str) -> int:
        priority = {
            "党委书记": 4,
            "校长": 3,
            "常务副校长": 2,
            "副校长": 1,
        }
        return priority.get(role, 0)

    async def fetch_and_parse(self) -> list[CrawledItem]:
        from app.crawlers.utils.playwright_pool import get_page

        source_url = self.config["url"]
        wait_for = self.config.get("wait_for", "networkidle")
        wait_timeout = self.config.get("wait_timeout", 12000)
        request_delay = self.config.get("request_delay", 0)

        source_name = self.config.get("name", self.source_id)
        university_name = _extract_university_name(source_name, self.source_id)

        apply_webdriver_patch = not bool(self.config.get("disable_webdriver_patch", False))

        async with get_page(apply_webdriver_patch=apply_webdriver_patch) as page:
            await page.goto(source_url, wait_until="domcontentloaded", timeout=wait_timeout)
            if wait_for == "networkidle":
                try:
                    await page.wait_for_load_state("networkidle", timeout=wait_timeout)
                except Exception:
                    pass
            else:
                await page.wait_for_selector(wait_for, timeout=wait_timeout)

            html = await page.content()
            leaders = await self._extract_from_list_page(html, base_url=source_url)

            items: list[CrawledItem] = []
            for leader in leaders:
                detail: dict[str, object] = {
                    "content": None,
                    "content_html": None,
                    "content_hash": None,
                    "avatar_url": None,
                    "detail_name_text": None,
                    "intro_lines": [],
                }

                if leader.profile_url:
                    try:
                        if request_delay:
                            await asyncio.sleep(request_delay)
                        detail = await self._fetch_detail(page, leader.profile_url)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Failed to fetch detail %s (%s %s): %s",
                            leader.profile_url,
                            leader.role,
                            leader.name,
                            exc,
                        )

                detail_name_text = str(detail.get("detail_name_text") or "")
                content_text = detail.get("content")
                detail_probe = _build_detail_role_probe(
                    detail_name_text=detail_name_text,
                    content_text=content_text if isinstance(content_text, str) else None,
                )
                detail_probe = self._apply_role_aliases(detail_probe)
                detail_role = _detect_target_role_from_detail(detail_probe)

                if detail_role is None and _NON_TARGET_DETAIL_ROLE_RE.search(detail_probe):
                    # Detail explicitly indicates non-target roles (e.g. 党委副书记/纪委书记).
                    continue

                final_role = detail_role or leader.role
                if final_role not in _TARGET_ROLES:
                    continue

                tags = list(self.config.get("tags", []))
                if "university_leadership" not in tags:
                    tags.append("university_leadership")
                if final_role not in tags:
                    tags.append(final_role)

                profile_url = leader.profile_url or f"{source_url}#leader-{final_role}-{leader.name}"
                detail_avatar = str(detail.get("avatar_url") or "").strip() or None
                list_avatar = str(leader.avatar_url or "").strip() or None

                if detail_avatar and not _looks_like_generic_avatar(detail_avatar):
                    final_avatar = detail_avatar
                elif list_avatar and not _looks_like_generic_avatar(list_avatar):
                    final_avatar = list_avatar
                else:
                    final_avatar = None

                extra = {
                    "entity_type": "university_leader",
                    "university_name": university_name,
                    "position": final_role,
                    "name": leader.name,
                    "profile_url": leader.profile_url,
                    "profile_page_url": profile_url,
                    "source_page_url": source_url,
                    "avatar_url": final_avatar,
                    "personal_intro": content_text,
                    "intro_lines": detail.get("intro_lines", []),
                    "detail_name_text": detail.get("detail_name_text"),
                    "list_block_text": leader.source_text,
                    "list_position_raw": leader.role,
                }

                items.append(
                    CrawledItem(
                        title=f"{final_role}-{leader.name}",
                        url=profile_url,
                        author=leader.name,
                        content=content_text if isinstance(content_text, str) else None,
                        content_html=detail.get("content_html") if isinstance(detail.get("content_html"), str) else None,
                        content_hash=detail.get("content_hash") if isinstance(detail.get("content_hash"), str) else None,
                        source_id=self.source_id,
                        dimension=self.config.get("dimension"),
                        tags=tags,
                        extra=extra,
                    )
                )

            # Merge duplicates inside one university by (role, name), preserving the richer record.
            merged: dict[tuple[str, str], CrawledItem] = {}
            for item in items:
                role = str(item.extra.get("position", ""))
                name = str(item.extra.get("name", item.author or ""))
                key = (role, name)

                existing = merged.get(key)
                if existing is None:
                    merged[key] = item
                    continue

                if self._item_quality_score(item, source_url) > self._item_quality_score(existing, source_url):
                    merged[key] = item

            # If one person appears under multiple target roles, keep the highest-priority role.
            by_name: dict[str, CrawledItem] = {}
            for item in merged.values():
                name = str(item.extra.get("name", item.author or "")).strip()
                if not name:
                    continue

                prev = by_name.get(name)
                if prev is None:
                    by_name[name] = item
                    continue

                role = str(item.extra.get("position", ""))
                prev_role = str(prev.extra.get("position", ""))
                role_score = self._role_priority(role) * 10 + self._item_quality_score(item, source_url)
                prev_score = self._role_priority(prev_role) * 10 + self._item_quality_score(prev, source_url)
                if role_score > prev_score:
                    by_name[name] = item

            return list(by_name.values())
