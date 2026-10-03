# -*- coding: utf-8 -*-
"""Queue of read-later links saved via the web interface or the bookmarklet.
app.py adds the links, pocket-ersatz.py fetches the articles and mails them."""

import sqlite3

DB_PATH = "/app/data/nsm.db"
MAX_ATTEMPTS = 3  # a link that fails this often is given up


def open_db():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.execute("""CREATE TABLE IF NOT EXISTS readlater_queue (
        id INTEGER PRIMARY KEY,
        url TEXT NOT NULL,
        title TEXT,
        added_at TEXT DEFAULT (datetime('now', 'localtime')),
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        done_at TEXT)""")
    return db


def _pending_condition():
    return f"done_at IS NULL AND attempts < {MAX_ATTEMPTS}"


def add(db, url, title=None):
    """Queue url; returns False if it is already waiting to be processed."""
    with db:
        if db.execute(f"SELECT 1 FROM readlater_queue WHERE url = ? AND {_pending_condition()}", (url,)).fetchone():
            return False
        db.execute("INSERT INTO readlater_queue (url, title) VALUES (?, ?)", (url, title or None))
    return True


def next_pending(db, skip_ids=()):
    """Return (id, url, title) of the oldest unprocessed link, leaving out skip_ids, or None."""
    skip_ids = list(skip_ids)
    placeholders = ",".join("?" * len(skip_ids))
    exclude = f" AND id NOT IN ({placeholders})" if skip_ids else ""
    return db.execute(f"SELECT id, url, title FROM readlater_queue WHERE {_pending_condition()}{exclude} "
                      "ORDER BY id LIMIT 1", skip_ids).fetchone()


def mark_done(db, item_id):
    with db:
        db.execute("UPDATE readlater_queue SET done_at = datetime('now', 'localtime'), last_error = NULL "
                   "WHERE id = ?", (item_id,))


def mark_failed(db, item_id, error):
    with db:
        db.execute("UPDATE readlater_queue SET attempts = attempts + 1, last_error = ? WHERE id = ?",
                   (str(error)[:500], item_id))


def recent(db, limit=15):
    """The newest links with their state: queued, retrying, sent or failed."""
    items = []
    for url, title, added_at, attempts, last_error, done_at in db.execute(
            "SELECT url, title, added_at, attempts, last_error, done_at FROM readlater_queue "
            "ORDER BY id DESC LIMIT ?", (limit,)):
        if done_at:
            state = "sent"
        elif attempts >= MAX_ATTEMPTS:
            state = "failed"
        elif attempts:
            state = "retrying"
        else:
            state = "queued"
        items.append({"url": url, "title": title, "added_at": added_at, "state": state,
                      "attempts": attempts, "error": last_error, "done_at": done_at})
    return items
