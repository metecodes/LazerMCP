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
        self.assertEqual(stats["dealer_users"], 0)
        self.assertEqual(stats["user_users"], 0)

    def test_admin_can_set_three_models_and_upsert_keeps_dealer(self):
        from supabase_auth import (
            account_model_of,
            can_mint_activation,
            can_mint_keys,
            set_account_model,
            upsert_user,
            user_stats,
        )

        upsert_user({"id": "u3", "email": "bayi@ornek.com", "name": "Bayi"})
        dealer = set_account_model("bayi@ornek.com", "bayi", by="metehan1387@gmail.com")
        self.assertEqual(dealer["account_model"], "dealer")
        self.assertEqual(dealer["kind"], "dealer")
        self.assertFalse(dealer["org_grant"])
        self.assertFalse(can_mint_keys(dealer))
        self.assertTrue(can_mint_activation(dealer))
        again = upsert_user({"id": "u3", "email": "bayi@ornek.com", "name": "Bayi"})
        self.assertEqual(account_model_of(again), "dealer")
        self.assertEqual(again["kind"], "dealer")
        self.assertFalse(can_mint_keys(again))
        user = set_account_model("bayi@ornek.com", "user", by="metehan1387@gmail.com")
        self.assertEqual(user["account_model"], "user")
        self.assertFalse(can_mint_activation(user))
        org = set_account_model("bayi@ornek.com", "kurumsal", by="metehan1387@gmail.com")
        self.assertEqual(org["account_model"], "org")
        self.assertTrue(can_mint_keys(org))
        stats = user_stats()
        self.assertEqual(stats["dealer_users"], 0)
        self.assertEqual(stats["org_users"], 1)
        self.assertIsNone(set_account_model("yok@ornek.com", "dealer", by="admin"))
        self.assertIsNone(set_account_model("bayi@ornek.com", "vip", by="admin"))

    def test_key_request_waits_for_admin(self):
        from access_requests import decide_key_request, list_key_requests, submit_key_request
        from supabase_auth import can_mint_keys, upsert_user

        upsert_user({"id": "u4", "email": "atölye@ornek.com", "name": "A"})
        first = submit_key_request({"id": "u4", "email": "atölye@ornek.com", "name": "A"}, note="Cursor", want="org")
        self.assertEqual(first["request"]["status"], "open")
        again = submit_key_request({"id": "u4", "email": "atölye@ornek.com", "name": "A"}, note="tekrar")
        self.assertEqual(again["request"]["id"], first["request"]["id"])
        self.assertEqual(len(list_key_requests()), 1)
        self.assertFalse(can_mint_keys(upsert_user({"id": "u4", "email": "atölye@ornek.com", "name": "A"})))
        decided = decide_key_request("atölye@ornek.com", approve=True, by="metehan1387@gmail.com", model="org")
        self.assertEqual(decided["request"]["status"], "approved")
        self.assertEqual(decided["user"]["account_model"], "org")
        self.assertTrue(can_mint_keys(decided["user"]))
        self.assertEqual(list_key_requests(), [])

    def test_search_needs_query(self):
        from supabase_auth import search_users, upsert_user

        upsert_user({"id": "u2", "email": "gizli@ornek.com", "name": "G"})
        self.assertEqual(search_users(""), [])
        self.assertEqual(search_users("g"), [])
        self.assertEqual(search_users("gizli")[0]["email"], "gizli@ornek.com")
