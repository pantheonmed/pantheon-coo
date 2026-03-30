# Security

## Reporting a vulnerability

**Do not** open a public GitHub issue for security vulnerabilities.

Please email **security@pantheon.ai** with:

- A short description of the issue
- Steps to reproduce (if possible)
- Impact assessment (if known)
- Your contact for follow-up

We aim to acknowledge receipt within a few business days and will work with you on a coordinated disclosure where appropriate.

## Supported versions

Security fixes are applied to the latest release branch maintained by Pantheon Meditech. Use the newest tagged release or `main` for deployments when possible.

## General practices

- Run with `AUTH_MODE=jwt` in production and a strong `JWT_SECRET`.
- Keep API keys (`ANTHROPIC_API_KEY`, payment keys, webhooks) out of source control; use environment variables or a secrets manager.
- Restrict admin routes to trusted operators only.
