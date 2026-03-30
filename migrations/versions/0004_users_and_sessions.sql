-- Multi-user auth: users, sessions, tasks.user_id
-- Idempotent for migration runner.

CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    plan          TEXT NOT NULL DEFAULT 'free',
    api_key       TEXT UNIQUE,
    is_active     INTEGER DEFAULT 1,
    created_at    TEXT NOT NULL,
    last_login    TEXT
);

CREATE TABLE IF NOT EXISTS user_sessions (
    session_id   TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    jwt_token    TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_email   ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);

-- Add user_id to tasks if this DB was created before the column existed.
-- SQLite has no IF NOT EXISTS for columns; runner applies this file once.
-- If column already exists (from newer SCHEMA), this migration may fail on old tooling —
-- in that case skip manually or rely on store._ensure_task_user_id_column().
