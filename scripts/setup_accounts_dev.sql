-- ============================================================
-- Accounts schema dev setup for folder-sharing-mvp branch
-- Run once against local DB: psql -h localhost -U rds -d goat -f this_file.sql
-- ============================================================

-- 1. Add organization_id to accounts.user (missing from core stub)
ALTER TABLE accounts."user"
    ADD COLUMN IF NOT EXISTS organization_id UUID
        REFERENCES accounts.organization(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_user_organization_id
    ON accounts."user" (organization_id);

-- 2. Add role_id to accounts.user_team (missing from core stub, needed for full auth)
ALTER TABLE accounts.user_team
    ADD COLUMN IF NOT EXISTS role_id UUID
        REFERENCES accounts.role(id) ON DELETE SET NULL;

-- 3. Create accounts.resource_grant
CREATE TABLE IF NOT EXISTS accounts.resource_grant (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_type   VARCHAR(50)  NOT NULL,
    resource_id     UUID         NOT NULL,
    grantee_type    VARCHAR(50)  NOT NULL,
    grantee_id      UUID         NOT NULL,
    role_id         UUID         NOT NULL REFERENCES accounts.role(id) ON DELETE CASCADE,
    granted_by      UUID         NOT NULL REFERENCES accounts."user"(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (resource_type, resource_id, grantee_type, grantee_id)
);

CREATE INDEX IF NOT EXISTS idx_resource_grant_resource
    ON accounts.resource_grant (resource_type, resource_id);

CREATE INDEX IF NOT EXISTS idx_resource_grant_grantee
    ON accounts.resource_grant (grantee_type, grantee_id);

-- 4. Insert folder roles (role table has no UNIQUE on name, guard with WHERE NOT EXISTS)
INSERT INTO accounts.role (name, created_at, updated_at)
SELECT v.name, now(), now()
FROM (VALUES ('folder-viewer'), ('folder-editor')) AS v(name)
WHERE NOT EXISTS (
    SELECT 1 FROM accounts.role r WHERE r.name = v.name
);

-- 5. Seed dev data: organisation, user, team, memberships
--    Use fixed UUIDs so dev scripts can reference them reliably

-- Organisation
INSERT INTO accounts.organization (id, name, avatar, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Plan4Better Dev',
    '',
    now(), now()
) ON CONFLICT (id) DO NOTHING;

-- User
INSERT INTO accounts."user" (id, firstname, lastname, avatar, organization_id)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    'Dev',
    'User',
    '',
    '00000000-0000-0000-0000-000000000001'
) ON CONFLICT (id) DO NOTHING;

-- Update organization_id for existing users that don't have one (dev convenience)
-- Only runs if the column was just added and existing rows are NULL
UPDATE accounts."user"
SET    organization_id = '00000000-0000-0000-0000-000000000001'
WHERE  organization_id IS NULL
  AND  id != '00000000-0000-0000-0000-000000000002';

-- Team
INSERT INTO accounts.team (id, name, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000003',
    'Marketing Dev Team',
    now(), now()
) ON CONFLICT (id) DO NOTHING;

-- User → Team membership
INSERT INTO accounts.user_team (user_id, team_id)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000003'
) ON CONFLICT DO NOTHING;

-- 6. Stamp the accounts alembic version table so future accounts migrations work
CREATE TABLE IF NOT EXISTS alembic_version_accounts (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_accounts_pkc PRIMARY KEY (version_num)
);

-- Stamp at the latest accounts migration (03aa40b88854 = added_credit_usage_table)
-- This tells accounts alembic "everything up to this point is already applied"
INSERT INTO alembic_version_accounts (version_num)
VALUES ('03aa40b88854')
ON CONFLICT DO NOTHING;

-- Done
SELECT 'accounts dev setup complete' AS status;
