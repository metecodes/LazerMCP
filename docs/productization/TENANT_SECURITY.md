# Tenant Security (Sprint 0.5)

## Owner boundary

Every authenticated user gets a **personal organization** (`kind=personal`, `role=owner`).  
`organization_id` is deterministic: UUID5 of `lasermcp-personal:{user_id}`.

No invitations, seats, or workspace UI.

## Who may read an artifact

Allow if any of:

- principal `organization_id` matches the artifact
- principal user id is a member of that organization
- principal is the admin env token (`id=admin`)

Deny if unauthenticated (when auth is on) or Org A vs Org B.

`latest.svg` / `latest.dxf` are denied when auth is on.

Public `/demo/*` is unchanged.

## Application auth vs RLS

| Path | Mechanism |
| --- | --- |
| MCP / API keys / cookies | `persist.authz` in the LaserMCP process |
| Future user-JWT dashboard | RLS policies in `migrations/0001_sprint_0_5.sql` |
| Service role | Bypasses RLS; **server only** |

Do not assume RLS authorizes an `lzr_` key. It does not.

## Session HMAC

Production (`MCP_ENV=production` or `VERCEL=1`) **requires** `MCP_SESSION_SECRET`.  
It must not equal the Supabase anon/publishable key.  
`MCP_AUTH_TOKEN` is no longer a session-secret fallback.  
Missing secret: new sessions fail (`SessionSecretError` / HTTP 503). Existing cookies do not verify. Users sign in again after rotation.

Development uses explicit `MCP_SESSION_SECRET` or the literal `lasermcp-dev-session`.

## API keys

- Raw token shown once.
- SHA-256 hash at rest (JSON + sqlite).
- `prefix` stored (`lzr_` + 8).
- `revoked_at` / `expires_at` supported.
- List never returns raw token or hash.
- JSON store is **not** deleted.

## Rate limits

In-memory (`persist.rate_limit`). **Not globally reliable on multi-instance Vercel.**

| Surface | Limit (process-local) |
| --- | --- |
| POST `/mcp` | 60 / minute / principal |
| POST `/api/generate`, `/api/cad/*` | 30 / hour / principal |
| POST `/api/account/keys` | 10 / hour / user |
| POST `/api/beta` | 5 / hour / IP |

No SQL write per check.

## Google bearer `/auth/v1/user`

Still live-verified on each Google access token. **No token cache in this sprint** (revocation/security). Safe future options: short TTL cache of `{hash(token) → principal}` with TTL ≤ 60s, keyed only by hash, never logging the token; or require MCP OAuth / `lzr_` on the hot path so Google JWT is only used at session create.

## IDOR

`/files/{filename}` is owner-gated when `auth_required()`. Guessing a UUID or old `file_id` does not grant Org B access.
