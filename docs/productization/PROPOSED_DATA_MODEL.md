# Proposed Data Model

**Status:** design only. Do not migrate. Do not implement.

Compatible with existing Google login, onboarding pages, org API keys (`lzr_`), and MCP OAuth.  
Does **not** replace Supabase Auth identities.

---

## 0. Persistence rule

| Kind | Store |
| --- | --- |
| Identity | Supabase Auth `user.id` (already used) |
| Relational metadata | Postgres (future), never CAD bytes |
| CAD / preview / reports | Private object storage |
| Hot session | Signed cookie / hashed bearer (already) |
| Usage facts | Daily aggregates in Postgres; raw optional short TTL |

PostgreSQL row for a file:

`project_id`, `version_id`, `storage_path`, `file_size`, `mime_type`, `hash`, `created_at`  
— not the SVG.

Prefer **WebP** for persistent previews. Keep SVG/DXF as cut files. Temporary PNG/render → TTL.

---

## 1. Owner boundary

Prefer **organization ownership** for projects.

Today “org” is only an email-domain flag. Future:

- Every Google user has a **personal organization** (1:1) created at first durable write — **or** projects stay `owner_user_id` until workspaces ship.
- Domain-allowlisted users may belong to a **shared** organization (membership table). Existing `LASERMCP_ORG_DOMAINS` + `can_mint_keys` stay the mint gate until workspaces exist.

**Compatibility path:**

```
organizations
  id
  kind            -- personal | workspace
  name
  created_by      -- auth user id

organization_members
  organization_id
  user_id
  role            -- owner | admin | member
  created_at
```

API keys already have `owner` = user id. Future keys add `organization_id` **without** removing hash-at-rest.

Sprint 1 must **not** invent membership UI. Schema should still have `organization_id` on projects so you do not rewrite later.

---

## 2. Core tables (proposed)

### organizations

| Column | Notes |
| --- | --- |
| id | uuid |
| kind | personal / workspace |
| name | |
| created_by | auth uid |
| created_at | |

### organization_members

| Column | Notes |
| --- | --- |
| organization_id | fk |
| user_id | auth uid |
| role | |
| created_at | |
| unique (organization_id, user_id) | |

### projects

| Column | Notes |
| --- | --- |
| id | uuid |
| organization_id | **owner boundary** |
| created_by | auth uid |
| name | |
| status | see product status |
| current_version | int, starts 0 |
| created_at / updated_at | |

No SVG column.

### project_versions

| Column | Notes |
| --- | --- |
| id | uuid |
| project_id | fk |
| n | int, monotonic per project |
| base_n | int, client’s `base_version` (optimistic concurrency) |
| trigger | generation / repair / manual_save / prototype_checkpoint |
| status | copy of gate at that moment |
| recipe_hash | hash of primitives + parameters (not full JSON dump) |
| created_by | auth uid or key id |
| created_at | |

**Do not insert** for: preview, validation, health, failed generation, tool discovery, `plan_laser_job`.

Failed generation: write optional `generation_attempts` (short TTL) or only logs — **no** version.

### artifacts

| Column | Notes |
| --- | --- |
| id | uuid |
| organization_id | for RLS |
| project_id | |
| version_id | nullable for tmp |
| kind | svg / dxf / preview_webp / report / bom / tmp |
| storage_path | |
| file_size | |
| mime_type | |
| hash | sha256 |
| created_at | |
| expires_at | null if durable; set for tmp |

### api_keys (move from JSON when durable DB exists)

Keep current security properties:

| Column | Now | Proposed |
| --- | --- | --- |
| id | yes | yes |
| name | yes | yes |
| hash | yes | yes (never plaintext) |
| prefix | no | `lzr_` + first 8 public chars |
| owner / organization_id | owner user | both |
| created | yes | created_at |
| last_used | yes | last_used_at, **sampled** |
| expires_at | no | nullable |
| revoked_at | no | nullable |
| role / plan / email / kind | yes | yes |

### usage_daily

| Column | Notes |
| --- | --- |
| organization_id | |
| date | utc |
| generation_count | |
| validation_count | |
| repair_count | |
| preview_count | |
| export_count | |
| mcp_call_count | |
| unique (organization_id, date) | |

Buffer in process or a queue; flush upsert. **No unlimited `usage_events` table for billing.**

Optional `usage_events` with 7–14 day TTL only if you need debug — not required for Sprint 1.

### machine_profiles

| Column | Notes |
| --- | --- |
| id | |
| organization_id | null = system catalog |
| name | |
| machine_type | e.g. diode / CO2 — catalog string |
| bed_w / bed_h | mm |
| y_up | bool |
| cut / etch | colors |
| gap_mm / nick_mm | workspace |
| extra | jsonb **small** settings only |

Seed from today’s `profiles.MACHINES` (`payas_workshop`, `desktop_400`, `lasercad_900`).

### material_profiles

| Column | Notes |
| --- | --- |
| id | |
| organization_id | null = system |
| name | |
| material | poplar / mdf / acrylic |
| nominal_thickness_mm | |
| measured_thickness_mm | nullable, human |
| kerf_mm | from coupon, **not invented by AI** |
| preferred_fit | tight / standard / loose |
| sheet_w / sheet_h | |

### prototype_feedback

| Column | Notes |
| --- | --- |
| id | |
| organization_id | |
| project_id / version_id | |
| fit | too_tight / perfect / too_loose |
| measured_bar_mm | |
| measured_joint | optional |
| notes | short text |
| photo_artifact_id | optional |
| created_by / created_at | |

Maps today’s `physical.py` human flags into a stored object. Software still must not invent PASS.

---

## 3. Product status model

Do not let model prose set production.

| Status | Meaning | Who sets |
| --- | --- | --- |
| DRAFT | Recipe exists, no successful authorized SVG | System |
| VALIDATED | Digital gate PASS (today’s digital scorecard) | Reviewer |
| PROTOTYPE_READY | Authorized Prototype SVG | Reviewer (exists today as `PROTOTYPE READY`) |
| PROTOTYPE_VALIDATED | Human prototype_feedback recorded | Human |
| PRODUCTION_READY | Validation rules **and** physical confirmation | Human + rules — never AI text |
| ARCHIVED | Hidden from default lists | Human |

Map current strings:

- `BLOCKED` → stay `DRAFT` or a `BLOCKED` overlay; do not skip to prototype.
- `PROTOTYPE READY` → `PROTOTYPE_READY`.
- `PRODUCTION READY` → only if feedback + kerf/assembly/movement/use rules pass (already `physical.production_ok`).

Landing instruction “software never says PRODUCTION” should become: software may **compute** eligibility; **UI/MCP speak** stays non-production until `PROTOTYPE_VALIDATED` + policy. Resolve this copy vs `review.py` before shipping Projects.

---

## 4. Optimistic concurrency

Problem (required): ChatGPT and Cursor both read v7; both try to write v8.

```
Client sends: project_id, base_version (= 7), recipe
Server: if projects.current_version != base_version → 409 stale
Else: insert version n = current+1, set current_version = n
```

MCP `look_again`: “base_version 7 is stale; current is 8; fetch version 8.”  
Do not merge silently. Do not overwrite.

`base_n` on `project_versions` is the audit trail.

---

## 5. Object storage layout

```
artifacts/{organization_id}/{project_id}/{version_id}/{hash}.svg
artifacts/{organization_id}/{project_id}/{version_id}/{hash}.webp
artifacts/{organization_id}/{project_id}/{version_id}/{hash}.dxf
tmp/{organization_id}/{yyyy-mm-dd}/{uuid}.png
```

Bucket: **private**. Access: app authorization then **signed URL** (short TTL, **ASSUMPTION** 5–15 min).

Do not serve `GET /files/{guessable-name}` as a permanent public object.

`latest.svg` must die as a global name.

---

## 6. Cleanup

| Prefix / kind | Policy |
| --- | --- |
| `tmp/` | TTL 24 h, cron or lifecycle rule |
| Failed gen | no `project_versions` row; tmp only |
| Preview/validate | tmp only |
| Orphan artifacts | GC if no artifact row |
| Revoked keys | `revoked_at` set; hash remains for audit |

---

## 7. Usage buffering

1. Increment in-memory counters keyed by `organization_id` (process-local is enough on one box; on Vercel use Redis / or write upsert with `ON CONFLICT` **at most once per request batch**, not 8 statements).
2. Flush to `usage_daily`.
3. Billing later reads daily sums. Stripe is out of scope.

Do not call `touch_key` as a full document rewrite on every MCP hit. Future: update `last_used_at` at most once per hour per key.

---

## 8. Repository boundaries (do not refactor yet)

Propose, later:

| Port | Hides |
| --- | --- |
| `OrganizationRepository` | orgs + members |
| `ProjectRepository` | projects |
| `VersionRepository` | versions + concurrency |
| `ArtifactRepository` + `StorageService` | metadata + signed put/get |
| `UsageRepository` | daily upsert |
| `KeyRepository` | hashed keys |

Keep `supabase_auth.py` as the **Auth adapter** only. Do not let `server.py` grow raw SQL.

---

## 9. What stays file-local until Sprint 0 durability

Until `MCP_DATA_DIR` / object storage is durable:

- Do not add Postgres “because SaaS”.
- Do not migrate `users.json` mid-flight without a backup story.

Auth can stay Supabase-only. Application data needs a **non-`/tmp`** disk or a database **before** Projects are real.
