-- REVIEW ONLY. Not executed by this task. Default is ROLLBACK.
-- Requires two independently approved proofs described in GOOGLE_ACCOUNT_MIGRATION.md.
-- Supply psql variables target_user_id (UUID) and approved_google_sub (verified sub).
-- Do not put Google credentials, passwords or session JWTs into SQL/variables.
\set ON_ERROR_STOP on
BEGIN;
SELECT id, google_sub, is_active, is_admin
FROM app_users
WHERE id = :'target_user_id'::uuid
FOR UPDATE;

-- Reviewer must confirm exactly one changed row, preserve all original roles/IDs.
UPDATE app_users
SET google_sub = :'approved_google_sub', updated_at = CURRENT_TIMESTAMP
WHERE id = :'target_user_id'::uuid
  AND google_sub IS NULL
  AND is_active = TRUE
  AND is_admin = FALSE
  AND length(:'approved_google_sub') BETWEEN 1 AND 255
  AND NOT EXISTS (
      SELECT 1 FROM app_users AS bound
      WHERE bound.google_sub = :'approved_google_sub'
  )
RETURNING id, google_sub, is_active, is_admin;

-- Review the returned identity and unchanged ownership/privilege fields.
-- An approved execution copy requires a separate, explicit authorization.
ROLLBACK;
