-- Affiliates + referrals + payout requests (SQLite)
CREATE TABLE IF NOT EXISTS affiliates (
    affiliate_id   TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    referral_code  TEXT NOT NULL UNIQUE,
    commission_pct REAL DEFAULT 20.0,
    total_referred INTEGER DEFAULT 0,
    total_earned   REAL DEFAULT 0.0,
    link_clicks    INTEGER DEFAULT 0,
    is_active      INTEGER DEFAULT 1,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS referrals (
    referral_id     TEXT PRIMARY KEY,
    affiliate_id    TEXT NOT NULL,
    referred_email    TEXT NOT NULL,
    referred_user_id  TEXT,
    status            TEXT DEFAULT 'pending',
    commission_inr    REAL DEFAULT 0.0,
    converted_at      TEXT,
    created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_affiliates_code ON affiliates(referral_code);
CREATE INDEX IF NOT EXISTS idx_referrals_affiliate ON referrals(affiliate_id);
CREATE INDEX IF NOT EXISTS idx_referrals_referred_user ON referrals(referred_user_id);

CREATE TABLE IF NOT EXISTS affiliate_payout_requests (
    request_id    TEXT PRIMARY KEY,
    affiliate_id  TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    upi_id        TEXT NOT NULL,
    amount        REAL NOT NULL,
    status        TEXT DEFAULT 'pending',
    created_at    TEXT NOT NULL
);
