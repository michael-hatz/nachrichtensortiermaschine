import feedparser
import pytest

FEED = "https://feed.example/rss"


def make_feed(items):
    xml = "<rss version='2.0'><channel><title>t</title>" + "".join(
        f"<item><title>{title}</title><link>{link}</link>" + (f"<guid>{guid}</guid>" if guid else "") + "</item>"
        for title, link, guid in items) + "</channel></rss>"
    return feedparser.parse(xml)


@pytest.fixture
def db(nsm, monkeypatch, tmp_path):
    import common
    import feeddb
    monkeypatch.setattr(common, "DB_PATH", str(tmp_path / "nsm.db"))
    db = feeddb.open_db()
    yield db
    db.close()


def test_normalize_url_strips_tracking(nsm):
    assert (nsm.normalize_url("https://Example.com/a?id=5&utm_source=rss&utm_medium=feed&fbclid=x#top")
            == "https://example.com/a?id=5")


def test_normalize_url_keeps_query_untouched_without_tracking(nsm):
    url = "https://example.com/search?q=a%20b&ref=main"
    assert nsm.normalize_url(url) == url


def test_seen_with_different_tracking_parameters(nsm, db):
    first = make_feed([("A", "https://example.com/a?utm_source=rss", None)])
    nsm.mark_seen(db, FEED, nsm.new_entries(first, db, FEED))
    again = make_feed([("A", "https://example.com/a?utm_source=newsletter", None)])
    assert nsm.new_entries(again, db, FEED) == []


def test_seen_by_guid_when_link_changes(nsm, db):
    first = make_feed([("A", "https://example.com/a", "article-1")])
    nsm.mark_seen(db, FEED, nsm.new_entries(first, db, FEED))
    moved = make_feed([("A", "https://example.com/2026/a-renamed", "article-1")])
    assert nsm.new_entries(moved, db, FEED) == []


def test_guid_is_scoped_to_the_feed(nsm, db):
    nsm.mark_seen(db, FEED, nsm.new_entries(make_feed([("A", "https://a.example/1", "1")]), db, FEED))
    other = make_feed([("B", "https://b.example/1", "1")])
    assert len(nsm.new_entries(other, db, "https://other.example/rss")) == 1


def test_legacy_raw_links_still_count(nsm, db):
    raw = "https://example.com/a?utm_source=rss"
    db.execute("INSERT INTO seen_urls (url) VALUES (?)", (raw,))
    assert nsm.new_entries(make_feed([("A", raw, None)]), db, FEED) == []


def test_duplicates_within_one_feed(nsm, db):
    feed = make_feed([("A", "https://example.com/a?utm_source=x", "1"), ("A", "https://example.com/a", "2")])
    assert len(nsm.new_entries(feed, db, FEED)) == 1
