# Phase MVP-R1.2 — Invite Security Closure

**Date:** 2026-07-26  
**Branch:** `mvp-r12/data-and-invite-closure` → `release/demo-staging`  
**State:** B (real provider not active, real_calls=0, cost=¥0)

## Decision: `INVITE_SECURITY_CLOSED`

All P0 security gaps from the post-deployment audit are fixed.
Migrations must be applied to Supabase (owner action).

## P0 Fixes Implemented

| # | Issue | Fix |
|---|-------|-----|
| P0-R1.2-1 | `POST /auth/register` — no invite required | `invite_code` field required; atomic validate+consume |
| P0-R1.2-2 | `POST /mvp/invites` — no admin auth | `is_admin=True` Bearer token required |
| P0-R1.2-3 | Invite codes stored as plaintext | SHA-256 hash only; plaintext never persisted |
| P0-R1.2-4 | No `is_admin` field on User | `is_admin` column + migration `o3p4q5r6s7t8` |
| P0-R1.2-5 | MVP tables missing from Supabase | **Owner action: `alembic upgrade head`** |

## What Was Implemented

### Backend

- **Migration `o3p4q5r6s7t8`** — adds `is_admin` to `app_users`; adds `code_hash`/`code_prefix` to `mvp_invite`; drops plaintext `invite_code` column
- **`User` model** — `is_admin: bool = False`; `RegisterRequest` now requires `invite_code`
- **`MvpInvite` model** — `code_hash` (SHA-256, unique) + `code_prefix` (8 chars for display); plaintext field removed
- **`auth.py`** — atomic register+redeem in one transaction (`SELECT FOR UPDATE`); email login support
- **`mvp.py`** — hash-based invite lookups; admin auth on `POST /mvp/invites`; new `GET /mvp/admin/invites`; new `DELETE /mvp/admin/invites/{id}`; removed old `/mvp/invites/redeem`
- **`runtime_reliability.py`** — `AuthPrincipal.is_admin` field; `role="admin"` propagation
- **`dependencies.py`** — `get_admin_user` dependency
- **`backend/app/cli/create_admin.py`** — CLI to create or promote admin users

### Frontend

- **`AdminInvitesView.vue`** — full invite management UI: create/list/revoke
- **Router** — `/admin/invites` route added

## Tests

- **96/96** MVP-R1.2 targeted PASS
- **74/74** MVP-R1.1 regression PASS
- **114/114** MVP-R1 regression PASS
- **284 PASS / 0 FAIL** total

## Owner Action Required

```bash
# 1. Apply migrations to Supabase
cd backend
DATABASE_URL="$SUPABASE_DATABASE_URL" alembic upgrade head

# 2. Create first admin user
DATABASE_URL="$SUPABASE_DATABASE_URL" python -m app.cli.create_admin \
  --username admin --email admin@yourcompany.com --password STRONGPASSWORD

# 3. Verify tables exist
psql $SUPABASE_DATABASE_URL -c "SELECT table_name FROM information_schema.tables WHERE table_name IN ('mvp_invite','chat_feedback','mvp_analytics_event');"
```

## Invite Flow (Post-Fix)

```
Admin login → POST /mvp/invites (Bearer admin token)
  → server: generate 48-char code, store sha256(code) + prefix[:8]
  → response: plaintext code (returned ONCE)
Admin → send code out-of-band to user

User → POST /auth/register {username, email, password, invite_code}
  → server: SELECT mvp_invite FOR UPDATE WHERE code_hash = sha256(invite_code)
  → validate: exists, not expired, use_count < max_uses, email binding
  → INSERT app_users
  → FLUSH (get user.id)
  → UPDATE mvp_invite (use_count++, redeemed_by_user_id=user.id)
  → COMMIT
```

## Why

MVP-R1.1 deployed to `aastock.cloud` revealed two categories of issues:
1. MVP tables missing from Supabase (migration never applied)
2. Critical security gaps in the invite-only registration flow

This phase closes all security gaps. The data/migration issue requires an owner `alembic upgrade head` against Supabase.
