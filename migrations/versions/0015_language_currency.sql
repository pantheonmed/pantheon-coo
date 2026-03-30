-- Task 58–59: user language, currency, country (SQLite; applied via store._ensure_* at runtime)
ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en';
ALTER TABLE users ADD COLUMN currency TEXT DEFAULT 'INR';
ALTER TABLE users ADD COLUMN country_code TEXT DEFAULT 'IN';

ALTER TABLE orders ADD COLUMN stripe_payment_intent_id TEXT;
ALTER TABLE orders ADD COLUMN payment_gateway TEXT DEFAULT 'razorpay';
