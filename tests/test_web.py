import time

import pytest


class FakeResponse:
    def __init__(self, url, content):
        self.url, self.content = url, content.encode()

    def raise_for_status(self):
        pass


RSS = "<rss version='2.0'><channel><title>Beispiel</title><item><link>https://x.example/1</link></item></channel></rss>"


@pytest.fixture
def pages(app_module, monkeypatch):
    pages = {}

    def fetch_url(url):
        if url not in pages:
            raise app_module.requests.ConnectionError("404")
        return FakeResponse(url, pages[url])
    monkeypatch.setattr(app_module, "fetch_url", fetch_url)
    return pages


def test_discover_a_feed_url_directly(app_module, pages):
    pages["https://x.example/feed"] = RSS
    assert app_module.discover_feeds("https://x.example/feed") == [{"url": "https://x.example/feed", "title": "Beispiel"}]


def test_discover_link_rel_alternate(app_module, pages):
    pages["https://x.example/blog/"] = """<html><head>
        <link rel="alternate" type="application/rss+xml" title="Artikel" href="/feed.xml">
        <link rel="alternate" type="application/atom+xml" title="Kommentare" href="https://x.example/comments.atom">
        <link rel="alternate" type="application/json" href="/wp-json/wp/v2/posts/1">
        <link rel="alternate" hreflang="en" href="/en/">
        </head></html>"""
    assert app_module.discover_feeds("https://x.example/blog/") == [
        {"url": "https://x.example/feed.xml", "title": "Artikel"},
        {"url": "https://x.example/comments.atom", "title": "Kommentare"},
    ]


def test_discover_falls_back_to_common_paths(app_module, pages):
    pages["https://x.example/"] = "<html><head><title>Ohne Link</title></head></html>"
    pages["https://x.example/rss"] = RSS
    assert app_module.discover_feeds("https://x.example/")[0]["url"] == "https://x.example/rss"


def test_discover_nothing(app_module, pages):
    pages["https://x.example/"] = "<html></html>"
    assert app_module.discover_feeds("https://x.example/") == []


def test_job_captures_output_live(app_module, monkeypatch):
    monkeypatch.setitem(app_module.JOBS, "test", ("Test", ["python3", "-c",
        "import time, os; print('eins'); time.sleep(1); print('zwei', os.getcwd() != '/app'); raise SystemExit(3)"]))
    job, started = app_module.start_job("test")
    assert started
    again, started_again = app_module.start_job("test")
    assert again is job and not started_again
    deadline = time.time() + 10
    while job.finished is None and time.time() < deadline:
        time.sleep(0.1)
    state = job.state()
    assert state["lines"] == ["eins", "zwei True"]
    assert state["returncode"] == 3 and not state["running"]
    assert job.state(since=1)["lines"] == ["zwei True"]
