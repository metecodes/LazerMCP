"""Optional PostgREST + Storage via service role. Never send this key to a browser."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlencode
from typing import Any

from persist.env import supabase_service_role, supabase_url


def rest(path: str, *, method: str = "GET", params: dict | None = None,
         body: Any = None, prefer: str = "") -> Any:
    """Service-role metadata requests. Fail closed; never fall back to /tmp."""
    url = f"{supabase_url()}/rest/v1/{path}"
    if params:
        url += "?" + urlencode(params)
    headers = _headers()
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


def rows(table: str, **filters) -> list[dict]:
    if "limit" in filters:
        return rest(table, params={"select": "*", **filters}) or []
    found = []
    while True:
        page = rest(table, params={"select": "*", **filters, "limit": 1000, "offset": len(found)}) or []
        found.extend(page)
        if len(page) < 1000:
            return found


def upsert(table: str, payload: Any, conflict: str = "id", *, ignore: bool = False):
    resolution = "ignore-duplicates" if ignore else "merge-duplicates"
    return rest(table, method="POST", params={"on_conflict": conflict}, body=payload,
                prefer=f"resolution={resolution},return=representation")


def _headers(json_body: bool = True) -> dict[str, str]:
    key = supabase_service_role()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers



def storage_create_bucket(bucket: str, public: bool = True) -> None:
    url = f"{supabase_url()}/storage/v1/bucket"
    body = json.dumps({"id": bucket, "name": bucket, "public": public}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError:
        pass

def storage_upload(bucket: str, path: str, data: bytes, mime: str) -> None:

    url = f"{supabase_url()}/storage/v1/object/{bucket}/{path}"
    req = urllib.request.Request(url, data=data, method="POST", headers={**_headers(False), "Content-Type": mime, "x-upsert": "true"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def storage_download(bucket: str, path: str) -> bytes:
    url = f"{supabase_url()}/storage/v1/object/{bucket}/{path}"
    req = urllib.request.Request(url, method="GET", headers=_headers(False))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise FileNotFoundError(path) from exc
        if exc.code == 400:
            try:
                error = json.loads(exc.read())
            except (ValueError, TypeError):
                error = {}
            if str(error.get("statusCode")) == "404" or error.get("error") == "not_found" or error.get("message") == "Object not found":
                raise FileNotFoundError(path) from exc
        raise


def storage_delete(bucket: str, path: str) -> None:
    url = f"{supabase_url()}/storage/v1/object/{bucket}"
    req = urllib.request.Request(url, data=json.dumps({"prefixes": [path]}).encode("utf-8"), method="DELETE", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise


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
