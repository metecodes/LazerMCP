# Current Architecture

**Source of truth:** this repository, inspected 12 September 2026.  
**Not inspected:** live Supabase dashboard, Vercel env values, production disk, DNS, Google Cloud OAuth client settings.

Anything not proven in code is marked **NOT VERIFIED**.

**Sprint 0.5 addendum (code):** `persist/` adds SQLite application metadata (`organizations`, `organization_members`, `artifacts`, `api_keys`), private object storage, owner-gated `/files`, sampled `last_used`, and an in-memory rate limiter. Production session HMAC requires an independent `MCP_SESSION_SECRET`. JSON stores are still the compatibility path. Supabase Postgres/Storage are opt-in via service role; repositories still write SQLite unless/until PostgREST is wired. See `SPRINT_0_5_IMPLEMENTATION_REPORT.md`.

---

## 1. Frontend

| Claim | Verified |
| --- | --- |
| Framework | None. Static HTML + CSS + page-local JavaScript under `web/`. |
| Bundler / SPA | Not present. |
| React / Next / Vue | Not present. |
| Pages | `landing.html` (`/`), `connect.html` (`/connect`), `account.html` (`/account`, `/auth/callback`), `index.html` (`/app`, `/workshop`), `dashboard.html` (`/dashboard`). |
| Shared script | `web/nav-auth.js` — `GET /api/account` with `credentials: "same-origin"`. |
| i18n | In-page TR/EN dictionaries (`localStorage.lmcp_lang`). |

Onboarding is marketing + connect copy, not a persisted wizard:

- Landing `#how`: AI → parametrik tasarım → mekanik doğrulama → üretim doğrulama → lazer kesim çıktısı.
- `connect.html`: ChatGPT / Claude / Cursor steps + Google / org-key cards.
- `account.html`: 5-step hat after sign-in.

There is no onboarding table, step index, or completion flag in code.

---

## 2. Backend

| Claim | Verified |
| --- | --- |
| Runtime | Python. Entry `server.py`. |
| HTTP | Starlette `Request` / `Response` / `FileResponse` / `JSONResponse`. |
| MCP | `mcp.server.mcpserver.MCPServer` (`mcp>=2.2.0`). Streamable HTTP at `/mcp`. |
| Local serve | `uvicorn` via `server.py:main`. |
| Deploy | `vercel.json` maps `server.py` (`maxDuration` 300). `IS_VERCEL = os.environ.get("VERCEL") == "1"`. |
| CAD | `boxes_adapter.py` imports Boxes.py from `BOXES_PATH` or `vendor/boxes-master`. |
| Pipeline | `pipeline.py` runs Designer → Reviewer → Repair → Reviewer → Final Gate **inside** `create_design`. |
| Manufacturing | Every primitive has `semantic_role` + `operation`. SVG export groups `CUT` / `ENGRAVE` / `SCORE` / `GUIDE` / `LABEL`. Color is presentation. See `docs/MANUFACTURING_OPERATIONS.md`. |

ASGI stack (verified):

```
McpOriginAlias → BearerGate → mcp.streamable_http_app
```

- `McpOriginAlias`: non-GET/HEAD on `/` is rewritten to `/mcp`.
- `BearerGate`: protects paths that are not in `PUBLIC_PATHS` / `PUBLIC_PREFIXES` when `auth_required()` is true.
- Vercel: `stateless_http=True`, DNS-rebinding protection off, body limit 20 MiB.

`requirements.txt` lists CAD/MCP libraries. Starlette/uvicorn are not listed there; they arrive only if the `mcp` package (or the host) provides them. **Host install graph: NOT VERIFIED.**

---

## 3. Supabase integration

Verified usage is **Auth HTTP only**:

- `SUPABASE_URL` + `SUPABASE_ANON_KEY` (or `SUPABASE_PUBLISHABLE_KEY`).
- `GET {SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to=…&apikey=…`
- `GET {SUPABASE_URL}/auth/v1/user` with `Authorization: Bearer` + `apikey` (`verify_access_token`).

Not present in this repo:

- `supabase-py` / `create_client`
- `rest/v1` queries
- Storage API
- Realtime
- Edge Functions
- SQL migrations
- `CREATE TABLE` / RLS policy files

**Postgres schema, buckets, RLS, triggers, Edge Functions: NOT VERIFIED** (no client in this app).

Google OAuth itself is **Supabase Auth → Google provider**. This app does not implement Google token exchange. It only redirects to Supabase authorize and later verifies the access token.

---

## 4. Persistence (actual)

All product state that this process writes is **local JSON / JSONL / files**, not Postgres.

| Store | Module | Path |
| --- | --- | --- |
| Users | `supabase_auth.py` | `{data_dir}/users.json` |
| API keys | `keys.py` | `{data_dir}/api_keys.json` |
| Projects | `projects.py` | `{data_dir}/projects.json` |
| Calibrations | `calibrate.py` | `{data_dir}/calibrations.json` |
| OAuth clients / codes / tokens | `oauth_mcp.py` | `{data_dir}/oauth_*.json` |
| Usage | `metering.py` | `{data_dir}/usage.jsonl` |
| Telemetry | `telemetry.py` | `{data_dir}/telemetry.jsonl` |
| Beta list | `server.py` `/api/beta` | `{data_dir}/beta.jsonl` |
| Legacy sessions | `session_user` fallback | `{data_dir}/sessions.json` |
| CAD artifacts | `boxes_adapter.py` | `{OUTPUT_DIR}/` |

`data_dir()` (`studio_store.py`):

- `MCP_DATA_DIR` if set, else `{OUTPUT_DIR}/studio`.

`OUTPUT_DIR` (`boxes_adapter._resolve_output_dir`):

- `MCP_OUTPUT_DIR` or `LASER_OUTPUT_DIR` if set.
- else if `VERCEL=1`: `{TMPDIR or /tmp}/laser-mcp-output`.
- else: repo `output/`.

**Whether production sets `MCP_DATA_DIR` / `MCP_OUTPUT_DIR` to durable storage: NOT VERIFIED.**

If those env vars are unset on Vercel, users, keys, OAuth tokens, usage, projects, and CAD files live on an **ephemeral serverless disk**. Signed cookie sessions still work because they do not need `sessions.json`.

---

## 5. Authentication architecture

Three bearer/cookie identities, resolved in `keys.resolve_bearer` then `BearerGate`:

1. **Admin override** — env `MCP_AUTH_TOKEN`, compared with `hmac.compare_digest`.
2. **Org API key** — `lzr_` + urlsafe token. Only the SHA-256 hex **hash** is stored. Shown once at mint.
3. **MCP OAuth access token** — `mcp_` prefix, SHA-256 hash in `oauth_tokens.json`, 30-day `exp`, PKCE S256.
4. **Supabase Google access token** — live `auth/v1/user` check, then `upsert_user` into `users.json`.
5. **Browser session** — HttpOnly cookie `lmcp_sid` = HMAC-signed payload (`new_session` / `session_user`), 30 days, `SameSite=lax`, `Secure` when the request is HTTPS.

`auth_required()` is true if Supabase is configured **or** an admin token exists **or** any hashed key file is non-empty.

Query `?token=` is accepted only when `Host` is `127.0.0.1` / `localhost` / `::1`.

Google sign-in routes (do not change in this phase):

- `GET /auth/google` → HTML+Location to Supabase authorize (status 200, not 302).
- `GET /auth/callback` serves `account.html`.
- `POST /api/auth/session` verifies access token, upserts user, sets `lmcp_sid`.
- `POST /api/auth/logout` deletes the cookie.

`next` is filtered by `safe_next_path` (same-origin path or allowlisted origin).

---

## 6. User model

Not a SQL user table.

**Supabase Auth user** (external): `id`, `email`, `user_metadata.full_name|name`. Verified only as the JSON returned by `/auth/v1/user`.

**Local `users.json` row** (verified fields written by `upsert_user`):

| Field | Meaning |
| --- | --- |
| `id` | Supabase user id |
| `email` | Google email |
| `name` | Display name |
| `kind` | `"org"` if email host ∈ `LASERMCP_ORG_DOMAINS`, else `"individual"` |
| `created` | ISO timestamp |
| `last_seen` | ISO timestamp |

`kind` passed into `upsert_user(..., kind=)` is ignored for privilege; domain allowlist wins (`test_upsert_ignores_client_org_kind`).

There is **no** password, avatar, locale, or org_id column.

---

## 7. Organization model

There is **no** organization table, slug, seat count, or billing customer id.

An “organization” is:

- email host listed in `LASERMCP_ORG_DOMAINS`, **and**
- `can_mint_keys()` returns true, **and**
- minted keys get `kind="org"`, `role="workshop"`, `plan="maker"`.

`public_config` returns the allowlist to the browser.

---

## 8. Organization membership model

Sprint 0.5 adds a **personal organization** per authenticated user (`persist.orgs`, SQLite). No invitations, seats, or workspace UI. Keys may carry `organization_id`. Team workspaces remain unimplemented.

---

## 9. API key implementation

`keys.create_key`:

- Token: `lzr_` + `secrets.token_urlsafe(24)`.
- Stored: `id` (8 hex), `name`, `role`, `plan`, `kind`, `owner`, `email`, `hash` (SHA-256 hex of raw token), `created`, `last_used`, plus `prefix` / `expires_at` / `revoked_at` when set. Dual-written to SQLite `api_keys` when available.
- Returned once: `{id, name, role, token, prefix, note: "shown once"}`.
- `list_keys` never returns the raw token or hash.
- `touch_key` is sampled (~1 hour per key), not rewritten on every resolve.

Not stored: raw token, salt, scopes.

Mint path: `POST /api/account/keys` or MCP `studio(action=keys)` — both require `can_mint_keys`.

---

## 10. MCP authentication and endpoints

| Surface | Verified |
| --- | --- |
| MCP URL | `/mcp` (public site `https://mcp.metehanavci.com/mcp` in README / landing copy) |
| Discovery | `/.well-known/oauth-authorization-server`, `/.well-known/oauth-protected-resource` (+ `/mcp`) |
| DCR | `POST /oauth/register` — redirect host allowlist (ChatGPT, Claude, Cursor, localhost, `LASERMCP_OAUTH_REDIRECT_HOSTS`) |
| Authorize | `GET /oauth/authorize` — requires `lmcp_sid`; issues PKCE code |
| Token | `POST /oauth/token` — authorization_code + S256 verifier |
| Tools | `MCP_TOOLS` in `server.py` (list below) |

OAuth metadata CORS: `Access-Control-Allow-Origin: *`.

### MCP tools (registered)

`plan_laser_job`, `create_from_reference`, `create_design`, `payas_defaults`, `list_cad_tools`, `get_generator_schema`, `generate_svg`, `validate_svg`, `validate_assembly`, `render_preview`, `studio`, `create_traffic_light`, `create_robot_bank`, `create_drawing_robot`, `create_product_box`, `create_yacht`, `create_astronaut`.

Named `create_*` kits are existing Payas products only.

---

## 11. Authorization middleware

`BearerGate` is the only request gate. It is not per-resource ACL.

After a principal is set in `current_auth`:

- `plans.entitled` / `gate_job` — **bypassed when `LASERMCP_BETA` is unset or truthy** (`beta_open()` defaults open).
- `studio.overview` / `studio_action(keys)` — keys listed by owner when configured.
- `list_projects` / `project_history` — **no owner filter**.
- `list_calibrations` — **no owner filter**.
- `/files/{filename}` — any authenticated principal who can guess `file_id` and whose instance still has the file.

Cookie sessions also unlock `/api/*` and `/files` when Bearer is absent.

---

## 12. HTTP API (non-MCP)

Public without bearer (still may 401 inside the handler): `/`, `/health`, `/connect`, `/account`, `/auth/*`, `/api/auth/config`, `/api/auth/session`, `/api/auth/logout`, `/api/account`, `/api/plans`, `/api/beta`, `/api/demo`, `/demo/*`, brand assets, `/.well-known/*`, `/oauth/*`.

Protected when auth is on: `/mcp`, `/files/*`, `/api/generate`, `/api/validate`, `/api/preview`, `/api/studio`, `/api/generators`, `/api/schema`, `/api/cad/*`, `/api/status` (status is **not** in `PUBLIC_PATHS` — verified).

`/api/account` is in `PUBLIC_PATHS` so the browser can call it without a Bearer header; the handler requires cookie or `current_auth`.

---

## 13. Storage architecture (files)

Successful generation (`boxes_adapter` persist path) writes, when present:

- `{stem}.svg` plus `latest.svg`
- `{stem}.json` sidecar (speak, scorecard, primitives, bom, nesting, …)
- `{stem}-preview.png`
- `{stem}-production.md`
- `{stem}-assembly.txt`
- `{stem}-bom.txt`
- `{stem}.dxf` plus `latest.dxf`
- extra nest sheets `{stem}-sheetN.svg`

`file_id` is a filename, not a UUID object key. URLs are `{public_base}/files/{file_id}`.

`_safe_output_file` blocks path traversal (`parent != OUTPUT_DIR`). It does not check owner.

PNG previews exist. **WebP is not used.**  
**Signed URLs are not implemented.**  
**Object storage (S3 / Supabase Storage) is not implemented.**

---

## 14. Rate limiting

**Not implemented.** No token bucket, no IP throttle, no per-key QPS in this repo.

---

## 15. Logging

- `telemetry.emit` → `telemetry.jsonl` (no SVG bodies; fields truncated to 400 chars).
- `record_usage` → `usage.jsonl` (one line per finished job in `finish_result`).
- Process logs: uvicorn `log_level=info`. **Central APM: NOT VERIFIED.**

`usage_summary` reads the **last 200 lines** then counts those only. `designs_this_month` scans the **entire** file.

---

## 16. Plans / billing

`plans.py` defines `free` / `maker` / `pro` quotas and feature flags in memory. `public_plans()` hides `price_usd`. No Stripe, no webhook, no customer portal.

`LASERMCP_BETA` default open → `entitled(*)` is always true → quotas and feature strips do not apply unless beta is turned off.

---

## 17. Product status (current)

`review.py` / MCP instructions:

| Status | When |
| --- | --- |
| `BLOCKED` | Required digital FAIL or NOT_VERIFIED |
| `PROTOTYPE READY` | Digital OK; physical not all PASS |
| `PRODUCTION READY` | Digital OK **and** `physical.production_ok` (human kerf + assembly + movement + use) |

MCP tool instructions tell the client: software never authorizes production; paste `speak` verbatim. `PRODUCTION READY` **can still be set in `review.py` if human flags are passed**. That is a policy/product tension with landing copy (“yazılım PRODUCTION demez”).

Statuses **not** in code: `DRAFT`, `VALIDATED`, `PROTOTYPE_VALIDATED`, `ARCHIVED`.

---

## 18. Partial product surfaces already in code

| Roadmap item | What exists | Gap |
| --- | --- | --- |
| Projects | `projects.save_version` into one global JSON | No owner, no concurrency, versions on almost every `file_id` |
| Version history | Version array + `studio` history action | Same file, no ACL |
| Machine / material profiles | Hardcoded `profiles.MATERIALS` / `MACHINES` | Not user-owned; kerf is catalog default |
| MCP connection center | `connect.html` + OAuth DCR | No connection records |
| Usage | `usage.jsonl` + monthly count | Unbounded append, not daily aggregates |
| Prototype feedback | `physical.py` human flags | No stored feedback object / fit enum |
| Template gallery | `demo_kits.py` three static kits | Not a gallery product |
| Plans / billing | In-code catalog | No payments |
| Team workspaces | — | Absent |

---

## 19. Deployment architecture

Verified:

- GitHub `metecodes/LazerMCP` (README).
- Vercel function wrapping `server.py`.
- Public host named in copy: `mcp.metehanavci.com`.

Not verified: region, cron, durable volume, CDN, custom domain certs, whether `/tmp` is the live data plane.
