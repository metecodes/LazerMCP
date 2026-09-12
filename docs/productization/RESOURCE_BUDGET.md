# Resource Budget

Estimates for the **planned** SaaS features, grounded in **current write behavior** where verified.

Official Supabase Free Plan numeric limits: **LIMIT NOT VERIFIED**.  
This file is an architecture budget, not a pricing sheet.

Labels:

- **VERIFIED** — observed in code.
- **ASSUMPTION** — planning number, not measured in production.
- **LIMIT NOT VERIFIED** — vendor quota unknown from this repo.

---

## Current write profile (VERIFIED)

One successful `create_design` / named kit persist typically creates:

| Artifact | Type | Notes |
| --- | --- | --- |
| `{stem}.svg` | SVG | Always if persist path runs |
| `latest.svg` | SVG | Global overwrite |
| `{stem}.json` | JSON sidecar | Large: primitives + review |
| `{stem}-preview.png` | PNG | If nest preview succeeds |
| `{stem}-production.md` | Markdown | Gate card |
| `{stem}-assembly.txt` | Text | If assembly sheet exists |
| `{stem}-bom.txt` | Text | If BOM speak exists |
| `{stem}.dxf` + `latest.dxf` | DXF | If DXF entitled / produced |
| 1 `usage.jsonl` line | JSONL | `finish_result` |
| 1–2 `telemetry.jsonl` lines | JSONL | job_saved / look_again |
| 1 project version | JSON rewrite | If `entitled("project_history")` (beta default **on**) and `file_id` exists |
| 1 `api_keys.json` rewrite | JSON | If request used a hashed key (`touch_key`) |

Failed generations that never persist a `file_id` do not call `save_version` (it returns `None` without name/pid/`file_id`). **Failed in-memory reviews that still persist SVG: NOT VERIFIED per all call sites** — persist happens after pipeline in the adapter; BLOCKED jobs can still write files if the adapter persist path runs. Treat “failed = no version” as a **requirement**, not current law.

`plan_laser_job`, `validate_*`, `list_cad_tools`, `payas_defaults`, `get_generator_schema` do not go through `finish_result` (no usage line from that helper). **Whether some of them write telemetry elsewhere: only `studio.finish_result` and `studio.attach` paths were fully traced.** Other tools: **NOT VERIFIED** as zero-write.

---

## Size assumptions (ASSUMPTION)

Used only for scale math. Not production telemetry.

| Object | Assumed size |
| --- | --- |
| Simple box SVG | 80 KB |
| Compact mill SVG | 400 KB |
| Preview PNG | 200 KB |
| DXF | 150 KB |
| Sidecar JSON | 40 KB |
| md/txt extras | 8 KB |
| **Bundle / successful job** | **~0.5–1.0 MB** (use **0.8 MB** mid) |
| usage/telemetry line | 200 B |
| project version record (current, with speak) | 2–20 KB |

WebP target for **future** persistent previews: **ASSUMPTION** 40–80 KB (not implemented).

---

## Shared columns for every planned feature

For each feature below: rows, writes, reads, storage, file types, retention, cleanup, Free Plan impact.

---

### 1. Projects

| | |
| --- | --- |
| Rows / user | **ASSUMPTION** 3–20 active projects. 1 row per project. |
| Writes / action | Create project: 1 insert. Rename: 1 update. **Must not** write on preview/validate. |
| Reads / action | List: 1 query by `org_id`/`owner_id`. Get: 1 by id. |
| Storage | Metadata only (KB). Artifacts elsewhere. |
| Files | None in SQL. |
| Retention | Until user/org delete or `ARCHIVED` + policy. |
| Cleanup | Soft-delete then GC artifacts. |
| Free Plan impact | Low row count if metadata-only. **LIMIT NOT VERIFIED**. |

Current `projects.json` is global, unowned, and embeds speak — **do not clone that into Postgres**.

### 2. Project version history

| | |
| --- | --- |
| Rows / user | **ASSUMPTION** 2–8 versions / project × projects. |
| Writes / action | 1 insert **only** on successful generation, successful repair, manual save, prototype checkpoint. |
| Reads / action | History list: 1 query. Restore: 1 version + artifact metadata. |
| Storage | Pointers + hash + status. Not SVG. |
| Files | Object store: SVG, optional DXF, WebP preview. |
| Retention | Keep last N (ASSUMPTION 20) or 90 days for drafts; longer for `PROTOTYPE_VALIDATED`+. |
| Cleanup | Drop failed/tmp versions; expire draft blobs. |
| Free Plan impact | Row count grows with AI retries if you version everything — **do not**. |

### 3. Machine profiles

| | |
| --- | --- |
| Rows / user | **ASSUMPTION** 1–5. Org catalog + optional user override. |
| Writes | Rare (create/edit). |
| Reads | 1 per generate (resolve by id). Cacheable. |
| Storage | Tens of rows, small JSON settings. |
| Files | None. |
| Retention | Until replaced. |
| Cleanup | Soft-delete. |
| Free Plan impact | Negligible if not written per job. |

### 4. Material profiles

| | |
| --- | --- |
| Rows / user | **ASSUMPTION** 2–10. |
| Writes | Rare; calibration update is **1 row upsert**, not a new profile per cut. |
| Reads | 1 per generate. |
| Storage | Small. Kerf is a number, not a file. |
| Files | None. |
| Retention | Keep latest calibration; optional history table later. |
| Cleanup | One current row per (org, machine, material). |
| Free Plan impact | Negligible. |

### 5. MCP Connection Center

| | |
| --- | --- |
| Rows / user | **ASSUMPTION** 1–4 connections (ChatGPT, Claude, Cursor, key). |
| Writes | Register / revoke / last_seen. last_seen **must be sampled**, not every MCP call. |
| Reads | Dashboard list. |
| Storage | Client id, redirect, created, revoked. |
| Files | None. |
| Retention | Until revoke + 30 days. |
| Cleanup | Expire DCR clients (today already caps `oauth_clients.json` at 200 — VERIFIED). |
| Free Plan impact | Low if last_seen is not per-call. |

### 6. Usage tracking

| | |
| --- | --- |
| Rows / user | **Target:** 1 `usage_daily` row per org per UTC day. Not 1 row per tool call. |
| Writes / action | Buffer → 1 upsert/day/org (or flush every N events). |
| Reads / action | Billing/dashboard: 30-row month window. |
| Storage | Tiny integers. |
| Files | Optional cold JSONL in object store, not Postgres. |
| Retention | Daily rows: 13–25 months for billing disputes (**ASSUMPTION**). Raw events: 7–14 days then delete. |
| Cleanup | TTL on raw; compact daily. |
| Free Plan impact | **High if you copy `usage.jsonl` into SQL.** Daily aggregates stay small at 1k users (see scale table). |

### 7. Prototype feedback

| | |
| --- | --- |
| Rows / user | **ASSUMPTION** 0–3 per project (tight / perfect / loose + measured mm). |
| Writes | Human submit only. |
| Reads | Gate + history. |
| Storage | Enum + numbers + optional photo **in object storage**. |
| Files | Optional JPEG/WebP of the physical part. |
| Retention | Life of project. |
| Cleanup | With project. |
| Free Plan impact | Low write rate (humans, not AI loops). |

### 8. Template gallery

| | |
| --- | --- |
| Rows | Global catalog **ASSUMPTION** 10–50 templates, not per user. |
| Writes | Admin/publish rare. |
| Reads | Gallery page + MCP pick. Cache. |
| Storage | Template metadata in SQL; preview WebP + SVG in **public or signed** object store (product decision). Demo kits today are static `web/demo/*` — VERIFIED. |
| Files | SVG + WebP. |
| Retention | Until unpublished. |
| Cleanup | Unpublish hides; GC later. |
| Free Plan impact | Catalog is small; **do not duplicate per user**. |

### 9. Plans / billing

| | |
| --- | --- |
| Rows / user | 1 customer + 1 subscription + invoice pointers (**ASSUMPTION**). Stripe remains source of truth. |
| Writes | Webhook updates, not per MCP call. |
| Reads | `entitled()` should read **cached plan** on principal, not Stripe live. |
| Storage | Plan id, period, status. |
| Files | None in-app. |
| Retention | Accounting: long. |
| Cleanup | None aggressive. |
| Free Plan impact | Low. **Do not implement now.** |

### 10. Team workspaces

| | |
| --- | --- |
| Rows / org | 1 org + N members (**ASSUMPTION** 2–15) + invites. |
| Writes | Invite/accept/role change. |
| Reads | Every authorized request needs org membership — **cache on principal**. |
| Storage | Small. |
| Files | None. |
| Retention | Until leave/revoke. |
| Cleanup | Expire invites (7 days **ASSUMPTION**). |
| Free Plan impact | Low if membership is not logged per tool call. |

---

## Scale snapshots

**ASSUMPTION** mix: 40% users generate 2 jobs/month, 40% generate 8, 20% generate 25. Mean **≈ 8.8 jobs / user / month**.  
**ASSUMPTION** 0.8 MB stored artifacts / job if you keep everything forever (current habit).  
Daily usage rows = users × active-days; use **1 row / user / active day**, **ASSUMPTION** 10 active days / month.

| Users | Jobs / month | Artifact GB / month if retained | `usage_daily` rows / month | Project rows (15/user) |
| ---: | ---: | ---: | ---: | ---: |
| 10 | ~90 | ~0.07 | ~100 | 150 |
| 100 | ~880 | ~0.7 | ~1,000 | 1,500 |
| 500 | ~4,400 | ~3.5 | ~5,000 | 7,500 |
| 1,000 | ~8,800 | ~7 | ~10,000 | 15,000 |

If every job also writes a 15 KB sidecar **into Postgres**: +~0.13 GB/month at 1k users of **database** bloat — avoid.

If every MCP tool call writes a fact row (**do not**): 1k users × **ASSUMPTION** 40 calls/job × 8.8 jobs ≈ **350k rows/month**. That is the anti-pattern.

Official whether 7 GB Storage or 15k rows fits Free Plan: **LIMIT NOT VERIFIED**.

---

## Retention and cleanup (required design)

| Class | TTL | Action |
| --- | --- | --- |
| `tmp/` render, failed gen, health/preview | 24 h **ASSUMPTION** | Delete objects; no version row |
| Draft versions without checkpoint | 14–30 days | Delete blobs; keep or drop metadata |
| Prototype checkpoint | 1 year or until archive | Keep SVG + WebP |
| Production-validated | Until customer delete | Keep |
| Raw usage events | 7–14 days | Delete after rollup |
| `usage_daily` | 13–25 months | Then compact or export |
| OAuth codes | 5 min (already `exp` +300s — VERIFIED) | Already dropped on exchange |
| OAuth tokens | 30 days (VERIFIED) | Cap file today; SQL needs `expires_at` |

---

## Free Plan impact (architecture, not vendor numbers)

Cheap:

- Auth users
- Org/project/version **pointers**
- Daily usage
- Profile catalogs

Expensive / fatal if done wrong:

- SVG/PNG/DXF in Postgres
- Per-tool analytics rows
- Updating `last_used` on every MCP call as a full-table write
- Storing `speak` in every version row
- No TTL on `/tmp` copies that you later “sync” into SQL

**LIMIT NOT VERIFIED** for: Auth MAU, DB size, Storage GB, egress, file count, Edge invocations.
