"""Environment flags. Never print secrets."""

from __future__ import annotations

import os


def is_production() -> bool:
    if os.environ.get("VERCEL") == "1":
        return True
    return (os.environ.get("MCP_ENV") or "").strip().lower() in {"production", "prod"}


def supabase_url() -> str:
    return (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")


def supabase_anon_key() -> str:
    return (
        os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_PUBLISHABLE_KEY") or ""
    ).strip()


def supabase_service_role() -> str:
    return (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()


def storage_bucket() -> str:
    return (os.environ.get("LASERMCP_STORAGE_BUCKET") or "cikti").strip()


def uses_supabase_app_db() -> bool:
    return bool(supabase_url() and supabase_service_role())
