"""Sprint 0.5 durability and tenant isolation."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class _Iso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = {
            key: os.environ.get(key)
            for key in (
                "MCP_DATA_DIR",
                "MCP_ENV",
                "VERCEL",
                "MCP_SESSION_SECRET",
                "SUPABASE_URL",
                "SUPABASE_ANON_KEY",
                "SUPABASE_SERVICE_ROLE_KEY",
                "LASERMCP_ORG_DOMAINS",
            )
        }
        os.environ["MCP_DATA_DIR"] = self.tmp
        for key in ("MCP_ENV", "VERCEL", "MCP_SESSION_SECRET", "SUPABASE_SERVICE_ROLE_KEY"):
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class SessionSecretTests(_Iso):
    def test_dev_fallback_signs(self):
        from supabase_auth import new_session, session_user

        sid = new_session({"id": "u1", "email": "a@b.com", "name": "A"})
        self.assertEqual(session_user(sid)["email"], "a@b.com")

    def test_production_missing_secret_fails(self):
        os.environ["MCP_ENV"] = "production"
        from supabase_auth import SessionSecretError, new_session

        with self.assertRaises(SessionSecretError):
            new_session({"id": "u1", "email": "a@b.com", "name": "A"})

    def test_production_rejects_anon_key_as_secret(self):
        os.environ["MCP_ENV"] = "production"
        os.environ["SUPABASE_ANON_KEY"] = "public-anon"
        os.environ["MCP_SESSION_SECRET"] = "public-anon"
        from supabase_auth import SessionSecretError, new_session

        with self.assertRaises(SessionSecretError):
            new_session({"id": "u1", "email": "a@b.com", "name": "A"})

    def test_production_does_not_use_auth_token_as_secret(self):
        os.environ["MCP_ENV"] = "production"
        os.environ["MCP_AUTH_TOKEN"] = "admin-token-must-not-sign-cookies"
        from supabase_auth import SessionSecretError, new_session

        with self.assertRaises(SessionSecretError):
            new_session({"id": "u1", "email": "a@b.com", "name": "A"})

    def test_production_independent_secret_works(self):
        os.environ["MCP_ENV"] = "production"
        os.environ["MCP_SESSION_SECRET"] = "independent-session-secret"
        from supabase_auth import new_session, session_user

        sid = new_session({"id": "u2", "email": "c@d.com", "name": "C"})
        self.assertEqual(session_user(sid)["id"], "u2")


class ApiKeyFoundationTests(_Iso):
    def test_raw_key_not_stored_and_hash_resolves(self):
        from keys import create_key, list_keys, resolve_key
        from persist.db import connect

        created = create_key("shop", owner="u1", email="a@b.com")
        self.assertTrue(created["token"].startswith("lzr_"))
        blob = (Path(self.tmp) / "api_keys.json").read_text(encoding="utf-8")
        self.assertNotIn(created["token"], blob)
        with connect() as conn:
            hashes = [r[0] for r in conn.execute("SELECT hash FROM api_keys").fetchall()]
        self.assertTrue(hashes)
        self.assertNotIn(created["token"], hashes)
        self.assertEqual(resolve_key(created["token"])["name"], "shop")
        listed = list_keys(owner="u1")
        self.assertTrue(listed)
        self.assertNotIn("hash", listed[0])
        self.assertNotIn("token", listed[0])

    def test_revoke_and_expire(self):
        from keys import create_key, resolve_key, revoke_key
        from persist.keys_repo import KeyRepository
        from studio_store import now_iso

        created = create_key("gone", owner="u1", email="a@b.com")
        self.assertTrue(revoke_key(created["id"], owner="u1"))
        self.assertIsNone(resolve_key(created["token"]))
        dead = create_key("old", owner="u1", email="a@b.com")
        repo = KeyRepository()
        row = repo.by_id(dead["id"])
        assert row
        row["expires_at"] = "2000-01-01T00:00:00+00:00"
        repo.insert(row)
        self.assertIsNone(resolve_key(dead["token"]))
        self.assertTrue(now_iso())

    def test_json_keys_still_resolve_if_sqlite_empty(self):
        import hashlib
        import json
        from pathlib import Path

        from keys import resolve_key
        from studio_store import now_iso

        token = "lzr_legacycompatkeytokenxxxx"
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        Path(self.tmp, "api_keys.json").write_text(
            json.dumps(
                [
                    {
                        "id": "ab12cd34",
                        "name": "legacy",
                        "role": "workshop",
                        "plan": "maker",
                        "kind": "org",
                        "owner": "u9",
                        "email": "z@z.com",
                        "hash": digest,
                        "created": now_iso(),
                    }
                ]
            ),
            encoding="utf-8",
        )
        self.assertEqual(resolve_key(token)["name"], "legacy")


class TenantIsolationTests(_Iso):
    def test_org_a_cannot_read_org_b_artifact(self):
        from persist.authz import authorize_customer_file
        from persist.job import persist_bytes
        from persist.orgs import ensure_personal_org

        org_a = ensure_personal_org("user-a", "A")
        org_b = ensure_personal_org("user-b", "B")
        meta = persist_bytes(
            organization_id=org_b,
            kind="svg",
            data=b"<svg id='secret-b'/>",
            mime_type="image/svg+xml",
            source_file_id="create-design-secret.svg",
            durable=True,
            name="cut.svg",
        )
        prin_a = {"id": "user-a", "organization_id": org_a}
        prin_b = {"id": "user-b", "organization_id": org_b}
        denied = authorize_customer_file(meta["id"], prin_a, auth_on=True)
        allowed = authorize_customer_file(meta["id"], prin_b, auth_on=True)
        self.assertFalse(denied["allow"])
        self.assertTrue(allowed["allow"])
        guessed = authorize_customer_file("create-design-secret.svg", prin_a, auth_on=True)
        self.assertFalse(guessed["allow"])
        anon = authorize_customer_file(meta["id"], None, auth_on=True)
        self.assertFalse(anon["allow"])
        latest = authorize_customer_file("latest.svg", prin_b, auth_on=True)
        self.assertFalse(latest["allow"])

    def test_metadata_has_no_svg_bytes(self):
        from persist.job import persist_bytes
        from persist.orgs import ensure_personal_org
        from persist.storage import StorageService

        org = ensure_personal_org("user-c", "C")
        svg = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
        meta = persist_bytes(
            organization_id=org,
            kind="svg",
            data=svg,
            mime_type="image/svg+xml",
            durable=True,
            name="box.svg",
        )
        self.assertNotIn("bytes", meta)
        self.assertEqual(meta["hash"], __import__("hashlib").sha256(svg).hexdigest())
        self.assertEqual(StorageService().get(meta["storage_path"]), svg)
        self.assertIsNone(StorageService().signed_url(meta["storage_path"]))

    def test_tmp_gets_expiry(self):
        from persist.job import persist_bytes
        from persist.orgs import ensure_personal_org

        org = ensure_personal_org("user-d", "D")
        meta = persist_bytes(
            organization_id=org,
            kind="tmp",
            data=b"preview",
            mime_type="image/png",
            durable=False,
            name="p.png",
        )
        self.assertTrue(meta.get("expires_at"))
        self.assertTrue(str(meta["storage_path"]).startswith("tmp/"))
        from datetime import datetime, timezone

        exp = datetime.fromisoformat(str(meta["expires_at"]))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        remain = (exp - datetime.now(timezone.utc)).total_seconds()
        self.assertGreater(remain, 23 * 3600)
        self.assertLessEqual(remain, 24 * 3600)

    def test_persist_failure_does_not_claim_durable_save(self):
        from keys import current_auth
        from persist.job import attach_durable_artifacts
        from persist.orgs import ensure_personal_org

        org = ensure_personal_org("user-fail", "F")
        token = current_auth.set({"id": "user-fail", "organization_id": org, "name": "F"})
        try:
            out = attach_durable_artifacts(
                {
                    "success": True,
                    "final_status": "PROTOTYPE READY",
                    "file_id": "missing-on-purpose.svg",
                    "look_again": [],
                }
            )
        finally:
            current_auth.reset(token)
        self.assertEqual(out["design_generation"], "DESIGN_GENERATION_SUCCESS")
        self.assertEqual(out["artifact_persistence"], "ARTIFACT_PERSISTENCE_FAILED")
        self.assertFalse(out["durable_persistence"])

    def test_public_demo_stays_public(self):
        from demo_kits import demo_file, list_kits
        from server import PUBLIC_PREFIXES

        kits = list_kits()
        self.assertTrue(kits.get("success"))
        name = kits["kits"][0]["src_url"].rsplit("/", 1)[-1]
        self.assertTrue(demo_file(name).is_file())
        self.assertIn("/demo/", PUBLIC_PREFIXES)


class RateLimitTests(_Iso):
    def test_limiter_has_no_sql(self):
        from persist.rate_limit import allow, reset

        reset()
        self.assertTrue(allow("k", 2, 60))
        self.assertTrue(allow("k", 2, 60))
        self.assertFalse(allow("k", 2, 60))
        db = Path(self.tmp) / "app.sqlite"
        if db.is_file():
            before = db.stat().st_size
            allow("k2", 1, 60)
            self.assertEqual(db.stat().st_size, before)


class RegressionTests(_Iso):
    def test_mcp_tools_unchanged(self):
        from server import MCP_TOOLS

        self.assertIn("create_design", MCP_TOOLS)
        self.assertIn("validate_svg", MCP_TOOLS)
        self.assertIn("render_preview", MCP_TOOLS)
        self.assertIn("plan_laser_job", MCP_TOOLS)

    def test_create_design_without_assembled_preview_is_blocked(self):
        os.environ["MCP_DATA_DIR"] = self.tmp
        from payas_cad import create_design

        result = create_design(
            primitives=[{"type": "box", "x": 180, "y": 120, "h": 80, "bottom": True}],
            parameters={"material": "poplar_3mm", "machine": "payas_workshop", "what_you_see": "dört duvar ve taban"},
            public_base_url="http://127.0.0.1:8000",
        )
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("final_status"), "BLOCKED")
        self.assertEqual(result["review"]["categories"]["3D_ASSEMBLY"]["status"], "NOT_VERIFIED")
        self.assertEqual(result.get("design_generation"), "DESIGN_GENERATION_SUCCESS")
        from boxes_adapter import render_preview, validate_svg

        checked = validate_svg(result["file_id"])
        self.assertIn("look_again", checked)
        self.assertNotIn("error", checked)
        preview = render_preview(result["file_id"])
        self.assertTrue(preview.get("success"))
        self.assertEqual(preview.get("format"), "svg")

    def test_validate_missing_still_mcp_safe(self):
        from payas_cad import validate_assembly

        report = validate_assembly(file_id="no-such-file.svg")
        self.assertTrue(report.get("success"))
        self.assertTrue(report.get("look_again"))

    def test_oauth_and_google_helpers_still_pass(self):
        from oauth_mcp import metadata
        from supabase_auth import safe_next_path

        self.assertIn("S256", metadata("https://mcp.metehanavci.com")["code_challenge_methods_supported"])
        self.assertEqual(safe_next_path("/connect", origins=["https://mcp.metehanavci.com"]), "/connect")


if __name__ == "__main__":
    unittest.main()
