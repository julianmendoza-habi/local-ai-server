-- Migration 001: replace OAuth-only users table with local-auth schema
-- Safe to run against an empty users table (no data loss beyond provider/provider_id columns).

-- 1. Add new columns to users
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS avatar_url TEXT;  -- already existed in old schema, IF NOT EXISTS handles it

-- 2. Drop OAuth-only columns (no longer needed — moved to user_identities)
ALTER TABLE users
    DROP COLUMN IF EXISTS provider,
    DROP COLUMN IF EXISTS provider_id;

-- 3. Multi-provider identities table
CREATE TABLE IF NOT EXISTS user_identities (
    id              BIGSERIAL   PRIMARY KEY,
    user_id         UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider        TEXT        NOT NULL,   -- 'local' | 'google' | 'github' | 'microsoft'
    provider_id     TEXT,                   -- NULL for provider='local'
    password_hash   TEXT,                   -- only used when provider='local'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, provider_id),
    UNIQUE (user_id, provider)
);

-- 4. Admin-managed allowlist
CREATE TABLE IF NOT EXISTS allowed_emails (
    email       TEXT        PRIMARY KEY,
    note        TEXT,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
