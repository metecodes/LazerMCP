"""Idempotent JSON → durable api_keys copy. Does not delete the JSON store."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from persist.keys_repo import KeyRepository
from persist.orgs import ensure_personal_org
from studio_store import data_dir


def json_path() -> Path:
    return data_dir() / "api_keys.json"


def load_json() -> list[dict]:
    path = json_path()
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, list) else []


def migrate(*, dry_run: bool = True) -> dict[str, int]:
    repo = KeyRepository()
    copied = 0
    skipped = 0
    for row in load_json():
        digest = str(row.get("hash") or "")
        if not digest:
            skipped += 1
            continue
        if repo.by_hash(digest):
            skipped += 1
            continue
        owner = str(row.get("owner") or "")
        org_id = ""
        if owner and not dry_run:
            org_id = ensure_personal_org(owner, str(row.get("email") or owner))
        token_hint = str(row.get("prefix") or "lzr_")
        if dry_run:
            copied += 1
            continue
        repo.insert(
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "hash": digest,
                "prefix": token_hint,
                "owner_user_id": owner,
                "organization_id": org_id,
                "role": row.get("role"),
                "plan": row.get("plan"),
                "kind": row.get("kind"),
                "email": row.get("email"),
                "created_at": row.get("created"),
                "last_used_at": row.get("last_used"),
            }
        )
        copied += 1
    return {"copied": copied, "skipped": skipped, "dry_run": int(dry_run)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy hashed JSON API keys into app.sqlite. Never prints secrets.")
    parser.add_argument("--apply", action="store_true", help="Write rows. Default is dry-run.")
    args = parser.parse_args()
    stats = migrate(dry_run=not args.apply)
    print(f"migrate_json_keys copied={stats['copied']} skipped={stats['skipped']} dry_run={stats['dry_run']}")
    print(f"source={json_path()} (left in place)")


if __name__ == "__main__":
    main()
