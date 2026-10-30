# -*- coding: utf-8 -*-
"""Database of nsm.py: mailed articles (seen_urls) and the state of every feed. nsm.py writes
it, the status page of the web app reads it."""


import common


def open_db():
    db = common.connect_db()
    db.execute("""CREATE TABLE IF NOT EXISTS seen_urls (
        url TEXT PRIMARY KEY,
        feed TEXT,
        seen_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    # 1 = the article was mailed, 0 = only remembered (first run of a feed, broken article),
    # NULL = from a version that didn't record it
    if "sent" not in [row[1] for row in db.execute("PRAGMA table_info(seen_urls)")]:
        db.execute("ALTER TABLE seen_urls ADD COLUMN sent INTEGER")
    db.execute("""CREATE TABLE IF NOT EXISTS feed_errors (
        feed TEXT PRIMARY KEY,
        failing_since TEXT,
        last_mailed TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS feed_status (
        feed TEXT PRIMARY KEY,
        last_run TEXT,
        last_success TEXT,
        last_error TEXT)""")
    db.commit()
    return db


def record_run(db, section, error=None):
    """Remember the result of fetching a feed; error is None if the feed itself worked."""
    with db:
        db.execute("INSERT OR IGNORE INTO feed_status (feed) VALUES (?)", (section,))
        if error is None:
            db.execute("UPDATE feed_status SET last_run = datetime('now', 'localtime'), "
                       "last_success = datetime('now', 'localtime'), last_error = NULL WHERE feed = ?", (section,))
        else:
            db.execute("UPDATE feed_status SET last_run = datetime('now', 'localtime'), last_error = ? "
                       "WHERE feed = ?", (error[-2000:], section))


def feed_overview(db, feeds):
    """Status of the feeds, given as [(section, url, active)], in that order."""
    result = []
    for section, url, active in feeds:
        status = db.execute("SELECT last_run, last_success, last_error FROM feed_status WHERE feed = ?",
                            (section,)).fetchone() or (None, None, None)
        failing_since = (db.execute("SELECT failing_since FROM feed_errors WHERE feed = ?", (section,)).fetchone()
                         or (None,))[0]
        sent_total, sent_30_days, last_article = db.execute(
            "SELECT COUNT(*), SUM(seen_at >= datetime('now', '-30 days')), MAX(datetime(seen_at, 'localtime')) "
            "FROM seen_urls WHERE feed = ? AND sent = 1 AND url NOT LIKE 'guid:%'", (url,)).fetchone()
        known = db.execute("SELECT COUNT(*) FROM seen_urls WHERE feed = ? AND url NOT LIKE 'guid:%'",
                           (url,)).fetchone()[0]
        result.append({
            "name": section, "url": url, "active": active,
            "last_run": status[0], "last_success": status[1], "last_error": status[2],
            "failing_since": failing_since,
            "sent_total": sent_total, "sent_30_days": sent_30_days or 0, "last_article": last_article,
            "known": known,
        })
    return result
