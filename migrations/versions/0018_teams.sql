CREATE TABLE IF NOT EXISTS teams (
    team_id      TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    owner_id     TEXT NOT NULL,
    plan         TEXT NOT NULL DEFAULT 'starter',
    invite_code  TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_members (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id      TEXT NOT NULL,
    user_id      TEXT NOT NULL,
    role         TEXT DEFAULT 'member',
    joined_at    TEXT NOT NULL,
    UNIQUE(team_id, user_id)
);

CREATE TABLE IF NOT EXISTS team_tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id      TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    assigned_to  TEXT DEFAULT '',
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id);
CREATE INDEX IF NOT EXISTS idx_team_tasks_team ON team_tasks(team_id);
