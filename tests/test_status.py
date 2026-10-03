import sqlite3

import pytest

import common
import feeddb

FEED = "https://feed.example/rss"


@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setattr(common, "DB_PATH", str(tmp_path / "nsm.db"))
    db = feeddb.open_db()
    yield db
    db.close()


def test_old_database_gets_the_sent_column(monkeypatch, tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE seen_urls (url TEXT PRIMARY KEY, feed TEXT, seen_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    old.execute("INSERT INTO seen_urls (url, feed) VALUES ('https://a.example/1', ?)", (FEED,))
    old.commit()
    old.close()
    monkeypatch.setattr(common, "DB_PATH", str(path))
    db = feeddb.open_db()
    [row] = feeddb.feed_overview(db, [("Feed", FEED, True)])
    assert (row["sent_total"], row["known"]) == (0, 1)


def test_overview_counts_only_sent_articles(nsm, db):
    import feedparser
    feed = feedparser.parse("<rss version='2.0'><channel><title>t</title>"
                            "<item><link>https://a.example/1</link><guid>1</guid></item>"
                            "<item><link>https://a.example/2</link><guid>2</guid></item></channel></rss>")
    sent, skipped = feed.entries
    nsm.mark_seen(db, FEED, [sent], sent=True)
    nsm.mark_seen(db, FEED, [skipped])
    feeddb.record_run(db, "Feed")
    [row] = feeddb.feed_overview(db, [("Feed", FEED, True)])
    assert (row["sent_total"], row["sent_30_days"], row["known"]) == (1, 1, 2)
    assert row["last_success"] and row["last_article"] and row["last_error"] is None


def test_overview_shows_a_failing_feed(db):
    feeddb.record_run(db, "Feed")
    feeddb.record_run(db, "Feed", "HTTPError: 404")
    [row] = feeddb.feed_overview(db, [("Feed", FEED, True)])
    assert row["last_error"] == "HTTPError: 404"
    assert row["last_success"]  # the earlier successful run is kept


def test_new_failure_after_recovery_is_reported_right_away(nsm, db):
    assert nsm.feed_error_due(db, "Feed", True)[0]
    nsm.mark_feed_error_mailed(db, ["Feed"])
    assert not nsm.feed_error_due(db, "Feed", True)[0]  # still failing: throttled
    nsm.feed_error_due(db, "Feed", False)  # works again
    assert nsm.feed_error_due(db, "Feed", True)[0]
