CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Reserved for future OAuth2 authentication.
-- user_id on chat_sessions is nullable so anonymous sessions work today
-- and become attributable once auth is wired in.
CREATE TABLE IF NOT EXISTS users (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT        UNIQUE NOT NULL,
    display_name    TEXT,
    avatar_url      TEXT,
    provider        TEXT        NOT NULL,   -- 'google' | 'github' | 'microsoft'
    provider_id     TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ,
    UNIQUE (provider, provider_id)
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id          TEXT        PRIMARY KEY,
    user_id     UUID        REFERENCES users(id) ON DELETE CASCADE,  -- NULL = anonymous
    model       TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id
    ON chat_sessions (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id          BIGSERIAL   PRIMARY KEY,
    chat_id     TEXT        NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        TEXT        NOT NULL,   -- 'human' | 'assistant' | 'system'
    content     TEXT        NOT NULL,
    thinking    TEXT,                  -- reasoning_content from extended-thinking models
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_id
    ON messages (chat_id, id ASC);
