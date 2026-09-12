# Migration Guide (Sprint 0.5)

Non-destructive. JSON/JSONL stores stay in place.

## 1. Backup

Copy `MCP_DATA_DIR` (or `output/studio` + `output/`) before applying SQL or running the key copy.

Do not commit backups that contain customer CAD.

## 2. Postgres (Supabase)

1. Open the SQL editor.
2. Run `migrations/0001_sprint_0_5.sql`.
3. Confirm tables: `organizations`, `organization_members`, `artifacts`, `api_keys`.
4. Confirm RLS is enabled (script does this).

The LaserMCP **process** still uses local SQLite unless `SUPABASE_SERVICE_ROLE_KEY` is set. The SQL file is the reproducible schema for when you point the server at Supabase. A live PostgREST repository for every table is **not fully wired** in this sprint — SQLite is the implemented app DB. See report (NOT VERIFIED / deferred).

## 3. JSON API keys → sqlite (optional)

Dry-run (default):

```
python -m persist.migrate_json_keys
```

Apply (copies hashed rows only; does not delete JSON):

```
python -m persist.migrate_json_keys --apply
```

Idempotent: existing hashes are skipped. No raw tokens are printed.

## 4. Storage bucket

Create a **private** bucket `lasermcp-artifacts` (or `LASERMCP_STORAGE_BUCKET`).  
No public policies. Server uses the service role.

## 5. Rollback

- Revert the application deploy.
- Leave JSON key files untouched.
- Optional: `DROP TABLE` the four public tables **only** if they contain no data you need.
- Users must sign in again if `MCP_SESSION_SECRET` changed.
