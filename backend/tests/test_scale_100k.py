from __future__ import annotations

import os
import time

import pytest
from sqlalchemy import func, select

from app.models.auth import Organization
from app.models.inventory import UrlRecord
from app.models.projects import Project
from app.services.imports import upsert_urls


@pytest.mark.slow
def test_100k_url_inventory_imports_and_pages_without_full_load(client, db, auth_headers):
    """Acceptance check for the 100,000+ URL requirement.

    The API must return a bounded page with total counts; it must never serialise
    the full inventory into the browser. Run with `pytest -q -m slow` to include.
    """
    target = int(os.environ.get("SEO_LAB_SCALE_URLS", "100000"))
    org = Organization(name="Scale test org", slug="scale-test-org")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name=f"Scale test {target:,}", domain="scale.example.com")
    db.add(project)
    db.commit()

    urls = (f"https://scale.example.com/products/category-{i % 50}/product-{i}/" for i in range(target))
    started = time.perf_counter()
    accepted, rejected, errors = upsert_urls(
        db, project.id, urls, "scale_test", "imported", batch_size=5000,
    )
    db.commit()
    elapsed = time.perf_counter() - started

    assert accepted == target
    assert rejected == 0
    assert errors == []
    assert db.scalar(select(func.count()).select_from(UrlRecord).where(
        UrlRecord.project_id == project.id
    )) == target
    assert elapsed < 90, f"100k URL import took {elapsed:.1f}s"

    last_page = client.get(
        f"/api/v1/inventory/urls?project_id={project.id}&limit=50&offset={target - 50}",
        headers=auth_headers,
    )
    assert last_page.status_code == 200, last_page.text
    payload = last_page.json()
    assert payload["total"] == target
    assert len(payload["items"]) == 50
    assert payload["has_more"] is False
    assert payload["page"] == target // 50
    assert payload["items"][-1]["url"].endswith(f"product-{target - 1}/")
    assert len(last_page.content) < 200_000
