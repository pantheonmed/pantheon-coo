-- Razorpay billing orders (idempotent)
CREATE TABLE IF NOT EXISTS orders (
    order_id              TEXT PRIMARY KEY,
    user_id               TEXT NOT NULL,
    razorpay_order_id     TEXT,
    razorpay_payment_id   TEXT,
    plan                  TEXT NOT NULL,
    amount                INTEGER NOT NULL,
    currency              TEXT DEFAULT 'INR',
    status                TEXT DEFAULT 'pending',
    created_at            TEXT NOT NULL,
    completed_at          TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_rzp ON orders(razorpay_order_id);
