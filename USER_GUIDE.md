# Pantheon COO OS — User Guide

## What is Pantheon COO OS?

Your **AI Chief Operating Officer**: you describe outcomes in plain language, and the system plans, runs tools, evaluates results, and remembers what worked — in a continuous loop until the job is done or clearly blocked.

## How to write good commands

**Good:** “Check disk space on the server and write a short markdown report under `workspace/reports/`.”

**Bad:** “check disk” — too vague; the COO must guess scope and output.

**Good:** “Write a professional email to supplier@example.com requesting a quotation for 50 units of Product X with delivery to Mumbai by 30 April 2026.”

**Bad:** “write email” — missing recipient, subject context, and constraints.

## Command tips

- State the **outcome** and **success criteria** (what file, what format, what tone).
- Mention **paths** in the workspace when files matter.
- Include **names, amounts, dates, and regions** when relevant.
- Prefer **templates** from the Templates tab for repeated workflows.

## Understanding task status

| Status | Meaning |
|--------|---------|
| **queued** | Accepted, waiting to start |
| **reasoning** | Understanding goal and risks |
| **planning** | Building step-by-step plan |
| **executing** | Running tools/steps |
| **evaluating** | Scoring outcome vs. goal |
| **done** | Completed successfully |
| **failed** | Stopped with error — open logs and retry if appropriate |

## Templates

Templates package proven command patterns (GST reports, content, integrations). Pick one, fill variables, run — faster than rewriting the same instructions.

## Schedules

Automate recurring work, for example: “Every Monday 09:00 Asia/Kolkata — email me a one-paragraph operations summary.” Schedules use the server’s scheduler configuration.

## Projects

For large goals, use **projects** to split work into multiple linked tasks (research, compare, write, notify). See API `POST /projects` and dashboard Projects tab when enabled.

## Getting help

- API reference: `/docs` on your deployment.
- Operator setup: `OPERATOR_GUIDE.md`.
- Security reports: see `SECURITY.md` (do not file security issues publicly).
