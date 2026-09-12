# Sprint 0.5 Implementation Report

## Baseline vs final

| Run | Command | Result |
| --- | --- | --- |
| Baseline (before this sprint) | `python -m unittest discover -s tests -v` | **45 OK** |
| Final (project venv) | `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` | **63 OK** |

System `python` without the venv cannot import `starlette` (pre-existing; `server.py` needs the venv). Use `.venv`.

One `ResourceWarning` remains: unclosed font file `fonts/Arimo-Regular.ttf` (pre-existing Boxes.py/font path, not introduced here).

## What shipped

- Production-safe `MCP_SESSION_SECRET` (no anon/publishable key, no `MCP_AUTH_TOKEN` fallback). Missing production secret → `SessionSecretError` / HTTP 503. Dev fallback is the explicit literal `lasermcp-dev-session` only.
- Personal organization + membership in SQLite (`persist/`).
- Artifact metadata + private object store (local files; optional Supabase Storage helpers when service role is set).
- Owner-gated `/files` when auth is on (`latest.svg` / `latest.dxf` denied).
- Dual-write hashed API keys (JSON kept) + revoke/expiry + sampled `last_used` (~1h).
- In-memory rate limits on expensive HTTP paths.
- CAD persist hook: `DESIGN_GENERATION_SUCCESS` vs `ARTIFACT_PERSISTENCE_*` are separate. Persist failure does not claim a durable save.
- SQL migration + RLS for future Supabase.
- Tests in `tests/test_sprint_0_5.py`.

## What did not ship (by design)

Projects, versions, billing, workspaces, gallery, `usage_daily`, Google token cache, CAD/OAuth redesign.

## Docs vs code

`CURRENT_ARCHITECTURE.md` previously said there is no Postgres client and `touch_key` rewrites on every resolve. **Trust the code:** the implemented app DB is still **SQLite**. `touch_key` is sampled. `persist.supabase_rest` implements Storage helpers only — applying `0001_sprint_0_5.sql` does **not** switch the running process onto PostgREST. That wiring is deferred.

## Changed files (tracked)

- `.env.example`
- `boxes_adapter.py`
- `keys.py`
- `server.py`
- `supabase_auth.py`

## New files

- `migrations/0001_sprint_0_5.sql`
- `persist/__init__.py`
- `persist/env.py`
- `persist/db.py`
- `persist/orgs.py`
- `persist/keys_repo.py`
- `persist/artifacts.py`
- `persist/storage.py`
- `persist/supabase_rest.py`
- `persist/authz.py`
- `persist/rate_limit.py`
- `persist/cleanup.py`
- `persist/job.py`
- `persist/migrate_json_keys.py`
- `tests/test_sprint_0_5.py`
- `docs/productization/SPRINT_0_5_IMPLEMENTATION_PLAN.md`
- `docs/productization/SPRINT_0_5_IMPLEMENTATION_REPORT.md`
- `docs/productization/STORAGE_ARCHITECTURE.md`
- `docs/productization/TENANT_SECURITY.md`
- `docs/productization/MIGRATION_GUIDE.md`
- `docs/productization/DEPLOYMENT_CHECKLIST.md`

Also updated (productization set): `CURRENT_ARCHITECTURE.md` addendum.

Do **not** commit `.cursor/` or secrets.

## Migrations created

`migrations/0001_sprint_0_5.sql` — `organizations`, `organization_members`, `artifacts`, `api_keys` + RLS.  
No `projects`, `project_versions`, billing, templates.

## Environment variables required / added

| Variable | Required |
| --- | --- |
| `MCP_SESSION_SECRET` | **Yes in production.** Independent. Never the anon key. |
| `MCP_ENV` | If not on Vercel (`VERCEL=1` already counts as production) |
| `MCP_DATA_DIR` | Strongly recommended for durable SQLite + local objects |
| `MCP_OUTPUT_DIR` | Recommended on Vercel (CAD scratch is otherwise `/tmp`) |
| `SUPABASE_SERVICE_ROLE_KEY` | Server only, if using Supabase Storage |
| `LASERMCP_STORAGE_BUCKET` | Optional (default `lasermcp-artifacts`) |

Existing: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `LASERMCP_ORG_DOMAINS`, `MCP_PUBLIC_BASE_URL`.

## Manual Supabase dashboard actions

1. Apply `migrations/0001_sprint_0_5.sql`.
2. Confirm RLS is enabled on the four tables.
3. Create **private** bucket `lasermcp-artifacts` (or `LASERMCP_STORAGE_BUCKET`).
4. Set Vercel `MCP_SESSION_SECRET` (rotate cookies; users sign in again).
5. Optionally set `SUPABASE_SERVICE_ROLE_KEY` (never in the browser).
6. Optional key copy: `python -m persist.migrate_json_keys` then `--apply`. Do not delete `api_keys.json`.

**Dashboard state: NOT VERIFIED.**

## NOT VERIFIED

- Live Vercel env values (whether `MCP_SESSION_SECRET` is already set)
- Whether production data still lands on ephemeral `/tmp`
- libwebp availability for WebP (Pillow path falls back to PNG)
- Official Supabase Free Plan numeric limits
- Cluster-wide rate limiting (in-memory is process-local)
- Live PostgREST against the new tables
- Live private-bucket signed URL round-trip

## Deferred

- Wire SQLite repositories to PostgREST when service role is set (Storage helpers exist; table repos do not)
- Distributed rate limiter (Redis / Upstash)
- Google bearer short-TTL cache (live `/auth/v1/user` left intact)
- `usage_daily`
- Projects / version history / `base_version`
- Team workspace UI

## Session rotation

Existing `lmcp_sid` cookies become invalid after `MCP_SESSION_SECRET` is set or rotated. Acceptable.

## SPRINT 0.5 STATUS

**PASS WITH WARNINGS**

Local foundation and tests are green. Live Supabase SQL/bucket and production durable disk/Storage are ops, not proven in this environment.

## READY FOR PROJECTS SPRINT

**NO**

Do not start Projects until production has an independent `MCP_SESSION_SECRET`, the SQL migration applied, a private bucket, and a durable data plane (`MCP_DATA_DIR` and/or service-role Storage **plus** metadata that will survive a Vercel instance). Applying the SQL file alone does not move the running app off SQLite.
