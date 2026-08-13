from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
  id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, path TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL, type TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL,
  body TEXT NOT NULL, content_hash TEXT NOT NULL, storage_tier TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN (0,1)), indexed_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
  page_id UNINDEXED, slug, title, body, tokenize='unicode61'
);
CREATE TABLE IF NOT EXISTS links (
  source_id TEXT NOT NULL, target_ref TEXT NOT NULL, target_id TEXT, link_type TEXT NOT NULL, line INTEGER NOT NULL,
  PRIMARY KEY(source_id,target_ref,link_type,line),
  FOREIGN KEY(source_id) REFERENCES pages(id) ON DELETE CASCADE,
  FOREIGN KEY(target_id) REFERENCES pages(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS facts (
  page_id TEXT NOT NULL, subject TEXT NOT NULL, predicate TEXT NOT NULL, object TEXT NOT NULL, line INTEGER NOT NULL,
  PRIMARY KEY(page_id,subject,predicate,object,line), FOREIGN KEY(page_id) REFERENCES pages(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, started TEXT NOT NULL,
  finished TEXT, status TEXT NOT NULL, dry_run INTEGER NOT NULL CHECK(dry_run IN (0,1)), summary TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS audit (
  seq INTEGER PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL, object_hash TEXT NOT NULL,
  detail TEXT NOT NULL, prev_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS source_checkpoints (
  source_id TEXT NOT NULL, source_path TEXT NOT NULL, content_hash TEXT NOT NULL,
  checked_at TEXT NOT NULL, PRIMARY KEY(source_id,source_path)
);
CREATE INDEX IF NOT EXISTS pages_updated ON pages(updated);
CREATE INDEX IF NOT EXISTS facts_key ON facts(subject,predicate);
CREATE INDEX IF NOT EXISTS links_target ON links(target_id);
"""


def _limits(conn: sqlite3.Connection) -> None:
    if not hasattr(conn, "setlimit"):
        return
    for category, value in (
        (sqlite3.SQLITE_LIMIT_LENGTH, 16 * 1024 * 1024),
        (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 1 * 1024 * 1024),
        (sqlite3.SQLITE_LIMIT_COLUMN, 256),
        (sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 32),
        (sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 512),
        (sqlite3.SQLITE_LIMIT_ATTACHED, 0),
        (sqlite3.SQLITE_LIMIT_LIKE_PATTERN_LENGTH, 4096),
    ):
        conn.setlimit(category, value)


def connect(path: Path, *, initialize: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=5.0)
    try:
        path.chmod(0o600)
        conn.row_factory = sqlite3.Row
        _limits(conn)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        if initialize:
            conn.executescript(SCHEMA)
        try:
            conn.execute("PRAGMA trusted_schema=OFF")
        except sqlite3.DatabaseError:
            # Older SQLite versions do not expose this hardening pragma.
            pass
        return conn
    except BaseException:
        conn.close()
        raise


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()
