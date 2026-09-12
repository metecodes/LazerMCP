"""Operator admin: active users and org grant."""

from __future__ import annotations

import os
import tempfile
import unittest


class AdminGrantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = {
            key: os.environ.get(key)
            for key in ("MCP_DATA_DIR", "LASERMCP_ORG_DOMAINS", "LASERMCP_ADMIN_EMAILS")
        }
        os.environ["MCP_DATA_DIR"] = self.tmp
        os.environ.pop("LASERMCP_ORG_DOMAINS", None)
        os.environ.pop("LASERMCP_ADMIN_EMAILS", None)

    def tearDown(self):
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_default_admin_email(self):
        from supabase_auth import is_admin

        self.assertTrue(is_admin({"email": "metehan1387@gmail.com"}))
        self.assertTrue(is_admin({"email": "Metehan1387@Gmail.com"}))
        self.assertFalse(is_admin({"email": "kisi@ornek.com"}))
        self.assertFalse(is_admin(None))

    def test_grant_survives_upsert_and_mints(self):
        from supabase_auth import can_mint_keys, grant_org, search_users, upsert_user, user_stats

        upsert_user({"id": "u1", "email": "kisi@ornek.com", "name": "Kisi"})
        self.assertFalse(can_mint_keys({"email": "kisi@ornek.com"}))
        granted = grant_org("kisi@ornek.com", by="metehan1387@gmail.com")
        self.assertTrue(granted["org_grant"])
        self.assertEqual(granted["kind"], "org")
        again = upsert_user({"id": "u1", "email": "kisi@ornek.com", "name": "Kisi"})
        self.assertEqual(again["kind"], "org")
        self.assertTrue(can_mint_keys(again))
        hits = search_users("kisi@ornek")
        self.assertEqual(len(hits), 1)
        stats = user_stats(active_days=30)
        self.assertEqual(stats["total_users"], 1)
        self.assertEqual(stats["active_users"], 1)
        self.assertEqual(stats["org_users"], 1)

    def test_search_needs_query(self):
        from supabase_auth import search_users, upsert_user

        upsert_user({"id": "u2", "email": "gizli@ornek.com", "name": "G"})
        self.assertEqual(search_users(""), [])
        self.assertEqual(search_users("g"), [])
        self.assertEqual(search_users("gizli")[0]["email"], "gizli@ornek.com")
