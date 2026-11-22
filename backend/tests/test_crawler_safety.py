from __future__ import annotations

from app.services.crawler import CrawlConfig, CrawlEngine


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


def test_cancellation_stops_before_any_request(monkeypatch, db):
    FakeClient.calls = []
    monkeypatch.setattr("app.services.crawler.httpx.Client", FakeClient)
    config = CrawlConfig.from_dict({
        "start_url": "https://demo.example.com/",
        "max_urls": 5, "concurrency": 1, "crawl_delay": 0,
        "respect_robots": True, "sitemap_discovery": False,
    })
    engine = CrawlEngine(db, 1, 999999, None, config, cancelled=lambda: True)
    stats = engine.run()
    assert stats["crawled"] == 0
    assert any("Cancelled" in str(item) for item in stats["errors"])
    assert FakeClient.calls == []
