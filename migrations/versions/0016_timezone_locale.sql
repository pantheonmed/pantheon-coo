-- Task 64: timezone + locale on users; schedule timezone
ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT 'Asia/Kolkata';
ALTER TABLE users ADD COLUMN locale TEXT DEFAULT 'en-IN';

ALTER TABLE schedules ADD COLUMN timezone TEXT DEFAULT 'Asia/Kolkata';
