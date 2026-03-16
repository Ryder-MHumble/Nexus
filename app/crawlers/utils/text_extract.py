from __future__ import annotations

import re

from bs4 import BeautifulSoup


def html_to_text(html: str) -> str:
    """Extract clean text from HTML, stripping tags and collapsing whitespace."""
    soup = BeautifulSoup(html, "lxml")
    # Remove script and style elements
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Collapse blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_by_selector(html: str, selector: str) -> str:
    """Extract text from a specific CSS selector."""
    soup = BeautifulSoup(html, "lxml")
    element = soup.select_one(selector)
    if element is None:
        return ""
    return element.get_text(separator="\n").strip()
