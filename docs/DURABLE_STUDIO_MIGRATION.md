# Durable studio migration

The Supabase backend now stores artifact metadata, organization membership and
project histories in `lasermcp_artifacts`, `lasermcp_organizations`,
`lasermcp_organization_members` and `lasermcp_projects`. SVG/DXF bytes remain in
the existing Supabase Storage bucket. Without Supabase credentials, local
development continues to use SQLite and JSON. A remote error never falls back
to temporary local metadata.

## Deployment order

1. Apply [0002_durable_studio.sql](../migrations/0002_durable_studio.sql) in the
   configured Supabase project's SQL editor. This standalone migration adds
   namespaced tables and functions and leaves other applications' tables intact.
   Do not apply `0001_sprint_0_5.sql` to this shared project: its `organizations`
   name conflicts with an existing application's schema.
2. Run `python -m persist.migrate_studio --check`.
3. With generation paused during cutover, run
   `python -m persist.migrate_studio --apply --data-dir <legacy-studio-directory>`
   on each machine that still has legacy records. Existing remote rows are
   preserved; local source records are never deleted. Missing object bytes must
   already exist in Storage; otherwise migration stops rather than creating a
   broken reference. Rerunning skips registered artifacts and existing projects.
4. Deploy the updated server with `SUPABASE_URL` and
   `SUPABASE_SERVICE_ROLE_KEY` configured. Keep the service-role key on the server.
5. Generate a design, then open its URL in a browser signed in with the same
   account. Verify loading from a fresh server instance and check version history.

Previously lost Vercel `/tmp` records cannot be recovered by this migration.
File IDs and project IDs that are still available are preserved.

Project version append and latest-version approval lock the project row in SQL
to avoid losing concurrent updates. Direct browser access to the new metadata
tables and SQL functions is revoked; access remains through the existing server.

Automated checks: `test_durable_studio.py`, `test_sprint_0_5.py`, `test_editor.py`
and `test_workshop.py` (45 tests passed).

## Applied on 2026-09-17

The SQL migration was applied to the configured Supabase project, and six
available local project histories were copied. The source SQLite database had
no artifact rows, so no legacy artifact metadata could be copied from it.
Source files were preserved.

Live verification passed: a persisted SVG and its project were readable in a
fresh Python process, an unrelated user was denied file access, eight concurrent
version appends received consecutive unique numbers, and latest-version approval
was retained. Only isolated smoke-test records were deleted afterwards.

The updated server was deployed to `https://mcp.metehanavci.com` on 2026-09-17.
Production deployment: `dpl_GxZU32H3y63mUc7t5x55LFc2RExY`.

## 24-hour retention and editor load fix

`0003_artifact_retention.sql` has been applied. It enforces a creation-based
24-hour lifetime and schedules Storage cleanup every 15 minutes, in batches of
100 objects. The cleanup function uses Vault-held credentials and deletes
metadata only after a successful Storage API response. Active files remain.
Live tests verified real expired object deletion and that older code cannot
clear the expiry. Only isolated test records were removed by the smoke tests.

The updated editor API returns project context and SVG together with no-cache
headers. The browser retries transient failures, returns to the file after
sign-in, distinguishes expiry from missing files, and disables controls if
loading fails. Additional generated sheets and attachments use the same managed
storage and retention. New Vercel Blob duplicates are disabled when Supabase is
configured; previously untracked legacy Blob objects cannot be cleaned through
the new metadata table.

The MCP server/editor changes are deployed and the public file URL has been
verified end to end. Previously lost temporary files still require regeneration.

Latest checks: 71 Python tests passed across retention, editor, workshop,
durable studio, Sprint 0.5 and auth suites. Browser tests passed for editor
interactions and load failure/retry/sign-in scenarios. A real compiled design,
its attachments and editable metadata were verified together through the editor
API against live Supabase. The scheduled cleanup job also recorded a successful
automatic run. Production was missing `SUPABASE_SERVICE_ROLE_KEY`; the existing
project credential was added as a Sensitive production variable before deployment.
The deployed editor asset matches the local source byte for byte. A real isolated
design loaded through the production domain's editor API with SVG, editable parts
and expiry, and its `/out/` page returned successfully. Test records were removed.
