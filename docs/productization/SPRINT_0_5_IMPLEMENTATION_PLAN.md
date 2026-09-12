# Sprint 0.5 Implementation Plan

**Baseline (2026-09-12):** `python -m unittest discover -s tests -v` → **45 tests, OK**.

Docs vs code: `PRODUCT_ROADMAP.md` previously said “no migrations.” This sprint **does** add a SQL migration. Application data is still JSON-on-disk today (`CURRENT_ARCHITECTURE.md` is correct). Trust the code; this plan adds an opt-in durable layer beside it.

---

## Files to change

| File | Why |
| --- | --- |
| `supabase_auth.py` | Production session secret; attach personal org on upsert/principal |
| `keys.py` | Dual-write durable keys; revoke/expiry; sampled `last_used` |
| `server.py` | Owner-gated `/files`; rate limits; persist-safe session 503 |
| `boxes_adapter.py` | After CAD write, optional durable artifact attach (no geometry change) |
| `.env.example` | New env vars |

## Files not to change

Google OAuth routes, MCP OAuth/PKCE/DCR (`oauth_mcp.py`), MCP tool **schemas**, `job_planner.py`, `review.py`, `pipeline.py`, `payas_cad.py` geometry, `web/*` onboarding, `demo_kits.py`, `projects.py` (no Projects product), `metering.py` / `usage.jsonl`.

## Migrations to add

`migrations/0001_sprint_0_5.sql` — `organizations`, `organization_members`, `artifacts`, `api_keys` + RLS.  
No `projects`, `project_versions`, profiles, billing, templates.

## New modules

`persist/` — `OrganizationRepository`, `KeyRepository`, `ArtifactRepository`, `StorageService`, rate limiter, cleanup, JSON-key migrate (dry-run).  
Local/tests: SQLite under `MCP_DATA_DIR` (stdlib). Production optional: PostgREST + private Storage via **service role** (never in the browser).

## Compatibility risks

- Production without `MCP_SESSION_SECRET` refuses new sessions (users re-login after rotate).
- `/files/latest.svg` no longer a customer identity when auth is on.
- Unregistered legacy filenames denied when auth is on (local workshop with auth off unchanged).
- JSON `api_keys.json` is **not** deleted.

## Rollback

Revert the commit. Remove env vars. Leave JSON stores in place. Drop new SQL tables only if they were applied (`DROP TABLE` in `MIGRATION_GUIDE.md`).
