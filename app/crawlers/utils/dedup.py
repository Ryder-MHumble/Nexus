import hashlib
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Tracking parameters to strip from URLs
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "from", "spm", "share_token", "wfr", "isappinstalled",
}


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication: lowercase host, strip tracking params, trailing slash."""
    parsed = urlparse(url)
    # Lowercase scheme and host
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    # Strip tracking params
    query_params = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in query_params.items() if k.lower() not in _TRACKING_PARAMS}
    query = urlencode(filtered, doseq=True)
    # Strip trailing slash from path
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, parsed.params, query, parsed.fragment))


def compute_url_hash(url: str) -> str:
    """Compute SHA-256 hash of a normalized URL."""
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of cleaned content text."""
    # Collapse whitespace for consistent hashing
    cleaned = re.sub(r"\s+", " ", content.strip())
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
