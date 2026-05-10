CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT        UNIQUE NOT NULL,
    display_name    TEXT,
    avatar_url      TEXT,
    is_admin        BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

-- One row per (user, provider) — same email can log in via Google, GitHub, or local
-- and all map to the same user.id
CREATE TABLE IF NOT EXISTS user_identities (
    id              BIGSERIAL   PRIMARY KEY,
    user_id         UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider        TEXT        NOT NULL,   -- 'local' | 'google' | 'github' | 'microsoft'
    provider_id     TEXT,                   -- NULL for provider='local'
    password_hash   TEXT,                   -- only used when provider='local'
    password_salt   TEXT,                   -- bcrypt salt, only used when provider='local'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, provider_id),
    UNIQUE (user_id, provider)
);

-- Admin-managed allowlist: only emails listed here (or in ADMIN_EMAILS env) may register
CREATE TABLE IF NOT EXISTS allowed_emails (
    email       TEXT        PRIMARY KEY,
    note        TEXT,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id          TEXT        PRIMARY KEY,
    user_id     UUID        REFERENCES users(id) ON DELETE CASCADE,
    model       TEXT        NOT NULL,
    title       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id
    ON chat_sessions (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id          BIGSERIAL   PRIMARY KEY,
    chat_id     TEXT        NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        TEXT        NOT NULL,   -- 'human' | 'assistant' | 'system'
    content     TEXT        NOT NULL,
    thinking    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_id
    ON messages (chat_id, id ASC);
