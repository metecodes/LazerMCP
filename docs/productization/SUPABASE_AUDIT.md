# Supabase Audit

**Inspected:** application source only.  
**Not inspected:** Supabase project dashboard, SQL editor, Auth settings UI, Storage, Edge Functions, logs.

This app does **not** open a Postgres connection. A dashboard-only object that this repo never queries is **NOT VERIFIED**.

---

## 1. How Supabase is used

| Capability | In repo? | Evidence |
| --- | --- | --- |
| Auth (Google) | Yes | `supabase_auth.verify_access_token`, `server._google_authorize_url` |
| Auth user upsert in **this** app | Local `users.json`, not Auth Admin API | `upsert_user` |
| Postgres / PostgREST | No | No `rest/v1`, no client |
| Storage | No | No `storage.from` |
| Realtime | No | No channel subscribe |
| Edge Functions | No | No invoke |
| Database functions / triggers | No | No SQL |
| RLS | No | No policies in repo |
| Service role key | Not referenced | Only anon / publishable key env names |

Env names verified in `.env.example` and `supabase_auth.py`:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY` or `SUPABASE_PUBLISHABLE_KEY`

Service-role usage: **not present** (good). Live project may still have a service role in the dashboard — **NOT VERIFIED**.

---

## 2. Existing tables

**None defined in this repository.**

Supabase Auth manages its own `auth.users` (and related Auth schemas) when Google login succeeds. That schema is **owned by Supabase Auth**, not by LaserMCP migrations.

| Object | Status |
| --- | --- |
| Application `public.*` tables | **NOT VERIFIED** / not created by this repo |
| Indexes | **NOT VERIFIED** |
| Foreign keys | **NOT VERIFIED** |
| RLS policies | **NOT VERIFIED** |
| Storage buckets | **NOT VERIFIED** (unused by code) |
| Public/private buckets | **NOT VERIFIED** |
| DB functions | **NOT VERIFIED** |
| Triggers | **NOT VERIFIED** |
| Realtime publications | **NOT VERIFIED** |
| Edge Functions | **NOT VERIFIED** |

---

## 3. Auth usage (verified)

1. Browser or `/auth/google` hits `{SUPABASE_URL}/auth/v1/authorize?provider=google`.
2. Supabase completes Google and redirects to `{origin}/auth/callback` (must be listed in Supabase Auth URL config — **dashboard values NOT VERIFIED**).
3. Client posts `access_token` to `/api/auth/session`.
4. Server `GET /auth/v1/user` with that JWT.
5. Identity is copied into `users.json` and a **LaserMCP** signed cookie is issued.

The long-lived session used by the site and by `/oauth/authorize` is **not** a Supabase refresh-token store. It is `lmcp_sid`.

Every MCP request that presents a **Google access token** (not `lzr_` / `mcp_`) calls `/auth/v1/user` again (`resolve_bearer`). That is a **remote Auth read on the hot path**.

---

## 4. Potentially expensive patterns (if you later put data in Supabase)

These are **risks of the current local design**, not proven Postgres queries:

| Pattern | Today | Risk if naively moved to Postgres |
| --- | --- | --- |
| Full-file `users.json` rewrite on every login | Yes | Row upsert is cheap; rewriting a blob is not |
| `touch_key` rewrite of all keys | Yes | `UPDATE last_used` per resolve — high write rate |
| `usage.jsonl` append + full scan for monthly quota | Yes | Unbounded fact table + `COUNT(*)` per job |
| `projects.json` rewrite + embed `speak` / `bom` | Yes | Large JSON/text columns |
| CAD SVG/PNG/DXF on disk | Yes | **Must not** become `bytea` / text in Postgres |
| Sidecar `{stem}.json` with primitives + review | Yes | Same — metadata only in SQL |

---

## 5. High-frequency writes (current process)

On a typical successful `create_design` (verified in `boxes_adapter` + `studio.finish_result`):

1. Multiple artifact writes under `OUTPUT_DIR`.
2. `usage.jsonl` append.
3. `telemetry.jsonl` append (job_saved; maybe look_again).
4. If beta/history entitled (default yes) and `file_id` exists: rewrite entire `projects.json`.
5. If a hashed API key was used: rewrite entire `api_keys.json` (`touch_key`).

None of these hit Supabase Postgres today.

---

## 6. Duplicate data

| Fact | Copies |
| --- | --- |
| User id / email / name | Supabase Auth JWT, `users.json`, `lmcp_sid` payload, OAuth token rows, API key `owner`/`email` |
| `final_status` / `speak` | MCP result, `{stem}.json`, `{stem}-production.md`, `projects.json` version, `usage.jsonl` |
| Kerf suggestion | `calibrations.json`, sidecar `calibration`, parameters |

---

## 7. Large JSON / text

Verified large-ish payloads:

- `{stem}.json` includes `speak`, `scorecard`, `primitives`, `bom`, `nesting`, `review`, `pipeline`, `design_map`, `connections`.
- `projects.py` copies `speak` and bom speak into each version.
- Gate card `speak` is a multi-line text block (`review.format_gate_card`).

These must stay **out of PostgreSQL row bodies** except as short summaries or storage pointers.

---

## 8. Scalability problems (honest)

1. **Vercel `/tmp` as system of record** if `MCP_DATA_DIR` is unset — data loss, split-brain keys, vanished CAD URLs. Production env: **NOT VERIFIED**.
2. **No Postgres yet** — the next mistake is dumping artifacts into Free Plan Postgres.
3. **Auth `/user` on every Google-bearer MCP call** — Auth rate / latency. Official Auth rate limits: **LIMIT NOT VERIFIED**.
4. **Single JSON files** — not concurrent-safe; last writer wins.
5. **`usage.jsonl` growth** — quota read is O(file).
6. **Shared `OUTPUT_DIR`** — no tenant isolation.
7. **`latest.svg` / `latest.dxf`** — global overwrite.

Do **not** optimize Postgres that does not exist. Fix the durability and ownership model before adding tables.

---

## 9. Free Plan (application view)

This repo does not encode Free Plan quotas. Official current limits: **LIMIT NOT VERIFIED**.

What the **architecture** already spends on Supabase if the project exists:

- Auth users (one per Google login).
- Auth token verification HTTP.
- Redirect allowlist configuration.

What it does **not** spend today: database rows, Storage GB, Realtime connections, Edge invocations.

---

## 10. Recommendation (design only)

Keep Auth on Supabase.  
Do **not** put SVG/PNG/DXF/PDF or full review JSON in Postgres.  
Introduce application tables only after a durable store + private object storage decision (see `PROPOSED_DATA_MODEL.md`).
