# Schedules & cron

**Duration:** ~8 minutes

## Steps

1. From the API docs or dashboard integrations, create a schedule with a natural-language goal.
2. Set timezone and cadence (e.g. daily briefing).
3. Confirm the next run time in the scheduler response.

## Example commands

- `Every weekday at 9:00 Asia/Kolkata, email me a one-paragraph business summary`
- `Weekly on Monday generate a workspace report`

## Expected result

Scheduled jobs appear in the scheduler store and run at the configured times (requires server scheduler enabled).
