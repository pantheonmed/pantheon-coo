CREATE TABLE IF NOT EXISTS marketplace_tools (
    tool_id        TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT NOT NULL,
    author_user_id TEXT NOT NULL,
    price_inr      INTEGER DEFAULT 0,
    category       TEXT DEFAULT 'general',
    downloads      INTEGER DEFAULT 0,
    rating         REAL DEFAULT 0.0,
    code           TEXT NOT NULL,
    is_approved    INTEGER DEFAULT 0,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_purchases (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id      TEXT NOT NULL,
    buyer_id     TEXT NOT NULL,
    amount       INTEGER DEFAULT 0,
    author_share INTEGER DEFAULT 0,
    platform_share INTEGER DEFAULT 0,
    purchased_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_marketplace_approved ON marketplace_tools(is_approved, category);
CREATE INDEX IF NOT EXISTS idx_tool_purchases_buyer ON tool_purchases(buyer_id);
