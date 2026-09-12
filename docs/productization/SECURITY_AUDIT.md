# Security Audit

Inspected implementation only. No penetration test. No live key dump.

Do not paste real secrets into this file. None are included.

---

## 1. RLS

**Not applicable in-app.** There is no Postgres client and no RLS policy in the repo.

When tables are added, RLS must key off `organization_id` (and membership), not only `auth.uid()` on every artifact path. Until then: **NOT VERIFIED**.

---

## 2. Organization isolation

| Check | Result |
| --- | --- |
| Org entity | Email-domain flag only |
| Key mint | `can_mint_keys` + `LASERMCP_ORG_DOMAINS` — VERIFIED |
| Client cannot self-promote to org | `upsert_user` ignores caller `kind` — VERIFIED |
| Project isolation | **Fail.** `projects.json` has no owner. `list_projects` returns all |
| Calibration isolation | **Fail.** Global `calibrations.json` |
| File isolation | **Fail.** Shared `OUTPUT_DIR`; auth ≠ ownership |

A signed-in individual who can call `/api/studio?action=projects` sees every project on that instance.

---

## 3. Project and artifact ownership

`save_version` does not write `owner` or `organization_id`.  
`/files/{filename}` uses `_safe_output_file` (path-safe) then `FileResponse`. Any principal that passes `BearerGate` can fetch any existing `file_id`.

`file_id` looks like `create-design-YYYYMMDD-HHMMSS-{8hex}.svg` — not a secret capability.

`latest.svg` / `latest.dxf` are shared names.

**IDOR (files and projects): present in the current model** whenever more than one tenant shares a process and disk.

---

## 4. Storage policies and signed URLs

| Control | Status |
| --- | --- |
| Private bucket | Not implemented |
| Signed URLs | Not implemented |
| Public `/files` | Behind auth **if** `auth_required()` (Supabase configured ⇒ yes) |
| Guessable URL after auth | Yes |
| Demo kit files | `/demo/*` is **public** — OK for marketing cuts, not customer jobs |

Customer CAD must not become public because someone knows the path. Today they are “auth-gated, not owner-gated.”

---

## 5. API key security

| Property | Status |
| --- | --- |
| Stored as hash | Yes, SHA-256 hex of raw token |
| Shown once | Yes |
| Prefix `lzr_` | Yes (detectable; full secret not stored) |
| Separate `prefix` column | No |
| `created` | Yes |
| `last_used` | Yes — **full file rewrite** on each resolve |
| `expires_at` | No |
| `revoked_at` | No — delete-from-array would be the only revoke; **no revoke API verified** |
| Timing-safe compare | Admin env token uses `hmac.compare_digest`. Key search is hash equality over a list |
| Salt | No — acceptable for 256-bit random tokens |

Do not start storing reusable plaintext keys.

---

## 6. OAuth / session security

### Google / Supabase

- Authorize URL built server-side; Vercel uses status 200 HTML redirect (avoids 302 follow 500).
- Access token verified at Supabase, not parsed as a local JWT without check.
- `next` is same-origin filtered.

**Dashboard redirect allowlist and Google client settings: NOT VERIFIED.**

### `lmcp_sid`

- HttpOnly, SameSite=lax, Secure on HTTPS, 30 days.
- HMAC-SHA256 over base64 payload.
- Secret chain (`_session_secret`): `MCP_SESSION_SECRET` → `MCP_AUTH_TOKEN` → **anon key** → literal `"lasermcp-dev-session"`.

If production lacks `MCP_SESSION_SECRET`, the cookie is signed with the **publishable anon key** (also sent to browsers via `/api/auth/config`). That is **forgeable by anyone who can read the public config**.

**Whether production sets `MCP_SESSION_SECRET`: NOT VERIFIED.** Treat missing secret as a **top risk**.

Legacy `sessions.json` still accepted if the cookie is not a signed pair.

### MCP OAuth

- PKCE S256 required.
- Redirect host allowlist (first-party + env).
- Codes expire 300s; consumed on exchange.
- Tokens hashed; 30-day exp; last 400 kept.
- DCR `token_endpoint_auth_method: none` (public clients) — expected for ChatGPT/Claude.
- Implicit client insert if `client_id` unknown but host allowlisted — convenience vs strict DCR; still host-checked.

OAuth JSON CORS `*`: metadata/token endpoints are public-by-design for MCP clients.

---

## 7. Secret exposure

| Item | Exposure |
| --- | --- |
| `SUPABASE_ANON_KEY` | Returned by `GET /api/auth/config` when configured — **intentional** for browser Google |
| Org domain list | Same endpoint |
| API raw key | Only mint response |
| `.env` | `.env.example` has placeholders; **do not commit `.env`** |
| Service role | Not in repo |

Anon key is not a service role, but it **must not** be the session HMAC secret.

---

## 8. Rate limiting

None. Auth, generate, and mint are unbounded in process.

Abuse: generate loops fill `/tmp` or `output/`; Google-bearer path hammers `/auth/v1/user`.

---

## 9. Other notes

- MCP tools prefer `success` + `look_again` (no `error` keys) — good for clients; HTTP `/api/generate` still uses `_error` with `{"success": false, "error": ...}`.
- `BearerGate` 401 body tells the user to sign in — fine.
- `?token=` disabled off localhost — VERIFIED.
- Beta email `POST /api/beta` appends to `beta.jsonl` with only syntactic email check — public write, no CAPTCHA (**NOT VERIFIED** if edge WAF exists).
- Vercel ephemeral disk: security + reliability (keys/users vanish; new instance looks empty).

---

## 10. Required before multi-tenant Projects

1. Confirm `MCP_SESSION_SECRET` in production (rotate sessions if it was the anon key).
2. Owner (org) on every project and artifact.
3. Authorize `/files` (or successor) by org, not “any logged-in user”.
4. Private object storage + signed URLs.
5. Key revoke + stop rewriting the whole key file on every call.
6. Per-key / per-org rate limit on generate.

Do not change the Google OAuth **flow** in this phase; changing the **cookie secret** is an ops fix, not a flow change, and should be done carefully (all users re-login).
