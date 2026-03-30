-- PantheonMed: users.industry (medical | retail | agency | tech | other)
-- New installs get this column from memory/store.py SCHEMA; legacy DBs may get it
-- via store._ensure_user_industry_column() at startup.
-- This migration records version 0008; safe to apply on DBs that already have the column
-- only if you run migrations before first app init — otherwise rely on runtime ensure.
SELECT 1;
