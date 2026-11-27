from __future__ import annotations

import socket

import pytest

from app.core.url_utils import (
    canonical_url,
    classify_page_type,
    hostname_of,
    is_same_host,
    normalize_url,
    safe_csv_value,
    validate_target_url,
)


def test_normalize_url_strips_tracking_but_preserves_real_params():
    url = "HTTPS://WWW.Example.com/Path/?utm_source=news&id=42&fbclid=abc#section"
    assert normalize_url(url) == "https://www.example.com/Path/?id=42"
    assert normalize_url(url, {"strip_tracking_params": False}).endswith("fbclid=abc")
    assert normalize_url(url, {"strip_www": True, "lowercase_path": True}) == "https://example.com/path/?id=42"


def test_normalize_url_handles_empty_and_relative_values():
    assert normalize_url("") == ""
    assert normalize_url("example.com/a/") == "https://example.com/a/"


def test_validate_target_url_blocks_ssrf_vectors():
    for bad in [
        "http://localhost/admin",
        "http://127.0.0.1:8080/",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "https://user:pass@example.com/",
        "javascript:alert(1)",
        "",
        "x" * 5000,
    ]:
        with pytest.raises(ValueError) as exc:
            validate_target_url(bad)
        assert str(exc.value)


def test_validate_target_url_allows_public_http_targets():
    assert validate_target_url("https://demo.example.com/page/") == "https://demo.example.com/page/"
    with pytest.raises(ValueError):
        validate_target_url("http://localhost/", allow_private=False)
    assert validate_target_url("http://localhost:8000/", allow_private=True).endswith(":8000/")


def test_validate_target_url_rejects_private_dns_answers_and_numeric_ips(monkeypatch):
    def private_answer(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))]

    monkeypatch.setattr("app.core.url_utils.socket.getaddrinfo", private_answer)
    with pytest.raises(ValueError, match="private"):
        validate_target_url("https://rebind.example.com/")
    with pytest.raises(ValueError, match="Private"):
        validate_target_url("http://2130706433/")
    with pytest.raises(ValueError, match="Host could not be resolved"):
        monkeypatch.setattr(
            "app.core.url_utils.socket.getaddrinfo",
            lambda *args, **kwargs: (_ for _ in ()).throw(socket.gaierror("blocked")),
        )
        validate_target_url("https://unknown.example.com/")


def test_helpers_cover_canonical_host_and_classification():
    assert canonical_url("/about/", "https://example.com/blog/post/") == "https://example.com/about/"
    assert canonical_url("https://example.com/about/", "https://other.com/") == "https://example.com/about/"
    assert hostname_of("https://Example.com:8443/a") == "example.com"
    assert is_same_host("https://example.com/a", "https://www.example.com/b") is True
    assert classify_page_type("https://example.com/products/category-a/product-1/") == "product"
    assert classify_page_type("https://example.com/services/vapt/") == "service"
    assert classify_page_type("https://example.com/") == "homepage"


def test_safe_csv_value_neutralises_formula_injection():
    assert safe_csv_value("=HYPERLINK(\"http://evil\")").startswith("'")
    assert safe_csv_value("@SUM(A1)").startswith("'")
    assert safe_csv_value("Ordinary title") == "Ordinary title"
    assert safe_csv_value(None) == ""
