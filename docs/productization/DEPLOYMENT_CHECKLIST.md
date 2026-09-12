# Deployment Checklist (Sprint 0.5)

## Vercel / host environment

- [ ] `MCP_SESSION_SECRET` — random, **not** the Supabase anon/publishable key. Without this, Google can finish but `/account` stays signed out (cookie never set).
- [ ] `MCP_ENV=production` if `VERCEL` is not `1`
- [ ] `SUPABASE_URL`
- [ ] `SUPABASE_ANON_KEY` (browser Google only)
- [ ] `LASERMCP_ORG_DOMAINS` if org keys must mint
- [ ] `MCP_PUBLIC_BASE_URL=https://mcp.metehanavci.com`
- [ ] `MCP_DATA_DIR` on durable storage **or** accept SQLite-on-instance limits
- [ ] `SUPABASE_SERVICE_ROLE_KEY` — server only, when using Supabase Storage
- [ ] `LASERMCP_STORAGE_BUCKET=lasermcp-artifacts`

Never put the service role in `web/` or `/api/auth/config`.

## Supabase dashboard

- [ ] Apply `migrations/0001_sprint_0_5.sql`
- [ ] RLS enabled on the four tables
- [ ] Private Storage bucket created
- [ ] Auth URL allowlist still includes `/auth/callback` (do not change Google flow)
- [ ] Anon key still only Auth + public config

## API keys

- [ ] Backup `api_keys.json`
- [ ] Optional: `python -m persist.migrate_json_keys --apply`
- [ ] Confirm an existing `lzr_` key still resolves
- [ ] Do **not** delete the JSON store until verified

## Rate limit

In-memory limiter is **not** cluster-wide on Vercel. For strict production limits, put a distributed limiter (Redis / Upstash) behind `persist.rate_limit` later.

## Session rotation

Setting a new `MCP_SESSION_SECRET` signs out every browser cookie. Users Google-sign-in again. Acceptable.

## Rollback

Redeploy the previous git SHA. Keep JSON stores. Drop new SQL tables only if unused.
