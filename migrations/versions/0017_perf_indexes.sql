-- Task 81 — composite indexes for task/log/analytics queries
-- Safe to run multiple times (IF NOT EXISTS).

CREATE INDEX IF NOT EXISTS idx_tasks_user_created ON tasks(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_logs_task_level ON logs(task_id, level);
CREATE INDEX IF NOT EXISTS idx_analytics_type_user ON analytics_events(event_type, user_id, created_at);
