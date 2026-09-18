"""Delete expired artifact bytes before metadata; failed deletes remain retryable."""

from __future__ import annotations

from persist.artifacts import ArtifactRepository
from persist.storage import StorageService
from studio_store import now_iso


def cleanup_expired(now: str | None = None) -> int:
    stamp = now or now_iso()
    repo = ArtifactRepository()
    store = StorageService()
    n = 0
    for row in repo.expired(stamp):
        try:
            store.delete(str(row.get("storage_path") or ""))
        except Exception:
            continue
        repo.delete(str(row["id"]))
        n += 1
    return n
