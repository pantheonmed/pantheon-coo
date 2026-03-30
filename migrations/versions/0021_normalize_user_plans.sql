-- Normalize legacy user.plan values: NULL, empty, or 'open' → 'free'
-- (Same logic runs on every app startup via store.normalize_legacy_user_plans.)

UPDATE users SET plan = 'free'
WHERE plan IS NULL
   OR TRIM(COALESCE(plan, '')) = ''
   OR LOWER(TRIM(plan)) = 'open';
