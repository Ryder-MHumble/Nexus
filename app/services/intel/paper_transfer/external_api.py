"""Clients for the zkygyzlyj authorship API and arXiv API."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

AUTHORSHIP_BASE = (
    "https://paper-authorship-detection.zeabur.app/api/integration/v2/authorship"
)
ARXIV_API = "https://export.arxiv.org/api/query"


async def fetch_all_students(school_filter: str | None = None) -> list[dict]:
    """Fetch all students from the authorship API (paginated).

    Args:
        school_filter: Optional fuzzy substring to match against school_cn.
    """
    students: list[dict] = []
    offset = 0
    limit = 200
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            resp = await client.get(
                f"{AUTHORSHIP_BASE}/students",
                params={"limit": limit, "offset": offset},
            )
            resp.raise_for_status()
            data = resp.json()
            page_items: list[dict] = data.get("items", [])
            if not page_items:
                break
            if school_filter:
                sf = school_filter.lower()
                filtered = [s for s in page_items if sf in s.get("school_cn", "").lower()]
            else:
                filtered = page_items
            students.extend(filtered)
            offset += len(page_items)  # advance by unfiltered count to paginate correctly
            if offset >= data.get("total", 0):
                break
    logger.info("Fetched %d students (school_filter=%r)", len(students), school_filter)
    return students


async def fetch_student_papers(student_id: str, date_from: str | None = None) -> list[dict]:
    """Fetch all papers for a student, optionally filtered by publication date.

    Retries up to 2 times on timeout/network errors before returning an empty list.

    Args:
        student_id: External student ID.
        date_from: ISO date string (YYYY-MM-DD). Papers older than this are excluded.
    """
    for attempt in range(3):
        try:
            papers: list[dict] = []
            offset = 0
            limit = 200
            async with httpx.AsyncClient(timeout=60.0) as client:
                while True:
                    resp = await client.get(
                        f"{AUTHORSHIP_BASE}/students/{student_id}/papers",
                        params={"limit": limit, "offset": offset},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    page_items: list[dict] = data.get("items", [])
                    if not page_items:
                        break
                    if date_from:
                        filtered = [
                            p
                            for p in page_items
                            if (p.get("publication_date") or "") >= date_from
                        ]
                    else:
                        filtered = page_items
                    papers.extend(filtered)
                    offset += len(page_items)
                    if offset >= data.get("total", 0):
                        break
            return papers
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            logger.warning(
                "fetch_student_papers %s attempt %d failed: %s", student_id, attempt + 1, e
            )
            if attempt == 2:
                logger.error("Giving up on %s after 3 attempts", student_id)
                return []
    return []


async def fetch_arxiv_abstract(arxiv_id: str) -> str | None:
    """Fetch paper abstract from arXiv Atom API.

    Returns the abstract text with internal newlines collapsed, or None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(ARXIV_API, params={"id_list": arxiv_id})
            resp.raise_for_status()
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        summary = root.find(".//atom:entry/atom:summary", ns)
        if summary is not None and summary.text:
            return summary.text.strip().replace("\n", " ")
    except Exception as e:
        logger.warning("Failed to fetch arXiv abstract for %s: %s", arxiv_id, e)
    return None
