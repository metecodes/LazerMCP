"""Operator admin: active users and org grant."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone


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

    def test_new_account_waits_for_operator_approval(self):
        from supabase_auth import (
            account_access_state,
            account_is_approved,
            pending_users,
            set_account_approval,
            upsert_user,
        )

        fresh = upsert_user({"id": "u-pending", "email": "odeme@ornek.com", "name": "Ödeme"})
        self.assertEqual(fresh["approval_status"], "pending")
        self.assertFalse(account_is_approved(fresh))
        self.assertEqual(pending_users()[0]["email"], "odeme@ornek.com")
        approved = set_account_approval("odeme@ornek.com", approve=True, by="metehan1387@gmail.com")
        self.assertTrue(approved["approved"])
        self.assertTrue(account_is_approved(approved))
        denied = set_account_approval("odeme@ornek.com", approve=False, by="metehan1387@gmail.com")
        self.assertEqual(denied["approval_status"], "denied")
        self.assertFalse(account_is_approved(denied))

    def test_first_approval_is_three_day_trial_then_needs_membership_approval(self):
        from studio_store import read_json, write_json
        from supabase_auth import account_access_state, account_is_approved, set_account_approval, upsert_user

        upsert_user({"id": "u-trial", "email": "trial@ornek.com", "name": "Trial"})
        trial = set_account_approval("trial@ornek.com", approve=True, by="metehan1387@gmail.com")
        self.assertEqual(trial["access_state"], "trial")
        self.assertTrue(account_is_approved(trial))
        expires = datetime.fromisoformat(trial["trial_expires_at"])
        self.assertLessEqual(expires - datetime.now(timezone.utc), timedelta(days=3, seconds=2))
        rows = read_json("users.json", [])
        rows[0]["trial_expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        write_json("users.json", rows)
        expired = next(row for row in read_json("users.json", []) if row["id"] == "u-trial")
        self.assertEqual(account_access_state(expired), "trial_expired")
        self.assertFalse(account_is_approved(expired))
        continued = set_account_approval("trial@ornek.com", approve=True, by="metehan1387@gmail.com")
        self.assertEqual(continued["access_state"], "approved")
        self.assertTrue(account_is_approved(continued))
