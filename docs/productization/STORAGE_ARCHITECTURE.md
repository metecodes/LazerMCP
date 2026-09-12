# Storage Architecture (Sprint 0.5)

CAD bytes are **never** stored in PostgreSQL/SQLite metadata tables.

## Layers

| Layer | Local / tests | Production (optional) |
| --- | --- | --- |
| Metadata | `MCP_DATA_DIR/app.sqlite` | Supabase Postgres via `migrations/0001_sprint_0_5.sql` + service role |
| Bytes | `MCP_DATA_DIR/objects/` | Private bucket `LASERMCP_STORAGE_BUCKET` (default `lasermcp-artifacts`) |
| Working CAD | `OUTPUT_DIR` (pipeline scratch) | Same; not the customer identity |

## Paths

```
artifacts/{organization_id}/{artifact_id}/{sha256}.{ext}
tmp/{organization_id}/{yyyy-mm-dd}/{uuid}.{ext}
```

`latest.svg` / `latest.dxf` may still be written as **scratch** for the local workshop. They are **not** authorized customer downloads when auth is on.

## Access

1. Authenticate (cookie, `lzr_` key, MCP OAuth, or Google bearer).
2. Authorize organization membership (or key `organization_id`).
3. Local: app proxies bytes from `StorageService.get`.
4. Supabase Storage: short-lived signed URL when `SUPABASE_SERVICE_ROLE_KEY` is set.

Filename is not authorization.

## Persistence flags

| Flag | Meaning |
| --- | --- |
| `design_generation=DESIGN_GENERATION_SUCCESS` | Boxes.py/pipeline wrote a local result |
| `artifact_persistence=ARTIFACT_PERSISTENCE_SUCCESS` | Durable metadata + object write succeeded |
| `ARTIFACT_PERSISTENCE_FAILED` | Do not treat as a stored customer artifact |
| `durable_persistence` | True only for `PROTOTYPE READY` / `PRODUCTION READY` **and** a successful object write |

`BLOCKED` jobs that still produce a local SVG are stored as **tmp** (24h `expires_at`) when an org exists.

Preview/validate MCP tools do not call this persist path.

## Preview format

Persistent previews try WebP via Pillow. If libwebp is unavailable, PNG is kept. SVG/DXF are never converted.

## Cleanup

`persist.cleanup.cleanup_expired` deletes expired metadata + objects. Invoked at most hourly from `attach_durable_artifacts`. Not a distributed cron. Document a daily job in production if you need strict TTL.

## Service role

The browser never receives `SUPABASE_SERVICE_ROLE_KEY`. MCP/API-key traffic cannot use Supabase user JWT RLS alone; the server authorizes in Python and uses the service role as a **defense-in-depth companion**, not the only lock.
