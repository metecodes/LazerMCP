"""ArtifactRepository — metadata only. No SVG/DXF bytes in SQL."""

from __future__ import annotations

import uuid
from typing import Any

from persist.db import connect
from studio_store import now_iso


class ArtifactRepository:
    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "id": row.get("id") or str(uuid.uuid4()),
            "organization_id": row["organization_id"],
            "project_id": row.get("project_id"),
            "version_id": row.get("version_id"),
            "kind": row["kind"],
            "storage_path": row["storage_path"],
            "file_size": int(row["file_size"]),
            "mime_type": row["mime_type"],
            "hash": row["hash"],
            "created_at": row.get("created_at") or now_iso(),
            "expires_at": row.get("expires_at"),
            "source_file_id": row.get("source_file_id"),
        }
        if "bytes" in payload or (isinstance(payload.get("hash"), (bytes, bytearray))):
            raise ValueError("artifact metadata must not contain file bytes")
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (
                  id, organization_id, project_id, version_id, kind, storage_path,
                  file_size, mime_type, hash, created_at, expires_at, source_file_id
                ) VALUES (
                  :id, :organization_id, :project_id, :version_id, :kind, :storage_path,
                  :file_size, :mime_type, :hash, :created_at, :expires_at, :source_file_id
                )
                """,
                payload,
            )
            conn.commit()
        return payload

    def get(self, artifact_id: str) -> dict[str, Any] | None:
        with connect() as conn:
            row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        return dict(row) if row else None

    def by_source(self, source_file_id: str) -> dict[str, Any] | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM artifacts WHERE source_file_id = ? ORDER BY created_at DESC",
                (source_file_id,),
            ).fetchone()
        return dict(row) if row else None

    def expired(self, now: str) -> list[dict[str, Any]]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (now,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, artifact_id: str) -> None:
        with connect() as conn:
            conn.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
            conn.commit()
