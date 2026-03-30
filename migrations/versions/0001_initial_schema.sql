-- migrations/versions/0001_initial_schema.sql
-- Full initial schema for Pantheon COO OS v2.
-- All statements use IF NOT EXISTS so this is safe to run on an existing DB.

CREATE TABLE IF NOT EXISTS tasks (
    task_id         TEXT PRIMARY KEY,
    command         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'queued',
    loop_iterations INTEGER DEFAULT 0,
    eval_score      REAL,
    goal            TEXT DEFAULT '',
    goal_type       TEXT DEFAULT '',
    plan_json       TEXT DEFAULT '{}',
    results_json    TEXT DEFAULT '[]',
    summary         TEXT DEFAULT '',
    error           TEXT,
    source          TEXT DEFAULT 'api',
    created_at      TEXT NOT NULL,
    completed_at    TEXT
);

CREATE TABLE IF NOT EXISTS logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL,
    level       TEXT NOT NULL DEFAULT 'info',
    message     TEXT NOT NULL,
    data_json   TEXT DEFAULT '{}',
    logged_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learnings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL,
    goal_type   TEXT NOT NULL,
    learning    TEXT NOT NULL,
    score       REAL DEFAULT 0.0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_tools (
    tool_id         TEXT PRIMARY KEY,
    tool_name       TEXT NOT NULL UNIQUE,
    description     TEXT NOT NULL,
    module_path     TEXT NOT NULL,
    trigger_pattern TEXT NOT NULL,
    created_from    TEXT,
    usage_count     INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_patterns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       TEXT NOT NULL,
    goal_type     TEXT,
    step_sequence TEXT NOT NULL,
    recorded_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS briefings (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at         TEXT NOT NULL,
    period_hours         INTEGER DEFAULT 24,
    headline             TEXT DEFAULT '',
    health               TEXT DEFAULT 'unknown',
    sections_json        TEXT DEFAULT '[]',
    recommendations_json TEXT DEFAULT '[]',
    full_text            TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS schedules (
    schedule_id  TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    command      TEXT NOT NULL,
    cron         TEXT NOT NULL DEFAULT '0 * * * *',
    enabled      INTEGER DEFAULT 1,
    last_run_at  TEXT,
    next_run_at  TEXT,
    run_count    INTEGER DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_prompts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name   TEXT NOT NULL,
    goal_type    TEXT NOT NULL,
    prompt_text  TEXT NOT NULL,
    version      INTEGER DEFAULT 1,
    avg_score    REAL DEFAULT 0.0,
    task_count   INTEGER DEFAULT 0,
    is_active    INTEGER DEFAULT 1,
    created_at   TEXT NOT NULL,
    notes        TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS projects (
    project_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    goal         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',
    task_ids     TEXT DEFAULT '[]',
    progress     REAL DEFAULT 0.0,
    created_at   TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tasks_status      ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_goal_type   ON tasks(goal_type);
CREATE INDEX IF NOT EXISTS idx_tasks_created     ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_logs_task         ON logs(task_id);
CREATE INDEX IF NOT EXISTS idx_logs_level        ON logs(level);
CREATE INDEX IF NOT EXISTS idx_learnings_type    ON learnings(goal_type);
CREATE INDEX IF NOT EXISTS idx_learnings_score   ON learnings(score DESC);
CREATE INDEX IF NOT EXISTS idx_custom_tools_name ON custom_tools(tool_name);
CREATE INDEX IF NOT EXISTS idx_patterns_type     ON task_patterns(goal_type);
CREATE INDEX IF NOT EXISTS idx_schedules_enabled ON schedules(enabled);
CREATE INDEX IF NOT EXISTS idx_prompts_agent     ON agent_prompts(agent_name, goal_type, is_active);
CREATE INDEX IF NOT EXISTS idx_projects_status   ON projects(status);
