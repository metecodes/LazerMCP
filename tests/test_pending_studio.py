"""Pending Google sessions keep Studio design identity; mint/keys stay blocked."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from keys import current_auth


PENDING = {
    "id": "u-pending",
    "email": "pending@example.com",
    "provider": "google",
    "approval_status": "pending",
    "organization_id": "org-pending",
}


class PendingStudioGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_principal_kept_on_studio_public_api(self):
        from server import BearerGate

        seen = {}

        async def app(scope, receive, send):
            seen["principal"] = current_auth.get()
            body = b'{"success":true,"preview":true}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/studio/box",
            "headers": [],
        }
        with patch.object(BearerGate, "_principal", return_value=PENDING):
            await BearerGate(app)(scope, AsyncMock(), AsyncMock())
        self.assertEqual(seen["principal"]["id"], "u-pending")
        self.assertEqual(seen["principal"]["organization_id"], "org-pending")

    async def test_pending_stripped_from_non_studio_public_api(self):
        from server import BearerGate

        seen = {}

        async def app(scope, receive, send):
            seen["principal"] = current_auth.get()
            body = b'{"success":true}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/plans",
            "headers": [],
        }
        with patch.object(BearerGate, "_principal", return_value=PENDING):
            await BearerGate(app)(scope, AsyncMock(), AsyncMock())
        self.assertIsNone(seen["principal"])

    async def test_pending_account_keys_still_403(self):
        from server import BearerGate

        sent = {}

        async def app(scope, receive, send):
            raise AssertionError("protected route must not reach app for pending")

        async def send(message):
            if message["type"] == "http.response.start":
                sent["status"] = message["status"]

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/account/keys",
            "headers": [],
        }
        with patch("keys.auth_required", return_value=True), patch.object(
            BearerGate, "_principal", return_value=PENDING
        ), patch("supabase_auth.account_is_approved", return_value=False), patch(
            "supabase_auth.account_access_state", return_value="pending"
        ):
            await BearerGate(app)(scope, AsyncMock(), send)
        self.assertEqual(sent.get("status"), 403)


if __name__ == "__main__":
    unittest.main()
