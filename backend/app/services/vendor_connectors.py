"""Dormant, credential-gated live vendor adapters.

Nothing in this module makes a network request unless all of these are true:

1. ``LIVE_CONNECTORS_ENABLED=true`` in the deployment environment;
2. that provider's OAuth client credentials (or LLM key) are present there; and
3. an authenticated caller explicitly triggers a sync for a configured project.

Rows returned by these adapters are verbatim provider responses. Nothing is
synthesised, inferred or back-filled. Until a sync actually succeeds, the
existing ``Not supplied`` contract is unchanged. Generated LLM text is labelled
as an assistive draft and is never treated as verified evidence.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.core.crypto import decrypt

TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GSC_ENDPOINT = "https://www.googleapis.com/webmasters/v3"
GA4_ENDPOINT = "https://analyticsdata.googleapis.com/v1beta"
LLM_ENDPOINT = "https://api.openai.com/v1/chat/completions"

LIVE_PROVIDERS = ("google_search_console", "google_analytics_4", "llm_provider")
SYNC_PROVIDERS = frozenset({"google_search_console", "google_analytics_4"})
DATA_KINDS = {
    "google_search_console": "api_live:gsc",
    "google_analytics_4": "api_live:ga4",
}


class ConnectorUnavailable(RuntimeError):
    """A connector is disabled, unconfigured, or received invalid input."""


def connector_readiness() -> dict[str, bool]:
    """Report activation state without ever exposing a credential value."""
    enabled = bool(settings.live_connectors_enabled)
    return {
        "google_search_console": enabled and all([
            settings.gsc_client_id, settings.gsc_client_secret, settings.gsc_redirect_uri,
        ]),
        "google_analytics_4": enabled and all([
            settings.ga4_client_id, settings.ga4_client_secret, settings.ga4_redirect_uri,
        ]),
        "llm_provider": enabled and bool(settings.llm_api_key),
    }


def _post_json(
    url: str,
    *,
    data: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    response = httpx.post(
        url, data=data, json=payload, headers=headers,
        timeout=settings.vendor_request_timeout_seconds,
    )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ConnectorUnavailable("Provider returned a non-object response")
    return body


def stored_refresh_token(credentials_encrypted: str) -> str:
    """Decrypt a stored refresh token; accept a bare token or a JSON object."""
    if not credentials_encrypted:
        raise ConnectorUnavailable("No stored credentials for this integration")
    try:
        raw = decrypt(credentials_encrypted)
    except Exception as exc:  # Fernet errors must never leak the secret value.
        raise ConnectorUnavailable("Stored credentials could not be decrypted") from exc
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        parsed = None
    value = parsed.get("refresh_token") or parsed.get("refreshToken") if isinstance(parsed, dict) else raw
    token = str(value or "").strip()
    if not token or any(ord(character) < 32 for character in token):
        raise ConnectorUnavailable("Stored credentials contain no usable refresh token")
    return token


def _access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    body = _post_json(TOKEN_ENDPOINT, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        raise ConnectorUnavailable("OAuth token response contained no access token")
    return token


def _date_range(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    try:
        end = date.fromisoformat(str(end_date)) if end_date else date.today()
        start = date.fromisoformat(str(start_date)) if start_date else end - timedelta(days=7)
    except (TypeError, ValueError) as exc:
        raise ConnectorUnavailable("Dates must use YYYY-MM-DD") from exc
    if start > end:
        raise ConnectorUnavailable("start_date must be on or before end_date")
    if (end - start).days > 90:
        raise ConnectorUnavailable("A live sync is limited to a 90-day range")
    return start.isoformat(), end.isoformat()


def _row_limit(value: Any) -> int:
    try:
        limit = int(value) if value not in (None, "") else settings.vendor_max_rows
    except (TypeError, ValueError) as exc:
        raise ConnectorUnavailable("Invalid row limit") from exc
    return min(max(limit, 1), settings.vendor_max_rows)


def fetch_gsc_rows(
    credentials_encrypted: str,
    site_url: str | None,
    start_date: str | None = None,
    end_date: str | None = None,
    row_limit: Any = None,
) -> list[dict[str, Any]]:
    """Fetch verbatim Search Console search-analytics rows for one site."""
    if not connector_readiness()["google_search_console"]:
        raise ConnectorUnavailable("Search Console connector is disabled or not configured")
    site = str(site_url or settings.gsc_site_url or "").strip()
    if not site or len(site) > 255 or any(ord(character) < 32 for character in site):
        raise ConnectorUnavailable("A valid GSC site_url is required")
    start, end = _date_range(start_date, end_date)
    token = _access_token(
        settings.gsc_client_id, settings.gsc_client_secret,
        stored_refresh_token(credentials_encrypted),
    )
    body = _post_json(
        f"{GSC_ENDPOINT}/sites/{quote(site, safe='')}/searchAnalytics/query",
        payload={
            "startDate": start, "endDate": end,
            "dimensions": ["date", "query", "page"],
            "rowLimit": _row_limit(row_limit), "startRow": 0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    rows: list[dict[str, Any]] = []
    for item in body.get("rows", []):
        if not isinstance(item, dict):
            continue
        keys = item.get("keys") or []
        row = {
            "date": keys[0] if len(keys) > 0 else "",
            "query": keys[1] if len(keys) > 1 else "",
            "page": keys[2] if len(keys) > 2 else "",
        }
        for metric in ("clicks", "impressions", "ctr", "position"):
            row[metric] = item.get(metric, "")
        rows.append(row)
    return rows


def fetch_ga4_rows(
    credentials_encrypted: str,
    property_id: str | None,
    start_date: str | None = None,
    end_date: str | None = None,
    row_limit: Any = None,
) -> list[dict[str, Any]]:
    """Fetch verbatim GA4 Data API report rows for one property."""
    if not connector_readiness()["google_analytics_4"]:
        raise ConnectorUnavailable("GA4 connector is disabled or not configured")
    prop = str(property_id or settings.ga4_property_id or "").strip()
    if not re.fullmatch(r"(?:properties/)?\d{1,20}", prop):
        raise ConnectorUnavailable("A numeric GA4 property_id is required")
    if not prop.startswith("properties/"):
        prop = f"properties/{prop}"
    start, end = _date_range(start_date, end_date)
    token = _access_token(
        settings.ga4_client_id, settings.ga4_client_secret,
        stored_refresh_token(credentials_encrypted),
    )
    body = _post_json(
        f"{GA4_ENDPOINT}/{prop}/runReport",
        payload={
            "dateRanges": [{"startDate": start, "endDate": end}],
            "dimensions": [{"name": "date"}, {"name": "pagePath"}],
            "metrics": [
                {"name": "sessions"}, {"name": "conversions"}, {"name": "totalRevenue"},
            ],
            "limit": str(_row_limit(row_limit)),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    rows: list[dict[str, Any]] = []
    for item in body.get("rows", []):
        if not isinstance(item, dict):
            continue
        dimensions = [
            entry.get("value", "") for entry in item.get("dimensionValues", [])
            if isinstance(entry, dict)
        ]
        metrics = [
            entry.get("value", "") for entry in item.get("metricValues", [])
            if isinstance(entry, dict)
        ]
        rows.append({
            "date": dimensions[0] if len(dimensions) > 0 else "",
            "pagePath": dimensions[1] if len(dimensions) > 1 else "",
            "sessions": metrics[0] if len(metrics) > 0 else "",
            "conversions": metrics[1] if len(metrics) > 1 else "",
            "totalRevenue": metrics[2] if len(metrics) > 2 else "",
        })
    return rows


def generate_llm_text(prompt: str) -> str:
    """Call an explicitly configured LLM for an assistive draft, never evidence."""
    if not connector_readiness()["llm_provider"]:
        raise ConnectorUnavailable("LLM connector is disabled or has no API key")
    text = str(prompt or "").strip()
    if not text or len(text) > 8000:
        raise ConnectorUnavailable("A prompt of 1-8000 characters is required")
    body = _post_json(
        LLM_ENDPOINT,
        payload={
            "model": settings.llm_model,
            "max_tokens": 500,
            "messages": [{"role": "user", "content": text}],
        },
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
    )
    choices = body.get("choices") or []
    content = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        content = message.get("content", "") if isinstance(message, dict) else ""
    if not isinstance(content, str) or not content.strip():
        raise ConnectorUnavailable("LLM response contained no text")
    return content.strip()


def assistive_llm_text(prompt: str) -> dict[str, Any]:
    """Label generated text so it can never be mistaken for an observation."""
    return {
        "text": generate_llm_text(prompt),
        "generated": True,
        "note": "Model-generated draft. Not a verified observation, public-evidence finding or measured metric.",
    }
