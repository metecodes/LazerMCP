"""SQLite application database. Matches migrations/0001_sprint_0_5.sql."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from studio_store import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('personal', 'workspace')),
  name TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS organization_members (
  organization_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
  created_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, user_id)
);
CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT,
  version_id TEXT,
  kind TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  file_size INTEGER NOT NULL,
  mime_type TEXT NOT NULL,
  hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  source_file_id TEXT
);
CREATE INDEX IF NOT EXISTS artifacts_org ON artifacts (organization_id);
CREATE INDEX IF NOT EXISTS artifacts_source ON artifacts (source_file_id);
CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  hash TEXT NOT NULL UNIQUE,
  prefix TEXT,
  owner_user_id TEXT,
  organization_id TEXT,
  role TEXT,
  plan TEXT,
  kind TEXT,
  email TEXT,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  expires_at TEXT,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS api_keys_hash ON api_keys (hash);
CREATE INDEX IF NOT EXISTS api_keys_owner ON api_keys (owner_user_id);
"""


def db_path() -> Path:
    path = data_dir() / "app.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
