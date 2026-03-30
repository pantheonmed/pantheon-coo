-- Semantic long-term memories (SQLite)
CREATE TABLE IF NOT EXISTS semantic_memories (
    memory_id     TEXT PRIMARY KEY,
    task_id       TEXT,
    owner_user_id TEXT,
    content       TEXT NOT NULL,
    memory_type   TEXT NOT NULL,
    tags_json     TEXT DEFAULT '[]',
    importance    REAL DEFAULT 0.5,
    access_count  INTEGER DEFAULT 0,
    last_accessed TEXT,
    deleted       INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_smem_type ON semantic_memories(memory_type, importance DESC);
