"""URL helpers for official-report shadow comparison."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


_OFFICIAL_DOMAINS = {
    "static.cninfo.com.cn",
    "www.cninfo.com.cn",
    "cninfo.com.cn",
    "www.sse.com.cn",
    "static.sse.com.cn",
    "sse.com.cn",
    "disc.static.szse.cn",
    "www.szse.cn",
    "szse.cn",
    "www.hkexnews.hk",
    "hkexnews.hk",
}
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {"spm", "from", "source", "channel", "campaign", "share_token"}
_SIGNED_KEYS = {"signature", "sign", "token", "expires", "x-amz-signature", "x-amz-expires"}


def normalize_report_url(url: str | None) -> str | None:
    if not url:
        return None
    raw = str(url).strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return raw
    host = (parsed.hostname or "").lower()
    scheme = "https" if host in _OFFICIAL_DOMAINS and parsed.scheme in {"http", "https"} else parsed.scheme.lower()
    query = parsed.query
    if not _has_signed_query(parsed.query):
        pairs = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            lower = key.lower()
            if lower in _TRACKING_KEYS or lower.startswith(_TRACKING_PREFIXES):
                continue
            pairs.append((key, value))
        query = urlencode(pairs, doseq=True)
    path = parsed.path or "/"
    return urlunparse((scheme, parsed.netloc.lower(), path, "", query, ""))


def official_domain_verified(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(str(url).strip())
    host = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and (
        host in _OFFICIAL_DOMAINS or any(host.endswith(f".{domain}") for domain in _OFFICIAL_DOMAINS)
    )


def report_url_identity(url: str | None) -> dict[str, object]:
    return {
        "raw": url or None,
        "normalized": normalize_report_url(url),
        "official_domain_verified": official_domain_verified(url),
    }


def _has_signed_query(query: str) -> bool:
    if not query:
        return False
    for key, _value in parse_qsl(query, keep_blank_values=True):
        lower = key.lower()
        if lower in _SIGNED_KEYS or lower.startswith("x-amz-"):
            return True
    return False
