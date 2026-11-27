"""URL validation, normalisation and classification.

Normalisation is deliberately configurable: query parameters are never blindly
removed, and variant equivalence is a project-level decision.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DEFAULT_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "gclid", "gclsrc", "fbclid", "msclkid", "dclid", "igshid",
    "_ga", "_gl", "mc_cid", "mc_eid", "ref", "source",
}

DEFAULT_RULES = {
    "lowercase_host": True,
    "lowercase_path": False,
    "strip_fragment": True,
    "strip_tracking_params": True,
    "tracking_params": sorted(DEFAULT_TRACKING_PARAMS),
    "preserve_params": [],
    "remove_trailing_slash": False,
    "strip_www": False,
    "force_https": False,
    "drop_default_ports": True,
}

TRACKING_RE = re.compile(r"^(utm_|gclid$|fbclid$|msclkid$|dclid$|mc_[ce]id$|_ga$|_gl$)", re.I)
RESERVED_HOST_SUFFIXES = (
    ".localhost", ".local", ".internal", ".localdomain", ".home.arpa",
)


def _forbidden_ip(ip: ipaddress._BaseAddress) -> bool:
    return bool(
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        or ip.is_multicast or ip.is_unspecified
    )


def _ip_literal(host: str) -> ipaddress._BaseAddress | None:
    """Parse dotted, IPv6 and decimal/hex integer IP spellings."""
    candidate = host.strip().strip("[]")
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        pass
    for base in (10, 16):
        try:
            value = int(candidate, base)
        except (TypeError, ValueError):
            continue
        if 0 <= value <= (2 ** 128) - 1:
            try:
                return ipaddress.ip_address(value)
            except ValueError:
                continue
    return None


def _is_forbidden_literal_host(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    if normalized in {"localhost", "metadata", "metadata.google.internal"}:
        return True
    if any(normalized.endswith(suffix) for suffix in RESERVED_HOST_SUFFIXES):
        return True
    literal = _ip_literal(normalized)
    return bool(literal and _forbidden_ip(literal))


def _resolve_public_addresses(host: str) -> None:
    """Fail closed when a hostname resolves to any non-public address."""
    normalized = host.rstrip(".").encode("idna").decode("ascii")
    try:
        infos = socket.getaddrinfo(normalized, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"Host could not be resolved safely: {type(exc).__name__}") from exc
    if not infos:
        raise ValueError("Host has no usable address")
    for info in infos[:20]:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(str(address).split("%", 1)[0])
        except ValueError as exc:
            raise ValueError("Host resolved to an unrecognised address") from exc
        if _forbidden_ip(ip):
            raise ValueError("Host resolves to a private or internal network address")


def validate_target_url(url: str, allow_private: bool = False, resolve_dns: bool = True) -> str:
    """Validate a URL before any network access. Raises ValueError on unsafe input.

    Public targets are DNS-resolved and rejected when any resolved address is
    private, loopback, link-local, reserved or multicast. Callers cannot bypass
    this by spelling an IPv4 address as an integer. ``allow_private`` exists only
    for explicit local tooling and still rejects embedded credentials.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL is required")
    url = url.strip()
    if len(url) > 4096:
        raise ValueError("URL exceeds 4096 characters")
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only http and https URLs are allowed")
    if not parts.hostname:
        raise ValueError("URL has no hostname")
    if parts.username or parts.password:
        raise ValueError("Embedded credentials are not allowed")
    if not allow_private:
        if _is_forbidden_literal_host(parts.hostname):
            raise ValueError("Private or internal network addresses are not allowed")
        if resolve_dns and _ip_literal(parts.hostname) is None:
            _resolve_public_addresses(parts.hostname)
    if parts.port and not (1 <= parts.port <= 65535):
        raise ValueError("Invalid port")
    return url


def normalize_url(url: str, rules: dict | None = None) -> str:
    """Return a stable comparison key for a URL. Invalid URLs are returned cleaned."""
    cfg = {**DEFAULT_RULES, **(rules or {})}
    raw = (url or "").strip()
    if not raw:
        return ""
    if not raw.lower().startswith(("http://", "https://")):
        raw = "https://" + raw.lstrip("/")
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw
    scheme = "https" if cfg.get("force_https") else parts.scheme.lower()
    host = parts.hostname or ""
    if cfg.get("lowercase_host", True):
        host = host.lower()
    if cfg.get("strip_www") and host.startswith("www."):
        host = host[4:]
    port = parts.port
    if cfg.get("drop_default_ports", True) and port and (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        port = None
    netloc = host + (f":{port}" if port else "")
    path = parts.path or "/"
    if cfg.get("lowercase_path"):
        path = path.lower()
    if cfg.get("remove_trailing_slash") and len(path) > 1:
        path = path.rstrip("/")
    preserve = set(cfg.get("preserve_params") or [])
    tracking = set(cfg.get("tracking_params") or []) | set(DEFAULT_TRACKING_PARAMS)
    if cfg.get("strip_tracking_params") is False:
        query = parts.query
    else:
        pairs = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k in preserve or not (k in tracking or TRACKING_RE.match(k))
        ]
        query = urlencode(sorted(pairs))
    fragment = "" if cfg.get("strip_fragment", True) else parts.fragment
    return urlunsplit((scheme, netloc, path, query, fragment))


def url_hash(url: str, rules: dict | None = None) -> str:
    return hashlib.sha256(normalize_url(url, rules).encode("utf-8")).hexdigest()


def canonical_url(candidate: str | None, final_url: str) -> str:
    if not candidate:
        return ""
    parts = urlsplit(candidate.strip())
    if not parts.scheme or not parts.netloc:
        # relative canonicals resolve against the final URL
        base = urlsplit(final_url)
        return urlunsplit((base.scheme, base.netloc, parts.path, parts.query, ""))
    return candidate.strip()


def hostname_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def path_of(url: str) -> str:
    try:
        return urlsplit(url).path
    except ValueError:
        return ""


def is_same_host(a: str, b: str) -> bool:
    ha, hb = hostname_of(a), hostname_of(b)
    return bool(ha and hb) and (ha == hb or ha == "www." + hb or hb == "www." + ha)


def classify_page_type(url: str, title: str = "") -> str:
    """Heuristic page classification, exposed as a rule (not a vendor metric)."""
    p = path_of(url).lower()
    text = f"{p} {title.lower()}"
    rules = [
        (("product/", "/products/", "/p/"), "product"),
        (("category/", "/categories/", "/collections/"), "category"),
        (("blog/", "/news/", "/articles/", "/insights/"), "article"),
        (("service/", "/services/", "solution"), "service"),
        (("location/", "/locations/", "/branches/"), "location"),
        (("/faq", "/help/"), "faq"),
        (("/careers", "/jobs"), "careers"),
        (("/support/", "/docs/"), "support"),
    ]
    for needles, label in rules:
        if any(n in text for n in needles):
            return label
    if p in ("", "/", "/index.html", "/home"):
        return "homepage"
    return "unknown"


def safe_csv_value(value) -> str:
    """Neutralise spreadsheet formula injection in exported cells."""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text
