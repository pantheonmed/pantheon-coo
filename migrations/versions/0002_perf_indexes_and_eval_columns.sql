-- migrations/versions/0002_perf_indexes_and_eval_columns.sql
-- Phase 4 additions: extra columns for performance tracking,
-- confidence score storage, and composite indexes for monitor queries.

-- Store per-task confidence scores (Phase 4 — Confidence Scorer)
-- SQLite ALTER TABLE only supports ADD COLUMN
-- These are no-ops if columns already exist (SQLite ignores IF NOT EXISTS on ALTER)
-- We guard with a separate check in application code.

-- Composite index for monitor queries (goal_type + status + created_at)
CREATE INDEX IF NOT EXISTS idx_tasks_type_status ON tasks(goal_type, status);

-- Index for eval score trending (monitor dashboard sparkline)
CREATE INDEX IF NOT EXISTS idx_tasks_score_date  ON tasks(created_at, eval_score);

-- Index for briefing queries
CREATE INDEX IF NOT EXISTS idx_briefings_date    ON briefings(generated_at DESC);

-- Index for prompt version lookup
CREATE INDEX IF NOT EXISTS idx_prompts_version   ON agent_prompts(agent_name, version DESC);

-- Index for project task lookup
CREATE INDEX IF NOT EXISTS idx_patterns_seq      ON task_patterns(step_sequence);
