"""Optional PostgREST + Storage via service role. Never send this key to a browser."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from persist.env import supabase_service_role, supabase_url


def _headers(json_body: bool = True) -> dict[str, str]:
    key = supabase_service_role()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def storage_upload(bucket: str, path: str, data: bytes, mime: str) -> None:
    url = f"{supabase_url()}/storage/v1/object/{bucket}/{path}"
    req = urllib.request.Request(url, data=data, method="POST", headers={**_headers(False), "Content-Type": mime})
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def storage_download(bucket: str, path: str) -> bytes:
    url = f"{supabase_url()}/storage/v1/object/{bucket}/{path}"
    req = urllib.request.Request(url, method="GET", headers=_headers(False))
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def storage_delete(bucket: str, path: str) -> None:
    url = f"{supabase_url()}/storage/v1/object/{bucket}/{path}"
    req = urllib.request.Request(url, method="DELETE", headers=_headers(False))
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
    except urllib.error.HTTPError:
        pass


def storage_signed_url(bucket: str, path: str, ttl: int) -> str | None:
    url = f"{supabase_url()}/storage/v1/object/sign/{bucket}/{path}"
    body = json.dumps({"expiresIn": int(ttl)}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload: Any = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    signed = payload.get("signedURL") or payload.get("signedUrl")
    if not signed:
        return None
    if str(signed).startswith("http"):
        return str(signed)
    return f"{supabase_url()}/storage/v1{signed}"
