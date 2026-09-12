# Product Roadmap

Design only. **Sprint 1 is not implemented in this pass.**

Existing product to keep intact: Google login, onboarding pages, enterprise API keys, MCP tools and OAuth.

---

## 1. Current architecture summary

LaserMCP is a **Python MCP + Starlette** server with a **static HTML** site. CAD is Boxes.py. The digital pipeline (review → repair → gate) runs **inside** `create_design`.

Supabase is **Google Auth HTTP only**. Application state is **JSON/JSONL + local files**. On Vercel, files default to **`/tmp`** unless env overrides (those overrides: **NOT VERIFIED**).

Tenants are not isolated. “Organization” means allowlisted email that may mint hashed `lzr_` keys. Sessions are HMAC cookies. MCP clients use PKCE OAuth or those keys.

---

## 2. What is already implemented

- Google sign-in via Supabase Auth; signed `lmcp_sid`; account page + nav profile.
- Connect guides (ChatGPT / Claude / Cursor) and MCP OAuth 2.1 + PKCE + DCR host allowlist.
- Hashed org API keys, shown once, owner-scoped listing when auth is on.
- Bearer/cookie gate on `/mcp`, `/files`, most `/api/*`.
- Planner + compose/trace rules; named Payas kits; review scorecard; human physical flags.
- Hardcoded material/machine catalogs; coupon calibration JSON.
- Plans catalog in code (beta open ⇒ entitlements off).
- Landing 5-step onboarding copy; demo kit wow section.
- Usage JSONL + telemetry JSONL.
- Global `projects.json` version append on finished jobs with `file_id`.

---

## 3. What is partially implemented

| Feature | Partial piece |
| --- | --- |
| Projects / history | Unowned JSON versions, often every file |
| Machine / material profiles | System catalog, not tenant profiles |
| Usage | Append-only log, not daily aggregates, not billing-ready |
| Prototype feedback | Flags on the generate call, not a feedback entity |
| Template gallery | Three static demos |
| Connection center | Docs + OAuth, no connection registry UI/data |
| Production status | `PRODUCTION READY` exists in reviewer if humans pass flags; marketing says software never says PRODUCTION |
| Persistence | Works on a single local disk; serverless durability unknown |

---

## 4. Top product gaps

1. No durable, owned **Project** as the unit of work.
2. No **optimistic concurrency** for two AIs.
3. No **MCP Connection Center** as a product (status, revoke, last seen).
4. No **template gallery** beyond three files.
5. No **team workspace** / membership.
6. No **billing** (correct for now).
7. No tenant **machine/material** profiles or stored **prototype feedback** loop.
8. Status model missing DRAFT / VALIDATED / PROTOTYPE_VALIDATED / ARCHIVED.

---

## 5. Top database risks

There is **no application database**. The risk is building the wrong one:

- Putting SVG/review JSON in Postgres.
- Per-MCP-call fact rows.
- Cloning `projects.json` (speak blobs, no owner) into a table.
- Full-document rewrites (`touch_key`, `users.json`) as SQL transactions that still serialize the world.

Official Free Plan size: **LIMIT NOT VERIFIED**.

---

## 6. Top storage risks

1. Vercel `/tmp` as CAD + key store (**env NOT VERIFIED**).
2. Shared `OUTPUT_DIR` + `latest.svg`.
3. Auth-gated but **not owner-gated** `/files/{file_id}`.
4. PNG previews kept forever; no WebP; no TTL.
5. Sidecar JSON duplicates the whole review.

---

## 7. Top security risks

1. Cookie HMAC may fall back to **public anon key** or a **dev literal** if `MCP_SESSION_SECRET` is unset — **production value NOT VERIFIED**.
2. IDOR on projects, calibrations, files.
3. No key revoke / expiry.
4. No rate limit.
5. Google access token on MCP hot path → Auth API load.
6. Customer files are capability-by-filename after login.

---

## 8. Supabase Free Plan bottlenecks

Today the app barely uses the plan (Auth only). Bottlenecks **after** a naive port:

| Bottleneck | Why |
| --- | --- |
| DB size / I/O | Artifacts or per-call usage in Postgres |
| Auth rate | `/auth/v1/user` per Google-bearer tool call |
| Storage (if used) | No lifecycle on tmp renders |
| Row churn | `last_used` every resolve |

Exact quotas: **LIMIT NOT VERIFIED**.

---

## 9. Changes required before Projects

Do these **without** shipping the Projects product UI:

1. **Durability decision:** where do `users`, keys, and artifacts live if not `/tmp`? (object storage + Postgres **or** a persistent volume). Confirm current Vercel env — **NOT VERIFIED**.
2. **`MCP_SESSION_SECRET`** set and independent of the anon key.
3. **Owner boundary** on any new project row (`organization_id`).
4. **Version insert policy** (success/repair/save/checkpoint only).
5. **Concurrency** (`base_version` / `current_version`).
6. **Artifacts as pointers**; private store; no public guessable forever-URL.
7. **Stop embedding `speak` in the version document.**
8. Resolve **PRODUCTION** speak vs `review.py`.
9. Do **not** migrate blindly; do **not** change Google OAuth flow.

---

## 10. Recommended Sprint 1 implementation plan

**Do not execute this sprint in the current change set.**

Sprint 1 is an **architecture + durability** sprint, not Projects-for-users.

1. Read-only: confirm Vercel `MCP_DATA_DIR`, `MCP_OUTPUT_DIR`, `MCP_SESSION_SECRET`, `LASERMCP_ORG_DOMAINS` (ops, not code).
2. Write (later) a `StorageService` interface + private bucket design; no product UI.
3. Freeze schema draft from `PROPOSED_DATA_MODEL.md`; still **no migration**.
4. Specify MCP error for stale `base_version` (`look_again`, no `error` key).
5. Specify `usage_daily` counters and what **does not** increment versions.
6. Add revoke/expiry **fields** to the key design; do not break existing hashes.
7. Leave Google OAuth, onboarding HTML, and mint rules untouched.

Out of Sprint 1: gallery, billing, workspaces, new MCP tools, feedback UI.

---

## 11. GO / NO-GO for Sprint 1

| | |
| --- | --- |
| **GO** | Ops verification of secrets + disk; design review of this pack; decide object storage vendor (Supabase Storage vs other) **on paper**. |
| **NO-GO** | Implementing Projects, migrations, new Auth, changing Google OAuth, turning off org keys, or storing CAD in Postgres. |

**Overall: CONDITIONAL GO** for a non-feature Sprint 1 (verify + decide).  
**NO-GO** for feature implementation until durability and session secret are known.

If `/tmp` is the live data plane, shipping Projects now would lose customer work. That alone is **NO-GO** for product Projects.

---

## Suggested sequence (after Sprint 1 GO)

0. Durability + secrets (ops).  
1. Artifact metadata + private storage (no gallery).  
2. Owned projects + version policy + concurrency.  
3. `usage_daily` (billing later).  
4. Connection center (revoke, last seen sampled).  
5. Tenant profiles + prototype_feedback.  
6. Status enum alignment.  
7. Workspaces.  
8. Plans / Stripe.

Keep the manufacturing loop:

`AI → Design → Validate → Prototype → Physical Feedback → Production`

Software never invents kerf, hardware, or a physical PASS.
