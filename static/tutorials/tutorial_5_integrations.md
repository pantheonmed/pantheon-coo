# Integrations overview

**Duration:** ~12 minutes

## Steps

1. Configure keys in `.env` for the integrations you need (WhatsApp, Telegram, Google Sheets, Zapier, etc.).
2. Send a test message or trigger a test webhook.
3. Verify a task was created under **Recent tasks**.

## Example commands

- WhatsApp / Telegram: send a text message to your bot with a short COO goal.
- Zapier: trigger `POST /webhook/zapier` with a `command` body (see docs).

## Expected result

Inbound events become COO tasks; outbound tools post to external systems when configured.
