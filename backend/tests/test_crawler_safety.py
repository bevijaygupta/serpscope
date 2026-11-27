from __future__ import annotations

from app.db.session import SessionLocal
from app.models.inventory import Crawl
from app.models.projects import Job
from app.services.crawler import CrawlConfig, CrawlEngine
from app.services.jobs import progress


class FakeResponse:
    def __init__(self, status_code: int, text: str = "", headers: dict | None = None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.content = text.encode("utf-8")
        self.url = "https://demo.example.com/"


class FakeClient:
    calls: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url: str, **kwargs):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FakeResponse(200, "User-agent: *\nDisallow: /\n")
        return FakeResponse(200, "<html><title>Should not be fetched</title></html>",
                            {"content-type": "text/html"})


class SitemapFakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url: str, **kwargs):
        if url.endswith("/robots.txt"):
            return FakeResponse(
                200,
                "User-agent: *\nAllow: /\nSitemap: https://demo.example.com/sitemap_index.xml\n",
            )
        if url.endswith("/sitemap_index.xml"):
            return FakeResponse(200, (
                '<?xml version="1.0"?>'
                '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                '<sitemap><loc>https://demo.example.com/post-sitemap.xml</loc></sitemap>'
                '</sitemapindex>'
            ), {"content-type": "application/xml"})
        if url.endswith("/post-sitemap.xml"):
            return FakeResponse(200, (
                '<?xml version="1.0"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                '<url><loc>https://demo.example.com/from-sitemap/</loc></url>'
                '</urlset>'
            ), {"content-type": "application/xml"})
        return FakeResponse(200, "<html><head><title>From sitemap</title></head><body>Hello</body></html>",
                            {"content-type": "text/html"})


def test_robots_disallow_is_checked_before_page_request(monkeypatch, db):
    FakeClient.calls = []
    monkeypatch.setattr("app.services.crawler.httpx.Client", FakeClient)
    config = CrawlConfig.from_dict({
        "start_url": "https://demo.example.com/",
        "max_urls": 1, "concurrency": 1, "crawl_delay": 0,
        "respect_robots": True, "sitemap_discovery": False,
    })
    engine = CrawlEngine(db, 1, 999999, None, config)
    stats = engine.run()
    assert stats["excluded"] == 1
    assert stats["crawled"] == 0
    assert FakeClient.calls == ["https://demo.example.com/robots.txt"]


def test_sitemap_discovery_releases_write_lock_before_progress(monkeypatch, db, demo_project):
    """Progress is written through another session; SQLite allows one writer."""
    monkeypatch.setattr("app.services.crawler.httpx.Client", SitemapFakeClient)
    job = Job(name="Progress test", job_type="test", status="running")
    db.add(job)
    db.flush()
    crawl = Crawl(project_id=demo_project["project_id"], job_id=job.id, name="Sitemap progress test")
    db.add(crawl)
    db.commit()
    config = CrawlConfig.from_dict({
        "start_url": "https://demo.example.com/",
        "max_urls": 1, "max_depth": 0, "concurrency": 1, "crawl_delay": 0,
        "respect_robots": True, "sitemap_discovery": True,
    })
    engine = CrawlEngine(
        db, demo_project["project_id"], crawl.id, job.id, config,
        on_progress=lambda value, total, message: progress(job.id, value, total, message),
    )
    stats = engine.run()
    assert stats["crawled"] == 1
    assert stats["sitemap"]["sitemap_urls"] >= 1
    fresh = SessionLocal()
    try:
        stored = fresh.get(Job, job.id)
        assert stored.progress >= 1
    finally:
        fresh.close()


def test_cancellation_stops_before_any_request(monkeypatch, db):
    FakeClient.calls = []
    monkeypatch.setattr("app.services.crawler.httpx.Client", FakeClient)
    config = CrawlConfig.from_dict({
        "start_url": "https://demo.example.com/",
        "max_urls": 5, "concurrency": 1, "crawl_delay": 0,
        "respect_robots": True, "sitemap_discovery": True,
    })
    engine = CrawlEngine(db, 1, 999999, None, config, cancelled=lambda: True)
    stats = engine.run()
    assert stats["crawled"] == 0
    assert any("Cancelled" in str(item) for item in stats["errors"])
    assert FakeClient.calls == []


def test_redirect_to_private_host_is_not_followed(monkeypatch, db):
    calls: list[str] = []

    class RedirectClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url: str, **kwargs):
            calls.append(url)
            if url.endswith("/robots.txt"):
                return FakeResponse(200, "User-agent: *\nAllow: /\n")
            if url == "https://demo.example.com/start":
                return FakeResponse(302, "", {"location": "http://127.0.0.1/admin"})
            return FakeResponse(200, "<html><title>Should not be fetched</title></html>",
                                {"content-type": "text/html"})

    monkeypatch.setattr("app.services.crawler.httpx.Client", RedirectClient)
    config = CrawlConfig.from_dict({
        "start_url": "https://demo.example.com/start",
        "max_urls": 1, "concurrency": 1, "crawl_delay": 0,
        "respect_robots": True, "sitemap_discovery": False,
    })
    stats = CrawlEngine(db, 1, 999999, None, config).run()
    assert stats["crawled"] == 0
    assert stats["excluded"] == 1
    assert calls == ["https://demo.example.com/robots.txt", "https://demo.example.com/start"]


def test_crawler_config_ignores_caller_network_overrides():
    config = CrawlConfig.from_dict({
        "start_url": "https://demo.example.com/",
        "allow_private": True,
        "auth_headers": {"Authorization": "Bearer secret"},
    })
    assert config.allow_private is False
    assert config.auth_headers == {}
