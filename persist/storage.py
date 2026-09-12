"""StorageService — private object bytes. Never put CAD in Postgres."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from persist.env import storage_bucket, uses_supabase_app_db
from studio_store import data_dir, now_iso

SIGNED_TTL_SEC = 10 * 60


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ext_for(mime: str, name: str = "") -> str:
    if name and "." in name:
        return name.rsplit(".", 1)[-1].lower()
    return {
        "image/svg+xml": "svg",
        "image/vnd.dxf": "dxf",
        "application/dxf": "dxf",
        "image/webp": "webp",
        "image/png": "png",
        "application/json": "json",
        "text/markdown": "md",
        "text/plain": "txt",
    }.get(mime, "bin")


class StorageService:
    def root(self) -> Path:
        path = data_dir() / "objects"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def durable_path(self, organization_id: str, artifact_id: str, digest: str, ext: str) -> str:
        return f"artifacts/{organization_id}/{artifact_id}/{digest}.{ext}"

    def tmp_path(self, organization_id: str, ext: str) -> str:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return f"tmp/{organization_id}/{day}/{uuid.uuid4()}.{ext}"

    def put(self, storage_path: str, data: bytes, mime_type: str) -> None:
        if uses_supabase_app_db():
            from persist.supabase_rest import storage_upload

            storage_upload(storage_bucket(), storage_path, data, mime_type)
            return
        dest = (self.root() / storage_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def get(self, storage_path: str) -> bytes:
        if uses_supabase_app_db():
            from persist.supabase_rest import storage_download

            return storage_download(storage_bucket(), storage_path)
        dest = (self.root() / storage_path).resolve()
        if self.root() not in dest.parents and dest != self.root():
            raise FileNotFoundError(storage_path)
        if not dest.is_file():
            raise FileNotFoundError(storage_path)
        return dest.read_bytes()

    def delete(self, storage_path: str) -> None:
        if uses_supabase_app_db():
            from persist.supabase_rest import storage_delete

            storage_delete(storage_bucket(), storage_path)
            return
        dest = self.root() / storage_path
        if dest.is_file():
            dest.unlink()

    def signed_url(self, storage_path: str, ttl: int = SIGNED_TTL_SEC) -> str | None:
        if uses_supabase_app_db():
            from persist.supabase_rest import storage_signed_url

            return storage_signed_url(storage_bucket(), storage_path, ttl)
        return None


def maybe_webp(png_bytes: bytes) -> tuple[bytes, str]:
    """Prefer WebP for persistent previews. PNG if conversion is unavailable."""
    try:
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(png_bytes))
        out = BytesIO()
        img.save(out, format="WEBP", quality=82, method=4)
        data = out.getvalue()
        if data:
            return data, "image/webp"
    except Exception:
        pass
    return png_bytes, "image/png"


def expires_in_hours(hours: int = 24) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0).isoformat()


def dump_meta(row: dict[str, Any]) -> str:
    return json.dumps({k: v for k, v in row.items() if k != "bytes"}, ensure_ascii=False)
